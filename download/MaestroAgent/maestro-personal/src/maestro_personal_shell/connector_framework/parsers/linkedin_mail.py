"""LinkedIn email parser — extracts connection/follow-up commitments from LinkedIn emails.

LinkedIn's personal DMs aren't available via API, but LinkedIn sends notification
emails for connection requests, "following up" messages, and profile views that
contain commitments. This parser recognizes them and tags source:"linkedin".
"""
from __future__ import annotations

import re
import logging

from maestro_personal_shell.connector_framework import Signal
from maestro_personal_shell.connector_framework.parsers import register_parser

logger = logging.getLogger(__name__)


@register_parser(r"linkedin\.com|@linkedin", re.IGNORECASE)
def parse_linkedin(signal: Signal) -> list[Signal]:
    """Extract LinkedIn commitments from notification emails."""
    text = signal.text
    signals = []

    # "X wants to connect" / "X sent you a connection request"
    connect_match = re.search(
        r"(\w[\w\s]+?)\s+(?:wants to connect|sent you.{0,20}connection)",
        text, re.IGNORECASE,
    )
    if connect_match:
        person = connect_match.group(1).strip()
        signals.append(Signal(
            source="linkedin",
            source_id=f"linkedin_connect_{signal.source_id}",
            thread_id=signal.thread_id,
            entity=person,
            text=f"LinkedIn: {person} wants to connect",
            timestamp=signal.timestamp,
            direction="inbound",
            metadata={
                "source": "linkedin",
                "type": "connection_request",
                "person": person,
                "parent_signal_id": signal.source_id,
            },
            confidence=0.7,
        ))

    # "X is following up" / "X replied to your message"
    followup_match = re.search(
        r"(\w[\w\s]+?)\s+(?:is following up|replied to|sent you.{0,20}message)",
        text, re.IGNORECASE,
    )
    if followup_match:
        person = followup_match.group(1).strip()
        signals.append(Signal(
            source="linkedin",
            source_id=f"linkedin_followup_{signal.source_id}",
            thread_id=signal.thread_id,
            entity=person,
            text=f"LinkedIn: {person} is following up",
            timestamp=signal.timestamp,
            direction="commitment_theirs",
            metadata={
                "source": "linkedin",
                "type": "follow_up",
                "person": person,
                "parent_signal_id": signal.source_id,
            },
            confidence=0.6,
        ))

    # "X viewed your profile"
    view_match = re.search(r"(\w[\w\s]+?)\s+viewed your profile", text, re.IGNORECASE)
    if view_match:
        person = view_match.group(1).strip()
        signals.append(Signal(
            source="linkedin",
            source_id=f"linkedin_view_{signal.source_id}",
            thread_id=signal.thread_id,
            entity=person,
            text=f"LinkedIn: {person} viewed your profile",
            timestamp=signal.timestamp,
            direction="inbound",
            metadata={
                "source": "linkedin",
                "type": "profile_view",
                "person": person,
                "parent_signal_id": signal.source_id,
            },
            confidence=0.4,
        ))

    if not signals:
        signals.append(Signal(
            source="linkedin",
            source_id=f"linkedin_fyi_{signal.source_id}",
            thread_id=signal.thread_id,
            entity="LinkedIn",
            text=f"LinkedIn notification: {text[:200]}",
            timestamp=signal.timestamp,
            direction="inbound",
            metadata={
                "source": "linkedin",
                "type": "notification",
                "parent_signal_id": signal.source_id,
            },
            confidence=0.3,
        ))

    return signals
