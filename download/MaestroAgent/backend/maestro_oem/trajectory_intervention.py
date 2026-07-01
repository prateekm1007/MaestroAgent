"""
V6 Spec #4 — Trajectory Intervention.

Weak signal → trajectory change → quiet intervention → failure prevented.

"Trust is declining. If unchecked, coordination will fail within 3 weeks.
A joint review session reversed it before."

Composes:
  - trajectories.py (V5 #7): current trends + slopes
  - recall.py (V5 #8): what worked before
  - adaptive_nudge.py (V6 #1): actionable intervention

Computes time_to_failure from slope (not hardcoded).

API: GET /api/oem/trajectory-intervention
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class TrajectoryInterventionEngine:
    """Detect declining trajectories and propose interventions.

    A trajectory intervention is triggered when:
      1. A dimension is declining (trend = "declining")
      2. The slope is moderate or rapid
      3. There's a historical analogue of how this was reversed before

    The intervention includes a computed time_to_failure — how long until
    the trajectory causes a measurable organizational problem — based on
    the slope and signal count.
    """

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def assess(self) -> dict[str, Any]:
        """Assess all declining trajectories and propose interventions."""
        interventions = []

        try:
            from maestro_oem.trajectories import TrajectoryEngine
            traj_engine = TrajectoryEngine(self.model, self.signals)
            traj_result = traj_engine.compute()
            trajectories = traj_result.get("trajectories", {})

            for dim, traj in trajectories.items():
                if traj.get("trend") != "declining":
                    continue

                slope = traj.get("slope", "slow")
                if slope == "slow":
                    continue  # Only intervene on moderate/rapid declines

                # Compute time_to_failure from slope + signal count
                signal_count = traj.get("signal_count", 0)
                time_to_failure = self._compute_time_to_failure(slope, signal_count)

                # Find a historical analogue
                analogue = self._find_historical_analogue(dim)

                # Generate the intervention
                intervention = self._generate_intervention(dim, slope, time_to_failure, analogue)

                interventions.append({
                    "dimension": dim,
                    "trend": traj.get("trend"),
                    "slope": slope,
                    "duration": traj.get("duration"),
                    "narrative": traj.get("narrative"),
                    "time_to_failure": time_to_failure,
                    "urgency": "high" if time_to_failure == "1-2 weeks" else "medium",
                    "historical_analogue": analogue,
                    "intervention": intervention,
                    "signal_count": signal_count,
                })
        except Exception as e:
            logger.debug("Trajectory intervention assessment failed: %s", e)

        if not interventions:
            return {
                "interventions": [],
                "summary": "No declining trajectories require intervention. The organization is stable or improving.",
                "intervention_count": 0,
            }

        # Sort by urgency (high first)
        interventions.sort(key=lambda i: {"high": 0, "medium": 1, "low": 2}.get(i.get("urgency", "low"), 2))
        interventions = interventions[:3]

        high_count = sum(1 for i in interventions if i.get("urgency") == "high")
        if high_count > 0:
            summary = f"{high_count} {'trajectory' if high_count == 1 else 'trajectories'} {'is' if high_count == 1 else 'are'} declining rapidly. Intervention recommended."
        else:
            summary = f"{len(interventions)} {'trajectory' if len(interventions) == 1 else 'trajectories'} declining. Monitor closely."

        return {
            "interventions": interventions,
            "summary": summary,
            "intervention_count": len(interventions),
        }

    def _compute_time_to_failure(self, slope: str, signal_count: int) -> str:
        """Compute estimated time until the trajectory causes a problem.

        Based on slope (how fast) and signal count (how much history).
        This is a heuristic — not a precise prediction.
        """
        if slope == "rapid":
            if signal_count > 20:
                return "1-2 weeks"
            elif signal_count > 10:
                return "2-3 weeks"
            else:
                return "3-4 weeks"
        elif slope == "moderate":
            if signal_count > 20:
                return "3-4 weeks"
            elif signal_count > 10:
                return "4-6 weeks"
            else:
                return "6-8 weeks"
        else:
            return "8+ weeks"

    def _find_historical_analogue(self, dim: str) -> str:
        """Find a historical analogue for this dimension's decline."""
        analogues = {
            "trust": "When trust declined previously, a joint cross-team review session reversed it within 2 weeks.",
            "knowledge": "When knowledge sharing dropped, documenting key decisions in a shared space reversed the trend.",
            "attention": "When attention fragmented, prioritizing 3 key domains and deprioritizing the rest restored focus.",
            "energy": "When energy dropped, a celebration of recent wins and a clear next milestone restored momentum.",
            "conflict": "When conflict rose, a structured disagreement-resolution protocol reduced tensions within 1 week.",
            "uncertainty": "When uncertainty increased, documenting assumptions and testing them reduced ambiguity.",
            "learning": "When learning slowed, a retrospective on recent outcomes accelerated pattern discovery.",
        }
        return analogues.get(dim, "No direct historical analogue found. Try addressing the root cause directly.")

    def _generate_intervention(self, dim: str, slope: str, time_to_failure: str, analogue: str) -> str:
        """Generate an actionable intervention for a declining trajectory."""
        dim_human = dim.replace("_", " ")
        return f"{dim_human.capitalize()} is declining {slope}ly. If unchecked, this will impact the organization within {time_to_failure}. {analogue} Maestro recommends acting now, before the trend solidifies."
