"""
Receipt — provenance chain element.

Every OEM update is traceable back to the original signals that caused it.
A Receipt records: which signal, at what time, produced which change.

Receipts chain together: Signal → Receipt → LearningObject → Pattern → Law → Recommendation.
This is the evidence chain the CEO can replay end-to-end.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Receipt(BaseModel):
    """
    A provenance record. One signal produces one or more receipts.
    A receipt links a signal to the OEM change it caused.
    """

    receipt_id: UUID = Field(default_factory=uuid4)
    signal_id: UUID  # The signal that caused this receipt
    signal_type: str
    signal_provider: str
    signal_timestamp: datetime
    signal_actor: str
    signal_artifact: str  # The PR URL, ticket ID, etc.
    oem_change: str  # What changed in the OEM (e.g., "law.L-0007.evidence_added")
    oem_target: str  # What was affected (e.g., "L-0007")
    change_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    change_data: dict[str, Any] = Field(default_factory=dict)

    def to_chain_entry(self) -> dict[str, Any]:
        return {
            "receipt_id": str(self.receipt_id),
            "signal_type": self.signal_type,
            "provider": self.signal_provider,
            "artifact": self.signal_artifact,
            "actor": self.signal_actor,
            "oem_change": self.oem_change,
            "oem_target": self.oem_target,
            "timestamp": self.change_timestamp.isoformat(),
        }


class ReceiptChain(BaseModel):
    """
    A chain of receipts linking a final OEM output (law, recommendation, prediction)
    back to the original signals that produced it.
    """

    chain_id: UUID = Field(default_factory=uuid4)
    target: str  # What this chain explains (e.g., "L-0007", "rec:hiring-plan")
    target_type: str  # "law", "recommendation", "prediction", "pattern"
    receipts: list[Receipt] = Field(default_factory=list)

    def add(self, receipt: Receipt) -> None:
        self.receipts.append(receipt)

    def to_display(self) -> list[dict[str, Any]]:
        """Convert to a display-friendly list for the UI provenance chain."""
        return [r.to_chain_entry() for r in self.receipts]

    def is_complete(self) -> bool:
        """A chain is complete if it has at least one receipt."""
        return len(self.receipts) > 0

    def get_signals(self) -> list[UUID]:
        """Return all signal IDs in this chain."""
        return [r.signal_id for r in self.receipts]
