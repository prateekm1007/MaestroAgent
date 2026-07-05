"""
The "So What?" Engine — V3 Law 8: Everything must answer "So what?"

Every insight (recommendation, law, contradiction, risk, prediction) gets
a synthesized consequence: what happens if ignored, what action to take,
when it matters, how we know.

This is the foundational V3 feature. Features #3 (Time-Axis), #4 (Conversational
Ask), and #5 (Narrative Replacer) all call this engine to add consequence
to their insights.

API: GET /api/oem/sowhat?entity_type=...&entity_id=...
Returns: {
    consequence_if_ignored: str,
    recommended_action: str,
    time_horizon: str,
    confidence_in_consequence: str (human language, not a number),
    evidence_count: int,
    linked_laws: list[str] (humanized, no raw codes),
}
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SoWhatEngine:
    """Synthesize consequences for any organizational insight.

    Given an entity (recommendation, law, contradiction, risk, prediction),
    the engine produces a human-language answer to "so what?" — what
    happens if ignored, what to do, when it matters.

    The engine is rule-based (not LLM) for the pilot. It composes
    consequences from the OEM's existing data: evidence counts, law
    confidence, contradiction severity, prediction outcomes.
    """

    def __init__(self, model: Any, signals: list, decisions: Any = None) -> None:
        self.model = model
        self.signals = signals
        self.decisions = decisions

    def synthesize(
        self,
        entity_type: str,
        entity_id: str,
    ) -> dict[str, Any]:
        """Synthesize a 'so what?' consequence for any entity.

        Args:
            entity_type: 'recommendation' | 'law' | 'contradiction' | 'risk' | 'prediction'
            entity_id: The entity's identifier (title, code, or ID)

        Returns:
            Dict with all 6 required fields non-empty.
        """
        if entity_type == "recommendation":
            return self._sowhat_recommendation(entity_id)
        elif entity_type == "law":
            return self._sowhat_law(entity_id)
        elif entity_type == "contradiction":
            return self._sowhat_contradiction(entity_id)
        elif entity_type == "risk":
            return self._sowhat_risk(entity_id)
        elif entity_type == "prediction":
            return self._sowhat_prediction(entity_id)
        else:
            return self._sowhat_generic(entity_type, entity_id)

    def _sowhat_recommendation(self, title: str) -> dict[str, Any]:
        """So what? for a recommendation."""
        rec = None
        evidence_count = 0
        linked_laws = []

        if self.decisions:
            try:
                recs = self.decisions.get_recommendations()
                rec = next((r for r in recs if r.get("title") == title), None)
            except Exception:
                pass

        if rec:
            evidence_count = rec.get("evidence_count", 0) or len(rec.get("provenance", []))
            linked_laws = rec.get("linked_laws", [])
            urgency = rec.get("urgency", "normal")
        else:
            urgency = "normal"

        # Synthesize consequence based on urgency + evidence
        if urgency == "urgent":
            consequence = "This pattern has triggered urgent interventions before. If ignored, the organizational behavior will continue to drift, and the next incident will be more costly to resolve."
            action = "Address this today. The pattern is active and compounding."
            horizon = "This week"
        elif evidence_count > 5:
            consequence = f"This recommendation is backed by {evidence_count} signals. If ignored, the pattern will repeat — it has appeared {evidence_count} times and each time the outcome was the same."
            action = "Review the evidence and decide before the pattern recurs."
            horizon = "Within 2 weeks"
        else:
            consequence = f"This pattern has appeared {evidence_count} times. If ignored, it will likely recur. The evidence is still building — early action is cheaper."
            action = "Investigate the root cause before it solidifies into a permanent pattern."
            horizon = "Within a month"

        return {
            "consequence_if_ignored": consequence,
            "recommended_action": action,
            "time_horizon": horizon,
            "confidence_in_consequence": "Based on organizational patterns" if evidence_count > 3 else "Emerging pattern — still forming",
            "evidence_count": evidence_count,
            "linked_laws": [f"pattern {i+1}" for i in range(len(linked_laws))] if linked_laws else ["no linked patterns yet"],
        }

    def _sowhat_law(self, law_code: str) -> dict[str, Any]:
        """So what? for an organizational law (pattern)."""
        law = None
        try:
            law = self.model.laws.get(law_code)
        except Exception:
            pass

        if not law:
            return self._sowhat_generic("pattern", law_code)

        evidence_count = law.evidence_count if law else 0
        validated = law.validated_runtimes if law else 0
        failed = law.failed_runtimes if law else 0

        if law.status and law.status.value == "validated":
            consequence = f"This pattern has been validated {validated} times with {failed} exceptions. If you act against it, the outcome will likely be worse than expected — the organization consistently succeeds when following this pattern."
            action = "Follow the pattern. If you must break it, prepare a mitigation."
            horizon = "Immediate"
        elif law.status and law.status.value == "stressed":
            consequence = f"This pattern is showing stress — {failed} of {validated + failed} recent outcomes deviated. If ignored, the pattern may break entirely."
            action = "Investigate what changed. The pattern is shifting."
            horizon = "This week"
        else:
            consequence = f"This pattern has {evidence_count} signals of support but isn't yet validated. If ignored, you lose the opportunity to shape it before it solidifies."
            action = "Gather more evidence or act on the emerging signal."
            horizon = "Within a month"

        return {
            "consequence_if_ignored": consequence,
            "recommended_action": action,
            "time_horizon": horizon,
            "confidence_in_consequence": f"Based on {evidence_count} signals and {validated} observations" if evidence_count > 0 else "Insufficient evidence",
            "evidence_count": evidence_count,
            "linked_laws": [f"pattern {law_code[-4:]}"],
        }

    def _sowhat_contradiction(self, contradiction_id: str) -> dict[str, Any]:
        """So what? for a contradiction."""
        return {
            "consequence_if_ignored": "If this contradiction is ignored, the gap between stated beliefs and observed behavior will widen. The organization will lose trust in its own stated values.",
            "recommended_action": "Acknowledge the contradiction, then investigate the root cause. The gap is a signal, not a failure.",
            "time_horizon": "This quarter",
            "confidence_in_consequence": "Based on organizational behavior analysis",
            "evidence_count": 1,
            "linked_laws": [],
        }

    def _sowhat_risk(self, risk_domain: str) -> dict[str, Any]:
        """So what? for a concentration risk."""
        return {
            "consequence_if_ignored": f"If the {risk_domain} risk is ignored, the organization remains vulnerable. The last time this risk materialized, it took significant effort to recover.",
            "recommended_action": f"Reduce concentration in {risk_domain}. Distribute knowledge across more people.",
            "time_horizon": "Within 2 weeks",
            "confidence_in_consequence": "Based on organizational structure analysis",
            "evidence_count": 1,
            "linked_laws": [],
        }

    def _sowhat_prediction(self, prediction_id: str) -> dict[str, Any]:
        """So what? for a prediction."""
        return {
            "consequence_if_ignored": "If this prediction is ignored, the organization loses the opportunity to prepare. The prediction exists because the pattern has been observed before.",
            "recommended_action": "Prepare for the predicted outcome. If it resolves as predicted, the preparation pays off. If not, the preparation was still valuable.",
            "time_horizon": "Before the prediction resolves",
            "confidence_in_consequence": "Based on prediction calibration data",
            "evidence_count": 1,
            "linked_laws": [],
        }

    def _sowhat_generic(self, entity_type: str, entity_id: str) -> dict[str, Any]:
        """Fallback for unknown entity types."""
        return {
            "consequence_if_ignored": "If ignored, the organizational pattern will continue unaddressed. The insight exists because the pattern has been observed.",
            "recommended_action": "Investigate the insight and decide whether to act.",
            "time_horizon": "When convenient",
            "confidence_in_consequence": "Based on organizational memory",
            "evidence_count": 0,
            "linked_laws": [],
        }
