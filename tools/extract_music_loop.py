#!/usr/bin/env python3
"""Extract a deterministic render MIDI for the original Space Cadet music loop.

The original PINBALL.MID contains a two-second setup region followed by nine
identical copies of the same musical block. This tool verifies that structure
before writing a temporary MIDI containing setup state plus three copies of the
verified loop. The asset builder renders all three copies and crops the middle
copy by exact MIDI-derived timing, so the final PCM loop already contains the
steady-state synth/reverb tail from the preceding iteration.

No silence detection or audio heuristics are used.
"""
from __future__ import annotations

from dataclasses import dataclass
import argparse
import hashlib
import json
from pathlib import Path
import struct
from typing import Iterable

LOOP_START_TICK = 1920
LOOP_LENGTH_TICKS = 53760
LOOP_END_TICK = LOOP_START_TICK + LOOP_LENGTH_TICKS
EXPECTED_REPEATS = 9
OUTPUT_REPEATS = 3
TARGET_RATE = 22050


@dataclass(frozen=True)
class Event:
    tick: int
    kind: str  # midi, meta, sysex
    code: int
    data: bytes
    order: int


def read_vlq(buf: bytes, pos: int) -> tuple[int, int]:
    value = 0
    for _ in range(4):
        if pos >= len(buf):
            raise ValueError("truncated VLQ")
        b = buf[pos]
        pos += 1
        value = (value << 7) | (b & 0x7F)
        if not (b & 0x80):
            return value, pos
    raise ValueError("invalid VLQ")


def write_vlq(value: int) -> bytes:
    if value < 0 or value > 0x0FFFFFFF:
        raise ValueError(f"VLQ out of range: {value}")
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append(0x80 | (value & 0x7F))
        value >>= 7
    return bytes(reversed(out))


def parse_track(track: bytes) -> list[Event]:
    pos = 0
    tick = 0
    running_status = None
    events: list[Event] = []
    order = 0
    while pos < len(track):
        delta, pos = read_vlq(track, pos)
        tick += delta
        if pos >= len(track):
            raise ValueError("truncated event")
        first = track[pos]
        if first < 0x80:
            if running_status is None:
                raise ValueError("running status without previous channel status")
            status = running_status
            first_data = first
            pos += 1
        else:
            status = first
            first_data = None
            pos += 1
            if status < 0xF0:
                running_status = status
            elif status in (0xF0, 0xF7, 0xFF):
                running_status = None

        if status == 0xFF:
            if pos >= len(track):
                raise ValueError("truncated meta event")
            meta_type = track[pos]
            pos += 1
            length, pos = read_vlq(track, pos)
            payload = track[pos:pos + length]
            if len(payload) != length:
                raise ValueError("truncated meta payload")
            pos += length
            events.append(Event(tick, "meta", meta_type, payload, order))
        elif status in (0xF0, 0xF7):
            length, pos = read_vlq(track, pos)
            payload = track[pos:pos + length]
            if len(payload) != length:
                raise ValueError("truncated sysex payload")
            pos += length
            events.append(Event(tick, "sysex", status, payload, order))
        else:
            high = status & 0xF0
            data_len = 1 if high in (0xC0, 0xD0) else 2
            vals = bytearray()
            if first_data is not None:
                vals.append(first_data)
            need = data_len - len(vals)
            if pos + need > len(track):
                raise ValueError("truncated MIDI event")
            vals.extend(track[pos:pos + need])
            pos += need
            events.append(Event(tick, "midi", status, bytes(vals), order))
        order += 1
    return events


