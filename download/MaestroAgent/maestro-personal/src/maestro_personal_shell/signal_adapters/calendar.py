"""
Calendar adapter — extracts personal signals from calendar events.

Per revised roadmap v2: Gmail + Calendar adapters. This adapter takes
calendar event data (from Google Calendar API or mock data) and converts
it to PersonalSignal objects.

The adapter does NOT call the Calendar API directly — that requires OAuth
credentials. Instead, it provides:
  - extract_signals_from_event(): converts one calendar event to signals
  - detect_upcoming_meetings(): flags meetings approaching within N hours
  - extract_meeting_context(): gets prep context for a meeting
"""

from __future__ import annotations

import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


def _parse_datetime(dt_str: str) -> datetime:
    """Parse an ISO datetime string, handling both aware and naive."""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)


def extract_signals_from_event(
    event: dict[str, Any],
    user_email: str = "me",
) -> list[dict[str, Any]]:
    # Guard against malformed input (S2 fix: calendar sync crash on non-dict)
    if not isinstance(event, dict):
        logger.warning("Calendar adapter received non-dict event: %s", type(event).__name__)
        return []
    """Extract personal signals from a calendar event.

    Args:
        event: Calendar event dict with keys:
            - id: str
            - summary: str (event title)
            - start: dict with dateTime or date
            - end: dict with dateTime or date
            - attendees: list of dicts with email, displayName
            - status: "confirmed", "tentative", "cancelled"
        user_email: the user's email (to identify self in attendees)

    Returns:
        List of signal dicts.
    """
    signals = []
    event_id = event.get("id", str(uuid4()))
    summary = event.get("summary", "Untitled event")
    status = event.get("status", "confirmed")

    # S2-04 fix (auditor finding): handle both string and dict forms for
    # start/end. Google Calendar API returns dicts like {"dateTime": "...",
    # "timeZone": "..."}, but some clients send plain strings like
    # "2026-07-19T10:00:00Z". The previous code called .get("dateTime") on
    # the value, which crashed with AttributeError when the value was a string.
    def _extract_datetime(val):
        """Extract datetime string from either a dict or a plain string."""
        if isinstance(val, dict):
            return val.get("dateTime") or val.get("date", "")
        elif isinstance(val, str):
            return val
        return ""

    start_raw = event.get("start", {})
    end_raw = event.get("end", {})
    start_str = _extract_datetime(start_raw)
    end_str = _extract_datetime(end_raw)
    start_time = _parse_datetime(start_str) if start_str else datetime.now(timezone.utc)

    # Extract primary attendee (the person the user is meeting with)
    attendees = event.get("attendees", [])
    entity = "unknown"
    for attendee in attendees:
        if not isinstance(attendee, dict):
            continue
        email = attendee.get("email", "")
        if email.lower() != user_email.lower():
            entity = attendee.get("displayName") or email.split("@")[0]
            break

    # 1. Meeting scheduled signal
    if status == "confirmed":
        signals.append({
            "entity": entity,
            "text": f"Meeting: {summary}",
            "signal_type": "meeting.scheduled",
            "timestamp": start_time.isoformat(),
            "metadata": {
                "event_id": event_id,
                "source": "calendar",
                "summary": summary,
                "start": start_str,
                "attendees": [a.get("email") for a in attendees],
            },
        })

    # 2. Meeting cancelled
    elif status == "cancelled":
        signals.append({
            "entity": entity,
            "text": f"Meeting cancelled: {summary}",
            "signal_type": "meeting.cancelled",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": {
                "event_id": event_id,
                "source": "calendar",
                "summary": summary,
            },
        })

    # 3. Detect if meeting is approaching (within 24 hours)
    now = datetime.now(timezone.utc)
    time_until = start_time - now
    if timedelta(0) < time_until < timedelta(hours=24) and status == "confirmed":
        hours_until = int(time_until.total_seconds() / 3600)
        signals.append({
            "entity": entity,
            "text": f"Meeting with {entity} in {hours_until}h: {summary}",
            "signal_type": "deadline.approaching",
            "timestamp": now.isoformat(),
            "metadata": {
                "event_id": event_id,
                "source": "calendar",
                "summary": summary,
                "hours_until": hours_until,
                "start": start_str,
            },
        })

    return signals


def detect_upcoming_meetings(
    events: list[dict[str, Any]],
    hours_ahead: int = 24,
    user_email: str = "me",
) -> list[dict[str, Any]]:
    """Detect meetings approaching within N hours.

    Used by the Whisper surface to proactively surface meeting prep.
    """
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=hours_ahead)

    upcoming = []
    for event in events:
        start_str = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date", "")
        if not start_str:
            continue
        start_time = _parse_datetime(start_str)
        if now <= start_time <= cutoff and event.get("status") == "confirmed":
            upcoming.append(event)

    return upcoming


def extract_meeting_context(
    event: dict[str, Any],
    signals: list[dict[str, Any]],
) -> dict[str, Any]:
    """Extract meeting context for the Prepare surface.

    Given a calendar event and existing signals, find signals related to
    the meeting's entity and subject. This is what Prepare uses to
    surface "here's what you should know before this meeting."
    """
    summary = event.get("summary", "").lower()
    attendees = event.get("attendees", [])

    # Find signals from any attendee
    attendee_emails = {a.get("email", "").lower() for a in attendees}
    attendee_names = {a.get("displayName", "").lower() for a in attendees}

    related_signals = []
    for sig in signals:
        entity = sig.get("entity", "").lower()
        text = sig.get("text", "").lower()

        # Match by entity name or by subject keywords in the signal text
        if entity in attendee_emails or entity in attendee_names:
            related_signals.append(sig)
        elif any(word in text for word in summary.split() if len(word) > 3):
            related_signals.append(sig)

    return {
        "event_id": event.get("id"),
        "summary": event.get("summary"),
        "related_signal_count": len(related_signals),
        "related_signals": related_signals[:5],
        "attendee_count": len(attendees),
    }
