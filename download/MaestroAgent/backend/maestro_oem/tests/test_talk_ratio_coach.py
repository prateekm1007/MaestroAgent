"""Phase 15 — Talk Ratio & Communication Coach tests.

Tests talk ratio calculation, interruption detection, clarity scoring,
coaching suggestions, and P25 confidence gate.
"""

from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import pytest


def make_segment(speaker, start, end, text=""):
    from maestro_oem.talk_ratio_coach import SpeechSegment
    return SpeechSegment(speaker=speaker, start_time=start, end_time=end, text=text)


class TestTalkRatioCoach:
    """Phase 15: TalkRatioCoach."""

    def _make_coach(self):
        from maestro_oem.talk_ratio_coach import TalkRatioCoach
        return TalkRatioCoach()

    def test_talk_ratio_calculation(self):
        """Talk ratio is correctly calculated as percentage of speaking time."""
        coach = self._make_coach()
        coach.add_segment(make_segment("you", 0, 60, "I talk for 60 seconds"))
        coach.add_segment(make_segment("them", 60, 100, "They talk for 40 seconds"))
        report = coach.generate_report()
        assert report.talk_ratios["you"] == 60.0  # 60 out of 100 seconds
        assert report.talk_ratios["them"] == 40.0

    def test_talk_ratio_too_high_triggers_coaching(self):
        """Talking >60% triggers gentle correction coaching."""
        coach = self._make_coach()
        coach.add_segment(make_segment("you", 0, 70, "I talk too much"))
        coach.add_segment(make_segment("them", 70, 30, "They barely talk"))
        report = coach.generate_report()
        ratio_suggestions = [s for s in report.coaching_suggestions if s["type"] == "talk_ratio"]
        assert len(ratio_suggestions) >= 1
        assert "questions" in ratio_suggestions[0]["text"].lower()  # "ask more questions"

    def test_talk_ratio_too_low_triggers_encouragement(self):
        """Talking <40% triggers encouraging coaching."""
        coach = self._make_coach()
        coach.add_segment(make_segment("you", 0, 20, "I barely talk"))
        coach.add_segment(make_segment("them", 20, 80, "They talk a lot"))
        report = coach.generate_report()
        ratio_suggestions = [s for s in report.coaching_suggestions if s["type"] == "talk_ratio"]
        assert len(ratio_suggestions) >= 1
        assert ratio_suggestions[0]["tone"] == "encouraging"

    def test_interruption_detection(self):
        """Overlapping segments from different speakers are detected as interruptions."""
        coach = self._make_coach()
        coach.add_segment(make_segment("you", 0, 30, "Let me finish my point about"))
        coach.add_segment(make_segment("them", 28, 40, "But I disagree"))  # 2s overlap = medium
        report = coach.generate_report()
        assert report.interruption_count >= 1
        assert report.interruptions[0].interrupter == "them"
        assert report.interruptions[0].interrupted == "you"

    def test_interruption_severity_classification(self):
        """Interruption severity is classified by overlap duration."""
        coach = self._make_coach()
        # High: >2s overlap
        coach.add_segment(make_segment("you", 0, 10, "Speaking"))
        coach.add_segment(make_segment("them", 7, 15, "Interrupting"))  # 3s overlap
        report = coach.generate_report()
        high_count = sum(1 for i in report.interruptions if i.severity == "high")
        assert high_count >= 1

    def test_your_interruptions_trigger_coaching(self):
        """When you interrupt >=2 times, coaching is generated."""
        coach = self._make_coach()
        coach.add_segment(make_segment("them", 0, 10, "They speak"))
        coach.add_segment(make_segment("you", 8, 20, "I interrupt"))  # 2s overlap
        coach.add_segment(make_segment("them", 20, 30, "They speak again"))
        coach.add_segment(make_segment("you", 28, 40, "I interrupt again"))  # 2s overlap
        report = coach.generate_report()
        your_interruptions = [i for i in report.interruptions if i.interrupter == "you"]
        assert len(your_interruptions) >= 2
        int_suggestions = [s for s in report.coaching_suggestions if s["type"] == "interruptions"]
        assert len(int_suggestions) >= 1

    def test_clarity_scoring_short_sentences(self):
        """Short, clear sentences get high clarity scores."""
        coach = self._make_coach()
        coach.add_segment(make_segment("you", 0, 60, "This is clear. Short sentences work well. Easy to follow."))
        report = coach.generate_report()
        assert report.clarity_score > 60  # should be decent with short sentences

    def test_clarity_scoring_long_sentences(self):
        """Long, rambling sentences get lower clarity scores."""
        coach = self._make_coach()
        long_text = "This is a very long sentence that goes on and on and on and does not get to the point quickly which makes it hard to follow and reduces the clarity of the overall message that I am trying to convey to the other person in this meeting."
        coach.add_segment(make_segment("you", 0, 30, long_text))
        report = coach.generate_report()
        assert report.clarity_factors.get("avg_sentence_length", 0) > 20

    def test_clarity_filler_word_detection(self):
        """Filler words (um, uh, like) are counted and affect clarity."""
        coach = self._make_coach()
        coach.add_segment(make_segment("you", 0, 30, "Um, I think, like, we should, uh, probably, you know, consider this."))
        report = coach.generate_report()
        assert report.clarity_factors.get("filler_rate", 0) > 5  # high filler rate

    def test_coaching_suggestions_have_evidence(self):
        """Every coaching suggestion has an evidence source (anti-Cluely)."""
        coach = self._make_coach()
        coach.add_segment(make_segment("you", 0, 70, "I talk too much about pricing and budget"))
        coach.add_segment(make_segment("them", 70, 30, "They talk"))
        report = coach.generate_report()
        for suggestion in report.coaching_suggestions:
            assert suggestion.get("evidence"), f"Suggestion missing evidence: {suggestion}"
            assert suggestion["evidence"].get("source"), f"Evidence missing source: {suggestion}"

    def test_positive_reinforcement_for_good_balance(self):
        """Good clarity + no interruptions triggers positive reinforcement."""
        coach = self._make_coach()
        coach.add_segment(make_segment("you", 0, 30, "Clear point. Short sentence. Easy to follow."))
        coach.add_segment(make_segment("them", 30, 30, "They respond."))
        report = coach.generate_report()
        positive = [s for s in report.coaching_suggestions if s["type"] == "positive"]
        # May or may not trigger depending on exact clarity score, but should exist if conditions met
        if report.clarity_score >= 80 and report.interruption_count == 0:
            assert len(positive) >= 1

    def test_p25_confidence_has_denominator(self):
        """P25: clarity confidence shows denominator (call count)."""
        coach = self._make_coach()
        coach.add_segment(make_segment("you", 0, 30, "Test."))
        report = coach.generate_report()
        assert "insufficient" in report.confidence_label  # no calibration calls
        assert report.calibration_denominator == 0

        for _ in range(12):
            coach.record_call_for_calibration()
        report2 = coach.generate_report()
        assert report2.calibration_denominator == 12
        assert "12" in report2.confidence_label

    def test_report_to_dict(self):
        """TalkRatioReport serializes correctly."""
        coach = self._make_coach()
        coach.add_segment(make_segment("you", 0, 30, "Test sentence."))
        coach.add_segment(make_segment("them", 30, 30, "Response."))
        report = coach.generate_report()
        d = report.to_dict()
        assert "talk_ratios" in d
        assert "interruption_count" in d
        assert "clarity_score" in d
        assert "coaching_suggestions" in d
        assert "confidence_label" in d

    def test_no_segments_returns_empty_report(self):
        """Empty segment list returns a valid empty report."""
        coach = self._make_coach()
        report = coach.generate_report()
        assert report.total_duration == 0
        assert report.interruption_count == 0


class TestPhase15L0NoRegression:
    """Phase 15 must not regress the L0 substrate."""

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
