"""Tests for the 4-Dimensional State Model — Gate 0 Task 2.

Per the CEO audit directive: the single SituationState enum mixes
epistemic maturity, operational lifecycle, delivery eligibility, and
learning status. This creates impossible state combinations when learning
closes (can a situation be RESOLVED and LEARNING simultaneously? The
single enum says no, but conceptually yes).

The 4 orthogonal dimensions:
  epistemic_state:   what do we know? (evidence-backed)
  operational_state: what's happening operationally? (lifecycle)
  delivery_state:    how should we surface this? (delivery eligibility)
  learning_state:    what's the learning status? (hypothesis testing)

Globex can simultaneously be:
  epistemic_state = contested
  operational_state = decision_pending
  delivery_state = prepare_eligible
  learning_state = hypothesis_created

Also tests the enriched DimensionTransition receipt (dimension, rule_id,
unknowns_added, unknowns_resolved, delivery_effect).
"""

from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from datetime import datetime, timezone
import pytest


# ════════════════════════════════════════════════════════════════════════════
# 4-Dimensional State Enums
# ════════════════════════════════════════════════════════════════════════════

class TestEpistemicDimensionState:
    """Dimension 1: What do we know? (evidence-backed)"""

    def test_5_states_exist(self):
        from maestro_cognitive_council import EpistemicDimensionState
        states = [s.value for s in EpistemicDimensionState]
        assert set(states) == {"preliminary", "supported", "contested", "insufficient", "resolved"}

    def test_states_are_orthogonal_to_operational(self):
        """Epistemic states don't overlap with operational states."""
        from maestro_cognitive_council import EpistemicDimensionState, OperationalDimensionState
        epistemic_vals = {s.value for s in EpistemicDimensionState}
        operational_vals = {s.value for s in OperationalDimensionState}
        assert epistemic_vals.isdisjoint(operational_vals), (
            "Epistemic and operational states must be orthogonal (no overlap)"
        )


class TestOperationalDimensionState:
    """Dimension 2: What's happening operationally? (lifecycle)"""

    def test_5_states_exist(self):
        from maestro_cognitive_council import OperationalDimensionState
        states = [s.value for s in OperationalDimensionState]
        assert set(states) == {
            "observing", "decision_pending", "action_in_progress",
            "awaiting_outcome", "closed",
        }


class TestDeliveryDimensionState:
    """Dimension 3: How should we surface this? (delivery eligibility)"""

    def test_5_states_exist(self):
        from maestro_cognitive_council import DeliveryDimensionState
        states = [s.value for s in DeliveryDimensionState]
        assert set(states) == {
            "silent", "briefing_eligible", "whisper_eligible",
            "prepare_eligible", "urgent",
        }


class TestLearningDimensionState:
    """Dimension 4: What's the learning status? (hypothesis testing)"""

    def test_6_states_exist(self):
        from maestro_cognitive_council import LearningDimensionState
        states = [s.value for s in LearningDimensionState]
        assert set(states) == {
            "none", "hypothesis_created", "prospectively_testing",
            "outcome_pending", "learning_updated", "falsified",
        }


# ════════════════════════════════════════════════════════════════════════════
# LivingSituation has 4 dimensions
# ════════════════════════════════════════════════════════════════════════════

class TestLivingSituationHas4Dimensions:
    """LivingSituation has all 4 orthogonal state dimensions."""

    def test_situation_has_epistemic_dimension(self):
        from maestro_cognitive_council import LivingSituation, EpistemicDimensionState
        s = LivingSituation(situation_id="s1", title="test", entity="X")
        assert hasattr(s, "epistemic_dimension")
        assert isinstance(s.epistemic_dimension, EpistemicDimensionState)
        assert s.epistemic_dimension == EpistemicDimensionState.INSUFFICIENT  # default

    def test_situation_has_operational_dimension(self):
        from maestro_cognitive_council import LivingSituation, OperationalDimensionState
        s = LivingSituation(situation_id="s1", title="test", entity="X")
        assert hasattr(s, "operational_dimension")
        assert isinstance(s.operational_dimension, OperationalDimensionState)
        assert s.operational_dimension == OperationalDimensionState.OBSERVING  # default

    def test_situation_has_delivery_dimension(self):
        from maestro_cognitive_council import LivingSituation, DeliveryDimensionState
        s = LivingSituation(situation_id="s1", title="test", entity="X")
        assert hasattr(s, "delivery_dimension")
        assert isinstance(s.delivery_dimension, DeliveryDimensionState)
        assert s.delivery_dimension == DeliveryDimensionState.SILENT  # default

    def test_situation_has_learning_dimension(self):
        from maestro_cognitive_council import LivingSituation, LearningDimensionState
        s = LivingSituation(situation_id="s1", title="test", entity="X")
        assert hasattr(s, "learning_dimension")
        assert isinstance(s.learning_dimension, LearningDimensionState)
        assert s.learning_dimension == LearningDimensionState.NONE  # default

    def test_dimensions_in_to_dict(self):
        """All 4 dimensions are exposed in to_dict()."""
        from maestro_cognitive_council import LivingSituation
        s = LivingSituation(situation_id="s1", title="test", entity="X")
        d = s.to_dict()
        assert "epistemic_dimension" in d
        assert "operational_dimension" in d
        assert "delivery_dimension" in d
        assert "learning_dimension" in d
        assert "dimension_transitions" in d


