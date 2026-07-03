"""Loop 4 — Organizational Learning Ledger.

CEO directive (auditor recommendation, CEO-validated): "Loop 4 —
Organizational Learning: cross-case pattern detection and delivery-policy
learning. This is the final loop — it connects the first three loops into
a unified learning system."

The OrganizationalLearningLedger collects Learning Ledger entries from
all 3 loops:
  - Loop 1: commitment learnings (whisper_id, action, outcome, learning_entry)
  - Loop 2: meeting learnings (meeting_id, outcome, learning_entry)
  - Loop 3: decision learnings (decision_id, hypothesis, outcome, learning_entry)

Each entry is tagged with its source_loop ("commitment", "meeting",
"decision") so the CrossLoopPatternDetector can find patterns that span
loops.

This is the unified memory. Loops 1-3 each had their own Learning Ledger;
Loop 4 aggregates them so the system can learn about its own delivery
effectiveness.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class LearningEntry:
    """A single learning entry from any of the 3 loops.

    Attributes:
        source_loop: "commitment" | "meeting" | "decision"
        entity: The customer/org this learning is about
        learning_entry: The honest sentence from the loop's Learning Ledger
        action: For commitment entries — "acted" | "ignored" | "overrode"
        outcome: The observed outcome ("honored", "broken", etc.)
        delivery_context: For commitment entries — when/how the Whisper was delivered
        id: The loop-specific ID (whisper_id, meeting_id, decision_id)
        recorded_at: When this entry was recorded
    """

    source_loop: str
    entity: str
    learning_entry: str
    action: str | None = None
    outcome: str | None = None
    delivery_context: str | None = None
    id: str = ""
    recorded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_loop": self.source_loop,
            "entity": self.entity,
            "learning_entry": self.learning_entry,
            "action": self.action,
            "outcome": self.outcome,
            "delivery_context": self.delivery_context,
            "id": self.id,
            "recorded_at": self.recorded_at.isoformat() if hasattr(self.recorded_at, "isoformat") else str(self.recorded_at),
        }


class OrganizationalLearningLedger:
    """Collects Learning Ledger entries from all 3 loops.

    Usage:
        ledger = OrganizationalLearningLedger()
        ledger.record_commitment_learning(entity="Globex", whisper_id="wspr-1",
            action="ignored", outcome="broken", learning_entry="...")
        ledger.record_meeting_learning(entity="Globex", meeting_id="mtg-1",
            outcome="commitment_broken", learning_entry="...")
        ledger.record_decision_learning(entity="Globex", decision_id="dec-1",
            hypothesis="...", outcome="...", learning_entry="...")
        all_entries = ledger.get_all_entries()
    """

    def __init__(self) -> None:
        self._entries: list[LearningEntry] = []
        self._lock = threading.Lock()

    def record_commitment_learning(
        self,
        entity: str,
        whisper_id: str,
        action: str,
        outcome: str,
        learning_entry: str,
        delivery_context: str | None = None,
    ) -> None:
        """Record a learning entry from Loop 1 (commitment intelligence)."""
        with self._lock:
            self._entries.append(LearningEntry(
                source_loop="commitment",
                entity=entity,
                learning_entry=learning_entry,
                action=action,
                outcome=outcome,
                delivery_context=delivery_context,
                id=whisper_id,
            ))

    def record_meeting_learning(
        self,
        entity: str,
        meeting_id: str,
        outcome: str,
        learning_entry: str,
    ) -> None:
        """Record a learning entry from Loop 2 (meeting intelligence)."""
        with self._lock:
            self._entries.append(LearningEntry(
                source_loop="meeting",
                entity=entity,
                learning_entry=learning_entry,
                outcome=outcome,
                id=meeting_id,
            ))

    def record_decision_learning(
        self,
        entity: str,
        decision_id: str,
        hypothesis: str,
        outcome: str,
        learning_entry: str,
    ) -> None:
        """Record a learning entry from Loop 3 (decision intelligence)."""
        with self._lock:
            self._entries.append(LearningEntry(
                source_loop="decision",
                entity=entity,
                learning_entry=learning_entry,
                outcome=outcome,
                id=decision_id,
            ))

    def get_all_entries(self) -> list[LearningEntry]:
        """Get all learning entries from all 3 loops."""
        with self._lock:
            return list(self._entries)

    def get_entries_by_loop(self, source_loop: str) -> list[LearningEntry]:
        """Get entries from a specific loop."""
        with self._lock:
            return [e for e in self._entries if e.source_loop == source_loop]

    def total_entries(self) -> int:
        """Total number of learning entries across all loops."""
        with self._lock:
            return len(self._entries)

    def clear(self) -> None:
        """Clear all entries (for testing)."""
        with self._lock:
            self._entries.clear()
