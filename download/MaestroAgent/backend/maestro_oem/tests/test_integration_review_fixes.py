"""System Integration Review fixes — data volume + weak compounding links.

Tests the Phase 1 (data volume management) and Phase 2 (weak compounding)
fixes from the MAESTRO_SYSTEM_INTEGRATION_REVIEW.md.
"""

from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from datetime import datetime, timedelta, timezone

import pytest


class TestSignalVolumeManager:
    """Phase 1: Data Volume Management."""

    def _make_manager(self):
        from maestro_oem.signal_volume_manager import SignalVolumeManager
        return SignalVolumeManager()

    def test_noise_filtered_newsletter(self):
        """Newsletters are filtered out."""
        mgr = self._make_manager()
        assert mgr.should_process("news@company.com", "Weekly Newsletter - Unsubscribe", "Click here to unsubscribe") is False

    def test_noise_filtered_noreply(self):
        """No-reply addresses are filtered."""
        mgr = self._make_manager()
        assert mgr.should_process("noreply@github.com", "PR merged", "Your PR was merged") is False

    def test_noise_filtered_auto_reply(self):
        """Auto-replies are filtered."""
        mgr = self._make_manager()
        assert mgr.should_process("raj@acme.com", "Out of office", "I am on vacation") is False

    def test_high_signal_processed(self):
        """High-signal emails are processed."""
        mgr = self._make_manager()
        assert mgr.should_process("raj@acme.com", "SSO deployment", "We will deliver SSO by Friday") is True

    def test_classify_intent_commitment(self):
        """Commitments are classified correctly."""
        mgr = self._make_manager()
        from maestro_oem.signal_volume_manager import SignalIntent
        assert mgr.classify_intent("We will deliver SSO by Friday") == SignalIntent.COMMITMENT

    def test_classify_intent_decision(self):
        """Decisions are classified correctly."""
        mgr = self._make_manager()
        from maestro_oem.signal_volume_manager import SignalIntent
        assert mgr.classify_intent("We decided to go with the phased approach") == SignalIntent.DECISION

    def test_classify_intent_informational(self):
        """Low-signal content is classified as informational."""
        mgr = self._make_manager()
        from maestro_oem.signal_volume_manager import SignalIntent
        assert mgr.classify_intent("The weather is nice today") == SignalIntent.INFORMATIONAL

    def test_summarize_short_text_unchanged(self):
        """Short text is not summarized."""
        mgr = self._make_manager()
        assert mgr.summarize("Short text.", max_length=200) == "Short text."

    def test_summarize_long_text_truncated(self):
        """Long text is summarized to max_length."""
        mgr = self._make_manager()
        long_text = "This is a sentence. " * 50  # ~1000 chars
        summary = mgr.summarize(long_text, max_length=100)
        assert len(summary) <= 103  # max_length + "..."
        assert summary.endswith("...")

    def test_retention_high_signal_always_retained(self):
        """High-signal intents are always retained."""
        mgr = self._make_manager()
        from maestro_oem.signal_volume_manager import SignalIntent
        old_timestamp = datetime.now(timezone.utc) - timedelta(days=365)
        assert mgr.should_retain(old_timestamp, SignalIntent.COMMITMENT, days=30) is True
        assert mgr.should_retain(old_timestamp, SignalIntent.DECISION, days=30) is True

    def test_retention_informational_expired(self):
        """Informational signals are deleted after 30 days."""
        mgr = self._make_manager()
        from maestro_oem.signal_volume_manager import SignalIntent
        old_timestamp = datetime.now(timezone.utc) - timedelta(days=60)
        assert mgr.should_retain(old_timestamp, SignalIntent.INFORMATIONAL, days=30) is False

    def test_retention_informational_recent(self):
        """Recent informational signals are retained."""
        mgr = self._make_manager()
        from maestro_oem.signal_volume_manager import SignalIntent
        recent_timestamp = datetime.now(timezone.utc) - timedelta(days=5)
        assert mgr.should_retain(recent_timestamp, SignalIntent.INFORMATIONAL, days=30) is True

    def test_filter_stats(self):
        """Filter statistics are tracked."""
        mgr = self._make_manager()
        mgr.should_process("noreply@test.com", "Newsletter", "Unsubscribe")
        mgr.should_process("raj@acme.com", "SSO", "We will deliver")
        stats = mgr.get_stats()
        assert stats["total_seen"] >= 2
        assert stats["filtered_noise"] >= 1
        assert stats["processed"] >= 1


