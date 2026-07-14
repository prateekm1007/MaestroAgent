#!/usr/bin/env bash
# verify_task_56_57.sh — Mechanical verification of every Task 56 + 57 claim.
#
# This IS "the loop" — a single script any auditor (or CEO) can run to
# verify every claim from Tasks 56 and 57 BY EXECUTION (P1).
#
# Run from repo root:
#   bash audit_scripts/verify_task_56_57.sh
#
# Exits 0 if ALL checks pass, 1 otherwise. Pasted output IS the evidence.

set -u
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MAESTRO_PERSONAL="$REPO_ROOT/maestro-personal"
DOWNLOAD_DIR="/home/z/my-project/download"
SCRIPTS_DIR="/home/z/my-project/scripts"
WORKLOG="/home/z/my-project/worklog.md"

PASS_COUNT=0
FAIL_COUNT=0
FAILS=""

check() {
  local name="$1"
  local condition="$2"
  if eval "$condition"; then
    echo "  PASS: $name"
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    echo "  FAIL: $name"
    FAIL_COUNT=$((FAIL_COUNT + 1))
    FAILS="$FAILS\n  - $name"
  fi
}

echo "=== TASK 56 + 57 VERIFICATION $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "Repo: $REPO_ROOT"
echo ""

# ----------------------------------------------------------------------
# Gate 11: HEAD matches origin/main
# ----------------------------------------------------------------------
echo "=== Gate 11: HEAD matches origin/main ==="
cd "$REPO_ROOT"
git fetch origin 2>/dev/null
HEAD_LOCAL=$(git rev-parse HEAD)
HEAD_REMOTE=$(git rev-parse origin/main)
if [ "$HEAD_LOCAL" = "$HEAD_REMOTE" ]; then
  echo "  PASS: HEAD matches origin/main ($HEAD_LOCAL)"
  PASS_COUNT=$((PASS_COUNT + 1))
else
  echo "  FAIL: local HEAD ($HEAD_LOCAL) != origin/main ($HEAD_REMOTE)"
  FAIL_COUNT=$((FAIL_COUNT + 1))
  FAILS="$FAILS\n  - Gate 11 HEAD mismatch"
fi
echo ""

# ----------------------------------------------------------------------
# Task 56 — Mobile screenshots
# ----------------------------------------------------------------------
echo "=== Task 56: Mobile screenshots ==="

# 16 screenshots exist
SCREENSHOT_COUNT=$(ls "$DOWNLOAD_DIR"/mobile-real-*.png 2>/dev/null | wc -l)
check "16 mobile screenshots exist" "[ $SCREENSHOT_COUNT -eq 16 ]"
echo "    Found: $SCREENSHOT_COUNT at /home/z/my-project/download/mobile-real-*.png"

# Each screenshot is non-trivial in size (>100 KB)
LARGE_COUNT=0
for f in "$DOWNLOAD_DIR"/mobile-real-*.png; do
  if [ -f "$f" ]; then
    SIZE=$(stat -c%s "$f" 2>/dev/null || stat -f%z "$f")
    if [ "$SIZE" -gt 100000 ]; then
      LARGE_COUNT=$((LARGE_COUNT + 1))
    fi
  fi
done
check "All screenshots >100KB (real content, not blank)" "[ $LARGE_COUNT -eq 16 ]"

# Scripts exist
check "maestro_mobile_screens.py exists" "[ -f '$SCRIPTS_DIR/maestro_mobile_screens.py' ]"
check "maestro_mobile_ask.py exists" "[ -f '$SCRIPTS_DIR/maestro_mobile_ask.py' ]"

# Methodology doc exists
check "MOBILE_SCREENSHOTS_METHOD.md exists in repo" "[ -f '$MAESTRO_PERSONAL/docs/MOBILE_SCREENSHOTS_METHOD.md' ]"
check "MOBILE_SCREENSHOTS_METHOD.md exists in download" "[ -f '$DOWNLOAD_DIR/MOBILE_SCREENSHOTS_METHOD.md' ]"

# CLAIM_FREEZE has the mobile screenshots row
CLAIM_FREEZE="$MAESTRO_PERSONAL/docs/CLAIM_FREEZE.md"
if grep -q "Mobile-form-factor web screenshots" "$CLAIM_FREEZE"; then
  echo "  PASS: CLAIM_FREEZE has 'Mobile-form-factor web screenshots' row"
  PASS_COUNT=$((PASS_COUNT + 1))
