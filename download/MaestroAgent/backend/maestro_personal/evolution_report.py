"""
V8 Personal Mode — Phase 2-11: Memory Evolution Report.

Quarterly summary of how the user's interests, goals, and patterns
evolved — based on their own data. A narrative, not a dashboard.

WITHDRAWAL PATH (Guideline P9):
The user could review their own journal and calendar manually. The
report synthesizes patterns the user might not notice; without it,
the user is less aware of their own evolution but fully functional.
"""

from __future__ import annotations

import logging
from typing import Any

from maestro_personal.knowledge_graph import PersonalKG
from maestro_personal.habits import HabitCoach
from maestro_personal.prediction_market import PersonalPredictionMarket
from maestro_personal.contradictions import PersonalContradictions

logger = logging.getLogger(__name__)


class EvolutionReport:
    """Generates a quarterly narrative of the user's own evolution.

    Uses only the user's own data. No third-party analysis. The tone
    is observational, not judgmental.
    """

    @staticmethod
    def generate(quarter: str = "") -> dict[str, Any]:
        """Generate a quarterly evolution report.

        Args:
            quarter: e.g. "Q2-2026". If empty, uses current quarter.

        Returns:
            {
                narrative: str,
                interests_changed: list[str],
                goals_progress: list[dict],
                habit_trajectories: list[dict],
                prediction_calibration: dict | None,
                contradictions_addressed: int,
                withdrawal_path: str,
            }
        """
        # Gather data
        kg_entities = PersonalKG.get_entities()
        habits = HabitCoach.get_habits()
        predictions = PersonalPredictionMarket.get_predictions()
        calibration = PersonalPredictionMarket.get_calibration()
        contradictions = PersonalContradictions.detect()

        # Interests
        interests = [e for e in kg_entities if e.entity_type == "interest"]
        interests_changed = [e.name for e in interests]

        # Goals
        goals = [e for e in kg_entities if e.entity_type == "goal"]
        goals_progress = [{
            "goal": g.name,
            "status": "active" if g.attributes.get("status", "active") == "active" else "completed",
            "source": g.source,
        } for g in goals]

        # Habit trajectories
        habit_trajectories = [{
            "habit": h.name,
            "check_ins": len(h.check_ins),
            "current_streak": h.current_streak,
        } for h in habits]

        # Build narrative
        narrative_parts: list[str] = []

        if quarter:
            narrative_parts.append(f"## Your Evolution — {quarter}\n")
        else:
            narrative_parts.append("## Your Evolution — Recent Quarter\n")

        if goals:
            narrative_parts.append(f"You set {len(goals)} goal(s) this period: {', '.join(g.name for g in goals[:5])}.")
        else:
            narrative_parts.append("You haven't set any goals in your knowledge graph yet.")

        if habits:
            narrative_parts.append(f"\nYou're tracking {len(habits)} habit(s). "
                                   f"Your longest current streak is {max(h.current_streak for h in habits)} check-in(s).")
        else:
            narrative_parts.append("\nYou're not tracking any habits yet.")

        if calibration.get("total", 0) > 0:
            narrative_parts.append(f"\nYou made {calibration['total']} prediction(s) and your average Brier score is "
                                   f"{calibration.get('average_brier', 'N/A')}. "
                                   f"{'You are well-calibrated.' if calibration.get('average_brier', 1) < 0.25 else 'You tend to be overconfident — your predictions were more optimistic than outcomes.'}")
        else:
            narrative_parts.append("\nYou haven't made any predictions yet.")

        if contradictions["count"] > 0:
            narrative_parts.append(f"\nI noticed {contradictions['count']} contradiction(s) between your stated values and behavior. "
                                   "These are patterns, not failures — worth reflecting on.")
        else:
            narrative_parts.append("\nYour values and behavior are aligned — no contradictions detected.")

        narrative_parts.append(f"\nYou have {len(interests)} interest(s) recorded and {len(kg_entities)} total entities in your knowledge graph.")

        return {
            "narrative": "\n".join(narrative_parts),
            "interests_changed": interests_changed,
            "goals_progress": goals_progress,
            "habit_trajectories": habit_trajectories,
            "prediction_calibration": calibration if calibration.get("total", 0) > 0 else None,
            "contradictions_addressed": contradictions["count"],
            "withdrawal_path": (
                "The user could review their own journal and calendar manually. The report synthesizes "
                "patterns the user might not notice; without it, the user is less aware of their own "
                "evolution but fully functional."
            ),
        }
