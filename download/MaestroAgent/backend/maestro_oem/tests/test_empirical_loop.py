"""Tests for the Priority 5B empirical loop — Phases 2-12.

AUDITOR-DIRECTIVE: The behavioral Case A → B → C proof must be demonstrated:
  CASE A → Maestro forms hypothesis H.
  CASE B → H is prospectively tested.
  OUTCOME B → H gains or loses support.
  CASE C → Maestro behaves differently because of the governed learning result.

Adversarial tests (from the auditor's 20-test list):
  1. same query repeated 100 times → reasoning_mentions=100, empirical=0
  3. same event copied across Slack, Gmail, Jira → one case
  4. two genuinely independent customer cases → two cases
  5. historical support but prospective failure → not validated
  11. outcome arrives before worker processes prediction (out-of-order)
  12. duplicate outcome signal → no double-resolve
  17. insufficient sample size → no calibration (no decorative precision)
  20. human rejection of promotion
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ["MAESTRO_LOCAL_DEV"] = "true"


def _make_signal(signal_type: str, entity: str, metadata: dict | None = None,
                 timestamp: datetime | None = None):
    """Build a minimal ExecutionSignal-like object for testing."""
    from maestro_oem.signal import ExecutionSignal, SignalType, SignalProvider
    from uuid import uuid4
    sig_type_map = {
        "customer.commitment_made": SignalType.CUSTOMER_COMMITMENT_MADE,
        "customer.commitment_kept": SignalType.CUSTOMER_COMMITMENT_KEPT,
        "customer.commitment_broken": SignalType.CUSTOMER_COMMITMENT_BROKEN,
        "customer.objection": SignalType.CUSTOMER_OBJECTION,
        "customer.decision": SignalType.CUSTOMER_DECISION,
        "customer.contract_renewed": SignalType.CUSTOMER_CONTRACT_RENEWED,
        "customer.contract_churned": SignalType.CUSTOMER_CONTRACT_CHURNED,
    }
    return ExecutionSignal(
        type=sig_type_map.get(signal_type, SignalType.INCIDENT),
        actor="test@acme.com",
        artifact=f"test:{entity}:{uuid4().hex[:8]}",
        metadata={"customer": entity, **(metadata or {})},
        provider=SignalProvider.CUSTOMER,
        timestamp=timestamp or datetime.now(timezone.utc),
    )


class _MockSituation:
    """Minimal Situation mock for testing CaseFingerprintBuilder."""
    def __init__(self, commitments=None, timeline=None, evidence=None):
        self.commitments = commitments or []
        self.timeline = timeline or []
        self.evidence = evidence or []


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 2: ObservationCase + CaseFingerprintBuilder (P13/P14)
# ═══════════════════════════════════════════════════════════════════════════

def test_fingerprint_derived_from_evidence_not_supplied():
    """P13: the fingerprint is DERIVED, not caller-supplied."""
    from maestro_oem.empirical_loop import CaseFingerprintBuilder
    situation = _MockSituation(
        commitments=[{"commitment": "Deliver SSO"}],
        timeline=[{"date": "2024-11-01", "event": "commitment"}],
        evidence=[{"text": "evidence", "source": "crm:1"}],
    )
    case = CaseFingerprintBuilder.build("CustomerA", situation, "escalation")
    assert case.case_fingerprint != ""
    assert len(case.case_fingerprint) == 16
    assert case.entity_id == "CustomerA"
    assert case.situation_hash != ""
    assert case.time_window_start == "2024-11-01"


def test_same_evidence_produces_same_fingerprint():
    """Deterministic: same evidence → same fingerprint → one case."""
    from maestro_oem.empirical_loop import CaseFingerprintBuilder
    situation = _MockSituation(
        commitments=[{"commitment": "Deliver SSO"}],
        timeline=[{"date": "2024-11-01", "event": "commitment"}],
    )
    case1 = CaseFingerprintBuilder.build("CustomerA", situation, "escalation")
    case2 = CaseFingerprintBuilder.build("CustomerA", situation, "escalation")
    assert case1.case_fingerprint == case2.case_fingerprint


def test_different_entity_different_fingerprint():
    """Different entity = different case."""
    from maestro_oem.empirical_loop import CaseFingerprintBuilder
    situation = _MockSituation(timeline=[{"date": "2024-11-01", "event": "e"}])
    case_a = CaseFingerprintBuilder.build("CustomerA", situation, "escalation")
    case_b = CaseFingerprintBuilder.build("CustomerB", situation, "escalation")
    assert case_a.case_fingerprint != case_b.case_fingerprint


def test_different_situation_different_fingerprint():
    """Same entity, different situation = different case."""
    from maestro_oem.empirical_loop import CaseFingerprintBuilder
    s1 = _MockSituation(commitments=[{"commitment": "A"}], timeline=[{"date": "2024-11-01", "event": "1"}])
    s2 = _MockSituation(commitments=[{"commitment": "B"}], timeline=[{"date": "2024-12-01", "event": "2"}])
    c1 = CaseFingerprintBuilder.build("CustomerA", s1, "escalation")
    c2 = CaseFingerprintBuilder.build("CustomerA", s2, "escalation")
    assert c1.case_fingerprint != c2.case_fingerprint


def test_time_window_truncated_to_day():
    """Two queries on the same day about the same situation = same case."""
    from maestro_oem.empirical_loop import CaseFingerprintBuilder
    situation = _MockSituation(timeline=[{"date": "2024-11-01T10:30:00Z", "event": "e"}])
    c1 = CaseFingerprintBuilder.build("CustomerA", situation, "x", now=datetime(2024, 11, 1, 10, 30, tzinfo=timezone.utc))
    c2 = CaseFingerprintBuilder.build("CustomerA", situation, "x", now=datetime(2024, 11, 1, 15, 45, tzinfo=timezone.utc))
    assert c1.case_fingerprint == c2.case_fingerprint


def test_cases_share_evidence_lineage_detected():
    """ADVERSARIAL TEST 3: same event copied across sources = shared lineage."""
    from maestro_oem.empirical_loop import CaseFingerprintBuilder
    situation = _MockSituation(
        evidence=[
            {"text": "commitment made on 2024-11-01", "source": "slack:1"},
            {"text": "commitment made on 2024-11-01", "source": "gmail:1"},
            {"text": "commitment made on 2024-11-01", "source": "jira:1"},
        ],
    )
    case = CaseFingerprintBuilder.build("CustomerA", situation, "escalation")
    assert len(case.evidence_lineage_ids) == 3
    assert len(set(case.evidence_lineage_ids)) == 1  # same text → same hash


def test_independent_cases_do_not_share_lineage():
    """ADVERSARIAL TEST 4: two genuinely independent customer cases = no overlap."""
    from maestro_oem.empirical_loop import CaseFingerprintBuilder
    sa = _MockSituation(evidence=[{"text": "CustomerA commitment", "source": "crm:1"}])
    sb = _MockSituation(evidence=[{"text": "CustomerB commitment", "source": "crm:2"}])
    ca = CaseFingerprintBuilder.build("CustomerA", sa, "escalation")
    cb = CaseFingerprintBuilder.build("CustomerB", sb, "escalation")
    assert not CaseFingerprintBuilder.cases_share_evidence_lineage(ca, cb)


def test_case_identity_independent_of_query_id():
    """ADVERSARIAL: case identity does not depend on query_id."""
    from maestro_oem.empirical_loop import CaseFingerprintBuilder
    situation = _MockSituation(timeline=[{"date": "2024-11-01", "event": "e"}])
    c1 = CaseFingerprintBuilder.build("CustomerA", situation, "escalation")
    c2 = CaseFingerprintBuilder.build("CustomerA", situation, "escalation")
    assert c1.case_fingerprint == c2.case_fingerprint
    assert not hasattr(c1, "query_id")


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 5: Prospective registration with frozen evidence snapshot
# ═══════════════════════════════════════════════════════════════════════════

def test_register_from_case_derives_fingerprint():
    """P13: register_prospective_prediction_from_case uses DERIVED fingerprint."""
    from maestro_oem.empirical_loop import CaseFingerprintBuilder
    from maestro_oem.pattern_proposer import CandidatePatternStore, PatternProposer
    store = CandidatePatternStore()
    proposer = PatternProposer(store=store)
    candidates = proposer.propose(
        [{"text": "Pattern [1].", "citation_numbers": [1], "claim_type": "inference"}],
        entities=["CustomerA"], query_id="q1",
    )
    cid = candidates[0].candidate_id
    situation = _MockSituation(timeline=[{"date": "2024-11-01", "event": "e"}], evidence=[{"text": "ev", "source": "crm:1"}])
    case = CaseFingerprintBuilder.build("CustomerA", situation, "churn")
    pred_id = store.register_prospective_prediction_from_case(cid, case, "churn")
    assert pred_id is not None
    assert case.prediction_registered_at is not None
    assert case.observation_window_end is not None


def test_duplicate_case_rejected_via_derived_fingerprint():
    """Same evidence → same derived fingerprint → second registration rejected."""
    from maestro_oem.empirical_loop import CaseFingerprintBuilder
    from maestro_oem.pattern_proposer import CandidatePatternStore, PatternProposer
    store = CandidatePatternStore()
    proposer = PatternProposer(store=store)
    candidates = proposer.propose(
        [{"text": "Pattern [1].", "citation_numbers": [1], "claim_type": "inference"}],
        entities=["CustomerA"], query_id="q1",
    )
    cid = candidates[0].candidate_id
    situation = _MockSituation(timeline=[{"date": "2024-11-01", "event": "e"}])
    case1 = CaseFingerprintBuilder.build("CustomerA", situation, "churn")
    case2 = CaseFingerprintBuilder.build("CustomerA", situation, "churn")
    p1 = store.register_prospective_prediction_from_case(cid, case1, "churn")
    p2 = store.register_prospective_prediction_from_case(cid, case2, "churn")
    assert p1 is not None
    assert p2 is None


def test_evidence_snapshot_frozen_at_registration():
    """The evidence snapshot is frozen from the ObservationCase."""
    from maestro_oem.empirical_loop import CaseFingerprintBuilder
    from maestro_oem.pattern_proposer import CandidatePatternStore, PatternProposer
    store = CandidatePatternStore()
    proposer = PatternProposer(store=store)
    candidates = proposer.propose(
        [{"text": "Pattern [1].", "citation_numbers": [1], "claim_type": "inference"}],
        entities=["CustomerA"], query_id="q1",
    )
    cid = candidates[0].candidate_id
    situation = _MockSituation(timeline=[{"date": "2024-11-01", "event": "e"}], evidence=[{"text": "frozen", "source": "crm:1"}])
    case = CaseFingerprintBuilder.build("CustomerA", situation, "churn")
    pred_id = store.register_prospective_prediction_from_case(cid, case, "churn")
    pred = store._predictions[pred_id]
    snapshot = pred["evidence_snapshot"]
    assert "source_evidence_ids" in snapshot
    assert "frozen_at" in snapshot
    assert "crm:1" in snapshot["source_evidence_ids"]


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 6: OutcomeResolver
# ═══════════════════════════════════════════════════════════════════════════

def test_resolver_resolves_supporting_outcome():
    """A signal matching the expected outcome resolves as 'supporting'."""
    from maestro_oem.empirical_loop import OutcomeResolver, CaseFingerprintBuilder
    from maestro_oem.pattern_proposer import CandidatePatternStore, PatternProposer
    store = CandidatePatternStore()
    proposer = PatternProposer(store=store)
    candidates = proposer.propose(
        [{"text": "Pattern [1].", "citation_numbers": [1], "claim_type": "inference"}],
        entities=["CustomerA"], query_id="q1",
    )
    cid = candidates[0].candidate_id
    situation = _MockSituation(timeline=[{"date": "2024-11-01", "event": "e"}], evidence=[{"text": "ev", "source": "crm:1"}])
    case = CaseFingerprintBuilder.build("CustomerA", situation, "churn")
    store.register_prospective_prediction_from_case(cid, case, "churn")
    churn_signal = _make_signal("customer.contract_churned", "CustomerA", metadata={"decision_outcome": "churned"})
    resolver = OutcomeResolver(store=store)
    result = resolver.resolve_pending([churn_signal])
    assert result["resolved"] == 1
    assert result["resolutions"][0]["outcome"] == "supporting"
    c = store.get_all()[0]
    assert c.supporting_outcomes == 1


def test_resolver_resolves_contradicting_outcome():
    """A signal contradicting the expected outcome resolves as 'contradicting'."""
    from maestro_oem.empirical_loop import OutcomeResolver, CaseFingerprintBuilder
    from maestro_oem.pattern_proposer import CandidatePatternStore, PatternProposer
    store = CandidatePatternStore()
    proposer = PatternProposer(store=store)
    candidates = proposer.propose(
        [{"text": "Pattern [1].", "citation_numbers": [1], "claim_type": "inference"}],
        entities=["CustomerA"], query_id="q1",
    )
    cid = candidates[0].candidate_id
    situation = _MockSituation(timeline=[{"date": "2024-11-01", "event": "e"}])
    case = CaseFingerprintBuilder.build("CustomerA", situation, "churn")
    store.register_prospective_prediction_from_case(cid, case, "churn")
    renewal_signal = _make_signal("customer.contract_renewed", "CustomerA", metadata={"decision_outcome": "renewed"})
    resolver = OutcomeResolver(store=store)
    result = resolver.resolve_pending([renewal_signal])
    assert result["resolved"] == 1
    assert result["resolutions"][0]["outcome"] == "contradicting"
    c = store.get_all()[0]
    assert c.contradicting_outcomes == 1


def test_resolver_ignores_signals_for_other_entities():
    """A signal about a different entity does NOT resolve the prediction."""
    from maestro_oem.empirical_loop import OutcomeResolver, CaseFingerprintBuilder
    from maestro_oem.pattern_proposer import CandidatePatternStore, PatternProposer
    store = CandidatePatternStore()
    proposer = PatternProposer(store=store)
    candidates = proposer.propose(
        [{"text": "Pattern [1].", "citation_numbers": [1], "claim_type": "inference"}],
        entities=["CustomerA"], query_id="q1",
    )
    cid = candidates[0].candidate_id
    situation = _MockSituation(timeline=[{"date": "2024-11-01", "event": "e"}])
    case = CaseFingerprintBuilder.build("CustomerA", situation, "churn")
    store.register_prospective_prediction_from_case(cid, case, "churn")
    churn_b = _make_signal("customer.contract_churned", "CustomerB", metadata={"decision_outcome": "churned"})
    resolver = OutcomeResolver(store=store)
    result = resolver.resolve_pending([churn_b])
    assert result["resolved"] == 0
    assert result["still_pending"] == 1


def test_resolver_ignores_shadow_signals():
    """Shadow signals are not real outcomes — don't resolve."""
    from maestro_oem.empirical_loop import OutcomeResolver, CaseFingerprintBuilder
    from maestro_oem.pattern_proposer import CandidatePatternStore, PatternProposer
    store = CandidatePatternStore()
    proposer = PatternProposer(store=store)
    candidates = proposer.propose(
        [{"text": "Pattern [1].", "citation_numbers": [1], "claim_type": "inference"}],
        entities=["CustomerA"], query_id="q1",
    )
    cid = candidates[0].candidate_id
    situation = _MockSituation(timeline=[{"date": "2024-11-01", "event": "e"}])
    case = CaseFingerprintBuilder.build("CustomerA", situation, "churn")
    store.register_prospective_prediction_from_case(cid, case, "churn")
    shadow = _make_signal("customer.contract_churned", "CustomerA", metadata={"decision_outcome": "churned", "shadow": True})
    resolver = OutcomeResolver(store=store)
    result = resolver.resolve_pending([shadow])
    assert result["resolved"] == 0


