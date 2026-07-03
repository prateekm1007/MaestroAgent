"""
Gmail / Google Workspace signal normalizer.

Gmail signals affect:
- Decision velocity (meeting cadence, email response times)
- External communication patterns (customer/vendor interactions)
- Meeting patterns (who meets with whom — decision graph)

Privacy: only metadata is processed. No email content is stored.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from maestro_oem.signal import ExecutionSignal, SignalProvider, SignalType


def normalize_gmail(event: dict[str, Any]) -> ExecutionSignal:
    """
    Convert a Gmail/Workspace event into an ExecutionSignal.

    Expected event format:
    {
        "event_type": "email_sent" | "email_received" | "meeting_scheduled" | "meeting_completed",
        "actor": "jane.doe@example.com",
        "artifact": "msg-12345" | "cal-event-67890",
        "timestamp": "2024-11-12T09:14:00Z",
        "metadata": {
            "recipient": "raj@example.com",
            "recipient_type": "external" | "internal",
            "participants": ["jane.doe@example.com", "raj@example.com"],
            "duration": 30,  # minutes, for meetings
            "subject": "Q4 renewal discussion",  # subject only, not body
            "calendar": "work",
        }
    }
    """
    event_type = event.get("event_type", "email_sent")

    type_map = {
        "email_sent": SignalType.EMAIL_SENT,
        "email_received": SignalType.EMAIL_RECEIVED,
        "meeting_scheduled": SignalType.MEETING_SCHEDULED,
        "meeting_completed": SignalType.MEETING_COMPLETED,
    }

    sig_type = type_map.get(event_type, SignalType.EMAIL_SENT)

    actor = event.get("actor", "unknown")
    artifact = event.get("artifact", "")
    timestamp = event.get("timestamp", datetime.now().isoformat())

    metadata = {
        "recipient": event.get("metadata", {}).get("recipient", ""),
        "recipient_type": event.get("metadata", {}).get("recipient_type", "internal"),
        "participants": event.get("metadata", {}).get("participants", []),
        "duration": event.get("metadata", {}).get("duration", 0),
        "subject": event.get("metadata", {}).get("subject", ""),  # Subject only, no body
        "calendar": event.get("metadata", {}).get("calendar", "work"),
    }

    # Meetings are decision events
    is_decision = sig_type in (SignalType.MEETING_COMPLETED, SignalType.MEETING_SCHEDULED)

    # Lower confidence for inferred patterns
    confidence = 0.9 if is_decision else 1.0

    return ExecutionSignal(
        type=sig_type,
        timestamp=_parse_timestamp(timestamp),
        actor=actor,
        team=event.get("team", "unknown"),
        artifact=artifact,
        decision=is_decision,
        confidence=confidence,
        metadata=metadata,
        provider=SignalProvider.GMAIL,
    )


def _parse_timestamp(ts: str | datetime) -> datetime:
    if isinstance(ts, datetime):
        return ts
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        from datetime import timezone
        return datetime.now(timezone.utc)
