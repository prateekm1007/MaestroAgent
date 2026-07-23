"""Instagram email parser — extracts comment/mention/DM notifications from Instagram emails.

Instagram's personal DMs aren't available via API for consumer apps, but Instagram
sends notification emails for "X commented", "X mentioned you", "X sent you a message"
that contain social commitments. This parser recognizes them and tags source:"instagram".
"""
from __future__ import annotations

import re
import logging

from maestro_personal_shell.connectors import Signal
from maestro_personal_shell.connectors.parsers import register_parser

logger = logging.getLogger(__name__)


@register_parser(r"@instagram|instagram\.com|instagrammail", re.IGNORECASE)
def parse_instagram(signal: Signal) -> list[Signal]:
    """Extract Instagram commitments from notification emails."""
    text = signal.text
    signals = []

    # "X commented on your post"
    comment_match = re.search(
        r"(\w[\w\s.]+?)\s+(?:commented on|replied to)",
        text, re.IGNORECASE,
    )
    if comment_match:
        person = comment_match.group(1).strip()
        signals.append(Signal(
            source="instagram",
            source_id=f"ig_comment_{signal.source_id}",
            thread_id=signal.thread_id,
            entity=person,
            text=f"Instagram: {person} commented on your post",
            timestamp=signal.timestamp,
            direction="inbound",
            metadata={
                "source": "instagram",
                "type": "comment",
                "person": person,
                "parent_signal_id": signal.source_id,
            },
            confidence=0.5,
        ))

    # "X mentioned you" / "X tagged you"
    mention_match = re.search(
        r"(\w[\w\s.]+?)\s+(?:mentioned you|tagged you)",
        text, re.IGNORECASE,
    )
    if mention_match:
        person = mention_match.group(1).strip()
        signals.append(Signal(
            source="instagram",
            source_id=f"ig_mention_{signal.source_id}",
            thread_id=signal.thread_id,
            entity=person,
            text=f"Instagram: {person} mentioned you",
            timestamp=signal.timestamp,
            direction="inbound",
            metadata={
                "source": "instagram",
                "type": "mention",
                "person": person,
                "parent_signal_id": signal.source_id,
            },
            confidence=0.5,
        ))

    # "X sent you a message" / "X DM'd you"
    dm_match = re.search(
        r"(\w[\w\s.]+?)\s+(?:sent you.{0,10}message|DM['']?d you|messaged you)",
        text, re.IGNORECASE,
    )
    if dm_match:
        person = dm_match.group(1).strip()
        signals.append(Signal(
            source="instagram",
            source_id=f"ig_dm_{signal.source_id}",
            thread_id=signal.thread_id,
            entity=person,
            text=f"Instagram: {person} sent you a message",
            timestamp=signal.timestamp,
            direction="commitment_theirs",
            metadata={
                "source": "instagram",
                "type": "dm_notification",
                "person": person,
                "parent_signal_id": signal.source_id,
            },
            confidence=0.6,
        ))

    if not signals:
        signals.append(Signal(
            source="instagram",
            source_id=f"ig_fyi_{signal.source_id}",
            thread_id=signal.thread_id,
            entity="Instagram",
            text=f"Instagram notification: {text[:200]}",
            timestamp=signal.timestamp,
            direction="inbound",
            metadata={
                "source": "instagram",
                "type": "notification",
                "parent_signal_id": signal.source_id,
            },
            confidence=0.3,
        ))

    return signals
