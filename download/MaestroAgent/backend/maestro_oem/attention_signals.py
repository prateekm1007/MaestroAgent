"""
V8 P1-5 — The Briefing Learns (Attention Signals).

Records which briefing items the CEO clicks. Over time, the briefing
ranking weights items by historical attention. If the CEO consistently
clicks "commitments" first, commitments move to the top. If they never
click "risks", risks move to the bottom (but are never hidden —
Radical Honesty).

Attention signals never hide information; they only reorder it. The
CEO can reset the ranking in settings.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AttentionSignal:
    """A single attention signal — a click on a briefing item."""
    item_type: str = ""  # "commitments", "one_thing", "money", "knowledge", etc.
    item_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_type": self.item_type,
            "item_id": self.item_id,
            "timestamp": self.timestamp,
        }


class AttentionSignalStore:
    """In-memory store of attention signals.

    Records which briefing item types the CEO clicks. The briefing
    ranking uses this to reorder items by historical attention.

    Reordering rules (Radical Honesty — never hide, only reorder):
      - Items with more clicks move up
      - Items with 0 clicks stay in their default position (not hidden)
      - The CEO can reset all attention signals in settings
    """

    _signals: list[AttentionSignal] = []

    @classmethod
    def record(cls, item_type: str, item_id: str = "") -> AttentionSignal:
        """Record an attention signal."""
        signal = AttentionSignal(item_type=item_type, item_id=item_id)
        cls._signals.append(signal)
        logger.info("Attention signal: item_type=%s item_id=%s", item_type, item_id)
        return signal

    @classmethod
    def get_click_counts(cls) -> dict[str, int]:
        """Get click counts per item type."""
        counts: Counter[str] = Counter()
        for s in cls._signals:
            counts[s.item_type] += 1
        return dict(counts)

    @classmethod
    def get_summary(cls) -> dict[str, Any]:
        """Get a summary of attention signals."""
        counts = cls.get_click_counts()
        total = sum(counts.values())
        # Sort by click count descending
        ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return {
            "total_clicks": total,
            "click_counts": counts,
            "ranked": [{"item_type": k, "clicks": v} for k, v in ranked],
            "signal_count": len(cls._signals),
        }

    @classmethod
    def get_ranking_weight(cls, item_type: str) -> float:
        """Get the ranking weight for an item type.

        Returns a float >= 0.0. Higher = more clicks = should appear higher.
        Items with 0 clicks get weight 0.0 (neutral — stay in default position).
        Items with clicks get weight proportional to their share of total clicks.
        """
        counts = cls.get_click_counts()
        total = sum(counts.values())
        if total == 0:
            return 0.0
        return counts.get(item_type, 0) / total

    @classmethod
    def clear(cls) -> None:
        """Clear all signals (for testing or reset)."""
        cls._signals = []
