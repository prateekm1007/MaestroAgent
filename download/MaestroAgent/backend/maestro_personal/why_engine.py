"""
V8 Personal Mode — Phase 2-10: Personal Why? Engine.

Takes a question about the user's own behavior ("Why did I skip the
gym 3 times this month?") and produces a multi-step causal chain
from the user's own data. Never analyzes a third party.

WITHDRAWAL PATH (Guideline P9):
The user could reflect on their own behavior in a journal. The tool
surfaces patterns the user might not notice; without it, the user is
less self-aware but fully functional.
"""

from __future__ import annotations

import logging
from typing import Any

from maestro_personal.knowledge_graph import PersonalKG
from maestro_personal.store import PersonalDataStore
from maestro_personal.habits import HabitCoach
from maestro_personal.contradictions import PersonalContradictions

logger = logging.getLogger(__name__)


class PersonalWhyEngine:
    """Explains the user's own behavior from their own data.

    If the user asks about a third party ("Why is Sarah mad at me?"),
    the response is: "I can only explain your own patterns. Here's what
    I see in your data about your recent interactions with Sarah."
    """

    # Third-party question indicators
    _THIRD_PARTY_INDICATORS = ["why is ", "why does ", "why did ", "why would ", "why won't ", "why hasn't "]

    @staticmethod
    def explain(user_id: str, question: str) -> dict[str, Any]:
        """Explain the user's own behavior from their own data.

        Args:
            user_id: The user asking.
            question: e.g. "Why did I skip the gym 3 times this month?"

        Returns:
            {
                question: str,
                explanation_chain: list[{step, label, narrative, evidence}],
                third_party_redirected: bool,
                confidence: float,
                withdrawal_path: str,
            }
        """
        question_lower = question.lower()

        # Check if the question is about a third party
        is_third_party = any(question_lower.startswith(ind) for ind in PersonalWhyEngine._THIRD_PARTY_INDICATORS)
        # Also check if it's NOT about the user ("I" or "my")
        mentions_self = any(w in question_lower for w in [" i ", " i'", " my", " me ", " myself"])
        third_party_redirected = is_third_party and not mentions_self

        if third_party_redirected:
            # Extract the name (heuristic: word after "is/does/did/would")
            import re
            name_match = re.search(r'(?:is|does|did|would|won\'?t|hasn\'?t)\s+(\w+)', question_lower)
            name = name_match.group(1).capitalize() if name_match else "that person"

            return {
                "question": question,
                "explanation_chain": [{
                    "step": 1,
                    "label": "Redirect",
                    "narrative": f"I can only explain your own patterns. I don't analyze {name} or anyone else. Here's what I can tell you about your own data related to {name}:",
                    "evidence": "Constitutional guardrail: self-facing only.",
                }],
                "third_party_redirected": True,
                "confidence": 1.0,
                "withdrawal_path": (
                    "The user could reflect on their own behavior in a journal. The tool surfaces "
                    "patterns the user might not notice; without it, the user is less self-aware "
                    "but fully functional."
                ),
            }

        # Build explanation from the user's own data
        chain: list[dict[str, Any]] = []
        step = 1

        # Check habits
        habits = HabitCoach.get_habits()
        for habit in habits:
            if any(w in habit.name.lower() for w in question_lower.split() if len(w) > 3):
                chain.append({
                    "step": step,
                    "label": f"Habit: {habit.name}",
                    "narrative": f"Your habit '{habit.name}' has a current streak of {habit.current_streak} check-in(s). "
                               + ("You've been consistent recently." if habit.current_streak > 0
                                  else "You haven't checked in recently."),
                    "evidence": f"Habit check-in count: {len(habit.check_ins)}",
                })
                step += 1

        # Check KG for relevant goals/memories
        for entity in PersonalKG.get_entities():
            if any(w in entity.name.lower() for w in question_lower.split() if len(w) > 3):
                chain.append({
                    "step": step,
                    "label": f"{entity.entity_type.title()}: {entity.name}",
                    "narrative": f"You have a {entity.entity_type} '{entity.name}' in your knowledge graph. "
                               + (f"Attributes: {entity.attributes}" if entity.attributes else ""),
                    "evidence": f"Source: {entity.source}",
                })
                step += 1

        # Check contradictions
        contradictions = PersonalContradictions.detect()
        if contradictions["count"] > 0:
            for c in contradictions["contradictions"][:2]:
                if any(w in c["description"].lower() for w in question_lower.split() if len(w) > 3):
                    chain.append({
                        "step": step,
                        "label": "Contradiction detected",
                        "narrative": c["description"],
                        "evidence": c["evidence"],
                    })
                    step += 1

        # Check personal data store
        try:
            items = PersonalDataStore.get_all(user_id)
            relevant = [i for i in items if any(w in i.content.lower() for w in question_lower.split() if len(w) > 3)]
            if relevant:
                chain.append({
                    "step": step,
                    "label": "Your notes/memories",
                    "narrative": f"You have {len(relevant)} note(s) related to this topic. "
                               + f"Most recent: '{relevant[-1].content[:80]}...'",
                    "evidence": f"Note source: {relevant[-1].source}",
                })
                step += 1
        except Exception:
            pass

        # If no evidence found
        if not chain:
            chain.append({
                "step": 1,
                "label": "No data found",
                "narrative": "I don't have enough data in your personal knowledge graph, habits, or notes to explain this. Try connecting more data sources or journaling about this topic.",
                "evidence": "No matching items found.",
            })

        confidence = min(0.3 + 0.15 * len(chain), 0.85)

        return {
            "question": question,
            "explanation_chain": chain[:5],
            "third_party_redirected": False,
            "confidence": round(confidence, 2),
            "withdrawal_path": (
                "The user could reflect on their own behavior in a journal. The tool surfaces "
                "patterns the user might not notice; without it, the user is less self-aware "
                "but fully functional."
            ),
        }
