#!/usr/bin/env bash
# pilot_smoke.sh — Verify pilot readiness from docs only.
#
# Per acceptance checklist I3: 'script can be run from docs, verifies
# health + key executive routes.'
#
# Usage:
#   cd download/MaestroAgent
#   bash scripts/pilot_smoke.sh
#
# Prerequisites:
#   - Python 3.12+ with pip
#   - The backend package installed (pip install -e backend)

set -e

echo "══════════════════════════════════════════════════════════"
echo "MAESTRO PILOT SMOKE TEST"
echo "══════════════════════════════════════════════════════════"
echo ""

# Configuration
PORT=8765
BASE_URL="http://localhost:${PORT}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="${REPO_DIR}/backend"

# Environment
export MAESTRO_LOCAL_DEV=true
export MAESTRO_DEMO_SEED=true
export MAESTRO_APP_DIR="${REPO_DIR}"
export MAESTRO_AUTH_DB="/tmp/maestro_pilot_smoke_auth.db"
export MAESTRO_ADMIN_PASSWORD="pilot-smoke-test"
export MAESTRO_USE_COUNCIL=true

# Step 1: Check Python
echo "▶ Step 1: Checking Python..."
python3 --version
echo ""

# Step 2: Start backend
echo "▶ Step 2: Starting backend on port ${PORT}..."
cd "${BACKEND_DIR}"

# Kill any existing server on this port
lsof -ti:${PORT} 2>/dev/null | xargs kill -9 2>/dev/null || true

# Start the server in background
python3 -m maestro_api.main &
SERVER_PID=$!
echo "  Server PID: ${SERVER_PID}"

# Wait for server to be ready
echo "  Waiting for server..."
for i in $(seq 1 30); do
    if curl -s "${BASE_URL}/api/health" > /dev/null 2>&1; then
        echo "  Server ready after ${i}s"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "  FAIL: Server did not start within 30s"
        kill $SERVER_PID 2>/dev/null || true
        exit 1
    fi
    sleep 1
done
echo ""

# Step 3: Health check
echo "▶ Step 3: Health check..."
HEALTH=$(curl -s "${BASE_URL}/api/health")
echo "  ${HEALTH}"
echo ""

# Step 4: Council situations (cold start — no OEM warmup)
echo "▶ Step 4: Council situations (cold start)..."
SITUATIONS=$(curl -s "${BASE_URL}/api/council/situations")
SIT_COUNT=$(echo "$SITUATIONS" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('situations',[])))" 2>/dev/null || echo "0")
echo "  Situations: ${SIT_COUNT}"
if [ "$SIT_COUNT" -gt 0 ] 2>/dev/null; then
    echo "  PASS: Council cold start works"
else
    echo "  FAIL: No situations on cold start"
fi
echo ""

# Step 5: Ask
echo "▶ Step 5: Ask..."
ASK=$(curl -s -X POST "${BASE_URL}/api/council/ask" \
    -H "Content-Type: application/json" \
    -d '{"query": "What is happening with Globex?"}')
ANSWER_LEN=$(echo "$ASK" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('answer','')))" 2>/dev/null || echo "0")
echo "  Answer length: ${ANSWER_LEN} chars"
if [ "$ANSWER_LEN" -gt 0 ] 2>/dev/null; then
    echo "  PASS: Ask returns answer"
else
    echo "  FAIL: Ask returned empty answer"
fi
echo ""

# Step 6: Briefing
echo "▶ Step 6: Briefing..."
BRIEFING=$(curl -s -X POST "${BASE_URL}/api/council/briefing" \
    -H "Content-Type: application/json" \
    -d '{"user_email": "", "org_id": "default", "briefing_type": "morning"}')
BRIEFING_OK=$(echo "$BRIEFING" | python3 -c "import sys,json; d=json.load(sys.stdin); print('ok' if d.get('generated_at') or d.get('greeting') else 'fail')" 2>/dev/null || echo "fail")
echo "  Briefing: ${BRIEFING_OK}"
echo ""

# Step 7: XSS regression
echo "▶ Step 7: XSS regression..."
XSS_RESP=$(curl -s "${BASE_URL}/api/oem/ask?q=<script>alert(1)</script>")
if echo "$XSS_RESP" | grep -q "<script>"; then
    echo "  FAIL: XSS payload not escaped"
else
    echo "  PASS: XSS payload escaped"
fi
echo ""

# Step 8: Council default mode
echo "▶ Step 8: Council default mode..."
HTML=$(curl -s "${BASE_URL}/")
if echo "$HTML" | grep -q "MAESTRO_USE_COUNCIL = true"; then
    echo "  PASS: Council is default"
else
    echo "  FAIL: Council not default"
fi
echo ""

# Cleanup
echo "▶ Cleanup: Stopping server..."
kill $SERVER_PID 2>/dev/null || true
echo ""

# Summary
echo "══════════════════════════════════════════════════════════"
echo "PILOT SMOKE COMPLETE"
echo "══════════════════════════════════════════════════════════"
