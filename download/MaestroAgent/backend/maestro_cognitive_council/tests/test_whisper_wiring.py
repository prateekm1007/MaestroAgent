"""Tests for Surface 4: Whisper → Delivery Governor.

Proves the Whisper surface is wired to the Cognitive Council's Delivery
Governor (Gate 3) with the opportunity cost model + 4D state.

Key properties tested:
  1. Whisper takes a LivingSituation (not raw signals)
  2. Uses the Delivery Governor's decide() (not the old decide_delivery())
  3. Applies the opportunity cost model (intervention value vs interruption cost)
  4. References situation.evidence_refs (not copies)
  5. Explains WHY it's silent (transparency builds trust)
  6. Batch routing applies fatigue caps
"""

from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from datetime import datetime, timezone
import pytest


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════

def _make_situation(state=None, has_blocking_unknown=False, entity="CustomerA",
                     material_changes=None, judgment=None):
    from maestro_cognitive_council import (
        LivingSituation, SituationState, EpistemicState, Unknown, Judgment,
    )
    s = LivingSituation(
        situation_id="sit-test",
        title=f"{entity} situation",
        entity=entity,
        state=state or SituationState.OBSERVING,
        epistemic_state=EpistemicState.REPORTED,
    )
    if has_blocking_unknown:
        s.add_unknown(Unknown(
            question="Was security approval cleared?",
            why_it_matters="Blocks the decision",
            blocking=True,
        ))
    if material_changes:
        s.material_changes = material_changes
    if judgment:
        s.judgment = judgment
    return s


# ════════════════════════════════════════════════════════════════════════════
# Whisper → Delivery Governor
# ════════════════════════════════════════════════════════════════════════════

class TestWhisperSituationBridge:
    """Whisper takes a LivingSituation and routes through the Delivery Governor."""

    def test_whisper_uses_delivery_governor(self):
        """Whisper uses the Delivery Governor's decide() — not the old decide_delivery()."""
        from maestro_cognitive_council import WhisperSituationBridge, SituationState

        situation = _make_situation(state=SituationState.NEEDS_PREPARATION,
                                     has_blocking_unknown=True)
        bridge = WhisperSituationBridge()

        result = bridge.from_situation(situation)

        # Should have a delivery route from the Delivery Governor
        assert result.delivery_route in ("silent", "ask", "briefing", "whisper", "prepare", "urgent")
        # NEEDS_PREPARATION + blocking unknown → PREPARE
        assert result.delivery_route == "prepare"

    def test_whisper_takes_situation_not_signals(self):
        """Whisper takes a LivingSituation as primary input — not raw signals."""
        from maestro_cognitive_council import WhisperSituationBridge

        situation = _make_situation()
        bridge = WhisperSituationBridge()

        result = bridge.from_situation(situation)

        assert result.situation_id == situation.situation_id
        assert result.situation_title == situation.title
        assert result.entity == situation.entity

    def test_whisper_applies_opportunity_cost_model(self):
        """Whisper applies the opportunity cost model (intervention value vs interruption cost)."""
        from maestro_cognitive_council import WhisperSituationBridge, SituationState

        situation = _make_situation(state=SituationState.NEEDS_PREPARATION,
                                     has_blocking_unknown=True)
        bridge = WhisperSituationBridge()

        result = bridge.from_situation(situation)

        # The opportunity cost assessment should be included
        assert result.opportunity_cost is not None
        assert "intervention_value" in result.opportunity_cost
        assert "interruption_cost" in result.opportunity_cost
        assert "should_surface" in result.opportunity_cost

    def test_whisper_references_evidence_not_copies(self):
        """Whisper references situation.evidence_refs — not copies."""
        from maestro_cognitive_council import WhisperSituationBridge, SituationState

        situation = _make_situation(state=SituationState.NEEDS_PREPARATION,
                                     has_blocking_unknown=True)
        situation.evidence_refs = ["ev-1", "ev-2", "ev-3"]
        bridge = WhisperSituationBridge()

        result = bridge.from_situation(situation)

        assert result.evidence_refs == ["ev-1", "ev-2", "ev-3"]
        # Whispers should also reference evidence_refs (strings, not objects)
        for w in result.whispers:
            assert all(isinstance(r, str) for r in w.get("evidence_refs", []))

    def test_whisper_explains_why_silent(self):
        """When SILENT, Whisper explains WHY — transparency builds trust."""
        from maestro_cognitive_council import (
            WhisperSituationBridge, SituationState, UserContext,
        )

        # OBSERVING situation with no blocking unknown + focus mode → SILENT
        situation = _make_situation(state=SituationState.OBSERVING)
        bridge = WhisperSituationBridge()

        result = bridge.from_situation(
            situation,
            user_context=UserContext(is_in_focus_mode=True),
        )

        if result.delivery_route == "silent":
            assert result.suppression_reason  # non-empty
            assert "silent" in result.delivery_explanation.lower() or \
                   "watching" in result.delivery_explanation.lower()

    def test_whisper_generates_whispers_when_not_silent(self):
        """When not SILENT, Whisper generates whisper cards from the Situation."""
        from maestro_cognitive_council import WhisperSituationBridge, SituationState

        situation = _make_situation(
            state=SituationState.NEEDS_PREPARATION,
            has_blocking_unknown=True,
            material_changes=["Security prerequisite threatens commitment"],
        )
        bridge = WhisperSituationBridge()

        result = bridge.from_situation(situation)

        # PREPARE route → should have whispers
        assert result.delivery_route == "prepare"
        assert len(result.whispers) > 0

        # Whispers should reference the situation
        for w in result.whispers:
            assert w["situation_id"] == situation.situation_id

    def test_whisper_includes_unknowns(self):
        """Whisper surfaces unknowns from the Situation."""
        from maestro_cognitive_council import WhisperSituationBridge, SituationState

        situation = _make_situation(
            state=SituationState.NEEDS_PREPARATION,
            has_blocking_unknown=True,
        )
        bridge = WhisperSituationBridge()

        result = bridge.from_situation(situation)

        # At least one whisper should surface the blocking unknown
        all_unknowns = []
        for w in result.whispers:
            all_unknowns.extend(w.get("unknowns_surfaced", []))
        assert any("security" in u.lower() for u in all_unknowns) or \
               any("approval" in u.lower() for u in all_unknowns)

    def test_whisper_to_dict(self):
        """WhisperResult exposes full structure in to_dict()."""
        from maestro_cognitive_council import WhisperSituationBridge

        situation = _make_situation()
        bridge = WhisperSituationBridge()
        result = bridge.from_situation(situation)
        d = result.to_dict()

        required = [
            "situation_id", "situation_title", "entity",
            "delivery_route", "delivery_explanation",
            "opportunity_cost", "whispers", "suppression_reason",
            "evidence_refs", "generated_at",
        ]
        for field in required:
            assert field in d, f"Missing field: {field}"


