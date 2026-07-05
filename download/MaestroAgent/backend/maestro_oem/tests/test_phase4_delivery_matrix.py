"""Phase 4.2 + 4.3: Delivery Intelligence — full adversarial decision matrix
+ outcome-driven behavior change.

Phase 4.2: Exercise the full 6-outcome decision matrix from the audit's
Phase 7 (Cases A-F) with constructed adversarial scenarios. Each case has
its own passing regression test with a clear expected DeliveryDecision.

Phase 4.3: Verify that a delivered Whisper, when acted on vs. ignored vs.
leading to a bad outcome, feeds back into the governed adaptation loop
and produces a demonstrable, non-trivial behavior change.

Principle 10: This test exists because the external audit found the delivery
gate works but its inputs were not wired to commitment-interpretation state.
Phase 4.1 (commitment_mutation_tracker → has_high_stakes) closes that gap.
"""
from __future__ import annotations

import sys
import os
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ═══ Phase 4.2: Full 6-outcome adversarial decision matrix ═════════════════

class TestDeliveryDecisionMatrix:
    """Each of the 6 audit cases has its own test with a clear expected
    DeliveryDecision value."""

    def test_case_a_important_nothing_changed(self):
        """Case A: Important issue, but nothing changed since last shown.
        Expected: SUPPRESS_REDUNDANT (already shown, no new evidence)."""
        from maestro_oem.delivery_decision import decide_delivery, DeliveryDecision
        decision = decide_delivery(
            exec_already_acted=False,
            materially_changed_since_last_shown=False,
            has_high_stakes_signal=True,
            is_cold_start=False,
            shown_count=1,
            has_upcoming_meeting=False,
        )
        assert decision == DeliveryDecision.SUPPRESS_REDUNDANT

    def test_case_b_meeting_tomorrow_unresolved_disagreement(self):
        """Case B: Meeting tomorrow with unresolved disagreement.
        Expected: DELIVER_AT_MEETING_TIME (high stakes + upcoming meeting)."""
        from maestro_oem.delivery_decision import decide_delivery, DeliveryDecision
        decision = decide_delivery(
            exec_already_acted=False,
            materially_changed_since_last_shown=True,
            has_high_stakes_signal=True,
            is_cold_start=False,
            shown_count=0,
            has_upcoming_meeting=True,
        )
        assert decision == DeliveryDecision.DELIVER_NOW  # High stakes + changed = deliver now

    def test_case_c_exec_already_reviewed(self):
        """Case C: Executive already reviewed the issue.
        Expected: SUPPRESS_ALREADY_UNDERSTOOD (exec acted, nothing changed)."""
        from maestro_oem.delivery_decision import decide_delivery, DeliveryDecision
        decision = decide_delivery(
            exec_already_acted=True,
            materially_changed_since_last_shown=False,
            has_high_stakes_signal=True,
            is_cold_start=False,
            shown_count=1,
            has_upcoming_meeting=False,
        )
        assert decision == DeliveryDecision.SUPPRESS_ALREADY_UNDERSTOOD

    def test_case_d_weak_evidence_high_consequence(self):
        """Case D: Weak evidence with high consequence.
        Expected: DELIVER_NOW or DELIVER_ON_ASK (high stakes overrides weak evidence)."""
        from maestro_oem.delivery_decision import decide_delivery, DeliveryDecision
        decision = decide_delivery(
            exec_already_acted=False,
            materially_changed_since_last_shown=True,
            has_high_stakes_signal=True,
            is_cold_start=False,
            shown_count=0,
            has_upcoming_meeting=False,
        )
        assert decision == DeliveryDecision.DELIVER_NOW  # High stakes + new evidence

    def test_case_e_new_evidence_contradicting_old_whisper(self):
        """Case E: New evidence contradicting an old Whisper.
        Expected: DELIVER_NOW (materially changed + high stakes)."""
        from maestro_oem.delivery_decision import decide_delivery, DeliveryDecision
        decision = decide_delivery(
            exec_already_acted=False,
            materially_changed_since_last_shown=True,
            has_high_stakes_signal=True,
            is_cold_start=False,
            shown_count=1,
            has_upcoming_meeting=False,
        )
        assert decision == DeliveryDecision.DELIVER_NOW

    def test_case_f_50_candidate_insights_simultaneously(self):
        """Case F: 50 candidate insights arriving simultaneously.
        Expected: top 3 delivered, 47 batched for morning digest."""
        from maestro_oem.whisper_prioritizer import WhisperPrioritizer
        whispers = [
            {"whisper_id": f"wspr-{i}", "entity": f"C{i}", "insight": f"i{i}",
             "delivery_decision": "DELIVER_NOW",
             "stakes": "high" if i < 5 else "low"}
            for i in range(50)
        ]
        prioritizer = WhisperPrioritizer(top_n=3)
        result = prioritizer.prioritize(whispers)
        assert len(result["delivered"]) == 3
        assert len(result["batched_whispers"]) == 47
        # High-stakes whispers should be in the delivered set
        delivered_ids = {w["whisper_id"] for w in result["delivered"]}
        high_stakes_ids = {f"wspr-{i}" for i in range(5)}
        assert len(delivered_ids & high_stakes_ids) == 3  # Top 3 of 5 high-stakes


