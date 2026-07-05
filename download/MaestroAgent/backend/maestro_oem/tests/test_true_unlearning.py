"""True Unlearning — adversarial test proving Maestro can say "We were wrong."

AUDITOR-DIRECTIVE:
> If every contradiction merely produces SCOPE_LIMITED, the system could
> preserve false beliefs by continuously shrinking their scope.
>
> Maestro must be capable of saying: "We were wrong."
>
> Adversarial test:
> Pattern P becomes active.
> Then: 10 diverse, prospectively registered, cleanly resolved, low-confounder cases
> contradict P.
> Expected: P becomes FALSIFIED or RETRACTED, not merely SCOPE_LIMITED.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ["MAESTRO_LOCAL_DEV"] = "true"


def _make_signal(signal_type_str: str, entity: str, metadata: dict | None = None):
    from maestro_oem.signal import ExecutionSignal, SignalType, SignalProvider
    from uuid import uuid4
    sig_type_map = {
        "customer.commitment_kept": SignalType.CUSTOMER_COMMITMENT_KEPT,
        "customer.contract_renewed": SignalType.CUSTOMER_CONTRACT_RENEWED,
        "customer.commitment_broken": SignalType.CUSTOMER_COMMITMENT_BROKEN,
        "customer.contract_churned": SignalType.CUSTOMER_CONTRACT_CHURNED,
    }
    return ExecutionSignal(
        type=sig_type_map.get(signal_type_str, SignalType.INCIDENT),
        actor="test@acme.com",
        artifact=f"test:{entity}:{uuid4().hex[:8]}",
        metadata={"customer": entity, **(metadata or {})},
        provider=SignalProvider.CUSTOMER,
        timestamp=datetime.now(timezone.utc),
    )


class _MockSituation:
    def __init__(self, commitments=None, timeline=None, evidence=None):
        self.commitments = commitments or []
        self.timeline = timeline or []
        self.evidence = evidence or []


class _MockModelProvider:
    def __init__(self):
        self.available = True
        self.circuit_state = type("S", (), {"value": "closed"})()

    async def synthesize(self, system, user):
        return type("R", (), {
            "text": "Generic answer.",
            "model_used": "mock", "provider_name": "mock",
            "mode": "model", "fallback_reason": "",
            "latency_ms": 50, "prompt_tokens": 10, "completion_tokens": 5,
        })()


def test_true_unlearning_10_contradictions_falsifies_active_pattern():
    """10 diverse contradictory cases FALSIFY an active pattern — not just SCOPE_LIMITED.

    AUDITOR-DIRECTIVE:
    > Pattern P becomes active.
    > Then: 10 diverse, prospectively registered, cleanly resolved, low-confounder cases
    > contradict P.
    > Expected: P becomes FALSIFIED or RETRACTED, not merely SCOPE_LIMITED.
    """
    from maestro_oem.pattern_proposer import (
        CandidatePatternStore, PatternProposer, CandidatePattern, CandidateStatus,
    )
    from maestro_oem.empirical_loop import CaseFingerprintBuilder, OutcomeResolver
    from maestro_oem.active_cognition import ActiveCognitionResolver
    from maestro_oem.ask_pipeline import AskPipeline

    store = CandidatePatternStore()

    # ─── Pattern P becomes active ──────────────────────────────────────────
    # Hypothesis: "ownership ambiguity leads to delay in cross-functional work"
    # 3 supporting cases → TESTING → governance → ACTIVE_PATTERN
    candidate = CandidatePattern(
        hypothesis="ownership ambiguity may lead to delay in cross-functional work",
        claim_type="inference", entities=["Platform", "Security", "cross-functional"],
    )
    store.upsert(candidate, query_id="q0")

    # 3 supporting cases
    for i in range(3):
        s = _MockSituation(
            commitments=[{"commitment": f"cross-func-{i}"}],
            timeline=[{"date": f"2024-11-0{i+1}", "event": f"commitment_{i}"}],
            evidence=[{"text": f"ev_{i}", "source": f"crm:{i+10}"}],
        )
        case = CaseFingerprintBuilder.build("Platform", s, "commitment broken")
        pred_id = store.register_prospective_prediction_from_case(
            candidate.candidate_id, case, "commitment broken",
        )
        store.resolve_prospective_prediction(pred_id, "supporting", f"signal:{i}")

    c = next(c for c in store.get_all() if c.candidate_id == candidate.candidate_id)
    assert c.status == CandidateStatus.TESTING

    # Governance approves
    store.governance_approve(
        candidate.candidate_id, actor="board",
        valid_scope={"work_type": "cross-functional"},
    )
    c = next(c for c in store.get_all() if c.candidate_id == candidate.candidate_id)
    assert c.status in (CandidateStatus.ACTIVE_PATTERN, CandidateStatus.SCOPE_LIMITED)
    active_status = c.status

    # ─── Verify the pattern IS being used in answers ───────────────────────
    pipe = AskPipeline(
        signals=[], synthesis_provider=_MockModelProvider(),
        candidate_pattern_store=store,
    )
    with_insight = asyncio.run(pipe.execute_async(
        "What should I clarify before approving this cross-functional plan?",
        user_email="auditor@acme.com",
    ))
    assert "Learned insight" in with_insight["answer"], "Pattern should be active"

    # ─── 10 diverse, prospectively registered, cleanly resolved contradictions ─
    # Different entities, different situations, different time windows
    # All contradict the hypothesis (ownership ambiguity did NOT lead to delay)
    for i in range(10):
        entity = f"Team{i}"  # diverse entities
        s = _MockSituation(
            commitments=[{"commitment": f"diverse-commitment-{i}"}],
            timeline=[{"date": f"2024-12-{i+1:02d}", "event": f"event_{i}"}],
            evidence=[{"text": f"diverse_ev_{i}", "source": f"crm:{i+100}"}],
        )
        case = CaseFingerprintBuilder.build(entity, s, "commitment kept")
        pred_id = store.register_prospective_prediction_from_case(
            candidate.candidate_id, case, "commitment kept",
        )
        assert pred_id is not None, f"Case {i} should register (independent)"
        # Cleanly resolved: the commitment was KEPT despite ownership ambiguity
        store.resolve_prospective_prediction(pred_id, "contradicting", f"signal:{i+100}")

    # ─── THE KEY ASSERTION: pattern is FALSIFIED, not merely SCOPE_LIMITED ──
    c = next(c for c in store.get_all() if c.candidate_id == candidate.candidate_id)
    print(f"After 10 contradictions: status={c.status.value}, supports={c.supporting_outcomes}, contradicts={c.contradicting_outcomes}")
    assert c.status == CandidateStatus.FALSIFIED, \
        f"10 diverse contradictions must FALSIFY the pattern, not merely narrow scope. Got: {c.status.value}"
    assert c.contradicting_outcomes == 10
    assert c.supporting_outcomes == 3

    # ─── Maestro no longer uses the falsified pattern ──────────────────────
    without_insight = asyncio.run(pipe.execute_async(
        "What should I clarify before approving this cross-functional plan?",
        user_email="auditor@acme.com",
    ))
    assert "Learned insight" not in without_insight["answer"], \
        "FALSIFIED pattern must NOT appear in answers — Maestro unlearned it"

    # The trace records 0 active patterns
    active_cog = without_insight["synthesis_trace"]["metadata"]["active_cognition"]
    assert active_cog["active_patterns_applied"] == 0

    # ─── "We were wrong" ───────────────────────────────────────────────────
    # The pattern that was previously helping is now gone.
    # Maestro changed its mind when reality disagreed.
    assert "Learned insight" in with_insight["answer"]  # was there before
    assert "Learned insight" not in without_insight["answer"]  # gone after unlearning


def test_3_contradictions_with_supports_suspends_not_falsifies():
    """3 contradictions with some supports → SUSPEND (SCOPE_LIMITED), not FALSIFY.

    The system should distinguish:
    - 3 contradictions, 0 supports → FALSIFY (clearly wrong)
    - 3 contradictions, 3 supports → SUSPEND (conflicting evidence, under review)
    - 10 contradictions, 3 supports → FALSIFY (reality has spoken)
    """
    from maestro_oem.pattern_proposer import (
        CandidatePatternStore, CandidatePattern, CandidateStatus,
    )
    from maestro_oem.empirical_loop import CaseFingerprintBuilder

    store = CandidatePatternStore()
    candidate = CandidatePattern(
        hypothesis="test hypothesis",
        claim_type="inference", entities=["CustomerA"],
        status=CandidateStatus.ACTIVE_PATTERN,
        supporting_outcomes=3, contradicting_outcomes=0,
    )
    store._candidates[candidate.dedup_key] = candidate

    # Add 3 contradictions (3 supports already exist)
    for i in range(3):
        s = _MockSituation(
            timeline=[{"date": f"2024-12-0{i+1}", "event": f"e{i}"}],
            evidence=[{"text": f"ev{i}", "source": f"crm:{i+50}"}],
        )
        case = CaseFingerprintBuilder.build("CustomerA", s, "churn")
        pred_id = store.register_prospective_prediction_from_case(
            candidate.candidate_id, case, "churn",
        )
        store.resolve_prospective_prediction(pred_id, "contradicting", f"signal:{i}")

    c = store.get_all()[0]
    # 3 contradictions + 3 supports → SUSPEND (SCOPE_LIMITED), not FALSIFY
    assert c.status == CandidateStatus.SCOPE_LIMITED, \
        f"3 contradictions with 3 supports should SUSPEND, not FALSIFY. Got: {c.status.value}"
    assert c.contradicting_outcomes == 3
    assert c.supporting_outcomes == 3
