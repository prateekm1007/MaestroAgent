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
        narrative = self._narrative(current, thieves, ignore)

        return {
            "current_allocation": current,
            "recommended_allocation": recommended,
            "attention_thieves": thieves,
            "should_ignore": ignore,
            "narrative": narrative,
            "summary": narrative,
        }

    def _assess_current(self) -> list[dict[str, Any]]:
        """Assess where attention currently is, by domain.

        Filters out 'unknown' domain (signals without domain metadata)
        so the allocation reflects real organizational attention, not
        a data-inference gap. Normalizes percentages to sum to 100%.
        """
        domain_counts = Counter()
        unknown_count = 0
        for s in self.signals:
            domain = s.metadata.get("domain", "")
            if not domain or domain == "unknown":
                unknown_count += 1
                continue
            domain_counts[domain] += 1

        total = sum(domain_counts.values())
        if total == 0:
            return [{"domain": "untracked", "percentage": 100, "signal_count": 0,
                     "narrative": "Most signals lack domain metadata. Connect more providers to improve domain inference."}]

        allocation = []
        for domain, count in domain_counts.most_common():
            pct = round(count / total * 100)
            allocation.append({
                "domain": domain,
                "percentage": pct,
                "signal_count": count,
            })

        # Normalize: adjust the largest domain to make percentages sum to 100
        diff = 100 - sum(a["percentage"] for a in allocation)
        if diff != 0 and allocation:
            allocation[0]["percentage"] += diff

        return allocation

    def _find_thieves(self, current: list[dict]) -> list[dict[str, Any]]:
        """Find what is stealing disproportionate attention."""
        thieves = []
        for item in current:
            if item["domain"] == "untracked":
                continue
            if item["percentage"] > 40:
                thieves.append({
                    "domain": item["domain"],
                    "percentage": item["percentage"],
                    "reason": f"{item['domain']} is consuming {item['percentage']}% of organizational attention. This is disproportionate — no single domain should dominate.",
                    "narrative": f"Your organization is over-indexing on {item['domain']}. Consider whether this is intentional or whether other domains are being neglected.",
                    "signal_count": item["signal_count"],
                })
        return thieves

    def _find_should_ignore(self, current: list[dict]) -> list[dict[str, Any]]:
        """Find what to deprioritize."""
        ignore = []
        for item in current:
            if item["domain"] == "untracked":
                continue
            if item["percentage"] < 5 and item["signal_count"] < 3:
                ignore.append({
                    "domain": item["domain"],
                    "reason": f"Only {item['signal_count']} {'signal' if item['signal_count'] == 1 else 'signals'} from {item['domain']}. Too little to draw conclusions. Stop monitoring until it grows.",
                    "narrative": f"Deprioritize {item['domain']} — the signal volume is too low to justify attention.",
                    "signal_count": item["signal_count"],
                })
        return ignore

    def _recommend(self, current: list, thieves: list, ignore: list) -> list[dict[str, Any]]:
        """Recommend a reallocation.

        Caps any domain at 35%, redistributes the freed percentage
        proportionally to non-ignored domains below 20%.
        """
        if not current:
            return []

        # Filter out untracked and ignored domains from reallocation
        ignore_domains = {i["domain"] for i in ignore}
        active = [c for c in current if c["domain"] not in ignore_domains and c["domain"] != "untracked"]
        if not active:
            return current

        recommended = []
        excess = 0
        for item in active:
            if item["percentage"] > 35:
                excess += item["percentage"] - 35
                recommended.append({**item, "percentage": 35})
            else:
                recommended.append({**item})

        # Distribute excess to under-attended domains (proportionally)
        if excess > 0:
            under = [r for r in recommended if r["percentage"] < 20]
            if under:
                total_under = sum(r["percentage"] for r in under) or 1
                for r in under:
                    share = int(excess * (r["percentage"] / total_under))
                    r["percentage"] = min(35, r["percentage"] + share)

        # Re-normalize to 100%
        diff = 100 - sum(r["percentage"] for r in recommended)
        if diff != 0 and recommended:
            recommended[0]["percentage"] += diff

        return recommended

    def _narrative(self, current, thieves, ignore) -> str:
        """Generate a human-language narrative of the attention state."""
        if not thieves and not ignore:
            return "Your organization's attention is well-distributed. No reallocation needed."

        parts = []
        if thieves:
            for t in thieves:
                parts.append(f"{t['domain']} is taking {t['percentage']}% of attention — that's too much")
        if ignore:
            domains = ", ".join(i["domain"] for i in ignore)
            parts.append(f"deprioritize {domains} (too few signals to act on)")

        return ". ".join(parts) + "." if parts else "Attention is balanced."