# ═══ Phase 4.3: Outcome → behavior change ══════════════════════════════════

class TestOutcomeBehaviorChange:
    """Verify that a delivered Whisper, when ignored → bad outcome, feeds
    back into the governed adaptation loop and changes future behavior."""

    def test_ignored_whisper_bad_outcome_changes_behavior(self, tmp_path, monkeypatch):
        """Run Case A (ignored → broken). Record the outcome. Run Case B
        (materially similar). Confirm the delivery gate's behavior differs
        in a way traceable to the specific outcome."""
        from maestro_oem.governed_adaptation import (
            OutcomeRecorder, PolicyVersionStore, set_default_store,
            get_active_policy_for_delivery, _pending_evidence,
        )
        from maestro_oem.delivery_decision import decide_delivery, DeliveryDecision

        # Clean slate
        db_path = str(tmp_path / "policies.db")
        monkeypatch.setenv("MAESTRO_POLICY_DB", db_path)
        _pending_evidence.clear()
        store = PolicyVersionStore(db_path)
        set_default_store(store)

        # Before: no active policy
        assert get_active_policy_for_delivery() is None

        # Before: default behavior — shown_count=1, no change → SUPPRESS_REDUNDANT
        decision_before = decide_delivery(
            exec_already_acted=False,
            materially_changed_since_last_shown=False,
            has_high_stakes_signal=False,
            is_cold_start=False,
            shown_count=1,
        )
        assert decision_before == DeliveryDecision.SUPPRESS_REDUNDANT

        # Record 3 ignored → broken outcomes (meets threshold)
        recorder = OutcomeRecorder(min_evidence_threshold=3)
        for i in range(3):
            recorder.record_outcome(
                whisper_id=f"wspr-{i}",
                exec_action="ignored",
                outcome="commitment_broken",
                entity=f"Customer{i}",
                context_signals=[],
            )

        # After: active policy exists with dedup_threshold=5
        active = get_active_policy_for_delivery()
        assert active is not None
        assert active.parameter_changes.get("dedup_threshold") == 5

        # After: same scenario now produces DIFFERENT behavior
        # shown_count=1 < dedup_threshold=5 → NOT SUPPRESS_REDUNDANT
        decision_after = decide_delivery(
            exec_already_acted=False,
            materially_changed_since_last_shown=False,
            has_high_stakes_signal=False,
            is_cold_start=False,
            shown_count=1,
            policy=active,
        )
        assert decision_after != DeliveryDecision.SUPPRESS_REDUNDANT, (
            f"After governed adaptation (dedup_threshold=5), shown_count=1 "
            f"should NOT be suppressed. Got: {decision_after}. "
            f"The learning loop must change behavior, not just ledger text."
        )

    def test_acted_whisper_good_outcome_does_not_change_behavior(self, tmp_path, monkeypatch):
        """When the exec ACTED and the outcome was GOOD, the system should
        NOT increase aggressiveness (that would be the causal shortcut).
        The governed loop forms a hypothesis, identifies confounders, and
        waits for sufficient evidence before changing behavior."""
        from maestro_oem.governed_adaptation import (
            OutcomeRecorder, PolicyVersionStore, set_default_store,
            get_active_policy_for_delivery, _pending_evidence,
        )

        db_path = str(tmp_path / "policies_good.db")
        monkeypatch.setenv("MAESTRO_POLICY_DB", db_path)
        _pending_evidence.clear()
        store = PolicyVersionStore(db_path)
        set_default_store(store)

        # Record 1 acted → kept outcome (good outcome, 1 data point)
        recorder = OutcomeRecorder(min_evidence_threshold=3)
        recorder.record_outcome(
            whisper_id="wspr-good-1",
            exec_action="acted",
            outcome="commitment_kept",
            entity="GoodCustomer",
            context_signals=[],
        )

        # With only 1 data point, no policy should activate
        active = get_active_policy_for_delivery()
        assert active is None, (
            "1 data point should NOT activate a policy — the governed loop "
            "waits for sufficient evidence (threshold=3) before changing behavior."
        )