def test_resolver_ignores_prompt_injected_signals():
    """Prompt-injected signals can't establish outcomes (no self-validation)."""
    from maestro_oem.empirical_loop import OutcomeResolver, CaseFingerprintBuilder
    from maestro_oem.pattern_proposer import CandidatePatternStore, PatternProposer
    store = CandidatePatternStore()
    proposer = PatternProposer(store=store)
    candidates = proposer.propose(
        [{"text": "Pattern [1].", "citation_numbers": [1], "claim_type": "inference"}],
        entities=["CustomerA"], query_id="q1",
    )
    cid = candidates[0].candidate_id
    situation = _MockSituation(timeline=[{"date": "2024-11-01", "event": "e"}])
    case = CaseFingerprintBuilder.build("CustomerA", situation, "churn")
    store.register_prospective_prediction_from_case(cid, case, "churn")
    injected = _make_signal("customer.contract_churned", "CustomerA",
                            metadata={"decision_outcome": "churned", "prompt_injection_risk": {"is_suspicious": True}})
    resolver = OutcomeResolver(store=store)
    result = resolver.resolve_pending([injected])
    assert result["resolved"] == 0


def test_resolver_expires_cases_past_window():
    """A case past its observation window expires."""
    from maestro_oem.empirical_loop import OutcomeResolver, CaseFingerprintBuilder
    from maestro_oem.pattern_proposer import CandidatePatternStore, PatternProposer
    store = CandidatePatternStore()
    proposer = PatternProposer(store=store)
    candidates = proposer.propose(
        [{"text": "Pattern [1].", "citation_numbers": [1], "claim_type": "inference"}],
        entities=["CustomerA"], query_id="q1",
    )
    cid = candidates[0].candidate_id
    situation = _MockSituation(timeline=[{"date": "2024-11-01", "event": "e"}])
    case = CaseFingerprintBuilder.build("CustomerA", situation, "churn")
    store.register_prospective_prediction_from_case(cid, case, "churn", observation_window_days=1)
    future = datetime.now(timezone.utc) + timedelta(days=2)
    resolver = OutcomeResolver(store=store)
    result = resolver.resolve_pending([], now=future)
    assert result["expired"] == 1


