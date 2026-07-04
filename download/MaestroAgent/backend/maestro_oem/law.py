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
    # C-002 fix: Track content hashes to prevent duplicate-content inflation.
    # Same text via Slack + email + Jira + Confluence = 1 source, not 4.
    content_hashes: set[str] = Field(default_factory=set, exclude=True)

    # Provenance
    pattern_ids: list[UUID] = Field(default_factory=list)
    signal_ids: list[UUID] = Field(default_factory=list)
    providers: set[str] = Field(default_factory=set)

    # Computed
    confidence: float = 0.0
    known_to_leadership: bool = False

    # V8 Competitor Analysis Feature C — Verified Knowledge Layer.
    # Human sign-off before high-confidence citation. The Guru lesson:
    # verified knowledge is the differentiator — human-verified laws that
    # no competitor has. When a human verifies a law, their identity and
    # the timestamp are recorded. Only verified laws are cited as "facts"
    # in high-stakes contexts (briefings, playbooks, write-backs).
    verified_by: str | None = None  # email of the verifier
    verified_at: datetime | None = None  # when the law was verified

    # Metadata
    first_inferred: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_validated: datetime | None = None
    drift_detected: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    def add_validation(self, signal_id: UUID | None = None, content_hash: str | None = None) -> None:
        """Record that the law held true in a new runtime.

        C-002 fix: If content_hash is provided and already seen, the validation
        is counted as a DUPLICATE — not a new independent source. This prevents
        the same text arriving via Slack + email + Jira + Confluence from
        inflating validated_runtimes 4x.
        """
        # C-002: Check content hash for dedup
        if content_hash and content_hash in self.content_hashes:
            return  # Duplicate content — don't count as new validation
        if content_hash:
            self.content_hashes.add(content_hash)

        self.validated_runtimes += 1
        self.evidence_count = max(self.evidence_count, self.validated_runtimes + self.failed_runtimes)
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
        self.evidence_count = max(self.evidence_count, self.validated_runtimes + self.failed_runtimes)
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
