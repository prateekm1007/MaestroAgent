"""
V8 Personal Mode — Phase 2-5: Habit & Self-Improvement Coach.

Tracks habits from user-entered check-ins. Suggests micro-improvements,
celebrates wins, provides gentle accountability. No social accountability
circles. One reminder per missed habit per day, maximum. No nagging.

WITHDRAWAL PATH (Guideline P9):
The user could stop using the habit coach and track habits with a paper
tracker or a simple app. The coach adds structure; without it, the user
relies on self-discipline, which is harder but fully functional.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class Habit:
    """A habit the user is tracking."""
    habit_id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    frequency: str = "daily"  # "daily", "weekly"
    check_ins: list[str] = field(default_factory=list)  # ISO timestamps
    reminders_enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def current_streak(self) -> int:
        """Current consecutive check-in streak."""
        if not self.check_ins:
            return 0
        # Simple streak: count consecutive days (simplified for pilot)
        return len(self.check_ins)

    def to_dict(self) -> dict[str, Any]:
        return {
            "habit_id": self.habit_id,
            "name": self.name,
            "frequency": self.frequency,
            "check_in_count": len(self.check_ins),
            "current_streak": self.current_streak,
            "reminders_enabled": self.reminders_enabled,
            "created_at": self.created_at,
        }


class HabitCoach:
    """Gentle habit accountability. One reminder per missed habit per day."""

    _habits: dict[str, Habit] = {}
    _reminders_sent: dict[str, str] = {}  # habit_id → date of last reminder (YYYY-MM-DD)

    @classmethod
    def create_habit(cls, name: str, frequency: str = "daily") -> Habit:
        habit = Habit(name=name, frequency=frequency)
        cls._habits[habit.habit_id] = habit
        return habit

    @classmethod
    def check_in(cls, habit_id: str) -> Habit | None:
        habit = cls._habits.get(habit_id)
        if not habit:
            return None
        habit.check_ins.append(datetime.now(timezone.utc).isoformat())
        return habit

    @classmethod
    def get_habits(cls) -> list[Habit]:
        return list(cls._habits.values())

    @classmethod
    def get_streaks(cls) -> list[dict[str, Any]]:
        return [h.to_dict() for h in cls._habits.values()]

    @classmethod
    def get_suggestions(cls) -> list[str]:
        """Gentle micro-improvement suggestions. No nagging."""
        suggestions: list[str] = []
        for habit in cls._habits.values():
            if habit.current_streak == 0:
                suggestions.append(f"You haven't checked in for '{habit.name}' yet today. A small step counts.")
            elif habit.current_streak >= 7:
                suggestions.append(f"Great streak on '{habit.name}' — {habit.current_streak} days! Keep going.")
        return suggestions[:3]  # max 3 suggestions

    @classmethod
    def get_reminder(cls, habit_id: str) -> str | None:
        """Get a reminder for a missed habit. One per day maximum.

        Returns the reminder text, or None if already reminded today or
        reminders are disabled.
        """
        habit = cls._habits.get(habit_id)
        if not habit or not habit.reminders_enabled:
            return None

        today = datetime.now(timezone.utc).date().isoformat()
        if cls._reminders_sent.get(habit_id) == today:
            return None  # already reminded today

        # Check if the habit was checked in today
        today_check_ins = [ts for ts in habit.check_ins if ts.startswith(today)]
        if today_check_ins:
            return None  # already checked in today

        cls._reminders_sent[habit_id] = today
        return f"Gentle reminder: you haven't checked in for '{habit.name}' today."

    @classmethod
    def silence_reminders(cls, habit_id: str) -> bool:
        habit = cls._habits.get(habit_id)
        if not habit:
            return False
        habit.reminders_enabled = False
        return True

    @classmethod
    def clear(cls) -> None:
        cls._habits = {}
        cls._reminders_sent = {}
