"""Gate 1 acceptance test: Living Situation evolves correctly across time.

This is the CEO-specified acceptance criterion for Gate 1:
  "new signal → correct situation found → delta computed → state transition
   justified → unknowns updated → no future leakage"

PROOF: The Globex renewal timeline (Day 12 → 40 → 50 → 55 → 59) must
produce correct state transitions with justified reasons at each step.

  DAY 12: Commitment made
    State: DETECTED → OBSERVING
    Unknown: delivery feasibility

  DAY 40: Security approval conditional
    Transition: OBSERVING → MATERIAL
    Reason: new prerequisite threatens commitment feasibility

  DAY 50: Work reported complete
    Transition: remain MATERIAL (completion claim doesn't resolve prereq)
    New unknown: did security approval clear before completion?

  DAY 55: Customer defines availability as production access
    Transition: MATERIAL → NEEDS_PREPARATION
    Reason: external expectation may differ from internal completion state

  DAY 59: Calendar: renewal meeting tomorrow
    Transition: NEEDS_PREPARATION → DECISION_PENDING
    Surface: Prepare

This is the "living quality" test. Without the lifecycle, Situation is
just a sophisticated folder. With the lifecycle, Maestro understands
that organizational reality evolves.
"""

from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════

def _make_signal(
    sig_type: str,
    entity: str,
    text: str,
    signal_id: str,
    days_ago: int = 0,
):
    """Create a mock OEM signal."""
    sig = MagicMock()
    sig.type = MagicMock()
    sig.type.value = sig_type
    sig.entity = entity
    sig.text = text
    sig.signal_id = signal_id
    sig.metadata = {"customer": entity}
    sig.timestamp = datetime.now(timezone.utc) - timedelta(days=days_ago)
    sig.actor = ""
    sig.org_id = "default"
    return sig


# ════════════════════════════════════════════════════════════════════════════
# THE GLOBEX TIMELINE — the Gate 1 acceptance test
# ════════════════════════════════════════════════════════════════════════════

