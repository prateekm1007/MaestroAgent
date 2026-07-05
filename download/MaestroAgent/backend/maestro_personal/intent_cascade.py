"""
V8 Personal Mode — Phase 2-9: Intent Cascade for Personal Goals.

Breaks down big personal intents ("improve fitness," "write a book")
into assumptions, hypotheses, preparations, and evidence. All derived
from the user's own data (past habits, past outcomes, personal KG).

WITHDRAWAL PATH (Guideline P9):
The user could break down the goal manually in a journal. The tool
surfaces the user's own past patterns to inform the breakdown; without
it, the user relies on their own analysis, which is less data-informed
but fully functional.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from maestro_personal.knowledge_graph import PersonalKG
from maestro_personal.habits import HabitCoach

logger = logging.getLogger(__name__)


@dataclass
class CascadeItem:
    """A single item in the intent cascade (assumption, hypothesis, etc.)."""
    item_id: str = field(default_factory=lambda: str(uuid4()))
    item_type: str = ""  # "assumption", "hypothesis", "preparation", "evidence"
    text: str = ""
    status: str = "open"  # "open", "resolved", "invalidated"
    resolved_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "item_type": self.item_type,
            "text": self.text,
            "status": self.status,
            "resolved_at": self.resolved_at,
        }


class PersonalIntentCascade:
    """Breaks down big personal intents into testable components.

    The cascade is informational, not prescriptive. The user can resolve
    or invalidate each assumption/hypothesis. No auto-generation of tasks.
    """

    _cascades: dict[str, list[CascadeItem]] = {}  # intent → items

    @classmethod
    def cascade(cls, intent: str) -> dict[str, Any]:
        """Break down a personal intent into assumptions, hypotheses, etc.

        Args:
            intent: e.g. "improve fitness", "write a book", "strengthen friendships"

        Returns:
            {
                intent: str,
                assumptions: list[CascadeItem],
                hypotheses: list[CascadeItem],
                preparations: list[CascadeItem],
                evidence_plan: list[CascadeItem],
                based_on_user_data: bool,
                withdrawal_path: str,
            }
        """
        intent_lower = intent.lower()

        # Find relevant past patterns from the KG
        kg_entities = PersonalKG.get_entities()
        relevant_goals = [e for e in kg_entities if e.entity_type == "goal"
                         and any(w in e.name.lower() for w in intent_lower.split() if len(w) > 3)]
        relevant_habits = HabitCoach.get_habits()

        # Generate assumptions
        assumptions = [
            CascadeItem(item_type="assumption",
                       text=f"You have time in your schedule for '{intent}'."),
            CascadeItem(item_type="assumption",
                       text=f"You have the resources (money, equipment, support) needed for '{intent}'."),
        ]
        if relevant_goals:
            assumptions.append(CascadeItem(item_type="assumption",
                text=f"Your previous goal '{relevant_goals[0].name}' is not conflicting with this new intent."))

        # Generate hypotheses
        hypotheses = [
            CascadeItem(item_type="hypothesis",
                       text=f"If you commit 30 minutes daily to '{intent}', you will see progress in 30 days."),
            CascadeItem(item_type="hypothesis",
                       text=f"If you track your progress, you will be more consistent."),
        ]
        if relevant_habits:
            hypotheses.append(CascadeItem(item_type="hypothesis",
                text=f"Your existing habit '{relevant_habits[0].name}' can be extended to support this intent."))

        # Generate preparations
        preparations = [
            CascadeItem(item_type="preparation",
                       text=f"Set up a tracking system (habit check-in, journal, or calendar) for '{intent}'."),
            CascadeItem(item_type="preparation",
                       text=f"Identify one person who can support you in this goal."),
            CascadeItem(item_type="preparation",
                       text=f"Remove one obstacle that prevented progress on similar goals before."),
        ]

        # Generate evidence plan
        evidence_plan = [
            CascadeItem(item_type="evidence",
                       text=f"Track daily/weekly progress with a simple yes/no check-in."),
            CascadeItem(item_type="evidence",
                       text=f"Review progress every 2 weeks and adjust the approach."),
            CascadeItem(item_type="evidence",
                       text=f"After 30 days, assess: did the hypothesis hold? Was the assumption correct?"),
        ]

        # Store the cascade
        all_items = assumptions + hypotheses + preparations + evidence_plan
        cls._cascades[intent] = all_items

        return {
            "intent": intent,
            "assumptions": [a.to_dict() for a in assumptions],
            "hypotheses": [h.to_dict() for h in hypotheses],
            "preparations": [p.to_dict() for p in preparations],
            "evidence_plan": [e.to_dict() for e in evidence_plan],
            "based_on_user_data": len(relevant_goals) > 0 or len(relevant_habits) > 0,
            "withdrawal_path": (
                "The user could break down the goal manually in a journal. The tool surfaces "
                "the user's own past patterns to inform the breakdown; without it, the user "
                "relies on their own analysis, which is less data-informed but fully functional."
            ),
        }

    @classmethod
    def resolve_item(cls, intent: str, item_id: str, status: str) -> bool:
        """Resolve or invalidate a cascade item.

        Args:
            intent: The intent the item belongs to.
            item_id: The item to resolve.
            status: "resolved" or "invalidated".
        """
        items = cls._cascades.get(intent, [])
        for item in items:
            if item.item_id == item_id:
                item.status = status
                from datetime import datetime, timezone
                item.resolved_at = datetime.now(timezone.utc).isoformat()
                return True
        return False

    @classmethod
    def clear(cls) -> None:
        cls._cascades = {}
