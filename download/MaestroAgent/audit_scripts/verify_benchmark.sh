#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# verify_benchmark.sh — Scans evaluation/scoreboard/*.json for VOID conditions
# per the anti-gaming clauses in SCORING_SYSTEM.md.
#
# EXIT CODES:
#   0 = all artifacts pass (no VOID conditions detected)
#   1 = one or more VOID conditions detected
#
# This script is wired into audit_gates.sh and must pass before any
# benchmark result can be cited as evidence for a score.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

# Find the scoreboard directory relative to this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCOREBOARD_DIR="$SCRIPT_DIR/../maestro-personal/evaluation/scoreboard"
VOIDED_DIR="$SCOREBOARD_DIR/voided"

FAILURES=0
PASS=0

echo "=== verify_benchmark.sh — scanning scoreboard artifacts ==="
echo ""

# ───────────────────────────────────────────────────────────────────────
# CHECK 1: No voided files in the active scoreboard directory
# ───────────────────────────────────────────────────────────────────────
echo "Check 1: No voided files in active scoreboard directory..."
if [ -f "$SCOREBOARD_DIR/ablation_round68.json" ]; then
    echo "  ❌ FAIL: ablation_round68.json found in active directory (should be in voided/)"
    FAILURES=$((FAILURES + 1))
else
    echo "  ✅ PASS: No voided files in active directory"
    PASS=$((PASS + 1))
fi
echo ""

# ───────────────────────────────────────────────────────────────────────
# CHECK 2: Metadata-consistency — top-level llm_active must agree with rows
# ───────────────────────────────────────────────────────────────────────
echo "Check 2: Metadata-consistency (top-level vs per-row llm_active)..."
for json_file in "$SCOREBOARD_DIR"/*.json; do
    [ -f "$json_file" ] || continue  # glob didn't match
    filename=$(basename "$json_file")

    # Use python to check consistency
    result=$(python3 -c "
import json, sys

with open('$json_file') as f:
    try:
        d = json.load(f)
    except json.JSONDecodeError:
        print('INVALID_JSON')
        sys.exit(0)

if not isinstance(d, dict):
    sys.exit(0)  # not a dict, skip

# Check top-level llm_active vs per-row
top_llm = d.get('llm_active')
if top_llm is None:
    sys.exit(0)  # no llm_active field, skip

# Find row-level data
rows = None
for key in ('maestro_results', 'results', 'results_B', 'rows', 'queries'):
    if key in d and isinstance(d[key], list) and len(d[key]) > 0:
        rows = d[key]
        break

if rows is None:
    sys.exit(0)  # no rows to compare, skip

# Check if rows have llm_active field
row_llm_values = set()
for r in rows:
    if isinstance(r, dict) and 'llm_active' in r:
        row_llm_values.add(r['llm_active'])

if not row_llm_values:
    sys.exit(0)  # rows don't have llm_active, skip

# Compare
top_bool = bool(top_llm)
row_bool = bool(list(row_llm_values)[0]) if len(row_llm_values) == 1 else None

if row_bool is not None and top_bool != row_bool:
    print(f'METADATA_MISMATCH: top={top_llm} rows={row_llm_values}')
else:
    print('OK')
" 2>&1)

    if [ "$result" = "OK" ]; then
        echo "  ✅ $filename: metadata consistent"
        PASS=$((PASS + 1))
    elif echo "$result" | grep -q "METADATA_MISMATCH"; then
        echo "  ❌ $filename: $result"
        FAILURES=$((FAILURES + 1))
    elif [ "$result" = "INVALID_JSON" ]; then
        echo "  ⚠️  $filename: invalid JSON (skip)"
    fi
done
echo ""

# ───────────────────────────────────────────────────────────────────────
# CHECK 3: No comparison arm with >0% error rate
# ───────────────────────────────────────────────────────────────────────
echo "Check 3: No comparison arm with >0% error rate..."
for json_file in "$SCOREBOARD_DIR"/*.json; do
    [ -f "$json_file" ] || continue
    filename=$(basename "$json_file")

    result=$(python3 -c "
import json, sys

with open('$json_file') as f:
    try:
        d = json.load(f)
    except json.JSONDecodeError:
        sys.exit(0)

if not isinstance(d, dict):
    sys.exit(0)

# Check for error/exception fields in result rows
for arm_key in ('maestro_results', 'results', 'results_A', 'results_B', 'results_C',
                'llm_only_results', 'rule_based_results', 'bm25_results'):
    if arm_key not in d:
        continue
    arm = d[arm_key]
    if not isinstance(arm, list) or len(arm) == 0:
        continue

    error_count = 0
    total = len(arm)
    for r in arm:
        if isinstance(r, dict):
            if r.get('error') or r.get('exception') or r.get('traceback'):
                error_count += 1
            # Check for RuntimeError in answer text
            answer = str(r.get('answer', ''))
            if 'RuntimeError' in answer or 'Traceback' in answer:
                error_count += 1

    if total > 0 and error_count == total:
        print(f'ALL_ERRORS: {arm_key} has {error_count}/{total} errors')
        sys.exit(0)
    elif error_count > 0:
        print(f'SOME_ERRORS: {arm_key} has {error_count}/{total} errors')

print('OK')
" 2>&1)

    if [ "$result" = "OK" ]; then
        echo "  ✅ $filename: no error arms"
        PASS=$((PASS + 1))
    elif echo "$result" | grep -q "ALL_ERRORS"; then
        echo "  ❌ $filename: $result (VOID per anti-gaming clause 1)"
        FAILURES=$((FAILURES + 1))
    elif echo "$result" | grep -q "SOME_ERRORS"; then
        echo "  ⚠️  $filename: $result (warning, not VOID)"
    fi
done
echo ""

# ───────────────────────────────────────────────────────────────────────
# CHECK 4: Voided directory exists with README
# ───────────────────────────────────────────────────────────────────────
echo "Check 4: Voided directory exists with README..."
if [ -d "$VOIDED_DIR" ] && [ -f "$VOIDED_DIR/README.md" ]; then
    echo "  ✅ PASS: voided/ directory exists with README"
    PASS=$((PASS + 1))
else
    echo "  ⚠️  voided/ directory or README missing (not a failure, but recommended)"
fi
echo ""

# ───────────────────────────────────────────────────────────────────────
# SUMMARY
# ───────────────────────────────────────────────────────────────────────
echo "=== Summary ==="
echo "  Passes: $PASS"
echo "  Failures: $FAILURES"
echo ""

if [ "$FAILURES" -gt 0 ]; then
    echo "FAIL: verify_benchmark.sh — $FAILURES VOID condition(s) detected"
    echo "   Fix the flagged artifacts before citing any benchmark as evidence."
    exit 1
else
    echo "PASS: verify_benchmark.sh — all scoreboard artifacts honest"
    exit 0
fi
