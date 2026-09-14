#!/usr/bin/env python3
from pathlib import Path
import sys

from psp_patches.build import patch_cmake, patch_main, verify_native_plunger_release_window, write_psp_build_script
from psp_patches.ui_input import patch_ui_input_runtime, patch_pause_prompt, strip_startup_profiler
from psp_patches.audio import patch_audio_assets, patch_sfx_direct_pcm, patch_sfx_fast_lookup
from psp_patches.music_streamer import patch_psp_pcm_music_streamer
from psp_patches.render_video import patch_renderer, patch_dirty_upload, patch_vscreen_dirty_tracking, patch_video_modes

UPSTREAM_COMMIT = "cb9b7b886244a27773f66b0b19fdc2998392565e"

def require_tree(src: Path):
    required = [
        src / "CMakeLists.txt",
        src / "SpaceCadetPinball" / "winmain.cpp",
        src / "SpaceCadetPinball" / "render.cpp",
        src / "SpaceCadetPinball" / "SpaceCadetPinball.cpp",
        src / "SpaceCadetPinball" / "Sound.cpp",
        src / "SpaceCadetPinball" / "loader.cpp",
        src / "SpaceCadetPinball" / "TPlunger.cpp",
    ]
    missing=[str(p) for p in required if not p.exists()]
    if missing:
        raise SystemExit("Not a SpaceCadetPinball tree; missing:\n  " + "\n  ".join(missing))

def verify_result(src: Path):
    win=(src/"SpaceCadetPinball"/"winmain.cpp").read_text(encoding="utf-8")
    render=(src/"SpaceCadetPinball"/"render.cpp").read_text(encoding="utf-8")
    sound=(src/"SpaceCadetPinball"/"Sound.cpp").read_text(encoding="utf-8")
    checks={
        "physics 120 Hz": "physicsStepMs = 1000.0 / 120.0" in win,
        "30/60 FPS runtime": "FramesPerSecond >= 60 ? 60.0 : 30.0" in win,
        "default MUSIC OFF": "Options.Music = false;" in win,
        "default VIDEO 60 FPS": "Options.Resolution = 1;" in win and "Options.FramesPerSecond = 60;" in win,
        "default CPU 266 MHz": "PspCpuClockMHz = 266" in win,
        "frame remainder preserved": "renderAccumulatorMs -= renderStepMs" in win,
        "large VIDEO value": 'PspDrawText(renderer, 248, 144, PspVideoProfileName(videoProfile), 2)' in win,
        "benchmark option": "PspShowBenchmark" in win and "PspDrawBenchmarkOverlay" in win and "benchmark=" in win,
        "FPS/BENCHMARK mutual exclusion": "if (enabled && PspShowBenchmark)" in win and "if (enabled && PspShowFps)" in win and "if (PspShowBenchmark && PspShowFps)" in win,
        "benchmark power telemetry": "scePowerGetBatteryTemp" in win and "scePowerGetCpuClockFrequencyInt" in win,
        "CPU clock centralized apply": "void PspApplyCpuClock()" in win and "scePowerSetCpuClockFrequency" in win and "scePowerSetBusClockFrequency" in win,
        "CPU clock applies after config": "SDL_RWclose(rw);\n\t\tPspApplyCpuClock();" in win,
        "CPU clock readback status": "PspClockApplyStatus" in win and "PspClockStatusName" in win and '"LOCKED"' in win and '"FAILED"' in win,
        "benchmark memory telemetry": "sceKernelTotalFreeMemSize" in win,
        "BGR565": "SDL_PIXELFORMAT_BGR565" in render,
        "dirty upload": "PspDirtyRects" in render,
        "fast PCM SFX": "Mix_QuickLoad_RAW" in sound,
        "custom PCM music streamer": "PSP_PCM_MUSIC_STREAMER" in (src/"SpaceCadetPinball"/"midi.cpp").read_text(encoding="utf-8") and "Mix_HookMusic(PspMusicCallback" in (src/"SpaceCadetPinball"/"midi.cpp").read_text(encoding="utf-8"),
        "startup profiler removed": "startup_profile.txt" not in win and "PspStartupMark" not in win,
    }
    failed=[k for k,v in checks.items() if not v]
    for k,v in checks.items(): print(f"[{'ok' if v else 'FAIL'}] verify {k}")
    if failed:
        raise RuntimeError("post-patch verification failed: " + ", ".join(failed))

def main():
    src=Path(sys.argv[1] if len(sys.argv)>1 else ".").resolve()
    upload_mode=(sys.argv[2] if len(sys.argv)>2 else "dirty").lower()
    if upload_mode not in ("dirty","full"):
        raise SystemExit("upload mode must be 'dirty' or 'full'")
    require_tree(src)
    patch_cmake(src)
    patch_main(src)
    patch_ui_input_runtime(src)
    strip_startup_profiler(src)
    patch_pause_prompt(src)
    verify_native_plunger_release_window(src)
    patch_audio_assets(src)
    patch_sfx_direct_pcm(src)
    patch_sfx_fast_lookup(src)
    patch_psp_pcm_music_streamer(src)
    patch_renderer(src)
    if upload_mode == "dirty":
        patch_dirty_upload(src)
        patch_vscreen_dirty_tracking(src)
    else:
        print("[info] PSP upload mode: FULL")
    patch_video_modes(src, upload_mode)
    write_psp_build_script(src)
    verify_result(src)
    print(f"\nPSP consolidated port 1.0.0 applied (upload={upload_mode}, VIDEO=30/60 FPS).")

if __name__ == "__main__": main()
