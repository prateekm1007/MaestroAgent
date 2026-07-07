"""Phase 19 - Ambient Notifications tests.

Tests smart nudges, context-aware timing, DND integration, fatigue
prevention, quiet hours, and L0 no-regression.
"""

from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from datetime import datetime, timezone, time, timedelta

import pytest


class TestAmbientNotificationEngine:
    """Phase 19: AmbientNotificationEngine."""

    def _make_engine(self):
        from maestro_oem.ambient_notifications import AmbientNotificationEngine
        return AmbientNotificationEngine()

    def _make_notification(self, priority="medium", ntype="follow_up_due"):
        from maestro_oem.ambient_notifications import Notification, NotificationPriority, NotificationType
        return Notification(
            notification_id=f"test-{priority}-{ntype}",
            type=NotificationType(ntype),
            priority=NotificationPriority(priority),
            title="Test notification",
            body="Test body",
        )

    def _make_context(self, **kwargs):
        from maestro_oem.ambient_notifications import NotificationContext
        return NotificationContext(**kwargs)

    def test_critical_always_shows(self):
        """CRITICAL notifications always show, even during DND/in-call/quiet hours."""
        engine = self._make_engine()
        engine.add_notification(self._make_notification(priority="critical"))
        context = self._make_context(is_in_call=True, is_dnd_active=True)
        # Force quiet hours
        context.current_time = datetime.now(timezone.utc).replace(hour=22)  # 10pm
        visible = engine.get_visible_notifications(context)
        assert len(visible) >= 1
        assert visible[0].priority.value == "critical"

    def test_medium_blocked_in_call(self):
        """MEDIUM notifications are blocked during calls."""
        engine = self._make_engine()
        engine.add_notification(self._make_notification(priority="medium"))
        context = self._make_context(is_in_call=True)
        visible = engine.get_visible_notifications(context)
        assert len(visible) == 0

    def test_medium_blocked_dnd(self):
        """MEDIUM notifications are blocked during DND."""
        engine = self._make_engine()
        engine.add_notification(self._make_notification(priority="medium"))
        context = self._make_context(is_dnd_active=True)
        visible = engine.get_visible_notifications(context)
        assert len(visible) == 0

    def test_high_shows_during_focus_mode(self):
        """HIGH notifications show during focus mode."""
        engine = self._make_engine()
        engine.add_notification(self._make_notification(priority="high"))
        context = self._make_context(is_focus_mode=True)
        visible = engine.get_visible_notifications(context)
        assert len(visible) >= 1

    def test_medium_blocked_during_focus_mode(self):
        """MEDIUM notifications are blocked during focus mode."""
        engine = self._make_engine()
        engine.add_notification(self._make_notification(priority="medium"))
        context = self._make_context(is_focus_mode=True)
        visible = engine.get_visible_notifications(context)
        assert len(visible) == 0

    def test_quiet_hours_block_non_critical(self):
        """Non-critical notifications are blocked during quiet hours (8pm-8am)."""
        engine = self._make_engine()
        engine.add_notification(self._make_notification(priority="high"))
        context = self._make_context()
        context.current_time = datetime.now(timezone.utc).replace(hour=22)  # 10pm
        visible = engine.get_visible_notifications(context)
        assert len(visible) == 0

    def test_quiet_hours_allow_critical(self):
        """CRITICAL notifications pass during quiet hours."""
        engine = self._make_engine()
        engine.add_notification(self._make_notification(priority="critical"))
        context = self._make_context()
        context.current_time = datetime.now(timezone.utc).replace(hour=22)  # 10pm
        visible = engine.get_visible_notifications(context)
        assert len(visible) >= 1

    def test_fatigue_prevention_max_per_hour(self):
        """Max 5 non-critical notifications per hour."""
        engine = self._make_engine()
        # Add 10 medium notifications
        for i in range(10):
            engine.add_notification(self._make_notification(priority="medium"))
        context = self._make_context()
        visible = engine.get_visible_notifications(context, limit=20)
        # Should be capped at 5 (MAX_PER_HOUR)
        assert len(visible) <= 5

    def test_dismissed_notifications_not_reshown(self):
        """Dismissed notifications are not re-shown."""
        engine = self._make_engine()
        notif = self._make_notification(priority="high")
        engine.add_notification(notif)
        engine.dismiss_notification(notif.notification_id)
        context = self._make_context()
        visible = engine.get_visible_notifications(context)
        assert len(visible) == 0

    def test_user_feedback_tracking(self):
        """User feedback is tracked for improving relevance."""
        engine = self._make_engine()
        notif = self._make_notification(priority="high")
        engine.add_notification(notif)
        engine.provide_feedback(notif.notification_id, "helpful")
        engine.provide_feedback("other-id", "not_helpful")
        summary = engine.get_feedback_summary()
        assert summary["helpful"] == 1
        assert summary["not_helpful"] == 1

    def test_overdue_commitment_notification_generation(self):
        """Overdue commitment notifications are generated correctly."""
        engine = self._make_engine()
        notif = engine.generate_overdue_commitment_notification(
            commitment_text="Deploy SSO by Friday",
            days_overdue=10,
            entity="Globex",
        )
        assert "Overdue" in notif.title
        assert "10" in notif.title
        assert notif.priority.value == "critical"  # 10 days = critical

    def test_preparation_gap_notification_generation(self):
        """Preparation gap notifications are generated correctly."""
        engine = self._make_engine()
        notif = engine.generate_preparation_gap_notification(
            meeting_title="Q3 Renewal - Globex",
            minutes_to_start=15,
            talking_points=["Address SSO timeline", "Discuss pricing"],
        )
        assert "15" in notif.title
        assert "no prep" in notif.title.lower()
        assert notif.priority.value == "high"

    def test_stale_relationship_notification_generation(self):
        """Stale relationship notifications are generated correctly."""
        engine = self._make_engine()
        notif = engine.generate_stale_relationship_notification(
            entity="Initech",
            days_since_interaction=35,
        )
        assert "stale" in notif.title.lower()
        assert "35" in notif.body
        assert notif.priority.value == "high"  # >30 days = high

    def test_daily_digest_generation(self):
        """Daily digest notifications are generated correctly."""
        engine = self._make_engine()
        notif = engine.generate_daily_digest(
            meeting_count=8,
            overdue_count=3,
            at_risk_count=2,
        )
        assert "8" in notif.body
        assert "3" in notif.body
        assert "2" in notif.body
        assert notif.priority.value == "low"

    def test_notification_to_dict(self):
        """Notification serializes correctly."""
        engine = self._make_engine()
        notif = engine.generate_overdue_commitment_notification("Test", 5, "Globex")
        d = notif.to_dict()
        assert "notification_id" in d
        assert "type" in d
        assert "priority" in d
        assert "title" in d
        assert "body" in d

    def test_active_hours_show_all_priorities(self):
        """During active hours (9am-5pm), all non-DND notifications show."""
        engine = self._make_engine()
        engine.add_notification(self._make_notification(priority="low"))
        context = self._make_context()
        context.current_time = datetime.now(timezone.utc).replace(hour=10)  # 10am
        visible = engine.get_visible_notifications(context)
        assert len(visible) >= 1


class TestPhase19L0NoRegression:
    """Phase 19 must not regress the L0 substrate."""

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