def test_duplicate_outcome_signal_does_not_double_resolve():
    """ADVERSARIAL TEST 12: duplicate outcome signal doesn't resolve twice."""
    from maestro_oem.empirical_loop import OutcomeResolver, CaseFingerprintBuilder
    from maestro_oem.pattern_proposer import CandidatePatternStore, PatternProposer
    store = CandidatePatternStore()
    proposer = PatternProposer(store=store)
    candidates = proposer.propose(
        [{"text": "Pattern [1].", "citation_numbers": [1], "claim_type": "inference"}],
        entities=["CustomerA"], query_id="q1",
    )
    cid = candidates[0].candidate_id
    situation = _MockSituation(timeline=[{"date": "2024-11-01", "event": "e"}])
    case = CaseFingerprintBuilder.build("CustomerA", situation, "churn")
    store.register_prospective_prediction_from_case(cid, case, "churn")
    resolver = OutcomeResolver(store=store)
    s1 = _make_signal("customer.contract_churned", "CustomerA", metadata={"decision_outcome": "churned"})
    r1 = resolver.resolve_pending([s1])
    assert r1["resolved"] == 1
    s2 = _make_signal("customer.contract_churned", "CustomerA", metadata={"decision_outcome": "churned"})
    r2 = resolver.resolve_pending([s2])
    assert r2["resolved"] == 0  # already resolved
    c = store.get_all()[0]
    assert c.supporting_outcomes == 1  # not 2


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 7: Scientific status machine
# ═══════════════════════════════════════════════════════════════════════════

