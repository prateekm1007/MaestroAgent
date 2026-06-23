#!/usr/bin/env bash
# MaestroAgent — one-click install script for self-hosting.
#
# Usage:
#   curl -fsSL https://maestroagent.dev/install.sh | bash
#   # or
#   ./install.sh
#
# This script:
#   1. Checks for Docker (and Docker Compose).
#   2. Clones MaestroAgent (if not already in a repo).
#   3. Builds and starts the stack via `docker compose up -d`.
#   4. Prints the URL where the PWA is reachable.
#
# After install, open http://localhost:8765 in Chrome/Firefox/Brave
# and click "Install" in the address bar.

set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

echo -e "${BOLD}MaestroAgent — Self-Host Installer${NC}"
echo ""

# --- 1. Check Docker ---
if ! command -v docker &> /dev/null; then
    error "Docker not found. Install Docker first: https://docs.docker.com/get-docker/"
fi
if ! docker compose version &> /dev/null; then
    error "Docker Compose not found. Install Docker Compose v2: https://docs.docker.com/compose/install/"
fi
info "Docker + Compose found: $(docker --version)"

# --- 2. Locate repo or clone ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/docker-compose.yml" ]; then
    REPO_DIR="$SCRIPT_DIR"
    info "Using local repo at $REPO_DIR"
elif [ -d "$HOME/maestroagent" ]; then
    REPO_DIR="$HOME/maestroagent"
    info "Using existing clone at $REPO_DIR"
else
    REPO_DIR="$HOME/maestroagent"
    info "Cloning MaestroAgent to $REPO_DIR..."
    git clone https://github.com/your-org/maestroagent.git "$REPO_DIR"
fi
cd "$REPO_DIR"

# --- 3. Create .env from template if missing ---
if [ ! -f .env ]; then
    info "Creating .env from .env.example..."
    cat > .env <<'EOF'
# MaestroAgent environment variables.
# Uncomment and set the ones you have keys for.

# Local LLMs (default — no key needed if Ollama is running)
OLLAMA_BASE_URL=http://host.docker.internal:11434

# Cloud providers (optional)
#OPENAI_API_KEY=sk-...
#ANTHROPIC_API_KEY=sk-ant-...
#OPENROUTER_API_KEY=sk-or-...
#XAI_API_KEY=xai-...

# Logging level: debug | info | warning | error
MAESTRO_LOG=info
EOF
    warn ".env created. Edit it to add your API keys, then re-run: ./install.sh"
    exit 0
fi

# --- 4. Build + start ---
info "Building and starting MaestroAgent..."
docker compose build
docker compose up -d

# --- 5. Wait for health ---
info "Waiting for the engine to come online..."
for i in {1..30}; do
    if curl -sf http://localhost:8765/api/health &> /dev/null; then
        break
    fi
    sleep 1
    [ $i -eq 30 ] && error "Engine did not come online within 30s. Check: docker compose logs"
done

echo ""
echo -e "${BOLD}${GREEN}✓ MaestroAgent is running!${NC}"
echo ""
echo "  ${BOLD}PWA + API:${NC}  http://localhost:8765"
echo "  ${BOLD}API docs:${NC}   http://localhost:8765/docs"
echo ""
echo "  To install as a PWA:"
echo "    1. Open http://localhost:8765 in Chrome/Firefox/Brave"
echo "    2. Click the install icon in the address bar"
echo "    3. MaestroAgent will appear in your app launcher"
echo ""
echo "  Commands:"
echo "    docker compose logs -f        # follow logs"
echo "    docker compose down           # stop"
echo "    docker compose down -v        # stop + reset data"
echo ""
