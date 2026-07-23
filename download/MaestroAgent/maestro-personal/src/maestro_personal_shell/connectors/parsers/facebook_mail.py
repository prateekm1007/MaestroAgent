"""Facebook email parser — extracts event RSVP / message notifications from Facebook emails.

Facebook's personal messages aren't available via API for consumer apps, but Facebook
sends notification emails for event invitations, "X sent you a message", and RSVP requests
that contain social commitments. This parser recognizes them and tags source:"facebook".
"""
from __future__ import annotations

import re
import logging

from maestro_personal_shell.connectors import Signal
from maestro_personal_shell.connectors.parsers import register_parser

logger = logging.getLogger(__name__)


@register_parser(r"@facebook|facebookmail|facebook\.com", re.IGNORECASE)
def parse_facebook(signal: Signal) -> list[Signal]:
    """Extract Facebook commitments from notification emails."""
    text = signal.text
    signals = []

    # Event invitation: "X invited you to Event Name"
    event_match = re.search(
        r"(\w[\w\s.]+?)\s+invited you to\s+(.+?)(?:\.|$|\n)",
        text, re.IGNORECASE,
    )
    if event_match:
        person = event_match.group(1).strip()
        event = event_match.group(2).strip()
        signals.append(Signal(
            source="facebook",
            source_id=f"fb_event_{signal.source_id}",
            thread_id=signal.thread_id,
            entity=person,
            text=f"Facebook: {person} invited you to {event}",
            timestamp=signal.timestamp,
            direction="commitment_theirs",
            metadata={
                "source": "facebook",
                "type": "event_invitation",
                "person": person,
                "event": event,
                "parent_signal_id": signal.source_id,
            },
            confidence=0.6,
        ))

    # "X sent you a message" / "X messaged you"
    msg_match = re.search(
        r"(\w[\w\s.]+?)\s+(?:sent you.{0,10}message|messaged you)",
        text, re.IGNORECASE,
    )
    if msg_match:
        person = msg_match.group(1).strip()
        signals.append(Signal(
            source="facebook",
            source_id=f"fb_msg_{signal.source_id}",
            thread_id=signal.thread_id,
            entity=person,
            text=f"Facebook: {person} sent you a message",
            timestamp=signal.timestamp,
            direction="commitment_theirs",
            metadata={
                "source": "facebook",
                "type": "message_notification",
                "person": person,
                "parent_signal_id": signal.source_id,
            },
            confidence=0.6,
        ))

    # "X commented on your post" / "X reacted to your post"
    react_match = re.search(
        r"(\w[\w\s.]+?)\s+(?:commented on|reacted to|liked)",
        text, re.IGNORECASE,
    )
    if react_match:
        person = react_match.group(1).strip()
        signals.append(Signal(
            source="facebook",
            source_id=f"fb_react_{signal.source_id}",
            thread_id=signal.thread_id,
            entity=person,
            text=f"Facebook: {person} engaged with your post",
            timestamp=signal.timestamp,
            direction="inbound",
            metadata={
                "source": "facebook",
                "type": "engagement",
                "person": person,
                "parent_signal_id": signal.source_id,
            },
            confidence=0.4,
        ))

    if not signals:
        signals.append(Signal(
            source="facebook",
            source_id=f"fb_fyi_{signal.source_id}",
            thread_id=signal.thread_id,
            entity="Facebook",
            text=f"Facebook notification: {text[:200]}",
            timestamp=signal.timestamp,
            direction="inbound",
            metadata={
                "source": "facebook",
                "type": "notification",
                "parent_signal_id": signal.source_id,
            },
            confidence=0.3,
        ))

    return signals
