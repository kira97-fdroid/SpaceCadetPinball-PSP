from .common import *

def patch_cmake(src):
    p = src / "CMakeLists.txt"

    old = '''if(${CMAKE_VERSION} VERSION_GREATER "3.16.0" OR ${CMAKE_VERSION} VERSION_EQUAL "3.16.0")
    target_precompile_headers(SpaceCadetPinball
            PUBLIC
            SpaceCadetPinball/pch.h
            )
endif()

target_link_libraries(SpaceCadetPinball ${SDL2_LIBRARY} ${SDL2_MIXER_LIBRARY})'''

    new = '''if(NOT PSP AND (${CMAKE_VERSION} VERSION_GREATER "3.16.0" OR ${CMAKE_VERSION} VERSION_EQUAL "3.16.0"))
    target_precompile_headers(SpaceCadetPinball
            PUBLIC
            SpaceCadetPinball/pch.h
            )
endif()

if(PSP)
    target_compile_definitions(SpaceCadetPinball PRIVATE SPACECADET_PSP=1)
    target_compile_options(SpaceCadetPinball PRIVATE -O2 -G0)

    if(SC_PSP_WINDOWS_PREBUILT)
        # pspdev-win ships the PSP static libraries prebuilt.  Do not invoke
        # pkg-config here: the native Windows bundle does not need it, and an
        # MSYS pkg-config may not describe the C:/pspdev target tree correctly.
        # This is the same dependency order produced by psp-pkg-config for the
        # validated macOS/Linux PSP builds.
        set(PSP_SDL_STATIC_LIBS
            vorbisfile
            vorbis
            ogg
            modplug
            stdc++
            m
            SDL2main
            SDL2
            m
            GL
            pspvram
            pspaudio
            pspvfpu
            pspdisplay
            pspgu
            pspge
            psphprm
            pspctrl
            psppower
        )
        message(STATUS "PSP SDL static libs (Windows prebuilt bundle): ${PSP_SDL_STATIC_LIBS}")
    else()
        if(NOT PKG_CONFIG_EXECUTABLE)
            find_program(PKG_CONFIG_EXECUTABLE NAMES psp-pkg-config pkg-config)
        endif()
        if(NOT PKG_CONFIG_EXECUTABLE)
            message(FATAL_ERROR "psp-pkg-config/pkg-config not found")
        endif()

        execute_process(
            COMMAND "${PKG_CONFIG_EXECUTABLE}" --static --libs sdl2 SDL2_mixer
            OUTPUT_VARIABLE PSP_SDL_STATIC_LIBS_RAW
            OUTPUT_STRIP_TRAILING_WHITESPACE
            RESULT_VARIABLE PSP_SDL_PKGCONFIG_RESULT
        )
        if(NOT PSP_SDL_PKGCONFIG_RESULT EQUAL 0)
            message(FATAL_ERROR "pkg-config failed for SDL2/SDL2_mixer")
        endif()

        separate_arguments(
            PSP_SDL_STATIC_LIBS
            NATIVE_COMMAND
            "${PSP_SDL_STATIC_LIBS_RAW}"
        )
        message(STATUS "PSP SDL static libs: ${PSP_SDL_STATIC_LIBS}")
    endif()

    target_link_libraries(SpaceCadetPinball
        ${SDL2_MIXER_LIBRARY}
        ${PSP_SDL_STATIC_LIBS}
    )

    create_pbp_file(
        TARGET SpaceCadetPinball
        TITLE "Space Cadet Pinball"
        VERSION "01.001"
        MEMSIZE 1
    )
else()
    target_link_libraries(SpaceCadetPinball ${SDL2_LIBRARY} ${SDL2_MIXER_LIBRARY})
endif()'''

    replace_once(p, old, new, "CMake PSP target/link/PBP")
    replace_once(
        p,
        "if(UNIX AND NOT APPLE)",
        "if(UNIX AND NOT APPLE AND NOT PSP)",
        "exclude PSP from Linux install rules"
    )


