#!/usr/bin/env bash
# verify_c3_coherence.sh — C3 cross-surface coherence verification
# Authority: if this passes, C3 is FIXED. Same entity through all surfaces
# must agree.
#
# This script is the AUTHORITY — not a grep. It runs the real
# test_cross_surface_coherence.py which queries Globex + Initech through
# all 6 surfaces (Briefing/Ask/Whisper/Preparation/Situation/Timeline)
# and asserts cross-surface agreement.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/download/MaestroAgent/backend"

# Check 1: AskPipeline uses SituationBuilder (structural)
if ! grep -q "SituationBuilder" maestro_oem/ask_pipeline.py; then
  echo "FAIL: C3 — AskPipeline does not use SituationBuilder"
  exit 1
fi

# Check 2: the real cross-surface coherence test exists
if [ ! -f "maestro_oem/tests/test_cross_surface_coherence.py" ]; then
  echo "FAIL: C3 — test_cross_surface_coherence.py does not exist"
  exit 1
fi

# Check 3: the real cross-surface coherence test PASSES (the authority)
# This is the test the auditor flagged as missing 3 times. It queries all
# 6 surfaces horizontally and asserts agreement. If this fails, C3 is open
# — even if the grep passes.
RESULT=$(python3 -m pytest maestro_oem/tests/test_cross_surface_coherence.py -q --tb=line 2>&1 || true)
if echo "$RESULT" | grep -q "2 passed"; then
  echo "PASS: C3 — cross-surface coherence test passes (Globex + Initech across 6 surfaces)"
else
  echo "FAIL: C3 — test_cross_surface_coherence.py does not pass (2/2 expected)"
  echo "$RESULT" | tail -5
  exit 1
fi