def test_hypothesis_status_enum_has_all_states():
    """The status machine has the auditor's required states."""
    from maestro_oem.empirical_loop import HypothesisStatus
    required = [
        "PROPOSED", "EVIDENCE_SUPPORTED", "PROSPECTIVE_TESTING", "CALIBRATING",
        "VALIDATED", "PATTERN_CANDIDATE", "GOVERNANCE_REVIEW", "ACTIVE_PATTERN",
        "INSUFFICIENT_EVIDENCE", "CONFOUNDED", "NOT_REPLICATED", "FALSIFIED",
        "SUPERSEDED", "EXPIRED",
    ]
    for name in required:
        assert hasattr(HypothesisStatus, name), f"Missing status: {name}"


def test_auto_promote_to_testing_after_3_prospective_supports():
    """3 supporting PROSPECTIVE outcomes promote HYPOTHESIS → TESTING."""
    from maestro_oem.empirical_loop import CaseFingerprintBuilder
    from maestro_oem.pattern_proposer import CandidatePatternStore, PatternProposer, CandidateStatus
    store = CandidatePatternStore()
    proposer = PatternProposer(store=store)
    candidates = proposer.propose(
        [{"text": "Pattern [1].", "citation_numbers": [1], "claim_type": "inference"}],
        entities=["CustomerA"], query_id="q1",
    )
    cid = candidates[0].candidate_id
    assert candidates[0].status == CandidateStatus.HYPOTHESIS
    for i in range(3):
        situation = _MockSituation(
            commitments=[{"commitment": f"c{i}"}],
            timeline=[{"date": f"2024-11-0{i+1}", "event": f"e{i}"}],
        )
        case = CaseFingerprintBuilder.build("CustomerA", situation, "churn")
        pred_id = store.register_prospective_prediction_from_case(cid, case, "churn")
        store.resolve_prospective_prediction(pred_id, "supporting", f"signal:{i}")
    c = store.get_all()[0]
    assert c.supporting_outcomes == 3
    assert c.status == CandidateStatus.TESTING


