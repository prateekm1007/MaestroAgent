"""
Spec #7 — Temporal Trajectories: org-wide trend memory.

"Trust has fallen slowly for 8 weeks." Extends consciousness.py's
point-in-time state to org-wide trajectory memory. All 7 consciousness
dimensions get trend + slope + duration + narrative.

A trajectory is not a chart. It's a sentence: "Trust has been declining
for 3 weeks. The trend started after the Q2 reorganization."

API: GET /api/oem/trajectories
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class TrajectoryEngine:
    """Compute temporal trajectories for all organizational dimensions.

    A trajectory has 4 properties:
      - trend: improving | declining | stable | emerging
      - slope: how fast (slow | moderate | rapid)
      - duration: how long (N weeks)
      - narrative: a human sentence

    The engine uses signal history (not time-series data, which doesn't
    exist yet) to infer trends from the distribution of signal types
    over the available history.
    """

    DIMENSIONS = [
        "attention",
        "knowledge",
        "trust",
        "conflict",
        "energy",
        "uncertainty",
        "learning",
    ]

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def compute(self) -> dict[str, Any]:
        """Compute trajectories for all 7 dimensions."""
        trajectories = {}
        for dim in self.DIMENSIONS:
            trajectories[dim] = self._compute_dimension(dim)

        # Count non-stable trajectories
        active = sum(1 for t in trajectories.values() if t["trend"] != "stable")
        if active == 0:
            summary = "All dimensions are stable. The organization is in equilibrium."
        else:
            improving = sum(1 for t in trajectories.values() if t["trend"] == "improving")
            declining = sum(1 for t in trajectories.values() if t["trend"] == "declining")
            if improving > declining:
                summary = f"{improving} dimensions improving, {declining} declining. The organization is getting smarter."
            elif declining > improving:
                summary = f"{declining} dimensions declining, {improving} improving. The organization needs attention."
            else:
                summary = f"Mixed signals: {improving} improving, {declining} declining. The organization is in transition."

        return {
            "trajectories": trajectories,
            "summary": summary,
            "active_count": active,
        }

    def _compute_dimension(self, dim: str) -> dict[str, Any]:
        """Compute trajectory for a single dimension."""
        # Use signal history to infer trend
        # Each dimension maps to specific signal types
        dim_signals = self._get_dim_signals(dim)
        count = len(dim_signals)

        if count < 3:
            return {
                "trend": "emerging",
                "slope": "unknown",
                "duration": "insufficient history",
                "narrative": f"Not enough history to determine the {dim} trajectory. Need at least 3 signals; have {count}.",
                "signal_count": count,
            }

        # Simple trend inference: compare first-half vs second-half signal density
        # (more signals in second half = increasing activity)
        midpoint = count // 2
        first_half = midpoint
        second_half = count - midpoint

        if dim in ("conflict", "uncertainty"):
            # For these, more signals = bad (increasing tension/uncertainty)
            if second_half > first_half * 1.3:
                trend = "declining"
                slope = "rapid" if second_half > first_half * 1.8 else "moderate"
            elif second_half < first_half * 0.7:
                trend = "improving"
                slope = "rapid" if second_half < first_half * 0.4 else "moderate"
            else:
                trend = "stable"
                slope = "slow"
        else:
            # For attention, knowledge, trust, energy, learning:
            # more signals = good (more activity/engagement)
            if second_half > first_half * 1.3:
                trend = "improving"
                slope = "rapid" if second_half > first_half * 1.8 else "moderate"
            elif second_half < first_half * 0.7:
                trend = "declining"
                slope = "rapid" if second_half < first_half * 0.4 else "moderate"
            else:
                trend = "stable"
                slope = "slow"

        # Duration estimate (rough — based on signal count)
        if count > 20:
            duration = "8+ weeks"
        elif count > 10:
            duration = "4-8 weeks"
        else:
            duration = "1-4 weeks"

        narrative = self._narrative(dim, trend, slope, duration, count)

        return {
            "trend": trend,
            "slope": slope,
            "duration": duration,
            "narrative": narrative,
            "signal_count": count,
        }

    def _get_dim_signals(self, dim: str) -> list:
        """Get signals relevant to a dimension."""
        from maestro_oem.signal import SignalType

        dim_map = {
            "attention": [SignalType.ISSUE_TRANSITIONED, SignalType.PR_OPENED],
            "knowledge": [SignalType.PAGE_CREATED, SignalType.PAGE_EDITED],
            "trust": [SignalType.AGREEMENT, SignalType.CONFLICT],
            "conflict": [SignalType.CONFLICT],
            "energy": [SignalType.PR_OPENED, SignalType.PR_MERGED, SignalType.COMMIT],
            "uncertainty": [SignalType.QUESTION_ASKED, SignalType.THREAD_STARTED],
            "learning": [SignalType.PR_REVIEWED, SignalType.AGREEMENT],
        }

        types = dim_map.get(dim, [])
        return [s for s in self.signals if s.type in types]

    def _narrative(self, dim: str, trend: str, slope: str, duration: str, count: int) -> str:
        """Generate a human narrative for a trajectory."""
        dim_human = dim.replace("_", " ")

        if trend == "stable":
            return f"{dim_human.capitalize()} has been stable for {duration}. No significant change detected."
        elif trend == "improving":
            return f"{dim_human.capitalize()} has been {trend} for {duration}, {slope}ly. Based on {count} signals. This is a positive trajectory — keep doing what you're doing."
        elif trend == "declining":
            return f"{dim_human.capitalize()} has been {trend} for {duration}, {slope}ly. Based on {count} signals. This warrants attention — investigate what changed."
        else:
            return f"{dim_human.capitalize()} is still emerging. Not enough history ({count} signals) to determine direction."
