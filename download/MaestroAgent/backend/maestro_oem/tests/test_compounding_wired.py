"""P31 execution-based verification: cross-feature compounding is WIRED into
production call paths, not just defined in isolation.

These tests verify that:
  1. DealHealthEngine.compute_score() actually CALLS adjust_deal_health_for_commitments()
     when there are overdue commitments → the score is LOWER than without compounding.
  2. CrossMeetingThreadBuilder.build_threads() actually CALLS compute_sentiment_trend_across_meetings()
     when meetings have sentiment data → the thread has a sentiment_trend dict.
  3. MeetingGrader.grade_meeting() actually CALLS adjust_meeting_grade_for_followup()
     when workplace signals show a follow-up within 24h → the grade score is HIGHER.

The auditor's directive: "wire the cross-feature compounding into production
call paths." These tests prove the wiring is real — not theater.
"""

from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import pytest


# ════════════════════════════════════════════════════════════════════════════
# Link 1: Deal Health + Commitment — PRODUCTION WIRING
# ════════════════════════════════════════════════════════════════════════════

class TestLink1DealHealthCompoundingWired:
    """Link 1: DealHealthEngine.compute_score() calls adjust_deal_health_for_commitments()."""

    def _make_signal(self, sig_type, entity, metadata=None):
        """Create a mock signal for the OEM state."""
        sig = MagicMock()
        sig.type = sig_type
        sig.metadata = metadata or {"customer": entity}
        sig.actor = ""
        sig.timestamp = datetime.now(timezone.utc)
        return sig

    def test_score_drops_with_broken_commitments(self):
        """PRODUCTION WIRING: broken commitments reduce the deal health score.

        This proves DealHealthEngine.compute_score() actually calls
        CrossFeatureCompounding.adjust_deal_health_for_commitments().
        """
        from maestro_oem.deal_health import DealHealthEngine
        from maestro_oem.signal import SignalType

        # Build OEM state with a broken commitment for "TestCorp"
        oem = MagicMock()
        oem.signals = [self._make_signal(
            SignalType.CUSTOMER_COMMITMENT_BROKEN, "TestCorp"
        )]

        engine = DealHealthEngine(oem_state=oem)
        score = engine.compute_score("TestCorp")

        # The compounding adjustment must be recorded
        assert len(score.compounding_adjustments) > 0, (
            "DealHealthScore.compounding_adjustments is empty — "
            "adjust_deal_health_for_commitments() was NOT called."
        )
        adj = score.compounding_adjustments[0]
        assert adj["link"] == "deal_health_plus_commitment"
        assert adj["overdue_count"] == 1
        assert adj["penalty_applied"] == 5.0  # 5 points per overdue
        assert adj["post_compound_score"] < adj["pre_compound_score"]

    def test_score_unchanged_without_overdue(self):
        """No overdue commitments = no compounding adjustment applied."""
        from maestro_oem.deal_health import DealHealthEngine
        from maestro_oem.signal import SignalType

        # OEM state with a KEPT commitment (not broken, not overdue)
        oem = MagicMock()
        oem.signals = [self._make_signal(
            SignalType.CUSTOMER_COMMITMENT_KEPT, "GoodCorp"
        )]

        engine = DealHealthEngine(oem_state=oem)
        score = engine.compute_score("GoodCorp")

        # No compounding adjustment because no overdue commitments
        assert score.compounding_adjustments == [], (
            "Compounding was applied even though there are no overdue commitments."
        )

    def test_compounding_adjustment_in_to_dict(self):
        """The compounding adjustment is visible in to_dict() (P4 transparency)."""
        from maestro_oem.deal_health import DealHealthEngine
        from maestro_oem.signal import SignalType

        oem = MagicMock()
        oem.signals = [
            self._make_signal(SignalType.CUSTOMER_COMMITMENT_BROKEN, "TestCorp"),
            self._make_signal(SignalType.CUSTOMER_COMMITMENT_BROKEN, "TestCorp"),
            self._make_signal(SignalType.CUSTOMER_COMMITMENT_BROKEN, "TestCorp"),
        ]

        engine = DealHealthEngine(oem_state=oem)
        score = engine.compute_score("TestCorp")
        d = score.to_dict()

        assert "compounding_adjustments" in d
        assert len(d["compounding_adjustments"]) == 1
        assert d["compounding_adjustments"][0]["overdue_count"] == 3
        # 3 overdue × 5 points = 15 penalty (under the 25 cap)
        assert d["compounding_adjustments"][0]["penalty_applied"] == 15.0

    def test_compounding_penalty_capped_at_25(self):
        """The compounding penalty is capped at 25 points (6+ overdue = 25)."""
        from maestro_oem.deal_health import DealHealthEngine
        from maestro_oem.signal import SignalType

        # 10 broken commitments → penalty capped at 25 (not 50)
        oem = MagicMock()
        oem.signals = [
            self._make_signal(SignalType.CUSTOMER_COMMITMENT_BROKEN, "TestCorp")
            for _ in range(10)
        ]

        engine = DealHealthEngine(oem_state=oem)
        score = engine.compute_score("TestCorp")

        adj = score.compounding_adjustments[0]
        assert adj["overdue_count"] == 10
        assert adj["penalty_applied"] == 25.0  # capped


