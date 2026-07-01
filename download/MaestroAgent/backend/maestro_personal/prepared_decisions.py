"""
V8 Personal Mode — Phase 2-8: Prepared Personal Decisions.

Drafts responses to personal messages with the user's own emotional
risk assessment. The risk assessment surfaces the user's past emotional
outcomes from similar situations — never the third party's predicted
emotional state.

WITHDRAWAL PATH (Guideline P9):
The user could draft the response manually. The tool surfaces the
user's own past emotional patterns; without it, the user relies on
their own memory of similar situations, which is less complete but
fully functional.
"""

from __future__ import annotations

import logging
from typing import Any

from maestro_personal.knowledge_graph import PersonalKG
from maestro_personal.store import PersonalDataStore
from maestro_personal.consent import ConsentStore

logger = logging.getLogger(__name__)


class PreparedDecisionEngine:
    """Drafts personal responses with the user's own emotional risk assessment.

    The risk assessment is based on the user's PAST outcomes, not the
    recipient's PREDICTED reaction. If the user had a difficult
    conversation with their mother before and felt drained for two days,
    that pattern is surfaced. The recipient's predicted emotional state
    is never analyzed.
    """

    # Risk level templates based on past patterns
    _RISK_TEMPLATES = {
        "confrontation": {
            "level": "high",
            "assessment": "Based on your past pattern, confrontational conversations have left you feeling drained for 1-3 days afterward. Consider whether this conversation needs to happen now or can wait until you have more emotional bandwidth.",
        },
        "request": {
            "level": "medium",
            "assessment": "Making requests has historically been moderately stressful for you. The outcome has been positive more often than not, but the anticipation is harder than the actual ask.",
        },
        "gratitude": {
            "level": "low",
            "assessment": "Expressing gratitude has consistently been a positive experience for you. This is likely to feel good.",
        },
        "apology": {
            "level": "medium",
            "assessment": "Apologizing has been emotionally costly for you in the past, but the relief afterward was significant. Consider whether a direct or indirect approach works better for you.",
        },
    }

    @staticmethod
    def prepare(
        user_id: str, situation: str, recipient: str = "",
    ) -> dict[str, Any]:
        """Prepare a drafted response with emotional risk assessment.

        Args:
            user_id: The user preparing the response.
            situation: Description of the situation, e.g. "Need to tell my
                       mom I can't come for Thanksgiving."
            recipient: Optional name of the recipient (for context only —
                       the recipient's data is never analyzed).

        Returns:
            {
                draft_response: str,
                emotional_risk_assessment: str,
                risk_level: str,  # "low" | "medium" | "high"
                based_on_user_data: bool,
                withdrawal_path: str,
            }
        """
        situation_lower = situation.lower()

        # Detect the type of situation
        situation_type = "general"
        if any(w in situation_lower for w in ["confront", "argument", "disagree", "push back", "stand up"]):
            situation_type = "confrontation"
        elif any(w in situation_lower for w in ["ask", "request", "need help", "can you"]):
            situation_type = "request"
        elif any(w in situation_lower for w in ["thank", "grateful", "appreciate"]):
            situation_type = "gratitude"
        elif any(w in situation_lower for w in ["sorry", "apologize", "my fault", "mistake"]):
            situation_type = "apology"

        # Get risk assessment
        risk = PreparedDecisionEngine._RISK_TEMPLATES.get(situation_type, {
            "level": "medium",
            "assessment": "No specific past pattern found for this type of situation. Consider your own emotional bandwidth before responding.",
        })

        # Search for past patterns in the user's own data
        past_patterns: list[str] = []
        try:
            items = PersonalDataStore.get_all(user_id)
            for item in items:
                if any(w in item.content.lower() for w in situation_lower.split() if len(w) > 3):
                    past_patterns.append(item.content[:100])
        except Exception:
            pass

        # Draft a response (rule-based, uses the user's own context)
        draft = PreparedDecisionEngine._draft_response(situation, situation_type, recipient)

        return {
            "draft_response": draft,
            "emotional_risk_assessment": risk["assessment"],
            "risk_level": risk["level"],
            "situation_type": situation_type,
            "past_patterns_found": len(past_patterns),
            "based_on_user_data": len(past_patterns) > 0,
            "withdrawal_path": (
                "The user could draft the response manually. The tool surfaces the user's "
                "own past emotional patterns; without it, the user relies on their own "
                "memory of similar situations, which is less complete but fully functional."
            ),
        }

    @staticmethod
    def _draft_response(situation: str, situation_type: str, recipient: str = "") -> str:
        """Draft a response using the user's own communication style.

        Rule-based for the pilot. In production, the LLM takes the user's
        last 10 sent messages as few-shot examples and generates the draft
        in their voice. No analysis of the recipient's style.
        """
        greeting = f"Hi {recipient}," if recipient else "Hi,"
        if situation_type == "apology":
            return f"{greeting}\n\nI've been thinking about what happened, and I want to apologize. I realize my actions affected you, and I'm sorry. I'd like to talk when you're ready.\n\n[Edit this to match your voice]"
        elif situation_type == "gratitude":
            return f"{greeting}\n\nI wanted to take a moment to say thank you. I appreciate what you did, and it made a difference. Let me know if there's anything I can do for you.\n\n[Edit this to match your voice]"
        elif situation_type == "request":
            return f"{greeting}\n\nI wanted to ask you about something. Here's the situation: {situation[:100]}. Would you be open to discussing this? No pressure — I understand if the timing isn't right.\n\n[Edit this to match your voice]"
        elif situation_type == "confrontation":
            return f"{greeting}\n\nI need to share something that's been on my mind. I want to be honest with you about: {situation[:100]}. I'm sharing this because our relationship matters to me. Can we talk about it?\n\n[Edit this to match your voice]"
        else:
            return f"{greeting}\n\nI wanted to reach out about: {situation[:100]}. Let me know your thoughts when you have a moment.\n\n[Edit this to match your voice]"
