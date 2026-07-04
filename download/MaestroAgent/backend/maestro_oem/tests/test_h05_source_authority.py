"""H-05 fix: Source authority weighting — CTO vs intern should not be equal.

The prior adversarial audit found (H-05):
> All signals of the same type carry equal evidentiary weight regardless
> of source authority. A CEO's Slack message carries the same evidentiary
> weight as a junior employee's message of the same signal type.

The fix has 3 parts:
  1. An `authority_weight` field on ExecutionSignal (0.0-1.0, default 0.5)
  2. A SourceAuthorityModel that maps actor emails → authority weights
     based on role/seniority (configurable, derived from org chart data)
  3. ConfidenceCalculator + EvidenceBuilder use authority_weight to
     modulate evidence strength

Design decisions:
  - authority_weight is PER-SIGNAL, not per-actor. The same person can
    have different authority in different contexts (a senior engineer's
    commit vs their casual Slack joke).
  - The default authority_weight is 0.5 (neutral). Unknown actors get
    neutral weight — never zero (would silence new hires).
  - The SourceAuthorityModel is opt-in. If no model is configured, all
    signals carry default weight (backward-compatible).
  - Authority is NOT a "trust score." A junior person reporting a bug
    is still reporting a real bug. Authority modulates how much the
    signal influences LAW/PATTERN promotion, not whether it's ingested.

Adversarial tests (write first, watch fail, then fix):

  1. test_signal_has_authority_weight_field
     ExecutionSignal must have an `authority_weight` field (default 0.5).

  2. test_source_authority_model_exists
     SourceAuthorityModel must exist and be importable.

  3. test_authority_model_assigns_weight_by_role
     Given an actor with role "CTO", the model assigns weight ≥ 0.8.
     Given an actor with role "intern", the model assigns weight ≤ 0.3.

  4. test_authority_model_unknown_actor_gets_neutral
     An actor not in the org chart gets weight 0.5 (neutral, not zero).

  5. test_confidence_calculator_uses_authority_weight
     ConfidenceCalculator.compute_lo_confidence must accept an
     `authority_weights` parameter and modulate confidence accordingly.
     Same evidence_count + contradiction_count, but authority_weights=[0.9]
     should produce HIGHER confidence than authority_weights=[0.2].

  6. test_evidence_builder_records_authority_weight
     EvidenceBuilder must record the authority_weight of contributing
     signals in the evidence spine's observed_facts.

  7. test_wiring_p11_authority_in_confidence_py
     P11: authority_weight must be referenced in confidence.py.

  8. test_wiring_p11_authority_in_evidence_py
     P11: authority_weight must be referenced in evidence.py.

  9. test_authority_model_never_silences_signals
     A low-authority signal (weight 0.1) must still be ingested and
     must still appear in evidence. Authority modulates confidence,
     not visibility. (P6: fail-closed, never silent.)

  10. test_authority_model_backward_compat
      Existing code that constructs ExecutionSignal without authority_weight
      must still work (default 0.5).

P2: Untested code is unverified code.
P6: Fail-closed — authority never silences a signal.
P11: Wiring proved by grep + execution.
P13: Authority is DERIVED from org chart data, not caller-supplied per-signal.
"""
from __future__ import annotations

import sys
import inspect
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ═══ H-05: Source authority weighting ═══════════════════════════════════════

# ─── 1. Signal has authority_weight field ──────────────────────────────────

def test_signal_has_authority_weight_field():
    """ExecutionSignal must have an `authority_weight` field (default 0.5)."""
    from maestro_oem.signal import ExecutionSignal, SignalType, SignalProvider

    sig = ExecutionSignal(
        type=SignalType.CUSTOMER_COMMITMENT_MADE,
        actor="jane@example.com",
        artifact="crm:1",
        provider=SignalProvider.CUSTOMER,
    )
    assert hasattr(sig, "authority_weight"), (
        "ExecutionSignal must have 'authority_weight' field (H-05)"
    )
    assert sig.authority_weight == 0.5, (
        f"Default authority_weight must be 0.5 (neutral). Got: {sig.authority_weight}"
    )


# ─── 2. SourceAuthorityModel exists ────────────────────────────────────────

