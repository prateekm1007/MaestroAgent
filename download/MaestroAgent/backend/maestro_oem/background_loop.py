"""
V6 Spec #3 — Background Adaptation Loop.

V6 Law 2 made real: "The organization improves even when nobody opens Maestro."

Runs on every signal ingest (hooked into oem_state.py live_ingest()),
checks for improvement opportunities, queues nudges, detects regressions.

TODAY shows "Maestro noticed this while you were away."

API: GET /api/oem/background-loop
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class BackgroundAdaptationLoop:
    """Continuously monitors for improvement opportunities and regressions.

    The loop runs after every signal ingest and produces:
      - new_nudges: restructuring suggestions that became available since last check
      - regressions: patterns that were improving but started declining
      - improvements: patterns that were declining but started improving
      - overnight_notices: things Maestro noticed while nobody was watching

    The output is what TODAY displays as "Maestro noticed this while you were away."
    """

    _last_check: datetime | None = None
    _last_nudge_count: int = 0
    _last_trajectory_trends: dict[str, str] = {}

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def run(self) -> dict[str, Any]:
        """Run the background adaptation loop.

        This is called after every signal ingest. It compares the current
        state to the last check and surfaces what changed.
        """
        notices = []
        regressions = []
        improvements = []

        # 1. Check for new nudges
        new_nudges = self._check_new_nudges()
        if new_nudges:
            notices.append({
                "type": "new_suggestion",
                "message": f"Maestro found {len(new_nudges)} new {'restructuring suggestion' if len(new_nudges) == 1 else 'restructuring suggestions'} based on recent signals.",
                "detail": new_nudges[0].get("intervention", "")[:80] if new_nudges else "",
                "urgency": "normal",
            })

        # 2. Check for trajectory regressions (was improving, now declining)
        traj_changes = self._check_trajectory_changes()
        regressions.extend(traj_changes.get("regressions", []))
        improvements.extend(traj_changes.get("improvements", []))

        for reg in regressions:
            notices.append({
                "type": "regression",
                "message": f"{reg['dimension']} was improving but has started declining. This is a regression — investigate what changed.",
                "detail": reg.get("narrative", ""),
                "urgency": "high",
            })

        for imp in improvements:
            notices.append({
                "type": "improvement",
                "message": f"{imp['dimension']} was declining but has started improving. The organization is recovering.",
                "detail": imp.get("narrative", ""),
                "urgency": "normal",
            })

        # 3. Check for new contradictions
        new_contradictions = self._check_new_contradictions()
        if new_contradictions:
            notices.append({
                "type": "new_tension",
                "message": f"Maestro detected {len(new_contradictions)} new {'tension' if len(new_contradictions) == 1 else 'tensions'} while you were away.",
                "detail": new_contradictions[0].get("title", "")[:80] if new_contradictions else "",
                "urgency": "medium",
            })

        # Update last check time
        BackgroundAdaptationLoop._last_check = datetime.now(timezone.utc)

        if not notices:
            summary = "Everything is stable. Maestro is watching."
        else:
            high = sum(1 for n in notices if n.get("urgency") == "high")
            summary = f"Maestro noticed {len(notices)} {'thing' if len(notices) == 1 else 'things'} while you were away. {high} {'needs' if high == 1 else 'need'} immediate attention."

        return {
            "notices": notices[:5],
            "new_nudges": new_nudges[:2],
            "regressions": regressions,
            "improvements": improvements,
            "summary": summary,
            "last_check": BackgroundAdaptationLoop._last_check.isoformat() if BackgroundAdaptationLoop._last_check else None,
            "notice_count": len(notices),
        }

    def _check_new_nudges(self) -> list[dict[str, Any]]:
        """Check if new nudges are available since last check."""
        try:
            from maestro_oem.adaptive_nudge import AdaptiveNudgeEngine
            engine = AdaptiveNudgeEngine(self.model, self.signals)
            result = engine.generate()
            current_count = result.get("nudge_count", 0)
            nudges = result.get("nudges", [])

            # If nudge count increased, return the new ones
            if current_count > BackgroundAdaptationLoop._last_nudge_count:
                BackgroundAdaptationLoop._last_nudge_count = current_count
                return nudges
            return []
        except Exception as e:
            logger.debug("Nudge check failed: %s", e)
            return []

    def _check_trajectory_changes(self) -> dict[str, list[dict[str, Any]]]:
        """Check for trajectory changes (regressions and improvements)."""
        regressions = []
        improvements = []

        try:
            from maestro_oem.trajectories import TrajectoryEngine
            engine = TrajectoryEngine(self.model, self.signals)
            result = engine.compute()
            trajectories = result.get("trajectories", {})

            for dim, traj in trajectories.items():
                current_trend = traj.get("trend", "stable")
                previous_trend = BackgroundAdaptationLoop._last_trajectory_trends.get(dim, "stable")

                if previous_trend == "improving" and current_trend == "declining":
                    regressions.append({
                        "dimension": dim,
                        "previous_trend": previous_trend,
                        "current_trend": current_trend,
                        "narrative": traj.get("narrative", ""),
                    })
                elif previous_trend == "declining" and current_trend == "improving":
                    improvements.append({
                        "dimension": dim,
                        "previous_trend": previous_trend,
                        "current_trend": current_trend,
                        "narrative": traj.get("narrative", ""),
                    })

                BackgroundAdaptationLoop._last_trajectory_trends[dim] = current_trend
        except Exception as e:
            logger.debug("Trajectory change check failed: %s", e)

        return {"regressions": regressions, "improvements": improvements}

    def _check_new_contradictions(self) -> list[dict[str, Any]]:
        """Check for new contradictions since last check."""
        try:
            from maestro_oem.contradictions import ContradictionDetector
            from maestro_api.routes.oem import _get_assumption_graph
            graph = _get_assumption_graph()
            detector = ContradictionDetector(self.model, self.signals, graph)
            contradictions = detector.detect_all()
            # Return only unacknowledged ones
            return [c for c in contradictions if c.get("status") == "open"][:2]
        except Exception as e:
            logger.debug("Contradiction check failed: %s", e)
            return []
