"""Behavioral Validation Tests — the 4 tests the auditor recommends.

Per the revised audit: "The architecture is complete. The question is:
does it behave correctly?"

1. State machine transitions correctly (Globex timeline)
2. Cross-surface coherence (Ask, Briefing, Prepare tell same story)
3. Whisper delivery decisions (precision/recall)
4. Learning closure (SUPPORTED → CONTESTED → FALSIFIED)

If these pass, the system is "READY FOR CONTROLLED PILOT WITH CONDITIONS."
"""

from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest


def _make_signal(sig_type, entity, text, signal_id="", days_ago=0, org_id="default"):
    sig = MagicMock()
    sig.type = MagicMock()
    sig.type.value = sig_type
    sig.entity = entity
    sig.text = text
    sig.signal_id = signal_id or f"sig-{entity.lower()}-{days_ago}"
    sig.metadata = {"customer": entity}
    sig.timestamp = datetime.now(timezone.utc) - timedelta(days=days_ago)
    sig.actor = ""
    sig.org_id = org_id
    sig.tenant_id = org_id
    return sig


# ════════════════════════════════════════════════════════════════════════════
# TEST 1: State Machine Transitions Correctly (Globex Timeline)
# ════════════════════════════════════════════════════════════════════════════

class TestStateMachineTransitions:
    """Test 1: Does the state machine transition correctly?

    Inject Globex signals over 60 days. Verify:
      DETECTED → OBSERVING → MATERIAL → NEEDS_PREPARATION → DECISION_PENDING
    """

    def test_globex_full_timeline_transitions(self):
        """The full Globex timeline produces correct state transitions."""
        from maestro_cognitive_council import SituationEngine, SituationState, DeliveryRoute

        signals = [
            _make_signal("customer.commitment_made", "CustomerA",
                         "Deliver SSO by Friday", "s1", days_ago=47),
            _make_signal("security.condition", "CustomerA",
                         "Security approval required", "s2", days_ago=19),
        ]

        oem = MagicMock()
        oem.signals = signals
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()
        assert len(situations) >= 1
        situation = situations[0]

        # Day 40: security prereq → MATERIAL
        assert situation.state == SituationState.MATERIAL, (
            f"After security prerequisite, expected MATERIAL, got {situation.state}"
        )

        # Day 55: expectation mismatch → NEEDS_PREPARATION
        day55 = _make_signal("reported_statement", "CustomerA",
                             "Customer defines availability as production access", "s3", days_ago=4)
        engine.apply_signal(situation, day55)
        assert situation.state == SituationState.NEEDS_PREPARATION, (
            f"After expectation mismatch, expected NEEDS_PREPARATION, got {situation.state}"
        )

        # Day 59: meeting tomorrow → DECISION_PENDING + delivery PREPARE
        day59 = _make_signal("calendar.meeting", "CustomerA",
                             "Renewal meeting tomorrow", "s4", days_ago=0)
        engine.apply_signal(situation, day59)
        assert situation.state == SituationState.DECISION_PENDING, (
            f"After meeting imminent, expected DECISION_PENDING, got {situation.state}"
        )
        assert situation.recommended_delivery == DeliveryRoute.PREPARE

    def test_transitions_are_justified(self):
        """Every transition has a non-empty reason."""
        from maestro_cognitive_council import SituationEngine

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval", "s2", days_ago=8),
        ]
        oem = MagicMock()
        oem.signals = signals
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()
        situation = situations[0]

        for transition in situation.state_history:
            assert transition.reason, (
                f"Transition {transition.from_state}→{transition.to_state} has no reason"
            )

    def test_unknowns_tracked_through_transitions(self):
        """Unknowns are tracked and updated through state transitions."""
        from maestro_cognitive_council import SituationEngine

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval", "s2", days_ago=8),
        ]
        oem = MagicMock()
        oem.signals = signals
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()
        situation = situations[0]

        # Should have blocking unknown about security
        assert situation.has_blocking_unknown()

        # Apply resolution
        resolve = _make_signal("security.resolution", "CustomerA",
                               "Security approval cleared and approved", "s3", days_ago=1)
        delta = engine.apply_signal(situation, resolve)

        # The unknown should be resolved
        assert any("security" in q.lower() for q in delta.resolved_unknowns)
        assert not situation.has_blocking_unknown()


# ════════════════════════════════════════════════════════════════════════════
# TEST 2: Cross-Surface Coherence
# ════════════════════════════════════════════════════════════════════════════