class TestGlobexTimeline:
    """The canonical Globex renewal timeline — Gate 1 acceptance criterion.

    This test proves that one organizational situation changes correctly
    over time. The proof is NOT that every proposed class exists. The
    proof is that this situation evolves through the correct states with
    justified transitions.
    """

    def test_globex_renewal_full_timeline(self):
        """DAY 12 → 40 → 50 → 55 → 59: the full Globex renewal timeline.

        Each step must:
          1. Find the correct situation
          2. Compute the delta
          3. Justify the state transition (reason + evidence)
          4. Update unknowns
        """
        from maestro_cognitive_council import (
            SituationEngine, SituationState, SideState, DeliveryRoute,
        )

        # ── DAY 12: Commitment made ──────────────────────────────────────
        day12_signal = _make_signal(
            "customer.commitment_made", "Globex",
            "Deliver SSO integration by Friday",
            signal_id="sig-day12-commitment",
            days_ago=47,  # 59 - 12 = 47 days ago
        )

        oem = MagicMock()
        oem.signals = [day12_signal]
        engine = SituationEngine(oem_state=oem)

        # With only 1 signal, no situation is detected yet (need 2+)
        situations = engine.detect_situations()
        assert len(situations) == 0, "Need 2+ signals to detect a situation"

        # ── DAY 40: Security approval conditional ────────────────────────
        day40_signal = _make_signal(
            "security.condition", "Globex",
            "Security approval required for SSO — conditional on audit",
            signal_id="sig-day40-security",
            days_ago=19,  # 59 - 40 = 19 days ago
        )

        oem.signals = [day12_signal, day40_signal]
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()

        assert len(situations) == 1
        situation = situations[0]
        assert situation.entity == "Globex"

        # State should be MATERIAL (security prereq threatens commitment)
        assert situation.state == SituationState.MATERIAL, (
            f"Expected MATERIAL after security prereq, got {situation.state}"
        )

        # Should have a blocking unknown about security clearance
        assert situation.has_blocking_unknown(), (
            "Should have a blocking unknown about security clearance"
        )

        # The transition OBSERVING → MATERIAL should be logged with a reason
        transitions = situation.state_history
        assert len(transitions) >= 2, (
            f"Expected ≥2 transitions (DETECTED→OBSERVING + OBSERVING→MATERIAL), "
            f"got {len(transitions)}"
        )
        material_transition = transitions[-1]
        assert material_transition.from_state == SituationState.OBSERVING
        assert material_transition.to_state == SituationState.MATERIAL
        assert "prerequisite" in material_transition.reason.lower() or \
               "feasibility" in material_transition.reason.lower()
        assert material_transition.triggering_evidence_ref is not None

        # ── DAY 50: Work reported complete ───────────────────────────────
        day50_signal = _make_signal(
            "reported_statement", "Globex",
            "SSO implementation reported complete",
            signal_id="sig-day50-complete",
            days_ago=9,  # 59 - 50 = 9 days ago
        )

        delta50 = engine.apply_signal(situation, day50_signal)

        # The completion claim does NOT resolve the security prereq
        # → state should REMAIN MATERIAL (not transition)
        assert situation.state == SituationState.MATERIAL, (
            f"Completion claim should not resolve prereq — expected MATERIAL, "
            f"got {situation.state}"
        )

        # A new unknown should be added: "did security approval clear?"
        new_unknown_questions = delta50.new_unknowns
        assert any("security" in q.lower() for q in new_unknown_questions), (
            f"Expected new unknown about security clearance, got: {new_unknown_questions}"
        )

        # The delta should describe what changed (material change)
        assert delta50.material_change_description, (
            "Delta should describe the material change (completion claim)"
        )

        # ── DAY 55: Customer defines availability as production access ───
        day55_signal = _make_signal(
            "reported_statement", "Globex",
            "Customer defines availability as production access, not just implementation",
            signal_id="sig-day55-expectation",
            days_ago=4,  # 59 - 55 = 4 days ago
        )

        delta55 = engine.apply_signal(situation, day55_signal)

        # External expectation differs → NEEDS_PREPARATION
        assert situation.state == SituationState.NEEDS_PREPARATION, (
            f"External expectation mismatch → expected NEEDS_PREPARATION, "
            f"got {situation.state}"
        )

        # The transition must be justified
        transition55 = delta55.transition
        assert transition55 is not None, "Expected a state transition on Day 55"
        assert transition55.from_state == SituationState.MATERIAL
        assert transition55.to_state == SituationState.NEEDS_PREPARATION
        assert "expectation" in transition55.reason.lower(), (
            f"Transition reason should mention expectation, got: {transition55.reason}"
        )

        # ── DAY 59: Calendar: renewal meeting tomorrow ───────────────────
        day59_signal = _make_signal(
            "calendar.meeting", "Globex",
            "Globex renewal meeting scheduled for tomorrow",
            signal_id="sig-day59-meeting",
            days_ago=0,  # today
        )

        delta59 = engine.apply_signal(situation, day59_signal)

        # Imminent meeting → DECISION_PENDING + delivery route PREPARE
        assert situation.state == SituationState.DECISION_PENDING, (
            f"Imminent meeting → expected DECISION_PENDING, got {situation.state}"
        )
        assert situation.recommended_delivery == DeliveryRoute.PREPARE, (
            f"Imminent meeting → expected PREPARE delivery, got {situation.recommended_delivery}"
        )

        transition59 = delta59.transition
        assert transition59 is not None
        assert transition59.from_state == SituationState.NEEDS_PREPARATION
        assert transition59.to_state == SituationState.DECISION_PENDING
        assert "meeting" in transition59.reason.lower()

        # ── Verify the full state history is correct ─────────────────────
        history = situation.state_history
        # DETECTED → OBSERVING (initial), OBSERVING → MATERIAL (Day 40),
        # MATERIAL → NEEDS_PREPARATION (Day 55), NEEDS_PREPARATION → DECISION_PENDING (Day 59)
        assert len(history) >= 4, (
            f"Expected ≥4 transitions in history, got {len(history)}: "
            f"{[t.from_state.value + '→' + t.to_state.value for t in history]}"
        )

        # Verify the chain
        states = [t.to_state for t in history]
        assert SituationState.OBSERVING in states
        assert SituationState.MATERIAL in states
        assert SituationState.NEEDS_PREPARATION in states
        assert SituationState.DECISION_PENDING in states


