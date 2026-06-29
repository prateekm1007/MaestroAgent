"""
OrganizationalLaw — a pattern that has been validated and promoted to a law.

A Law says: "When condition X occurs, outcome Y follows with probability P."

Confidence is computed from:
- Number of validated runtimes (times the law held true)
- Number of counter-examples (times it didn't)
- Diversity of providers that contributed evidence
- Recency of last validation

This is the confidence formula, and it is NOT arbitrary.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class LawStatus(str, Enum):
    CANDIDATE = "candidate"  # Just detected, not yet validated
    VALIDATED = "validated"  # Has held true in multiple runtimes
    STRESSED = "stressed"  # Recent counter-evidence, confidence dropping
    INVALIDATED = "invalidated"  # Disproven
    UNKNOWN_TO_LEADERSHIP = "unknown_to_leadership"  # Validated but not surfaced


class OrganizationalLaw(BaseModel):
    """
    An organizational execution law.

    confidence is computed from evidence — see confidence.py
    """

    law_id: UUID = Field(default_factory=uuid4)
    code: str  # "L-0007", "L-0014", etc.
    statement: str  # Human-readable
    condition: str  # When this happens...
    outcome: str  # ...this follows
    status: LawStatus = LawStatus.CANDIDATE

    # Evidence
    evidence_count: int = 0
    counter_examples: int = 0
    validated_runtimes: int = 0  # Times the law held true
    failed_runtimes: int = 0  # Times it didn't

    # Provenance
    pattern_ids: list[UUID] = Field(default_factory=list)
    signal_ids: list[UUID] = Field(default_factory=list)
    providers: set[str] = Field(default_factory=set)

    # Computed
    confidence: float = 0.0
    known_to_leadership: bool = False

    # Metadata
    first_inferred: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_validated: datetime | None = None
    drift_detected: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    def add_validation(self, signal_id: UUID | None = None) -> None:
        """Record that the law held true in a new runtime."""
        self.validated_runtimes += 1
        self.last_validated = datetime.now(timezone.utc)
        if signal_id and signal_id not in self.signal_ids:
            self.signal_ids.append(signal_id)
        if self.status == LawStatus.CANDIDATE and self.validated_runtimes >= 3:
            self.status = LawStatus.VALIDATED
        if self.status == LawStatus.STRESSED:
            self.status = LawStatus.VALIDATED

    def add_counter_example(self, signal_id: UUID | None = None) -> None:
        """Record that the law failed to hold in a new runtime."""
        self.failed_runtimes += 1
        self.counter_examples += 1
        if signal_id and signal_id not in self.signal_ids:
            self.signal_ids.append(signal_id)
        if self.failed_runtimes >= 2 and self.validated_runtimes > 0:
            ratio = self.failed_runtimes / (self.validated_runtimes + self.failed_runtimes)
            if ratio > 0.3:
                self.status = LawStatus.STRESSED
            if ratio > 0.5:
                self.status = LawStatus.INVALIDATED

    def mark_unknown_to_leadership(self) -> None:
        if self.status == LawStatus.VALIDATED and not self.known_to_leadership:
            self.status = LawStatus.UNKNOWN_TO_LEADERSHIP

    def mark_known_to_leadership(self) -> None:
        self.known_to_leadership = True
        if self.status == LawStatus.UNKNOWN_TO_LEADERSHIP:
            self.status = LawStatus.VALIDATED
