"""Tests for the Cognitive Council — Situation Engine, Perspective Contract,
Judgment Synthesizer, and Delivery Governor.

These tests verify the architectural reframe from the CEO directive:
  - Situation is the living product unit (not Agent → Insight)
  - Specialists contribute Perspectives (structured, not free-form)
  - The Synthesizer preserves disagreement (doesn't naively aggregate)
  - The Delivery Governor decides routing deterministically
"""

from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest


# ════════════════════════════════════════════════════════════════════════════
# Phase 1: Situation Engine
# ════════════════════════════════════════════════════════════════════════════

class TestSituationEngine:
    """The Situation Engine builds LivingSituations from OEM signals."""

    def _make_signal(self, sig_type, entity, text="", metadata=None, days_ago=0):
        sig = MagicMock()
        sig.type = MagicMock()
        sig.type.value = sig_type
        sig.entity = entity
        sig.text = text
        sig.metadata = metadata or {"customer": entity}
        sig.timestamp = datetime.now(timezone.utc) - timedelta(days=days_ago)
        sig.actor = ""
        sig.org_id = "default"
        return sig

    def test_detect_situations_from_signals(self):
        """SituationEngine detects situations from 2+ signals per entity."""
        from maestro_cognitive_council import SituationEngine

        oem = MagicMock()
        oem.signals = [
            self._make_signal("customer.commitment_made", "TestCorp",
                              "Deliver SSO by Friday", days_ago=10),
            self._make_signal("customer.commitment_made", "TestCorp",
                              "Send pricing", days_ago=5),
        ]

        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()

        assert len(situations) >= 1
        assert situations[0].entity == "TestCorp"
        assert len(situations[0].timeline) >= 2

    def test_situation_has_timeline(self):
        """A LivingSituation has a chronological timeline of events."""
        from maestro_cognitive_council import SituationEngine

        oem = MagicMock()
        oem.signals = [
            self._make_signal("customer.commitment_made", "TestCorp",
                              "Commitment 1", days_ago=10),
            self._make_signal("customer.commitment_made", "TestCorp",
                              "Commitment 2", days_ago=5),
            self._make_signal("customer.commitment_made", "TestCorp",
                              "Commitment 3", days_ago=1),
        ]

        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()

        assert len(situations[0].timeline) == 3
        # Timeline should be sorted chronologically
        timestamps = [e.timestamp for e in situations[0].timeline]
        assert timestamps == sorted(timestamps)

    def test_situation_detects_unknowns(self):
        """The engine detects unknowns (gaps in evidence).

        If there's a commitment but no outcome, the status is unknown.
        If there's a security signal but no resolution, the approval is unknown.
        """
        from maestro_cognitive_council import SituationEngine

        oem = MagicMock()
        oem.signals = [
            self._make_signal("customer.commitment_made", "TestCorp",
                              "Deliver SSO by Friday", days_ago=10),
            self._make_signal("security.condition", "TestCorp",
                              "Security approval required", days_ago=8),
        ]

        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()

        s = situations[0]
        # Should have at least one unknown (commitment status or security clearance)
        assert len(s.unknowns) >= 1
        # The security unknown should be blocking
        assert any(u.blocking for u in s.unknowns)

    def test_situation_state_needs_preparation_when_blocking_unknown(self):
        """A situation with a blocking unknown is in NEEDS_PREPARATION state."""
        from maestro_cognitive_council import SituationEngine, SituationState

        oem = MagicMock()
        oem.signals = [
            self._make_signal("customer.commitment_made", "TestCorp",
                              "Deliver SSO", days_ago=10),
            self._make_signal("security.condition", "TestCorp",
                              "Security approval required", days_ago=8),
        ]

        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()

        assert situations[0].state == SituationState.NEEDS_PREPARATION

    def test_specialist_routing_is_selective(self):
        """NOT all 17 specialists run for every situation.

        The engine routes only relevant specialists based on the
        situation's topic keywords.
        """
        from maestro_cognitive_council import SituationEngine

        oem = MagicMock()
        oem.signals = [
            self._make_signal("customer.commitment_made", "TestCorp",
                              "Deliver SSO integration by Friday", days_ago=10),
            self._make_signal("customer.commitment_made", "TestCorp",
                              "Send pricing for renewal", days_ago=5),
        ]

        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()

        specialists = situations[0].relevant_specialists
        # Should include chief_of_staff (always), sales, customer_success (entity-based)
        assert "chief_of_staff" in specialists
        assert "sales" in specialists
        assert "customer_success" in specialists
        # Should include security (because "SSO" is a security keyword)
        assert "security" in specialists
        # Should NOT include all 17 — that's the AI theater we're preventing
        assert len(specialists) < 17, (
            f"Routing {len(specialists)} specialists — should be selective, not all 17. "
            f"Got: {specialists}"
        )

    def test_epistemic_state_disputed_when_blocking_unknown(self):
        """Epistemic state is DISPUTED when there's a blocking unknown."""
        from maestro_cognitive_council import SituationEngine, EpistemicState

        oem = MagicMock()
        oem.signals = [
            self._make_signal("customer.commitment_made", "TestCorp",
                              "Deliver SSO", days_ago=10),
            self._make_signal("security.condition", "TestCorp",
                              "Security approval required", days_ago=8),
        ]

        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()

        assert situations[0].epistemic_state == EpistemicState.DISPUTED

    def test_situation_to_dict_has_required_fields(self):
        """LivingSituation.to_dict() exposes the full situation structure."""
        from maestro_cognitive_council import SituationEngine

        oem = MagicMock()
        oem.signals = [
            self._make_signal("customer.commitment_made", "TestCorp",
                              "Deliver SSO", days_ago=5),
            self._make_signal("customer.commitment_made", "TestCorp",
                              "Send pricing", days_ago=3),
        ]

        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()
        d = situations[0].to_dict()

        required = [
            "situation_id", "title", "entity", "state", "epistemic_state",
            "timeline", "known_facts", "unknowns", "perspectives",
            "disagreements", "judgment", "recommended_delivery",
            "relevant_specialists",
        ]
        for field in required:
            assert field in d, f"Missing field: {field}"

    def test_get_situations_needing_preparation(self):
        """get_situations_needing_preparation returns only NEEDS_PREPARATION."""
        from maestro_cognitive_council import SituationEngine, SituationState

        oem = MagicMock()
        oem.signals = [
            # TestCorp: has blocking unknown → NEEDS_PREPARATION
            self._make_signal("customer.commitment_made", "TestCorp",
                              "Deliver SSO", days_ago=10),
            self._make_signal("security.condition", "TestCorp",
                              "Security approval", days_ago=8),
            # OtherCorp: no blocking unknown → WATCHING
            self._make_signal("customer.commitment_made", "OtherCorp",
                              "Send docs", days_ago=5),
            self._make_signal("customer.commitment_made", "OtherCorp",
                              "Schedule call", days_ago=3),
        ]

        engine = SituationEngine(oem_state=oem)
        engine.detect_situations()

        needing_prep = engine.get_situations_needing_preparation()
        assert all(s.state == SituationState.NEEDS_PREPARATION for s in needing_prep)
        assert any(s.entity == "TestCorp" for s in needing_prep)
        assert not any(s.entity == "OtherCorp" for s in needing_prep)

    def test_null_oem_state_graceful(self):
        """The engine works with a null OEM state (standalone mode)."""
        from maestro_cognitive_council import SituationEngine

        engine = SituationEngine(oem_state=None)
        situations = engine.detect_situations()
        assert situations == []