class TestCrossFeatureCompounding:
    """Phase 2: Weak compounding links strengthened."""

    def _make_compounding(self):
        from maestro_oem.cross_feature_compounding import CrossFeatureCompounding
        return CrossFeatureCompounding()

    def test_link1_deal_health_drops_with_overdue(self):
        """Link 1: Deal health drops 5 points per overdue commitment."""
        c = self._make_compounding()
        adjusted = c.adjust_deal_health_for_commitments(base_score=75.0, overdue_count=3)
        assert adjusted == 60.0  # 75 - 3*5 = 60

    def test_link1_deal_health_capped_penalty(self):
        """Link 1: Penalty capped at 25 points."""
        c = self._make_compounding()
        adjusted = c.adjust_deal_health_for_commitments(base_score=75.0, overdue_count=10)
        assert adjusted == 50.0  # 75 - 25 (capped) = 50

    def test_link1_deal_health_no_overdue(self):
        """Link 1: No overdue commitments = no penalty."""
        c = self._make_compounding()
        adjusted = c.adjust_deal_health_for_commitments(base_score=75.0, overdue_count=0)
        assert adjusted == 75.0

    def test_link1_deal_health_floor_zero(self):
        """Link 1: Score never goes below 0."""
        c = self._make_compounding()
        adjusted = c.adjust_deal_health_for_commitments(base_score=10.0, overdue_count=10)
        assert adjusted == 0.0  # 10 - 25 = -15 → floor at 0

    def test_link2_sentiment_declining(self):
        """Link 2: Declining sentiment trend detected."""
        c = self._make_compounding()
        result = c.compute_sentiment_trend_across_meetings([0.8, 0.6, 0.4, 0.2])
        assert result["trend"] == "declining"
        assert result["warning"] is not None
        assert "declining" in result["warning"].lower()

    def test_link2_sentiment_improving(self):
        """Link 2: Improving sentiment trend detected."""
        c = self._make_compounding()
        result = c.compute_sentiment_trend_across_meetings([0.2, 0.4, 0.6, 0.8])
        assert result["trend"] == "improving"
        assert result["warning"] is not None

    def test_link2_sentiment_stable(self):
        """Link 2: Stable sentiment trend detected."""
        c = self._make_compounding()
        result = c.compute_sentiment_trend_across_meetings([0.5, 0.52, 0.51, 0.5])
        assert result["trend"] == "stable"
        assert result["warning"] is None

    def test_link2_sentiment_insufficient_data(self):
        """Link 2: Insufficient data with <2 meetings."""
        c = self._make_compounding()
        result = c.compute_sentiment_trend_across_meetings([0.5])
        assert result["trend"] == "insufficient_data"

    def test_link2_sentiment_has_evidence(self):
        """Link 2: Trend has evidence source (anti-Cluely)."""
        c = self._make_compounding()
        result = c.compute_sentiment_trend_across_meetings([0.8, 0.4])
        assert result["evidence"].get("source") == "cross_meeting_sentiment"

    def test_link3_grade_boosted_with_followup(self):
        """Link 3: Meeting grade boosted +5 if follow-up sent within 24h."""
        c = self._make_compounding()
        adjusted = c.adjust_meeting_grade_for_followup(base_grade_score=72.0, follow_up_sent_within_24h=True)
        assert adjusted == 77.0

    def test_link3_grade_unchanged_without_followup(self):
        """Link 3: No boost if no follow-up sent."""
        c = self._make_compounding()
        adjusted = c.adjust_meeting_grade_for_followup(base_grade_score=72.0, follow_up_sent_within_24h=False)
        assert adjusted == 72.0

    def test_link3_grade_capped_at_100(self):
        """Link 3: Grade never exceeds 100."""
        c = self._make_compounding()
        adjusted = c.adjust_meeting_grade_for_followup(base_grade_score=98.0, follow_up_sent_within_24h=True)
        assert adjusted == 100.0

    def test_link3_check_follow_up_sent_true(self):
        """Link 3: Follow-up detected within 24h."""
        c = self._make_compounding()
        meeting_end = datetime.now(timezone.utc) - timedelta(hours=12)
        signals = [
            {"timestamp": (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()},
        ]
        assert c.check_follow_up_sent(meeting_end, signals) is True

    def test_link3_check_follow_up_sent_false(self):
        """Link 3: No follow-up within 24h."""
        c = self._make_compounding()
        meeting_end = datetime.now(timezone.utc) - timedelta(hours=48)
        signals = [
            {"timestamp": (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()},  # before meeting
        ]
        assert c.check_follow_up_sent(meeting_end, signals) is False

    def test_link3_check_follow_up_sent_empty(self):
        """Link 3: No signals = no follow-up."""
        c = self._make_compounding()
        meeting_end = datetime.now(timezone.utc)
        assert c.check_follow_up_sent(meeting_end, []) is False


class TestIntegrationReviewL0NoRegression:
    """L0 must not regress after integration review fixes."""

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

    def test_demo_entity_leak_guard(self):
        """C4 guard: no demo entities in production logic."""
        import pathlib, re
        repo_root = pathlib.Path(__file__).resolve().parents[3]
        production_files = [
            repo_root / "backend" / "maestro_oem" / "calendar_awareness.py",
            repo_root / "backend" / "maestro_oem" / "commitment_escalation.py",
            repo_root / "backend" / "maestro_oem" / "deal_health.py",
            repo_root / "backend" / "maestro_oem" / "crm_connector.py",
            repo_root / "backend" / "maestro_oem" / "workplace_signal_fusion.py",
        ]
        demo_entities = ["Globex", "Initech", "acme.com"]
        for file_path in production_files:
            if not file_path.exists():
                continue
            src = file_path.read_text()
            # Check for demo entities in non-comment, non-docstring lines
            for entity in demo_entities:
                # Simple check: skip if entity only appears in comments
                lines = [l for l in src.split("\n") if not l.strip().startswith("#") and not l.strip().startswith('"""')]
                active_src = "\n".join(lines)
                # Allow in test method names or test descriptions but not in actual code
                if entity in active_src:
                    # Check if it's in a string literal that would be a default value
                    for line in lines:
                        if entity in line and not line.strip().startswith("def test_"):
                            # Check if it's a hardcoded default (not a test or docstring)
                            if "=" in line and entity in line.split("=")[1] and "test" not in line.lower():
                                if 'KNOWN_ENTITIES' not in line and '[]' in line:
                                    continue  # empty list is fine
                                if 'KNOWN_ENTITIES' in line and '[]' in line:
                                    continue  # empty list is fine
                                pytest.fail(f"Demo entity '{entity}' found in {file_path.name}: {line.strip()}")
