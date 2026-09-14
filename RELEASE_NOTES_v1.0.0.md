# Space Cadet Pinball PSP v1.0.0

The first stable public release of the native PSP port of **3D Pinball - Space Cadet**, based on the open-source [k4zmu2a/SpaceCadetPinball](https://github.com/k4zmu2a/SpaceCadetPinball) project.

## Highlights

- Native PSP port — **not emulation**.
- 120 Hz physics.
- 30 / 60 FPS rendering, **60 FPS default**.
- DIRTY + BGR565 optimized PSP presentation.
- Fast startup.
- MUSIC OFF and SFX ON by default.
- Selectable 222 / 266 / 300 / 333 MHz CPU clock, **266 MHz by default**.
- FPS counter and benchmark overlay.
- Direct PSP controls and HOME-menu exit support.
- Automatic builders for **macOS, Linux and native Windows**.
- Copyright-clean distribution: no original Microsoft game data is included.

## Original game files required

You must provide your own original **3D Pinball - Space Cadet** installation containing:

- `PINBALL.DAT`
- `PINBALL.MID`
- the original `SOUND*.WAV` files

The guided builder locally generates the PSP runtime files. Do **not** upload your generated `output/` folder to the public GitHub release unless you have the rights to redistribute those game assets.

## PSP installation

After a successful build, copy these files from `output/` to:

`ms0:/PSP/GAME/SpaceCadetPinball/`

- `EBOOT.PBP`
- `PINBALL.DAT`
- `SFXBANK.BIN`
- `PINBALL.WAV`

## Build

See `INSTRUCTIONS.md` for macOS, Linux and Windows instructions. The platform launchers can bootstrap the PSP development environment automatically.

## Credits

- **k4zmu2a / SpaceCadetPinball** — reverse-engineering/decompilation and cross-platform SDL codebase on which this port is based.
- **PSPDEV / PSPSDK** and the SDL2/SDL2_mixer ecosystem.
- This PSP port was developed with substantial AI assistance for code generation, analysis, refactoring and debugging, combined with iterative testing on real PSP hardware.

Feedback and bug reports are welcome.
