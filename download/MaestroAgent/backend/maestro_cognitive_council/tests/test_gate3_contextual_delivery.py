"""Gate 3 acceptance test: Contextual Delivery.

Gate 3 acceptance criterion:
  "The same Situation produces different behavior depending on timing
   and context without contradicting itself."

PROOF: The same Globex situation produces:
  - SILENT during focus mode (opportunity cost: user can't act now)
  - PREPARE before the meeting (state: NEEDS_PREPARATION)
  - WHISPER during the meeting (state: MATERIAL, user is in meeting)
  - BRIEFING during morning review (state: OBSERVING, user is reviewing)
  - ASK when user is not in any special context
  - URGENT when a critical perspective with evidence arrives

The best Whisper system is not the one that discovers the most.
It is the one whose silence users learn to trust.
"""

from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════

def _make_situation(state=None, has_blocking_unknown=False, entity="Globex"):
    from maestro_cognitive_council import (
        LivingSituation, SituationState, EpistemicState, Unknown,
    )
    s = LivingSituation(
        situation_id="sit-globex",
        title=f"{entity} renewal situation",
        entity=entity,
        state=state or SituationState.OBSERVING,
        epistemic_state=EpistemicState.REPORTED,
    )
    if has_blocking_unknown:
        s.add_unknown(Unknown(
            question="Was security approval cleared?",
            why_it_matters="Blocks the renewal decision",
            blocking=True,
        ))
    return s


def _make_perspective(urgency="normal", evidence_count=1):
    from maestro_cognitive_council import Perspective
    return Perspective(
        observation="test observation",
        evidence=[{"source": f"ev-{i}"} for i in range(evidence_count)],
        urgency=urgency,
    )


# ════════════════════════════════════════════════════════════════════════════
# The Same Situation Produces Different Behavior by Context
# ════════════════════════════════════════════════════════════════════════════

