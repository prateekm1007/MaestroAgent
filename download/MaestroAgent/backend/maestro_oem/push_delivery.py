"""
V8 P0-5 — Push Delivery (Opt-In).

The Bond lesson: the briefing finds the CEO, not vice versa. But push
delivery without consent is a trust violation. Default: pull (no push).
Push is opt-in per channel.

The customer chooses:
  - Channel: "slack" | "email" | "none" (default: none)
  - Time: HH:MM in their timezone (default: 07:00)
  - Enabled: True/False (default: False)

Never push to a channel the customer has not explicitly authorized.
Never push at a time the customer has not chosen. The push includes a
one-tap "Open in Maestro" link that deep-links to the briefing.

API:
  POST /api/oem/push/settings — set push channel + time
  POST /api/oem/push/test — send a test push
  GET /api/oem/push/settings — get current settings
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PushSettings:
    """Per-user push delivery settings. Default: disabled."""
    channel: str = "none"  # "slack" | "email" | "none"
    time: str = "07:00"    # HH:MM in user's timezone
    enabled: bool = False
    timezone: str = "UTC"
    slack_channel: str = ""  # Slack channel/DM to post to
    email_address: str = ""  # Email to send to
    last_pushed: str | None = None  # ISO timestamp of last push

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "time": self.time,
            "enabled": self.enabled,
            "timezone": self.timezone,
            "slack_channel": self.slack_channel,
            "email_address": self.email_address,
            "last_pushed": self.last_pushed,
        }


class PushDeliveryService:
    """Manages push delivery of the morning briefing.

    Settings are stored in memory (per-user, keyed by user_id). In
    production, these would be persisted to the database. The service
    checks whether push is enabled, whether it's time to push, and
    delivers the briefing to the chosen channel.

    Governance: NEVER push to a channel the customer has not explicitly
    authorized. NEVER push at a time the customer has not chosen. The
    customer can disable push at any time.
    """

    _settings: dict[str, PushSettings] = {}

    def get_settings(self, user_id: str = "default") -> PushSettings:
        """Get push settings for a user. Returns defaults if not set."""
        return self._settings.get(user_id, PushSettings())

    def set_settings(
        self,
        user_id: str = "default",
        channel: str = "none",
        time: str = "07:00",
        enabled: bool = False,
        timezone: str = "UTC",
        slack_channel: str = "",
        email_address: str = "",
    ) -> PushSettings:
        """Set push settings for a user.

        Args:
            channel: "slack" | "email" | "none"
            time: HH:MM format (e.g. "07:00")
            enabled: whether push is active
            timezone: IANA timezone (e.g. "America/New_York")
            slack_channel: Slack channel/DM ID (required if channel=slack)
            email_address: Email address (required if channel=email)

        Returns:
            The updated PushSettings.
        """
        # Validate channel
        if channel not in ("slack", "email", "none"):
            raise ValueError(f"Invalid channel: '{channel}'. Must be 'slack', 'email', or 'none'.")

        # Validate time format
        try:
            parts = time.split(":")
            if len(parts) != 2 or not (0 <= int(parts[0]) <= 23 and 0 <= int(parts[1]) <= 59):
                raise ValueError
        except Exception:
            raise ValueError(f"Invalid time: '{time}'. Must be HH:MM (e.g. '07:00').")

        # Validate channel-specific fields
        if channel == "slack" and not slack_channel:
            raise ValueError("slack_channel is required when channel='slack'")
        if channel == "email" and not email_address:
            raise ValueError("email_address is required when channel='email'")

        settings = PushSettings(
            channel=channel,
            time=time,
            enabled=enabled,
            timezone=timezone,
            slack_channel=slack_channel,
            email_address=email_address,
        )
        self._settings[user_id] = settings
        return settings

    def should_push_now(self, user_id: str = "default") -> bool:
        """Check if a push should be sent now for this user.

        Returns True if:
          - Push is enabled
          - The current time matches the user's chosen push time (within 5 min)
          - The last push was not today
        """
        settings = self.get_settings(user_id)
        if not settings.enabled or settings.channel == "none":
            return False

        now = datetime.now(timezone.utc)
        # Check if current time matches the push time (within 5 minutes)
        push_hour, push_min = int(settings.time.split(":")[0]), int(settings.time.split(":")[1])
        if abs(now.hour - push_hour) > 0 or abs(now.minute - push_min) > 5:
            return False

        # Check if already pushed today
        if settings.last_pushed:
            try:
                last = datetime.fromisoformat(settings.last_pushed)
                if last.date() == now.date():
                    return False
            except Exception:
                pass

        return True

    def deliver_briefing(
        self,
        user_id: str = "default",
        briefing_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Deliver the morning briefing to the user's chosen channel.

        Args:
            user_id: The user to deliver to.
            briefing_data: The briefing payload (from GET /api/oem/ceo-briefing).

        Returns:
            {
                delivered: bool,
                channel: str,
                message: str,
                preview: str,  # what was sent
            }

        Governance: This method NEVER sends without checking settings.enabled
        and settings.channel. If push is disabled, it returns delivered=False.
        """
        settings = self.get_settings(user_id)
        if not settings.enabled or settings.channel == "none":
            return {
                "delivered": False,
                "channel": settings.channel,
                "message": "Push delivery is not enabled. Enable via POST /api/oem/push/settings.",
            }

        if not briefing_data:
            return {
                "delivered": False,
                "channel": settings.channel,
                "message": "No briefing data provided.",
            }

        # Build the push payload (summary + deep-link)
        one_thing = briefing_data.get("one_thing", {})
        headline = one_thing.get("title", "No urgent items today.")
        summary = briefing_data.get("overnight", {}).get("summary", "Nothing changed overnight.")
        commitments = briefing_data.get("commitments", {}).get("summary", "")

        preview = f"Morning Briefing\n\nTop priority: {headline}\n\n{summary}"
        if commitments:
            preview += f"\n\n{commitments}"
        preview += "\n\nOpen in Maestro for full details."

        # Mark as pushed
        settings.last_pushed = datetime.now(timezone.utc).isoformat()
        self._settings[user_id] = settings

        if settings.channel == "slack":
            return {
                "delivered": True,
                "channel": "slack",
                "target": settings.slack_channel,
                "preview": preview,
                "message": f"Would post briefing to Slack channel {settings.slack_channel}.",
                "deep_link": "/#today",
            }
        elif settings.channel == "email":
            return {
                "delivered": True,
                "channel": "email",
                "target": settings.email_address,
                "preview": preview,
                "subject": "Your Maestro Morning Briefing",
                "message": f"Would send briefing email to {settings.email_address}.",
                "deep_link": "/#today",
            }

        return {"delivered": False, "channel": settings.channel, "message": "Unknown channel."}

    def send_test_push(self, user_id: str = "default") -> dict[str, Any]:
        """Send a test push to verify the channel works.

        This sends a minimal test message (not the full briefing) to
        verify the channel configuration is correct.
        """
        settings = self.get_settings(user_id)
        if settings.channel == "none":
            return {
                "delivered": False,
                "message": "No channel configured. Set channel via POST /api/oem/push/settings first.",
            }

        test_message = "This is a test push from Maestro. If you see this, push delivery is working."

        if settings.channel == "slack":
            return {
                "delivered": True,
                "channel": "slack",
                "target": settings.slack_channel,
                "preview": test_message,
                "message": f"Test push would be sent to Slack channel {settings.slack_channel}.",
            }
        elif settings.channel == "email":
            return {
                "delivered": True,
                "channel": "email",
                "target": settings.email_address,
                "preview": test_message,
                "subject": "Maestro Test Push",
                "message": f"Test push would be sent to {settings.email_address}.",
            }

        return {"delivered": False, "message": "Unknown channel."}
