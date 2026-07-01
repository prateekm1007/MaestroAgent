"""
V8 Personal Mode — Phase 2-7: Contradictions in Personal Life.

Scans the PersonalKG for stated values vs. recorded behavior.
"You say you want to exercise but haven't checked in to the gym habit
in 3 weeks." Surfaces contradictions gently. The user can dismiss a
contradiction for 30 days.

WITHDRAWAL PATH (Guideline P9):
The user could stop using contradictions and simply reflect on their
own behavior. The engine surfaces gaps the user might not notice;
without it, the user is less self-aware but fully functional.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from maestro_personal.knowledge_graph import PersonalKG
from maestro_personal.habits import HabitCoach

logger = logging.getLogger(__name__)


class PersonalContradictions:
    """Surfaces contradictions between stated values and recorded behavior.

    Contradictions are surfaced, not punished. The tone is "noticed this
    pattern," not "you failed." The user can dismiss a contradiction for
    30 days.
    """

    _dismissed: dict[str, str] = {}  # contradiction_key → dismissed_until (ISO date)

    @classmethod
    def detect(cls) -> dict[str, Any]:
        """Detect contradictions between values and behavior.

        Returns:
            {
                contradictions: list[{type, description, evidence, severity}],
                count: int,
                summary: str,
            }
        """
        contradictions: list[dict[str, Any]] = []

        # Check for stated goals vs. habit behavior
        goals = PersonalKG.get_entities(entity_type="goal")
        habits = HabitCoach.get_habits()

        for goal in goals:
            goal_name_lower = goal.name.lower()
            # Check if any habit matches this goal
            for habit in habits:
                habit_name_lower = habit.name.lower()
                # If the goal mentions exercise/fitness and the habit hasn't been checked in recently
                if any(w in habit_name_lower for w in goal_name_lower.split()):
                    if habit.current_streak == 0:
                        key = f"goal:{goal.entity_id}:habit:{habit.habit_id}"
                        if cls._is_dismissed(key):
                            continue
                        contradictions.append({
                            "type": "value_vs_behavior",
                            "description": f"You set a goal '{goal.name}' but haven't checked in for '{habit.name}' recently.",
                            "evidence": f"Goal: {goal.name}. Habit '{habit.name}' has 0 current streak.",
                            "severity": "gentle",
                            "dismiss_key": key,
                        })

        # Check for stated values with no matching behavior
        for goal in goals:
            if "exercise" in goal.name.lower() or "fitness" in goal.name.lower():
                matching_habits = [h for h in habits if any(w in h.name.lower() for w in ["exercise", "gym", "fitness", "run", "workout"])]
                if not matching_habits:
                    key = f"goal:{goal.entity_id}:no_habit"
                    if cls._is_dismissed(key):
                        continue
                    contradictions.append({
                        "type": "value_vs_no_behavior",
                        "description": f"You set a goal '{goal.name}' but have no habit tracking for it.",
                        "evidence": f"Goal: {goal.name}. No matching habit found.",
                        "severity": "gentle",
                        "dismiss_key": key,
                    })

        # Build summary
        if contradictions:
            summary = f"Found {len(contradictions)} contradiction{'s' if len(contradictions) != 1 else ''}. These are patterns, not failures."
        else:
            summary = "No contradictions detected. Your values and behavior are aligned."

        return {
            "contradictions": contradictions,
            "count": len(contradictions),
            "summary": summary,
        }

    @classmethod
    def dismiss(cls, dismiss_key: str) -> dict[str, Any]:
        """Dismiss a contradiction for 30 days."""
        dismissed_until = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        cls._dismissed[dismiss_key] = dismissed_until
        return {
            "dismissed": True,
            "key": dismiss_key,
            "until": dismissed_until,
            "message": "Contradiction dismissed for 30 days. It won't resurface until then.",
        }

    @classmethod
    def _is_dismissed(cls, key: str) -> bool:
        """Check if a contradiction is currently dismissed."""
        until = cls._dismissed.get(key)
        if not until:
            return False
        try:
            until_dt = datetime.fromisoformat(until)
            if until_dt.tzinfo is None:
                until_dt = until_dt.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) < until_dt
        except Exception:
            return False

    @classmethod
    def clear(cls) -> None:
        cls._dismissed = {}
