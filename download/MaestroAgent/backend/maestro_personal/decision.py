"""
V8 Personal Mode — Phase 2-4: Decision Support for Life.

"Should I take this trip?" — surfaces pros, cons, past patterns from
the PersonalKG, and a confidence-scored recommendation. No emotional
modeling. Factual outcomes only. The recommendation is labeled
"informational, not prescriptive."

WITHDRAWAL PATH (Guideline P9):
The user could stop using decision support and make a pros/cons list
on paper. The tool surfaces past patterns the user might forget;
without it, the user relies on their own memory, which is less
complete but fully functional.
"""

from __future__ import annotations

import logging
from typing import Any

from maestro_personal.knowledge_graph import PersonalKG

logger = logging.getLogger(__name__)


class LifeDecisionEngine:
    """Decision support for personal life decisions.

    Takes a decision question and returns pros, cons, relevant past
    patterns, and a confidence-scored recommendation. The recommendation
    is explicitly labeled "informational, not prescriptive."
    """

    # Template pros/cons for common decision types
    _TEMPLATES = {
        "trip": {
            "pros": ["New experience", "Break from routine", "Memories with companions"],
            "cons": ["Cost", "Time away from responsibilities", "Planning overhead"],
        },
        "job": {
            "pros": ["Career growth", "New skills", "Compensation change"],
            "cons": ["Risk of unknown", "Disruption to routine", "Relationship changes"],
        },
        "purchase": {
            "pros": ["Utility", "Convenience", "Long-term value"],
            "cons": ["Cost", "Maintenance", "Depreciation"],
        },
    }

    @staticmethod
    def decide(question: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Analyze a personal decision.

        Returns:
            {
                question: str,
                pros: list[str],
                cons: list[str],
                past_patterns: list[dict],
                recommendation: str,
                confidence: float,
                label: str,  # "informational, not prescriptive"
            }
        """
        context = context or {}
        q_lower = question.lower()

        # Find matching template
        template = None
        for key, tmpl in LifeDecisionEngine._TEMPLATES.items():
            if key in q_lower:
                template = tmpl
                break

        if template:
            pros = list(template["pros"])
            cons = list(template["cons"])
        else:
            pros = context.get("pros", ["Potential benefit"])
            cons = context.get("cons", ["Potential cost"])

        # Find past patterns from the KG
        past_patterns: list[dict[str, Any]] = []
        for entity in PersonalKG.get_entities():
            if entity.entity_type == "goal" or entity.entity_type == "memory":
                # Check if this entity is related to the question
                if any(w in entity.name.lower() for w in q_lower.split() if len(w) > 3):
                    past_patterns.append({
                        "entity": entity.name,
                        "type": entity.entity_type,
                        "attributes": entity.attributes,
                    })

        # Build recommendation
        if pros and cons:
            recommendation = (
                f"Based on {len(pros)} pros and {len(cons)} cons"
                + (f", plus {len(past_patterns)} past pattern(s)" if past_patterns else "")
                + f", this decision has moderate complexity. Consider which factors matter most to you."
            )
        else:
            recommendation = "Not enough context to provide a specific recommendation. Consider listing your own pros and cons."

        confidence = 0.4 + (0.1 * len(past_patterns)) if past_patterns else 0.3
        confidence = min(confidence, 0.8)

        return {
            "question": question,
            "pros": pros,
            "cons": cons,
            "past_patterns": past_patterns[:5],
            "recommendation": recommendation,
            "confidence": round(confidence, 2),
            "label": "informational, not prescriptive",
        }
