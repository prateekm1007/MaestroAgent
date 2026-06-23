#!/usr/bin/env bash
# MaestroAgent — instant dev mode (no Docker build required).
#
# Starts the backend + frontend in dev mode with hot reload.
# Use this for fast iteration and browser review — Docker is for production.
#
# Usage:
#   ./dev.sh              # start both backend + frontend
#   ./dev.sh backend      # backend only
#   ./dev.sh frontend     # frontend only
#
# After starting:
#   - Backend API:  http://localhost:8765
#   - Frontend PWA: http://localhost:1420
#   - Open http://localhost:1420 in Chrome/Firefox/Brave
#   - Click "Install" in the address bar for PWA

set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

MODE="${1:-both}"

# --- Check prerequisites ---
check_prereqs() {
    local missing=()
    command -v python3 &>/dev/null || missing+=("python3")
    command -v node &>/dev/null || missing+=("node")
    command -v pnpm &>/dev/null || command -v npm &>/dev/null || missing+=("pnpm or npm")
    if [ ${#missing[@]} -gt 0 ]; then
        error "Missing prerequisites: ${missing[*]}. Install them first."
    fi
}

setup_backend() {
    info "Setting up backend..."
    cd backend
    if [ ! -d ".venv" ]; then
        python3 -m venv .venv
        info "Created virtualenv at backend/.venv"
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate
    pip install -e ".[dev]" -q 2>&1 | tail -3 || pip install -e . -q 2>&1 | tail -3
    cd ..
    info "Backend ready."
}

start_backend() {
    info "Starting backend on http://localhost:8765 ..."
    cd backend
    source .venv/bin/activate
    export MAESTRO_LOG="${MAESTRO_LOG:-info}"
    export MAESTRO_FRONTEND_DIST="${MAESTRO_FRONTEND_DIST:-../frontend/dist}"
    exec python -m maestro_cli.main serve --host 0.0.0.0 --port 8765
}

setup_frontend() {
    info "Setting up frontend..."
    cd frontend
    if [ ! -d "node_modules" ]; then
        if command -v pnpm &>/dev/null; then
            pnpm install
        else
            npm install
        fi
    fi
    # Generate PWA icons if missing.
    if [ ! -f "public/icons/icon-192.png" ]; then
        info "Generating PWA icons..."
        pip install cairosvg pillow -q 2>/dev/null && python scripts/gen-icons.py 2>/dev/null || warn "Icon generation skipped (install cairosvg to enable)"
    fi
    cd ..
    info "Frontend ready."
}

start_frontend() {
    info "Starting frontend on http://localhost:1420 ..."
    cd frontend
    if command -v pnpm &>/dev/null; then
        exec pnpm dev
    else
        exec npm run dev
    fi
}

# --- Main ---
echo -e "${BOLD}MaestroAgent — Dev Mode${NC}"
echo ""

check_prereqs

case "$MODE" in
    backend)
        setup_backend
        start_backend
        ;;
    frontend)
        setup_frontend
        start_frontend
        ;;
    both|"")
        setup_backend
        setup_frontend
        info "Starting both backend + frontend..."
        echo ""
        echo -e "${BOLD}Open in browser:${NC} ${BLUE}http://localhost:1420${NC}"
        echo -e "${BOLD}Backend API:${NC}   ${BLUE}http://localhost:8765${NC}"
        echo -e "${BOLD}API docs:${NC}      ${BLUE}http://localhost:8765/docs${NC}"
        echo ""
        echo "Press Ctrl+C to stop both."
        echo ""

        # Start backend in background.
        (
            cd backend
            source .venv/bin/activate
            export MAESTRO_LOG="${MAESTRO_LOG:-info}"
            export MAESTRO_FRONTEND_DIST="${MAESTRO_FRONTEND_DIST:-../frontend/dist}"
            python -m maestro_cli.main serve --host 0.0.0.0 --port 8765
        ) &
        BACKEND_PID=$!

        # Start frontend in foreground.
        (
            cd frontend
            if command -v pnpm &>/dev/null; then pnpm dev; else npm run dev; fi
        ) &
        FRONTEND_PID=$!

        # Trap Ctrl+C to kill both.
        trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
        wait
        ;;
    *)
        error "Unknown mode: $MODE. Use 'backend', 'frontend', or 'both' (default)."
        ;;
esac
