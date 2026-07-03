"""Loop 3 — Decision Intelligence: adversarial tests.

CEO directive (auditor recommendation, CEO-validated): "Loop 3 — Decision
Intelligence. The Decision object is the natural next first-class citizen
after Commitment and Meeting. Decisions have intent (what we're trying
to do), assumptions (what we believe), hypotheses (what we predict), and
outcomes (what happened). This exercises the claim_type epistemic types
(assumption, inference, prediction, outcome) more deeply than Loops 1
and 2 did."

A Decision is a first-class object with a lifecycle:
  PROPOSED → ASSUMPTIONS_RECORDED → HYPOTHESIS_STATED → DECIDED →
  OUTCOME_OBSERVED → LEARNING_RECORDED

Each transition is meaningful:
  - PROPOSED: a decision is on the table (intent stated)
  - ASSUMPTIONS_RECORDED: the assumptions underpinning the decision are
    recorded (each with claim_type="assumption")
  - HYPOTHESIS_STATED: a falsifiable prediction is made (claim_type="prediction")
  - DECIDED: the decision is made (the chosen course of action)
  - OUTCOME_OBSERVED: what actually happened (claim_type="outcome")
  - LEARNING_RECORDED: a Decision Learning Ledger entry is written

The Decision Learning Ledger entry is honest, signal-derived, references
the actual decision + assumptions + hypothesis + outcome, and acknowledges
when the hypothesis was wrong (no spin). It also references causality
uncertainty (richness lesson from Loop 2 audit).

Cross-decision patterns: "this is the third decision where the pricing
assumption was wrong" — connects decisions into a narrative.

These tests are adversarial: each assertion is non-vacuous (would fail
on the pre-Loop-3 codebase). Write first, watch fail, then build.
"""
from __future__ import annotations

import sys
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

# Ensure backend/ is on sys.path
_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest.fixture
def now():
    return datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)


# ─── 1. Decision dataclass + lifecycle ─────────────────────────────────────

def test_decision_has_lifecycle_states():
    """Decision must have a DecisionStatus enum with 6 lifecycle states.

    States: PROPOSED, ASSUMPTIONS_RECORDED, HYPOTHESIS_STATED, DECIDED,
    OUTCOME_OBSERVED, LEARNING_RECORDED
    """
    from maestro_oem.decision_v2 import DecisionStatus

    states = {s.name for s in DecisionStatus}
    expected = {
        "PROPOSED", "ASSUMPTIONS_RECORDED", "HYPOTHESIS_STATED",
        "DECIDED", "OUTCOME_OBSERVED", "LEARNING_RECORDED",
    }
    for s in expected:
        assert s in states, f"{s} must be a lifecycle state. Got: {states}"


def test_decision_dataclass_has_required_fields(now):
    """Decision must have: id, intent, entity, assumptions, hypothesis,
    decision_text, outcome, learning_entry, status, claim_types.
    """
    from maestro_oem.decision_v2 import Decision, DecisionStatus

    decision = Decision(
        intent="Prioritize SSO delivery to Globex",
        entity="Globex",
    )

    assert decision.intent == "Prioritize SSO delivery to Globex"
    assert decision.entity == "Globex"
    assert decision.status == DecisionStatus.PROPOSED  # Default state
    assert decision.assumptions == []  # Not yet recorded
    assert decision.hypothesis is None  # Not yet stated
    assert decision.decision_text is None  # Not yet decided
    assert decision.outcome is None  # Not yet observed
    assert decision.learning_entry is None  # Not yet recorded
    assert decision.decision_id  # Auto-generated


# ─── 2. Decision lifecycle transitions ─────────────────────────────────────

def test_decision_lifecycle_record_assumptions(now):
    """record_assumptions() transitions PROPOSED → ASSUMPTIONS_RECORDED.

    Each assumption is an Evidence object with claim_type="assumption".
    """
    from maestro_oem.decision_v2 import Decision, DecisionStatus
    from maestro_oem.decision_intelligence_loop import DecisionIntelligenceLoop

    decision = Decision(
        intent="Prioritize SSO delivery to Globex",
        entity="Globex",
    )
    loop = DecisionIntelligenceLoop()
    loop.record_assumptions(decision, assumptions=[
        {"text": "Globex will renew if SSO ships by Q4", "source": "sales"},
        {"text": "Engineering can deliver SSO by Q4", "source": "eng"},
    ])

    assert decision.status == DecisionStatus.ASSUMPTIONS_RECORDED
    assert len(decision.assumptions) == 2
    # Each assumption must have claim_type="assumption"
    for a in decision.assumptions:
        assert a.get("claim_type") == "assumption", \
            f"Assumptions must have claim_type='assumption'. Got: {a.get('claim_type')}"