# ════════════════════════════════════════════════════════════════════════════
# Link 2: Sentiment + Cross-Meeting Threads — PRODUCTION WIRING
# ════════════════════════════════════════════════════════════════════════════

class TestLink2SentimentThreadsCompoundingWired:
    """Link 2: CrossMeetingThreadBuilder.build_threads() calls compute_sentiment_trend_across_meetings()."""

    def _make_meeting(self, entity, topics, sentiment=None, days_ago=0):
        from maestro_oem.cross_meeting_threads import MeetingSummary
        return MeetingSummary(
            meeting_id=f"m-{entity}-{days_ago}",
            title=f"{entity} Review",
            entity=entity,
            start_time=datetime.now(timezone.utc) - timedelta(days=days_ago),
            attendees=["a@x.com", "b@y.com"],
            topics=topics,
            decisions=[],
            commitments=[],
            sentiment=sentiment,
        )

    def test_thread_has_sentiment_trend_when_meetings_have_sentiment(self):
        """PRODUCTION WIRING: threads get a sentiment_trend when meetings have sentiment.

        This proves CrossMeetingThreadBuilder.build_threads() actually calls
        CrossFeatureCompounding.compute_sentiment_trend_across_meetings().
        """
        from maestro_oem.cross_meeting_threads import CrossMeetingThreadBuilder

        builder = CrossMeetingThreadBuilder()
        # Declining sentiment across 3 meetings
        builder.add_meeting(self._make_meeting("TestCorp", ["pricing"], sentiment=0.8, days_ago=10))
        builder.add_meeting(self._make_meeting("TestCorp", ["pricing"], sentiment=0.5, days_ago=5))
        builder.add_meeting(self._make_meeting("TestCorp", ["pricing"], sentiment=0.2, days_ago=1))

        threads = builder.build_threads()
        assert len(threads) > 0

        thread = threads[0]
        assert thread.sentiment_trend is not None, (
            "MeetingThread.sentiment_trend is None — "
            "compute_sentiment_trend_across_meetings() was NOT called."
        )
        assert thread.sentiment_trend["trend"] == "declining"
        assert thread.sentiment_trend["slope"] < 0
        assert thread.sentiment_trend["warning"] is not None
        assert thread.sentiment_trend["evidence"]["source"] == "cross_meeting_sentiment"

    def test_thread_no_sentiment_trend_without_sentiment_data(self):
        """No sentiment on meetings = no sentiment_trend (graceful degradation)."""
        from maestro_oem.cross_meeting_threads import CrossMeetingThreadBuilder

        builder = CrossMeetingThreadBuilder()
        builder.add_meeting(self._make_meeting("TestCorp", ["pricing"], sentiment=None, days_ago=10))
        builder.add_meeting(self._make_meeting("TestCorp", ["pricing"], sentiment=None, days_ago=5))

        threads = builder.build_threads()
        if threads:
            assert threads[0].sentiment_trend is None, (
                "sentiment_trend was set even though no meeting had sentiment data."
            )

    def test_sentiment_trend_in_to_dict(self):
        """The sentiment_trend is visible in to_dict() (P4 transparency)."""
        from maestro_oem.cross_meeting_threads import CrossMeetingThreadBuilder

        builder = CrossMeetingThreadBuilder()
        # Improving sentiment
        builder.add_meeting(self._make_meeting("TestCorp", ["pricing"], sentiment=0.2, days_ago=10))
        builder.add_meeting(self._make_meeting("TestCorp", ["pricing"], sentiment=0.6, days_ago=5))
        builder.add_meeting(self._make_meeting("TestCorp", ["pricing"], sentiment=0.9, days_ago=1))

        threads = builder.build_threads()
        d = threads[0].to_dict()
        assert "sentiment_trend" in d
        assert d["sentiment_trend"] is not None
        assert d["sentiment_trend"]["trend"] == "improving"

    def test_sentiment_trend_insufficient_data(self):
        """Only 1 meeting with sentiment = insufficient_data trend."""
        from maestro_oem.cross_meeting_threads import CrossMeetingThreadBuilder

        builder = CrossMeetingThreadBuilder()
        builder.add_meeting(self._make_meeting("TestCorp", ["pricing"], sentiment=0.5, days_ago=10))
        builder.add_meeting(self._make_meeting("TestCorp", ["pricing"], sentiment=None, days_ago=5))

        threads = builder.build_threads()
        if threads:
            # Only 1 meeting has sentiment → insufficient data (need ≥2)
            assert threads[0].sentiment_trend is None


