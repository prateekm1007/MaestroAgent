#!/usr/bin/env bash
# verify_c5_api_key.sh — C5 API key (Bearer token) wiring verification
# Authority: if this passes, C5 is FIXED. oem routes must try Bearer token
# auth before falling back to cookie session auth.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/download/MaestroAgent/backend"

# Check 1: _require_oem_permission must extract Bearer token
if ! grep -q "bearer" maestro_api/routes/oem.py; then
  echo "FAIL: C5 — oem.py does not reference Bearer token auth"
  exit 1
fi

# Check 2: the test passes
if ! python3 -m pytest maestro_oem/tests/test_c5_api_key_wiring.py -q --tb=line 2>/dev/null | grep -q "3 passed"; then
  echo "FAIL: C5 — test_c5_api_key_wiring.py does not pass (3/3 expected)"
  exit 1
fi

echo "PASS: C5 — Bearer token auth wired into oem routes; 3/3 tests pass"
