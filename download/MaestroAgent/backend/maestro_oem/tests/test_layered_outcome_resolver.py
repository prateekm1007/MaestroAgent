"""Tests for LayeredOutcomeResolver — the auditor's Priority Zero.

AUDITOR-DIRECTIVE:
> The resolver should handle:
> Customer escalated.          → OBSERVED (Layer 2)
> Customer may escalate.       → UNRESOLVED (Layer 5 — future)
> Customer did not escalate.   → NOT_OBSERVED (Layer 4 — negation)
> Customer considered escalating. → UNRESOLVED (Layer 3 — ambiguous)
> Sales believes escalation is likely. → UNRESOLVED (Layer 3 — ambiguous)
> Escalation was avoided.      → NOT_OBSERVED (Layer 4 — negation)
> Escalation was resolved.     → UNRESOLVED (no clear outcome)
> The escalation mentioned was from last quarter. → UNRESOLVED (temporal mismatch)

Maestro should prefer NOT LEARNING over learning falsely.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ["MAESTRO_LOCAL_DEV"] = "true"


def _make_text_signal(text: str, entity: str = "CustomerA"):
    """Build a signal with free-text content (for Layer 2-7 tests)."""
    from maestro_oem.signal import ExecutionSignal, SignalType, SignalProvider
    from uuid import uuid4
    return ExecutionSignal(
        type=SignalType.MESSAGE_SENT,
        actor="test@acme.com",
        artifact=f"text:{uuid4().hex[:8]}",
        metadata={"customer": entity, "subject": text, "body": text},
        provider=SignalProvider.SLACK,
        timestamp=datetime.now(timezone.utc),
    )


def _make_structured_signal(signal_type: str, entity: str, metadata: dict | None = None):
    """Build a structured signal (for Layer 1 tests)."""
    from maestro_oem.signal import ExecutionSignal, SignalType, SignalProvider
    from uuid import uuid4
    sig_type_map = {
        "customer.contract_churned": SignalType.CUSTOMER_CONTRACT_CHURNED,
        "customer.contract_renewed": SignalType.CUSTOMER_CONTRACT_RENEWED,
        "customer.commitment_broken": SignalType.CUSTOMER_COMMITMENT_BROKEN,
        "customer.commitment_kept": SignalType.CUSTOMER_COMMITMENT_KEPT,
    }
    return ExecutionSignal(
        type=sig_type_map.get(signal_type, SignalType.MESSAGE_SENT),
        actor="test@acme.com",
        artifact=f"structured:{entity}:{uuid4().hex[:8]}",
        metadata={"customer": entity, **(metadata or {})},
        provider=SignalProvider.CUSTOMER,
        timestamp=datetime.now(timezone.utc),
    )


# ─── LAYER 1: STRUCTURED EVENTS ────────────────────────────────────────────

def test_layer1_structured_churn_resolves_observed():
    """A customer.contract_churned signal → OBSERVED for 'churn' outcome."""
    from maestro_oem.layered_outcome_resolver import LayeredOutcomeResolver, ResolutionState, ResolutionLayer
    resolver = LayeredOutcomeResolver()
    signal = _make_structured_signal("customer.contract_churned", "CustomerA",
                                      metadata={"decision_outcome": "churned"})
    result = resolver.resolve(signal, "churn", "CustomerA")
    assert result.state == ResolutionState.OBSERVED
    assert result.layer == ResolutionLayer.STRUCTURED_EVENT
    assert result.to_store_outcome() == "supporting"


def test_layer1_structured_renewal_resolves_not_observed_for_churn():
    """A customer.contract_renewed signal → NOT_OBSERVED for 'churn' outcome (contradicting)."""
    from maestro_oem.layered_outcome_resolver import LayeredOutcomeResolver, ResolutionState, ResolutionLayer
    resolver = LayeredOutcomeResolver()
    signal = _make_structured_signal("customer.contract_renewed", "CustomerA",
                                      metadata={"decision_outcome": "renewed"})
    result = resolver.resolve(signal, "churn", "CustomerA")
    assert result.state == ResolutionState.NOT_OBSERVED
    assert result.layer == ResolutionLayer.STRUCTURED_EVENT
    assert result.to_store_outcome() == "contradicting"


# ─── LAYER 2: EXPLICIT ASSERTIONS ──────────────────────────────────────────

def test_layer2_explicit_escalation_resolves_observed():
    """'Customer escalated the issue' → OBSERVED."""
    from maestro_oem.layered_outcome_resolver import LayeredOutcomeResolver, ResolutionState
    resolver = LayeredOutcomeResolver()
    signal = _make_text_signal("Customer escalated the issue today")
    result = resolver.resolve(signal, "escalation", "CustomerA")
    assert result.state == ResolutionState.OBSERVED
    assert result.to_store_outcome() == "supporting"


# ─── LAYER 3: AMBIGUOUS LANGUAGE ───────────────────────────────────────────

def test_layer3_ambiguous_does_not_resolve():
    """'Escalation risk is increasing' → UNRESOLVED (does NOT establish outcome)."""
    from maestro_oem.layered_outcome_resolver import LayeredOutcomeResolver, ResolutionState, ResolutionLayer
    resolver = LayeredOutcomeResolver()
    signal = _make_text_signal("Escalation risk is increasing for this account")
    result = resolver.resolve(signal, "escalation", "CustomerA")
    assert result.state == ResolutionState.UNRESOLVED
    assert result.layer == ResolutionLayer.AMBIGUOUS
    assert result.ambiguity_present is True
    assert result.to_store_outcome() == "insufficient_data"


def test_layer3_believes_likely_does_not_resolve():
    """'Sales believes escalation is likely' → UNRESOLVED (ambiguous)."""
    from maestro_oem.layered_outcome_resolver import LayeredOutcomeResolver, ResolutionState
    resolver = LayeredOutcomeResolver()
    signal = _make_text_signal("Sales believes escalation is likely for CustomerA")
    result = resolver.resolve(signal, "escalation", "CustomerA")
    assert result.state == ResolutionState.UNRESOLVED
    assert result.ambiguity_present is True


# ─── LAYER 4: NEGATION ─────────────────────────────────────────────────────

def test_layer4_negation_resolves_not_observed():
    """'Customer did not escalate' → NOT_OBSERVED (contradicting)."""
    from maestro_oem.layered_outcome_resolver import LayeredOutcomeResolver, ResolutionState, ResolutionLayer
    resolver = LayeredOutcomeResolver()
    signal = _make_text_signal("Customer did not escalate the issue")
    result = resolver.resolve(signal, "escalation", "CustomerA")
    assert result.state == ResolutionState.NOT_OBSERVED
    assert result.layer == ResolutionLayer.NEGATION
    assert result.to_store_outcome() == "contradicting"


def test_layer4_avoided_resolves_not_observed():
    """'Escalation was avoided' → NOT_OBSERVED (contradicting)."""
    from maestro_oem.layered_outcome_resolver import LayeredOutcomeResolver, ResolutionState
    resolver = LayeredOutcomeResolver()
    signal = _make_text_signal("Escalation was avoided through quick intervention")
    result = resolver.resolve(signal, "escalation", "CustomerA")
    assert result.state == ResolutionState.NOT_OBSERVED
    assert result.to_store_outcome() == "contradicting"


# ─── LAYER 5: FUTURE/HYPOTHETICAL ──────────────────────────────────────────

def test_layer5_future_does_not_resolve():
    """'Customer may escalate' → UNRESOLVED (future/hypothetical)."""
    from maestro_oem.layered_outcome_resolver import LayeredOutcomeResolver, ResolutionState, ResolutionLayer
    resolver = LayeredOutcomeResolver()
    signal = _make_text_signal("Customer may escalate next week")
    result = resolver.resolve(signal, "escalation", "CustomerA")
    assert result.state == ResolutionState.UNRESOLVED
    assert result.layer == ResolutionLayer.FUTURE
    assert result.to_store_outcome() == "insufficient_data"


# ─── LAYER 6: DISPUTED ─────────────────────────────────────────────────────

def test_layer6_disputed_does_not_resolve():
    """'Sales says escalation; CS disagrees' → DISPUTED (not resolved)."""
    from maestro_oem.layered_outcome_resolver import LayeredOutcomeResolver, ResolutionState, ResolutionLayer
    resolver = LayeredOutcomeResolver()
    signal = _make_text_signal("Sales says this was an escalation but CS disagrees")
    result = resolver.resolve(signal, "escalation", "CustomerA")
    assert result.state == ResolutionState.DISPUTED
    assert result.layer == ResolutionLayer.DISPUTED
    assert result.ambiguity_present is True
    assert result.to_store_outcome() == "insufficient_data"


# ─── LAYER 7: INDIRECT INFERENCE ───────────────────────────────────────────

def test_layer7_indirect_does_not_resolve():
    """'CEO joined the call' → UNRESOLVED (indirect inference, not itself outcome)."""
    from maestro_oem.layered_outcome_resolver import LayeredOutcomeResolver, ResolutionState, ResolutionLayer
    resolver = LayeredOutcomeResolver()
    signal = _make_text_signal("CEO joined the call unexpectedly")
    result = resolver.resolve(signal, "escalation", "CustomerA")
    assert result.state == ResolutionState.UNRESOLVED
    assert result.layer == ResolutionLayer.INDIRECT
    assert result.to_store_outcome() == "insufficient_data"


# ─── COMPREHENSIVE: Maestro prefers NOT LEARNING over learning falsely ─────

def test_maestro_prefers_not_learning_over_false_learning():
    """The auditor's core demand: prefer NOT LEARNING over learning falsely.

    If 10 ambiguous signals arrive and 0 clear signals, Maestro should
    resolve 0 outcomes — NOT learn from the ambiguous evidence.
    """
    from maestro_oem.layered_outcome_resolver import LayeredOutcomeResolver, ResolutionState
    resolver = LayeredOutcomeResolver()

    ambiguous_signals = [
        _make_text_signal("Customer may escalate"),
        _make_text_signal("Escalation risk is increasing"),
        _make_text_signal("Sales believes escalation is likely"),
        _make_text_signal("Customer is considering escalation"),
        _make_text_signal("CEO joined the call"),
    ]

    observed_count = 0
    unresolved_count = 0
    for signal in ambiguous_signals:
        result = resolver.resolve(signal, "escalation", "CustomerA")
        if result.state == ResolutionState.OBSERVED:
            observed_count += 1
        else:
            unresolved_count += 1

    assert observed_count == 0, \
        "Maestro must NOT learn from ambiguous signals — 0 observed, not 5"
    assert unresolved_count == 5, \
        "All 5 ambiguous signals should be UNRESOLVED"
