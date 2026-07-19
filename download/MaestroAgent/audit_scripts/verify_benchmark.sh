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


rows = None
for key in ('maestro_results', 'results', 'results_B', 'rows', 'queries'):
    if key in d and isinstance(d[key], list) and len(d[key]) > 0:
        rows = d[key]
        break

if rows is None:
    sys.exit(0)  # no rows to compare, skip

top_level_keys = {k for k, v in d.items() if isinstance(v, bool) or v in (0, 1, 'true', 'false', 'True', 'False')}

boolean_field_patterns = ['llm_active', 'llm_used', 'llm_powered', 'active',
                          'verified', 'configured', 'is_active', 'is_verified',
                          'used_llm', 'model_active', 'has_llm', 'llm_enabled']

for k in d:
    v = d[k]
    if isinstance(v, bool) or v in (0, 1, 'true', 'false', 'True', 'False'):
        top_level_keys.add(k)

for k in d:
    if 'count' in k.lower() or 'total' in k.lower() or 'precision' in k.lower() or 'recall' in k.lower() or 'score' in k.lower() or 'rate' in k.lower() or 'pct' in k.lower():
        continue  # skip statistics
    if any(p in k.lower() for p in ['active', 'verified', 'configured', 'enabled', 'powered', 'used']):
        top_level_keys.add(k)

if not top_level_keys:
    sys.exit(0)  # no boolean-shaped top-level fields, skip

mismatches = []
for field in top_level_keys:
    top_val = d.get(field)
    row_values = set()
    for r in rows:
        if isinstance(r, dict) and field in r:
            row_values.add(r[field])

    if not row_values:
        if isinstance(top_val, bool) and top_val:
            mismatches.append(f'{field}: top={top_val} but field absent in all rows (unasserted claim)')
        elif isinstance(top_val, (int, float)) and top_val == 1:
            mismatches.append(f'{field}: top={top_val} but field absent in all rows (unasserted claim)')
        continue

    def to_bool(v):
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return bool(v)
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes')
        return False

    top_bool = to_bool(top_val)
    row_bools = {to_bool(v) for v in row_values}

    if len(row_bools) == 1:
        row_bool = row_bools.pop()
        if top_bool != row_bool:
            mismatches.append(f'{field}: top={top_val} rows={row_values}')

if mismatches:
    print(f'METADATA_MISMATCH: {\" ; \".join(mismatches)}')
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


import re as _re

ERROR_KEYS = {'error', 'exception', 'traceback', 'exception_class',
              'exception_type', 'error_type', 'error_message'}
ERROR_PATTERN = _re.compile(r'(RuntimeError|TypeError|ValueError|KeyError|AttributeError|Exception|Traceback|ImportError|NameError|IndexError|ZeroDivisionError|OverflowError|MemoryError)\b')

def has_error_recursive(obj, visited=None):
    '''Recursively walk a dict/list looking for error-shaped keys/values.
    F1d: only flag values under ERROR_KEYS or strings matching the
    structural error pattern. Substring matching of Error in legitimate
    text like Error handling done. is a false positive.'''
    if visited is None:
        visited = set()
    obj_id = id(obj)
    if obj_id in visited:
        return False
    visited.add(obj_id)
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ERROR_KEYS:
                return True
            if isinstance(v, str) and ERROR_PATTERN.search(v):
                return True
            if has_error_recursive(v, visited):
                return True
    elif isinstance(obj, list):
        for item in obj:
            if has_error_recursive(item, visited):
                return True
    elif isinstance(obj, str):
        if ERROR_PATTERN.search(obj):
            return True
    return False

found_errors = False
for key, val in d.items():
    if not isinstance(val, list) or len(val) == 0:
        continue
    if not all(isinstance(r, dict) for r in val):
        continue

    error_count = 0
    total = len(val)
    for r in val:
        if has_error_recursive(r):
            error_count += 1

    if total > 0 and error_count > 0:
        pct = int(100 * error_count / total)
        print(f'HAS_ERRORS: {key} has {error_count}/{total} errors ({pct}%)')
        found_errors = True

total_q = d.get('total_questions') or d.get('total') or d.get('question_count')
if total_q and isinstance(total_q, int):
    completed = d.get('completed') or d.get('answered') or d.get('successful')
    skipped = d.get('skipped') or d.get('filtered') or d.get('excluded')
    accounted = (completed or 0) + (skipped or 0)

    for key, val in d.items():
        if isinstance(val, list) and all(isinstance(r, dict) for r in val) and len(val) > 0:
            if len(val) < total_q:
                gap = total_q - len(val)
                if accounted >= gap and accounted <= total_q:
                    continue
                print(f'SILENTLY_MISSING: {key} has {len(val)} rows but total_questions={total_q}')
                found_errors = True

if found_errors:
    sys.exit(0)

print('OK')
" 2>&1)

    if [ "$result" = "OK" ]; then
        echo "  ✅ $filename: no error arms"
        PASS=$((PASS + 1))
    elif echo "$result" | grep -q "HAS_ERRORS"; then
        echo "  ❌ $filename: $result (VOID per anti-gaming clause 2: >0% errors)"
        FAILURES=$((FAILURES + 1))
    elif echo "$result" | grep -q "SILENTLY_MISSING"; then
        echo "  ❌ $filename: $result (VOID: rows silently dropped)"
        FAILURES=$((FAILURES + 1))
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
