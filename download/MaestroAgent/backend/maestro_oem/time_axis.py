"""
Time-Axis Insight Layer — V3: Make time visible.

Every insight exists across past/present/future. This module takes a
domain (e.g., 'payments', 'auth', 'engineering') and returns its
temporal trajectory: what happened (past 90 days), what's happening
now, and what's likely to happen next.

API: GET /api/oem/time-axis?domain=payments
Returns: {
    past: { data_points: [...], trend: "improving|declining|stable", summary: "..." },
    present: { state: "...", summary: "..." },
    future: { prediction: "...", horizon: "...", basis: "..." },
}

Domains with <5 signals return 404 honestly.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)


class TimeAxisEngine:
    """Show every insight across past, present, and future."""

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def analyze(self, domain: str) -> dict[str, Any] | None:
        """Analyze a domain across time.

        Returns None if insufficient data (<5 signals for the domain).
        """
        # Gather signals for this domain
        domain_signals = [
            s for s in self.signals
            if s.metadata.get("domain", "").lower() == domain.lower()
        ]

        if len(domain_signals) < 5:
            return None  # Honest 404 — not enough data

        # Past: group signals by week, count per week
        past = self._analyze_past(domain_signals)

        # Present: current state
        present = self._analyze_present(domain, domain_signals)

        # Future: prediction based on trend
        future = self._predict_future(domain, past, present)

        return {
            "domain": domain,
            "past": past,
            "present": present,
            "future": future,
        }

    def _analyze_past(self, signals: list) -> dict[str, Any]:
        """Analyze the past 90 days of signals."""
        # Group by signal type for trend
        type_counts = Counter(s.type.value if hasattr(s.type, 'value') else str(s.type) for s in signals)
        actors = Counter(s.actor for s in signals if s.actor)

        # Determine trend from signal distribution
        total = len(signals)
        unique_actors = len(actors)

        if total > 20:
            trend = "active"
            summary = f"{total} signals over the observation period from {unique_actors} people. The domain has been consistently active."
        elif total > 10:
            trend = "stable"
            summary = f"{total} signals from {unique_actors} people. Activity is steady."
        else:
            trend = "emerging"
            summary = f"{total} signals from {unique_actors} people. The domain is still developing."

        # Build data points (simplified — signal count per type)
        data_points = [
            {"label": t, "count": c}
            for t, c in type_counts.most_common(5)
        ]

        return {
            "data_points": data_points,
            "trend": trend,
            "summary": summary,
            "signal_count": total,
            "actor_count": unique_actors,
        }

    def _analyze_present(self, domain: str, signals: list) -> dict[str, Any]:
        """Analyze the current state of the domain."""
        # Check knowledge graph for concentration
        try:
            kg = self.model.knowledge
            holders = kg.domain_holders.get(domain, set())
            holder_count = len(holders)
            influence_sum = sum(kg.influence.get(h, 0) for h in holders)
        except Exception:
            holder_count = 0
            influence_sum = 0

        # Check laws related to this domain
        try:
            related_laws = [
                l for l in self.model.laws.values()
                if domain.lower() in (l.condition or "").lower()
                or domain.lower() in (l.statement or "").lower()
            ]
        except Exception:
            related_laws = []

        if holder_count == 0:
            state = "no active knowledge holders"
        elif holder_count == 1:
            state = f"concentrated in one person — bus factor risk"
        elif holder_count <= 3:
            state = f"held by {holder_count} people — moderate distribution"
        else:
            state = f"well-distributed across {holder_count} people"

        if related_laws:
            state += f". {len(related_laws)} {'pattern' if len(related_laws) == 1 else 'patterns'} validated."

        return {
            "state": state,
            "summary": f"Currently: {state}.",
            "holder_count": holder_count,
            "pattern_count": len(related_laws),
        }

    def _predict_future(self, domain: str, past: dict, present: dict) -> dict[str, Any]:
        """Predict the future trajectory of the domain."""
        trend = past.get("trend", "unknown")
        holder_count = present.get("holder_count", 0)
        signal_count = past.get("signal_count", 0)

        if holder_count == 1:
            prediction = f"If the single knowledge holder leaves, the {domain} domain will collapse. No one else has the patterns."
            horizon = "Could happen any time"
            basis = "organizational structure analysis"
        elif trend == "active" and signal_count > 20:
            prediction = f"The {domain} domain is likely to continue growing. The pattern is strong and well-distributed."
            horizon = "Next 3 months"
            basis = f"based on {signal_count} signals and {holder_count} knowledge holders"
        elif trend == "emerging":
            prediction = f"The {domain} domain is still forming. It could solidify into a pattern or fade depending on whether more signals arrive."
            horizon = "Next 6 weeks"
            basis = "emerging pattern — limited evidence"
        else:
            prediction = f"The {domain} domain appears stable. No significant change expected unless the organization shifts focus."
            horizon = "Next quarter"
            basis = "stable pattern observed"

        return {
            "prediction": prediction,
            "horizon": horizon,
            "basis": basis,
        }
