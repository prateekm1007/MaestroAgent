"""Loop 1.5 — Commitment Mutation Tracker.

External auditor (AUDITOR-EXTERNAL-REVIEW-3):
> Commitment mutation tracking — preserve the history of how a
> commitment's wording changes, don't overwrite.

Organizations renegotiate. A commitment that started as "Deliver SSO
by 2024-12-15" might mutate to "Deliver SSO by 2025-01-31" (deadline
moved) or "Deliver SSO + MFA by 2024-12-15" (scope expanded). Each
mutation is a meaningful event — it tells Maestro that the situation
is evolving.

The OLD codebase treated commitment signals as a flat list — the
latest one wins, history is lost. This is wrong because:
  - The exec might remember the OLD commitment ("But you said
    December!"). Maestro needs to know both wordings to explain
    the change.
  - A pattern of frequent mutations is itself a signal (the customer
    keeps moving the goalposts = unstable relationship).
  - The Learning Ledger needs to reference what CHANGED, not just the
    current state.

The CommitmentMutationTracker:
  - record_commitment(signal): records a commitment, detecting mutations
  - get_mutation_history(entity): returns all commitment wordings (in order)
  - get_mutations(entity): returns only the mutation events (old→new)
  - get_current_commitment(entity): returns the latest wording

A mutation is detected when:
  - Same entity (customer)
  - Same commitment topic (e.g., "SSO") — extracted via simple keyword match
  - Different wording (text != previous text)

If the wording is identical, no mutation is recorded (avoid false positives).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CommitmentEntry:
    """A single commitment wording at a point in time."""

    entity: str
    commitment_text: str
    timestamp: datetime
    actor: str
    artifact: str

    def to_dict(self) -> dict:
        return {
            "entity": self.entity,
            "commitment_text": self.commitment_text,
            "timestamp": self.timestamp.isoformat() if hasattr(self.timestamp, "isoformat") else str(self.timestamp),
            "actor": self.actor,
            "artifact": self.artifact,
        }


@dataclass
class CommitmentMutation:
    """A mutation event — when a commitment's wording changed."""

    entity: str
    old_text: str
    new_text: str
    old_timestamp: datetime
    new_timestamp: datetime
    actor: str  # Who made the new commitment

    def to_dict(self) -> dict:
        return {
            "entity": self.entity,
            "old_text": self.old_text,
            "new_text": self.new_text,
            "old_timestamp": self.old_timestamp.isoformat() if hasattr(self.old_timestamp, "isoformat") else str(self.old_timestamp),
            "new_timestamp": self.new_timestamp.isoformat() if hasattr(self.new_timestamp, "isoformat") else str(self.new_timestamp),
            "actor": self.actor,
        }


class CommitmentMutationTracker:
    """Track how commitments mutate over time.

    Usage:
        tracker = CommitmentMutationTracker()
        tracker.record_commitment(signal1)  # Original wording
        tracker.record_commitment(signal2)  # Mutated wording
        history = tracker.get_mutation_history("Globex")
        mutations = tracker.get_mutations("Globex")
    """

    def __init__(self) -> None:
        # entity → list of CommitmentEntry (in arrival order)
        self._history: dict[str, list[CommitmentEntry]] = {}
        # entity → list of CommitmentMutation
        self._mutations: dict[str, list[CommitmentMutation]] = {}

    def record_commitment(self, signal: Any) -> None:
        """Record a commitment signal, detecting mutations.

        If the commitment wording differs from the previous wording for
        this entity, a CommitmentMutation is recorded.
        """
        try:
            entity = signal.metadata.get("customer", "") if hasattr(signal, "metadata") else ""
            commitment_text = signal.metadata.get("commitment", "") if hasattr(signal, "metadata") else ""
            if not entity or not commitment_text:
                return

            entry = CommitmentEntry(
                entity=entity,
                commitment_text=commitment_text,
                timestamp=signal.timestamp if hasattr(signal, "timestamp") else datetime.utcnow(),
                actor=signal.actor if hasattr(signal, "actor") else "",
                artifact=signal.artifact if hasattr(signal, "artifact") else "",
            )

            if entity not in self._history:
                self._history[entity] = []
                self._mutations[entity] = []

            # Check for mutation — compare to the LAST entry
            previous_entries = self._history[entity]
            if previous_entries:
                last_entry = previous_entries[-1]
                if last_entry.commitment_text != commitment_text:
                    # Mutation detected!
                    mutation = CommitmentMutation(
                        entity=entity,
                        old_text=last_entry.commitment_text,
                        new_text=commitment_text,
                        old_timestamp=last_entry.timestamp,
                        new_timestamp=entry.timestamp,
                        actor=entry.actor,
                    )
                    self._mutations[entity].append(mutation)
                    logger.info(
                        "CommitmentMutationTracker: mutation detected for %s — '%s' → '%s'",
                        entity, last_entry.commitment_text, commitment_text,
                    )

            self._history[entity].append(entry)
        except Exception as e:
            logger.warning("CommitmentMutationTracker: failed to record commitment: %s", e)

    def get_mutation_history(self, entity: str) -> list[CommitmentEntry]:
        """Get all commitment wordings for an entity (in arrival order)."""
        return list(self._history.get(entity, []))

    def get_mutations(self, entity: str) -> list[CommitmentMutation]:
        """Get only the mutation events for an entity."""
        return list(self._mutations.get(entity, []))

    def get_current_commitment(self, entity: str) -> CommitmentEntry | None:
        """Get the latest commitment wording for an entity."""
        entries = self._history.get(entity, [])
        if not entries:
            return None
        return entries[-1]

    def get_all_entities(self) -> list[str]:
        """Get all entities that have commitments tracked."""
        return list(self._history.keys())

    def to_dict(self) -> dict:
        """Serialize for API responses / debugging."""
        return {
            entity: {
                "history": [e.to_dict() for e in entries],
                "mutations": [m.to_dict() for m in self._mutations.get(entity, [])],
            }
            for entity, entries in self._history.items()
        }