# ════════════════════════════════════════════════════════════════════════════
# Phase 2: Perspective Contract
# ════════════════════════════════════════════════════════════════════════════

class TestPerspectiveContract:
    """The Perspective contract enforces epistemic discipline."""

    def test_perspective_has_required_fields(self):
        """A Perspective has the full epistemic schema."""
        from maestro_cognitive_council import Perspective, EpistemicState, DeliveryRoute

        p = Perspective(
            situation_id="sit-1",
            specialist="security",
            observation="Security approval for SSO is conditional",
            implication="Renewal may be blocked if condition isn't cleared",
            evidence=[{"source": "security_audit", "id": "ev-1"}],
            counterevidence=[{"source": "internal_record", "description": "Team claims approval was given"}],
            unknowns=["Was the condition subsequently cleared?"],
            epistemic_status=EpistemicState.DISPUTED,
            delivery_recommendation=DeliveryRoute.PREPARE,
        )

        d = p.to_dict()
        required = [
            "perspective_id", "situation_id", "specialist", "observation",
            "implication", "evidence", "counterevidence", "unknowns",
            "epistemic_status", "delivery_recommendation",
        ]
        for field in required:
            assert field in d, f"Missing field: {field}"

    def test_epistemic_honesty_requires_evidence_and_limits(self):
        """A perspective is epistemically honest only if it cites evidence
        AND acknowledges counterevidence or unknowns."""
        from maestro_cognitive_council import Perspective

        # Has evidence + counterevidence → honest
        honest = Perspective(
            observation="x",
            evidence=[{"source": "s"}],
            counterevidence=[{"source": "c"}],
        )
        assert honest.is_epistemically_honest()

        # Has evidence + unknowns → honest
        honest2 = Perspective(
            observation="x",
            evidence=[{"source": "s"}],
            unknowns=["we don't know y"],
        )
        assert honest2.is_epistemically_honest()

        # Has evidence but no counterevidence/unknowns → NOT honest
        not_honest = Perspective(
            observation="x",
            evidence=[{"source": "s"}],
        )
        assert not not_honest.is_epistemically_honest()

        # No evidence at all → NOT honest
        no_evidence = Perspective(observation="x")
        assert not no_evidence.is_epistemically_honest()


