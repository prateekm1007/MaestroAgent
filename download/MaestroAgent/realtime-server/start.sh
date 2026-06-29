#!/usr/bin/env bash
# start.sh — launch the MaestroAgent realtime server.
#
# Brings up the Node.js backend (Express + ws + z-ai-web-dev-sdk)
# on port 8765. The backend serves the UI at /, the mock UI at /mock,
# the REST API at /api/*, and the live event stream at /ws/{run_id}.
#
# Once started, open http://localhost:8765/ in your browser.

set -e
cd "$(dirname "$0")"

PORT="${PORT:-8765}"

# Make sure deps are installed.
if [ ! -d node_modules ]; then
  echo "Installing dependencies..."
  npm install
fi

echo "Starting MaestroAgent realtime server on port $PORT..."
exec node server.js