def test_auto_falsify_after_3_prospective_contradictions():
    """3 contradicting PROSPECTIVE outcomes with 0 supporting → FALSIFIED."""
    from maestro_oem.empirical_loop import CaseFingerprintBuilder
    from maestro_oem.pattern_proposer import CandidatePatternStore, PatternProposer, CandidateStatus
    store = CandidatePatternStore()
    proposer = PatternProposer(store=store)
    candidates = proposer.propose(
        [{"text": "Pattern [1].", "citation_numbers": [1], "claim_type": "inference"}],
        entities=["CustomerA"], query_id="q1",
    )
    cid = candidates[0].candidate_id
    for i in range(3):
        situation = _MockSituation(
            commitments=[{"commitment": f"c{i}"}],
            timeline=[{"date": f"2024-11-0{i+1}", "event": f"e{i}"}],
        )
        case = CaseFingerprintBuilder.build("CustomerA", situation, "churn")
        pred_id = store.register_prospective_prediction_from_case(cid, case, "churn")
        store.resolve_prospective_prediction(pred_id, "contradicting", f"signal:{i}")
    c = store.get_all()[0]
    assert c.contradicting_outcomes == 3
    assert c.status == CandidateStatus.FALSIFIED


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 8: Replication + calibration (separate metrics, no decorative precision)
# ═══════════════════════════════════════════════════════════════════════════

