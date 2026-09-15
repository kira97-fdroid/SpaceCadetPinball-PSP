# Space Cadet Pinball PSP v1.0.1

Maintenance release of the native PSP port of **3D Pinball - Space Cadet**.

## Changes from v1.0.0

- Added a long-term archival fallback for the exact pinned upstream SpaceCadetPinball revision.
- The builders still use the original `k4zmu2a/SpaceCadetPinball` repository first.
- If the original upstream source is unavailable, macOS/Linux and Windows automatically retry from [`kira97-fdroid/SpaceCadetPinball-upstream-snapshot`](https://github.com/kira97-fdroid/SpaceCadetPinball-upstream-snapshot).
- Both the original upstream and the archival mirror are pinned to commit `cb9b7b886244a27773f66b0b19fdc2998392565e`.
- Updated all current release/build version strings to **v1.0.1**.
- Updated the PSP `EBOOT.PBP` version metadata from `01.000` to **`01.001`**.
- Updated README, instructions and licensing documentation for the archival fallback.
- No gameplay, physics, rendering, control or audio behavior was intentionally changed from v1.0.0.

## Core configuration

- Native PSP port — **not emulation**.
- 120 Hz physics.
- 30 / 60 FPS rendering, **60 FPS default**.
- MUSIC OFF and SFX ON by default.
- Selectable 222 / 266 / 300 / 333 MHz CPU clock, **266 MHz by default**.
- Copyright-clean distribution: no original Microsoft game data or audio is included.

## Original game files required

You must provide your own original **3D Pinball - Space Cadet** installation containing:

- `PINBALL.DAT`
- `PINBALL.MID`
- the original `SOUND*.WAV` files

The builder generates the required PSP runtime files locally.

## Licensing

The PSP-specific additions are MIT-licensed under this repository's `LICENSE`.
The upstream SpaceCadetPinball project remains under its original MIT license and attribution.
The archival mirror preserves that exact upstream revision and does not change its ownership or licensing.

Feedback and real-hardware test results are welcome.
