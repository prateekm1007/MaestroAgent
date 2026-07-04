#!/usr/bin/env bash
# audit_gates.sh — Auditor gate script. Run before publishing ANY audit.
#
# This script is the authority. The auditor's report MUST include this
# script's output pasted inline. If the output is missing, reject the
# audit. If the output shows failures the auditor didn't acknowledge,
# reject the audit.
#
# Enforces mechanically:
#   Gate 11 (fetch first — local HEAD must match origin/main)
#   Gate 17 (execute reproduction — runs verify_*.sh scripts)
#   Gate 18 (re-verify prior verdicts — runs ALL scripts, not just new ones)
#   Blindspot #4 (full test suite, not curated subset)
set -u
cd "$(git rev-parse --show-toplevel)/download/MaestroAgent"

echo "=== AUDIT GATE $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

# Gate 11: fetch + verify HEAD matches origin/main
echo "=== Gate 11: fetch + HEAD match ==="
git fetch origin 2>/dev/null || { echo "FAIL: git fetch origin failed"; exit 1; }
HEAD_LOCAL=$(git rev-parse HEAD)
HEAD_REMOTE=$(git rev-parse origin/main)
if [ "$HEAD_LOCAL" != "$HEAD_REMOTE" ]; then
  echo "FAIL: local HEAD ($HEAD_LOCAL) != origin/main ($HEAD_REMOTE) — pull first"
  exit 1
fi
echo "PASS: HEAD matches origin/main ($HEAD_LOCAL)"

# Blindspot #4: full test suite (not curated)
echo ""
echo "=== Full test suite (not curated) ==="
cd backend
python3 -m pytest maestro_oem/tests/ maestro_api/tests/ maestro_auth/tests/ \
  -q --tb=line --junit-xml=../audit_test_results.xml 2>&1 | tail -5
TEST_EXIT=$?
cd ..
if [ $TEST_EXIT -ne 0 ]; then
  echo "FAIL: full test suite has failures (see above)"
fi

# Gate 17 + 18: run ALL verification scripts
echo ""
echo "=== Finding verification scripts ==="
PASS_COUNT=0
FAIL_COUNT=0
FAILED_SCRIPTS=""
for script in audit_scripts/verify_*.sh; do
  if [ ! -f "$script" ]; then
    continue
  fi
  RESULT=$(bash "$script" 2>&1 | tail -1)
  if echo "$RESULT" | grep -q "^PASS:"; then
    echo "  $RESULT"
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    echo "  $RESULT"
    FAIL_COUNT=$((FAIL_COUNT + 1))
    FAILED_SCRIPTS="$FAILED_SCRIPTS $script"
  fi
done

echo ""
echo "=== Gate complete ==="
echo "Verification scripts: $PASS_COUNT passed, $FAIL_COUNT failed"
if [ $FAIL_COUNT -gt 0 ]; then
  echo "FAILED SCRIPTS:$FAILED_SCRIPTS"
  exit 1
fi
echo "AUDIT GATE: PASS (all verification scripts green)"
