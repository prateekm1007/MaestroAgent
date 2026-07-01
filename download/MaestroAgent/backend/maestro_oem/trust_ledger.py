"""
V8 P1-1 — Progressive Trust Ledger.

Records every write-back action (manual and future auto-executed):
action_id, action_type, trust_score_at_execution, approver, outcome,
timestamp. This is the safety infrastructure for P1-2 (progressive
trust / auto-execute). No auto-execute path is added yet — the ledger
only records manual approvals. When P1-2 is built, it reads this
ledger to compute trust scores.

API: GET /api/oem/trust/ledger
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LedgerEntry:
    """A single trust ledger entry recording one write-back action."""
    action_id: str = ""
    provider: str = ""
    action_type: str = ""
    approver: str = ""
    trust_score_at_execution: int = 0
    outcome: str = "success"  # "success" | "failure" | "rolled_back"
    auto: bool = False  # True if auto-executed (P1-2), False if manually approved
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "provider": self.provider,
            "action_type": self.action_type,
            "approver": self.approver,
            "trust_score_at_execution": self.trust_score_at_execution,
            "outcome": self.outcome,
            "auto": self.auto,
            "timestamp": self.timestamp,
        }


class TrustLedger:
    """Records every write-back action for trust scoring.

    The ledger is the foundation of progressive trust (P1-2). It records:
      - Every manual approval (auto=False)
      - Every future auto-execution (auto=True, when P1-2 is built)
      - The outcome: success, failure, or rolled_back

    Trust score computation (used by P1-2):
      trust_score = (successful_actions - rolled_back_actions) per (user, action_type)
      Auto-execute eligibility: trust_score >= 10 AND rolled_back == 0

    The ledger is in-memory for the pilot. In production, it persists to
    the database (like the decision_log table).
    """

    _entries: list[LedgerEntry] = []

    @classmethod
    def record(
        cls,
        action_id: str,
        provider: str,
        action_type: str,
        approver: str,
        outcome: str = "success",
        auto: bool = False,
    ) -> LedgerEntry:
        """Record a write-back action in the ledger.

        Called by the WriteBackService.approve() method after every
        execution (manual or auto). The trust_score_at_execution is
        computed from the current ledger state for this (approver, action_type)
        pair at the time of recording.
        """
        trust_score = cls.compute_trust_score(approver, provider, action_type)
        entry = LedgerEntry(
            action_id=action_id,
            provider=provider,
            action_type=action_type,
            approver=approver,
            trust_score_at_execution=trust_score,
            outcome=outcome,
            auto=auto,
        )
        cls._entries.append(entry)
        logger.info(
            "Trust ledger: recorded %s.%s by %s (outcome=%s, trust=%d, auto=%s)",
            provider, action_type, approver, outcome, trust_score, auto,
        )
        return entry

    @classmethod
    def compute_trust_score(
        cls, user_id: str, provider: str, action_type: str,
    ) -> int:
        """Compute the trust score for a (user, provider, action_type) pair.

        trust_score = successful_actions - rolled_back_actions
        """
        successful = sum(
            1 for e in cls._entries
            if e.approver == user_id
            and e.provider == provider
            and e.action_type == action_type
            and e.outcome == "success"
        )
        rolled_back = sum(
            1 for e in cls._entries
            if e.approver == user_id
            and e.provider == provider
            and e.action_type == action_type
            and e.outcome == "rolled_back"
        )
        return successful - rolled_back

    @classmethod
    def is_auto_execute_eligible(
        cls, user_id: str, provider: str, action_type: str,
    ) -> bool:
        """Check if a (user, provider, action_type) pair is eligible for auto-execute.

        Eligible when: trust_score >= 10 AND rolled_back == 0.
        This is used by P1-2 (progressive trust) to decide whether to
        auto-execute or require manual approval.
        """
        trust_score = cls.compute_trust_score(user_id, provider, action_type)
        rolled_back = sum(
            1 for e in cls._entries
            if e.approver == user_id
            and e.provider == provider
            and e.action_type == action_type
            and e.outcome == "rolled_back"
        )
        return trust_score >= 10 and rolled_back == 0

    @classmethod
    def get_entries(
        cls,
        user_id: str = "",
        provider: str = "",
        action_type: str = "",
    ) -> list[LedgerEntry]:
        """Get ledger entries, optionally filtered."""
        entries = cls._entries
        if user_id:
            entries = [e for e in entries if e.approver == user_id]
        if provider:
            entries = [e for e in entries if e.provider == provider]
        if action_type:
            entries = [e for e in entries if e.action_type == action_type]
        return entries

    @classmethod
    def clear(cls) -> None:
        """Clear all entries (for testing)."""
        cls._entries = []

    @classmethod
    def get_summary(cls, user_id: str = "") -> dict[str, Any]:
        """Get a summary of the ledger."""
        entries = cls.get_entries(user_id=user_id)
        return {
            "total_entries": len(entries),
            "total_success": sum(1 for e in entries if e.outcome == "success"),
            "total_failure": sum(1 for e in entries if e.outcome == "failure"),
            "total_rolled_back": sum(1 for e in entries if e.outcome == "rolled_back"),
            "total_auto": sum(1 for e in entries if e.auto),
            "total_manual": sum(1 for e in entries if not e.auto),
        }
