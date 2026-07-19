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

# P30 fix (auditor S3): generalize past the literal field name 'llm_active'.
# Check ANY boolean-shaped field that appears at both top level and per-row.
# If the top-level value disagrees with the per-row values, it's a
# metadata-consistency violation regardless of what the field is called.

# Find row-level data
rows = None
for key in ('maestro_results', 'results', 'results_B', 'rows', 'queries'):
    if key in d and isinstance(d[key], list) and len(d[key]) > 0:
        rows = d[key]
        break

if rows is None:
    sys.exit(0)  # no rows to compare, skip

# Find all boolean-shaped fields at top level that look like claims
# (not counts or statistics). A boolean claim is: True, False, 0, or 1.
# Exclude values > 1 (those are counts like llm_active_count: 47).
top_level_keys = {k for k, v in d.items() if isinstance(v, bool) or v in (0, 1, 'true', 'false', 'True', 'False')}

# Also check common boolean field name patterns
boolean_field_patterns = ['llm_active', 'llm_used', 'llm_powered', 'active',
                          'verified', 'configured', 'is_active', 'is_verified',
                          'used_llm', 'model_active', 'has_llm', 'llm_enabled']

# Add any top-level key that looks boolean
for k in d:
    v = d[k]
    if isinstance(v, bool) or v in (0, 1, 'true', 'false', 'True', 'False'):
        top_level_keys.add(k)

# Also add pattern-matched keys (but exclude counts/statistics)
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
    # Check if rows have this field
    row_values = set()
    for r in rows:
        if isinstance(r, dict) and field in r:
            row_values.add(r[field])

    if not row_values:
        # Loophole 1 fix (auditor): if the top-level claims a boolean
        # (e.g. llm_active: True) but NO rows have the field at all,
        # that's an unasserted claim. Only flag boolean-shaped values
        # (True/False), NOT counts or floats (those are summary stats).
        if isinstance(top_val, bool) and top_val:
            mismatches.append(f'{field}: top={top_val} but field absent in all rows (unasserted claim)')
        elif isinstance(top_val, (int, float)) and top_val == 1:
            mismatches.append(f'{field}: top={top_val} but field absent in all rows (unasserted claim)')
        continue

    # Compare top vs row values
    # Normalize to boolean for comparison
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

    # If all rows agree on a single boolean value, and it differs from top
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

# Check for error/exception fields in result rows
# F1 fix (auditor): recursively walk row dicts for error-shaped keys/values.
# F1a fix: remove depth cap — use a visited set instead (depth > 5 missed
#   errors nested deeper than 5 levels). A visited set prevents infinite
#   recursion without imposing an arbitrary depth limit.
# F1b fix: iterate EVERY top-level list of dicts as a potential arm, not
#   just a whitelist of 8 known key names. A results list named 'trials'
#   was missed because it wasn't in the whitelist.
# F1c fix: if total_questions is present and len(rows) < total_questions,
#   flag as 'silently missing rows' — a benchmark that drops rows and
#   reports the survivors is VOID per Anti-Gaming Clause 2.

ERROR_KEYS = {'error', 'exception', 'traceback', 'exception_class',
              'exception_type', 'error_type', 'error_message'}
ERROR_VALUES = {'RuntimeError', 'Exception', 'Traceback', 'Error',
                'TypeError', 'ValueError', 'KeyError', 'AttributeError'}

def has_error_recursive(obj, visited=None):
    '''Recursively walk a dict/list looking for error-shaped keys/values.
    Uses a visited set (by id) to prevent infinite recursion on circular
    references — no arbitrary depth cap.'''
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
            if isinstance(v, str) and any(e in v for e in ERROR_VALUES):
                return True
            if has_error_recursive(v, visited):
                return True
    elif isinstance(obj, list):
        for item in obj:
            if has_error_recursive(item, visited):
                return True
    elif isinstance(obj, str):
        if any(e in obj for e in ERROR_VALUES):
            return True
    return False

# F1b fix: iterate EVERY top-level key whose value is a list of dicts.
# Previously only checked 8 hardcoded arm_key names. Any list of dicts
# could be a results arm.
found_errors = False
for key, val in d.items():
    if not isinstance(val, list) or len(val) == 0:
        continue
    # Only check lists of dicts (result rows)
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

# F1c fix: check for silently missing rows
total_q = d.get('total_questions') or d.get('total') or d.get('question_count')
if total_q and isinstance(total_q, int):
    for key, val in d.items():
        if isinstance(val, list) and all(isinstance(r, dict) for r in val) and len(val) > 0:
            if len(val) < total_q:
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
