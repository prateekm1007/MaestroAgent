"""Loop 2 — Meeting: a first-class object with a lifecycle.

CEO directive: build Loop 2 — Meeting Intelligence. "Builds naturally on
Loop 1 (commitments surface in meetings, meetings have preparation,
preparation has recall). The Situation abstraction from Loop 1.5 gives
Meeting Intelligence a natural unit to work with."

A Meeting is NOT just a calendar event. A calendar event is a point in
time. A Meeting is a cognitive object with a lifecycle:

  SCHEDULED → PREPARED → OCCURRED → OUTCOME_OBSERVED → LEARNING_RECORDED

Each transition is meaningful:
  - SCHEDULED: on the calendar (Phase 3 CalendarSource provides this)
  - PREPARED: Maestro assembles a Situation (Loop 1.5 SituationBuilder)
  - OCCURRED: the meeting happened; Maestro records topics + commitments
  - OUTCOME_OBSERVED: commitments honored/broken, decisions reached
  - LEARNING_RECORDED: Meeting Learning Ledger entry written

The Meeting carries the full history: situation (pre-meeting),
topics_discussed + commitments_made (during), outcome (post), and
learning_entry (the honest sentence about what Maestro learned).

This is the difference between a calendar tool and an organizational
memory. The calendar knows the meeting happened. Maestro knows what
the meeting meant.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class MeetingStatus(str, Enum):
    """The 5 lifecycle states of a Meeting."""

    SCHEDULED = "scheduled"
    PREPARED = "prepared"
    OCCURRED = "occurred"
    OUTCOME_OBSERVED = "outcome_observed"
    LEARNING_RECORDED = "learning_recorded"


@dataclass
class Meeting:
    """A first-class meeting object with a lifecycle.

    Attributes:
        title: Meeting title (from calendar)
        entity: The customer/org this meeting is with
        attendees: List of email addresses
        start: Start time (timezone-aware)
        end: End time (timezone-aware)
        status: Current lifecycle state (default: SCHEDULED)
        situation: The Situation assembled before the meeting (Loop 1.5)
        topics_discussed: Topics covered during the meeting (recorded after)
        commitments_made: Commitments made during the meeting (recorded after)
        outcome: The observed outcome (commitment_honored, commitment_broken, etc.)
        learning_entry: The Meeting Learning Ledger entry (honest sentence)
        meeting_id: Deterministic ID (hashlib.sha256 of title + start)
    """

    title: str
    entity: str
    attendees: list[str]
    start: datetime
    end: datetime
    status: MeetingStatus = MeetingStatus.SCHEDULED
    situation: Any = None  # Situation object (Loop 1.5)
    topics_discussed: list[str] = field(default_factory=list)
    commitments_made: list[str] = field(default_factory=list)
    outcome: str | None = None
    learning_entry: str | None = None
    meeting_id: str = ""

    def __post_init__(self) -> None:
        """Generate a deterministic meeting_id if not provided."""
        if not self.meeting_id:
            raw = f"meeting-{self.title}-{self.start.isoformat()}"
            self.meeting_id = f"mtg-{hashlib.sha256(raw.encode()).hexdigest()[:8]}"

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API responses."""
        return {
            "meeting_id": self.meeting_id,
            "title": self.title,
            "entity": self.entity,
            "attendees": list(self.attendees),
            "start": self.start.isoformat() if hasattr(self.start, "isoformat") else str(self.start),
            "end": self.end.isoformat() if hasattr(self.end, "isoformat") else str(self.end),
            "status": self.status.name,
            "situation": self.situation.to_dict() if self.situation and hasattr(self.situation, "to_dict") else None,
            "topics_discussed": list(self.topics_discussed),
            "commitments_made": list(self.commitments_made),
            "outcome": self.outcome,
            "learning_entry": self.learning_entry,
        }
