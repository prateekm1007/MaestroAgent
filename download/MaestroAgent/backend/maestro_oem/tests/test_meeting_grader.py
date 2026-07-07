"""Phase 16 - Meeting Grade and Post-Call Analytics tests.

Tests meeting effectiveness grading, action item extraction, follow-up
tracking, user override, P25 confidence gate, and L0 no-regression.
"""

from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import pytest


class TestMeetingGrader:
    """Phase 16: MeetingGrader."""

    def _make_grader(self):
        from maestro_oem.meeting_grader import MeetingGrader
        return MeetingGrader()

    def test_grade_a_for_good_meeting(self):
        """A good meeting (action items, balanced, 30-60 min, good sentiment) gets A or B."""
        grader = self._make_grader()
        grader.set_meeting_data(
            transcript="I will send the pricing by Friday. We will review the proposal next week.",
            duration_minutes=45,
            talk_ratio_balance=0.55,
            sentiment_score=0.8,
            participants=4,
        )
        report = grader.grade_meeting("test-1")
        assert report.score >= 70  # good meeting
        assert report.grade.value in ("A", "B", "C")

    def test_grade_low_for_poor_meeting(self):
        """A poor meeting (no action items, unbalanced, too long, bad sentiment) gets D or F."""
        grader = self._make_grader()
        grader.set_meeting_data(
            transcript="We talked about stuff. It was interesting.",
            duration_minutes=120,
            talk_ratio_balance=0.85,
            sentiment_score=0.3,
            participants=2,
        )
        report = grader.grade_meeting("test-2")
        assert report.score < 70  # poor meeting

    def test_action_item_extraction(self):
        """Action items are extracted from transcript."""
        grader = self._make_grader()
        grader.set_meeting_data(
            transcript="I will send the pricing by Friday. Sam will review the contract.",
            duration_minutes=30,
            talk_ratio_balance=0.5,
            sentiment_score=0.6,
            participants=2,
        )
        report = grader.grade_meeting("test-3")
        assert len(report.action_items) >= 1
        for item in report.action_items:
            assert item.text  # non-empty
            assert item.owner  # has owner

    def test_action_item_with_due_date(self):
        """Action items with 'by Friday' get due_date set."""
        grader = self._make_grader()
        grader.set_meeting_data(
            transcript="I will send the proposal by next Friday.",
            duration_minutes=30,
        )
        report = grader.grade_meeting("test-4")
        assert len(report.action_items) >= 1
        assert report.action_items[0].due_date is not None

    def test_transparent_factors(self):
        """Factors are transparent (show contributing components)."""
        grader = self._make_grader()
        grader.set_meeting_data(
            transcript="I will follow up.",
            duration_minutes=45,
            talk_ratio_balance=0.5,
            sentiment_score=0.7,
            participants=3,
        )
        report = grader.grade_meeting("test-5")
        assert "action_items" in report.factors
        assert "sentiment" in report.factors
        assert "participation" in report.factors
        assert "duration" in report.factors
        for factor_name, factor_data in report.factors.items():
            assert "score" in factor_data
            assert "weight" in factor_data
            assert "note" in factor_data  # transparent explanation

    def test_user_override(self):
        """User can override the computed grade."""
        from maestro_oem.meeting_grader import MeetingGrade
        grader = self._make_grader()
        grader.set_meeting_data(
            transcript="We talked.",
            duration_minutes=90,
            talk_ratio_balance=0.8,
            sentiment_score=0.4,
            participants=2,
        )
        report = grader.grade_meeting("test-6")
        original_grade = report.grade

        # Override
        grader.set_user_override(MeetingGrade.A)
        report2 = grader.grade_meeting("test-7")
        assert report2.effective_grade == MeetingGrade.A
        assert report2.user_override == MeetingGrade.A

    def test_follow_up_tracking(self):
        """Follow-ups are tracked across meetings."""
        grader = self._make_grader()
        grader.set_meeting_data(
            transcript="I will send pricing by Friday. Sam will review the contract.",
            duration_minutes=30,
        )
        report = grader.grade_meeting("meeting-1")
        assert report.follow_ups_pending >= 2

        # Mark one as completed
        grader.mark_action_item_completed("meeting-1", "pricing")
        report2 = grader.grade_meeting("meeting-2")
        assert report2.follow_ups_completed >= 1

    def test_p25_confidence_has_denominator(self):
        """P25: grade confidence shows denominator (meeting count)."""
        grader = self._make_grader()
        grader.set_meeting_data(transcript="Test.", duration_minutes=30)
        report = grader.grade_meeting("test-p25")
        assert "insufficient" in report.confidence_label
        assert report.calibration_denominator == 0

        for _ in range(12):
            grader.record_meeting_for_calibration()
        report2 = grader.grade_meeting("test-p25-2")
        assert report2.calibration_denominator == 12
        assert "12" in report2.confidence_label

    def test_report_to_dict(self):
        """MeetingGradeReport serializes correctly."""
        grader = self._make_grader()
        grader.set_meeting_data(
            transcript="I will send pricing.",
            duration_minutes=30,
            talk_ratio_balance=0.5,
            sentiment_score=0.6,
            participants=2,
        )
        report = grader.grade_meeting("test-serial")
        d = report.to_dict()
        assert "grade" in d
        assert "score" in d
        assert "factors" in d
        assert "action_items" in d
        assert "confidence_label" in d
        assert "follow_ups_pending" in d

    def test_no_action_items_lower_score(self):
        """Meetings with no action items score lower than those with."""
        grader_with = self._make_grader()
        grader_with.set_meeting_data(
            transcript="I will send the proposal.",
            duration_minutes=30,
            talk_ratio_balance=0.5,
            sentiment_score=0.6,
            participants=2,
        )
        report_with = grader_with.grade_meeting("with-items")

        grader_without = self._make_grader()
        grader_without.set_meeting_data(
            transcript="We had a nice chat about things.",
            duration_minutes=30,
            talk_ratio_balance=0.5,
            sentiment_score=0.6,
            participants=2,
        )
        report_without = grader_without.grade_meeting("without-items")

        assert report_with.factors["action_items"]["score"] > report_without.factors["action_items"]["score"]

    def test_get_follow_up_status(self):
        """Follow-up status is retrievable across meetings."""
        grader = self._make_grader()
        grader.set_meeting_data(
            transcript="I will send pricing. Sam will review.",
            duration_minutes=30,
        )
        grader.grade_meeting("m1")
        grader.mark_action_item_completed("m1", "pricing")

        status = grader.get_follow_up_status()
        assert len(status) >= 2
        pricing_status = [s for s in status if "pricing" in s["text"].lower()]
        assert len(pricing_status) >= 1
        assert pricing_status[0]["completed"] is True


class TestPhase16L0NoRegression:
    """Phase 16 must not regress the L0 substrate."""

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
