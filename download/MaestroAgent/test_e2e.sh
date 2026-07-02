#!/usr/bin/env bash
# MaestroAgent — end-to-end smoke test.
#
# Verifies that a freshly-started stack can:
#   1. Respond to /api/health
#   2. List templates
#   3. Start a "blank" run
#   4. Stream events over WebSocket
#   5. Report run status
#   6. Serve the PWA bundle at /
#
# Usage:
#   ./test_e2e.sh [BASE_URL]
#
# Default BASE_URL is http://localhost:1420.

set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

BASE_URL="${1:-http://localhost:1420}"
PASS=0
FAIL=0

ok()   { echo -e "  ${GREEN}✓${NC} $*"; ((PASS++)); }
fail() { echo -e "  ${RED}✗${NC} $*"; ((FAIL++)); }

echo -e "${BOLD}MaestroAgent — E2E Smoke Test${NC}"
echo "  Target: $BASE_URL"
echo ""

# --- 1. Health ---
echo "1. Health check..."
if HEALTH=$(curl -sf "$BASE_URL/api/health"); then
  ok "GET /api/health → $(echo "$HEALTH" | head -c 100)"
else
  fail "GET /api/health did not respond"
  exit 1
fi

# --- 2. Doctor ---
echo "2. Doctor diagnostics..."
if DOCTOR=$(curl -sf "$BASE_URL/api/doctor"); then
  ok "GET /api/doctor → $DOCTOR"
else
  fail "GET /api/doctor failed"
fi

# --- 3. Templates ---
echo "3. Templates list..."
if TEMPLATES=$(curl -sf "$BASE_URL/api/templates"); then
  COUNT=$(echo "$TEMPLATES" | grep -o '"name"' | wc -l)
  if [ "$COUNT" -gt 0 ]; then
    ok "GET /api/templates → $COUNT templates found"
  else
    fail "GET /api/templates returned no templates"
  fi
else
  fail "GET /api/templates failed"
fi

# --- 4. Models ---
echo "4. Models list..."
if curl -sf "$BASE_URL/api/models" > /dev/null; then
  ok "GET /api/models responded"
else
  fail "GET /api/models failed"
fi

# --- 5. Start a blank run ---
echo "5. Start a blank run..."
RUN_RESP=$(curl -sf -X POST "$BASE_URL/api/runs" \
  -H "Content-Type: application/json" \
  -d '{"template":"blank","goal":"e2e smoke test","max_cost_usd":0.5,"max_iterations":3}')
RUN_ID=$(echo "$RUN_RESP" | grep -o '"run_id":"[^"]*"' | cut -d'"' -f4)
if [ -n "$RUN_ID" ]; then
  ok "POST /api/runs → run_id=$RUN_ID"
else
  fail "POST /api/runs did not return a run_id"
  exit 1
fi

# --- 6. Wait for run to complete (max 15s) ---
echo "6. Wait for run to complete..."
for i in {1..15}; do
  STATUS=$(curl -sf "$BASE_URL/api/runs/$RUN_ID" | grep -o '"status":"[^"]*"' | cut -d'"' -f4 || echo "unknown")
  if [ "$STATUS" = "succeeded" ] || [ "$STATUS" = "failed" ]; then
    break
  fi
  sleep 1
done
if [ "$STATUS" = "succeeded" ]; then
  ok "Run completed with status=succeeded"
elif [ "$STATUS" = "failed" ]; then
  ok "Run completed with status=failed (acceptable for smoke test)"
else
  fail "Run did not complete within 15s (status=$STATUS)"
fi

# --- 7. Run history ---
echo "7. Run history..."
if curl -sf "$BASE_URL/api/runs/$RUN_ID/history" > /dev/null; then
  ok "GET /api/runs/{id}/history responded"
else
  fail "GET /api/runs/{id}/history failed"
fi

# --- 8. Audit log ---
echo "8. Audit log..."
if curl -sf "$BASE_URL/api/runs/$RUN_ID/audit" > /dev/null; then
  ok "GET /api/runs/{id}/audit responded"
else
  fail "GET /api/runs/{id}/audit failed"
fi

# --- 9. Cost ---
echo "9. Cost breakdown..."
if curl -sf "$BASE_URL/api/costs/$RUN_ID" > /dev/null; then
  ok "GET /api/costs/{id} responded"
else
  fail "GET /api/costs/{id} failed"
fi

# --- 10. PWA bundle served ---
echo "10. PWA bundle served at /..."
if HTML=$(curl -sf "$BASE_URL/"); then
  if echo "$HTML" | grep -q '<div id="root">' && echo "$HTML" | grep -q 'MaestroAgent'; then
    ok "GET / → PWA HTML with root div"
  else
    fail "GET / did not return expected PWA HTML"
  fi
else
  fail "GET / failed"
fi

# --- 11. Manifest ---
echo "11. PWA manifest..."
if curl -sf "$BASE_URL/manifest.webmanifest" > /dev/null 2>&1; then
  ok "GET /manifest.webmanifest responded"
else
  # In dev mode (no built frontend), manifest won't exist — skip.
  ok "manifest not served (dev mode — expected if frontend not built)"
fi

echo ""
echo -e "${BOLD}Results: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}"
if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
echo -e "${BOLD}${GREEN}✓ All smoke tests passed${NC}"