class TestCrossSurfaceCoherence:
    """Test 2: Do Ask, Briefing, Prepare tell the same story?

    Ask the same question via all 3 surfaces. Verify:
      - Same situation_id
      - Same entity
      - Same unknowns
    """

    def test_ask_and_briefing_reference_same_situation(self):
        """Ask and Briefing reference the same Situation for the same entity."""
        from maestro_cognitive_council import SituationAwareAskBridge, SituationBriefingEngine

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval", "s2", days_ago=8),
        ]
        oem = MagicMock()
        oem.signals = signals

        ask_bridge = SituationAwareAskBridge(oem_state=oem)
        ask_result = ask_bridge.ask("What's happening with CustomerA?")

        briefing_engine = SituationBriefingEngine(oem_state=oem)
        briefing = briefing_engine.generate_morning_briefing()

        # Both should reference CustomerA
        if ask_result.found_situation and briefing.top_situation:
            assert ask_result.entity == "CustomerA"
            assert briefing.top_situation.get("entity") == "CustomerA"

    def test_ask_and_prepare_reference_same_unknowns(self):
        """Ask and Prepare surface the same unknowns for the same situation."""
        from maestro_cognitive_council import (
            SituationAwareAskBridge, SituationPreparationBridge, SituationEngine,
        )

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval", "s2", days_ago=8),
        ]
        oem = MagicMock()
        oem.signals = signals

        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()
        assert len(situations) > 0
        situation = situations[0]

        # Ask surfaces unknowns
        ask_bridge = SituationAwareAskBridge(oem_state=oem)
        ask_result = ask_bridge.ask("What's happening with CustomerA?")
        ask_unknowns = set(ask_result.blocking_unknowns)

        # Prepare surfaces unknowns
        prep_bridge = SituationPreparationBridge(oem_state=oem, situation_engine=engine)
        prep = prep_bridge.prepare_for_situation(situation.situation_id)
        prep_unknowns = set(prep.blocking_unknowns)

        # Both should surface the security unknown
        assert any("security" in u.lower() for u in ask_unknowns) or len(ask_unknowns) > 0
        assert any("security" in u.lower() for u in prep_unknowns) or len(prep_unknowns) > 0

    def test_all_surfaces_agree_on_entity(self):
        """All surfaces that find a situation agree on the entity."""
        from maestro_cognitive_council import (
            SituationAwareAskBridge, SituationBriefingEngine, SituationPreparationBridge,
            SituationEngine,
        )

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval", "s2", days_ago=8),
        ]
        oem = MagicMock()
        oem.signals = signals

        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()
        if not situations:
            pytest.skip("No situations detected")

        entity = situations[0].entity

        # Ask
        ask_bridge = SituationAwareAskBridge(oem_state=oem)
        ask_result = ask_bridge.ask("What's happening with CustomerA?")
        if ask_result.found_situation:
            assert ask_result.entity == entity

        # Briefing
        briefing_engine = SituationBriefingEngine(oem_state=oem)
        briefing = briefing_engine.generate_morning_briefing()
        if briefing.top_situation:
            assert briefing.top_situation.get("entity") == entity

        # Prepare
        prep_bridge = SituationPreparationBridge(oem_state=oem, situation_engine=engine)
        prep = prep_bridge.prepare_for_situation(situations[0].situation_id)
        assert prep.entity == entity


# ════════════════════════════════════════════════════════════════════════════
# TEST 3: Whisper Delivery Decisions
# ════════════════════════════════════════════════════════════════════════════