# ════════════════════════════════════════════════════════════════════════════
# Phase 3: Judgment Synthesizer
# ════════════════════════════════════════════════════════════════════════════

class TestJudgmentSynthesizer:
    """The Synthesizer produces a reasoned Judgment — not a summary."""

    def _make_perspective(
        self,
        specialist="security",
        observation="Security approval is conditional",
        implication="Renewal at risk",
        urgency="high",
        evidence=None,
        counterevidence=None,
        unknowns=None,
        next_step="Verify the security clearance",
    ):
        from maestro_cognitive_council import Perspective, EpistemicState, DeliveryRoute
        return Perspective(
            situation_id="sit-1",
            specialist=specialist,
            observation=observation,
            implication=implication,
            evidence=evidence or [{"source": "audit", "id": "ev-1"}],
            counterevidence=counterevidence or [],
            unknowns=unknowns or ["Status of conditional approval"],
            urgency=urgency,
            recommended_next_step=next_step,
            epistemic_status=EpistemicState.REPORTED,
            delivery_recommendation=DeliveryRoute.PREPARE,
        )

    def _make_situation(self):
        from maestro_cognitive_council import LivingSituation, SituationState, EpistemicState
        return LivingSituation(
            situation_id="sit-1",
            title="TestCorp SSO Renewal",
            entity="TestCorp",
            state=SituationState.NEEDS_PREPARATION,
            epistemic_state=EpistemicState.DISPUTED,
        )

    def test_synthesize_produces_judgment(self):
        """The Synthesizer produces a Judgment with the required fields."""
        from maestro_cognitive_council import JudgmentSynthesizer

        synth = JudgmentSynthesizer()
        situation = self._make_situation()
        perspectives = [self._make_perspective()]

        judgment = synth.synthesize(situation, perspectives)

        assert judgment.central_claim
        assert judgment.strongest_reason_to_act
        assert judgment.recommended_next_step
        assert 0.0 <= judgment.confidence <= 1.0

    def test_synthesize_detects_disagreements(self):
        """The Synthesizer preserves disagreements — doesn't converge them away."""
        from maestro_cognitive_council import JudgmentSynthesizer

        synth = JudgmentSynthesizer()
        situation = self._make_situation()
        perspectives = [
            self._make_perspective(
                specialist="product",
                observation="Delay migration",
                implication="Avoid release conflict",
                urgency="low",
            ),
            self._make_perspective(
                specialist="security",
                observation="Don't delay migration",
                implication="Delay increases exposure",
                urgency="critical",
            ),
        ]

        judgment = synth.synthesize(situation, perspectives)

        # Disagreements should be detected and stored on the situation
        assert len(situation.disagreements) > 0
        # The judgment should acknowledge the disagreement
        assert "disagree" in judgment.central_claim.lower()

    def test_synthesize_acknowledges_unknowns(self):
        """The Judgment acknowledges blocking unknowns — doesn't hide them."""
        from maestro_cognitive_council import JudgmentSynthesizer, Unknown, LivingSituation

        synth = JudgmentSynthesizer()
        situation = self._make_situation()
        situation.add_unknown(Unknown(
            question="Was security approval cleared?",
            why_it_matters="Blocks the renewal decision",
            blocking=True,
        ))
        perspectives = [self._make_perspective()]

        judgment = synth.synthesize(situation, perspectives)

        assert len(judgment.unknowns_blocking_decision) > 0
        assert "Was security approval cleared?" in judgment.unknowns_blocking_decision

    def test_synthesize_deduplicates_perspectives(self):
        """Duplicate perspectives (same observation) are deduplicated."""
        from maestro_cognitive_council import JudgmentSynthesizer

        synth = JudgmentSynthesizer()
        situation = self._make_situation()
        perspectives = [
            self._make_perspective(specialist="sales", observation="Same observation"),
            self._make_perspective(specialist="cs", observation="Same observation"),
        ]

        judgment = synth.synthesize(situation, perspectives)
        # Deduplication should have reduced to 1 perspective
        # (confidence reflects the deduplication)
        assert judgment.confidence < 0.9  # not over-confident

    def test_confidence_is_calibrated_not_fabricated(self):
        """Confidence is based on evidence count, not pseudo-scientific precision."""
        from maestro_cognitive_council import JudgmentSynthesizer

        synth = JudgmentSynthesizer()
        situation = self._make_situation()

        # Single perspective with 1 evidence item → low confidence
        low_evidence = [self._make_perspective(evidence=[{"source": "s"}])]
        low_judgment = synth.synthesize(situation, low_evidence)

        # Multiple perspectives with more evidence → higher confidence
        high_evidence = [
            self._make_perspective(
                specialist="sales",
                evidence=[{"source": "s1"}, {"source": "s2"}, {"source": "s3"}],
            ),
            self._make_perspective(
                specialist="security",
                evidence=[{"source": "s4"}, {"source": "s5"}],
            ),
        ]
        high_judgment = synth.synthesize(situation, high_evidence)

        assert high_judgment.confidence > low_judgment.confidence

    def test_empty_perspectives_produces_low_confidence(self):
        """No perspectives → low confidence, honest acknowledgment."""
        from maestro_cognitive_council import JudgmentSynthesizer

        synth = JudgmentSynthesizer()
        situation = self._make_situation()
        judgment = synth.synthesize(situation, [])

        assert judgment.confidence == 0.0
        assert "insufficient" in judgment.central_claim.lower()


