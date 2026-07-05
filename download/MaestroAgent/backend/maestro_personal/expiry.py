"""
V8 Personal Mode — Data Expiration (Guideline P7).

All personal data has a default expiration (24 months, user-configurable).
Expired data is auto-archived or deleted unless the user explicitly opts
to keep it. This applies to signals, memories, and attention signals.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_EXPIRY_MONTHS = 24


@dataclass
class ExpirableItem:
    """An item that can expire. Has a timestamp and an optional 'keep' flag."""
    item_id: str
    item_type: str  # "signal", "memory", "attention_signal"
    timestamp: str
    keep: bool = False  # if True, never expires

    def is_expired(self, expiry_months: int = DEFAULT_EXPIRY_MONTHS) -> bool:
        if self.keep:
            return False
        try:
            ts = datetime.fromisoformat(self.timestamp)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            expiry_date = ts + timedelta(days=expiry_months * 30)
            return datetime.now(timezone.utc) > expiry_date
        except Exception:
            return False


class DataExpiry:
    """Manages data expiration for personal mode.

    All personal data has a default expiration (24 months). The user
    can configure a different expiry period. The user can flag specific
    items as "keep" to prevent expiration.
    """

    _items: list[ExpirableItem] = []
    _expiry_months: dict[str, int] = {}  # user_id → custom expiry months
    _archived: list[dict[str, Any]] = []

    @classmethod
    def register_item(cls, item_id: str, item_type: str, timestamp: str, keep: bool = False) -> ExpirableItem:
        """Register an item for expiration tracking."""
        item = ExpirableItem(item_id=item_id, item_type=item_type, timestamp=timestamp, keep=keep)
        cls._items.append(item)
        return item

    @classmethod
    def set_keep(cls, item_id: str, keep: bool = True) -> bool:
        """Set or unset the 'keep' flag for an item."""
        for item in cls._items:
            if item.item_id == item_id:
                item.keep = keep
                return True
        return False

    @classmethod
    def set_expiry_months(cls, user_id: str, months: int) -> None:
        """Set custom expiry period for a user."""
        cls._expiry_months[user_id] = months

    @classmethod
    def get_expiry_months(cls, user_id: str) -> int:
        """Get expiry period for a user (default 24 months)."""
        return cls._expiry_months.get(user_id, DEFAULT_EXPIRY_MONTHS)

    @classmethod
    def sweep(cls, user_id: str = "default") -> dict[str, Any]:
        """Sweep expired items. Archive (not delete) by default.

        Returns a summary of what was archived.
        """
        expiry_months = cls.get_expiry_months(user_id)
        archived_count = 0
        kept_count = 0

        remaining: list[ExpirableItem] = []
        for item in cls._items:
            if item.is_expired(expiry_months):
                cls._archived.append({
                    "item_id": item.item_id,
                    "item_type": item.item_type,
                    "timestamp": item.timestamp,
                    "archived_at": datetime.now(timezone.utc).isoformat(),
                    "reason": "expired" if not item.keep else "kept_flag_prevented_expiry",
                })
                if not item.keep:
                    archived_count += 1
                else:
                    kept_count += 1
                    remaining.append(item)
            else:
                remaining.append(item)

        cls._items = remaining
        logger.info("Expiry sweep: %d archived, %d kept, %d remaining", archived_count, kept_count, len(remaining))
        return {
            "archived": archived_count,
            "kept": kept_count,
            "remaining": len(remaining),
            "expiry_months": expiry_months,
        }

    @classmethod
    def get_archived(cls) -> list[dict[str, Any]]:
        """Get archived items."""
        return cls._archived

    @classmethod
    def clear(cls) -> None:
        """Clear all items (for testing)."""
        cls._items = []
        cls._expiry_months = {}
        cls._archived = []