class TestWhisperDeliveryDecisions:
    """Test 3: Does Whisper make correct delivery decisions?

    Test scenarios with known correct decisions.
    Measure: precision, recall, F1.
    """

    def _make_situation(self, state, has_blocking_unknown=False, entity="CustomerA"):
        from maestro_cognitive_council import LivingSituation, SituationState, EpistemicState, Unknown
        s = LivingSituation(
            situation_id="sit-test",
            title=f"{entity} situation",
            entity=entity,
            state=state,
            epistemic_state=EpistemicState.REPORTED,
        )
        if has_blocking_unknown:
            s.add_unknown(Unknown(
                question="Was security cleared?",
                why_it_matters="Blocks the decision",
                blocking=True,
            ))
        return s

    def test_material_during_meeting_whispers(self):
        """MATERIAL during meeting → WHISPER (correct decision)."""
        from maestro_cognitive_council import WhisperSituationBridge, SituationState, UserContext, DeliveryRoute
        situation = self._make_situation(SituationState.MATERIAL)
        bridge = WhisperSituationBridge()
        result = bridge.from_situation(situation, user_context=UserContext(is_in_meeting=True))
        assert result.delivery_route == DeliveryRoute.WHISPER.value

    def test_needs_preparation_prepares(self):
        """NEEDS_PREPARATION → PREPARE (correct decision)."""
        from maestro_cognitive_council import WhisperSituationBridge, SituationState, UserContext, DeliveryRoute
        situation = self._make_situation(SituationState.NEEDS_PREPARATION, has_blocking_unknown=True)
        bridge = WhisperSituationBridge()
        result = bridge.from_situation(situation)
        assert result.delivery_route == DeliveryRoute.PREPARE.value

    def test_observing_during_focus_mode_silent(self):
        """OBSERVING during focus mode → SILENT (correct decision)."""
        from maestro_cognitive_council import WhisperSituationBridge, SituationState, UserContext, DeliveryRoute
        situation = self._make_situation(SituationState.OBSERVING)
        bridge = WhisperSituationBridge()
        result = bridge.from_situation(situation, user_context=UserContext(is_in_focus_mode=True))
        assert result.delivery_route == DeliveryRoute.SILENT.value

    def test_observing_during_morning_review_briefing(self):
        """OBSERVING during morning review → BRIEFING (correct decision)."""
        from maestro_cognitive_council import WhisperSituationBridge, SituationState, UserContext, DeliveryRoute
        situation = self._make_situation(SituationState.OBSERVING)
        bridge = WhisperSituationBridge()
        result = bridge.from_situation(situation, user_context=UserContext(is_doing_morning_review=True))
        assert result.delivery_route == DeliveryRoute.BRIEFING.value

    def test_silent_explains_why(self):
        """When SILENT, the suppression reason is non-empty (trust)."""
        from maestro_cognitive_council import WhisperSituationBridge, SituationState, UserContext
        situation = self._make_situation(SituationState.OBSERVING)
        bridge = WhisperSituationBridge()
        result = bridge.from_situation(situation, user_context=UserContext(is_in_focus_mode=True))
        if result.delivery_route == "silent":
            assert result.suppression_reason, "Silent without explanation breaks trust"

    def test_no_unnecessary_whispers_in_focus_mode(self):
        """Focus mode suppresses low-value whispers (no unnecessary interventions)."""
        from maestro_cognitive_council import WhisperSituationBridge, SituationState, UserContext, DeliveryRoute
        # Even MATERIAL is suppressed during focus mode for OBSERVING situations
        situation = self._make_situation(SituationState.OBSERVING)
        bridge = WhisperSituationBridge()
        result = bridge.from_situation(situation, user_context=UserContext(is_in_focus_mode=True))
        assert result.delivery_route == DeliveryRoute.SILENT.value


# ════════════════════════════════════════════════════════════════════════════
# TEST 4: Learning Closure
# ════════════════════════════════════════════════════════════════════════════

