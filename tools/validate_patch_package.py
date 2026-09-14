#!/usr/bin/env python3
from pathlib import Path
import ast, re, sys
root=Path(__file__).resolve().parents[1]
py=list((root/"psp_patches").glob("*.py"))+[root/"apply_psp_port.py"]
for p in py: ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
joined="\n".join(p.read_text(encoding="utf-8") for p in py)
for bad in ("patch_psp_sfx_direct_pcm_055","patch_pb_startup_detail_053","patch_table_startup_detail_053","apply_psp_clean_057"):
    if bad in joined: raise SystemExit(f"legacy symbol remains: {bad}")
if "renderAccumulatorMs -= renderStepMs" not in (root/"templates"/"winmain_psp_loop.cpp.inc").read_text(): raise SystemExit("frame pacing remainder fix missing")
support_template=(root/"templates"/"winmain_psp_support.cpp.inc").read_text()
if 'PspDrawText(renderer, 248, 144, PspVideoProfileName(videoProfile), 2)' not in support_template: raise SystemExit("VIDEO value scale != 2")
if 'TRIANGLE BACK    X SELECT' not in support_template: raise SystemExit("Options control footer missing")
loop_template=(root/"templates"/"winmain_psp_loop.cpp.inc").read_text()
if '(options::Options.FramesPerSecond >= 60 ? 1 : 0)' not in loop_template: raise SystemExit("Options VIDEO display is not derived from active FPS")
opts=(root/"templates"/"winmain_psp_options.cpp.inc").read_text()
if "Options.Music = false;" not in opts: raise SystemExit("default MUSIC is not OFF")
if "Options.Sounds = true;" not in opts: raise SystemExit("default SFX is not ON")
if "Options.Resolution = 1;" not in opts or "Options.FramesPerSecond = 60;" not in opts: raise SystemExit("default VIDEO is not 60 FPS")
support=(root/"templates"/"winmain_psp_support.cpp.inc").read_text()
loop=(root/"templates"/"winmain_psp_loop.cpp.inc").read_text()
for required in ("PspShowBenchmark", "PspDrawBenchmarkOverlay", "scePowerGetBatteryTemp", "scePowerGetCpuClockFrequencyInt", "sceKernelTotalFreeMemSize", '"benchmark="'):
    if required not in support: raise SystemExit(f"benchmark support missing: {required}")
if "PspSetBenchmarkEnabled" not in loop or "PspBenchmark.cpuLoadPct" not in loop or "PspBenchmark.gpuLoadPct" not in loop: raise SystemExit("benchmark runtime timing missing")

if "if (enabled && PspShowBenchmark)" not in support or "PspShowBenchmark = false;" not in support:
    raise SystemExit("FPS/BENCHMARK mutual exclusion missing from FPS setter")
if "if (enabled && PspShowFps)" not in support or "PspShowFps = false;" not in support:
    raise SystemExit("FPS/BENCHMARK mutual exclusion missing from benchmark setter")
if "if (PspShowBenchmark && PspShowFps)" not in support:
    raise SystemExit("FPS/BENCHMARK config normalization missing")
if "SDL_Rect panel{304, 6, 170, 114};" not in support: raise SystemExit("benchmark panel is not right-aligned full-size")
if "PspDrawText(renderer, 310, 12 + i * 12, lines[i].c_str(), 1);" not in support: raise SystemExit("benchmark text is not right-aligned")
# CPU clock selector checks
for required in ("PspCpuClockMHz = 266", '"cpu="', "PspSetCpuClockProfile", "PspApplyCpuClock", "scePowerSetClockFrequency(requestedCpu, requestedCpu, requestedBus)", "scePowerSetCpuClockFrequency", "scePowerSetBusClockFrequency", "scePowerGetCpuClockFrequencyInt", "PspClockStatusName", '"> CPU:"'):
    if required not in support: raise SystemExit(f"CPU selector support missing: {required}")
if "% 6" not in loop or "PspOptionsSelection == 4" not in loop: raise SystemExit("CPU selector navigation missing")

if (root/"assets").exists(): raise SystemExit("copyright-clean package must not contain assets/")
for forbidden in ("PINBALL.WAV","SFXBANK.BIN","PINBALL.DAT"):
    for f in root.rglob(forbidden):
        if "generated_assets" not in str(f) and "output" not in str(f):
            raise SystemExit(f"copyright-derived asset bundled: {f}")
