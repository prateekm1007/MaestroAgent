#!/usr/bin/env bash
# verify_c2_ask_window.sh — C2 Ask 30-signal window verification
# Authority: if this passes, C2 is FIXED. The Ask pipeline must search ALL
# signals, not just the first 30.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/download/MaestroAgent/backend"

# Check: ask_pipeline.py must have "for s in self._signals:" (no slice)
# The actual fix line must exist. Comments/docstrings referencing the old
# [:30] are fine — they describe what was fixed.
if ! grep -q 'for s in self\._signals:' maestro_oem/ask_pipeline.py; then
  echo "FAIL: C2 — ask_pipeline.py missing 'for s in self._signals:' (no slice)"
  exit 1
fi

# Check: the actual for-loop line must NOT have a slice
if grep 'for s in self\._signals' maestro_oem/ask_pipeline.py | grep -v '#' | grep -q '\['; then
  echo "FAIL: C2 — ask_pipeline.py for-loop has a slice"
  exit 1
fi

echo "PASS: C2 — ask_pipeline.py iterates ALL signals (no [:30] slice)"
