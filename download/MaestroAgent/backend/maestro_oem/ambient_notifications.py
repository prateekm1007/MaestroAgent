"""
Ambient Notification Engine - smart nudges, context-aware timing, DND.

Phase 19 of the Ambient Intelligence roadmap (Days 134-143, 40 hours).

REALITY CHECK VERDICT: REALISTIC - build. Table stakes for any ambient
system. Do-not-disturb integration is standard (OS-level APIs).
Context-aware timing is just rule-based. Smart batching is simple.

What it does:
  1. Smart nudges - generates contextually relevant notifications
  2. Context-aware timing - no notifications during calls, deep work, off-hours
  3. Do-not-disturb integration - respects OS-level DND + calendar focus
  4. Nudge fatigue prevention - max 5/hour, escalation levels, user feedback
  5. Quiet hours - no notifications 8pm-8am local

AMBIENT dimension: works between calls, not just during.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta, time
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from collections import deque

logger = logging.getLogger(__name__)


class NotificationPriority(str, Enum):
    """Priority level for notifications."""
    CRITICAL = "critical"  # always shows (overdue commitment, relationship at risk)
    HIGH = "high"          # shows unless DND
    MEDIUM = "medium"      # shows unless DND or in-call
    LOW = "low"            # batches, shows during active hours only


class NotificationType(str, Enum):
    """Type of notification."""
    OVERDUE_COMMITMENT = "overdue_commitment"
    STALE_RELATIONSHIP = "stale_relationship"
    PREPARATION_GAP = "preparation_gap"
    MEETING_REMINDER = "meeting_reminder"
    COMMITMENT_TRACKED = "commitment_tracked"
    SENTIMENT_ALERT = "sentiment_alert"
    FOLLOW_UP_DUE = "follow_up_due"
    DAILY_DIGEST = "daily_digest"


@dataclass
class Notification:
    """A single notification."""
    notification_id: str
    type: NotificationType
    priority: NotificationPriority
    title: str
    body: str
    action_url: str = ""
    action_label: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "notification_id": self.notification_id,
            "type": self.type.value,
            "priority": self.priority.value,
            "title": self.title,
            "body": self.body[:200],
            "action_url": self.action_url,
            "action_label": self.action_label,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class NotificationContext:
    """Context that determines whether a notification should be shown."""
    current_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_in_call: bool = False
    is_dnd_active: bool = False
    is_focus_mode: bool = False
    user_timezone: str = "UTC"
    quiet_hours_start: time = time(20, 0)  # 8pm
    quiet_hours_end: time = time(8, 0)   # 8am


class AmbientNotificationEngine:
    """
    Smart notification engine with context-aware timing and fatigue prevention.

    Usage:
        engine = AmbientNotificationEngine()
        engine.add_notification(Notification(
            notification_id="n1",
            type=NotificationType.OVERDUE_COMMITMENT,
            priority=NotificationPriority.CRITICAL,
            title="Commitment Overdue",
            body="SSO deployment is 3 days overdue",
        ))

        context = NotificationContext(is_in_call=True, is_dnd_active=False)
        visible = engine.get_visible_notifications(context)
    """

    MAX_PER_HOUR = 5
    MAX_PER_DAY = 30

    def __init__(self):
        self._notifications: deque[Notification] = deque(maxlen=100)
        self._shown_history: list[datetime] = []  # timestamps of shown notifications
        self._dismissed_ids: set[str] = set()
        self._feedback: dict[str, str] = {}  # notification_id -> "helpful" / "not_helpful"

    def add_notification(self, notification: Notification) -> None:
        """Add a notification to the queue."""
        self._notifications.append(notification)

    def get_visible_notifications(
        self, context: NotificationContext, limit: int = 10
    ) -> list[Notification]:
        """Get notifications that should be shown given the current context.

        Filters by:
          1. Quiet hours (8pm-8am local) - only CRITICAL shows
          2. In-call - only CRITICAL shows
          3. DND active - only CRITICAL shows
          4. Focus mode - only CRITICAL and HIGH show
          5. Fatigue prevention - max 5/hour, max 30/day
          6. Dismissed notifications are not re-shown
        """
        now = context.current_time

        # Check quiet hours
        is_quiet_hours = self._is_quiet_hours(context)

        # Check fatigue limits
        hourly_count = self._count_shown_in_window(now, timedelta(hours=1))
        daily_count = self._count_shown_in_window(now, timedelta(hours=24))

        visible = []
        for notification in self._notifications:
            # Skip dismissed
            if notification.notification_id in self._dismissed_ids:
                continue

            # Skip already shown (unless CRITICAL re-alert after 1 hour)
            if self._was_shown_recently(notification, now, timedelta(hours=1)):
                continue

            # Priority filtering based on context
            if not self._should_show(notification, context, is_quiet_hours):
                continue

            # Fatigue prevention
            if notification.priority != NotificationPriority.CRITICAL:
                if hourly_count >= self.MAX_PER_HOUR:
                    continue
                if daily_count >= self.MAX_PER_DAY:
                    continue

            visible.append(notification)
            self._shown_history.append(now)
            hourly_count += 1
            daily_count += 1

            if len(visible) >= limit:
                break

        return visible

    def dismiss_notification(self, notification_id: str) -> None:
        """User dismisses a notification."""
        self._dismissed_ids.add(notification_id)

    def provide_feedback(self, notification_id: str, feedback: str) -> None:
        """User provides feedback on notification helpfulness."""
        if feedback not in ("helpful", "not_helpful"):
            return
        self._feedback[notification_id] = feedback

    def get_feedback_summary(self) -> dict[str, int]:
        """Get summary of user feedback (for improving notification relevance)."""
        helpful = sum(1 for f in self._feedback.values() if f == "helpful")
        not_helpful = sum(1 for f in self._feedback.values() if f == "not_helpful")
        return {"helpful": helpful, "not_helpful": not_helpful}

    def _should_show(
        self,
        notification: Notification,
        context: NotificationContext,
        is_quiet_hours: bool,
    ) -> bool:
        """Determine if a notification should be shown given the context."""
        # CRITICAL always shows
        if notification.priority == NotificationPriority.CRITICAL:
            return True

        # Quiet hours: only CRITICAL
        if is_quiet_hours:
            return False

        # In-call: only CRITICAL
        if context.is_in_call:
            return False

        # DND active: only CRITICAL
        if context.is_dnd_active:
            return False

        # Focus mode: only CRITICAL and HIGH
        if context.is_focus_mode and notification.priority == NotificationPriority.MEDIUM:
            return False

        # LOW priority: only during active hours (already filtered by quiet hours)
        if notification.priority == NotificationPriority.LOW:
            return not is_quiet_hours

        return True

    def _is_quiet_hours(self, context: NotificationContext) -> bool:
        """Check if current time is within quiet hours."""
        now = context.current_time
        # Convert to local time (simplified — uses UTC for demo)
        current_hour = now.hour

        # Quiet hours: 8pm (20) to 8am (8)
        if context.quiet_hours_start <= context.quiet_hours_end:
            # Same-day range (e.g., 9am-5pm)
            return context.quiet_hours_start.hour <= current_hour < context.quiet_hours_end.hour
        else:
            # Overnight range (e.g., 8pm-8am)
            return current_hour >= context.quiet_hours_start.hour or current_hour < context.quiet_hours_end.hour

    def _was_shown_recently(
        self, notification: Notification, now: datetime, window: timedelta
    ) -> bool:
        """Check if a notification was shown within the time window."""
        # Simplified: check if the notification ID appears in recent history
        # In production, would track per-notification-ID show times
        return False  # simplified for this implementation

    def _count_shown_in_window(self, now: datetime, window: timedelta) -> int:
        """Count notifications shown within the time window."""
        cutoff = now - window
        return sum(1 for ts in self._shown_history if ts > cutoff)

    def generate_overdue_commitment_notification(
        self, commitment_text: str, days_overdue: int, entity: str
    ) -> Notification:
        """Generate a notification for an overdue commitment."""
        priority = NotificationPriority.CRITICAL if days_overdue >= 7 else NotificationPriority.HIGH
        return Notification(
            notification_id=f"overdue-{entity}-{int(datetime.now(timezone.utc).timestamp())}",
            type=NotificationType.OVERDUE_COMMITMENT,
            priority=priority,
            title=f"Commitment Overdue ({days_overdue} days)",
            body=f"{commitment_text[:100]} — {entity}",
            action_url=f"/customers/{entity}",
            action_label="View commitment",
            metadata={"entity": entity, "days_overdue": days_overdue},
        )

    def generate_preparation_gap_notification(
        self, meeting_title: str, minutes_to_start: int, talking_points: list[str]
    ) -> Notification:
        """Generate a notification for a preparation gap."""
        return Notification(
            notification_id=f"prep-gap-{int(datetime.now(timezone.utc).timestamp())}",
            type=NotificationType.PREPARATION_GAP,
            priority=NotificationPriority.HIGH,
            title=f"Meeting in {minutes_to_start} min — no prep done",
            body=f"{meeting_title}. Top talking point: {talking_points[0] if talking_points else 'Review meeting context'}",
            action_url="/copilot",
            action_label="View briefing",
            metadata={"meeting_title": meeting_title, "minutes_to_start": minutes_to_start},
        )

    def generate_stale_relationship_notification(
        self, entity: str, days_since_interaction: int
    ) -> Notification:
        """Generate a notification for a stale relationship."""
        priority = NotificationPriority.HIGH if days_since_interaction > 30 else NotificationPriority.MEDIUM
        return Notification(
            notification_id=f"stale-{entity}-{int(datetime.now(timezone.utc).timestamp())}",
            type=NotificationType.STALE_RELATIONSHIP,
            priority=priority,
            title=f"Relationship stale: {entity}",
            body=f"No interaction in {days_since_interaction} days. Consider re-engaging.",
            action_url=f"/customers/{entity}",
            action_label="View relationship",
            metadata={"entity": entity, "days_since": days_since_interaction},
        )

    def generate_daily_digest(
        self, meeting_count: int, overdue_count: int, at_risk_count: int
    ) -> Notification:
        """Generate a daily digest notification."""
        return Notification(
            notification_id=f"digest-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
            type=NotificationType.DAILY_DIGEST,
            priority=NotificationPriority.LOW,
            title="Your day at a glance",
            body=f"{meeting_count} meetings, {overdue_count} overdue commitments, {at_risk_count} at-risk accounts",
            action_url="/dashboard",
            action_label="Open dashboard",
            metadata={"meeting_count": meeting_count, "overdue_count": overdue_count, "at_risk_count": at_risk_count},
        )
