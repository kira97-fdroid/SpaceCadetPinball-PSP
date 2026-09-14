#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
case "$(uname -s)" in
  Darwin) exec "$HERE/build_macos.sh" "${1:-}" ;;
  Linux)  exec "$HERE/build_linux.sh" "${1:-}" ;;
  *) echo "Unsupported Unix platform. On Windows, run build_windows.ps1."; exit 1 ;;
esac
