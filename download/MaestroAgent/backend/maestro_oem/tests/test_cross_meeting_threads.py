"""Phase 14 — Cross-Meeting Thread Builder tests.

Tests topic linking, decision tracking, confidence scoring, and the
<70% manual-correction caveat from the reality check.
"""

from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from datetime import datetime, timedelta, timezone

import pytest


def make_meeting(meeting_id, title, entity, topics, attendees, decisions=None, days_ago=0):
    from maestro_oem.cross_meeting_threads import MeetingSummary
    return MeetingSummary(
        meeting_id=meeting_id,
        title=title,
        entity=entity,
        start_time=datetime.now(timezone.utc) - timedelta(days=days_ago),
        attendees=attendees,
        topics=topics,
        decisions=decisions or [],
        commitments=[],
    )


class TestCrossMeetingThreadBuilder:
    """Phase 14: Cross-Meeting Thread Builder."""

    def _make_builder(self):
        from maestro_oem.cross_meeting_threads import CrossMeetingThreadBuilder
        return CrossMeetingThreadBuilder()

    def test_high_confidence_thread_auto_links(self):
        """Meetings with strong topic + attendee overlap auto-link (>=70%)."""
        builder = self._make_builder()
        builder.add_meeting(make_meeting("m1", "Globex Pricing", "Globex",
            ["pricing", "volume discount"], ["raj@globex.com", "sam@globex.com"],
            decisions=["Offer 10% discount"], days_ago=14))
        builder.add_meeting(make_meeting("m2", "Globex Renewal", "Globex",
            ["pricing", "renewal"], ["raj@globex.com", "sam@globex.com"],
            decisions=["Confirmed 10% discount"], days_ago=7))

        threads = builder.build_threads()
        assert len(threads) >= 1
        thread = threads[0]
        assert thread.entity == "Globex"
        assert len(thread.meetings) >= 2

    def test_low_confidence_requires_confirmation(self):
        """Threads with <70% confidence require user confirmation."""
        builder = self._make_builder()
        # Same entity, 1 topic overlap, no attendee overlap, far apart
        builder.add_meeting(make_meeting("m1", "Globex Intro", "Globex",
            ["pricing"], ["personA@globex.com"], days_ago=90))
        builder.add_meeting(make_meeting("m2", "Globex Follow-up", "Globex",
            ["pricing"], ["personB@globex.com"], days_ago=1))

        threads = builder.build_threads()
        for thread in threads:
            if thread.confidence < 0.70:
                assert thread.requires_confirmation is True
                assert thread.confidence_level.value in ("medium", "low")

    def test_manual_confirmation(self):
        """User can confirm a low-confidence thread."""
        builder = self._make_builder()
        builder.add_meeting(make_meeting("m1", "Meeting 1", "Globex",
            ["pricing"], ["a@globex.com"], days_ago=60))
        builder.add_meeting(make_meeting("m2", "Meeting 2", "Globex",
            ["pricing"], ["b@globex.com"], days_ago=1))

        threads = builder.build_threads()
        if threads:
            thread_id = threads[0].thread_id
            builder.confirm_thread(thread_id)
            # Thread should still appear (confirmed)
            threads2 = builder.build_threads()
            assert any(t.thread_id == thread_id for t in threads2)

    def test_manual_rejection(self):
        """User can reject a suggested thread (manual correction)."""
        builder = self._make_builder()
        builder.add_meeting(make_meeting("m1", "Meeting 1", "Globex",
            ["pricing"], ["a@globex.com"], days_ago=60))
        builder.add_meeting(make_meeting("m2", "Meeting 2", "Globex",
            ["pricing"], ["b@globex.com"], days_ago=1))

        threads = builder.build_threads()
        if threads:
            thread_id = threads[0].thread_id
            builder.reject_thread(thread_id)
            threads2 = builder.build_threads()
            assert not any(t.thread_id == thread_id for t in threads2)

    def test_decision_chain_tracked(self):
        """Decisions are tracked across meetings."""
        builder = self._make_builder()
        builder.add_meeting(make_meeting("m1", "Globex Pricing", "Globex",
            ["pricing"], ["raj@globex.com"],
            decisions=["Offer 10% discount"], days_ago=14))
        builder.add_meeting(make_meeting("m2", "Globex Renewal", "Globex",
            ["pricing"], ["raj@globex.com"],
            decisions=["Confirmed 10% discount"], days_ago=7))

        threads = builder.build_threads()
        assert len(threads) >= 1
        thread = threads[0]
        assert len(thread.decision_chain) >= 2
        decisions = [d["decision"] for d in thread.decision_chain]
        assert any("discount" in d.lower() for d in decisions)

    def test_topic_evolution_tracked(self):
        """Topic evolution is tracked across meetings."""
        builder = self._make_builder()
        builder.add_meeting(make_meeting("m1", "Globex Pricing", "Globex",
            ["pricing", "volume discount"], ["raj@globex.com"], days_ago=14))
        builder.add_meeting(make_meeting("m2", "Globex Renewal", "Globex",
            ["pricing", "renewal", "contract terms"], ["raj@globex.com"], days_ago=7))

        threads = builder.build_threads()
        assert len(threads) >= 1
        thread = threads[0]
        # Topic evolution should include topics from both meetings
        assert len(thread.topic_evolution) >= 2

    def test_different_entities_not_linked(self):
        """Meetings about different entities are not linked."""
        builder = self._make_builder()
        builder.add_meeting(make_meeting("m1", "Globex Meeting", "Globex",
            ["pricing"], ["raj@globex.com"], days_ago=7))
        builder.add_meeting(make_meeting("m2", "Initech Meeting", "Initech",
            ["pricing"], ["raj@initech.com"], days_ago=1))

        threads = builder.build_threads()
        # Each entity gets its own thread (or no thread if only 1 meeting)
        for thread in threads:
            assert thread.entity in ("Globex", "Initech")
            # No thread should contain meetings from both entities
            entities_in_thread = set(m.entity for m in thread.meetings)
            assert len(entities_in_thread) == 1

    def test_thread_to_dict(self):
        """MeetingThread serializes correctly."""
        builder = self._make_builder()
        builder.add_meeting(make_meeting("m1", "Globex Pricing", "Globex",
            ["pricing"], ["raj@globex.com"], decisions=["Test decision"], days_ago=7))
        builder.add_meeting(make_meeting("m2", "Globex Follow-up", "Globex",
            ["pricing"], ["raj@globex.com"], days_ago=1))

        threads = builder.build_threads()
        if threads:
            d = threads[0].to_dict()
            assert "thread_id" in d
            assert "entity" in d
            assert "meetings" in d
            assert "confidence" in d
            assert "requires_confirmation" in d
            assert "decision_chain" in d

    def test_keyword_based_topic_matching(self):
        """Topics phrased differently are matched via keywords."""
        builder = self._make_builder()
        builder.add_meeting(make_meeting("m1", "Globex Cost Discussion", "Globex",
            ["cost discussion"], ["raj@globex.com"], days_ago=7))
        builder.add_meeting(make_meeting("m2", "Globex Budget Review", "Globex",
            ["budget review"], ["raj@globex.com"], days_ago=1))

        threads = builder.build_threads()
        # "cost" and "budget" both map to the "pricing" keyword category
        assert len(threads) >= 1

    def test_get_decision_history(self):
        """Decision history is retrievable for an entity."""
        builder = self._make_builder()
        builder.add_meeting(make_meeting("m1", "Globex 1", "Globex",
            ["pricing"], ["raj@globex.com"], decisions=["Decision A"], days_ago=14))
        builder.add_meeting(make_meeting("m2", "Globex 2", "Globex",
            ["pricing"], ["raj@globex.com"], decisions=["Decision B"], days_ago=7))

        decisions = builder.get_decision_history("Globex")
        assert len(decisions) >= 2
        decision_texts = [d["decision"] for d in decisions]
        assert "Decision A" in decision_texts
        assert "Decision B" in decision_texts


class TestPhase14L0NoRegression:
    """Phase 14 must not regress the L0 substrate."""

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
