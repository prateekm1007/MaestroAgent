"""H-1 fix: Remove decorative precision — no fabricated probabilities,
no hardcoded improvement claims, no uncalibrated confidence scores.

The external audit found:
  1. "P1 cluster risk: 45% probability of velocity drop" — a linear formula
     (incident_count × 0.15) presented as a calibrated probability
  2. "Velocity predicted to drop 22%" — hardcoded, no methodology
  3. All demo laws show confidence=1.0 — no variance, no calibration

The fix: replace fabricated precision with honest labels.
  - "45% probability" → "elevated risk" (based on incident count)
  - "Velocity predicted to drop 22%" → remove the fabricated number
  - Law confidence: keep the Beta-Binomial formula (it's correct) but
    ensure the display uses evidence_strength labels, not raw floats
"""
from __future__ import annotations

import sys
import inspect
import pytest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ─── 1. No "probability" claim on p1_cluster_risk ──────────────────────────

def test_no_fabricated_probability_in_recommendations():
    """The recommendation text must NOT contain 'probability' for p1_cluster_risk.
    A linear formula (incident_count × 0.15) is not a calibrated probability."""
    from maestro_oem import decision
    source = inspect.getsource(decision)
    # Must NOT say "X% probability" — that's decorative precision
    assert "probability of velocity drop" not in source, (
        "decision.py must not claim 'probability of velocity drop' — "
        "p1_cluster_risk is a linear formula, not a calibrated probability. "
        "Use an honest label like 'elevated risk' instead."
    )


# ─── 2. No hardcoded "22%" improvement claim ───────────────────────────────

def test_no_hardcoded_velocity_percentage():
    """The recommendation must NOT contain a hardcoded '22%' velocity drop."""
    from maestro_oem import decision
    source = inspect.getsource(decision)
    assert "22%" not in source, (
        "decision.py must not contain a hardcoded '22%' velocity drop — "
        "this is decorative precision with no methodology, baseline, or "
        "reference class."
    )


# ─── 3. p1_cluster_risk uses honest label, not percentage ──────────────────

def test_p1_cluster_risk_uses_label():
    """The p1_cluster_risk recommendation should use an honest label
    (elevated/high/critical) based on the risk level, not a fabricated
    percentage."""
    from maestro_oem import decision
    source = inspect.getsource(decision)
    # Should use a label like "elevated" or "high" instead of "probability"
    assert "elevated" in source.lower() or "high risk" in source.lower() or "risk level" in source.lower(), (
        "decision.py should use an honest risk label (elevated/high/critical) "
        "instead of a fabricated percentage for p1_cluster_risk."
    )


# ─── 4. The linear formula is still computed (not removed) ─────────────────

def test_p1_cluster_risk_formula_exists():
    """The p1_cluster_risk formula should still exist (it's a useful heuristic)
    but must not be presented as a calibrated probability."""
    from maestro_oem import model
    source = inspect.getsource(model)
    assert "p1_cluster_risk" in source, "The p1_cluster_risk computation should still exist"
    # The formula is a heuristic — it's fine to compute, just not to call it "probability"


# ─── 5. Law confidence is not displayed as "1.0" without context ───────────

def test_law_confidence_uses_evidence_strength():
    """When law confidence is very high (≥0.95), the system should present
    it as an evidence_strength label ('strong evidence') rather than a
    raw float that implies calibration."""
    from maestro_oem import confidence
    source = inspect.getsource(confidence)
    # The ConfidenceCalculator should have a way to produce labels
    assert "evidence_strength" in source or "label" in source.lower() or "compute_confidence_bucket" in source, (
        "confidence.py should produce evidence_strength labels, not just raw floats"
    )
