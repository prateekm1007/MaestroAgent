#!/usr/bin/env bash
# verify_c1_loop1_suppression.sh — C1 loop1 whisper suppression verification
# Authority: if this passes, C1 is FIXED. loop1 must call decide_delivery
# before firing whispers.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/download/MaestroAgent/backend"

# Check: loop1_commitment_intelligence.py must call decide_delivery
if ! grep -q "decide_delivery" maestro_oem/loop1_commitment_intelligence.py; then
  echo "FAIL: C1 — loop1_commitment_intelligence.py does not call decide_delivery"
  exit 1
fi

# Check: the test passes
if ! python3 -m pytest maestro_oem/tests/test_c1_loop1_suppression.py -q --tb=line 2>/dev/null | grep -q "3 passed"; then
  echo "FAIL: C1 — test_c1_loop1_suppression.py does not pass (3/3 expected)"
  exit 1
fi

echo "PASS: C1 — loop1 calls decide_delivery; 3/3 suppression tests pass"