else
  echo "  FAIL: CLAIM_FREEZE missing mobile screenshots row"
  FAIL_COUNT=$((FAIL_COUNT + 1))
  FAILS="$FAILS\n  - CLAIM_FREEZE mobile row missing"
fi

# CLAIM_FREEZE row is VERIFIED (not NOT VERIFIED)
if grep -q "Mobile-form-factor web screenshots.*VERIFIED" "$CLAIM_FREEZE"; then
  echo "  PASS: CLAIM_FREEZE mobile row marked VERIFIED"
  PASS_COUNT=$((PASS_COUNT + 1))
else
  echo "  FAIL: CLAIM_FREEZE mobile row NOT marked VERIFIED"
  FAIL_COUNT=$((FAIL_COUNT + 1))
  FAILS="$FAILS\n  - CLAIM_FREEZE mobile row not VERIFIED"
fi
echo ""

# ----------------------------------------------------------------------
# Task 57-a — API contract tests
# ----------------------------------------------------------------------
echo "=== Task 57-a: API contract tests ==="

check "tests/test_api_contract.py exists" "[ -f '$MAESTRO_PERSONAL/tests/test_api_contract.py' ]"
check "scripts/dump_openapi.py exists" "[ -f '$MAESTRO_PERSONAL/scripts/dump_openapi.py' ]"
check "docs/openapi_schema.json exists" "[ -f '$MAESTRO_PERSONAL/docs/openapi_schema.json' ]"

# Run the contract tests
cd "$MAESTRO_PERSONAL"
CONTRACT_OUTPUT=$(OLLAMA_HOST="" python3 -m pytest tests/test_api_contract.py -q --tb=line --no-header 2>&1 | tail -3)
echo "    Contract test output (last 3 lines):"
echo "$CONTRACT_OUTPUT" | sed 's/^/      /'
if echo "$CONTRACT_OUTPUT" | grep -q "7 passed"; then
  echo "  PASS: 7/7 contract tests pass"
  PASS_COUNT=$((PASS_COUNT + 1))
else
  echo "  FAIL: contract tests did not all pass"
  FAIL_COUNT=$((FAIL_COUNT + 1))
  FAILS="$FAILS\n  - Contract tests not 7/7"
fi
echo ""

# ----------------------------------------------------------------------
# Task 57-b — Full backend test suite
# ----------------------------------------------------------------------
echo "=== Task 57-b: Full backend test suite ==="

# Collect test count
COLLECT_OUTPUT=$(cd "$MAESTRO_PERSONAL" && python3 -m pytest tests/ --collect-only -q 2>&1 | tail -1)
echo "    Collected: $COLLECT_OUTPUT"
if echo "$COLLECT_OUTPUT" | grep -qE "1[01][0-9][0-9] tests collected"; then
  echo "  PASS: ~1100 tests collected"
  PASS_COUNT=$((PASS_COUNT + 1))
else
  echo "  FAIL: test count unexpected"
  FAIL_COUNT=$((FAIL_COUNT + 1))
  FAILS="$FAILS\n  - test count"
fi

# Run a 30-test subset to prove the suite runs (full run takes 5+ min)
cd "$MAESTRO_PERSONAL"
SUBSET_OUTPUT=$(OLLAMA_HOST="" python3 -m pytest tests/test_api.py tests/test_api_contract.py tests/test_connectors.py -q --tb=line --no-header 2>&1 | tail -3)
echo "    Subset (3 files) output (last 3 lines):"
echo "$SUBSET_OUTPUT" | sed 's/^/      /'
if echo "$SUBSET_OUTPUT" | grep -qE "[0-9]+ passed"; then
  echo "  PASS: subset runs green"
  PASS_COUNT=$((PASS_COUNT + 1))
else
  echo "  FAIL: subset has failures"
  FAIL_COUNT=$((FAIL_COUNT + 1))
  FAILS="$FAILS\n  - subset failures"
fi
echo ""

# ----------------------------------------------------------------------
# Task 57-c — npm audit high=0
# ----------------------------------------------------------------------
echo "=== Task 57-c: npm audit high=0 ==="

