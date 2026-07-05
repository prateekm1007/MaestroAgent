"""ONE PATTERN THROUGH REALITY — the Active Cognition proof.

AUDITOR-DIRECTIVE (Gap 6):
> The most important arrow is: Governed Learning → Active Cognition.
> "Behaves differently" must mean something customer-visible or decision-relevant:
> * Ask gives a materially different answer.

This test proves the full chain with ONE hypothesis:
  "When ownership remains ambiguous after a cross-functional commitment,
   delivery delay becomes more likely."

The proof:
  BEFORE LEARNING: Ask Maestro → generic answer, no learned insight
  AFTER LEARNING: Ask Maestro → answer includes the learned insight (MATERIALLY DIFFERENT)
  AFTER UNLEARNING: contradictory cases → pattern narrows → insight changes

The executive receives reason, provenance, boundaries, and falsifiability.
No "87% confidence." No decorative precision.
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


def _make_signal(signal_type_str: str, entity: str, metadata: dict | None = None):
    """Build a minimal ExecutionSignal for testing."""
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
        type=sig_type_map.get(signal_type_str, SignalType.INCIDENT),
        actor="test@acme.com",
        artifact=f"test:{entity}:{uuid4().hex[:8]}",
        metadata={"customer": entity, **(metadata or {})},
        provider=SignalProvider.CUSTOMER,
        timestamp=datetime.now(timezone.utc),
    )


class _MockSituation:
    """Minimal Situation mock."""
    def __init__(self, commitments=None, timeline=None, evidence=None):
        self.commitments = commitments or []
        self.timeline = timeline or []
        self.evidence = evidence or []


class _MockModelProvider:
    """Mock LLM provider — returns a generic answer (no learned insight)."""
    def __init__(self):
        self.available = True
        self.circuit_state = type("S", (), {"value": "closed"})()

    async def synthesize(self, system, user):
        return type("R", (), {
            "text": (
                "The plan has dependencies across Platform and Security. "
                "Confirm the delivery date and ownership."
            ),
            "model_used": "mock", "provider_name": "mock",
            "mode": "model", "fallback_reason": "",
            "latency_ms": 50, "prompt_tokens": 10, "completion_tokens": 5,
        })()


# ═══════════════════════════════════════════════════════════════════════════
# THE ONE PATTERN THROUGH REALITY PROOF
# ═══════════════════════════════════════════════════════════════════════════

def test_one_pattern_through_reality():
    """THE PROOF: a learned pattern changes Ask output, then unlearns.

    AUDITOR-DIRECTIVE:
    > CASE A: Maestro discovers hypothesis H
    > CASE B: H is prospectively tested
    > OUTCOME: H gains bounded empirical support
    > GOVERNANCE: H becomes available to cognition within a defined scope
    > CASE C: a genuinely new situation arrives
    >   BEFORE learning: Maestro would have behaved X
    >   AFTER learning: Maestro behaves Y
    >   because: validated pattern H was available, scope matched

    Then unlearning:
    > Several future contradictory cases weaken the pattern.
    > Maestro stops using it universally or narrows its scope.
    > The customer-facing explanation changes accordingly.
    """
    from maestro_oem.pattern_proposer import (
        CandidatePatternStore, PatternProposer, CandidatePattern, CandidateStatus,
    )
    from maestro_oem.empirical_loop import CaseFingerprintBuilder, OutcomeResolver
    from maestro_oem.active_cognition import ActiveCognitionResolver
    from maestro_oem.ask_pipeline import AskPipeline

    store = CandidatePatternStore()

    # ─── BEFORE LEARNING: no active patterns ───────────────────────────────
    # The Ask answer should NOT contain "Learned insight"
    pipe = AskPipeline(
        signals=[], synthesis_provider=_MockModelProvider(),
        candidate_pattern_store=store,
    )
    before_result = asyncio.run(pipe.execute_async(
        "What should I clarify before approving this cross-functional plan?",
        user_email="auditor@acme.com",
    ))
    before_answer = before_result["answer"]
    assert "Learned insight" not in before_answer, \
        "BEFORE LEARNING: answer should NOT contain learned insight"

    # ─── CASE A: Maestro discovers hypothesis H ────────────────────────────
    # The hypothesis: "When ownership remains ambiguous after a cross-functional
    # commitment, delivery delay becomes more likely."
    hypothesis = (
        "the evidence may indicate that when ownership remains ambiguous after "
        "a cross-functional commitment, delivery delay becomes more likely"
    )
    candidate = CandidatePattern(
        hypothesis=hypothesis,
        claim_text="Ownership ambiguity may lead to delay",
        claim_type="inference",
        entities=["Platform", "Security", "cross-functional"],
        evidence_citation_numbers=[1, 2],
    )
    store.upsert(candidate, query_id="case-a")
    assert candidate.status == CandidateStatus.HYPOTHESIS

    # ─── CASE B: H is prospectively tested — 3 independent cases ───────────
    for i in range(3):
        situation = _MockSituation(
            commitments=[{"commitment": f"Cross-functional delivery {i}"}],
            timeline=[{"date": f"2024-11-0{i+1}", "event": f"commitment_{i}"}],
            evidence=[{"text": f"evidence_{i}", "source": f"crm:{i+10}"}],
        )
        case = CaseFingerprintBuilder.build("Platform", situation, "commitment broken")
        pred_id = store.register_prospective_prediction_from_case(
            candidate.candidate_id, case, "commitment broken",
        )
        assert pred_id is not None  # independent case (different fingerprint)

        # OUTCOME: the predicted outcome occurred (commitment was broken)
        store.resolve_prospective_prediction(pred_id, "supporting", f"signal:{i}")

    c = next((c for c in store.get_all() if c.candidate_id == candidate.candidate_id), None)
    assert c is not None
    assert c.supporting_outcomes == 3
    assert c.status == CandidateStatus.TESTING  # auto-promoted

    # ─── GOVERNANCE: H becomes available to cognition ──────────────────────
    # Governance approves with scope: valid for cross-functional work,
    # unproven for single-team work
    approved = store.governance_approve(
        candidate.candidate_id,
        actor="governance_review_board",
        valid_scope={"work_type": "cross-functional"},
        unproven_scope={"work_type": "single-team"},
    )
    assert approved
    c = next((c for c in store.get_all() if c.candidate_id == candidate.candidate_id), None)
    assert c is not None
    assert c.status == CandidateStatus.SCOPE_LIMITED  # narrow scope = SCOPE_LIMITED
    assert c.governance_approved_by == "governance_review_board"

    # ─── CASE C: a genuinely new situation arrives ─────────────────────────
    # Same query, but now Maestro has an active pattern. The answer should
    # be MATERIALLY DIFFERENT — it should contain the learned insight.
    after_result = asyncio.run(pipe.execute_async(
        "What should I clarify before approving this cross-functional plan?",
        user_email="auditor@acme.com",
    ))
    after_answer = after_result["answer"]

    # THE KEY ASSERTION: the AFTER answer is materially different
    assert "Learned insight" in after_answer, \
        "AFTER LEARNING: answer MUST contain learned insight — this is the Active Cognition arrow"
    assert "ownership" in after_answer.lower() or "ambiguous" in after_answer.lower(), \
        "AFTER LEARNING: answer should reference the learned pattern"
    assert "cross-functional" in after_answer.lower(), \
        "AFTER LEARNING: answer should reference the scope where the pattern applies"

    # The trace should record that an active pattern was applied
    trace = after_result["synthesis_trace"]
    assert trace["metadata"]["active_cognition"]["active_patterns_applied"] == 1

    # ─── UNLEARNING: contradictory cases weaken the pattern ────────────────
    # Register 5 contradictory cases — the pattern's scope should narrow
    for i in range(5):
        situation = _MockSituation(
            commitments=[{"commitment": f"Single-team delivery {i}"}],
            timeline=[{"date": f"2024-12-0{i+1}", "event": f"single_team_{i}"}],
            evidence=[{"text": f"single_ev_{i}", "source": f"crm:{i+20}"}],
        )
        case = CaseFingerprintBuilder.build("Platform", situation, "commitment kept")
        pred_id = store.register_prospective_prediction_from_case(
            candidate.candidate_id, case, "commitment kept",
        )
        if pred_id:
            # The outcome contradicts the hypothesis — commitment was KEPT despite ambiguity
            store.resolve_prospective_prediction(pred_id, "contradicting", f"signal:{i+10}")

    c = next((c for c in store.get_all() if c.candidate_id == candidate.candidate_id), None)
    assert c is not None
    assert c.contradicting_outcomes == 5
    # The pattern should be narrowed — governance narrows the scope
    store.narrow_scope(
        candidate.candidate_id,
        valid_scope={"work_type": "cross-functional", "segment": "security-sensitive"},
        unproven_scope={"work_type": "single-team"},
        invalid_scope={"work_type": "single-team"},
    )
    c = next((c for c in store.get_all() if c.candidate_id == candidate.candidate_id), None)
    assert c is not None
    assert c.status == CandidateStatus.SCOPE_LIMITED

    # ─── AFTER UNLEARNING: the insight changes ─────────────────────────────
    # The answer should still contain the insight, but now it should reflect
    # the narrowed scope and the contradictions
    unlearn_result = asyncio.run(pipe.execute_async(
        "What should I clarify before approving this cross-functional plan?",
        user_email="auditor@acme.com",
    ))
    unlearn_answer = unlearn_result["answer"]

    # The insight is still present (SCOPE_LIMITED is still active)
    assert "Learned insight" in unlearn_answer
    # But it should now mention the contradictions
    assert "contradicted" in unlearn_answer.lower() or "narrowing" in unlearn_answer.lower(), \
        "AFTER UNLEARNING: answer should acknowledge the contradictions"

    # ─── FULL FALSIFICATION: if 3 more contradictions arrive with 0 supports ─
    # Actually, the auto-falsify only triggers when contradicting >= 3 AND supporting == 0.
    # Since we have 3 supports, it won't auto-falsify. But governance can retire it.
    # Let's verify the pattern is still usable but narrowed.
    assert c.status == CandidateStatus.SCOPE_LIMITED
    assert c.supporting_outcomes == 3  # unchanged from before
    assert c.contradicting_outcomes == 5

    # ─── PROVENCE: the trace records the full chain ────────────────────────
    trace = unlearn_result["synthesis_trace"]
    active_cog = trace["metadata"]["active_cognition"]
    assert active_cog["active_patterns_applied"] == 1
    pattern_info = active_cog["patterns"][0]
    assert pattern_info["supporting_outcomes"] == 3
    assert pattern_info["contradicting_outcomes"] == 5
    assert pattern_info["status"] == "SCOPE_LIMITED"


def test_before_vs_after_answer_is_materially_different():
    """The BEFORE and AFTER answers must be materially different — not just whitespace."""
    from maestro_oem.pattern_proposer import (
        CandidatePatternStore, CandidatePattern, CandidateStatus,
    )
    from maestro_oem.ask_pipeline import AskPipeline

    store = CandidatePatternStore()
    pipe = AskPipeline(
        signals=[], synthesis_provider=_MockModelProvider(),
        candidate_pattern_store=store,
    )

    before = asyncio.run(pipe.execute_async(
        "What should I clarify before approving this cross-functional plan?",
        user_email="auditor@acme.com",
    ))

    # Create an active pattern
    candidate = CandidatePattern(
        hypothesis="ownership ambiguity may lead to delay in cross-functional work",
        claim_type="inference", entities=["Platform", "Security", "cross-functional"],
        status=CandidateStatus.ACTIVE_PATTERN,
        supporting_outcomes=5, contradicting_outcomes=0,
        valid_scope={"work_type": "cross-functional"},
        unproven_scope={"work_type": "single-team"},
        governance_approved_by="test",
    )
    store._candidates[candidate.dedup_key] = candidate

    after = asyncio.run(pipe.execute_async(
        "What should I clarify before approving this cross-functional plan?",
        user_email="auditor@acme.com",
    ))

    # The answers MUST be materially different
    assert before["answer"] != after["answer"]
    assert len(after["answer"]) > len(before["answer"])
    assert "Learned insight" in after["answer"]
    assert "Learned insight" not in before["answer"]


def test_falsified_pattern_not_used():
    """A FALSIFIED pattern is NOT used in answers — Maestro unlearns."""
    from maestro_oem.pattern_proposer import (
        CandidatePatternStore, CandidatePattern, CandidateStatus,
    )
    from maestro_oem.ask_pipeline import AskPipeline

    store = CandidatePatternStore()
    pipe = AskPipeline(
        signals=[], synthesis_provider=_MockModelProvider(),
        candidate_pattern_store=store,
    )

    # Create a FALSIFIED pattern
    candidate = CandidatePattern(
        hypothesis="ownership ambiguity may lead to delay",
        claim_type="inference", entities=["Platform", "cross-functional"],
        status=CandidateStatus.FALSIFIED,
        supporting_outcomes=0, contradicting_outcomes=3,
    )
    store._candidates[candidate.dedup_key] = candidate

    result = asyncio.run(pipe.execute_async(
        "What should I clarify before approving this cross-functional plan?",
        user_email="auditor@acme.com",
    ))

    # FALSIFIED patterns are NOT used
    assert "Learned insight" not in result["answer"]
    assert result["synthesis_trace"]["metadata"]["active_cognition"]["active_patterns_applied"] == 0