def parse_midi(path: Path):
    data = path.read_bytes()
    if len(data) < 14 or data[:4] != b"MThd":
        raise ValueError("not a Standard MIDI File")
    header_len = struct.unpack(">I", data[4:8])[0]
    if header_len < 6 or 8 + header_len > len(data):
        raise ValueError("invalid MIDI header")
    fmt, ntracks, division = struct.unpack(">HHH", data[8:14])
    if division & 0x8000:
        raise ValueError("SMPTE time division is not supported")
    pos = 8 + header_len
    tracks = []
    for index in range(ntracks):
        if pos + 8 > len(data) or data[pos:pos + 4] != b"MTrk":
            raise ValueError(f"missing MTrk chunk {index}")
        length = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        payload = data[pos + 8:pos + 8 + length]
        if len(payload) != length:
            raise ValueError(f"truncated MTrk chunk {index}")
        tracks.append(parse_track(payload))
        pos += 8 + length
    return fmt, division, tracks


def event_key(event: Event, relative_tick: int):
    return relative_tick, event.kind, event.code, event.data


def block_signature(tracks: list[list[Event]], start: int, end: int):
    sig = []
    for ti, track in enumerate(tracks):
        for event in track:
            if start <= event.tick < end and not (event.kind == "meta" and event.code == 0x2F):
                sig.append((ti,) + event_key(event, event.tick - start))
    return tuple(sig)


def verify_original_structure(tracks: list[list[Event]]):
    base = block_signature(tracks, LOOP_START_TICK, LOOP_END_TICK)
    if not base:
        raise ValueError("expected loop block contains no events")
    base_hash = hashlib.sha256(repr(base).encode("utf-8")).hexdigest()
    hashes = [base_hash]
    for rep in range(1, EXPECTED_REPEATS):
        start = LOOP_START_TICK + rep * LOOP_LENGTH_TICKS
        end = start + LOOP_LENGTH_TICKS
        current = block_signature(tracks, start, end)
        current_hash = hashlib.sha256(repr(current).encode("utf-8")).hexdigest()
        hashes.append(current_hash)
        if current != base:
            raise ValueError(
                f"PINBALL.MID structure mismatch: repetition {rep + 1}/{EXPECTED_REPEATS} "
                "is not identical to the first musical block"
            )
    final_tick = LOOP_START_TICK + EXPECTED_REPEATS * LOOP_LENGTH_TICKS
    for ti, track in enumerate(tracks):
        eot_ticks = [e.tick for e in track if e.kind == "meta" and e.code == 0x2F]
        if not eot_ticks or eot_ticks[-1] != final_tick:
            raise ValueError(f"track {ti}: unexpected End-of-Track position")
    return base, hashes


def tempo_events_for_block(tracks: list[list[Event]]):
    events = []
    for track in tracks:
        for e in track:
            if LOOP_START_TICK <= e.tick < LOOP_END_TICK and e.kind == "meta" and e.code == 0x51:
                if len(e.data) != 3:
                    raise ValueError("invalid tempo meta event")
                events.append((e.tick - LOOP_START_TICK, int.from_bytes(e.data, "big")))
    events.sort()
    if not events or events[0][0] != 0:
        raise ValueError("loop does not define tempo at its first tick")
    return events


def duration_seconds(division: int, tempos: list[tuple[int, int]]) -> float:
    total = 0.0
    pos = 0
    tempo = 500000
    for tick, new_tempo in tempos:
        if tick < pos:
            raise ValueError("non-monotonic tempo map")
        total += (tick - pos) * tempo / division / 1_000_000.0
        pos = tick
        tempo = new_tempo
    total += (LOOP_LENGTH_TICKS - pos) * tempo / division / 1_000_000.0
    return total


def serialize_event(event: Event) -> bytes:
    if event.kind == "midi":
        return bytes([event.code]) + event.data
    if event.kind == "meta":
        return b"\xFF" + bytes([event.code]) + write_vlq(len(event.data)) + event.data
    if event.kind == "sysex":
        return bytes([event.code]) + write_vlq(len(event.data)) + event.data
    raise ValueError(event.kind)


def is_note_event(event: Event) -> bool:
    return event.kind == "midi" and (event.code & 0xF0) in (0x80, 0x90)


