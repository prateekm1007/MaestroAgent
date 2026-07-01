"""
V8 Personal Mode — Phase 2-12: Self-Reflection Prompts.

Context-aware journaling prompts based only on the user's own signals.
Never uses sentiment analysis of a third party's messages.

WITHDRAWAL PATH (Guideline P9):
The user could journal without prompts. The tool adds structure;
without it, the user relies on their own initiative, which is harder
but fully functional.
"""

from __future__ import annotations

import logging
from typing import Any

from maestro_personal.knowledge_graph import PersonalKG
from maestro_personal.habits import HabitCoach
from maestro_personal.contradictions import PersonalContradictions

logger = logging.getLogger(__name__)


class ReflectionPrompts:
    """Generates journaling prompts from the user's own signals.

    Never analyzes a third party's messages. "Tough meeting" detection
    comes from the user's own self-report or journal entry, not from
    analyzing the boss's messages.
    """

    @staticmethod
    def generate(user_id: str = "") -> dict[str, Any]:
        """Generate reflection prompts based on the user's recent activity.

        Returns:
            {
                prompts: list[{prompt, context, type}],
                count: int,
                withdrawal_path: str,
            }
        """
        prompts: list[dict[str, Any]] = []

        # Check habits for reflection opportunities
        habits = HabitCoach.get_habits()
        for habit in habits:
            if habit.current_streak == 0:
                prompts.append({
                    "prompt": f"You haven't checked in for '{habit.name}' recently. What's getting in the way?",
                    "context": f"Habit '{habit.name}' has 0 current streak.",
                    "type": "habit_gap",
                })
            elif habit.current_streak >= 7:
                prompts.append({
                    "prompt": f"You're on a {habit.current_streak}-day streak for '{habit.name}'. What's working well?",
                    "context": f"Habit '{habit.name}' streak: {habit.current_streak}",
                    "type": "habit_success",
                })

        # Check contradictions for reflection
        contradictions = PersonalContradictions.detect()
        for c in contradictions.get("contradictions", [])[:2]:
            prompts.append({
                "prompt": f"I noticed: {c['description']} What's your perspective on this?",
                "context": c["evidence"],
                "type": "contradiction",
            })

        # Check KG goals for progress reflection
        goals = PersonalKG.get_entities(entity_type="goal")
        for goal in goals[:2]:
            prompts.append({
                "prompt": f"You set a goal: '{goal.name}'. How is it going? What progress have you made?",
                "context": f"Goal from your knowledge graph.",
                "type": "goal_progress",
            })

        # Check KG memories for reflection
        memories = PersonalKG.get_entities(entity_type="memory")
        if memories:
            recent = memories[-1]
            prompts.append({
                "prompt": f"You recently recorded: '{recent.name}'. Want to reflect on this?",
                "context": f"Memory from your knowledge graph.",
                "type": "memory_reflection",
            })

        # General prompt if no specific triggers
        if not prompts:
            prompts.append({
                "prompt": "What's on your mind today? Take a moment to write freely.",
                "context": "No specific triggers — general journaling prompt.",
                "type": "general",
            })

        # Limit to 5 prompts
        prompts = prompts[:5]

        return {
            "prompts": prompts,
            "count": len(prompts),
            "withdrawal_path": (
                "The user could journal without prompts. The tool adds structure; without it, "
                "the user relies on their own initiative, which is harder but fully functional."
            ),
        }
