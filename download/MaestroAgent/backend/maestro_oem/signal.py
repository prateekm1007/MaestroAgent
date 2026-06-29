"""
ExecutionSignal — the universal normalized signal type.

Every provider (GitHub, Jira, Slack, Confluence, Gmail) produces
ExecutionSignal objects. The OEM consumes these and updates itself.

Nothing else enters the OEM. If it's not an ExecutionSignal, it doesn't exist.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class SignalProvider(str, Enum):
    GITHUB = "github"
    JIRA = "jira"
    SLACK = "slack"
    CONFLUENCE = "confluence"
    GMAIL = "gmail"
    CALENDAR = "calendar"
    UNKNOWN = "unknown"


class SignalType(str, Enum):
    # GitHub
    PR_OPENED = "pr.opened"
    PR_MERGED = "pr.merged"
    PR_CLOSED = "pr.closed"
    PR_REVIEWED = "pr.reviewed"
    COMMIT = "commit"
    BRANCH_CREATED = "branch.created"
    REPO_CREATED = "repo.created"

    # Jira
    ISSUE_CREATED = "issue.created"
    ISSUE_TRANSITIONED = "issue.transitioned"
    ISSUE_ASSIGNED = "issue.assigned"
    SPRINT_STARTED = "sprint.started"
    SPRINT_COMPLETED = "sprint.completed"

    # Slack
    MESSAGE_SENT = "message.sent"
    THREAD_STARTED = "thread.started"
    DECISION_SIGNAL = "slack.decision"
    QUESTION_ASKED = "slack.question"
    AGREEMENT = "slack.agreement"
    CONFLICT = "slack.conflict"

    # Confluence
    PAGE_CREATED = "page.created"
    PAGE_EDITED = "page.edited"
    PAGE_OWNER_CHANGED = "page.owner_changed"
    RFC_CREATED = "rfc.created"
    POSTMORTEM_CREATED = "postmortem.created"

    # Gmail / Calendar
    MEETING_SCHEDULED = "meeting.scheduled"
    MEETING_COMPLETED = "meeting.completed"
    EMAIL_SENT = "email.sent"
    EMAIL_RECEIVED = "email.received"

    # Generic
    INCIDENT = "incident"
    DEPLOYMENT = "deployment"
    RELEASE = "release"


class ExecutionSignal(BaseModel):
    """
    The universal signal that enters the OEM.

    type: what happened (SignalType)
    timestamp: when it happened
    actor: who did it (email or external ID)
    team: which team they belong to
    artifact: what was affected (PR URL, ticket ID, page ID, etc.)
    decision: was this a decision-making event? (True/False)
    confidence: signal reliability 0..1 (1 = verified fact, 0.5 = inferred)
    metadata: provider-specific payload
    provider: which signal source produced this
    signal_id: unique identifier
    """

    signal_id: UUID = Field(default_factory=uuid4)
    type: SignalType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    actor: str
    team: str = "unknown"
    artifact: str  # URL, ticket ID, page ID, etc.
    decision: bool = False
    confidence: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)
    provider: SignalProvider = SignalProvider.UNKNOWN

    def to_receipt_data(self) -> dict[str, Any]:
        """Convert to a receipt-compatible dict for provenance tracking."""
        return {
            "signal_id": str(self.signal_id),
            "type": self.type.value,
            "provider": self.provider.value,
            "timestamp": self.timestamp.isoformat(),
            "actor": self.actor,
            "artifact": self.artifact,
        }

    def __hash__(self) -> int:
        return hash(self.signal_id)
