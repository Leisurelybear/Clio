#!/usr/bin/env bash
# packaging/build-desktop-macos.sh
# Build the Clio desktop shell for macOS as a PyInstaller onedir .app bundle
# (universal2: Intel + Apple Silicon) (R-040 multi-platform).
#
# Requires (installed automatically when missing):
#   - a universal2 CPython 3.11 (e.g. python.org pkg), because PyInstaller's
#     --target-architecture universal2 needs a universal2 interpreter
#   - pyinstaller, pywebview, pyobjc-core and the pyobjc frameworks (Cocoa,
#     WebKit, Quartz, Security)
#
# Usage: bash packaging/build-desktop-macos.sh [--no-clean]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLEAN=1
for arg in "$@"; do
    case "$arg" in
        --no-clean) CLEAN=0 ;;
        *) echo "unknown argument: $arg" >&2; exit 1 ;;
    esac
done

PYTHON_BIN="${PYTHON_BIN:-python3}"

"$PYTHON_BIN" -m pip install --quiet pyinstaller "pywebview" \
    "pyobjc-core" "pyobjc-framework-Cocoa" "pyobjc-framework-WebKit" \
    "pyobjc-framework-Quartz" "pyobjc-framework-Security"

cd "$ROOT"
ARGS=(packaging/clio.spec --noconfirm)
if [ "$CLEAN" -eq 1 ]; then
    ARGS+=(--clean)
fi

# universal2 requires a universal2 interpreter; fall back to host arch with a
# warning so the script still works on single-arch Pythons.
if "$PYTHON_BIN" -c 'import platform; exit(0 if "universal2" in platform.machine() else 1)'; then
    "$PYTHON_BIN" -m PyInstaller "${ARGS[@]}" --target-architecture universal2
else
    echo "WARNING: python is not a universal2 build; building host arch only" >&2
    "$PYTHON_BIN" -m PyInstaller "${ARGS[@]}"
fi

# Ship the desktop README (WebView2 / SmartScreen / ffmpeg notes) next to the app.
cp "$ROOT/packaging/README-desktop.md" "$ROOT/dist/README-desktop.md"

echo ""
echo "Built: dist/clio.app"
echo "Smoke test: open dist/clio.app"
