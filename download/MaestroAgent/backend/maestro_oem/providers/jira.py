"""
Jira signal normalizer.

Jira signals affect:
- Delivery patterns (issue lifecycle, sprint velocity)
- Approval gates (transitions that require approval)
- Incident patterns (P1 tickets)
- Assignment patterns (who gets assigned what)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from maestro_oem.signal import ExecutionSignal, SignalProvider, SignalType


def normalize_jira(event: dict[str, Any]) -> ExecutionSignal:
    """
    Convert a Jira webhook/API event into an ExecutionSignal.

    Expected event format:
    {
        "event_type": "issue_created" | "issue_transitioned" | "issue_assigned" | "sprint_started" | "sprint_completed",
        "project": "EMEA",
        "actor": "sara.k@example.com",
        "artifact": "EMEA-1247",
        "timestamp": "2024-11-12T09:14:00Z",
        "metadata": {
            "priority": "P1" | "P2" | "P3" | "Medium",
            "transition": "Approved" | "In Review" | "Done",
            "assignee": "priya.m@example.com",
            "sprint": "Q4 Sprint 3",
            "velocity": 42,
            "issue_type": "Bug" | "Task" | "Story" | "Epic",
        }
    }
    """
    event_type = event.get("event_type", "issue_created")

    type_map = {
        "issue_created": SignalType.ISSUE_CREATED,
        "issue_transitioned": SignalType.ISSUE_TRANSITIONED,
        "issue_assigned": SignalType.ISSUE_ASSIGNED,
        "sprint_started": SignalType.SPRINT_STARTED,
        "sprint_completed": SignalType.SPRINT_COMPLETED,
    }

    sig_type = type_map.get(event_type, SignalType.ISSUE_CREATED)

    actor = event.get("actor", "unknown")
    artifact = event.get("artifact", "")
    timestamp = event.get("timestamp", datetime.now().isoformat())

    metadata = {
        "project": event.get("project", ""),
        "priority": event.get("metadata", {}).get("priority", "Medium"),
        "transition": event.get("metadata", {}).get("transition", ""),
        "assignee": event.get("metadata", {}).get("assignee", ""),
        "sprint": event.get("metadata", {}).get("sprint", ""),
        "velocity": event.get("metadata", {}).get("velocity", 0),
        "issue_type": event.get("metadata", {}).get("issue_type", "Task"),
    }

    # Determine if this is a decision event
    is_decision = "approve" in metadata["transition"].lower() or "reject" in metadata["transition"].lower()

    return ExecutionSignal(
        type=sig_type,
        timestamp=_parse_timestamp(timestamp),
        actor=actor,
        team=event.get("team", metadata.get("project", "unknown")),
        artifact=artifact,
        decision=is_decision,
        confidence=1.0,
        metadata=metadata,
        provider=SignalProvider.JIRA,
    )


def _parse_timestamp(ts: str | datetime) -> datetime:
    if isinstance(ts, datetime):
        return ts
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        from datetime import timezone
        return datetime.now(timezone.utc)