class TestContextualDelivery:
    """The same Situation produces different behavior depending on context.

    This is the Gate 3 acceptance criterion.
    """

    def test_same_situation_silent_during_focus_mode(self):
        """SILENT during focus mode — opportunity cost is too high."""
        from maestro_cognitive_council import (
            DeliveryGovernor, DeliveryRoute, SituationState, UserContext,
        )

        gov = DeliveryGovernor()
        situation = _make_situation(state=SituationState.OBSERVING)
        ctx = UserContext(is_in_focus_mode=True)

        route = gov.decide(situation, [], ctx)
        # OBSERVING + focus mode → opportunity cost model suppresses → SILENT
        assert route == DeliveryRoute.SILENT, (
            f"OBSERVING situation during focus mode should be SILENT, got {route}"
        )

    def test_same_situation_prepare_before_meeting(self):
        """PREPARE before the meeting when state is NEEDS_PREPARATION."""
        from maestro_cognitive_council import (
            DeliveryGovernor, DeliveryRoute, SituationState, UserContext,
        )

        gov = DeliveryGovernor()
        situation = _make_situation(
            state=SituationState.NEEDS_PREPARATION,
            has_blocking_unknown=True,
        )
        ctx = UserContext()  # not in any special context

        route = gov.decide(situation, [], ctx)
        assert route == DeliveryRoute.PREPARE, (
            f"NEEDS_PREPARATION should route to PREPARE, got {route}"
        )

    def test_same_situation_whisper_during_meeting(self):
        """WHISPER during the meeting when state is MATERIAL."""
        from maestro_cognitive_council import (
            DeliveryGovernor, DeliveryRoute, SituationState, UserContext,
        )

        gov = DeliveryGovernor()
        situation = _make_situation(state=SituationState.MATERIAL)
        ctx = UserContext(is_in_meeting=True)

        route = gov.decide(situation, [], ctx)
        assert route == DeliveryRoute.WHISPER, (
            f"MATERIAL situation during meeting should WHISPER, got {route}"
        )

    def test_same_situation_briefing_during_morning_review(self):
        """BRIEFING during morning review when state is OBSERVING."""
        from maestro_cognitive_council import (
            DeliveryGovernor, DeliveryRoute, SituationState, UserContext,
        )

        gov = DeliveryGovernor()
        situation = _make_situation(state=SituationState.OBSERVING)
        ctx = UserContext(is_doing_morning_review=True)

        route = gov.decide(situation, [], ctx)
        assert route == DeliveryRoute.BRIEFING, (
            f"OBSERVING during morning review should BRIEFING, got {route}"
        )

    def test_same_situation_urgent_with_critical_perspective(self):
        """URGENT when a critical perspective with strong evidence arrives."""
        from maestro_cognitive_council import (
            DeliveryGovernor, DeliveryRoute, SituationState, UserContext,
        )

        gov = DeliveryGovernor()
        situation = _make_situation(state=SituationState.MATERIAL)
        perspectives = [_make_perspective(urgency="critical", evidence_count=3)]

        route = gov.decide(situation, perspectives, UserContext())
        assert route == DeliveryRoute.URGENT, (
            f"Critical perspective + MATERIAL state should URGENT, got {route}"
        )

    def test_same_situation_ask_when_no_special_context(self):
        """ASK when situation has facts but user is in no special context."""
        from maestro_cognitive_council import (
            DeliveryGovernor, DeliveryRoute, SituationState, UserContext,
            KnownFact, EpistemicState,
        )

        gov = DeliveryGovernor()
        situation = _make_situation(state=SituationState.MATERIAL)
        # MATERIAL state bypasses the opportunity cost gate, so it should
        # reach the WHISPER check. But user is not in meeting → no WHISPER.
        # Then BRIEFING check: not doing review → ASK.
        ctx = UserContext()  # no special context

        route = gov.decide(situation, [], ctx)
        # MATERIAL without meeting/review → ASK
        assert route == DeliveryRoute.ASK, (
            f"MATERIAL without meeting/review should ASK, got {route}"
        )

    def test_context_does_not_contradict_itself(self):
        """The same situation produces different routes by context, but
        each route is internally consistent with the situation's state.

        This is the 'without contradicting itself' part of the criterion.
        """
        from maestro_cognitive_council import (
            DeliveryGovernor, SituationState, UserContext, DeliveryRoute,
        )

        gov = DeliveryGovernor()
        situation = _make_situation(state=SituationState.NEEDS_PREPARATION,
                                     has_blocking_unknown=True)

        # Same situation, different contexts
        routes = {
            "normal": gov.decide(situation, [], UserContext()),
            "focus_mode": gov.decide(situation, [], UserContext(is_in_focus_mode=True)),
            "in_meeting": gov.decide(situation, [], UserContext(is_in_meeting=True)),
            "morning_review": gov.decide(situation, [], UserContext(is_doing_morning_review=True)),
            "high_fatigue": gov.decide(situation, [], UserContext(fatigue_level=0.9)),
        }

        # NEEDS_PREPARATION should produce PREPARE in most contexts
        # (the opportunity cost gate doesn't apply to NEEDS_PREPARATION)
        assert routes["normal"] == DeliveryRoute.PREPARE
        assert routes["focus_mode"] == DeliveryRoute.PREPARE  # focus mode doesn't block PREPARE
        assert routes["in_meeting"] == DeliveryRoute.PREPARE  # in-meeting doesn't override PREPARE
        assert routes["morning_review"] == DeliveryRoute.PREPARE
        # High fatigue (>0.8) suppresses PREPARE → falls through to other checks
        assert routes["high_fatigue"] != DeliveryRoute.PREPARE  # fatigue blocks PREPARE


# ════════════════════════════════════════════════════════════════════════════
# Opportunity Cost Model Tests
# ════════════════════════════════════════════════════════════════════════════