# ════════════════════════════════════════════════════════════════════════════
# No future leakage — situations don't bleed across entities
# ════════════════════════════════════════════════════════════════════════════

class TestNoFutureLeakage:
    """Situations must NOT bleed across entities.

    A signal for Globex must not affect a situation for Initech.
    This is the "no future leakage" acceptance criterion.
    """

    def test_signal_only_affects_matching_entity(self):
        """A signal for entity A does not affect entity B's situation."""
        from maestro_cognitive_council import SituationEngine, SituationState

        globex_signal = _make_signal(
            "customer.commitment_made", "Globex",
            "Deliver SSO", signal_id="sig-globex-1", days_ago=10,
        )
        globex_signal2 = _make_signal(
            "security.condition", "Globex",
            "Security approval required", signal_id="sig-globex-2", days_ago=8,
        )
        initech_signal = _make_signal(
            "customer.commitment_made", "Initech",
            "Deliver API integration", signal_id="sig-initech-1", days_ago=5,
        )
        initech_signal2 = _make_signal(
            "customer.commitment_made", "Initech",
            "Send pricing", signal_id="sig-initech-2", days_ago=3,
        )

        oem = MagicMock()
        oem.signals = [globex_signal, globex_signal2, initech_signal, initech_signal2]
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()

        # Should have 2 situations (Globex + Initech)
        assert len(situations) == 2
        globex_sit = next(s for s in situations if s.entity == "Globex")
        initech_sit = next(s for s in situations if s.entity == "Initech")

        # Apply a Globex-specific signal
        globex_new = _make_signal(
            "reported_statement", "Globex",
            "Customer defines availability as production access",
            signal_id="sig-globex-3", days_ago=1,
        )
        delta = engine.apply_signal(globex_sit, globex_new)

        # Globex should transition to NEEDS_PREPARATION
        assert globex_sit.state == SituationState.NEEDS_PREPARATION

        # Initech should be UNAFFECTED
        assert initech_sit.state != SituationState.NEEDS_PREPARATION, (
            "Initech situation should not be affected by a Globex signal"
        )

        # Initech's evidence_refs should NOT contain the Globex signal
        assert "sig-globex-3" not in initech_sit.evidence_refs, (
            "Globex signal leaked into Initech situation"
        )

    def test_get_situations_by_entity_is_isolated(self):
        """get_situations_by_entity returns only that entity's situations."""
        from maestro_cognitive_council import SituationEngine

        globex_sig1 = _make_signal("customer.commitment_made", "Globex", "A", "g1", days_ago=10)
        globex_sig2 = _make_signal("customer.commitment_made", "Globex", "B", "g2", days_ago=8)
        initech_sig1 = _make_signal("customer.commitment_made", "Initech", "C", "i1", days_ago=5)
        initech_sig2 = _make_signal("customer.commitment_made", "Initech", "D", "i2", days_ago=3)

        oem = MagicMock()
        oem.signals = [globex_sig1, globex_sig2, initech_sig1, initech_sig2]
        engine = SituationEngine(oem_state=oem)
        engine.detect_situations()

        globex_situations = engine.get_situations_by_entity("Globex")
        initech_situations = engine.get_situations_by_entity("Initech")

        assert all(s.entity == "Globex" for s in globex_situations)
        assert all(s.entity == "Initech" for s in initech_situations)
        assert len(globex_situations) == 1
        assert len(initech_situations) == 1


# ════════════════════════════════════════════════════════════════════════════
# Thin references — Situation holds refs, not copies
# ════════════════════════════════════════════════════════════════════════════

