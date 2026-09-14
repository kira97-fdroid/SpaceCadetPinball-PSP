#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
VERSION="1.0.0"

clean_drag_path() {
  local p="$1"
  p="${p%\"}"; p="${p#\"}"
  p="${p%\'}"; p="${p#\'}"
  # macOS Terminal drag-and-drop may append a trailing space.
  p="${p% }"
  printf '%s' "$p"
}

ORIGINAL_GAME_DIR="${1:-}"
if [[ -z "$ORIGINAL_GAME_DIR" ]]; then
  echo "============================================================"
  echo " Space Cadet Pinball PSP $VERSION - guided builder"
  echo "============================================================"
  echo
  echo "Drag the folder containing your original 3D Pinball - Space Cadet"
  echo "game files into this terminal window, then press Enter."
  echo
  read -r -p "Original game folder: " ORIGINAL_GAME_DIR
fi
ORIGINAL_GAME_DIR="$(clean_drag_path "$ORIGINAL_GAME_DIR")"
if [[ ! -d "$ORIGINAL_GAME_DIR" ]]; then
  echo "ERROR: folder not found: $ORIGINAL_GAME_DIR"
  exit 1
fi

export PSPDEV="${PSPDEV:-$HOME/pspdev}"
export PATH="$PSPDEV/bin:$PATH"
UPLOAD_MODE="${PSP_UPLOAD_MODE:-dirty}"
case "$UPLOAD_MODE" in dirty|full) ;; *) echo "ERROR: PSP_UPLOAD_MODE must be dirty or full"; exit 1;; esac

for cmd in psp-cmake cmake; do
  command -v "$cmd" >/dev/null || { echo "ERROR: missing required command: $cmd"; exit 1; }
done
if [[ -z "${SC_PINBALL_UPSTREAM_ARCHIVE:-}" ]]; then
  command -v git >/dev/null || { echo "ERROR: missing required command: git"; exit 1; }
else
  command -v unzip >/dev/null || { echo "ERROR: missing required command: unzip"; exit 1; }
fi
if [[ "${SC_WINDOWS_BUNDLED_LIBS:-0}" != "1" && "${SC_SKIP_PSP_PACMAN:-0}" != "1" ]]; then
  command -v psp-pacman >/dev/null || { echo "ERROR: missing required command: psp-pacman"; exit 1; }
fi
if command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD="python"
else
  echo "ERROR: missing required command: python3/python"
  exit 1
fi
for cmd in ffmpeg fluidsynth; do
  command -v "$cmd" >/dev/null || { echo "ERROR: missing host dependency: $cmd"; exit 1; }
done

"$PYTHON_CMD" "$HERE/tools/validate_patch_package.py"
rm -rf "$HERE/generated_assets" "$HERE/output"
"$PYTHON_CMD" "$HERE/tools/prepare_user_assets.py" "$ORIGINAL_GAME_DIR" "$HERE/generated_assets"

echo
echo "== Space Cadet Pinball PSP consolidated builder $VERSION =="
echo "PSPDEV: $PSPDEV"
echo "Upload mode: $UPLOAD_MODE"
echo "Physics: 120 Hz"
echo "Video: 30 FPS / 60 FPS (default 60)"
echo "CPU default: 266 MHz"
echo "Texture: BGR565 / GU_PSM_5650"
echo "Music: PCM WAV 22050 Hz mono (low CPU)"