# ════════════════════════════════════════════════════════════════════════════
# Phase 4: Delivery Governor
# ════════════════════════════════════════════════════════════════════════════

class TestDeliveryGovernor:
    """The Delivery Governor routes situations deterministically."""

    def _make_situation(self, state=None, has_blocking_unknown=False):
        from maestro_cognitive_council import (
            LivingSituation, SituationState, EpistemicState, Unknown,
        )
        s = LivingSituation(
            situation_id="sit-1",
            title="TestCorp Situation",
            entity="TestCorp",
            state=state or SituationState.WATCHING,
            epistemic_state=EpistemicState.REPORTED,
        )
        if has_blocking_unknown:
            s.add_unknown(Unknown(
                question="Blocking question?",
                why_it_matters="It blocks the decision",
                blocking=True,
            ))
        return s

    def _make_perspective(self, urgency="normal", evidence_count=1):
        from maestro_cognitive_council import Perspective
        return Perspective(
            observation="test",
            evidence=[{"source": f"ev-{i}"} for i in range(evidence_count)],
            urgency=urgency,
        )

    def test_urgent_route_for_critical_perspective_with_evidence(self):
        """URGENT route when a specialist flags critical + 2+ evidence."""
        from maestro_cognitive_council import DeliveryGovernor, DeliveryRoute, SituationState, UserContext

        gov = DeliveryGovernor()
        situation = self._make_situation(state=SituationState.ACTIVE)
        perspectives = [self._make_perspective(urgency="critical", evidence_count=3)]

        route = gov.decide(situation, perspectives, UserContext())
        assert route == DeliveryRoute.URGENT

    def test_prepare_route_for_needs_preparation_state(self):
        """PREPARE route when situation state is NEEDS_PREPARATION."""
        from maestro_cognitive_council import (
            DeliveryGovernor, DeliveryRoute, SituationState, UserContext,
        )

        gov = DeliveryGovernor()
        situation = self._make_situation(
            state=SituationState.NEEDS_PREPARATION,
            has_blocking_unknown=True,
        )

        route = gov.decide(situation, [], UserContext())
        assert route == DeliveryRoute.PREPARE

    def test_whisper_route_during_meeting(self):
        """WHISPER route when user is in a meeting + situation is relevant."""
        from maestro_cognitive_council import (
            DeliveryGovernor, DeliveryRoute, SituationState, UserContext,
        )

        gov = DeliveryGovernor()
        situation = self._make_situation(state=SituationState.ACTIVE)
        ctx = UserContext(is_in_meeting=True)

        route = gov.decide(situation, [], ctx)
        assert route == DeliveryRoute.WHISPER

    def test_no_whisper_during_focus_mode(self):
        """WHISPER is suppressed during focus mode (unless urgent)."""
        from maestro_cognitive_council import (
            DeliveryGovernor, DeliveryRoute, SituationState, UserContext,
        )

        gov = DeliveryGovernor()
        situation = self._make_situation(state=SituationState.ACTIVE)
        ctx = UserContext(is_in_meeting=True, is_in_focus_mode=True)

        route = gov.decide(situation, [], ctx)
        # Should NOT be WHISPER (focus mode suppresses it)
        assert route != DeliveryRoute.WHISPER

    def test_briefing_route_during_morning_review(self):
        """BRIEFING route when user is doing morning review + situation is active."""
        from maestro_cognitive_council import (
            DeliveryGovernor, DeliveryRoute, SituationState, UserContext,
        )

        gov = DeliveryGovernor()
        situation = self._make_situation(state=SituationState.WATCHING)
        ctx = UserContext(is_doing_morning_review=True)

        route = gov.decide(situation, [], ctx)
        assert route == DeliveryRoute.BRIEFING

    def test_silent_route_for_dormant_situations(self):
        """SILENT route for situations with no facts or activity."""
        from maestro_cognitive_council import (
            DeliveryGovernor, DeliveryRoute, SituationState, UserContext,
        )

        gov = DeliveryGovernor()
        situation = self._make_situation(state=SituationState.DORMANT)
        # No known facts, dormant state
        situation.known_facts = []

        route = gov.decide(situation, [], UserContext())
        assert route == DeliveryRoute.SILENT

    def test_routing_is_deterministic(self):
        """Same inputs → same output (no model guessing)."""
        from maestro_cognitive_council import (
            DeliveryGovernor, SituationState, UserContext,
        )

        gov = DeliveryGovernor()
        situation = self._make_situation(state=SituationState.NEEDS_PREPARATION,
                                         has_blocking_unknown=True)
        ctx = UserContext()

        route1 = gov.decide(situation, [], ctx)
        route2 = gov.decide(situation, [], ctx)
        assert route1 == route2

    def test_batch_routing_applies_fatigue_caps(self):
        """Batch routing caps the number of proactive pushes.

        At most: 1 URGENT + 2 PREPARE + 3 WHISPER + 5 BRIEFING per cycle.
        Excess situations are downgraded to ASK.
        """
        from maestro_cognitive_council import (
            DeliveryGovernor, DeliveryRoute, SituationState, UserContext,
            LivingSituation,
        )

        gov = DeliveryGovernor()
        # 5 situations all needing preparation
        situations = [
            LivingSituation(
                situation_id=f"sit-{i}",
                title=f"Situation {i}",
                entity=f"Entity{i}",
                state=SituationState.NEEDS_PREPARATION,
            )
            for i in range(5)
        ]
        # Add blocking unknowns to all
        from maestro_cognitive_council import Unknown
        for s in situations:
            s.add_unknown(Unknown(
                question="Blocking?", why_it_matters="Yes", blocking=True,
            ))

        routes = gov.route_batch(situations, {}, UserContext())

        # Only 2 should be PREPARE (the cap), rest downgraded to ASK
        prepare_count = sum(1 for r in routes.values() if r == DeliveryRoute.PREPARE)
        assert prepare_count <= 2, (
            f"Expected ≤2 PREPARE routes (fatigue cap), got {prepare_count}"
        )

    def test_explain_provides_transparency(self):
        """The Governor explains WHY it chose a route (transparency)."""
        from maestro_cognitive_council import (
            DeliveryGovernor, SituationState, UserContext,
        )

        gov = DeliveryGovernor()
        situation = self._make_situation(
            state=SituationState.NEEDS_PREPARATION,
            has_blocking_unknown=True,
        )
        ctx = UserContext()
        route = gov.decide(situation, [], ctx)
        explanation = gov.explain(situation, [], ctx, route)

        assert explanation  # non-empty
        assert "preparation" in explanation.lower() or "blocking" in explanation.lower()