def test_source_authority_model_exists():
    """SourceAuthorityModel must exist and be importable."""
    from maestro_oem.source_authority import SourceAuthorityModel
    assert SourceAuthorityModel is not None


# ─── 3. Authority model assigns weight by role ─────────────────────────────

def test_authority_model_assigns_weight_by_role():
    """CTO gets weight ≥ 0.8; intern gets weight ≤ 0.3."""
    from maestro_oem.source_authority import SourceAuthorityModel

    model = SourceAuthorityModel()
    # Register actors with roles
    model.register(actor="cto@example.com", role="CTO", level="executive")
    model.register(actor="intern@example.com", role="intern", level="junior")

    cto_weight = model.get_authority_weight("cto@example.com")
    intern_weight = model.get_authority_weight("intern@example.com")

    assert cto_weight >= 0.8, (
        f"CTO authority_weight must be ≥ 0.8. Got: {cto_weight}"
    )
    assert intern_weight <= 0.3, (
        f"Intern authority_weight must be ≤ 0.3. Got: {intern_weight}"
    )


# ─── 4. Unknown actor gets neutral weight ──────────────────────────────────

def test_authority_model_unknown_actor_gets_neutral():
    """An actor not in the org chart gets weight 0.5 (neutral, not zero).
    This is P6 fail-closed: never silence a signal just because we don't
    know the actor's role."""
    from maestro_oem.source_authority import SourceAuthorityModel

    model = SourceAuthorityModel()
    weight = model.get_authority_weight("unknown@example.com")
    assert weight == 0.5, (
        f"Unknown actor must get neutral weight 0.5 (not zero). Got: {weight}"
    )


# ─── 5. ConfidenceCalculator uses authority_weight ─────────────────────────

def test_confidence_calculator_uses_authority_weight():
    """ConfidenceCalculator.compute_lo_confidence must accept an
    `authority_weights` parameter and modulate confidence accordingly.
    Same evidence_count + contradiction_count, but authority_weights=[0.9]
    should produce HIGHER confidence than authority_weights=[0.2]."""
    from maestro_oem.confidence import ConfidenceCalculator
    import inspect as _inspect

    sig = _inspect.signature(ConfidenceCalculator.compute_lo_confidence_explained)
    params = set(sig.parameters.keys())
    assert "authority_weights" in params, (
        f"compute_lo_confidence_explained must accept 'authority_weights' parameter. "
        f"Params: {params}"
    )

    now = datetime.now(timezone.utc)
    # High-authority evidence
    high = ConfidenceCalculator.compute_lo_confidence(
        evidence_count=5,
        contradiction_count=0,
        providers={"slack"},
        first_seen=now - timedelta(days=10),
        last_seen=now,
        authority_weights=[0.9, 0.9, 0.9, 0.9, 0.9],
    )
    # Low-authority evidence (same count, same providers, same recency)
    low = ConfidenceCalculator.compute_lo_confidence(
        evidence_count=5,
        contradiction_count=0,
        providers={"slack"},
        first_seen=now - timedelta(days=10),
        last_seen=now,
        authority_weights=[0.2, 0.2, 0.2, 0.2, 0.2],
    )
    assert high > low, (
        f"High-authority evidence must produce higher confidence than low-authority. "
        f"high={high}, low={low}"
    )


# ─── 6. EvidenceBuilder records authority_weight ───────────────────────────

def test_evidence_builder_records_authority_weight():
    """EvidenceBuilder must record the authority_weight of contributing
    signals in the evidence spine's observed_facts."""
    from maestro_oem.evidence import EvidenceBuilder
    from maestro_oem.signal import ExecutionSignal, SignalType, SignalProvider

    sig = ExecutionSignal(
        type=SignalType.CUSTOMER_COMMITMENT_MADE,
        actor="cto@example.com",
        artifact="crm:1",
        metadata={"customer": "TestCorp", "commitment": "Deliver SSO by Q4"},
        provider=SignalProvider.CUSTOMER,
        authority_weight=0.9,
    )
    builder = EvidenceBuilder([sig])
    evidence = builder.build_for_whisper(
        whisper_type="commitment_exists",
        entity="TestCorp",
        topic="",
        raw_evidence={"artifact": "crm:1", "timestamp": sig.timestamp.isoformat()},
        context="meeting",
    )
    facts = evidence.observed_facts
    assert any(f.get("authority_weight") is not None for f in facts), (
        f"observed_facts must include authority_weight. Facts: {facts}"
    )