echo; echo "== Updating/checking SDL2 and SDL2_mixer =="
if [[ "${SC_WINDOWS_BUNDLED_LIBS:-0}" == "1" ]]; then
  echo "Using the prebuilt pspdev-win PSP library bundle (psp-pacman is not required on Windows)."
  required_psp_libs=(
    libSDL2.a libSDL2main.a libSDL2_mixer.a
    libvorbisfile.a libvorbis.a libogg.a libmodplug.a
    libGL.a libpspvram.a
  )
  missing_psp_libs=()
  for lib in "${required_psp_libs[@]}"; do
    [[ -f "$PSPDEV/psp/lib/$lib" ]] || missing_psp_libs+=("$lib")
  done
  if (( ${#missing_psp_libs[@]} )); then
    echo "ERROR: the Windows PSP library bundle is incomplete. Missing: ${missing_psp_libs[*]}"
    echo "Rerun build_windows.ps1 so it can repair the pspdev-win library bundle."
    exit 1
  fi
elif [[ "${SC_SKIP_PSP_PACMAN:-0}" == "1" ]]; then
  echo "Using existing PSP libraries; psp-pacman update skipped."
  required_psp_libs=(
    libSDL2.a libSDL2main.a libSDL2_mixer.a
    libvorbisfile.a libvorbis.a libogg.a libmodplug.a
    libGL.a libpspvram.a
  )
  missing_psp_libs=()
  for lib in "${required_psp_libs[@]}"; do
    [[ -f "$PSPDEV/psp/lib/$lib" ]] || missing_psp_libs+=("$lib")
  done
  if (( ${#missing_psp_libs[@]} )); then
    echo "ERROR: existing PSP library set is incomplete. Missing: ${missing_psp_libs[*]}"
    exit 1
  fi
else
  psp-pacman -Sy --noconfirm sdl2 sdl2-mixer
fi

TMP_BASE="${TMPDIR:-/tmp}"
WORK="$(mktemp -d "${TMP_BASE%/}/SpaceCadetPinball-PSP-076-${UPLOAD_MODE}.XXXXXX")"
cleanup() {
  rm -rf "$WORK"
}
trap cleanup EXIT INT TERM

UPSTREAM_COMMIT_PIN="cb9b7b886244a27773f66b0b19fdc2998392565e"
if [[ -n "${SC_PINBALL_UPSTREAM_ARCHIVE:-}" ]]; then
  echo; echo "== Extracting the pinned upstream source archive =="
  [[ -f "$SC_PINBALL_UPSTREAM_ARCHIVE" ]] || { echo "ERROR: upstream archive not found: $SC_PINBALL_UPSTREAM_ARCHIVE"; exit 1; }
  STAGE="${WORK}.archive"
  mkdir -p "$STAGE"
  unzip -q "$SC_PINBALL_UPSTREAM_ARCHIVE" -d "$STAGE"
  shopt -s nullglob dotglob
  roots=("$STAGE"/*)
  shopt -u nullglob dotglob
  [[ ${#roots[@]} -eq 1 && -d "${roots[0]}" ]] || { echo "ERROR: unexpected upstream archive layout"; exit 1; }
  rm -rf "$WORK"
  mv "${roots[0]}" "$WORK"
  rm -rf "$STAGE"
  ACTUAL="$UPSTREAM_COMMIT_PIN"
  echo "Upstream archive: $ACTUAL"
else
  echo; echo "== Cloning a clean upstream checkout =="
  git clone --quiet https://github.com/k4zmu2a/SpaceCadetPinball.git "$WORK"
  git -C "$WORK" checkout --quiet --detach "$UPSTREAM_COMMIT_PIN"
  ACTUAL="$(git -C "$WORK" rev-parse HEAD)"
  [[ "$ACTUAL" == "$UPSTREAM_COMMIT_PIN" ]] || { echo "ERROR: upstream commit mismatch"; exit 1; }
  echo "Upstream: $ACTUAL"
fi

echo; echo "== Applying the consolidated PSP port =="
"$PYTHON_CMD" "$HERE/apply_psp_port.py" "$WORK" "$UPLOAD_MODE"

echo; echo "== Building from scratch =="
cd "$WORK"
./build_psp.sh

mkdir -p "$HERE/output"
cp -f "$WORK/bin/EBOOT.PBP" "$HERE/output/EBOOT.PBP"
cp -f "$HERE/generated_assets/PINBALL.DAT" "$HERE/output/PINBALL.DAT"
cp -f "$HERE/generated_assets/SFXBANK.BIN" "$HERE/output/SFXBANK.BIN"
cp -f "$HERE/generated_assets/PINBALL.WAV" "$HERE/output/PINBALL.WAV"
MODE_UPPER="$(printf '%s' "$UPLOAD_MODE" | tr '[:lower:]' '[:upper:]')"
cp -f "$WORK/bin/EBOOT.PBP" "$HERE/output/EBOOT_${VERSION}_${MODE_UPPER}.PBP"
{
  echo "Space Cadet Pinball PSP $VERSION"
  echo "upload_mode=$UPLOAD_MODE"
  echo "physics_hz=120"
  echo "video_modes=30fps,60fps"
  echo "default_video=60fps"
  echo "default_cpu_mhz=266"
  echo "texture_format=BGR565"
  echo "music=PCM_S16LE_22050_MONO"
  echo "upstream_commit=$ACTUAL"
  echo "built_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if [[ "${SC_WINDOWS_BUNDLED_LIBS:-0}" == "1" ]]; then
    echo "psp_libraries=pspdev-win-prebuilt-bundle"
  elif [[ "${SC_SKIP_PSP_PACMAN:-0}" == "1" ]]; then
    echo "psp_libraries=existing-preinstalled-libraries"
  else
    psp-pacman -Q sdl2 sdl2-mixer 2>/dev/null || true
  fi
} > "$HERE/output/BUILD_INFO_${VERSION}_${MODE_UPPER}.txt"

echo
echo "============================================================"
echo "BUILD $VERSION COMPLETE"
echo "PSP-ready output folder: $HERE/output"
echo
echo "Copy these files to PSP/GAME/SpaceCadetPinball/:"
echo "  EBOOT.PBP"
echo "  PINBALL.DAT"
echo "  SFXBANK.BIN"
echo "  PINBALL.WAV"
echo "============================================================"
