"""Phase 20 - Advanced Analytics Dashboard tests (MASTER GATE).

Tests trend analysis, team performance (aggregate only), org learning
metrics, Brier score tracking, flywheel summary, P25, and L0 no-regression.

This is the MASTER GATE - the final phase. All prior tests must still pass.
"""

from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from datetime import datetime, timezone

import pytest


class TestAdvancedAnalyticsEngine:
    """Phase 20: AdvancedAnalyticsEngine (MASTER GATE)."""

    def _make_engine(self):
        from maestro_oem.advanced_analytics import AdvancedAnalyticsEngine
        return AdvancedAnalyticsEngine()

    def test_trend_improving(self):
        """Trend is IMPROVING when metric increases (>5%)."""
        engine = self._make_engine()
        engine.record_data_point("commitment_kept_rate", 0.65, period="30d")
        engine.record_data_point("commitment_kept_rate", 0.85, period="current")
        report = engine.generate_report()
        trend = [t for t in report.trends if t.name == "commitment_kept_rate"]
        assert len(trend) >= 1
        from maestro_oem.advanced_analytics import TrendDirection
        assert trend[0].direction == TrendDirection.IMPROVING

    def test_trend_declining(self):
        """Trend is DECLINING when metric decreases (>5%)."""
        engine = self._make_engine()
        engine.record_data_point("commitment_kept_rate", 0.85, period="30d")
        engine.record_data_point("commitment_kept_rate", 0.60, period="current")
        report = engine.generate_report()
        trend = [t for t in report.trends if t.name == "commitment_kept_rate"]
        from maestro_oem.advanced_analytics import TrendDirection
        assert trend[0].direction == TrendDirection.DECLINING

    def test_trend_stable(self):
        """Trend is STABLE when change is <5%."""
        engine = self._make_engine()
        engine.record_data_point("commitment_kept_rate", 0.75, period="30d")
        engine.record_data_point("commitment_kept_rate", 0.77, period="current")
        report = engine.generate_report()
        trend = [t for t in report.trends if t.name == "commitment_kept_rate"]
        from maestro_oem.advanced_analytics import TrendDirection
        assert trend[0].direction == TrendDirection.STABLE

    def test_trend_brier_lower_is_better(self):
        """Brier score: lower is IMPROVING (not declining)."""
        engine = self._make_engine()
        engine.record_data_point("brier_score", 0.15, period="30d")
        engine.record_data_point("brier_score", 0.08, period="current")
        report = engine.generate_report()
        trend = [t for t in report.trends if t.name == "brier_score"]
        from maestro_oem.advanced_analytics import TrendDirection
        assert trend[0].direction == TrendDirection.IMPROVING  # lower = better

    def test_brier_score_tracking(self):
        """Brier scores are tracked and trended."""
        engine = self._make_engine()
        engine.record_brier_score(0.15)
        engine.record_brier_score(0.10)
        engine.record_brier_score(0.08)
        report = engine.generate_report()
        assert report.brier_score == 0.08
        assert report.brier_score_previous == 0.10
        from maestro_oem.advanced_analytics import TrendDirection
        assert report.brier_trend == TrendDirection.IMPROVING

    def test_commitment_rates(self):
        """Commitment kept/broken rates are computed correctly."""
        engine = self._make_engine()
        for _ in range(7):
            engine.record_commitment(kept=True)
        for _ in range(3):
            engine.record_commitment(kept=False)
        report = engine.generate_report()
        assert report.commitment_kept_rate == 70.0
        assert report.commitment_broken_rate == 30.0

    def test_meeting_grade_average(self):
        """Meeting grade average is computed from letter grades."""
        engine = self._make_engine()
        for grade in ["A", "B", "C", "B", "A"]:
            engine.record_meeting_grade(grade)
        report = engine.generate_report()
        # A=90, B=80, C=70, B=80, A=90 → avg = 82
        assert report.meeting_grade_average == 82.0

    def test_deal_cycle_time(self):
        """Deal cycle time average is computed correctly."""
        engine = self._make_engine()
        engine.record_deal_cycle_time(45.0)
        engine.record_deal_cycle_time(60.0)
        engine.record_deal_cycle_time(30.0)
        report = engine.generate_report()
        assert report.deal_cycle_time_days == 45.0  # (45+60+30)/3

    def test_law_promotion_tracking(self):
        """Law validation and candidate counts are tracked."""
        engine = self._make_engine()
        for _ in range(5):
            engine.record_law(validated=True)
        for _ in range(3):
            engine.record_law(validated=False)
        report = engine.generate_report()
        assert report.laws_validated == 5
        assert report.laws_candidate == 3

    def test_team_performance_aggregate_only(self):
        """Team performance is AGGREGATE (never individual surveillance)."""
        engine = self._make_engine()
        engine.record_team_metric("meeting_grade", 85.0)
        engine.record_team_metric("meeting_grade", 75.0)
        engine.record_team_metric("meeting_grade", 90.0)
        report = engine.generate_report()
        team_metrics = [tp for tp in report.team_performance if tp.metric_name == "meeting_grade"]
        assert len(team_metrics) >= 1
        assert abs(team_metrics[0].team_average - 83.33) < 0.01  # (85+75+90)/3
        assert team_metrics[0].team_count == 3
        # No individual names or IDs in team performance (aggregate only)
        for tp in report.team_performance:
            d = tp.to_dict()
            assert "individual" not in str(d).lower()
            assert "person" not in str(d).lower()

    def test_p25_confidence_has_denominator(self):
        """P25: team performance confidence shows denominator."""
        engine = self._make_engine()
        engine.record_team_metric("test_metric", 0.5)
        report = engine.generate_report()
        for tp in report.team_performance:
            assert "insufficient" in tp.confidence_label  # no calibration yet
            assert tp.calibration_denominator == 0

        for _ in range(12):
            engine.record_calibration()
        report2 = engine.generate_report()
        for tp in report2.team_performance:
            assert tp.calibration_denominator == 12
            assert "12" in tp.confidence_label

    def test_trend_has_evidence(self):
        """Every trend has evidence source (anti-Cluely)."""
        engine = self._make_engine()
        engine.record_data_point("test_metric", 0.5, period="30d")
        engine.record_data_point("test_metric", 0.7, period="current")
        report = engine.generate_report()
        for trend in report.trends:
            assert trend.evidence.get("source"), f"Trend missing evidence: {trend}"

    def test_flywheel_summary(self):
        """Flywheel summary describes whether the system is compounding."""
        engine = self._make_engine()
        engine.record_data_point("commitment_kept_rate", 0.65, period="30d")
        engine.record_data_point("commitment_kept_rate", 0.85, period="current")
        engine.record_brier_score(0.15)
        engine.record_brier_score(0.08)
        for _ in range(5):
            engine.record_law(validated=True)
        engine.record_commitment(kept=True)
        engine.record_commitment(kept=True)
        engine.record_commitment(kept=False)
        summary = engine.get_flywheel_summary()
        assert "improving" in summary.lower() or "declining" in summary.lower() or "stable" in summary.lower()
        assert "brier" in summary.lower()
        assert "laws" in summary.lower()

    def test_report_to_dict(self):
        """OrgLearningReport serializes correctly."""
        engine = self._make_engine()
        engine.record_data_point("test", 0.5, period="30d")
        engine.record_data_point("test", 0.7, period="current")
        engine.record_brier_score(0.08)
        engine.record_commitment(kept=True)
        engine.record_meeting_grade("A")
        engine.record_deal_cycle_time(45.0)
        engine.record_law(validated=True)
        engine.record_pattern()
        report = engine.generate_report()
        d = report.to_dict()
        assert "trends" in d
        assert "team_performance" in d
        assert "laws_validated" in d
        assert "brier_score" in d
        assert "commitment_kept_rate" in d
        assert "meeting_grade_average" in d
        assert "deal_cycle_time_days" in d

    def test_empty_engine_returns_valid_report(self):
        """Empty engine returns a valid (but empty) report."""
        engine = self._make_engine()
        report = engine.generate_report()
        assert report.trends == []
        assert report.brier_score is None
        assert report.commitment_kept_rate == 0.0


class TestPhase20MasterGate:
    """Phase 20 MASTER GATE: all prior tests must still pass + L0 intact."""

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

    def test_sarcasm_classification(self):
        from maestro_oem.content_epistemic_classifier import ContentEpistemicClassifier
        clf = ContentEpistemicClassifier()
        assert clf.classify("Great, SSO is totally ready \U0001f644") == "sarcasm"

    def test_artifact_classification(self):
        from maestro_oem.content_epistemic_classifier import ContentEpistemicClassifier
        clf = ContentEpistemicClassifier()
        assert clf.classify("The deployment log shows SSO failed.") == "artifact"