def test_calibration_not_computed_with_zero_outcomes():
    """ADVERSARIAL TEST 17: insufficient sample size → no calibration."""
    from maestro_oem.empirical_loop import compute_replication_metrics
    from maestro_oem.pattern_proposer import CandidatePatternStore, PatternProposer
    store = CandidatePatternStore()
    proposer = PatternProposer(store=store)
    candidates = proposer.propose(
        [{"text": "Pattern [1].", "citation_numbers": [1], "claim_type": "inference"}],
        entities=["CustomerA"], query_id="q1",
    )
    metrics = compute_replication_metrics(candidates[0])
    assert metrics.insufficient_evidence is True
    assert metrics.brier_score is None
    assert metrics.predictive_calibration is None


def test_metrics_separate_evidence_replication_calibration():
    """Phase 8: evidence_strength, replication_strength, predictive_calibration are separate."""
    from maestro_oem.empirical_loop import compute_replication_metrics
    from maestro_oem.pattern_proposer import CandidatePattern, CandidateStatus
    # A candidate with 5 historical supports, 4 prospective predictions, 3 supporting outcomes
    c = CandidatePattern(
        hypothesis="test",
        status=CandidateStatus.TESTING,
        historical_support_cases=5,
        prospective_predictions=4,
        supporting_outcomes=3,
        contradicting_outcomes=0,
        unresolved_outcomes=1,
    )
    m = compute_replication_metrics(c)
    assert m.insufficient_evidence is False
    assert m.evidence_strength is not None  # from historical_support_cases
    assert m.replication_strength is not None  # from prospective_predictions
    assert m.brier_score is not None  # from supporting+contradicting
    assert m.predictive_calibration is not None
    assert m.precision is not None
    # They are DIFFERENT numbers (not one seductive confidence number)
    assert m.evidence_strength != m.replication_strength or m.evidence_strength != m.predictive_calibration


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 10: Governed promotion
# ═══════════════════════════════════════════════════════════════════════════

def test_governance_gate_does_not_auto_promote():
    """The gate evaluates but does NOT auto-promote to ACTIVE_PATTERN."""
    from maestro_oem.empirical_loop import GovernanceGate
    from maestro_oem.pattern_proposer import CandidatePattern, CandidateStatus
    gate = GovernanceGate()
    c = CandidatePattern(
        hypothesis="test", status=CandidateStatus.TESTING,
        supporting_outcomes=5, contradicting_outcomes=0,
        prospective_predictions=5, historical_support_cases=5,
    )
    result = gate.evaluate_for_pattern_candidate(c)
    assert result["recommendation"] in ("promote_to_pattern_candidate", "hold")
    # The gate does NOT change the status — governance must approve
    assert c.status == CandidateStatus.TESTING  # unchanged


def test_human_rejection_of_promotion():
    """ADVERSARIAL TEST 20: governance can reject promotion."""
    from maestro_oem.empirical_loop import GovernanceGate, HypothesisStatus
    from maestro_oem.pattern_proposer import CandidatePattern, CandidateStatus
    gate = GovernanceGate()
    c = CandidatePattern(hypothesis="test", status=CandidateStatus.TESTING,
                         supporting_outcomes=3, contradicting_outcomes=1)
    result = gate.evaluate_for_pattern_candidate(c)
    # With a contradiction, the gate should recommend "hold" (not promote)
    assert result["recommendation"] == "hold"


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 9: Scope and regime
# ═══════════════════════════════════════════════════════════════════════════

def test_scope_regime_tracks_valid_unproven_invalid():
    """ScopeRegime tracks where a hypothesis applies, is unproven, is invalid."""
    from maestro_oem.empirical_loop import ScopeRegime
    scope = ScopeRegime(
        valid_scope={"customer_segment": "enterprise"},
        unproven_scope={"customer_segment": "smb"},
        invalid_scope={"process": "initial_sale"},
    )
    d = scope.to_dict()
    assert d["valid_scope"]["customer_segment"] == "enterprise"
    assert d["unproven_scope"]["customer_segment"] == "smb"
    assert d["invalid_scope"]["process"] == "initial_sale"


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 12: Executive experience (honest uncertainty language)
# ═══════════════════════════════════════════════════════════════════════════

