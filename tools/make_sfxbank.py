#!/usr/bin/env python3
from pathlib import Path
import struct, sys
MAGIC=b'SPFXPK1\0'

def main():
    if len(sys.argv) != 3:
        raise SystemExit('usage: make_sfxbank.py <original_game_dir> <output.bin>')
    root=Path(sys.argv[1]).expanduser().resolve()
    out=Path(sys.argv[2]).expanduser().resolve()
    waves=sorted((p for p in root.rglob('*') if p.is_file() and p.name.upper().startswith('SOUND') and p.suffix.upper()=='.WAV'), key=lambda p:p.name.upper())
    if not waves:
        raise SystemExit('ERROR: no SOUND*.WAV files found in original game directory')
    names={}
    for p in waves:
        key=p.name.upper()
        if len(key.encode('ascii','strict'))>15:
            raise SystemExit(f'ERROR: SFX filename too long for bank index: {p.name}')
        names[key]=p
    waves=[names[k] for k in sorted(names)]
    header_size=12+24*len(waves)
    blobs=[]; entries=[]; pos=header_size
    for p in waves:
        data=p.read_bytes()
        if data[:4] != b'RIFF' or data[8:12] != b'WAVE':
            raise SystemExit(f'ERROR: not a RIFF WAVE file: {p}')
        name=p.name.upper().encode('ascii')
        entries.append((name,pos,len(data)))
        blobs.append(data); pos += len(data)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('wb') as f:
        f.write(MAGIC); f.write(struct.pack('<I',len(entries)))
        for name,offset,size in entries:
            f.write(name+b'\0'*(16-len(name)))
            f.write(struct.pack('<II',offset,size))
        for data in blobs: f.write(data)
    print(f'[assets] SFXBANK.BIN: {len(entries)} WAVs, {out.stat().st_size} bytes')
if __name__=='__main__': main()
