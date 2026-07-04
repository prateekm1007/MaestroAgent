#!/usr/bin/env bash
# verify_learning_loop.sh — learning loop tests verification
# Authority: if this passes, the learning loop is healthy. Runs ALL tests
# matching "learning_loop" — not a curated subset.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/download/MaestroAgent/backend"

RESULT=$(python3 -m pytest -k "learning_loop or loop4 or learning_ledger" -q --tb=line 2>&1 || true)
PASSED=$(echo "$RESULT" | grep -oP '\d+ passed' | grep -oP '\d+' || echo "0")
FAILED=$(echo "$RESULT" | grep -oP '\d+ failed' | grep -oP '\d+' || echo "0")

if [ "$FAILED" != "0" ]; then
  echo "FAIL: learning_loop — $FAILED test(s) failed ($PASSED passed)"
  echo "$RESULT" | tail -10
  exit 1
fi

if [ "$PASSED" -eq 0 ]; then
  echo "FAIL: learning_loop — 0 tests ran (no matching tests found)"
  exit 1
fi

echo "PASS: learning_loop — $PASSED test(s) pass, 0 failures"