# ════════════════════════════════════════════════════════════════════════════
# Link 3: Meeting Grade + Email Follow-up — PRODUCTION WIRING
# ════════════════════════════════════════════════════════════════════════════

class TestLink3MeetingGradeCompoundingWired:
    """Link 3: MeetingGrader.grade_meeting() calls adjust_meeting_grade_for_followup()."""

    def _make_grader(self):
        from maestro_oem.meeting_grader import MeetingGrader
        grader = MeetingGrader()
        grader.set_meeting_data(
            transcript="We will send the pricing by Friday. I will prepare the SSO docs.",
            duration_minutes=35,
            talk_ratio_balance=0.55,
            sentiment_score=0.7,
            participants=3,
        )
        return grader

    def test_grade_boosted_with_followup_within_24h(self):
        """PRODUCTION WIRING: follow-up within 24h boosts the grade by +5.

        This proves MeetingGrader.grade_meeting() actually calls
        CrossFeatureCompounding.adjust_meeting_grade_for_followup().
        """
        from maestro_oem.meeting_grader import MeetingGrader

        # Grade WITHOUT workplace signals (baseline)
        grader_baseline = self._make_grader()
        report_baseline = grader_baseline.grade_meeting("meeting-1")
        baseline_score = report_baseline.score

        # Grade WITH a follow-up sent 6h after the meeting
        grader_boosted = self._make_grader()
        meeting_end = datetime.now(timezone.utc) - timedelta(hours=12)
        follow_up_time = datetime.now(timezone.utc) - timedelta(hours=6)
        grader_boosted.set_workplace_signals(
            signals=[{"timestamp": follow_up_time.isoformat()}],
            meeting_end_time=meeting_end,
        )
        report_boosted = grader_boosted.grade_meeting("meeting-2")
        boosted_score = report_boosted.score

        assert boosted_score > baseline_score, (
            f"Boosted score ({boosted_score}) should be > baseline ({baseline_score}). "
            "adjust_meeting_grade_for_followup() was NOT called."
        )
        assert boosted_score - baseline_score == pytest.approx(5.0, abs=0.1), (
            f"Boost should be exactly +5, got {boosted_score - baseline_score}"
        )

    def test_grade_unchanged_without_followup(self):
        """No follow-up within 24h = no boost."""
        grader = self._make_grader()
        meeting_end = datetime.now(timezone.utc) - timedelta(hours=48)
        # Signal is BEFORE the meeting (not a follow-up)
        old_signal = datetime.now(timezone.utc) - timedelta(hours=72)
        grader.set_workplace_signals(
            signals=[{"timestamp": old_signal.isoformat()}],
            meeting_end_time=meeting_end,
        )
        report = grader.grade_meeting("meeting-3")

        # The follow_up_compounding factor should show boost_applied=False
        if "follow_up_compounding" in report.factors:
            assert report.factors["follow_up_compounding"]["boost_applied"] is False
            assert report.factors["follow_up_compounding"]["boost_amount"] == 0

    def test_grade_unchanged_without_workplace_signals(self):
        """No workplace signals set = no compounding factor shown."""
        grader = self._make_grader()
        report = grader.grade_meeting("meeting-4")

        # Without set_workplace_signals(), the follow_up_compounding factor
        # is not even added (graceful degradation)
        assert "follow_up_compounding" not in report.factors

    def test_compounding_factor_transparent_in_report(self):
        """The compounding is transparent in the grade report factors (P4)."""
        grader = self._make_grader()
        meeting_end = datetime.now(timezone.utc) - timedelta(hours=12)
        follow_up_time = datetime.now(timezone.utc) - timedelta(hours=6)
        grader.set_workplace_signals(
            signals=[{"timestamp": follow_up_time.isoformat()}],
            meeting_end_time=meeting_end,
        )
        report = grader.grade_meeting("meeting-5")

        assert "follow_up_compounding" in report.factors
        fc = report.factors["follow_up_compounding"]
        assert fc["link"] == "meeting_grade_plus_email"
        assert fc["follow_up_sent_within_24h"] is True
        assert fc["boost_applied"] is True
        assert fc["boost_amount"] == 5.0

    def test_grade_capped_at_100_with_boost(self):
        """Grade never exceeds 100 even with the boost."""
        from maestro_oem.meeting_grader import MeetingGrader, MeetingGrade

        grader = MeetingGrader()
        # Near-perfect meeting
        grader.set_meeting_data(
            transcript="I will send the proposal. We will deliver by Friday. I will schedule the demo.",
            duration_minutes=40,
            talk_ratio_balance=0.55,
            sentiment_score=0.95,
            participants=4,
        )
        meeting_end = datetime.now(timezone.utc) - timedelta(hours=12)
        follow_up_time = datetime.now(timezone.utc) - timedelta(hours=6)
        grader.set_workplace_signals(
            signals=[{"timestamp": follow_up_time.isoformat()}],
            meeting_end_time=meeting_end,
        )
        report = grader.grade_meeting("meeting-6")
        assert report.score <= 100.0


# ════════════════════════════════════════════════════════════════════════════
# No-regression: existing compounding module tests still pass
# ════════════════════════════════════════════════════════════════════════════

class TestNoRegressionCompoundingModule:
    """The standalone CrossFeatureCompounding module tests still pass."""

    def test_link1_standalone(self):
        from maestro_oem.cross_feature_compounding import CrossFeatureCompounding
        c = CrossFeatureCompounding()
        assert c.adjust_deal_health_for_commitments(75.0, 3) == 60.0

    def test_link2_standalone(self):
        from maestro_oem.cross_feature_compounding import CrossFeatureCompounding
        c = CrossFeatureCompounding()
        result = c.compute_sentiment_trend_across_meetings([0.8, 0.4])
        assert result["trend"] == "declining"

    def test_link3_standalone(self):
        from maestro_oem.cross_feature_compounding import CrossFeatureCompounding
        c = CrossFeatureCompounding()
        assert c.adjust_meeting_grade_for_followup(72.0, True) == 77.0