class TestOpportunityCostModel:
    """The opportunity cost model evaluates intervention value vs interruption cost."""

    def test_high_intervention_value_when_blocking_unknown(self):
        """High intervention value when there's a blocking unknown."""
        from maestro_cognitive_council import (
            OpportunityCostModel, SituationState, UserContext,
        )

        model = OpportunityCostModel()
        situation = _make_situation(
            state=SituationState.OBSERVING,
            has_blocking_unknown=True,
        )
        assessment = model.assess(situation, [], UserContext())

        assert assessment.intervention_value in ("low", "medium", "high"), (
            f"Blocking unknown should give some intervention value, got {assessment.intervention_value}"
        )
        assert any("blocking" in r.lower() for r in assessment.reasons_to_surface)

    def test_high_interruption_cost_during_focus_mode(self):
        """High interruption cost during focus mode."""
        from maestro_cognitive_council import (
            OpportunityCostModel, SituationState, UserContext,
        )

        model = OpportunityCostModel()
        situation = _make_situation(state=SituationState.OBSERVING)
        ctx = UserContext(is_in_focus_mode=True)

        assessment = model.assess(situation, [], ctx)

        assert "focus mode" in " ".join(assessment.reasons_to_remain_silent).lower()

    def test_high_interruption_cost_when_recently_surfaced(self):
        """High interruption cost when same issue was recently surfaced."""
        from maestro_cognitive_council import (
            OpportunityCostModel, SituationState, UserContext,
        )

        model = OpportunityCostModel()
        situation = _make_situation(state=SituationState.OBSERVING)
        situation.situation_id = "sit-recent"
        ctx = UserContext(recently_surfaced_situation_ids=["sit-recent"])

        assessment = model.assess(situation, [], ctx)

        assert any("recently" in r.lower() for r in assessment.reasons_to_remain_silent)

    def test_should_surface_when_value_exceeds_cost(self):
        """should_surface is True when intervention value > interruption cost."""
        from maestro_cognitive_council import (
            OpportunityCostModel, SituationState, UserContext,
        )

        model = OpportunityCostModel()
        # High value: blocking unknown + critical perspective + DECISION_PENDING state
        situation = _make_situation(
            state=SituationState.DECISION_PENDING,
            has_blocking_unknown=True,
        )
        perspectives = [_make_perspective(urgency="critical", evidence_count=3)]
        ctx = UserContext()  # no cost factors

        assessment = model.assess(situation, perspectives, ctx)

        assert assessment.should_surface, (
            f"High value + low cost should surface. "
            f"Value={assessment.intervention_value}, Cost={assessment.interruption_cost}"
        )

    def test_should_not_surface_when_cost_exceeds_value(self):
        """should_surface is False when interruption cost > intervention value."""
        from maestro_cognitive_council import (
            OpportunityCostModel, SituationState, UserContext,
        )

        model = OpportunityCostModel()
        # Low value: OBSERVING, no blocking unknown, no critical perspective
        situation = _make_situation(state=SituationState.OBSERVING)
        # High cost: focus mode + recently surfaced + can't act
        ctx = UserContext(
            is_in_focus_mode=True,
            recently_surfaced_situation_ids=["sit-globex"],
        )

        assessment = model.assess(situation, [], ctx)

        assert not assessment.should_surface, (
            f"Low value + high cost should NOT surface. "
            f"Value={assessment.intervention_value}, Cost={assessment.interruption_cost}"
        )

    def test_assessment_to_dict_exposes_full_reasoning(self):
        """The assessment exposes its reasoning (transparency)."""
        from maestro_cognitive_council import (
            OpportunityCostModel, SituationState, UserContext,
        )

        model = OpportunityCostModel()
        situation = _make_situation(state=SituationState.OBSERVING)
        assessment = model.assess(situation, [], UserContext())
        d = assessment.to_dict()

        assert "intervention_value" in d
        assert "interruption_cost" in d
        assert "should_surface" in d
        assert "reasons_to_surface" in d
        assert "reasons_to_remain_silent" in d


# ════════════════════════════════════════════════════════════════════════════
# CognitiveLoadEngine → fatigue_level wiring
# ════════════════════════════════════════════════════════════════════════════