class TestThinReferences:
    """Situation holds REFERENCES to OEM objects, not copies.

    CEO rule #1: "Situation organizes cognition. It does not duplicate
    organizational memory. The OEM remains the source of record."
    """

    def test_situation_uses_refs_not_copies(self):
        """LivingSituation has _refs fields, not _data fields."""
        from maestro_cognitive_council import LivingSituation

        s = LivingSituation(
            situation_id="sit-1",
            title="Test",
            entity="TestCorp",
        )
        d = s.to_dict()

        # Should have ref fields (NOT copy fields)
        assert "evidence_refs" in d
        assert "commitment_refs" in d
        assert "decision_refs" in d
        assert "meeting_refs" in d
        assert "entity_refs" in d
        assert "hypothesis_refs" in d
        assert "relationship_refs" in d

        # Should NOT have copy fields (old design)
        assert "commitments" not in d, "commitments should be commitment_refs"
        assert "decisions" not in d, "decisions should be decision_refs"
        assert "related_meetings" not in d, "related_meetings should be meeting_refs"
        assert "evidence_ids" not in d, "evidence_ids should be evidence_refs"

    def test_refs_are_strings_not_objects(self):
        """Refs are string IDs, not the actual OEM objects."""
        from maestro_cognitive_council import SituationEngine

        sig1 = _make_signal("customer.commitment_made", "TestCorp", "Deliver X", "ev-1", days_ago=10)
        sig2 = _make_signal("customer.commitment_made", "TestCorp", "Deliver Y", "ev-2", days_ago=8)

        oem = MagicMock()
        oem.signals = [sig1, sig2]
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()

        s = situations[0]
        # evidence_refs should be string IDs (the signal_id), not the signal objects
        assert all(isinstance(r, str) for r in s.evidence_refs)
        assert "ev-1" in s.evidence_refs
        assert "ev-2" in s.evidence_refs


# ════════════════════════════════════════════════════════════════════════════
# State transition justification — every transition has a reason
# ════════════════════════════════════════════════════════════════════════════

class TestTransitionJustification:
    """Every state transition must be JUSTIFIED (reason + evidence)."""

    def test_every_transition_has_reason(self):
        """Every StateTransition in state_history has a non-empty reason."""
        from maestro_cognitive_council import SituationEngine

        sig1 = _make_signal("customer.commitment_made", "TestCorp", "Deliver SSO", "ev-1", days_ago=10)
        sig2 = _make_signal("security.condition", "TestCorp", "Security approval required", "ev-2", days_ago=8)

        oem = MagicMock()
        oem.signals = [sig1, sig2]
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()

        s = situations[0]
        for transition in s.state_history:
            assert transition.reason, (
                f"Transition {transition.from_state}→{transition.to_state} has no reason"
            )
            assert len(transition.reason) > 10, (
                f"Transition reason too short: {transition.reason}"
            )

    def test_transition_has_triggering_evidence(self):
        """Every transition (except DETECTED→OBSERVING) has a triggering evidence ref."""
        from maestro_cognitive_council import SituationEngine, SituationState

        sig1 = _make_signal("customer.commitment_made", "TestCorp", "Deliver SSO", "ev-1", days_ago=10)
        sig2 = _make_signal("security.condition", "TestCorp", "Security approval required", "ev-2", days_ago=8)

        oem = MagicMock()
        oem.signals = [sig1, sig2]
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()

        s = situations[0]
        for transition in s.state_history:
            # The initial DETECTED→OBSERVING transition may not have triggering evidence,
            # but all subsequent transitions must.
            if transition.from_state != SituationState.DETECTED:
                assert transition.triggering_evidence_ref, (
                    f"Transition {transition.from_state}→{transition.to_state} "
                    f"has no triggering evidence"
                )

    def test_side_states_added_during_transition(self):
        """Side states (BLOCKED, DISPUTED) are added when appropriate."""
        from maestro_cognitive_council import SituationEngine, SideState

        sig1 = _make_signal("customer.commitment_made", "TestCorp", "Deliver SSO", "ev-1", days_ago=10)
        sig2 = _make_signal("security.condition", "TestCorp", "Security approval required", "ev-2", days_ago=8)

        oem = MagicMock()
        oem.signals = [sig1, sig2]
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()

        s = situations[0]
        # Should have BLOCKED side state (security prereq is blocking)
        assert s.has_side_state(SideState.BLOCKED), (
            "Should have BLOCKED side state due to blocking unknown"
        )

    def test_unknown_resolution_logged(self):
        """When an unknown is resolved, it's marked resolved with evidence."""
        from maestro_cognitive_council import SituationEngine

        sig1 = _make_signal("customer.commitment_made", "TestCorp", "Deliver SSO", "ev-1", days_ago=10)
        sig2 = _make_signal("security.condition", "TestCorp", "Security approval required", "ev-2", days_ago=8)

        oem = MagicMock()
        oem.signals = [sig1, sig2]
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()
        s = situations[0]

        # Initially has a blocking unknown about security
        assert s.has_blocking_unknown()

        # Apply a signal that resolves the security unknown
        resolve_sig = _make_signal(
            "security.resolution", "TestCorp",
            "Security approval cleared and approved",
            signal_id="ev-3-resolve", days_ago=1,
        )
        delta = engine.apply_signal(s, resolve_sig)

        # The unknown should be resolved
        assert any("security" in q.lower() for q in delta.resolved_unknowns), (
            "Security unknown should be resolved by the approval signal"
        )
        assert not s.has_blocking_unknown(), (
            "Should no longer have a blocking unknown after resolution"
        )


