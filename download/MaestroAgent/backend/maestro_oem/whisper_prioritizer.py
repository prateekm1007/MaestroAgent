"""Round 3 Fix 2: Cross-whisper prioritization + batched digest.

External auditor finding (Round 3):
> Batching/prioritization: decide_delivery evaluates per-whisper. No
> cross-whisper ranking. If 50 legitimately different things happened
> overnight, the system evaluates each independently rather than batching
> into a digest.

The WhisperPrioritizer ranks delivered whispers by priority and returns
the top N for immediate delivery, batching the rest for a morning digest.

Ranking factors (highest first):
  1. Stakes: high > medium > low
  2. Recency: newer signals > older
  3. Entity risk: broken commitment > objection > champion quiet > normal

Usage:
    prioritizer = WhisperPrioritizer(top_n=3)
    result = prioritizer.prioritize(delivered_whispers)
    # result = {"delivered": [...top 3], "batched_whispers": [...rest]}
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# Stakes ranking — higher number = higher priority
_STAKES_RANK = {"high": 3, "medium": 2, "low": 1, "": 0}


class WhisperPrioritizer:
    """Rank delivered whispers by priority. Top N delivered, rest batched.

    The prioritizer runs AFTER the delivery gate. The gate decides which
    whispers are eligible for delivery. The prioritizer decides which of
    those eligible whispers actually get surfaced now vs. batched for a
    morning digest.

    This prevents the "50 things happened overnight" problem: the exec
    sees the top 3 most important, not a flood of 50 cards.
    """

    def __init__(self, top_n: int = 3) -> None:
        self._top_n = top_n

    def prioritize(self, whispers: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        """Rank whispers and split into delivered (top N) + batched (rest).

        Args:
            whispers: List of whisper dicts that passed the delivery gate.
                Each should have: whisper_id, entity, insight, delivery_decision,
                stakes (optional: "high"|"medium"|"low").

        Returns:
            {"delivered": [...top N], "batched_whispers": [...rest]}
        """
        if not whispers:
            return {"delivered": [], "batched_whispers": []}

        # Sort by priority (highest first)
        ranked = sorted(whispers, key=self._priority_key, reverse=True)

        # Split: top N delivered, rest batched
        delivered = ranked[:self._top_n]
        batched = ranked[self._top_n:]

        # Mark each whisper with its priority rank (for transparency)
        for i, w in enumerate(delivered, 1):
            w["priority_rank"] = i
        for i, w in enumerate(batched, 1):
            w["priority_rank"] = self._top_n + i

        logger.info(
            "WhisperPrioritizer: %d delivered, %d batched (top_n=%d)",
            len(delivered), len(batched), self._top_n,
        )

        return {
            "delivered": delivered,
            "batched_whispers": batched,
        }

    def _priority_key(self, whisper: dict[str, Any]) -> tuple[int, int]:
        """Compute a priority key for ranking (higher = more important).

        Factors:
          1. Stakes (high=3, medium=2, low=1)
          2. Entity risk (broken commitment=3, objection=2, champion_quiet=1, normal=0)
        """
        stakes = _STAKES_RANK.get(whisper.get("stakes", "").lower(), 0)

        # Entity risk from whisper type / delivery context
        entity_risk = 0
        whisper_type = whisper.get("whisper_type", "").lower()
        if "broken" in whisper_type or "churn" in whisper_type:
            entity_risk = 3
        elif "objection" in whisper_type:
            entity_risk = 2
        elif "champion_quiet" in whisper_type or "drift" in whisper_type:
            entity_risk = 1

        # High-stakes signal flag
        if whisper.get("has_high_stakes_signal"):
            entity_risk = max(entity_risk, 3)

        return (stakes, entity_risk)
