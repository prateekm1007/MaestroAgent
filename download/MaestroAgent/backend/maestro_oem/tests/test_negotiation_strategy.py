"""Phase 12 — Negotiation Strategy Engine tests.

Tests BATNA analysis, anchoring detection, concession tracking, and
counter-offer suggestions with P25 confidence gate.
"""

from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import pytest


class TestNegotiationStrategyEngine:
    """Phase 12: NegotiationStrategyEngine."""

    def _make_engine(self):
        from maestro_oem.negotiation_strategy import NegotiationStrategyEngine
        return NegotiationStrategyEngine(oem_state=None)

    def test_anchor_detection(self):
        """Price anchors are detected from transcript text."""
        engine = self._make_engine()
        strategy = engine.process_transcript("We can offer $50,000 for the annual contract.", "Sam Kumar")
        assert strategy.their_anchor is not None
        assert strategy.their_anchor == 50000

    def test_first_anchor_is_theirs(self):
        """The first number mentioned by the other party is their anchor."""
        engine = self._make_engine()
        engine.process_transcript("Our budget is $50K.", "Sam Kumar")
        strategy = engine._generate_strategy()
        assert strategy.their_anchor == 50000

    def test_batna_analysis_below_batna(self):
        """When they anchor below BATNA, counter above BATNA."""
        engine = self._make_engine()
        engine.set_batna(65000)
        strategy = engine.process_transcript("We can offer $50,000.", "Sam Kumar")
        assert strategy.counter_offer_suggestion is not None
        assert "BATNA" in strategy.counter_offer_suggestion
        assert "65,000" in strategy.counter_offer_suggestion
        assert strategy.evidence.get("source") == "batna_analysis"

    def test_batna_analysis_above_batna(self):
        """When they anchor above BATNA, it's favorable."""
        engine = self._make_engine()
        engine.set_batna(50000)
        strategy = engine.process_transcript("We're thinking $75,000.", "Sam Kumar")
        assert "favorable" in strategy.counter_offer_suggestion.lower()

    def test_concession_detection(self):
        """Concessions are detected from concession language."""
        engine = self._make_engine()
        engine.process_transcript("We can offer $50,000.", "Sam Kumar")
        engine.process_transcript("How about we reduce to $45,000?", "Sam Kumar")
        strategy = engine._generate_strategy()
        assert len(strategy.concessions) >= 1
        assert strategy.concessions[0].concession_type == "price_reduction"

    def test_phase_progression(self):
        """Negotiation phase progresses correctly."""
        from maestro_oem.negotiation_strategy import NegotiationPhase
        engine = self._make_engine()

        # No anchors yet → pre-negotiation
        strategy = engine._generate_strategy()
        assert strategy.phase == NegotiationPhase.PRE_NEGOTIATION

        # Their anchor → anchoring
        engine.process_transcript("We offer $50K.", "Sam")
        assert engine._generate_strategy().phase == NegotiationPhase.ANCHORING

        # Your counter → counter_offer
        engine.process_transcript("We need $60K.", "you")
        assert engine._generate_strategy().phase == NegotiationPhase.COUNTER_OFFER

        # Concession → concession
        engine.process_transcript("How about $55K?", "Sam")
        assert engine._generate_strategy().phase in (NegotiationPhase.CONCESSION, NegotiationPhase.CLOSING)

    def test_p25_confidence_has_denominator(self):
        """P25: strategy confidence shows denominator (negotiation count)."""
        engine = self._make_engine()
        engine.set_batna(65000)
        strategy = engine.process_transcript("We offer $50K.", "Sam")
        # No historical negotiations → insufficient
        assert "insufficient" in strategy.confidence_label
        assert strategy.confidence_denominator == 0

        # Add 12 historical negotiations
        for i in range(12):
            engine.record_historical_negotiation("Corp" + str(i), "won", 55000)
        strategy2 = engine.process_transcript("We offer $50K again.", "Sam2")
        assert strategy2.confidence_denominator == 12
        assert "12" in strategy2.confidence_label

    def test_historical_pattern_suggestion(self):
        """When historical win rate is high, suggest holding position."""
        engine = self._make_engine()
        for _ in range(5):
            engine.record_historical_negotiation("Globex", "won", 55000)
        # No BATNA set — the historical pattern should surface
        strategy = engine.process_transcript("We offer $50K.", "Sam")
        # With 5 wins, the historical pattern should generate a suggestion
        assert strategy.evidence.get("historical_win_rate") is not None or strategy.counter_offer_suggestion is not None

    def test_strategy_to_dict(self):
        """NegotiationStrategy serializes correctly."""
        engine = self._make_engine()
        engine.set_batna(65000)
        strategy = engine.process_transcript("We offer $50K.", "Sam Kumar")
        d = strategy.to_dict()
        assert "phase" in d
        assert "batna" in d
        assert "their_anchor" in d
        assert "counter_offer_suggestion" in d
        assert "confidence_label" in d
        assert "evidence" in d

    def test_evidence_cited_on_every_suggestion(self):
        """Every counter-offer suggestion has evidence (anti-Cluely)."""
        engine = self._make_engine()
        engine.set_batna(65000)
        strategy = engine.process_transcript("We offer $50,000.", "Sam Kumar")
        if strategy.counter_offer_suggestion:
            assert strategy.evidence.get("source"), "Suggestion missing evidence source"
            assert strategy.evidence.get("their_anchor") is not None
            assert strategy.evidence.get("your_batna") is not None


class TestPhase12L0NoRegression:
    """Phase 12 must not regress the L0 substrate."""

    def test_situation_snapshot_27_fields(self):
        from maestro_oem.situation import Situation
        import dataclasses
        assert len(dataclasses.fields(Situation)) == 27

    def test_outcome_ledger_functional(self):
        from maestro_oem.governed_adaptation import OutcomeLedger
        ol = OutcomeLedger()
        assert hasattr(ol, "append") and hasattr(ol, "count")

    def test_classifier_new_types(self):
        from maestro_oem.content_epistemic_classifier import ContentEpistemicClassifier
        clf = ContentEpistemicClassifier()
        assert clf.classify("Maybe we can ship SSO by Q4.") == "tentative"
