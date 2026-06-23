#!/usr/bin/env bash
# Build the MaestroAgent Python sidecar as a frozen PyInstaller binary.
#
# This is used by `pnpm tauri build` to bundle a self-contained Python
# runtime into the desktop app, so end users don't need Python installed.
#
# Output: desktop/src-tauri/binaries/maestro-sidecar-{arch}
#
# Usage:
#   ./backend/scripts/build_sidecar.sh
#
# Requirements:
#   - Python 3.11+ in the active venv
#   - PyInstaller installed (pip install pyinstaller)
#   - The backend must be pip-installed: pip install -e ./backend

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
OUTPUT_DIR="$REPO_ROOT/desktop/src-tauri/binaries"

# Detect target architecture.
ARCH="$(uname -m)"
case "$ARCH" in
    x86_64)  TARGET_ARCH="x86_64";;
    arm64|aarch64) TARGET_ARCH="aarch64";;
    *) echo "Unsupported arch: $ARCH" >&2; exit 1;;
esac

# Detect OS for the binary suffix.
OS="$(uname -s)"
case "$OS" in
    Darwin) TARGET_SUFFIX="-$TARGET_ARCH";;
    Linux)  TARGET_SUFFIX="-$TARGET_ARCH";;
    MINGW*|MSYS*) TARGET_SUFFIX="-x86_64.exe";;
    *) echo "Unsupported OS: $OS" >&2; exit 1;;
esac

echo "Building MaestroAgent sidecar..."
echo "  Repo root:    $REPO_ROOT"
echo "  Backend dir:  $BACKEND_DIR"
echo "  Output dir:   $OUTPUT_DIR"
echo "  Target:       maestro-sidecar$TARGET_SUFFIX"
echo

mkdir -p "$OUTPUT_DIR"

# Ensure PyInstaller is installed.
if ! python -c "import PyInstaller" 2>/dev/null; then
    echo "PyInstaller not found. Installing..."
    pip install pyinstaller
fi

# Build the frozen binary.
cd "$BACKEND_DIR"

pyinstaller \
    --name "maestro-sidecar" \
    --onefile \
    --noconfirm \
    --clean \
    --collect-all maestro_core \
    --collect-all maestro_agents \
    --collect-all maestro_loops \
    --collect-all maestro_memory \
    --collect-all maestro_verify \
    --collect-all maestro_llm \
    --collect-all maestro_api \
    --collect-all maestro_plugins \
    --collect-all maestro_cli \
    --hidden-import "uvicorn.logging" \
    --hidden-import "uvicorn.protocols.http.auto" \
    --hidden-import "uvicorn.protocols.websockets.auto" \
    --hidden-import "uvicorn.lifespan.on" \
    --hidden-import "chromadb" \
    --hidden-import "networkx" \
    --add-data "examples/templates:examples/templates" \
    --add-data "plugins:plugins" \
    maestro_cli/main.py

# Move the binary to the Tauri binaries directory with the target suffix.
mv "dist/maestro-sidecar" "$OUTPUT_DIR/maestro-sidecar$TARGET_SUFFIX"
chmod +x "$OUTPUT_DIR/maestro-sidecar$TARGET_SUFFIX"

# Clean up build artifacts.
rm -rf build dist maestro-sidecar.spec

echo
echo "✓ Sidecar built: $OUTPUT_DIR/maestro-sidecar$TARGET_SUFFIX"
echo
echo "Next steps:"
echo "  1. cd desktop && pnpm tauri build"
echo "  2. The installer will be in desktop/src-tauri/target/release/bundle/"