prep=(root/"tools"/"prepare_user_assets.py").read_text()
if "make_sfxbank.py" not in prep or "PINBALL.DAT" not in prep: raise SystemExit("user asset preparation missing")
audio=(root/"psp_patches"/"audio.py").read_text()
if "MUS_OGG" in audio or "PINBALL.OGG" in audio: raise SystemExit("compressed OGG path must be absent")
music_streamer=(root/"psp_patches"/"music_streamer.py").read_text(encoding="utf-8")
if "PSP_PCM_MUSIC_STREAMER" not in music_streamer or "Mix_HookMusic" not in music_streamer: raise SystemExit("custom PCM music streamer missing")
build=(root/"build_common.sh").read_text()
if 'read -r -p "Original game folder: "' not in build: raise SystemExit("interactive original-folder prompt missing")
if "PINBALL.WAV" not in build: raise SystemExit("PINBALL.WAV output missing")
if "mktemp -d" not in build or "trap cleanup" not in build: raise SystemExit("temporary upstream workspace cleanup missing")
for launcher in ("build_macos.sh", "build_linux.sh", "build_windows.ps1"):
    if not (root/launcher).is_file(): raise SystemExit(f"platform launcher missing: {launcher}")
prep=(root/"tools"/"prepare_user_assets.py").read_text()
if "PINBALL.MID" not in prep or "pcm_s16le" not in prep or "22050" not in prep: raise SystemExit("automatic PCM music generation missing")

loop_tool=(root/"tools"/"extract_music_loop.py").read_text(encoding="utf-8")
for required in ("LOOP_START_TICK = 1920", "LOOP_LENGTH_TICKS = 53760", "EXPECTED_REPEATS = 9", "OUTPUT_REPEATS = 3", "verify_original_structure", "crop_start_sample"):
    if required not in loop_tool: raise SystemExit(f"deterministic MIDI loop extraction missing: {required}")
if "extract_music_loop.py" not in prep or "atrim=start_sample=" not in prep:
    raise SystemExit("MIDI-derived middle-loop crop missing")

if "download_fallback_soundfont" not in prep or "c278464b823daf9c52106c0957f752817da0e52964817ff682fe3a8d2f8446ce" not in prep:
    raise SystemExit("automatic verified SoundFont download missing")
for f in root.rglob("*.sf2"):
    raise SystemExit(f"SoundFont must not be bundled: {f}")
for f in root.rglob("*.sf3"):
    raise SystemExit(f"SoundFont must not be bundled: {f}")


# 1.0.0 automatic toolchain bootstrap checks
mac=(root/"build_macos.sh").read_text(encoding="utf-8")
lin=(root/"build_linux.sh").read_text(encoding="utf-8")
win=(root/"build_windows.ps1").read_text(encoding="utf-8")
helper=(root/"tools"/"install_pspdev_release.py").read_text(encoding="utf-8")
if "install_pspdev_release.py" not in mac or "pspdev/pspdev.git" not in mac:
    raise SystemExit("macOS automatic PSPDEV bootstrap missing")
if "install_pspdev_release.py" not in lin or "pspdev/pspdev.git" not in lin:
    raise SystemExit("Linux automatic PSPDEV bootstrap missing")
if "wsl.exe" in win.lower():
    raise SystemExit("Windows launcher must not invoke WSL")
if "MSYS2.MSYS2" not in win or "dmang-dev/pspdev-win" not in win or "C:\\pspdev" not in win:
    raise SystemExit("native Windows PSPDEV bootstrap missing")
if "SC_WINDOWS_BUNDLED_LIBS" not in win or "pspdev-win-libraries-" not in win:
    raise SystemExit("Windows prebuilt library-bundle path missing")
if "mingw-w64-ucrt-x86_64-cmake" not in win or "mingw-w64-ucrt-x86_64-ninja" not in win:
    raise SystemExit("Windows native UCRT64 CMake/Ninja bootstrap missing")
if "SC_WINDOWS_NATIVE_CMAKE" not in win or "native Windows path preflight" not in win:
    raise SystemExit("Windows native-path CMake/preflight mode missing")
build_patch=(root/"psp_patches"/"build.py").read_text(encoding="utf-8")
for required in ("SC_WINDOWS_NATIVE_CMAKE", "/ucrt64/bin/cmake.exe", "/ucrt64/bin/ninja.exe", "cygpath -m", "CMAKE_TOOLCHAIN_FILE", "SC_PSP_WINDOWS_PREBUILT"):
    if required not in build_patch:
        raise SystemExit(f"Windows native CMake build path missing: {required}")
for required in ("if(SC_PSP_WINDOWS_PREBUILT)", "vorbisfile", "SDL2main", "pspvram", "pspaudio", "psppower"):
    if required not in build_patch:
        raise SystemExit(f"Windows static PSP link fallback missing: {required}")
common=(root/"build_common.sh").read_text(encoding="utf-8")
if "SC_WINDOWS_BUNDLED_LIBS" not in common or "psp-pacman is not required on Windows" not in common:
    raise SystemExit("shared builder Windows library-bundle bypass missing")
if "api.github.com/repos/pspdev/pspdev/releases/latest" not in helper:
    raise SystemExit("official PSPDEV release bootstrap helper missing")

print("1.0.0 package validation: OK")
