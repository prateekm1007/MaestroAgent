"""
Attention Allocation — V5 Spec #3

Consciousness knows where attention IS → Attention decides where it
SHOULD BE. Produces:
  - current_allocation: where the org's attention actually is
  - recommended_allocation: where it should be
  - attention_thieves: what is stealing focus
  - should_ignore: what to deprioritize

API: GET /api/oem/attention
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from typing import Any

logger = logging.getLogger(__name__)


class AttentionEngine:
    """Decide where the organization's attention should be.

    Attention is the organization's scarcest resource. This engine
    analyzes where attention is currently allocated (from signal
    distribution), identifies what's stealing focus (disproportionate
    signal volume), and recommends a reallocation.
    """

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def allocate(self) -> dict[str, Any]:
        """Produce an attention allocation recommendation."""
        current = self._assess_current()
        thieves = self._find_thieves(current)
        ignore = self._find_should_ignore(current)
        recommended = self._recommend(current, thieves, ignore)

        return {
            "current_allocation": current,
            "recommended_allocation": recommended,
            "attention_thieves": thieves,
            "should_ignore": ignore,
            "summary": self._summarize(current, recommended, thieves, ignore),
        }

    def _assess_current(self) -> list[dict[str, Any]]:
        """Assess where attention currently is, by domain."""
        domain_counts = Counter()
        for s in self.signals:
            domain = s.metadata.get("domain", "unknown")
            domain_counts[domain] += 1

        total = sum(domain_counts.values())
        if total == 0:
            return [{"domain": "unknown", "percentage": 100, "signal_count": 0}]

        allocation = []
        for domain, count in domain_counts.most_common():
            allocation.append({
                "domain": domain,
                "percentage": round(count / total * 100),
                "signal_count": count,
            })
        return allocation

    def _find_thieves(self, current: list[dict]) -> list[dict[str, Any]]:
        """Find what is stealing disproportionate attention."""
        thieves = []
        for item in current:
            if item["percentage"] > 40:
                thieves.append({
                    "domain": item["domain"],
                    "percentage": item["percentage"],
                    "reason": f"{item['domain']} is consuming {item['percentage']}% of organizational attention. This is disproportionate — no single domain should dominate.",
                    "signal_count": item["signal_count"],
                })
        return thieves

    def _find_should_ignore(self, current: list[dict]) -> list[dict[str, Any]]:
        """Find what to deprioritize."""
        ignore = []
        for item in current:
            if item["percentage"] < 5 and item["signal_count"] < 3:
                ignore.append({
                    "domain": item["domain"],
                    "reason": f"Only {item['signal_count']} signals from {item['domain']}. This is too little to draw conclusions. Stop monitoring until it grows.",
                    "signal_count": item["signal_count"],
                })
        return ignore

    def _recommend(self, current: list, thieves: list, ignore: list) -> list[dict[str, Any]]:
        """Recommend a reallocation."""
        if not current:
            return []

        # Simple heuristic: cap any domain at 35%, redistribute the excess
        # to under-attended domains
        recommended = []
        excess = 0
        for item in current:
            if item["percentage"] > 35:
                excess += item["percentage"] - 35
                recommended.append({**item, "percentage": 35})
            else:
                recommended.append(item)

        # Distribute excess to under-attended domains
        if excess > 0:
            under_attended = [r for r in recommended if r["percentage"] < 20]
            if under_attended:
                share = excess / len(under_attended)
                for r in under_attended:
                    r["percentage"] = min(35, r["percentage"] + int(share))

        return recommended

    def _summarize(self, current, recommended, thieves, ignore) -> str:
        if not thieves and not ignore:
            return "Your organization's attention is well-distributed. No reallocation needed."
        parts = []
        if thieves:
            parts.append(f"{len(thieves)} {'domain' if len(thieves) == 1 else 'domains'} {'is' if len(thieves) == 1 else 'are'} stealing focus")
        if ignore:
            parts.append(f"{len(ignore)} {'domain' if len(ignore) == 1 else 'domains'} {'should' if len(ignore) == 1 else 'should'} be deprioritized")
        return f"{' and '.join(parts)}. Maestro recommends reallocating attention."
