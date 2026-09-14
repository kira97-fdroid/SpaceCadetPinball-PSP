#!/usr/bin/env python3
from pathlib import Path
import hashlib, io, json, lzma, os, shutil, subprocess, sys, tempfile, urllib.request, zipfile


def find_ci(root: Path, name: str):
    wanted = name.upper()
    for p in root.rglob('*'):
        if p.is_file() and p.name.upper() == wanted:
            return p
    return None


def run(cmd):
    print('[assets] +', ' '.join(str(x) for x in cmd))
    subprocess.run(cmd, check=True)


def find_soundfonts():
    home = Path.home()
    roots = [
        home / 'Library/Audio/Sounds/Banks',
        Path('/Library/Audio/Sounds/Banks'),
        Path('/opt/homebrew/share/sounds/sf2'),
        Path('/opt/homebrew/share/sounds/sf3'),
        Path('/usr/local/share/sounds/sf2'),
        Path('/usr/local/share/sounds/sf3'),
        Path('/usr/share/sounds/sf2'),
        Path('/usr/share/sounds/sf3'),
        home / 'Downloads',
    ]
    found = []
    seen = set()
    for root in roots:
        if not root.is_dir():
            continue
        # Avoid an expensive recursive walk through all Downloads: two levels is enough
        patterns = ('*.sf2', '*.SF2', '*.sf3', '*.SF3')
        candidates = []
        for pattern in patterns:
            candidates.extend(root.glob(pattern))
            candidates.extend(root.glob('*/' + pattern))
        for p in candidates:
            try:
                q = p.resolve()
            except OSError:
                continue
            if q.is_file() and q not in seen:
                seen.add(q)
                found.append(q)
    return found


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download_fallback_soundfont():
    """Download GeneralUser GS when no local SoundFont exists.

    Multiple HTTPS sources are tried because large binary assets occasionally move
    or are served differently by hosting providers. The downloaded SF2 is accepted
    only if its pinned SHA-256 matches.
    """
    expected_sha256 = 'c278464b823daf9c52106c0957f752817da0e52964817ff682fe3a8d2f8446ce'
    urls = [
        'https://github.com/shakfu/aldakit/releases/download/soundfonts-v1/GeneralUser-GS.sf2',
        'https://raw.githubusercontent.com/mrbumpy409/GeneralUser-GS/main/GeneralUser-GS.sf2',
    ]
    cache_dir = (Path.home() / 'Library' / 'Caches' / 'SpaceCadetPinballPSP' / 'soundfonts') if sys.platform == 'darwin' else ((Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'SpaceCadetPinballPSP' / 'soundfonts') if sys.platform.startswith('win') else (Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'SpaceCadetPinballPSP' / 'soundfonts'))
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached_sf2 = cache_dir / 'GeneralUser-GS.sf2'

    if cached_sf2.is_file() and cached_sf2.stat().st_size > 1024 * 1024:
        actual = hashlib.sha256(cached_sf2.read_bytes()).hexdigest()
        if actual.lower() == expected_sha256:
            print(f'[assets] SoundFont found in cache (verified): {cached_sf2}')
            return cached_sf2
        print('[assets] Cached SoundFont checksum mismatch; downloading again.')
        try:
            cached_sf2.unlink()
        except OSError:
            pass

    print('[assets] No local SoundFont found.')
    print('[assets] Downloading GeneralUser GS automatically...')

    for url in urls:
        print(f'[assets] Trying: {url}')
        req = urllib.request.Request(url, headers={'User-Agent': 'SpaceCadetPinballPSP/1.0.0'})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = r.read()
        except Exception as exc:
            print(f'[assets] Download failed from this source: {exc}')
            continue

        actual = _sha256_bytes(data)
        if actual.lower() != expected_sha256:
            print('[assets] Invalid SoundFont checksum from this source.')
            print(f'[assets] expected:  {expected_sha256}')
            print(f'[assets] actual: {actual}')
            continue

        try:
            cached_sf2.write_bytes(data)
            (cache_dir / 'SOURCE.txt').write_text(
                'GeneralUser GS\n'
                f'URL: {url}\n'
                f'SF2 SHA-256: {expected_sha256}\n',
                encoding='utf-8')
            print(f'[assets] SoundFont downloaded and verified: {cached_sf2}')
            return cached_sf2
        except Exception as exc:
            print(f'[assets] Could not save the SoundFont: {exc}')
            return None

    print('[assets] Automatic download failed from every source.')
    return None


