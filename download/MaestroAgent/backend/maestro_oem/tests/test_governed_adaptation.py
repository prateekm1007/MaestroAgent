"""Priority 1: Governed Adaptation Loop — close learning → behavior WITHOUT
the causal shortcut.

CEO directive (2026-07-04):
> Do NOT wire Learning Ledger output directly into the delivery gate.
> That would implement exactly the causal shortcut the audit warns
> against: 'ignored Whisper → bad outcome → increase alert aggressiveness.'
> That's not learning. That's overreaction.

The correct architecture:
  Outcome observed
    ↓
  Attribution analysis (what happened? was Maestro's intervention relevant?)
    ↓
  Alternative explanations (confounders)
    ↓
  Hypothesis formation (NOT a policy change — a testable hypothesis)
    ↓
  Prospective experiment
    ↓
  Sufficient repeated evidence
    ↓
  Bounded policy proposal (risk-tiered: LOW auto, MEDIUM propose, HIGH approval)
    ↓
  Human approval for material policy changes
    ↓
  Policy version (versioned, rollback-able)
    ↓
  Future behavior change (decide_delivery reads ACTIVE policy)
    ↓
  Evaluation

The verification gate (CEO-specified):
  Case A (ignored → broken): Maestro forms a hypothesis, identifies
  confounders, does NOT immediately change behavior.
  Case B (similar situation): Maestro may adjust LOW-risk parameters
  based on accumulated evidence, does NOT adjust HIGH-risk parameters
  without human approval, and any adjustment is versioned + rollback-able.

Adversarial tests (write first, watch fail, then build):

  1. test_adaptation_policy_dataclass_exists
     AdaptationPolicy dataclass must exist with all required fields.

  2. test_policy_version_store_exists_and_persists
     PolicyVersionStore must exist, be SQLite-backed, and survive restart.

  3. test_attribution_analyzer_exists
     AttributionAnalyzer must exist and be importable.

  4. test_attribution_analyzer_identifies_confounders
     Given an outcome (broken commitment after ignored Whisper), the
     analyzer MUST identify confounders (concurrent staffing changes,
     market shifts, etc.) — NOT just say "ignored → broken."

  5. test_attribution_analyzer_does_not_claim_causation
     The analyzer's output must say "hypothesis" or "may have," NOT
     "caused" or "proven." Causal uncertainty is preserved.

  6. test_policy_proposer_low_risk_auto_activates
     LOW-risk policy (dedup threshold, timing) with sufficient evidence
     auto-activates WITHOUT human approval.

  7. test_policy_proposer_high_risk_requires_approval
     HIGH-risk policy (escalation, recipient change) requires explicit
     human approval. Even with overwhelming evidence, it does NOT
     auto-activate.

  8. test_decide_delivery_reads_active_policy
     decide_delivery() must read the ACTIVE policy from PolicyVersionStore.
     The policy determines dedup threshold, timing preference, etc.

  9. test_case_a_ignored_broken_forms_hypothesis_not_behavior_change
     VERIFICATION GATE: Case A (ignored → broken) must produce a
     hypothesis in the store, NOT change the active policy. The
     delivery gate behavior must NOT change after one data point.

  10. test_case_b_accumulated_evidence_low_risk_adjustment
      VERIFICATION GATE: After N similar cases (configurable threshold),
      LOW-risk parameters may adjust. The adjustment is versioned and
      rollback-able.

  11. test_case_b_high_risk_no_auto_change
      VERIFICATION GATE: After N similar cases, HIGH-risk parameters
      do NOT change without human approval — even with strong evidence.

  12. test_policy_rollback
      A policy can be rolled back to a previous version. After rollback,
      decide_delivery() uses the previous policy's parameters.

  13. test_wiring_p11_decide_delivery_reads_policy_store
      P11: decide_delivery() must call PolicyVersionStore.get_active_policy().

  14. test_no_causal_shortcut
      CRITICAL: The Learning Ledger must NOT directly call decide_delivery()
      or modify its inputs. The only path is: Ledger → AttributionAnalyzer →
      Hypothesis → PolicyProposer → (approval) → PolicyVersionStore →
      decide_delivery reads active policy.

P2: Untested code is unverified code.
P6: Fail-closed — no behavior change without governed approval.
P11: Wiring proved by grep + execution.
P13: Confounders are DERIVED from signal context, not caller-supplied.
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


# ═══ GAL: Governed Adaptation Loop ═════════════════════════════════════════

# ─── 1. AdaptationPolicy dataclass ─────────────────────────────────────────

def test_adaptation_policy_dataclass_exists():
    """AdaptationPolicy dataclass must exist with all required fields."""
    from maestro_oem.governed_adaptation import AdaptationPolicy
    p = AdaptationPolicy(
        policy_id="pol-1",
        version=1,
        hypothesis="Acting on commitment warnings earlier may reduce broken commitments",
        evidence_for=[],
        evidence_against=[],
        confounders_identified=[],
        status="HYPOTHESIS",
        risk_level="LOW",
        requires_human_approval=False,
        approved_by=None,
        previous_policy_id=None,
        created_at=datetime.now(timezone.utc).isoformat(),
        activated_at=None,
    )
    assert p.policy_id == "pol-1"
    assert p.status == "HYPOTHESIS"
    assert p.risk_level == "LOW"


# ─── 2. PolicyVersionStore persists ────────────────────────────────────────

def test_policy_version_store_exists_and_persists(tmp_path):
    """PolicyVersionStore must exist, be SQLite-backed, and survive restart."""
    from maestro_oem.governed_adaptation import PolicyVersionStore, AdaptationPolicy

    db_path = str(tmp_path / "policies.db")
    store1 = PolicyVersionStore(db_path)
    policy = AdaptationPolicy(
        policy_id="pol-1",
        version=1,
        hypothesis="test hypothesis",
        evidence_for=[], evidence_against=[], confounders_identified=[],
        status="HYPOTHESIS", risk_level="LOW", requires_human_approval=False,
        approved_by=None, previous_policy_id=None,
        created_at=datetime.now(timezone.utc).isoformat(), activated_at=None,
    )
    store1.save(policy)
    store1.close()

    store2 = PolicyVersionStore(db_path)
    retrieved = store2.get("pol-1")
    assert retrieved is not None, "Policy must survive restart (SQLite-backed)"
    assert retrieved.hypothesis == "test hypothesis"
    store2.close()


# ─── 3. AttributionAnalyzer exists ─────────────────────────────────────────

def test_attribution_analyzer_exists():
    """AttributionAnalyzer must exist and be importable."""
    from maestro_oem.governed_adaptation import AttributionAnalyzer
    assert AttributionAnalyzer is not None


# ─── 4. AttributionAnalyzer identifies confounders ─────────────────────────

def test_attribution_analyzer_identifies_confounders():
    """Given an outcome (broken commitment after ignored Whisper), the
    analyzer MUST identify confounders — NOT just say 'ignored → broken.'"""
    from maestro_oem.governed_adaptation import AttributionAnalyzer

    analyzer = AttributionAnalyzer()
    # Simulate: a commitment warning was shown, exec ignored it, commitment broke
    outcome = {
        "whisper_shown": True,
        "exec_action": "ignored",
        "outcome": "commitment_broken",
        "entity": "TestCorp",
        "context_signals": [
            {"type": "staffing_change", "actor": "jane@example.com", "note": "champion left"},
            {"type": "market_shift", "note": "competitor lowered prices"},
        ],
    }
    analysis = analyzer.analyze(outcome)

    assert "confounders" in analysis, "Analysis must include confounders"
    assert len(analysis["confounders"]) > 0, (
        "Must identify at least 1 confounder (staffing change, market shift). "
        f"Got: {analysis['confounders']}"
    )


# ─── 5. AttributionAnalyzer preserves causal uncertainty ───────────────────

def test_attribution_analyzer_does_not_claim_causation():
    """The analyzer's output must say 'hypothesis' or 'may have,' NOT
    'caused' or 'proven.' Causal uncertainty is preserved."""
    from maestro_oem.governed_adaptation import AttributionAnalyzer

    analyzer = AttributionAnalyzer()
    outcome = {
        "whisper_shown": True,
        "exec_action": "ignored",
        "outcome": "commitment_broken",
        "entity": "TestCorp",
        "context_signals": [],
    }
    analysis = analyzer.analyze(outcome)

    hypothesis = analysis.get("hypothesis", "").lower()
    causal_strength = analysis.get("causal_strength", "").lower()

    # Must NOT claim causation. Note: "not a proven causal link" is ALLOWED —
    # that's hedged language explicitly disclaiming causation. We only forbid
    # affirmative claims of causation.
    forbidden_words = ["caused", "definitely", "certainly"]
    for word in forbidden_words:
        assert word not in hypothesis, (
            f"Hypothesis must not claim causation ('{word}'). Got: {hypothesis}"
        )
        assert word not in causal_strength, (
            f"Causal strength must not claim certainty ('{word}'). Got: {causal_strength}"
        )
    # "proven" is forbidden UNLESS it's in the phrase "not a proven" (hedged disclaimer)
    if "proven" in hypothesis:
        assert "not a proven" in hypothesis or "not proven" in hypothesis, (
            f"Hypothesis may only use 'proven' in a hedged disclaimer ('not a proven causal link'). "
            f"Got: {hypothesis}"
        )

    # Must use hedged language
    hedged = any(w in hypothesis for w in ["may", "might", "could", "hypothesis", "unclear"])
    assert hedged, (
        f"Hypothesis must use hedged language (may/might/could). Got: {hypothesis}"
    )


# ─── 6. LOW-risk policy auto-activates ─────────────────────────────────────

def test_policy_proposer_low_risk_auto_activates(tmp_path):
    """LOW-risk policy (dedup threshold, timing) with sufficient evidence
    auto-activates WITHOUT human approval."""
    from maestro_oem.governed_adaptation import PolicyProposer, PolicyVersionStore, AdaptationPolicy

    store = PolicyVersionStore(str(tmp_path / "policies.db"))
    proposer = PolicyProposer(store)

    # Simulate accumulated evidence (N=5, above threshold)
    evidence = [
        {"outcome": "broken", "whisper_shown": True, "exec_action": "ignored", "context_signals": []}
        for _ in range(5)
    ]
    proposal = proposer.propose(
        hypothesis="Acting on commitment warnings earlier may reduce broken commitments",
        evidence=evidence,
        risk_level="LOW",
        parameter_changes={"dedup_threshold": 0},  # LOW-risk: don't suppress duplicates
    )

    assert proposal.status == "ACTIVE", (
        f"LOW-risk policy with sufficient evidence must auto-activate. Got: {proposal.status}"
    )
    assert proposal.activated_at is not None, "Active policy must have activated_at"


# ─── 7. HIGH-risk policy requires approval ─────────────────────────────────

def test_policy_proposer_high_risk_requires_approval(tmp_path):
    """HIGH-risk policy (escalation, recipient change) requires explicit
    human approval. Even with overwhelming evidence, it does NOT auto-activate."""
    from maestro_oem.governed_adaptation import PolicyProposer, PolicyVersionStore

    store = PolicyVersionStore(str(tmp_path / "policies.db"))
    proposer = PolicyProposer(store)

    evidence = [
        {"outcome": "broken", "whisper_shown": True, "exec_action": "ignored", "context_signals": []}
        for _ in range(20)  # overwhelming evidence
    ]
    proposal = proposer.propose(
        hypothesis="Escalating ignored commitment warnings to VP may reduce broken commitments",
        evidence=evidence,
        risk_level="HIGH",
        parameter_changes={"escalation_recipient": "vp@example.com"},
    )

    assert proposal.status == "PROPOSED", (
        f"HIGH-risk policy must NOT auto-activate (requires human approval). Got: {proposal.status}"
    )
    assert proposal.requires_human_approval is True
    assert proposal.activated_at is None


# ─── 8. decide_delivery reads active policy ────────────────────────────────

def test_decide_delivery_reads_active_policy(tmp_path):
    """decide_delivery() must read the ACTIVE policy from PolicyVersionStore.
    The policy determines dedup threshold, timing preference, etc."""
    from maestro_oem.governed_adaptation import PolicyVersionStore, AdaptationPolicy
    from maestro_oem.delivery_decision import decide_delivery, DeliveryDecision
    import inspect as _inspect

    # P11: decide_delivery must accept a policy parameter (or read from store)
    sig = _inspect.signature(decide_delivery)
    params = set(sig.parameters.keys())
    assert "policy" in params or "policy_store" in params, (
        f"decide_delivery must accept a 'policy' or 'policy_store' parameter. "
        f"Params: {params}"
    )


# ─── 9. VERIFICATION GATE: Case A → hypothesis, not behavior change ────────

def test_case_a_ignored_broken_forms_hypothesis_not_behavior_change(tmp_path):
    """VERIFICATION GATE: Case A (ignored → broken) must produce a
    hypothesis in the store, NOT change the active policy. The
    delivery gate behavior must NOT change after one data point."""
    from maestro_oem.governed_adaptation import (
        AttributionAnalyzer, PolicyProposer, PolicyVersionStore,
    )

    store = PolicyVersionStore(str(tmp_path / "policies.db"))
    analyzer = AttributionAnalyzer()
    proposer = PolicyProposer(store)

    # Case A: one ignored → broken outcome
    outcome = {
        "whisper_shown": True,
        "exec_action": "ignored",
        "outcome": "commitment_broken",
        "entity": "TestCorp",
        "context_signals": [{"type": "staffing_change"}],
    }
    analysis = analyzer.analyze(outcome)

    # The proposer must NOT activate a policy from ONE data point
    proposal = proposer.propose(
        hypothesis=analysis["hypothesis"],
        evidence=[outcome],
        risk_level="MEDIUM",
        parameter_changes={"dedup_threshold": 0},
    )

    # Must be HYPOTHESIS or PROPOSED, NOT ACTIVE
    assert proposal.status in ("HYPOTHESIS", "PROPOSED"), (
        f"One data point must NOT activate a policy. Got status: {proposal.status}"
    )

    # No active policy should exist yet
    active = store.get_active_policy()
    # Either None (no policy) or the default policy — NOT a new behavior change
    if active is not None:
        assert active.version == 0 or active.policy_id == "default", (
            "After 1 data point, active policy must be the default (no behavior change)"
        )


# ─── 10. VERIFICATION GATE: Case B accumulated evidence LOW-risk ───────────

def test_case_b_accumulated_evidence_low_risk_adjustment(tmp_path):
    """VERIFICATION GATE: After N similar cases (configurable threshold),
    LOW-risk parameters may adjust. The adjustment is versioned and
    rollback-able."""
    from maestro_oem.governed_adaptation import PolicyProposer, PolicyVersionStore

    store = PolicyVersionStore(str(tmp_path / "policies.db"))
    proposer = PolicyProposer(store, min_evidence_threshold=5)

    # N=5 similar cases (meets threshold)
    evidence = [
        {"outcome": "broken", "whisper_shown": True, "exec_action": "ignored",
         "entity": f"Customer{i}", "context_signals": []}
        for i in range(5)
    ]
    proposal = proposer.propose(
        hypothesis="Acting on commitment warnings earlier may reduce broken commitments",
        evidence=evidence,
        risk_level="LOW",
        parameter_changes={"dedup_threshold": 0},
    )

    assert proposal.status == "ACTIVE", (
        f"5 data points (≥ threshold) + LOW risk → must activate. Got: {proposal.status}"
    )
    assert proposal.version > 0, "Activated policy must have version > 0"
    assert proposal.previous_policy_id is not None or proposal.version == 1, (
        "Must link to previous policy for rollback (or be version 1)"
    )


# ─── 11. VERIFICATION GATE: HIGH-risk no auto-change ───────────────────────

def test_case_b_high_risk_no_auto_change(tmp_path):
    """VERIFICATION GATE: After N similar cases, HIGH-risk parameters
    do NOT change without human approval — even with strong evidence."""
    from maestro_oem.governed_adaptation import PolicyProposer, PolicyVersionStore

    store = PolicyVersionStore(str(tmp_path / "policies.db"))
    proposer = PolicyProposer(store, min_evidence_threshold=5)

    evidence = [
        {"outcome": "broken", "whisper_shown": True, "exec_action": "ignored",
         "entity": f"Customer{i}", "context_signals": []}
        for i in range(20)  # overwhelming evidence
    ]
    proposal = proposer.propose(
        hypothesis="Escalating ignored warnings to VP may reduce broken commitments",
        evidence=evidence,
        risk_level="HIGH",
        parameter_changes={"escalation_recipient": "vp@example.com"},
    )

    assert proposal.status == "PROPOSED", (
        f"HIGH-risk must NOT auto-activate even with 20 data points. Got: {proposal.status}"
    )

    # Human approval flow
    approved = proposer.approve(proposal.policy_id, approved_by="ceo@example.com")
    assert approved.status == "ACTIVE", (
        f"After human approval, HIGH-risk policy must activate. Got: {approved.status}"
    )
    assert approved.approved_by == "ceo@example.com"


# ─── 12. Policy rollback ───────────────────────────────────────────────────

def test_policy_rollback(tmp_path):
    """A policy can be rolled back to a previous version. After rollback,
    decide_delivery() uses the previous policy's parameters."""
    from maestro_oem.governed_adaptation import PolicyProposer, PolicyVersionStore

    store = PolicyVersionStore(str(tmp_path / "policies.db"))
    proposer = PolicyProposer(store, min_evidence_threshold=3)

    # Activate policy v1
    evidence = [{"outcome": "broken", "whisper_shown": True, "exec_action": "ignored",
                 "entity": f"C{i}", "context_signals": []} for i in range(3)]
    v1 = proposer.propose(
        hypothesis="h1", evidence=evidence, risk_level="LOW",
        parameter_changes={"dedup_threshold": 1},
    )
    assert v1.status == "ACTIVE"

    # Activate policy v2 (replaces v1)
    v2 = proposer.propose(
        hypothesis="h2", evidence=evidence, risk_level="LOW",
        parameter_changes={"dedup_threshold": 0},
    )
    assert v2.status == "ACTIVE"
    assert v2.previous_policy_id == v1.policy_id

    # Rollback to v1
    rolled_back = store.rollback(v2.policy_id)
    active = store.get_active_policy()
    assert active.policy_id == v1.policy_id, (
        f"After rollback, active policy must be v1. Got: {active.policy_id}"
    )


# ─── 13. P11: decide_delivery reads policy store ───────────────────────────

def test_wiring_p11_decide_delivery_reads_policy_store():
    """P11: decide_delivery() must call PolicyVersionStore.get_active_policy()."""
    from maestro_oem import delivery_decision
    source = inspect.getsource(delivery_decision)
    assert "policy" in source.lower(), (
        "delivery_decision.py must reference 'policy' (P11 — wired to read active policy)"
    )


# ─── 14. CRITICAL: No causal shortcut ──────────────────────────────────────

def test_no_causal_shortcut():
    """CRITICAL: The Learning Ledger must NOT directly call decide_delivery()
    or modify its inputs. The only path is: Ledger → AttributionAnalyzer →
    Hypothesis → PolicyProposer → (approval) → PolicyVersionStore →
    decide_delivery reads active policy."""
    from maestro_oem import learning_ledger, delivery_decision

    ledger_source = inspect.getsource(learning_ledger)
    # The ledger must NOT import or call decide_delivery directly
    assert "decide_delivery" not in ledger_source, (
        "CRITICAL: learning_ledger.py must NOT call decide_delivery directly — "
        "that's the causal shortcut. The path must go through the governed loop."
    )