def test_decision_lifecycle_state_hypothesis(now):
    """state_hypothesis() transitions ASSUMPTIONS_RECORDED → HYPOTHESIS_STATED.

    The hypothesis is a falsifiable prediction with claim_type="prediction".
    """
    from maestro_oem.decision_v2 import Decision, DecisionStatus
    from maestro_oem.decision_intelligence_loop import DecisionIntelligenceLoop

    decision = Decision(intent="Prioritize SSO delivery to Globex", entity="Globex")
    loop = DecisionIntelligenceLoop()
    loop.record_assumptions(decision, assumptions=[
        {"text": "Globex will renew if SSO ships by Q4", "source": "sales"},
    ])
    loop.state_hypothesis(decision, hypothesis="SSO will ship by Q4 and Globex will renew")

    assert decision.status == DecisionStatus.HYPOTHESIS_STATED
    assert decision.hypothesis is not None
    assert decision.hypothesis.get("claim_type") == "prediction", \
        f"Hypothesis must have claim_type='prediction'. Got: {decision.hypothesis.get('claim_type')}"


def test_decision_lifecycle_decide(now):
    """decide() transitions HYPOTHESIS_STATED → DECIDED."""
    from maestro_oem.decision_v2 import Decision, DecisionStatus
    from maestro_oem.decision_intelligence_loop import DecisionIntelligenceLoop

    decision = Decision(intent="Prioritize SSO delivery to Globex", entity="Globex")
    loop = DecisionIntelligenceLoop()
    loop.record_assumptions(decision, assumptions=[{"text": "Globex will renew", "source": "sales"}])
    loop.state_hypothesis(decision, hypothesis="SSO will ship by Q4")
    loop.decide(decision, decision_text="Prioritize SSO over Initech integration for Q4")

    assert decision.status == DecisionStatus.DECIDED
    assert decision.decision_text == "Prioritize SSO over Initech integration for Q4"


def test_decision_lifecycle_observe_outcome(now):
    """observe_outcome() transitions DECIDED → OUTCOME_OBSERVED.

    The outcome has claim_type="outcome".
    """
    from maestro_oem.decision_v2 import Decision, DecisionStatus
    from maestro_oem.decision_intelligence_loop import DecisionIntelligenceLoop

    decision = Decision(intent="Prioritize SSO delivery to Globex", entity="Globex")
    loop = DecisionIntelligenceLoop()
    loop.record_assumptions(decision, assumptions=[{"text": "Globex will renew", "source": "sales"}])
    loop.state_hypothesis(decision, hypothesis="SSO will ship by Q4 and Globex will renew")
    loop.decide(decision, decision_text="Prioritize SSO for Q4")
    loop.observe_outcome(decision, outcome="SSO shipped, Globex renewed")

    assert decision.status == DecisionStatus.OUTCOME_OBSERVED
    assert decision.outcome is not None
    assert decision.outcome.get("claim_type") == "outcome", \
        f"Outcome must have claim_type='outcome'. Got: {decision.outcome.get('claim_type')}"