# ════════════════════════════════════════════════════════════════════════════
# The full Globex resolution arc (extended timeline)
# ════════════════════════════════════════════════════════════════════════════

class TestGlobexResolutionArc:
    """The extended Globex arc: Day 12 → 40 → 50 → 55 → 59 → meeting → resolved.

    This tests the full lifecycle from detection to resolution.
    """

    def test_full_arc_to_resolution(self):
        """The Globex situation resolves when the meeting concludes."""
        from maestro_cognitive_council import (
            SituationEngine, SituationState, DeliveryRoute,
        )

        # Build the situation through Day 59 (as in the main test)
        sigs = [
            _make_signal("customer.commitment_made", "Globex", "Deliver SSO", "s1", days_ago=47),
            _make_signal("security.condition", "Globex", "Security approval required", "s2", days_ago=19),
        ]
        oem = MagicMock()
        oem.signals = sigs
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()
        s = situations[0]

        # Day 50: completion claim (remain MATERIAL)
        engine.apply_signal(s, _make_signal("reported_statement", "Globex", "Implementation complete", "s3", days_ago=9))

        # Day 55: expectation mismatch (→ NEEDS_PREPARATION)
        engine.apply_signal(s, _make_signal("reported_statement", "Globex", "Customer defines availability as production access", "s4", days_ago=4))

        # Day 59: meeting tomorrow (→ DECISION_PENDING)
        engine.apply_signal(s, _make_signal("calendar.meeting", "Globex", "Renewal meeting tomorrow", "s5", days_ago=0))

        assert s.state == SituationState.DECISION_PENDING

        # Meeting starts (→ ACTION_IN_PROGRESS)
        delta_meeting = engine.apply_signal(s, _make_signal("meeting.started", "Globex", "Meeting started", "s6", days_ago=0))
        assert s.state == SituationState.ACTION_IN_PROGRESS
        assert s.recommended_delivery == DeliveryRoute.WHISPER

        # Meeting ends (→ AWAITING_OUTCOME)
        delta_end = engine.apply_signal(s, _make_signal("meeting.ended", "Globex", "Meeting concluded", "s7", days_ago=0))
        assert s.state == SituationState.AWAITING_OUTCOME

        # Outcome: customer accepted phased activation (→ RESOLVED)
        delta_resolved = engine.apply_signal(s, _make_signal("outcome.positive", "Globex", "Customer accepted phased activation — renewed", "s8", days_ago=0))
        assert s.state == SituationState.RESOLVED
        assert s.resolved_at is not None

        # Verify the full state history
        states = [t.to_state for t in s.state_history]
        expected_chain = [
            SituationState.OBSERVING,
            SituationState.MATERIAL,
            SituationState.NEEDS_PREPARATION,
            SituationState.DECISION_PENDING,
            SituationState.ACTION_IN_PROGRESS,
            SituationState.AWAITING_OUTCOME,
            SituationState.RESOLVED,
        ]
        for expected in expected_chain:
            assert expected in states, (
                f"Expected {expected.value} in state history, got: "
                f"{[s.value for s in states]}"
            )