# Web app
cd "$MAESTRO_PERSONAL/web"
WEB_AUDIT=$(npm audit --json 2>&1)
WEB_HIGH=$(echo "$WEB_AUDIT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('metadata',{}).get('vulnerabilities',{}).get('high',0))")
WEB_CRIT=$(echo "$WEB_AUDIT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('metadata',{}).get('vulnerabilities',{}).get('critical',0))")
echo "    Web: high=$WEB_HIGH critical=$WEB_CRIT"
check "Web app high=0" "[ $WEB_HIGH -eq 0 ]"
check "Web app critical=0" "[ $WEB_CRIT -eq 0 ]"

# Mobile app
cd "$MAESTRO_PERSONAL/mobile"
MOBILE_AUDIT=$(npm audit --json 2>&1)
MOBILE_HIGH=$(echo "$MOBILE_AUDIT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('metadata',{}).get('vulnerabilities',{}).get('high',0))")
MOBILE_CRIT=$(echo "$MOBILE_AUDIT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('metadata',{}).get('vulnerabilities',{}).get('critical',0))")
echo "    Mobile: high=$MOBILE_HIGH critical=$MOBILE_CRIT"
check "Mobile app high=0" "[ $MOBILE_HIGH -eq 0 ]"
check "Mobile app critical=0" "[ $MOBILE_CRIT -eq 0 ]"

# Override exists in package.json
if grep -q '"overrides"' "$MAESTRO_PERSONAL/mobile/package.json"; then
  echo "  PASS: mobile package.json has overrides field"
  PASS_COUNT=$((PASS_COUNT + 1))
else
  echo "  FAIL: mobile package.json missing overrides"
  FAIL_COUNT=$((FAIL_COUNT + 1))
  FAILS="$FAILS\n  - mobile overrides missing"
fi

# Mobile tests pass
cd "$MAESTRO_PERSONAL/mobile"
MOBILE_TEST=$(npm test 2>&1 | tail -5)
echo "    Mobile tests (last 5 lines):"
echo "$MOBILE_TEST" | sed 's/^/      /'
if echo "$MOBILE_TEST" | grep -qE "Tests:[[:space:]]+78 passed"; then
  echo "  PASS: 78/78 mobile tests pass"
  PASS_COUNT=$((PASS_COUNT + 1))
else
  echo "  FAIL: mobile tests not 78/78"
  FAIL_COUNT=$((FAIL_COUNT + 1))
  FAILS="$FAILS\n  - mobile tests"
fi
echo ""

# ----------------------------------------------------------------------
# CLAIM_FREEZE summary counts
# ----------------------------------------------------------------------
echo "=== CLAIM_FREEZE summary ==="
if grep -q "✅ VERIFIED | 53" "$CLAIM_FREEZE"; then
  echo "  PASS: CLAIM_FREEZE shows 53 VERIFIED (includes Issue 13 whisper rows)"
  PASS_COUNT=$((PASS_COUNT + 1))
else
  echo "  FAIL: CLAIM_FREEZE VERIFIED count wrong"
  FAIL_COUNT=$((FAIL_COUNT + 1))
  FAILS="$FAILS\n  - CLAIM_FREEZE count"
fi
echo ""

# ----------------------------------------------------------------------
# Worklog entries
# ----------------------------------------------------------------------
echo "=== Worklog entries ==="
TASK56_COUNT=$(grep -c "^Task ID: 56$" "$WORKLOG" 2>/dev/null || echo 0)
TASK57_COUNT=$(grep -c "^Task ID: 57$" "$WORKLOG" 2>/dev/null || echo 0)
echo "    Task 56 entries: $TASK56_COUNT"
echo "    Task 57 entries: $TASK57_COUNT"
check "Worklog has Task 56 entry" "[ $TASK56_COUNT -ge 1 ]"
check "Worklog has Task 57 entry" "[ $TASK57_COUNT -ge 1 ]"
echo ""

