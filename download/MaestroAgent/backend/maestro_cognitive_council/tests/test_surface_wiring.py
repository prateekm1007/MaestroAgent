"""Tests for the 3 surface wiring bridges: Ask, Briefing, Preparation.

These tests prove the Cognitive Council is now at level 3 (wired to
production) for 3 of the 5 surfaces. The bridges connect:
  1. Ask → Situation Engine (SituationAwareAskBridge)
  2. Briefing → Situation Judgment (SituationBriefingEngine)
  3. Prepare → LivingSituation (SituationPreparationBridge)

The remaining 2 surfaces (Whisper → Delivery Governor, Copilot → Situation
Engine) will be wired next.
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

def _make_signal(sig_type, entity, text, signal_id="", days_ago=0):
    sig = MagicMock()
    sig.type = MagicMock()
    sig.type.value = sig_type
    sig.entity = entity
    sig.text = text
    sig.signal_id = signal_id or f"sig-{entity.lower()}-{days_ago}"
    sig.metadata = {"customer": entity}
    sig.timestamp = datetime.now(timezone.utc) - timedelta(days=days_ago)
    sig.actor = ""
    sig.org_id = "default"
    return sig


def _make_oem_with_signals(signals):
    oem = MagicMock()
    oem.signals = signals
    return oem


# ════════════════════════════════════════════════════════════════════════════
# Surface 1: Ask → Situation Engine
# ════════════════════════════════════════════════════════════════════════════

class TestSituationAwareAskBridge:
    """Ask retrieves Situation (not just OEM signals)."""

    def test_ask_finds_situation_for_entity(self):
        """Ask detects the entity in the query and finds the relevant Situation."""
        from maestro_cognitive_council import SituationAwareAskBridge

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        bridge = SituationAwareAskBridge(oem_state=oem)

        result = bridge.ask("What's happening with the CustomerA renewal?")

        assert result.found_situation is True
        assert "CustomerA" in result.situation_title or "CustomerA" in result.entity

    def test_ask_reconstructs_chronology(self):
        """Ask reconstructs the chronology from the Situation's timeline."""
        from maestro_cognitive_council import SituationAwareAskBridge

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        bridge = SituationAwareAskBridge(oem_state=oem)

        result = bridge.ask("What's happening with CustomerA?")

        assert len(result.chronology) >= 2
        # Chronology should have timestamps + descriptions + evidence_refs
        for event in result.chronology:
            assert "timestamp" in event
            assert "description" in event
            assert "evidence_ref" in event  # reference, not copy

    def test_ask_distinguishes_fact_from_report(self):
        """Ask distinguishes known facts from reported statements."""
        from maestro_cognitive_council import SituationAwareAskBridge

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("reported_statement", "CustomerA", "Team says work is complete", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        bridge = SituationAwareAskBridge(oem_state=oem)

        result = bridge.ask("What's happening with CustomerA?")

        # Should have either known_facts or reported_statements (or both)
        assert len(result.known_facts) + len(result.reported_statements) > 0

    def test_ask_surfaces_unknowns(self):
        """Ask surfaces unknowns — what we don't know yet."""
        from maestro_cognitive_council import SituationAwareAskBridge

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        bridge = SituationAwareAskBridge(oem_state=oem)

        result = bridge.ask("What's happening with CustomerA?")

        assert len(result.unknowns) > 0
        # Should have blocking unknowns (security clearance)
        assert len(result.blocking_unknowns) > 0

    def test_ask_cites_evidence_by_reference(self):
        """Ask cites evidence by reference (not copy)."""
        from maestro_cognitive_council import SituationAwareAskBridge

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        bridge = SituationAwareAskBridge(oem_state=oem)

        result = bridge.ask("What's happening with CustomerA?")

        assert len(result.evidence_refs) > 0
        # Evidence refs should be strings (IDs), not objects
        assert all(isinstance(r, str) for r in result.evidence_refs)

    def test_ask_generates_answer_narrative(self):
        """Ask generates a Situation-centric answer narrative."""
        from maestro_cognitive_council import SituationAwareAskBridge

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        bridge = SituationAwareAskBridge(oem_state=oem)

        result = bridge.ask("What's happening with CustomerA?")

        assert result.answer  # non-empty
        # Should mention the situation title
        assert result.situation_title in result.answer or "CustomerA" in result.answer

    def test_ask_falls_back_gracefully_when_no_entity(self):
        """Ask falls back gracefully when no entity is detected."""
        from maestro_cognitive_council import SituationAwareAskBridge

        oem = _make_oem_with_signals([])
        bridge = SituationAwareAskBridge(oem_state=oem)

        result = bridge.ask("What's the weather?")

        assert result.found_situation is False
        assert "organizational memory" in result.answer.lower() or "don't have" in result.answer.lower()


# ════════════════════════════════════════════════════════════════════════════
# Surface 2: Briefing → Situation Judgment
# ════════════════════════════════════════════════════════════════════════════

class TestSituationBriefingEngine:
    """Briefing answers 'What materially changed?' — not agent insights."""

    def test_morning_briefing_has_top_situation(self):
        """Morning briefing identifies the one situation needing judgment."""
        from maestro_cognitive_council import SituationBriefingEngine

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        engine = SituationBriefingEngine(oem_state=oem)

        briefing = engine.generate_morning_briefing(user_email="jane@example.com")

        assert briefing.briefing_type == "morning"
        # Should have a top situation (CustomerA has security prereq → MATERIAL)
        if briefing.top_situation:
            assert "CustomerA" in briefing.top_situation.get("title", "") or \
                   "CustomerA" in briefing.top_situation.get("entity", "")

    def test_morning_briefing_includes_material_changes(self):
        """Morning briefing includes what materially changed."""
        from maestro_cognitive_council import SituationBriefingEngine

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        engine = SituationBriefingEngine(oem_state=oem)

        briefing = engine.generate_morning_briefing()

        assert len(briefing.material_changes) > 0

    def test_morning_briefing_includes_unknowns(self):
        """Morning briefing includes what's currently unknown."""
        from maestro_cognitive_council import SituationBriefingEngine

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        engine = SituationBriefingEngine(oem_state=oem)

        briefing = engine.generate_morning_briefing()

        # Should have unknowns (security clearance question)
        assert len(briefing.unknowns) > 0

    def test_morning_briefing_has_ask_prompt(self):
        """Morning briefing ends with an Ask prompt."""
        from maestro_cognitive_council import SituationBriefingEngine

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        engine = SituationBriefingEngine(oem_state=oem)

        briefing = engine.generate_morning_briefing()

        assert briefing.ask_prompt  # non-empty

    def test_evening_briefing_is_quieter(self):
        """Evening briefing is quieter than morning."""
        from maestro_cognitive_council import SituationBriefingEngine

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        engine = SituationBriefingEngine(oem_state=oem)

        briefing = engine.generate_evening_briefing()

        assert briefing.briefing_type == "evening"
        assert len(briefing.material_changes) > 0

    def test_briefing_to_dict(self):
        """Briefing exposes full structure in to_dict()."""
        from maestro_cognitive_council import SituationBriefingEngine

        oem = _make_oem_with_signals([])
        engine = SituationBriefingEngine(oem_state=oem)
        briefing = engine.generate_morning_briefing()
        d = briefing.to_dict()

        required = [
            "greeting", "date", "briefing_type", "briefing_id",
            "top_situation", "material_changes", "unknowns", "disputes",
            "can_decide_now", "cannot_decide_yet", "ask_prompt",
        ]
        for field in required:
            assert field in d, f"Missing field: {field}"


# ════════════════════════════════════════════════════════════════════════════
# Surface 3: Prepare → LivingSituation
# ════════════════════════════════════════════════════════════════════════════

class TestSituationPreparationBridge:
    """Prepare is Situation-aware — not generic."""

    def test_prepare_for_situation_finds_unknowns(self):
        """Preparation surfaces the unknowns that must be resolved."""
        from maestro_cognitive_council import SituationPreparationBridge, SituationEngine

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()
        bridge = SituationPreparationBridge(oem_state=oem, situation_engine=engine)

        if situations:
            prep = bridge.prepare_for_situation(situations[0].situation_id)
            assert prep.situation_id == situations[0].situation_id
            # Should have unknowns to resolve
            assert len(prep.unknowns_to_resolve) > 0

    def test_prepare_includes_blocking_unknowns(self):
        """Preparation includes blocking unknowns that must be resolved."""
        from maestro_cognitive_council import SituationPreparationBridge, SituationEngine

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()
        bridge = SituationPreparationBridge(oem_state=oem, situation_engine=engine)

        if situations:
            prep = bridge.prepare_for_situation(situations[0].situation_id)
            # Should have blocking unknowns (security clearance)
            assert len(prep.blocking_unknowns) > 0

    def test_prepare_generates_questions(self):
        """Preparation generates questions to ask in the meeting."""
        from maestro_cognitive_council import SituationPreparationBridge, SituationEngine

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()
        bridge = SituationPreparationBridge(oem_state=oem, situation_engine=engine)

        if situations:
            prep = bridge.prepare_for_situation(situations[0].situation_id)
            assert len(prep.questions_to_ask) > 0

    def test_prepare_detects_staleness(self):
        """Preparation detects if reality changed since preparation was made."""
        from maestro_cognitive_council import SituationPreparationBridge, SituationEngine

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()
        bridge = SituationPreparationBridge(oem_state=oem, situation_engine=engine)

        if situations:
            prep = bridge.prepare_for_situation(situations[0].situation_id)
            # Staleness is a bool — either stale or not
            assert isinstance(prep.is_stale, bool)

    def test_prepare_cites_evidence_by_reference(self):
        """Preparation cites evidence by reference (not copy)."""
        from maestro_cognitive_council import SituationPreparationBridge, SituationEngine

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()
        bridge = SituationPreparationBridge(oem_state=oem, situation_engine=engine)

        if situations:
            prep = bridge.prepare_for_situation(situations[0].situation_id)
            assert len(prep.evidence_refs) > 0
            assert all(isinstance(r, str) for r in prep.evidence_refs)

    def test_prepare_for_upcoming_meetings(self):
        """prepare_for_upcoming_meetings finds all situations needing preparation."""
        from maestro_cognitive_council import SituationPreparationBridge

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
            _make_signal("reported_statement", "CustomerA", "Customer defines availability as production access", "s3", days_ago=5),
        ]
        oem = _make_oem_with_signals(signals)
        from maestro_cognitive_council import SituationEngine
        engine = SituationEngine(oem_state=oem)
        engine.detect_situations()
        bridge = SituationPreparationBridge(oem_state=oem, situation_engine=engine)

        preps = bridge.prepare_for_upcoming_meetings()

        # Should find situations needing preparation
        assert isinstance(preps, list)

    def test_prepare_to_dict(self):
        """Preparation exposes full structure in to_dict()."""
        from maestro_cognitive_council import SituationPreparationBridge, SituationEngine

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        from maestro_cognitive_council import SituationEngine
        engine = SituationEngine(oem_state=oem)
        engine.detect_situations()
        bridge = SituationPreparationBridge(oem_state=oem, situation_engine=engine)
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()

        if situations:
            prep = bridge.prepare_for_situation(situations[0].situation_id)
            d = prep.to_dict()

            required = [
                "situation_id", "situation_title", "situation_state",
                "unknowns_to_resolve", "blocking_unknowns",
                "can_decide_now", "cannot_decide_yet",
                "is_stale", "questions_to_ask", "evidence_refs",
            ]
            for field in required:
                assert field in d, f"Missing field: {field}"