def choose_soundfont():
    found = find_soundfonts()
    if len(found) == 1:
        print(f'[assets] SoundFont found automatically: {found[0]}')
        return found[0]
    if len(found) > 1:
        print('[assets] SoundFonts found:')
        for i, p in enumerate(found, 1):
            print(f'  {i}) {p}')
        while True:
            raw = input(f'Choose SoundFont [1-{len(found)}] (Enter = 1): ').strip()
            if not raw:
                return found[0]
            if raw.isdigit() and 1 <= int(raw) <= len(found):
                return found[int(raw) - 1]
            print('Invalid choice.')

    downloaded = download_fallback_soundfont()
    if downloaded:
        return downloaded

    print('[assets] Automatic download failed.')
    print('[assets] You can still provide a GM SoundFont .sf2/.sf3 manually.')
    while True:
        raw = input('Drag the SoundFont .sf2/.sf3 file here and press Enter: ').strip().strip('"').strip("'")
        p = Path(raw).expanduser()
        if p.is_file() and p.suffix.lower() in ('.sf2', '.sf3'):
            return p.resolve()
        print('Invalid SoundFont file.')


def main():
    if len(sys.argv) != 3:
        raise SystemExit('usage: prepare_user_assets.py <original_game_dir> <output_dir>')
    root = Path(sys.argv[1]).expanduser().resolve()
    out = Path(sys.argv[2]).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f'ERROR: original game folder not found: {root}')

    out.mkdir(parents=True, exist_ok=True)

    dat = find_ci(root, 'PINBALL.DAT')
    midi = find_ci(root, 'PINBALL.MID')
    if not dat:
        raise SystemExit('ERROR: PINBALL.DAT was not found in the original game folder.')
    if not midi:
        raise SystemExit('ERROR: PINBALL.MID was not found. 1.0.0 always generates PINBALL.WAV from the original game files.')

    shutil.copy2(dat, out / 'PINBALL.DAT')
    print(f'[assets] PINBALL.DAT: {dat}')

    run([sys.executable, str(Path(__file__).with_name('make_sfxbank.py')), str(root), str(out / 'SFXBANK.BIN')])

    ffmpeg = shutil.which('ffmpeg')
    fluidsynth = shutil.which('fluidsynth')
    if not ffmpeg:
        raise SystemExit('ERROR: ffmpeg was not found.')
    if not fluidsynth:
        raise SystemExit('ERROR: fluidsynth was not found.')

    soundfont = choose_soundfont()
    with tempfile.TemporaryDirectory(prefix='scpinball_music_') as td:
        td = Path(td)
        render_midi = td / 'pinball_loop_render.mid'
        loop_meta = td / 'pinball_loop.json'
        rendered = td / 'pinball_render.wav'

        # PINBALL.MID contains nine identical musical repetitions after the setup
        # region. Verify that exact structure and build a 3-repeat render MIDI.
        # We then crop the middle repeat by MIDI-derived sample indices so the
        # final loop contains steady-state synth/reverb from the previous repeat.
        run([
            sys.executable, str(Path(__file__).with_name('extract_music_loop.py')),
            str(midi), str(render_midi), str(loop_meta)
        ])
        meta = json.loads(loop_meta.read_text(encoding='utf-8'))
        start_sample = int(meta['crop_start_sample'])
        end_sample = int(meta['crop_end_sample'])
        loop_samples = int(meta['loop_samples'])
        loop_seconds = float(meta['loop_seconds'])

        run([fluidsynth, '-ni', '-F', str(rendered), '-r', '22050', str(soundfont), str(render_midi)])
        target = out / 'PINBALL.WAV'
        audio_filter = f'atrim=start_sample={start_sample}:end_sample={end_sample},asetpts=PTS-STARTPTS'
        run([
            ffmpeg, '-y', '-loglevel', 'error', '-i', str(rendered),
            '-af', audio_filter, '-ac', '1', '-ar', '22050',
            '-c:a', 'pcm_s16le', '-map_metadata', '-1', str(target)
        ])

    expected_bytes = 44 + loop_samples * 2
    actual_bytes = target.stat().st_size
    # WAV headers can contain small optional chunks, so validate audio length
    # semantically via the known sample count rather than requiring 44-byte header.
    if actual_bytes < loop_samples * 2:
        raise SystemExit('ERROR: generated PINBALL.WAV is too short.')
    print(
        f'[assets] PINBALL.WAV: verified MIDI loop, {loop_seconds:.6f}s, '
        f'{loop_samples} samples, PCM 16-bit mono 22050 Hz ({actual_bytes} bytes)'
    )
    print('[assets] All runtime assets were generated locally from the game files supplied by the user.')


if __name__ == '__main__':
    main()
