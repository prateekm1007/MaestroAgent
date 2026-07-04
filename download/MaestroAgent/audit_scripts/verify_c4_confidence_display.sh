#!/usr/bin/env bash
# verify_c4_confidence_display.sh — C4 confidence display gate verification
# Authority: if this passes, C4 is FIXED. Confidence display must gate on
# sample size < 10 → "insufficient calibration history".
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/download/MaestroAgent/backend"

# Check 1: format_confidence_for_display exists in confidence.py
if ! grep -q "def format_confidence_for_display" maestro_oem/confidence.py; then
  echo "FAIL: C4 — format_confidence_for_display not in confidence.py"
  exit 1
fi

# Check 2: oem.py uses it
if ! grep -q "format_confidence_for_display" maestro_api/routes/oem.py; then
  echo "FAIL: C4 — oem.py does not use format_confidence_for_display"
  exit 1
fi

# Check 3: the test passes
if ! python3 -m pytest maestro_oem/tests/test_c4_confidence_display_gate.py -q --tb=line 2>/dev/null | grep -q "4 passed"; then
  echo "FAIL: C4 — test_c4_confidence_display_gate.py does not pass (4/4 expected)"
  exit 1
fi

echo "PASS: C4 — format_confidence_for_display gates on sample_size < 10; 4/4 tests pass"