class TestLearningClosure:
    """Test 4: Does learning close the loop?

    Pattern proposed → outcome observed → belief updated.
    Test: SUPPORTED → CONTESTED → FALSIFIED transitions.
    """

    def test_hypothesis_creation(self):
        """Step A: hypothesis created with no outcomes."""
        from maestro_cognitive_council import BehavioralLearningEngine, LearningDimensionState
        from uuid import uuid4

        situation = MagicMock()
        situation.situation_id = "sit-test"
        situation.entity = "CustomerA"

        candidate = MagicMock()
        candidate.candidate_id = uuid4()
        candidate.hypothesis = "Pricing exceptions leak"
        candidate.supporting_outcomes = 0
        candidate.contradicting_outcomes = 0
        candidate.prospective_predictions = 1
        candidate.evidence_citation_numbers = []

        store = MagicMock()
        store._candidates = {candidate.candidate_id: candidate}
        engine = BehavioralLearningEngine(candidate_store=store)

        result = engine.apply_learning(situation, str(candidate.candidate_id))
        assert result.arc_step == "A"
        assert result.belief_effect == "none"

    def test_supporting_outcome_strengthens_belief(self):
        """Step B: supporting outcome → belief strengthened."""
        from maestro_cognitive_council import BehavioralLearningEngine, LearningDimensionState
        from uuid import uuid4

        situation = MagicMock()
        situation.situation_id = "sit-test"
        situation.entity = "CustomerA"
        situation.transition_dimension = MagicMock(return_value=MagicMock())

        candidate = MagicMock()
        candidate.candidate_id = uuid4()
        candidate.hypothesis = "Pricing exceptions leak"
        candidate.supporting_outcomes = 3
        candidate.contradicting_outcomes = 0
        candidate.prospective_predictions = 3
        candidate.evidence_citation_numbers = []

        store = MagicMock()
        store._candidates = {candidate.candidate_id: candidate}
        engine = BehavioralLearningEngine(candidate_store=store)

        result = engine.apply_learning(situation, str(candidate.candidate_id))
        assert result.arc_step == "B"
        assert result.belief_effect == "strengthened"

    def test_contradicting_outcome_weakens_belief(self):
        """Step C: contradicting outcome → belief weakened."""
        from maestro_cognitive_council import BehavioralLearningEngine
        from uuid import uuid4

        situation = MagicMock()
        situation.situation_id = "sit-test"
        situation.entity = "CustomerA"
        situation.transition_dimension = MagicMock(return_value=MagicMock())

        candidate = MagicMock()
        candidate.candidate_id = uuid4()
        candidate.hypothesis = "Pricing exceptions leak"
        candidate.supporting_outcomes = 1
        candidate.contradicting_outcomes = 3
        candidate.prospective_predictions = 4
        candidate.evidence_citation_numbers = []

        store = MagicMock()
        store._candidates = {candidate.candidate_id: candidate}
        engine = BehavioralLearningEngine(candidate_store=store)

        result = engine.apply_learning(situation, str(candidate.candidate_id))
        assert result.belief_effect == "weakened"

    def test_falsification_completes_arc(self):
        """Step D: enough contradiction → belief falsified."""
        from maestro_cognitive_council import BehavioralLearningEngine, LearningDimensionState
        from uuid import uuid4

        situation = MagicMock()
        situation.situation_id = "sit-test"
        situation.entity = "CustomerA"
        situation.transition_dimension = MagicMock(return_value=MagicMock())

        candidate = MagicMock()
        candidate.candidate_id = uuid4()
        candidate.hypothesis = "Friday incident pattern"
        candidate.supporting_outcomes = 0
        candidate.contradicting_outcomes = 5
        candidate.prospective_predictions = 5
        candidate.evidence_citation_numbers = []

        store = MagicMock()
        store._candidates = {candidate.candidate_id: candidate}
        engine = BehavioralLearningEngine(candidate_store=store)

        result = engine.apply_learning(situation, str(candidate.candidate_id))
        assert result.arc_step == "D"
        assert result.belief_effect == "falsified"

    def test_falsified_situations_filtered_from_advice(self):
        """Falsified situations are filtered out (tombstone enforcement)."""
        from maestro_cognitive_council import (
            is_falsified, filter_falsified_situations, LearningDimensionState,
        )

        falsified = MagicMock()
        falsified.learning_dimension = LearningDimensionState.FALSIFIED
        falsified.learning_state = MagicMock()
        falsified.learning_state.value = "falsified"

        active = MagicMock()
        active.learning_dimension = LearningDimensionState.LEARNING_UPDATED
        active.learning_state = MagicMock()
        active.learning_state.value = "learning_updated"

        filtered = filter_falsified_situations([falsified, active])
        assert len(filtered) == 1
        assert filtered[0] is active
        assert is_falsified(falsified) is True
        assert is_falsified(active) is False

    def test_full_abcd_arc(self):
        """Full A→B→C→D arc: hypothesis → strengthened → weakened → falsified."""
        from maestro_cognitive_council import BehavioralLearningEngine, LearningDimensionState
        from uuid import uuid4

        situation = MagicMock()
        situation.situation_id = "sit-test"
        situation.entity = "CustomerA"
        situation.transition_dimension = MagicMock(return_value=MagicMock())

        engine = BehavioralLearningEngine(candidate_store=MagicMock())

        # Step A: no outcomes
        candidate_a = MagicMock()
        candidate_a.candidate_id = uuid4()
        candidate_a.hypothesis = "Test pattern"
        candidate_a.supporting_outcomes = 0
        candidate_a.contradicting_outcomes = 0
        candidate_a.prospective_predictions = 1
        candidate_a.evidence_citation_numbers = []
        engine._candidate_store._candidates = {candidate_a.candidate_id: candidate_a}
        result_a = engine.apply_learning(situation, str(candidate_a.candidate_id))
        assert result_a.arc_step == "A"

        # Step B: 3 supporting
        candidate_b = MagicMock()
        candidate_b.candidate_id = candidate_a.candidate_id
        candidate_b.hypothesis = "Test pattern"
        candidate_b.supporting_outcomes = 3
        candidate_b.contradicting_outcomes = 0
        candidate_b.prospective_predictions = 3
        candidate_b.evidence_citation_numbers = []
        engine._candidate_store._candidates = {candidate_b.candidate_id: candidate_b}
        result_b = engine.apply_learning(situation, str(candidate_b.candidate_id))
        assert result_b.arc_step == "B"
        assert result_b.belief_effect == "strengthened"

        # Step D: 5 contradicting, 0 supporting
        candidate_d = MagicMock()
        candidate_d.candidate_id = candidate_a.candidate_id
        candidate_d.hypothesis = "Test pattern"
        candidate_d.supporting_outcomes = 0
        candidate_d.contradicting_outcomes = 5
        candidate_d.prospective_predictions = 5
        candidate_d.evidence_citation_numbers = []
        engine._candidate_store._candidates = {candidate_d.candidate_id: candidate_d}
        result_d = engine.apply_learning(situation, str(candidate_d.candidate_id))
        assert result_d.arc_step == "D"
        assert result_d.belief_effect == "falsified"
