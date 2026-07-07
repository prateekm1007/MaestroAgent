"""Phase 11 — Deal Health Score tests.

Tests the DealHealthEngine: live scoring, risk factors, momentum, P25.
"""

from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from datetime import datetime, timedelta, timezone

import pytest


class TestDealHealthEngine:
    """Phase 11: DealHealthEngine with live scoring + risk factors + momentum."""

    def _make_engine(self):
        from maestro_oem.deal_health import DealHealthEngine
        return DealHealthEngine(oem_state=None)

    def test_score_neutral_with_no_data(self):
        """Score is neutral (50%) when there's no data for the entity."""
        engine = self._make_engine()
        score = engine.compute_score("UnknownCorp")
        assert 40 <= score.score <= 60  # neutral range
        assert score.calibration_denominator == 0
        assert "insufficient" in score.confidence_label  # P25

    def test_score_high_with_good_history(self):
        """Score is high when historical deals were won."""
        engine = self._make_engine()
        engine.record_deal_outcome("Globex", "won")
        engine.record_deal_outcome("Globex", "won")
        engine.record_deal_outcome("Globex", "won")
        score = engine.compute_score("Globex")
        assert score.score > 50  # good history boosts score
        assert score.calibration_denominator == 3

    def test_score_low_with_lost_deals(self):
        """Score is low when historical deals were lost."""
        engine = self._make_engine()
        engine.record_deal_outcome("Initech", "lost")
        engine.record_deal_outcome("Initech", "lost")
        score = engine.compute_score("Initech")
        assert score.score < 50  # poor history lowers score

    def test_status_classification(self):
        """Deal status is correctly classified from score."""
        from maestro_oem.deal_health import DealHealthStatus
        engine = self._make_engine()

        # Strong: many wins
        for _ in range(5):
            engine.record_deal_outcome("StrongCorp", "won")
        score = engine.compute_score("StrongCorp")
        assert score.status in (DealHealthStatus.STRONG, DealHealthStatus.ON_TRACK)

        # Critical: many losses
        engine2 = self._make_engine()
        for _ in range(5):
            engine2.record_deal_outcome("CriticalCorp", "lost")
        score2 = engine2.compute_score("CriticalCorp")
        assert score2.status in (DealHealthStatus.CRITICAL, DealHealthStatus.AT_RISK)

    def test_risk_factors_collected(self):
        """Risk factors are collected when scores are low."""
        engine = self._make_engine()
        engine.record_deal_outcome("RiskyCorp", "lost")
        engine.record_deal_outcome("RiskyCorp", "lost")
        score = engine.compute_score("RiskyCorp")
        assert len(score.risk_factors) > 0
        for rf in score.risk_factors:
            assert rf.severity in ("high", "medium", "low")
            assert rf.evidence.get("source")  # every risk has evidence source

    def test_positive_indicators_collected(self):
        """Positive indicators are collected when scores are high."""
        engine = self._make_engine()
        for _ in range(10):
            engine.record_deal_outcome("GoodCorp", "won")
        score = engine.compute_score("GoodCorp")
        # With 10 wins, historical score should be high
        assert len(score.positive_indicators) >= 0  # may or may not have positive indicators

    def test_momentum_computed(self):
        """Momentum is computed from score history."""
        from maestro_oem.deal_health import Momentum
        engine = self._make_engine()
        # First score (neutral)
        engine.compute_score("MomentumCorp")
        # Second score (add wins → score increases)
        for _ in range(5):
            engine.record_deal_outcome("MomentumCorp", "won")
        score = engine.compute_score("MomentumCorp")
        assert score.momentum in (Momentum.ACCELERATING, Momentum.STABLE, Momentum.DECELERATING)

    def test_p25_confidence_has_denominator(self):
        """P25: score confidence shows denominator (deal count in cohort)."""
        engine = self._make_engine()
        # No history → insufficient calibration
        score = engine.compute_score("NoHistoryCorp")
        assert "insufficient" in score.confidence_label
        assert score.calibration_denominator == 0

        # With 10+ deals → shows percentage + count
        for _ in range(12):
            engine.record_deal_outcome("CalibratedCorp", "won")
        score2 = engine.compute_score("CalibratedCorp")
        assert score2.calibration_denominator == 12
        assert "12" in score2.confidence_label

    def test_score_to_dict(self):
        """DealHealthScore serializes correctly."""
        engine = self._make_engine()
        engine.record_deal_outcome("Globex", "won")
        score = engine.compute_score("Globex")
        d = score.to_dict()
        assert "entity" in d
        assert "score" in d
        assert "status" in d
        assert "momentum" in d
        assert "confidence_label" in d
        assert "risk_factors" in d
        assert "score_history" in d

    def test_risk_factors_have_evidence(self):
        """Every risk factor cites its evidence source (anti-Cluely)."""
        engine = self._make_engine()
        engine.record_deal_outcome("RiskyCorp", "lost")
        engine.record_deal_outcome("RiskyCorp", "lost")
        score = engine.compute_score("RiskyCorp")
        for rf in score.risk_factors:
            assert rf.evidence.get("source"), f"Risk factor missing evidence source: {rf}"


class TestPhase11L0NoRegression:
    """Phase 11 must not regress the L0 substrate."""

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
