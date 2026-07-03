"""C5 fix: Remove hardcoded confidence values from explanations.py.

Adversarial audit finding (ADVERSARIAL-AUDIT-24PHASE):
> C5: Hardcoded confidence values in explanations.py. confidence: 0.7,
> 0.4, 0.8, 0.5 — hardcoded heuristic values, not calibrated. These are
> user-facing confidence scores with no denominator, no sample size, no
> Brier score. Violates the "never invents precision" constitution principle.

The constitution says: "Maestro never invents precision. If a prediction
cannot be empirically calibrated and explained, it is expressed as evidence
and reasoning rather than a numerical probability."

The same fix was applied to /whisper in the CEO directive (commit 3bff220):
replaced fake percentages with evidence-based strings. Now the same fix
applies to /explain.

3 categories of confidence values in explanations.py:
  1. Hardcoded constants (0.4, 0.7, 0.8) — FAKE PRECISION → replace with
     evidence-based labels ("supported by limited evidence", "strong signal
     pattern", "well-supported by multiple data points")
  2. Computed ratios (min(1.0, X / N)) — ACCEPTABLE (real data ratios)
     But the field name "confidence" implies calibrated probability → rename
     to "evidence_strength" (a ratio, not a probability)
  3. From model (law.confidence) — ACCEPTABLE (from law validation count)
     But same rename: "evidence_strength" not "confidence"

The fix: rename "confidence" → "evidence_strength" throughout
explanations.py, and replace all hardcoded constants with evidence-based
labels. Computed ratios keep their numeric values but under the honest
field name.
"""
from __future__ import annotations

import sys
import re
import pytest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ─── 1. No hardcoded confidence constants ──────────────────────────────────

def test_no_hardcoded_confidence_constants():
    """explanations.py must NOT contain hardcoded confidence values like
    0.7, 0.4, 0.8 in confidence assignments.

    These are fake precision — uncalibrated probabilities presented to
    users as if they were meaningful. The constitution says "Maestro never
    invents precision."
    """
    explanations_path = _BACKEND / "maestro_oem" / "explanations.py"
    content = explanations_path.read_text()

    # Find all lines with "confidence": <number> (not min(), not law.)
    # Pattern: "confidence": 0.X (hardcoded constant)
    hardcoded = re.findall(r'"confidence":\s*0\.\d+', content)

    assert len(hardcoded) == 0, \
        f"explanations.py must NOT contain hardcoded confidence constants. " \
        f"Found {len(hardcoded)}: {hardcoded[:5]}"


def test_no_conditional_hardcoded_confidence():
    """explanations.py must NOT contain conditional hardcoded confidence
    values like '0.7 if X else 0.4'.

    These are fake precision — arbitrary thresholds with arbitrary values.
    """
    explanations_path = _BACKEND / "maestro_oem" / "explanations.py"
    content = explanations_path.read_text()

    # Pattern: 0.7 if ... else 0.4
    conditional = re.findall(r'0\.\d+\s+if\s+.+\s+else\s+0\.\d+', content)

    assert len(conditional) == 0, \
        f"explanations.py must NOT contain conditional hardcoded confidence. " \
        f"Found: {conditional[:5]}"


# ─── 2. Confidence field renamed to evidence_strength ──────────────────────

def test_confidence_renamed_to_evidence_strength():
    """The 'confidence' field in explanations must be renamed to
    'evidence_strength' — a ratio of evidence count, not a calibrated
    probability.

    The word 'confidence' implies statistical calibration (a Brier score,
    a sample size, a posterior). A ratio of (PRs opened / 20) is not a
    confidence — it's an evidence strength. Renaming it makes the epistemic
    status honest.
    """
    explanations_path = _BACKEND / "maestro_oem" / "explanations.py"
    content = explanations_path.read_text()

    # Check that "evidence_strength" appears (the new field name)
    assert "evidence_strength" in content, \
        "explanations.py must use 'evidence_strength' instead of 'confidence'"

    # Check that NO new "confidence" assignments remain (excluding comments/docstrings)
    # Look for "confidence": in actual code (not in comments)
    lines = content.split('\n')
    code_confidence_lines = []
    in_docstring = False
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if '"""' in stripped:
            in_docstring = not in_docstring
            continue
        if in_docstring:
            continue
        if stripped.startswith('#'):
            continue
        if '"confidence"' in line and not stripped.startswith('#'):
            code_confidence_lines.append(f"Line {i}: {stripped[:100]}")

    assert len(code_confidence_lines) == 0, \
        f"explanations.py must NOT use 'confidence' in code (only in comments). " \
        f"Found: {code_confidence_lines[:5]}"


# ─── 3. Hardcoded constants replaced with evidence-based labels ───────────

def test_hardcoded_constants_replaced_with_labels():
    """The hardcoded constants must be replaced with evidence-based labels,
    not just removed. The explanation must still convey HOW WELL-SUPPORTED
    the step is — just honestly, not with fake numbers.

    Labels:
      - "well-supported" (was 0.8) — multiple data points, strong pattern
      - "supported" (was 0.7) — some data points, moderate pattern
      - "limited evidence" (was 0.4) — few data points, weak pattern
      - Computed ratios keep their numeric value under evidence_strength
    """
    explanations_path = _BACKEND / "maestro_oem" / "explanations.py"
    content = explanations_path.read_text()

    # The evidence labels must appear in the code
    assert "well-supported" in content or "well_supported" in content, \
        "Must use 'well-supported' label (was hardcoded 0.8)"
    assert "limited evidence" in content or "limited_evidence" in content, \
        "Must use 'limited evidence' label (was hardcoded 0.4)"


# ─── 4. Computed ratios are acceptable (under the new name) ───────────────

def test_computed_ratios_preserved():
    """Computed ratios (min(1.0, X / N)) must be preserved — they're real
    data, not fake precision. But they must be under 'evidence_strength',
    not 'confidence'.
    """
    explanations_path = _BACKEND / "maestro_oem" / "explanations.py"
    content = explanations_path.read_text()

    # Check that min(1.0, ...) patterns still exist (under evidence_strength)
    ratio_patterns = re.findall(r'"evidence_strength":\s*min\(1\.0,', content)

    assert len(ratio_patterns) > 0, \
        f"Computed ratios must be preserved under 'evidence_strength'. " \
        f"Found {len(ratio_patterns)} patterns."


# ─── 5. Overall confidence renamed too ────────────────────────────────────

def test_overall_confidence_renamed():
    """The 'overall_confidence' field must also be renamed to
    'overall_evidence_strength' — same epistemic honesty principle.
    """
    explanations_path = _BACKEND / "maestro_oem" / "explanations.py"
    content = explanations_path.read_text()

    assert "overall_evidence_strength" in content, \
        "Must use 'overall_evidence_strength' instead of 'overall_confidence'"
