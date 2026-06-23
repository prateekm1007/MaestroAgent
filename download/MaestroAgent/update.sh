#!/usr/bin/env bash
# MaestroAgent — one-click update script.
#
# Usage:
#   ./update.sh
#
# This script:
#   1. Pulls the latest code from git.
#   2. Rebuilds the Docker images.
#   3. Restarts the stack with zero downtime (rolling restart).
#   4. Verifies health.
#
# Data volumes are preserved — your runs, memory, and settings survive.

set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

echo -e "${BOLD}MaestroAgent — Updater${NC}"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# --- 1. Check for docker compose ---
if ! docker compose version &> /dev/null; then
    error "Docker Compose not found. Install it: https://docs.docker.com/compose/install/"
fi

# --- 2. Pull latest code ---
if [ -d ".git" ]; then
    info "Pulling latest code from git..."
    git pull --ff-only || warn "git pull failed (maybe local changes?) — continuing with current code"
else
    warn "Not a git repo — skipping pull. To update, re-clone or download the latest release."
fi

# --- 3. Rebuild images ---
info "Rebuilding Docker images (this may take a few minutes)..."
docker compose build --pull

# --- 4. Rolling restart ---
info "Restarting services (zero downtime)..."
docker compose up -d --remove-orphans

# --- 5. Wait for health ---
info "Waiting for the engine to come back online..."
for i in {1..30}; do
    if curl -sf http://localhost:8765/api/health &> /dev/null; then
        break
    fi
    sleep 1
    [ $i -eq 30 ] && error "Engine did not come online within 30s. Check: docker compose logs"
done

# --- 6. Show current version ---
VERSION=$(curl -s http://localhost:8765/api/health | grep -o '"version":"[^"]*"' | cut -d'"' -f4 || echo "unknown")
echo ""
echo -e "${BOLD}${GREEN}✓ MaestroAgent updated to v${VERSION}${NC}"
echo ""
echo "  PWA + API:  http://localhost:8765"
echo "  Health:     $(curl -s http://localhost:8765/api/health)"
echo ""
echo "  To check for new releases: https://github.com/your-org/maestroagent/releases"
echo ""
