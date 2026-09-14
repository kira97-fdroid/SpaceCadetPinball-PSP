# Space Cadet Pinball PSP — Instructions

This package builds a native PSP version of **3D Pinball - Space Cadet** from the open-source SpaceCadetPinball project. The original copyrighted game data is **not included**. You must provide your own original game files.

## PSP controls

| PSP control | Action |
| --- | --- |
| **X (Cross)** | Pull/release the plunger |
| **L** | Left flipper |
| **R** | Right flipper |
| **D-Pad Left** | Nudge table left |
| **D-Pad Right** | Nudge table right |
| **D-Pad Up** | Forward/bottom table nudge |
| **START** | Pause / resume |
| **SELECT** | Start a new game |
| **TRIANGLE** | Open / close Options |
| **HOME** | Exit through the PSP system menu |

### Options menu

- **D-Pad Up / Down:** move through the options.
- **X (Cross):** select/toggle the highlighted option.
- **D-Pad Left / Right:** change values such as VIDEO and CPU clock.
- **TRIANGLE:** go back to the game.
- The menu footer shows `TRIANGLE BACK    X SELECT`.
- **FPS** and **BENCHMARK** are mutually exclusive. Enabling one automatically disables the other.

## Original files required

The folder you give to the builder must come from your own original **3D Pinball - Space Cadet** installation and contain:

- `PINBALL.DAT`
- `PINBALL.MID`
- the original `SOUND*.WAV` files

The builder creates these PSP runtime files locally:

```text
EBOOT.PBP
PINBALL.DAT
SFXBANK.BIN
PINBALL.WAV
```

`SFXBANK.BIN` is generated from the original sound effects. `PINBALL.WAV` is generated from the original MIDI using the verified loop structure and a SoundFont. If a suitable SoundFont is not already installed, the builder downloads and verifies GeneralUser GS into a local user cache.

## Automatic toolchain setup

You do **not** need to install PSPSDK manually before starting. On macOS/Linux the launchers check `psp-gcc`, `psp-cmake` and `psp-pacman`. On Windows the launcher checks the native `pspdev-win` toolchain and its prebuilt PSP libraries; the project build deliberately does not use `psp-pacman` on Windows.

The first build may take substantially longer because dependencies and PSPDEV may need to be downloaded or built. Later builds reuse the installed environment.

Internet access is required during the first setup and for the clean upstream checkout.

## Build on macOS

From this package directory run:

```bash
chmod +x build_macos.sh build_from_scratch.sh
./build_macos.sh
```

The script will automatically:

1. install Homebrew if it is missing;
2. install the required host packages, including FFmpeg and FluidSynth;
3. install PSPDEV/PSPSDK into `$HOME/pspdev` if necessary;
4. prefer the latest official PSPDEV prebuilt archive for Apple Silicon or Intel;
5. fall back to the official PSPDEV source installer if no compatible prebuilt archive is available;
6. remove macOS Gatekeeper quarantine attributes from PSPDEV when required;
7. start the game/asset builder.

When prompted, drag your original Space Cadet game folder into Terminal and press **Enter**.

## Build on Linux

Run:

```bash
chmod +x build_linux.sh build_from_scratch.sh
./build_linux.sh
```

The launcher supports `apt`, `dnf`, and `pacman` for host packages. It installs PSPDEV/PSPSDK automatically into `$HOME/pspdev` unless `PSPDEV` points elsewhere. On Ubuntu/x86_64 it recognizes the official `pspdev-ubuntu-latest-x86_64.tar.gz` release and prefers that prebuilt toolchain instead of compiling GCC locally.

An existing complete PSPDEV installation is reused. If `psp-pacman` is missing but the compiler/SDK and every PSP library required by this port are already installed, the launcher also reuses that environment instead of rebuilding the toolchain.

A source-toolchain build is now only an emergency fallback. It defaults to **1 parallel job** to avoid exhausting RAM and freezing low-memory systems. Advanced users can override it with `PSPDEV_BUILD_JOBS=N`. The normal game build defaults to 2 jobs on Linux and can be overridden with `JOBS=N`.

## Build on Windows — no WSL required

Open PowerShell in this package folder and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build_windows.ps1
```

The Windows launcher is native and **does not use WSL**. It will automatically:

1. detect MSYS2;
2. install MSYS2 through `winget` if it is missing;
3. install/update the required MSYS2 packages;
4. download the latest prebuilt [`dmang-dev/pspdev-win`](https://github.com/dmang-dev/pspdev-win) toolchain into `C:\pspdev` if needed;
5. verify the bundled SDL2/SDL2_mixer and dependent PSP static libraries, automatically overlaying the libraries-only bundle if the installation is incomplete;
6. run the shared PSP builder inside the native MSYS2 environment without invoking `psp-pacman`.

`pspdev-win` is a third-party Windows PSPDEV toolchain project. It supplies the PSP compiler, PSPSDK, host tools and a prebuilt PSP library bundle for MSYS2 without requiring WSL, Docker or a Linux virtual machine.

For reliability, the Windows launcher downloads the exact pinned SpaceCadetPinball source ZIP with native PowerShell and then lets MSYS2 extract it. It does not use `git clone` for the upstream checkout on Windows.

If Windows does not provide `winget`, install MSYS2 manually from https://www.msys2.org/ and rerun `build_windows.ps1`; the PSPDEV toolchain installation remains automatic.

When prompted, enter the Windows path to your original game folder, for example:

```text
C:\Users\YourName\Downloads\Pinball
```

## Build output

After a successful build, the PSP-ready files are in this package's:

```text
output/
```

The generated files are:

```text
EBOOT.PBP
PINBALL.DAT
SFXBANK.BIN
PINBALL.WAV
```

## Install on the PSP

Create this folder on the PSP Memory Stick:

```text
PSP/GAME/SpaceCadetPinball/
```

Copy these **four files from `output/`** into it:

```text
PSP/GAME/SpaceCadetPinball/EBOOT.PBP
PSP/GAME/SpaceCadetPinball/PINBALL.DAT
PSP/GAME/SpaceCadetPinball/SFXBANK.BIN
PSP/GAME/SpaceCadetPinball/PINBALL.WAV
```

The final PSP folder should look like:

```text
PSP/
└── GAME/
    └── SpaceCadetPinball/
        ├── EBOOT.PBP
        ├── PINBALL.DAT
        ├── SFXBANK.BIN
        └── PINBALL.WAV
```

Safely disconnect the PSP, then launch **Space Cadet Pinball** from the PSP Game menu.

## Default settings

- Physics: **120 Hz**
- Video: **60 FPS**
- CPU clock: **266 MHz**
- Music: **OFF**
- SFX: **ON**
- FPS counter: **OFF**
- Benchmark: **OFF**

Settings are stored in the PSP-side `psp_options.cfg`. Existing saved settings take precedence over defaults.

## Notes

If the CPU status in the benchmark shows `LOCKED`, your CFW or a plugin is overriding the selected PSP CPU clock. The port does not attempt to bypass CFW clock control.

Do not redistribute the generated original/derived game assets unless you have the rights to do so. For public distribution, use this clean source/builder package.


## Windows build-path compatibility
The Windows launcher installs and uses UCRT64 CMake + Ninja. This is intentional: native CMake passes real Windows paths to `psp-gcc`, avoiding MSYS-only `/tmp/...` paths that the compiler front-end cannot resolve reliably. A small `psp-gcc` preflight compile runs before the full project build.