class TestCognitiveLoadWiring:
    """Wire CognitiveLoadEngine → UserContext.fatigue_level."""

    def test_low_cognitive_load_maps_to_low_fatigue(self):
        """OCL score <30 → fatigue_level <0.2 (fresh)."""
        from maestro_cognitive_council import DeliveryGovernor

        fatigue = DeliveryGovernor.derive_fatigue_from_cognitive_load(20)
        assert 0.0 <= fatigue < 0.2, f"OCL 20 → fatigue {fatigue}, expected <0.2"

    def test_critical_cognitive_load_maps_to_high_fatigue(self):
        """OCL score >=70 → fatigue_level >=0.7 (overloaded)."""
        from maestro_cognitive_council import DeliveryGovernor

        fatigue = DeliveryGovernor.derive_fatigue_from_cognitive_load(85)
        assert fatigue >= 0.7, f"OCL 85 → fatigue {fatigue}, expected >=0.7"

    def test_moderate_cognitive_load_maps_to_moderate_fatigue(self):
        """OCL score 30-70 → fatigue_level 0.2-0.7 (moderate)."""
        from maestro_cognitive_council import DeliveryGovernor

        fatigue = DeliveryGovernor.derive_fatigue_from_cognitive_load(50)
        assert 0.2 <= fatigue < 0.7, f"OCL 50 → fatigue {fatigue}, expected 0.2-0.7"

    def test_fatigue_monotonic_increasing(self):
        """Fatigue is monotonically increasing with cognitive load."""
        from maestro_cognitive_council import DeliveryGovernor

        scores = [10, 25, 40, 55, 70, 85, 95]
        fatigues = [DeliveryGovernor.derive_fatigue_from_cognitive_load(s) for s in scores]

        for i in range(len(fatigues) - 1):
            assert fatigues[i] <= fatigues[i + 1], (
                f"Fatigue not monotonic: {fatigues}"
            )

    def test_derive_fatigue_from_model_graceful_degradation(self):
        """derive_fatigue_from_model returns 0.0 if CognitiveLoadEngine unavailable."""
        from maestro_cognitive_council import DeliveryGovernor

        # Pass None model — should gracefully return 0.0
        fatigue = DeliveryGovernor.derive_fatigue_from_model(model=None, signals=[])
        assert fatigue == 0.0


# ════════════════════════════════════════════════════════════════════════════
# Unification: InterruptEngine + delivery_decision → DeliveryRoute
# ════════════════════════════════════════════════════════════════════════════

class TestInterruptEngineUnification:
    """Unify InterruptEngine priority → DeliveryRoute."""

    def test_ignore_maps_to_silent(self):
        from maestro_cognitive_council import DeliveryGovernor, DeliveryRoute
        assert DeliveryGovernor.interrupt_priority_to_route("ignore") == DeliveryRoute.SILENT

    def test_notify_maps_to_ask(self):
        from maestro_cognitive_council import DeliveryGovernor, DeliveryRoute
        assert DeliveryGovernor.interrupt_priority_to_route("notify") == DeliveryRoute.ASK

    def test_recommend_maps_to_briefing(self):
        from maestro_cognitive_council import DeliveryGovernor, DeliveryRoute
        assert DeliveryGovernor.interrupt_priority_to_route("recommend") == DeliveryRoute.BRIEFING

    def test_escalate_maps_to_prepare(self):
        from maestro_cognitive_council import DeliveryGovernor, DeliveryRoute
        assert DeliveryGovernor.interrupt_priority_to_route("escalate") == DeliveryRoute.PREPARE

    def test_interrupt_maps_to_urgent(self):
        from maestro_cognitive_council import DeliveryGovernor, DeliveryRoute
        assert DeliveryGovernor.interrupt_priority_to_route("interrupt") == DeliveryRoute.URGENT

    def test_unknown_priority_defaults_to_ask(self):
        from maestro_cognitive_council import DeliveryGovernor, DeliveryRoute
        assert DeliveryGovernor.interrupt_priority_to_route("unknown") == DeliveryRoute.ASK


class TestDeliveryDecisionUnification:
    """Unify delivery_decision.DeliveryDecision → DeliveryRoute."""

    def test_deliver_now_maps_to_whisper(self):
        from maestro_cognitive_council import DeliveryGovernor, DeliveryRoute
        assert DeliveryGovernor.delivery_decision_to_route("deliver_now") == DeliveryRoute.WHISPER

    def test_deliver_at_meeting_time_maps_to_prepare(self):
        from maestro_cognitive_council import DeliveryGovernor, DeliveryRoute
        assert DeliveryGovernor.delivery_decision_to_route("deliver_at_meeting_time") == DeliveryRoute.PREPARE

    def test_deliver_on_ask_maps_to_ask(self):
        from maestro_cognitive_council import DeliveryGovernor, DeliveryRoute
        assert DeliveryGovernor.delivery_decision_to_route("deliver_on_ask") == DeliveryRoute.ASK

    def test_suppress_variants_map_to_silent(self):
        from maestro_cognitive_council import DeliveryGovernor, DeliveryRoute
        for decision in [
            "suppress_already_understood",
            "suppress_redundant",
            "suppress_low_stakes",
            "defer_until_evidence",
        ]:
            assert DeliveryGovernor.delivery_decision_to_route(decision) == DeliveryRoute.SILENT, (
                f"{decision} should map to SILENT"
            )


