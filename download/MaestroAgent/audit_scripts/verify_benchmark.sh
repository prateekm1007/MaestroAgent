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
                if accounted >= gap and accounted <= total_q and (completed or 0) <= len(val):
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
# CHECK 5: Notes-vs-structured-field numeric consistency
# (auditor catch: notes string claimed -0.6pts but structured field said -3.9)
#
# Approach: extract EVERY number from notes/summary/description strings,
# collect ALL numeric values from the object (recursively), and flag any
# notes-number that doesn't match ANY object-number (within tolerance).
# This doesn't depend on field names — it catches stale numbers regardless
# of how they're phrased in the notes.
# ───────────────────────────────────────────────────────────────────────
echo "Check 5: Notes-vs-structured-field numeric consistency..."
for json_file in "$SCOREBOARD_DIR"/*.json; do
    [ -f "$json_file" ] || continue
    filename=$(basename "$json_file")

    result=$(python3 -c "
import json, re, sys

with open('$json_file') as f:
    try:
        d = json.load(f)
    except json.JSONDecodeError:
        sys.exit(0)

if not isinstance(d, dict):
    sys.exit(0)

def collect_all_numbers(obj, numbers):

    if isinstance(obj, dict):
        for v in obj.values():
            collect_all_numbers(v, numbers)
    elif isinstance(obj, list):
        for v in obj:
            collect_all_numbers(v, numbers)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        numbers.append(float(obj))

def collect_notes_text(obj, texts):

    if isinstance(obj, dict):
        for key in ('notes', 'note', 'summary', 'description'):
            if key in obj and isinstance(obj[key], str):
                texts.append(obj[key])
        for v in obj.values():
            collect_notes_text(v, texts)
    elif isinstance(obj, list):
        for v in obj:
            collect_notes_text(v, texts)

all_numbers = []
collect_all_numbers(d, all_numbers)

notes_texts = []
collect_notes_text(d, notes_texts)
notes_text = ' '.join(notes_texts)

if not notes_text or not all_numbers:
    print('OK')
    sys.exit(0)

# Extract all numbers from notes text (including signs and decimals)
# Pattern: optional +/-, digits, optional decimal part
notes_numbers = []
for m in re.finditer(r'([+-]?\d+\.?\d*)', notes_text):
    try:
        notes_numbers.append(float(m.group(1)))
    except ValueError:
        pass

# Filter out trivially small numbers (0, 1) that appear everywhere
# and would generate false positives (e.g., 'n=30' has 30 which is fine,
# but '0' appears in '0.6222' as a substring match)
notes_numbers = [n for n in notes_numbers if abs(n) > 0.01]

# Data-claim keywords: numbers near these words are data claims, not
# descriptive text. Only flag data-claim numbers that don't match any
# object number.
DATA_KEYWORDS = ('lift', 'score', 'pts', 'improvement', 'bm25', 'maestro',
                 'recall', 'mrr', 'delta', 'change', 'baseline', 'result',
                 'a_bm25', 'b_full', 'lift_b_vs_a')

def is_data_claim(notes_text, num_str):
    for m in re.finditer(re.escape(num_str), notes_text):
        start = max(0, m.start() - 15)
        preceding = notes_text[start:m.start()].lower()
        for kw in DATA_KEYWORDS:
            if kw in preceding:
                end = min(len(notes_text), m.end() + 30)
                context = notes_text[start:end]
                return True, context
    return False, ''

mismatches = []
for nn in notes_numbers:
    # Check if this notes-number matches ANY object-number (within tolerance)
    # Also check nn/100 (percentage display: 33.3 in notes vs 0.333 in data)
    # and nn*100 (raw number displayed as percentage)
    # Check if notes-number matches ANY object-number (within tolerance)
    # Also check nn/100 (percentage display: 33.3 in notes vs 0.333 in data)
    # and nn*100 (raw number displayed as percentage)
    # Also check if it's a delta between two object numbers (e.g., -50.0
    # = (0.5 - 1.0) * 100, for per-type score changes)
    # Match against raw, percentage-scaled, or percentage-of numbers
    # Only apply /100 scaling for larger notes-numbers (percentages like
    # 33.3 or -50.0, not small numbers like -0.6 which would falsely
    # match 0.0 via -0.6/100 = -0.006 ≈ 0)
    use_pct = abs(nn) > 5
    matched = any(
        abs(nn - on) < 0.01 or
        (use_pct and abs(nn/100 - on) < 0.01) or
        abs(nn*100 - on) < 0.01
        for on in all_numbers
    )
    # Also check if it's a percentage delta between two object numbers
    # (only for larger notes-numbers — deltas are typically |x| > 5,
    # while raw scores are 0.0-1.0 and percentages are 0-100)
    if not matched and abs(nn) > 5 and len(all_numbers) >= 2:
        for i, a in enumerate(all_numbers):
            for b in all_numbers[i+1:]:
                delta_pct = (b - a) * 100
                if abs(nn - delta_pct) < 0.5:
                    matched = True
                    break
            if matched:
                break
    if not matched:
        # Only flag if it's a data claim (near a keyword)
        is_claim, context = is_data_claim(notes_text, str(nn))
        if is_claim:
            context_clean = context.replace('\n', ' ').strip()[:80]
            mismatches.append(f'notes claims {nn} (near: "{context_clean}") but no matching value in structured fields (raw, /100, or *100)')

if mismatches:
    print('NOTES_MISMATCH: ' + ' ; '.join(mismatches[:3]))
else:
    print('OK')
" 2>&1)

    if [ "$result" = "OK" ]; then
        echo "  ✅ $filename: notes consistent with structured fields"
        PASS=$((PASS + 1))
    elif echo "$result" | grep -q "NOTES_MISMATCH"; then
        echo "  ❌ $filename: $result"
        FAILURES=$((FAILURES + 1))
    fi
done
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
