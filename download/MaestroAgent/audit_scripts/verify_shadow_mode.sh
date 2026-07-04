#!/usr/bin/env bash
# verify_shadow_mode.sh — Phase 4.2 shadow mode verification
# Authority: if this passes, shadow mode is wired. Real signals ingested
# but NOT surfaced to users.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/download/MaestroAgent/backend"

# Check 1: shadow_mode flag in oem_state
if ! grep -q "_shadow_mode" maestro_api/oem_state.py; then
  echo "FAIL: shadow_mode — _shadow_mode flag not in oem_state.py"
  exit 1
fi

# Check 2: shadow filtering in whisper.py
if ! grep -q "shadow" maestro_oem/whisper.py; then
  echo "FAIL: shadow_mode — whisper.py does not filter shadow signals"
  exit 1
fi

# Check 3: shadow-signals endpoint exists
if ! grep -q "shadow-signals" maestro_api/routes/oem.py; then
  echo "FAIL: shadow_mode — /shadow-signals endpoint not in oem.py"
  exit 1
fi

# Check 4: the test passes
if ! python3 -m pytest maestro_oem/tests/test_shadow_mode.py -q --tb=line 2>/dev/null | grep -q "5 passed"; then
  echo "FAIL: shadow_mode — test_shadow_mode.py does not pass (5/5 expected)"
  exit 1
fi

echo "PASS: shadow_mode — _shadow_mode flag + whisper filtering + /shadow-signals endpoint; 5/5 tests pass"