# ════════════════════════════════════════════════════════════════════════════
# Dimension Transitions (enriched receipts)
# ════════════════════════════════════════════════════════════════════════════

class TestDimensionTransitions:
    """Every dimension transition produces an enriched receipt.

    Per the CEO audit directive: "Every transition should produce a
    first-class transition receipt" with dimension, rule_id, unknowns,
    and delivery_effect.
    """

    def test_transition_dimension_logs_receipt(self):
        """transition_dimension() logs a DimensionTransition receipt."""
        from maestro_cognitive_council import LivingSituation, OperationalDimensionState
        s = LivingSituation(situation_id="s1", title="test", entity="X")

        transition = s.transition_dimension(
            dimension="operational",
            new_state="decision_pending",
            reason="Renewal meeting is within 24 hours",
            triggering_event_refs=["ev-meeting-1"],
            rule_id="operational.meeting_imminent",
            delivery_effect="Prepare surface may now be generated",
        )

        assert transition.dimension == "operational"
        assert transition.previous_state == "observing"
        assert transition.new_state == "decision_pending"
        assert transition.reason == "Renewal meeting is within 24 hours"
        assert transition.triggering_event_refs == ["ev-meeting-1"]
        assert transition.rule_id == "operational.meeting_imminent"
        assert transition.delivery_effect == "Prepare surface may now be generated"

        # The transition is logged
        assert len(s.dimension_transitions) == 1
        assert s.operational_dimension == OperationalDimensionState.DECISION_PENDING

    def test_transition_tracks_unknowns_added_and_resolved(self):
        """The transition receipt tracks unknowns added and resolved."""
        from maestro_cognitive_council import LivingSituation
        s = LivingSituation(situation_id="s1", title="test", entity="X")

        transition = s.transition_dimension(
            dimension="epistemic",
            new_state="contested",
            reason="New evidence conflicts with existing claim",
            triggering_event_refs=["ev-conflict-1"],
            rule_id="epistemic.conflict_detected",
            unknowns_added=["Which claim is more reliable?"],
            unknowns_resolved=["Is the original claim accurate?"],
            decision_boundary_changed=True,
        )

        assert transition.unknowns_added == ["Which claim is more reliable?"]
        assert transition.unknowns_resolved == ["Is the original claim accurate?"]
        assert transition.decision_boundary_changed is True

    def test_no_change_transition_logged_with_reason(self):
        """If the state doesn't actually change, the receipt says so."""
        from maestro_cognitive_council import LivingSituation
        s = LivingSituation(situation_id="s1", title="test", entity="X")
        # Default operational_dimension is OBSERVING
        transition = s.transition_dimension(
            dimension="operational",
            new_state="observing",  # same as default
            reason="No change",
        )
        assert transition.previous_state == "observing"
        assert transition.new_state == "observing"
        assert "no change" in transition.reason.lower()

    def test_get_dimension_transitions_filtered_by_dimension(self):
        """get_dimension_transitions returns only transitions for that dimension."""
        from maestro_cognitive_council import LivingSituation
        s = LivingSituation(situation_id="s1", title="test", entity="X")

        s.transition_dimension("epistemic", "contested", "conflict")
        s.transition_dimension("operational", "decision_pending", "meeting imminent")
        s.transition_dimension("delivery", "prepare_eligible", "prepare needed")

        epistemic_transitions = s.get_dimension_transitions("epistemic")
        operational_transitions = s.get_dimension_transitions("operational")
        delivery_transitions = s.get_dimension_transitions("delivery")

        assert len(epistemic_transitions) == 1
        assert len(operational_transitions) == 1
        assert len(delivery_transitions) == 1
        assert all(t.dimension == "epistemic" for t in epistemic_transitions)

    def test_get_latest_dimension_transition(self):
        """get_latest_dimension_transition returns the most recent for a dimension."""
        from maestro_cognitive_council import LivingSituation
        s = LivingSituation(situation_id="s1", title="test", entity="X")

        s.transition_dimension("operational", "decision_pending", "first")
        s.transition_dimension("operational", "action_in_progress", "second")

        latest = s.get_latest_dimension_transition("operational")
        assert latest is not None
        assert latest.new_state == "action_in_progress"
        assert latest.reason == "second"


