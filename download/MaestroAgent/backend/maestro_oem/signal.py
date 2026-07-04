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
    CUSTOMER = "customer"  # CRM, support, contracts — the Customer Judgment Engine
    # V8 Competitor Analysis Feature A — New Evidence Connectors.
    # The Glean lesson: pull their answers as evidence, spend effort on reasoning.
    GLEAN = "glean"      # enterprise search — answers as evidence signals
    GURU = "guru"        # knowledge management — cards as evidence signals
    DUST = "dust"        # AI assistant — actions as evidence signals
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

    # Customer Judgment Engine — CRM, support, contracts, commitments.
    # These are organizational relationship signals, not personal research.
    # Every type models a relationship event (who interacted with which
    # customer account, what commitment was made, what stage the relationship
    # moved to). The actor is always an internal employee; the customer is
    # always in metadata.customer.
    CUSTOMER_MEETING = "customer.meeting"            # internal × customer meeting completed
    CUSTOMER_EMAIL = "customer.email"                # internal × customer email exchanged
    CUSTOMER_STAGE_CHANGE = "customer.stage_change"  # pipeline stage transition (relationship milestone)
    CUSTOMER_COMMITMENT_MADE = "customer.commitment_made"   # a promise was made to the customer
    CUSTOMER_COMMITMENT_KEPT = "customer.commitment_kept"   # a promise was fulfilled
    CUSTOMER_COMMITMENT_BROKEN = "customer.commitment_broken"  # a promise was missed
    CUSTOMER_SUPPORT_TICKET = "customer.support_ticket"     # support interaction
    CUSTOMER_CONTRACT_SIGNED = "customer.contract_signed"   # legal milestone
    CUSTOMER_CONTRACT_RENEWED = "customer.contract_renewed"
    CUSTOMER_CONTRACT_CHURNED = "customer.contract_churned"
    CUSTOMER_DECISION = "customer.decision"          # the customer made a buying/renewal decision
    CUSTOMER_OBJECTION = "customer.objection"        # the customer raised a concern
    CUSTOMER_CHAMPION_ACTIVE = "customer.champion_active"   # champion is engaged
    CUSTOMER_CHAMPION_QUIET = "customer.champion_quiet"     # champion has gone silent (drift signal)


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
    authority_weight: source authority 0..1 (H-05 fix, default 0.5 neutral).
        Derived from org chart via SourceAuthorityModel — NOT caller-supplied
        per-signal in production. Modulates confidence contribution, never
        silences the signal (P6: low authority = lower confidence, not
        invisibility).
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
    authority_weight: float = 0.5  # H-05: 0.5 = neutral, 0.0-1.0 range

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
