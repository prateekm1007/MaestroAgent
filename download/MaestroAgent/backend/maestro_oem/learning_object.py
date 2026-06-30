"""
LearningObject — evidence unit derived from signals.

A LearningObject is what the OEM actually stores and reasons over.
Raw signals are transient; LearningObjects are persistent.

Types:
- DUPLICATE_WORK: same artifact built by different teams
- BOTTLENECK: a person or process that delays work
- HIDDEN_EXPERT: undocumented knowledge holder
- HANDOFF_DELAY: latency at a transfer point
- INCIDENT_PATTERN: recurring failure mode
- VELOCITY_DROP: sustained decrease in output
- DEPARTURE_RISK: signals indicating someone may leave
- KNOWLEDGE_DEATH: knowledge that doesn't transfer
- APPROVAL_GATE: a person who must approve before work proceeds
- DECISION_PATTERN: how decisions are made (who, how long, outcome)
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class LearningObjectType(str, Enum):
    DUPLICATE_WORK = "duplicate_work"
    BOTTLENECK = "bottleneck"
    HIDDEN_EXPERT = "hidden_expert"
    HANDOFF_DELAY = "handoff_delay"
    INCIDENT_PATTERN = "incident_pattern"
    VELOCITY_DROP = "velocity_drop"
    DEPARTURE_RISK = "departure_risk"
    KNOWLEDGE_DEATH = "knowledge_death"
    APPROVAL_GATE = "approval_gate"
    DECISION_PATTERN = "decision_pattern"
    RELEASE_PATTERN = "release_pattern"
    REVIEW_PATTERN = "review_pattern"
    # Customer Judgment Engine — relationship-level Learning Objects.
    # These are NOT people records; they model the organizational relationship
    # with a customer account (who champions us, what was promised, how the
    # relationship is drifting, what risks are accumulating).
    CUSTOMER_COMMITTEE_ROLE = "customer_committee_role"  # inferred buying-committee role (champion, economic buyer, etc.)
    CUSTOMER_COMMITMENT = "customer_commitment"           # a promise made to a customer (with due date + status)
    CUSTOMER_DECISION_PATTERN = "customer_decision_pattern"  # how this customer historically decides
    CUSTOMER_DRIFT = "customer_drift"                     # relationship momentum / trust / engagement trend
    CUSTOMER_RISK = "customer_risk"                       # accumulated risk on a customer relationship


class LearningObject(BaseModel):
    """
    A piece of evidence the OEM has learned from signals.

    confidence is computed from:
    - Number of supporting signals
    - Diversity of providers
    - Recency of evidence
    - Contradiction count

    It is NOT arbitrary. See confidence.py for the math.
    """

    lo_id: UUID = Field(default_factory=uuid4)
    type: LearningObjectType
    title: str  # Human-readable summary
    description: str
    entities: list[str] = Field(default_factory=list)  # Person/team IDs involved
    artifacts: list[str] = Field(default_factory=list)  # PR/ticket/doc IDs
    signal_ids: list[UUID] = Field(default_factory=list)  # Signals that produced this
    providers: set[str] = Field(default_factory=set)  # Which providers contributed
    confidence: float = 0.0  # Computed, never hardcoded
    evidence_count: int = 0  # Number of supporting signals
    contradiction_count: int = 0  # Number of contradicting signals
    first_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    def add_evidence(self, signal_id: UUID, provider: str) -> None:
        """Add a supporting signal."""
        if signal_id not in self.signal_ids:
            self.signal_ids.append(signal_id)
            self.evidence_count += 1
            self.providers.add(provider)
            self.last_seen = datetime.now(timezone.utc)

    def add_contradiction(self) -> None:
        """Mark a contradicting signal."""
        self.contradiction_count += 1

    def merge(self, other: LearningObject) -> LearningObject:
        """Merge another LO of the same type into this one."""
        if self.type != other.type:
            raise ValueError("Cannot merge LearningObjects of different types")
        self.signal_ids.extend(
            sid for sid in other.signal_ids if sid not in self.signal_ids
        )
        self.artifacts.extend(
            a for a in other.artifacts if a not in self.artifacts
        )
        self.entities.extend(
            e for e in other.entities if e not in self.entities
        )
        self.providers.update(other.providers)
        self.evidence_count = len(self.signal_ids)
        self.contradiction_count += other.contradiction_count
        self.last_seen = max(self.last_seen, other.last_seen)
        return self