def patch_main(src):
    p = src / "SpaceCadetPinball" / "SpaceCadetPinball.cpp"
    s = read(p)

    if "PSP_MODULE_INFO(SpaceCadetPinball" in s:
        print("[skip] PSP module/callbacks")
        return

    old = '#include "pch.h"\n#include "winmain.h"\n'
    new = '''#include "pch.h"
#include "winmain.h"

#ifdef SPACECADET_PSP
#include <pspuser.h>
#include <pspmoduleinfo.h>
#include <pspthreadman.h>
#include <pspkernel.h>
#include <psppower.h>

PSP_MODULE_INFO(SpaceCadetPinball, PSP_MODULE_USER, 4, 0);
PSP_MAIN_THREAD_ATTR(THREAD_ATTR_USER | THREAD_ATTR_VFPU);
PSP_MAIN_THREAD_STACK_SIZE_KB(1024);
PSP_HEAP_SIZE_KB(-1024);

static int PspExitCallback(int, int, void*)
{
    sceKernelExitGame();
    return 0;
}

static int PspCallbackThread(SceSize, void*)
{
    int cbid = sceKernelCreateCallback("Exit Callback", PspExitCallback, nullptr);
    if (cbid >= 0)
        sceKernelRegisterExitCallback(cbid);
    sceKernelSleepThreadCB();
    return 0;
}

static void PspSetupCallbacks()
{
    int thid = sceKernelCreateThread(
        "exit_callback_thread",
        PspCallbackThread,
        0x11,
        0xFA0,
        PSP_THREAD_ATTR_USER,
        nullptr
    );
    if (thid >= 0)
        sceKernelStartThread(thid, 0, nullptr);
}
#endif
'''
    if old not in s:
        raise RuntimeError("SpaceCadetPinball.cpp: include anchor not found")
    s = s.replace(old, new, 1)

    old = '''int main(int argc, char* argv[])
{
'''
    new = '''int main(int argc, char* argv[])
{
#ifdef SPACECADET_PSP
    PspSetupCallbacks();
    scePowerSetClockFrequency(266, 266, 133);
#endif
'''
    if old not in s:
        raise RuntimeError("SpaceCadetPinball.cpp: main anchor not found")
    s = s.replace(old, new, 1)

    write(p, s)
    print("[ok]   PSP module, HOME callback, 266 MHz")


def verify_native_plunger_release_window(src):
    p = src / "SpaceCadetPinball" / "TPlunger.cpp"
    text = read(p)
    needle = "timer::set(PullbackDelay, this, ReleasedTimer);"
    if text.count(needle) != 1:
        raise RuntimeError(f"{p}: expected original upstream plunger release timer exactly once")
    print("[ok]   upstream plunger release window unchanged (PullbackDelay / 25 ms)")


def write_psp_build_script(src):
    p = src / "build_psp.sh"
    p.write_text(r'''#!/usr/bin/env bash
set -euo pipefail

export PSPDEV="${PSPDEV:-$HOME/pspdev}"
export PATH="$PSPDEV/bin:$PATH"

command -v psp-cmake >/dev/null || { echo "ERROR: psp-cmake not found"; exit 1; }

rm -rf build-psp

if [[ "${SC_WINDOWS_NATIVE_CMAKE:-0}" == "1" ]]; then
    # On native Windows, do not use the MSYS CMake from /usr/bin: it emits
    # POSIX-only source paths such as /tmp/... that psp-gcc/cc1 cannot open.
    # Use the UCRT64 native CMake + Ninja pair and hand them Windows paths.
    command -v cygpath >/dev/null || { echo "ERROR: cygpath not found"; exit 1; }
    [[ -x /ucrt64/bin/cmake.exe ]] || { echo "ERROR: native UCRT64 CMake not found"; exit 1; }
    [[ -x /ucrt64/bin/ninja.exe ]] || { echo "ERROR: native UCRT64 Ninja not found"; exit 1; }

    SRC_WIN="$(cygpath -m "$PWD")"
    BUILD_WIN="$(cygpath -m "$PWD/build-psp")"
    PSPDEV_WIN="$(cygpath -m "$PSPDEV")"

    PSPDEV="$PSPDEV_WIN" /ucrt64/bin/cmake.exe \
        -S "$SRC_WIN" \
        -B "$BUILD_WIN" \
        -G Ninja \
        -DCMAKE_MAKE_PROGRAM=C:/msys64/ucrt64/bin/ninja.exe \
        -DCMAKE_TOOLCHAIN_FILE="$PSPDEV_WIN/psp/share/pspdev.cmake" \
        -DSC_PSP_WINDOWS_PREBUILT=ON \
        -DCMAKE_BUILD_TYPE=Release
    PSPDEV="$PSPDEV_WIN" /ucrt64/bin/cmake.exe --build "$BUILD_WIN" --parallel "${JOBS:-4}"
else
    mkdir build-psp
    cd build-psp
    psp-cmake .. -DCMAKE_BUILD_TYPE=Release
    cmake --build . -- -j"${JOBS:-4}"
    cd ..
fi

test -f bin/EBOOT.PBP || { echo "ERROR: bin/EBOOT.PBP was not created"; exit 1; }
echo "OK: $(pwd)/bin/EBOOT.PBP"
''', encoding="utf-8")
    p.chmod(0o755)
    print("[ok]   build_psp.sh")