# ════════════════════════════════════════════════════════════════════════════
# Integration: Situation → Perspectives → Judgment → Delivery
# ════════════════════════════════════════════════════════════════════════════

class TestFullCognitiveCouncilFlow:
    """The full flow: detect situation → contribute perspectives →
    synthesize judgment → decide delivery."""

    def test_full_flow(self):
        """End-to-end: signals → situation → perspectives → judgment → route."""
        from maestro_cognitive_council import (
            SituationEngine, JudgmentSynthesizer, DeliveryGovernor,
            Perspective, DeliveryRoute, SituationState, UserContext,
            EpistemicState,
        )

        # 1. Detect situation from signals
        oem = MagicMock()
        oem.signals = [
            MagicMock(
                type=MagicMock(value="customer.commitment_made"),
                entity="TestCorp",
                text="Deliver SSO by Friday",
                metadata={"customer": "TestCorp"},
                timestamp=datetime.now(timezone.utc) - timedelta(days=10),
                actor="",
                org_id="default",
            ),
            MagicMock(
                type=MagicMock(value="security.condition"),
                entity="TestCorp",
                text="Security approval required",
                metadata={"customer": "TestCorp"},
                timestamp=datetime.now(timezone.utc) - timedelta(days=8),
                actor="",
                org_id="default",
            ),
        ]

        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()
        assert len(situations) >= 1
        situation = situations[0]

        # 2. Only relevant specialists contribute perspectives
        # (the engine routed security + sales + customer_success + chief_of_staff)
        assert "security" in situation.relevant_specialists

        perspectives = [
            Perspective(
                situation_id=situation.situation_id,
                specialist="security",
                observation="Security approval is conditional",
                implication="Renewal may be blocked",
                evidence=[{"source": "audit", "id": "ev-1"}],
                unknowns=["Was the condition cleared?"],
                urgency="high",
                recommended_next_step="Verify security clearance before the meeting",
                epistemic_status=EpistemicState.DISPUTED,
            ),
        ]

        # 3. Synthesize judgment
        synth = JudgmentSynthesizer()
        situation.judgment = synth.synthesize(situation, perspectives)

        assert situation.judgment.central_claim
        assert situation.judgment.recommended_next_step

        # 4. Decide delivery
        gov = DeliveryGovernor()
        route = gov.decide(situation, perspectives, UserContext())

        # Situation is NEEDS_PREPARATION (has blocking unknown) → PREPARE
        assert route == DeliveryRoute.PREPARE