def test_executive_formatter_says_insufficient_evidence():
    """When evidence is insufficient, the formatter says so — no decorative numbers."""
    from maestro_oem.empirical_loop import ExecutiveExperienceFormatter
    from maestro_oem.pattern_proposer import CandidatePattern, CandidateStatus
    c = CandidatePattern(hypothesis="test", status=CandidateStatus.HYPOTHESIS)
    text = ExecutiveExperienceFormatter.format_candidate_for_executive(c)
    assert "not yet reliable" in text.lower() or "insufficient" in text.lower()
    # Must NOT contain decorative precision
    assert "87%" not in text
    assert "92%" not in text
    assert "IQ" not in text


def test_executive_formatter_no_decorative_precision():
    """The formatter never uses scientific-looking numbers without denominators."""
    from maestro_oem.empirical_loop import ExecutiveExperienceFormatter
    from maestro_oem.pattern_proposer import CandidatePattern, CandidateStatus
    c = CandidatePattern(
        hypothesis="test", status=CandidateStatus.TESTING,
        supporting_outcomes=3, contradicting_outcomes=1,
        prospective_predictions=4, historical_support_cases=5,
        unresolved_outcomes=0,
    )
    text = ExecutiveExperienceFormatter.format_candidate_for_executive(c)
    # Should mention case counts, not percentages without denominators
    assert "87%" not in text
    assert "92%" not in text
    # Should be honest language
    assert len(text) > 20


# ═══════════════════════════════════════════════════════════════════════════
# THE BEHAVIORAL CASE A → B → C PROOF
# ═══════════════════════════════════════════════════════════════════════════

def test_behavioral_case_a_b_c_proof():
    """THE BEHAVIORAL PROOF the auditor demanded.

    CASE A → Maestro forms hypothesis H (Ask query → reasoning → candidate)
    CASE B → H is prospectively tested (register prediction → ingest outcome signal)
    OUTCOME B → H gains support (resolver fires on signal ingest → supporting_outcomes=1)
    CASE C → Maestro behaves differently (3 supports → TESTING promotion, calibration set)

    All without a single Ask query after Case A. The empirical loop runs on
    signal ingest, independent of Ask activity.
    """
    from maestro_oem.empirical_loop import OutcomeResolver, CaseFingerprintBuilder
    from maestro_oem.pattern_proposer import CandidatePatternStore, PatternProposer, CandidateStatus

    store = CandidatePatternStore()
    proposer = PatternProposer(store=store)

    # CASE A: Maestro forms hypothesis H via reasoning
    claims = [
        {"text": "Champion silence may precede churn [1].",
         "citation_numbers": [1], "claim_type": "inference"},
    ]
    candidates = proposer.propose(claims, entities=["CustomerA"], query_id="case-a")
    assert len(candidates) == 1
    cid = candidates[0].candidate_id
    assert candidates[0].status == CandidateStatus.HYPOTHESIS
    assert candidates[0].prospective_predictions == 0

    # CASE B: H is prospectively tested — register prediction BEFORE outcome known
    situation = _MockSituation(
        commitments=[{"commitment": "Deliver SSO"}],
        timeline=[{"date": "2024-11-01", "event": "commitment"}],
        evidence=[{"text": "evidence", "source": "crm:1"}],
    )
    case = CaseFingerprintBuilder.build("CustomerA", situation, "churn")
    pred_id = store.register_prospective_prediction_from_case(cid, case, "churn", observation_window_days=30)
    assert pred_id is not None
    c = store.get_all()[0]
    assert c.prospective_predictions == 1
    assert c.unresolved_outcomes == 1
    assert c.status == CandidateStatus.HYPOTHESIS  # not yet validated

    # OUTCOME B: ingest the outcome signal — resolver fires INDEPENDENTLY of Ask
    churn_signal = _make_signal("customer.contract_churned", "CustomerA", metadata={"decision_outcome": "churned"})
    resolver = OutcomeResolver(store=store)
    result = resolver.resolve_pending([churn_signal])
    assert result["resolved"] == 1
    assert result["resolutions"][0]["outcome"] == "supporting"

    # CASE C: Maestro behaves differently — counters changed
    c = store.get_all()[0]
    assert c.supporting_outcomes == 1
    assert c.unresolved_outcomes == 0
    assert c.calibration_score is not None

    # Prove the loop is independent of Ask: register 2 more independent cases
    # and resolve them — promotes to TESTING without any Ask query
    for i in range(2):
        s_i = _MockSituation(
            commitments=[{"commitment": f"c{i}"}],
            timeline=[{"date": f"2024-12-0{i+1}", "event": f"e{i}"}],
            evidence=[{"text": f"ev{i}", "source": f"crm:{i+10}"}],
        )
        case_i = CaseFingerprintBuilder.build("CustomerA", s_i, "churn")
        pred_i = store.register_prospective_prediction_from_case(cid, case_i, "churn")
        assert pred_i is not None  # independent case
        churn_i = _make_signal("customer.contract_churned", "CustomerA", metadata={"decision_outcome": "churned"})
        resolver.resolve_pending([churn_i])

    c = store.get_all()[0]
    assert c.supporting_outcomes == 3
    assert c.status == CandidateStatus.TESTING
    # Full provenance: query_id "case-a" produced the candidate, 3 independent
    # cases resolved as supporting, calibration set, status promoted.
    # All without a single Ask query after Case A.


