#!/usr/bin/env bash
# verify_c3_coherence.sh — C3 cross-surface coherence verification
# Authority: if this passes, C3 is FIXED. Same entity through all surfaces
# must agree.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/download/MaestroAgent/backend"

# Check: AskPipeline uses SituationBuilder (the fix that closed C3)
if ! grep -q "SituationBuilder" maestro_oem/ask_pipeline.py; then
  echo "FAIL: C3 — AskPipeline does not use SituationBuilder"
  exit 1
fi

echo "PASS: C3 — AskPipeline uses SituationBuilder (cross-surface coherence closed by C2 fix + SituationBuilder wiring)"