def test_decision_lifecycle_record_learning(now):
    """record_learning() transitions OUTCOME_OBSERVED → LEARNING_RECORDED.

    The Decision Learning Ledger entry is honest, signal-derived, references
    the actual decision + assumptions + hypothesis + outcome, and
    acknowledges causality uncertainty (richness lesson from Loop 2 audit).
    """
    from maestro_oem.decision_v2 import Decision, DecisionStatus
    from maestro_oem.decision_intelligence_loop import DecisionIntelligenceLoop

    decision = Decision(intent="Prioritize SSO delivery to Globex", entity="Globex")
    loop = DecisionIntelligenceLoop()
    loop.record_assumptions(decision, assumptions=[
        {"text": "Globex will renew if SSO ships by Q4", "source": "sales"},
        {"text": "Engineering can deliver SSO by Q4", "source": "eng"},
    ])
    loop.state_hypothesis(decision, hypothesis="SSO will ship by Q4 and Globex will renew")
    loop.decide(decision, decision_text="Prioritize SSO for Q4")
    loop.observe_outcome(decision, outcome="SSO shipped, Globex renewed")
    entry = loop.record_learning(decision)

    assert decision.status == DecisionStatus.LEARNING_RECORDED
    assert entry, "Learning entry must be non-empty"
    assert len(entry) >= 50, \
        f"Learning entry must be rich (≥50 chars, richness lesson from Loop 2). Got: {entry!r} (len={len(entry)})"

    # REJECT placeholders (P6)
    FORBIDDEN = ["Learning recorded.", "Decision complete.", "TODO", "placeholder"]
    for phrase in FORBIDDEN:
        assert phrase.lower() not in entry.lower(), \
            f"Learning entry must not be a placeholder. Got: {entry!r}"

    # Must reference the actual decision + outcome (signal-derived)
    assert "globex" in entry.lower() or "sso" in entry.lower() or "decision" in entry.lower(), \
        f"Learning entry must reference the decision/entity. Got: {entry!r}"
    assert "renewed" in entry.lower() or "shipped" in entry.lower() or "outcome" in entry.lower(), \
        f"Learning entry must reference the outcome. Got: {entry!r}"

    # Richness lesson: must acknowledge causality uncertainty
    assert "does not know" in entry.lower() or "uncertain" in entry.lower() or "caus" in entry.lower() or "may have" in entry.lower(), \
        f"Learning entry must acknowledge causality uncertainty (richness lesson from Loop 2). Got: {entry!r}"


# ─── 3. Decision Learning Ledger honesty ───────────────────────────────────

def test_decision_learning_honest_when_hypothesis_wrong(now):
    """When the hypothesis was WRONG (outcome contradicts it), the learning
    entry must honestly say so — no spin. Maestro never invents precision.

    Scenario: hypothesis was "SSO will ship by Q4 and Globex will renew".
    Outcome: "SSO missed Q4, Globex churned". The entry must say the
    hypothesis was wrong, NOT spin it as a learning opportunity.
    """
    from maestro_oem.decision_v2 import Decision
    from maestro_oem.decision_intelligence_loop import DecisionIntelligenceLoop

    decision = Decision(intent="Prioritize SSO delivery to Globex", entity="Globex")
    loop = DecisionIntelligenceLoop()
    loop.record_assumptions(decision, assumptions=[
        {"text": "Globex will renew if SSO ships by Q4", "source": "sales"},
    ])
    loop.state_hypothesis(decision, hypothesis="SSO will ship by Q4 and Globex will renew")
    loop.decide(decision, decision_text="Prioritize SSO for Q4")
    loop.observe_outcome(decision, outcome="SSO missed Q4, Globex churned")
    entry = loop.record_learning(decision)

    # Must honestly say the hypothesis was wrong
    assert any(word in entry.lower() for word in ["wrong", "incorrect", "missed", "churned", "did not", "failed"]), \
        f"Learning entry must honestly say the hypothesis was wrong. Got: {entry!r}"
    # Must NOT spin it positively
    assert "renewed" not in entry.lower() or "churned" in entry.lower(), \
        f"Learning entry must NOT spin a wrong hypothesis as correct. Got: {entry!r}"


# ─── 4. Cross-decision pattern detection ───────────────────────────────────

def test_cross_decision_pattern_detects_recurring_wrong_assumption(now):
    """When the same assumption is wrong across 3 decisions, Maestro detects
    the pattern: 'this is the third decision where the X assumption was wrong.'

    This is the cross-decision narrative capability — Maestro connects
    decisions into a story about which assumptions keep failing.
    """
    from maestro_oem.decision_v2 import Decision
    from maestro_oem.decision_intelligence_loop import DecisionIntelligenceLoop
    from maestro_oem.cross_decision_patterns import CrossDecisionPatternDetector

    loop = DecisionIntelligenceLoop()

    # 3 decisions, all with the same wrong assumption
    decisions = []
    for i in range(3):
        d = Decision(intent=f"Decision #{i+1}", entity="Globex")
        loop.record_assumptions(d, assumptions=[
            {"text": "Globex will renew if we ship on time", "source": "sales"},
        ])
        loop.state_hypothesis(d, hypothesis="Shipping on time will lead to renewal")
        loop.decide(d, decision_text=f"Ship on time #{i+1}")
        loop.observe_outcome(d, outcome="Shipped on time, Globex did not renew")
        loop.record_learning(d)
        decisions.append(d)

    detector = CrossDecisionPatternDetector()
    patterns = detector.detect(decisions)

    assert len(patterns) >= 1, \
        f"Must detect the recurring wrong-assumption pattern. Got: {patterns}"
    # The pattern must reference the failed assumption
    renewal_pattern = next(
        (p for p in patterns if "renew" in p.assumption_text.lower() or "renew" in p.description.lower()),
        None,
    )
    assert renewal_pattern is not None, "Must detect the renewal assumption pattern"
    assert renewal_pattern.decision_count >= 3, \
        f"Pattern must count 3 decisions. Got: {renewal_pattern.decision_count}"
    assert "wrong" in renewal_pattern.description.lower() or "incorrect" in renewal_pattern.description.lower() or "failed" in renewal_pattern.description.lower(), \
        f"Pattern description must mention the assumption was wrong. Got: {renewal_pattern.description!r}"