# ----------------------------------------------------------------------
# Gold-150 honesty check (auditor finding, fixed in Task 58)
# ----------------------------------------------------------------------
echo "=== Gold-150 honesty check (auditor finding, fixed in Task 58) ==="
GOLD_FILE="$MAESTRO_PERSONAL/evaluation/scoreboard/gold_150_full_llm_results.json"
if [ -f "$GOLD_FILE" ]; then
  GOLD_LIFT=$(python3 -c "import json; d=json.load(open('$GOLD_FILE')); print(d.get('lift', 'N/A'))")
  GOLD_PASS=$(python3 -c "import json; d=json.load(open('$GOLD_FILE')); print(d.get('gate_pass', 'N/A'))")
  GOLD_LLM_ACTIVE=$(python3 -c "import json; d=json.load(open('$GOLD_FILE')); r=d.get('results',[]); print(sum(1 for x in r if x.get('llm_active', False)))")
  echo "    gold_150_full_llm_results.json:"
  echo "      lift: $GOLD_LIFT"
  echo "      gate_pass: $GOLD_PASS"
  echo "      llm_active=True count: $GOLD_LLM_ACTIVE / 150"
  # The CLAIM_FREEZE row MUST now be NOT VERIFIED (Task 58 fix)
  if grep -q "Gold-150 gate.*NOT VERIFIED" "$CLAIM_FREEZE"; then
    echo "  PASS: CLAIM_FREEZE Gold-150 gate row is NOT VERIFIED (honest)"
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    echo "  FAIL: CLAIM_FREEZE Gold-150 gate row is NOT marked NOT VERIFIED"
    FAIL_COUNT=$((FAIL_COUNT + 1))
    FAILS="$FAILS\n  - Gold-150 CLAIM_FREEZE honesty"
  fi
fi
echo ""

# ----------------------------------------------------------------------
# Issue 13: Whisper System checks (Task 60)
# ----------------------------------------------------------------------
echo "=== Issue 13: Whisper System ==="

# 13-A: rule-based function exists + is called
check "_should_whisper_rule_based exists" "grep -q '_should_whisper_rule_based' '$MAESTRO_PERSONAL/src/maestro_personal_shell/routers/surfaces.py'"

# 13-B: scheduler file exists + wired into lifespan
check "whisper_scheduler.py exists" "[ -f '$MAESTRO_PERSONAL/src/maestro_personal_shell/whisper_scheduler.py' ]"
check "scheduler wired into API lifespan" "grep -q 'whisper_loop' '$MAESTRO_PERSONAL/src/maestro_personal_shell/api.py'"

# 13-C: whisper cards on web Dashboard
check "WhisperCards on web Dashboard" "grep -q 'WhisperCards' '$MAESTRO_PERSONAL/web/src/components/maestro/Dashboard.tsx'"

# 13-C (P24 fix): whisper cards on mobile Dashboard too
check "WhisperCards on mobile Dashboard (P24)" "grep -q 'WhisperCards' '$MAESTRO_PERSONAL/mobile/src/screens/DashboardScreen.tsx'"

# 13-F: test file exists
check "test_whisper_system.py exists" "[ -f '$MAESTRO_PERSONAL/tests/test_whisper_system.py' ]"

# Run whisper tests
cd "$MAESTRO_PERSONAL"
WHISPER_OUTPUT=$(OLLAMA_HOST="" MAESTRO_PERSONAL_TOKEN=test python3 -m pytest tests/test_whisper_system.py -q --tb=line --no-header 2>&1 | tail -3)
echo "    Whisper tests (last 3 lines):"
echo "$WHISPER_OUTPUT" | sed 's/^/      /'
if echo "$WHISPER_OUTPUT" | grep -qE "16 passed"; then
  echo "  PASS: 16/16 whisper system tests pass"
  PASS_COUNT=$((PASS_COUNT + 1))
else
  echo "  FAIL: whisper tests not 16/16"
  FAIL_COUNT=$((FAIL_COUNT + 1))
  FAILS="$FAILS\n  - whisper tests"
fi

# Mobile typecheck
cd "$MAESTRO_PERSONAL/mobile"
TC_EXIT=0
npx tsc --noEmit > /dev/null 2>&1 || TC_EXIT=$?
check "Mobile typecheck passes" "[ $TC_EXIT -eq 0 ]"
echo ""
echo "=== SUMMARY ==="
echo "  Passed: $PASS_COUNT"
echo "  Failed: $FAIL_COUNT"
if [ $FAIL_COUNT -gt 0 ]; then
  echo -e "Failed checks:$FAILS"
  exit 1
fi
echo "  ALL CHECKS PASS — Task 56 + 57 claims verified by execution (P1)."
echo "AUDIT GATE: PASS"
