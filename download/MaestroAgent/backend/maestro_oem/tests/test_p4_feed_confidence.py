"""P4 fix: Remove hardcoded confidence from feed.py.

Uploaded audit finding (P2-02):
> feed.py has hardcoded confidence. Values 0.7, 0.8, 0.75 found in
> feed.py. Same fix as C5 (replace with evidence-based labels).

Same disease as C5 (explanations.py): fake precision. The constitution
says "Maestro never invents precision." A confidence of 0.7 on a
customer-drifting event implies calibration that doesn't exist.

The fix: rename 'confidence' → 'evidence_strength' throughout feed.py,
and replace hardcoded constants with evidence-based labels:
  - 1.0 (observed fact) → "observed"
  - 0.8 (strong pattern) → "well-supported"
  - 0.75 (concentration risk) → "well-supported"
  - 0.7 (drift signal) → "supported"
  - law.confidence (from model) → keep as numeric under evidence_strength
  - prediction confidence (from calibration) → keep as numeric under evidence_strength
"""
from __future__ import annotations

import sys
import re
import pytest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ─── 1. No hardcoded confidence constants ─────────────────────────────────

def test_no_hardcoded_confidence_constants_in_feed():
    """feed.py must NOT contain hardcoded confidence values like
    0.7, 0.8, 0.75 in confidence assignments."""
    feed_path = _BACKEND / "maestro_oem" / "feed.py"
    content = feed_path.read_text()

    # Find all lines with confidence=0.X (hardcoded constant, not from model/prediction)
    hardcoded = re.findall(r'confidence\s*=\s*0\.\d+', content)
    # Filter out law.confidence and prediction confidence (those are from model data)
    real_hardcoded = [h for h in hardcoded if "law." not in h and "pred" not in h]

    assert len(real_hardcoded) == 0, \
        f"feed.py must NOT contain hardcoded confidence constants. Found: {real_hardcoded}"


# ─── 2. Confidence field renamed to evidence_strength ─────────────────────

def test_confidence_renamed_to_evidence_strength_in_feed():
    """The 'confidence' field in FeedEvent must be renamed to
    'evidence_strength' — same fix as C5 for explanations.py."""
    feed_path = _BACKEND / "maestro_oem" / "feed.py"
    content = feed_path.read_text()

    assert "evidence_strength" in content, \
        "feed.py must use 'evidence_strength' instead of 'confidence'"

    # Check that no NEW confidence= assignments remain in code (comments OK)
    lines = content.split('\n')
    in_docstring = False
    code_confidence_lines = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if '"""' in stripped:
            in_docstring = not in_docstring
            continue
        if in_docstring or stripped.startswith('#'):
            continue
        # Check for confidence= in code (not law.confidence or pred confidence)
        if re.search(r'\bconfidence\s*=', line) and 'law.' not in line and 'pred' not in line and 'self.' not in line:
            code_confidence_lines.append(f"Line {i}: {stripped[:100]}")

    # self.confidence is the constructor parameter — that's OK if renamed
    # Check specifically for confidence=0.X patterns
    real_violations = [l for l in code_confidence_lines if '0.' in l]
    assert len(real_violations) == 0, \
        f"feed.py must NOT use hardcoded confidence=0.X in code. Found: {real_violations}"


# ─── 3. Hardcoded constants replaced with labels ──────────────────────────

def test_hardcoded_constants_replaced_with_labels_in_feed():
    """The hardcoded constants must be replaced with evidence-based labels."""
    feed_path = _BACKEND / "maestro_oem" / "feed.py"
    content = feed_path.read_text()

    # At least some labels must be present
    labels_found = []
    for label in ["observed", "well-supported", "supported", "limited evidence"]:
        if label in content:
            labels_found.append(label)

    assert len(labels_found) > 0, \
        f"feed.py must use evidence-based labels. Found: {labels_found}"