def test_cross_decision_pattern_no_false_positive_for_single_decision(now):
    """An assumption in only 1 decision does NOT trigger a pattern.

    Non-vacuous counter-test: false positives erode trust.
    """
    from maestro_oem.decision_v2 import Decision
    from maestro_oem.decision_intelligence_loop import DecisionIntelligenceLoop
    from maestro_oem.cross_decision_patterns import CrossDecisionPatternDetector

    loop = DecisionIntelligenceLoop()
    d = Decision(intent="One-off decision", entity="Globex")
    loop.record_assumptions(d, assumptions=[{"text": "One-off assumption", "source": "test"}])
    loop.state_hypothesis(d, hypothesis="One-off hypothesis")
    loop.decide(d, decision_text="One-off")
    loop.observe_outcome(d, outcome="One-off outcome")
    loop.record_learning(d)

    detector = CrossDecisionPatternDetector()
    patterns = detector.detect([d], min_decisions=2)

    assert len(patterns) == 0, \
        f"An assumption in only 1 decision must NOT trigger a pattern. Got: {patterns}"


# ─── 5. Full lifecycle end-to-end ──────────────────────────────────────────

def test_decision_intelligence_full_lifecycle(now):
    """ONE test that exercises the whole Decision Intelligence loop:

    propose → record_assumptions → state_hypothesis → decide →
    observe_outcome → record_learning

    The learning entry must be signal-derived, honest, rich (≥50 chars),
    reference the actual decision + outcome, and acknowledge causality
    uncertainty.
    """
    from maestro_oem.decision_v2 import Decision, DecisionStatus
    from maestro_oem.decision_intelligence_loop import DecisionIntelligenceLoop

    decision = Decision(
        intent="Prioritize SSO delivery to Globex over Initech integration",
        entity="Globex",
    )
    loop = DecisionIntelligenceLoop()

    # Full lifecycle
    loop.record_assumptions(decision, assumptions=[
        {"text": "Globex will renew if SSO ships by Q4", "source": "sales"},
        {"text": "Engineering can deliver SSO by Q4", "source": "eng"},
        {"text": "Initech integration can slip to Q1", "source": "product"},
    ])
    assert decision.status == DecisionStatus.ASSUMPTIONS_RECORDED
    assert len(decision.assumptions) == 3

    loop.state_hypothesis(decision, hypothesis="SSO will ship by Q4 and Globex will renew")
    assert decision.status == DecisionStatus.HYPOTHESIS_STATED

    loop.decide(decision, decision_text="Prioritize SSO over Initech integration for Q4")
    assert decision.status == DecisionStatus.DECIDED

    loop.observe_outcome(decision, outcome="SSO shipped by Q4, Globex renewed, Initech integration slipped to Q1")
    assert decision.status == DecisionStatus.OUTCOME_OBSERVED

    entry = loop.record_learning(decision)
    assert decision.status == DecisionStatus.LEARNING_RECORDED
    assert entry
    assert len(entry) >= 50

    # Must reference what actually happened
    assert "globex" in entry.lower() or "sso" in entry.lower() or "decision" in entry.lower(), \
        f"Must reference the decision/entity. Got: {entry!r}"
    assert "renewed" in entry.lower() or "shipped" in entry.lower() or "outcome" in entry.lower(), \
        f"Must reference the outcome. Got: {entry!r}"

    # The decision must carry the full history
    assert len(decision.assumptions) == 3, "3 assumptions must be recorded"
    assert decision.hypothesis is not None, "Hypothesis must be stated"
    assert decision.decision_text is not None, "Decision text must be recorded"
    assert decision.outcome is not None, "Outcome must be observed"
    assert decision.learning_entry == entry, "Learning entry must be persisted on the decision"