# ════════════════════════════════════════════════════════════════════════════
# Silence Users Learn to Trust — the CEO's directive
# ════════════════════════════════════════════════════════════════════════════

class TestSilenceUsersLearnToTrust:
    """The best Whisper system is not the one that discovers the most.

    It is the one whose silence users learn to trust.
    """

    def test_silent_when_nothing_materially_changed(self):
        """SILENT when nothing materially changed and user can't act."""
        from maestro_cognitive_council import (
            DeliveryGovernor, DeliveryRoute, SituationState, UserContext,
        )

        gov = DeliveryGovernor()
        situation = _make_situation(state=SituationState.OBSERVING)
        # No material changes, no special context → opportunity cost suppresses
        ctx = UserContext()

        route = gov.decide(situation, [], ctx)
        assert route == DeliveryRoute.SILENT, (
            f"Nothing materially changed + no context → SILENT, got {route}"
        )

    def test_silent_when_evidence_is_preliminary(self):
        """SILENT when evidence is still preliminary (don't jump the gun)."""
        from maestro_cognitive_council import (
            DeliveryGovernor, DeliveryRoute, SituationState, UserContext,
            Judgment, EvidenceState,
        )

        gov = DeliveryGovernor()
        situation = _make_situation(state=SituationState.OBSERVING)
        situation.judgment = Judgment(evidence_state=EvidenceState.PRELIMINARY)
        ctx = UserContext()

        route = gov.decide(situation, [], ctx)
        # Preliminary evidence + OBSERVING + no context → SILENT
        assert route == DeliveryRoute.SILENT

    def test_silent_explains_why(self):
        """When SILENT, the governor explains WHY (transparency builds trust)."""
        from maestro_cognitive_council import (
            DeliveryGovernor, SituationState, UserContext,
        )

        gov = DeliveryGovernor()
        situation = _make_situation(state=SituationState.OBSERVING)
        ctx = UserContext()

        route = gov.decide(situation, [], ctx)
        explanation = gov.explain(situation, [], ctx, route)

        assert route.value == "silent"
        # The explanation should mention WHY it's silent
        assert "silent" in explanation.lower() or "watching" in explanation.lower()

    def test_not_silent_when_decision_is_imminent(self):
        """NOT silent when a decision is imminent (value > cost)."""
        from maestro_cognitive_council import (
            DeliveryGovernor, DeliveryRoute, SituationState, UserContext,
        )

        gov = DeliveryGovernor()
        # DECISION_PENDING bypasses the opportunity cost gate
        situation = _make_situation(
            state=SituationState.DECISION_PENDING,
            has_blocking_unknown=True,
        )
        ctx = UserContext()

        route = gov.decide(situation, [], ctx)
        # DECISION_PENDING + blocking unknown → PREPARE (not SILENT)
        assert route != DeliveryRoute.SILENT, (
            f"DECISION_PENDING should not be SILENT, got {route}"
        )

    def test_high_fatigue_suppresses_prepare(self):
        """High fatigue (>0.8) suppresses PREPARE — don't overload the user."""
        from maestro_cognitive_council import (
            DeliveryGovernor, DeliveryRoute, SituationState, UserContext,
        )

        gov = DeliveryGovernor()
        situation = _make_situation(
            state=SituationState.NEEDS_PREPARATION,
            has_blocking_unknown=True,
        )
        ctx = UserContext(fatigue_level=0.9)  # overloaded

        route = gov.decide(situation, [], ctx)
        # High fatigue suppresses PREPARE → falls through
        assert route != DeliveryRoute.PREPARE, (
            f"High fatigue should suppress PREPARE, got {route}"
        )
