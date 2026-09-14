#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
[[ "$(uname -s)" == "Linux" ]] || { echo "ERROR: build_linux.sh is intended for Linux."; exit 1; }

SUDO=""
if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  command -v sudo >/dev/null 2>&1 || { echo "ERROR: sudo is required to install missing Linux packages."; exit 1; }
  SUDO="sudo"
fi

install_minimal_deps() {
  if command -v apt-get >/dev/null 2>&1; then
    $SUDO apt-get update
    $SUDO apt-get install -y git python3 cmake curl wget ffmpeg fluidsynth unzip xz-utils ca-certificates
  elif command -v dnf >/dev/null 2>&1; then
    $SUDO dnf install -y git python3 cmake curl wget ffmpeg fluidsynth unzip xz ca-certificates
  elif command -v pacman >/dev/null 2>&1; then
    $SUDO pacman -Sy --needed --noconfirm git python cmake curl wget ffmpeg fluidsynth unzip xz ca-certificates
  else
    echo "ERROR: supported package manager not found (apt, dnf or pacman)."
    exit 1
  fi
}

install_source_deps() {
  if command -v apt-get >/dev/null 2>&1; then
    $SUDO apt-get install -y build-essential patch texinfo flex bison gettext libgsl-dev libgmp-dev libmpfr-dev libmpc-dev libusb-1.0-0-dev libreadline-dev libarchive-dev libgpgme-dev libssl-dev libtool pkg-config autoconf automake meson ninja-build
  elif command -v dnf >/dev/null 2>&1; then
    $SUDO dnf install -y gcc gcc-c++ make patch texinfo flex bison gettext-devel gsl-devel gmp-devel mpfr-devel libmpc-devel libusb1-devel readline-devel libarchive-devel gpgme-devel openssl-devel libtool pkgconf-pkg-config autoconf automake meson ninja-build
  elif command -v pacman >/dev/null 2>&1; then
    $SUDO pacman -S --needed --noconfirm base-devel patch texinfo flex bison gettext gsl gmp mpfr libmpc libusb readline libarchive gpgme openssl libtool pkgconf autoconf automake meson ninja
  fi
}

psp_runtime_libs_ready() {
  local lib
  local libs=(
    libSDL2.a libSDL2main.a libSDL2_mixer.a
    libvorbisfile.a libvorbis.a libogg.a libmodplug.a
    libGL.a libpspvram.a
  )
  for lib in "${libs[@]}"; do
    [[ -f "$PSPDEV/psp/lib/$lib" ]] || return 1
  done
  return 0
}

install_minimal_deps
export PSPDEV="${PSPDEV:-$HOME/pspdev}"
export PATH="$PSPDEV/bin:$PATH"
# Keep normal project builds modest on Linux. Override explicitly if desired.
export JOBS="${JOBS:-2}"

install_pspdev_from_source() {
  # This is an emergency fallback only.  The official Ubuntu prebuilt should
  # normally be selected first.  Limit source-toolchain parallelism because a
  # GCC build can otherwise exhaust RAM and make a desktop appear frozen.
  local source_jobs="${PSPDEV_BUILD_JOBS:-1}"
  [[ "$source_jobs" =~ ^[1-9][0-9]*$ ]] || { echo "ERROR: PSPDEV_BUILD_JOBS must be a positive integer"; exit 1; }

  echo "No compatible prebuilt PSPDEV release asset was found."
  echo "Falling back to the official PSPDEV source build with $source_jobs job(s)."
  echo "You can override this with PSPDEV_BUILD_JOBS=N."
  install_source_deps

  local tmp safe_bin
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/pspdev-src.XXXXXX")"
  trap 'rm -rf "$tmp"' RETURN
  git clone --depth 1 https://github.com/pspdev/pspdev.git "$tmp/pspdev"

  # Several PSPDEV sub-builds use `-j$(nproc)` directly.  Put a tiny nproc
  # shim first in PATH so those nested builds also respect the safe cap.
  safe_bin="$tmp/safe-bin"
  mkdir -p "$safe_bin"
  cat > "$safe_bin/nproc" <<EOF
#!/usr/bin/env sh
echo "$source_jobs"
EOF
  chmod +x "$safe_bin/nproc"

  (
    cd "$tmp/pspdev"
    export PSPDEV="$PSPDEV"
    export PATH="$safe_bin:$PSPDEV/bin:$PATH"
    export MAKEFLAGS="-j$source_jobs"
    export CMAKE_BUILD_PARALLEL_LEVEL="$source_jobs"
    export NINJAFLAGS="-j$source_jobs"
    ./build-all.sh
  )
  rm -rf "$tmp"
  trap - RETURN
}

core_toolchain_ready=0
if command -v psp-gcc >/dev/null 2>&1 && command -v psp-cmake >/dev/null 2>&1; then
  core_toolchain_ready=1
fi

if [[ "$core_toolchain_ready" == "1" ]] && command -v psp-pacman >/dev/null 2>&1; then
  echo "Existing PSPDEV installation found; reusing: $PSPDEV"
elif [[ "$core_toolchain_ready" == "1" ]] && psp_runtime_libs_ready; then
  echo "Existing PSPDEV compiler/SDK and required PSP libraries found; reusing them."
  echo "psp-pacman is missing, but it is not needed for this build."
  export SC_SKIP_PSP_PACMAN=1
else
  echo "PSPDEV/PSPSDK is incomplete or missing. Installing the official prebuilt release into: $PSPDEV"
  arch="$(uname -m)"
  set +e
  python3 "$HERE/tools/install_pspdev_release.py" --platform linux --arch "$arch" --dest "$PSPDEV"
  rc=$?
  set -e
  if [[ $rc -ne 0 ]]; then
    install_pspdev_from_source
  fi
  hash -r
fi

for cmd in psp-gcc psp-cmake; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: PSPDEV bootstrap failed; missing $cmd"; exit 1; }
done

if ! command -v psp-pacman >/dev/null 2>&1; then
  if psp_runtime_libs_ready; then
    export SC_SKIP_PSP_PACMAN=1
  else
    echo "ERROR: PSPDEV bootstrap is incomplete: psp-pacman is missing and required PSP libraries are not installed."
    exit 1
  fi
fi

exec "$HERE/build_common.sh" "${1:-}"