# ════════════════════════════════════════════════════════════════════════════
# Orthogonality — the key property
# ════════════════════════════════════════════════════════════════════════════

class TestOrthogonality:
    """The 4 dimensions are orthogonal — they can vary independently.

    This is the key property the CEO audit directive identified as missing
    from the single-enum design. Globex can simultaneously be:
      epistemic = contested
      operational = decision_pending
      delivery = prepare_eligible
      learning = hypothesis_created
    """

    def test_globex_simultaneous_4_dimensions(self):
        """Globex can be in 4 different states across 4 dimensions simultaneously."""
        from maestro_cognitive_council import (
            LivingSituation,
            EpistemicDimensionState,
            OperationalDimensionState,
            DeliveryDimensionState,
            LearningDimensionState,
        )

        s = LivingSituation(situation_id="sit-globex", title="Globex renewal", entity="Globex")

        # Set all 4 dimensions independently
        s.transition_dimension("epistemic", "contested", "Security prereq conflicts with completion claim")
        s.transition_dimension("operational", "decision_pending", "Renewal meeting imminent")
        s.transition_dimension("delivery", "prepare_eligible", "Preparation needed before meeting")
        s.transition_dimension("learning", "hypothesis_created", "Hypothesis: expectation mismatches cause renewal risk")

        # All 4 dimensions are different — this is impossible with a single enum
        assert s.epistemic_dimension == EpistemicDimensionState.CONTESTED
        assert s.operational_dimension == OperationalDimensionState.DECISION_PENDING
        assert s.delivery_dimension == DeliveryDimensionState.PREPARE_ELIGIBLE
        assert s.learning_dimension == LearningDimensionState.HYPOTHESIS_CREATED

    def test_resolved_and_learning_simultaneously(self):
        """A situation can be operationally CLOSED but still LEARNING.

        This is the impossible-state-combination the audit identified:
        with a single enum, RESOLVED and LEARNING are mutually exclusive.
        With 4 dimensions, a situation can be operationally closed while
        the learning loop is still processing the outcome.
        """
        from maestro_cognitive_council import (
            LivingSituation,
            OperationalDimensionState,
            LearningDimensionState,
        )

        s = LivingSituation(situation_id="s1", title="test", entity="X")

        # Operationally closed (the situation concluded)
        s.transition_dimension("operational", "closed", "Situation concluded")
        # But learning is still pending (feeding to learning loop)
        s.transition_dimension("learning", "outcome_pending", "Awaiting learning loop processing")

        # Both are true simultaneously — impossible with a single enum
        assert s.operational_dimension == OperationalDimensionState.CLOSED
        assert s.learning_dimension == LearningDimensionState.OUTCOME_PENDING

    def test_contested_but_silent(self):
        """A situation can be epistemically CONTESTED but delivery SILENT.

        The opportunity cost model may determine that even though the
        evidence is contested, the user can't act on it now — so delivery
        is SILENT. With a single enum, this combination is impossible.
        """
        from maestro_cognitive_council import (
            LivingSituation,
            EpistemicDimensionState,
            DeliveryDimensionState,
        )

        s = LivingSituation(situation_id="s1", title="test", entity="X")
        s.transition_dimension("epistemic", "contested", "Evidence conflicts")
        s.transition_dimension("delivery", "silent", "User in focus mode — suppress")

        assert s.epistemic_dimension == EpistemicDimensionState.CONTESTED
        assert s.delivery_dimension == DeliveryDimensionState.SILENT


# ════════════════════════════════════════════════════════════════════════════
# Backward Compatibility — the legacy single-enum state still works
# ════════════════════════════════════════════════════════════════════════════

class TestBackwardCompatibility:
    """The legacy single-enum `state` field still works alongside the 4 dimensions.

    The 4 dimensions are the new primary representation, but the legacy
    `state` field is retained for backward compatibility with Gates 1-3
    tests (Globex timeline, OAuth scenario, contextual delivery).
    """

    def test_legacy_state_field_still_exists(self):
        from maestro_cognitive_council import LivingSituation, SituationState
        s = LivingSituation(situation_id="s1", title="test", entity="X")
        assert hasattr(s, "state")
        assert s.state == SituationState.DETECTED  # default

    def test_legacy_transition_to_still_works(self):
        from maestro_cognitive_council import LivingSituation, SituationState
        s = LivingSituation(situation_id="s1", title="test", entity="X")
        s.transition_to(SituationState.MATERIAL, reason="test")
        assert s.state == SituationState.MATERIAL

    def test_legacy_state_history_still_logged(self):
        from maestro_cognitive_council import LivingSituation, SituationState
        s = LivingSituation(situation_id="s1", title="test", entity="X")
        s.transition_to(SituationState.MATERIAL, reason="test")
        assert len(s.state_history) == 1