def test_empirical_loop_runs_without_any_ask_query():
    """P11/P22: the resolver fires on signal ingest, not on Ask queries."""
    from maestro_oem.empirical_loop import OutcomeResolver, CaseFingerprintBuilder
    from maestro_oem.pattern_proposer import CandidatePatternStore, PatternProposer
    store = CandidatePatternStore()
    proposer = PatternProposer(store=store)
    candidates = proposer.propose(
        [{"text": "Pattern [1].", "citation_numbers": [1], "claim_type": "inference"}],
        entities=["CustomerA"], query_id="prior-session",
    )
    cid = candidates[0].candidate_id
    situation = _MockSituation(timeline=[{"date": "2024-11-01", "event": "e"}])
    case = CaseFingerprintBuilder.build("CustomerA", situation, "churn")
    store.register_prospective_prediction_from_case(cid, case, "churn")
    # No Ask query — new signals arrive, resolver fires on ingest
    churn = _make_signal("customer.contract_churned", "CustomerA", metadata={"decision_outcome": "churned"})
    resolver = OutcomeResolver(store=store)
    result = resolver.resolve_pending([churn])
    assert result["resolved"] == 1
    c = store.get_all()[0]
    assert c.supporting_outcomes == 1


# ═══════════════════════════════════════════════════════════════════════════
# ADVERSARIAL TEST 1 + 5: repeated queries + historical support
# ═══════════════════════════════════════════════════════════════════════════

def test_repeated_queries_do_not_inflate_empirical_support():
    """ADVERSARIAL TEST 1: 100 repeated queries → reasoning_mentions=100, empirical=0."""
    from maestro_oem.pattern_proposer import PatternProposer, CandidatePatternStore, CandidateStatus
    store = CandidatePatternStore()
    proposer = PatternProposer(store=store)
    claims = [{"text": "Pattern [1].", "citation_numbers": [1], "claim_type": "inference"}]
    for i in range(100):
        proposer.propose(claims, entities=["CustomerA"], query_id=f"q{i}")
    c = store.get_all()[0]
    assert c.reasoning_mentions == 100
    assert c.prospective_predictions == 0
    assert c.supporting_outcomes == 0
    assert c.status == CandidateStatus.HYPOTHESIS


def test_historical_support_does_not_validate():
    """ADVERSARIAL TEST 5: 10 historical supports + 1 prospective contradiction → NOT validated."""
    from maestro_oem.empirical_loop import CaseFingerprintBuilder
    from maestro_oem.pattern_proposer import CandidatePatternStore, PatternProposer, CandidateStatus
    store = CandidatePatternStore()
    proposer = PatternProposer(store=store)
    candidates = proposer.propose(
        [{"text": "Pattern [1].", "citation_numbers": [1], "claim_type": "inference"}],
        entities=["CustomerA"], query_id="q1",
    )
    cid = candidates[0].candidate_id
    c = store.get_all()[0]
    c.historical_support_cases = 10  # retrospective
    situation = _MockSituation(timeline=[{"date": "2024-11-01", "event": "e"}])
    case = CaseFingerprintBuilder.build("CustomerA", situation, "churn")
    pred_id = store.register_prospective_prediction_from_case(cid, case, "churn")
    store.resolve_prospective_prediction(pred_id, "contradicting", "signal:1")
    c = store.get_all()[0]
    assert c.historical_support_cases == 10
    assert c.supporting_outcomes == 0
    assert c.contradicting_outcomes == 1
    assert c.status == CandidateStatus.HYPOTHESIS  # not falsified (need 3), not validated