class TestWhisperBatchRouting:
    """Batch routing applies fatigue caps."""

    def test_batch_routing_respects_fatigue_caps(self):
        """Batch routing caps proactive pushes (max 1 urgent + 2 prepare + 3 whisper + 5 briefing)."""
        from maestro_cognitive_council import (
            WhisperSituationBridge, LivingSituation, SituationState,
            Unknown, UserContext, DeliveryRoute,
        )

        # 5 situations all needing preparation
        situations = []
        for i in range(5):
            s = LivingSituation(
                situation_id=f"sit-{i}",
                title=f"Situation {i}",
                entity=f"Entity{i}",
                state=SituationState.NEEDS_PREPARATION,
            )
            s.add_unknown(Unknown(
                question=f"Blocking question {i}?",
                why_it_matters="Blocks the decision",
                blocking=True,
            ))
            situations.append(s)

        bridge = WhisperSituationBridge()
        results = bridge.from_situations_batch(situations, UserContext())

        # At most 2 should be PREPARE (the fatigue cap)
        prepare_count = sum(1 for r in results if r.delivery_route == "prepare")
        assert prepare_count <= 2, (
            f"Expected ≤2 PREPARE routes (fatigue cap), got {prepare_count}"
        )

    def test_batch_routing_returns_result_for_each_situation(self):
        """Batch routing returns a result for every situation."""
        from maestro_cognitive_council import (
            WhisperSituationBridge, LivingSituation, SituationState, UserContext,
        )

        situations = [
            LivingSituation(
                situation_id=f"sit-{i}",
                title=f"Situation {i}",
                entity=f"Entity{i}",
                state=SituationState.OBSERVING,
            )
            for i in range(3)
        ]

        bridge = WhisperSituationBridge()
        results = bridge.from_situations_batch(situations, UserContext())

        assert len(results) == 3
        for r in results:
            assert r.situation_id in [s.situation_id for s in situations]


class TestWhisperContextualBehavior:
    """The same Situation produces different Whisper behavior by context."""

    def test_whisper_during_meeting(self):
        """During a meeting, MATERIAL situations produce WHISPER route."""
        from maestro_cognitive_council import (
            WhisperSituationBridge, SituationState, UserContext,
        )

        situation = _make_situation(state=SituationState.MATERIAL)
        bridge = WhisperSituationBridge()

        result = bridge.from_situation(
            situation,
            user_context=UserContext(is_in_meeting=True),
        )

        assert result.delivery_route == "whisper"

    def test_whisper_during_focus_mode_suppressed(self):
        """During focus mode, low-urgency situations are SILENT."""
        from maestro_cognitive_council import (
            WhisperSituationBridge, SituationState, UserContext,
        )

        situation = _make_situation(state=SituationState.OBSERVING)
        bridge = WhisperSituationBridge()

        result = bridge.from_situation(
            situation,
            user_context=UserContext(is_in_focus_mode=True),
        )

        assert result.delivery_route == "silent"
        assert result.suppression_reason  # explained

    def test_whisper_morning_review_briefing(self):
        """During morning review, OBSERVING situations get BRIEFING route."""
        from maestro_cognitive_council import (
            WhisperSituationBridge, SituationState, UserContext,
        )

        situation = _make_situation(state=SituationState.OBSERVING)
        bridge = WhisperSituationBridge()

        result = bridge.from_situation(
            situation,
            user_context=UserContext(is_doing_morning_review=True),
        )

        assert result.delivery_route == "briefing"