def setup_events(track: list[Event]) -> list[Event]:
    # Preserve deterministic pre-loop synth/channel state, but never carry notes.
    # Track/instrument names are harmless and useful when inspecting the temp MIDI.
    out = []
    for e in track:
        if e.tick >= LOOP_START_TICK:
            break
        if e.kind == "meta" and e.code == 0x2F:
            continue
        if is_note_event(e):
            continue
        out.append(Event(0, e.kind, e.code, e.data, e.order))
    return out


def write_render_midi(path: Path, fmt: int, division: int, tracks: list[list[Event]]):
    chunks = []
    for track in tracks:
        out_events = []
        order_counter = 0
        for e in setup_events(track):
            out_events.append((0, order_counter, e))
            order_counter += 1
        block = [e for e in track if LOOP_START_TICK <= e.tick < LOOP_END_TICK and not (e.kind == "meta" and e.code == 0x2F)]
        for rep in range(OUTPUT_REPEATS):
            base_tick = rep * LOOP_LENGTH_TICKS
            for e in block:
                shifted = Event(base_tick + (e.tick - LOOP_START_TICK), e.kind, e.code, e.data, e.order)
                out_events.append((shifted.tick, order_counter, shifted))
                order_counter += 1
        # Stable ordering keeps setup first, then original event order at equal ticks.
        out_events.sort(key=lambda item: (item[0], item[1]))
        payload = bytearray()
        last_tick = 0
        for tick, _, e in out_events:
            payload += write_vlq(tick - last_tick)
            payload += serialize_event(e)
            last_tick = tick
        final_tick = OUTPUT_REPEATS * LOOP_LENGTH_TICKS
        payload += write_vlq(final_tick - last_tick)
        payload += b"\xFF\x2F\x00"
        chunks.append(b"MTrk" + struct.pack(">I", len(payload)) + payload)
    header = b"MThd" + struct.pack(">IHHH", 6, fmt, len(chunks), division)
    path.write_bytes(header + b"".join(chunks))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input_midi", type=Path)
    ap.add_argument("output_midi", type=Path)
    ap.add_argument("metadata_json", type=Path)
    args = ap.parse_args()

    fmt, division, tracks = parse_midi(args.input_midi)
    if fmt != 1 or division != 480 or len(tracks) != 5:
        raise SystemExit(
            f"ERROR: PINBALL.MID inatteso (format={fmt}, tracks={len(tracks)}, division={division}); "
            "non applico euristiche"
        )
    _, hashes = verify_original_structure(tracks)
    tempos = tempo_events_for_block(tracks)
    loop_seconds = duration_seconds(division, tempos)
    expected = 58.434768
    if abs(loop_seconds - expected) > 0.000001:
        raise SystemExit(f"ERROR: durata loop inattesa: {loop_seconds:.9f}s")

    args.output_midi.parent.mkdir(parents=True, exist_ok=True)
    write_render_midi(args.output_midi, fmt, division, tracks)

    loop_samples = round(loop_seconds * TARGET_RATE)
    metadata = {
        "loop_start_tick": LOOP_START_TICK,
        "loop_end_tick": LOOP_END_TICK,
        "loop_length_ticks": LOOP_LENGTH_TICKS,
        "original_repetitions": EXPECTED_REPEATS,
        "verified_block_sha256": hashes[0],
        "all_block_sha256": hashes,
        "division": division,
        "loop_seconds": loop_seconds,
        "target_rate": TARGET_RATE,
        "loop_samples": loop_samples,
        "render_repetitions": OUTPUT_REPEATS,
        "crop_start_sample": loop_samples,
        "crop_end_sample": loop_samples * 2,
    }
    args.metadata_json.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(
        f"[loop] verified {EXPECTED_REPEATS} identical MIDI blocks; "
        f"loop tick {LOOP_START_TICK}->{LOOP_END_TICK}, {loop_seconds:.6f}s, "
        f"{loop_samples} samples @ {TARGET_RATE} Hz"
    )


if __name__ == "__main__":
    main()