# ─── 7. P11: authority_weight referenced in confidence.py ─────────────────

def test_wiring_p11_authority_in_confidence_py():
    """P11: authority_weight must be referenced in confidence.py."""
    from maestro_oem import confidence
    source = inspect.getsource(confidence)
    assert "authority_weight" in source, (
        "confidence.py must reference authority_weight (P11 — wired into production)"
    )


# ─── 8. P11: authority_weight referenced in evidence.py ───────────────────

def test_wiring_p11_authority_in_evidence_py():
    """P11: authority_weight must be referenced in evidence.py."""
    from maestro_oem import evidence
    source = inspect.getsource(evidence)
    assert "authority_weight" in source, (
        "evidence.py must reference authority_weight (P11 — wired into production)"
    )


# ─── 9. Authority never silences signals (P6) ──────────────────────────────

def test_authority_model_never_silences_signals():
    """A low-authority signal (weight 0.1) must still be ingested and
    must still appear in evidence. Authority modulates confidence,
    not visibility. (P6: fail-closed, never silent.)"""
    from maestro_oem.evidence import EvidenceBuilder
    from maestro_oem.signal import ExecutionSignal, SignalType, SignalProvider

    sig = ExecutionSignal(
        type=SignalType.CUSTOMER_OBJECTION,
        actor="intern@example.com",
        artifact="slack:msg-1",
        metadata={"customer": "TestCorp", "objection_type": "pricing"},
        provider=SignalProvider.SLACK,
        authority_weight=0.1,  # Very low authority
    )
    builder = EvidenceBuilder([sig])
    evidence = builder.build_for_whisper(
        whisper_type="objection_exists",
        entity="TestCorp",
        topic="pricing",
        raw_evidence={"artifact": "slack:msg-1", "timestamp": sig.timestamp.isoformat()},
        context="meeting",
    )
    # The signal MUST still appear in observed_facts — low authority does
    # NOT mean the signal is dropped. It means its contribution to
    # confidence is reduced.
    assert len(evidence.observed_facts) > 0, (
        "Low-authority signal must still appear in evidence (P6: never silent)"
    )


# ─── 10. Backward compat ───────────────────────────────────────────────────

def test_authority_model_backward_compat():
    """Existing code that constructs ExecutionSignal without authority_weight
    must still work (default 0.5)."""
    from maestro_oem.signal import ExecutionSignal, SignalType, SignalProvider

    # No authority_weight argument — must default to 0.5
    sig = ExecutionSignal(
        type=SignalType.CUSTOMER_COMMITMENT_MADE,
        actor="jane@example.com",
        artifact="crm:1",
        provider=SignalProvider.CUSTOMER,
    )
    assert sig.authority_weight == 0.5, (
        f"Backward compat: default authority_weight must be 0.5. Got: {sig.authority_weight}"
    )


# ─── 11. Authority model loads from config (P13: derived from evidence) ────

def test_authority_model_loads_from_config():
    """The SourceAuthorityModel can be populated from a config dict
    (org chart data). This is P13: authority is DERIVED from org chart
    data, not caller-supplied per-signal."""
    from maestro_oem.source_authority import SourceAuthorityModel

    org_chart = [
        {"email": "cto@example.com", "role": "CTO", "level": "executive"},
        {"email": "vp-eng@example.com", "role": "VP Engineering", "level": "executive"},
        {"email": "senior-eng@example.com", "role": "Senior Engineer", "level": "senior"},
        {"email": "eng@example.com", "role": "Engineer", "level": "mid"},
        {"email": "junior-eng@example.com", "role": "Junior Engineer", "level": "junior"},
        {"email": "intern@example.com", "role": "Intern", "level": "junior"},
    ]
    model = SourceAuthorityModel()
    model.load_from_org_chart(org_chart)

    # Executive > senior > mid > junior
    assert model.get_authority_weight("cto@example.com") > model.get_authority_weight("senior-eng@example.com")
    assert model.get_authority_weight("senior-eng@example.com") > model.get_authority_weight("eng@example.com")
    assert model.get_authority_weight("eng@example.com") > model.get_authority_weight("intern@example.com")
