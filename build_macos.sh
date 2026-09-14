#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
[[ "$(uname -s)" == "Darwin" ]] || { echo "ERROR: build_macos.sh is intended for macOS."; exit 1; }

ensure_brew() {
  if command -v brew >/dev/null 2>&1; then return; fi
  echo "Homebrew was not found. Installing Homebrew..."
  echo "macOS may ask for your administrator password."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  if [[ -x /opt/homebrew/bin/brew ]]; then eval "$(/opt/homebrew/bin/brew shellenv)"; fi
  if [[ -x /usr/local/bin/brew ]]; then eval "$(/usr/local/bin/brew shellenv)"; fi
  command -v brew >/dev/null 2>&1 || { echo "ERROR: Homebrew installation did not become available in PATH."; exit 1; }
}

ensure_brew
# Official PSPDEV macOS prerequisites plus the host tools used by this builder.
brew install git python cmake curl wget pkgconf gnu-sed bash openssl libtool libmpc libarchive gettext texinfo bison flex isl gsl gmp mpfr libusb-compat zlib gpgme meson ninja ffmpeg fluid-synth xz

export PSPDEV="${PSPDEV:-$HOME/pspdev}"
export PATH="$PSPDEV/bin:$PATH"

install_pspdev_from_source() {
  echo "No compatible prebuilt PSPDEV release asset was found. Falling back to the official source installer."
  local tmp
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/pspdev-src.XXXXXX")"
  trap 'rm -rf "$tmp"' RETURN
  git clone --depth 1 https://github.com/pspdev/pspdev.git "$tmp/pspdev"
  (cd "$tmp/pspdev" && PSPDEV="$PSPDEV" PATH="$PSPDEV/bin:$PATH" ./build-all.sh)
  rm -rf "$tmp"
  trap - RETURN
}

if ! command -v psp-gcc >/dev/null 2>&1 || ! command -v psp-cmake >/dev/null 2>&1 || ! command -v psp-pacman >/dev/null 2>&1; then
  echo "PSPDEV/PSPSDK was not found. Installing it automatically into: $PSPDEV"
  arch="$(uname -m)"
  set +e
  python3 "$HERE/tools/install_pspdev_release.py" --platform macos --arch "$arch" --dest "$PSPDEV"
  rc=$?
  set -e
  if [[ $rc -ne 0 ]]; then install_pspdev_from_source; fi
  xattr -dr com.apple.quarantine "$PSPDEV" 2>/dev/null || true
  hash -r
fi

for cmd in psp-gcc psp-cmake psp-pacman; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: PSPDEV bootstrap failed; missing $cmd"; exit 1; }
done
exec "$HERE/build_common.sh" "${1:-}"
