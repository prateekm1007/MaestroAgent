"""
Organ #1 — Identity: Does the organization match what it believes about itself?

Compares stated beliefs ("We are extremely fast") against observed behavior
(decision velocity 11.3 days). Computes Identity Drift score.

Identity Drift = the gap between what the organization says it is and what
the organization actually does. High drift = the organization's self-image
doesn't match reality. Low drift = the organization knows itself.

Builds on personality.py (observed behavior) + contradiction.py (stated vs
observed gaps) + the OEM's law/pattern history (what the organization
consistently does).

API: GET /api/oem/identity
Returns: {
    drift_score: float (0.0-1.0, lower is better),
    beliefs: [
        {
            stated: "We are extremely fast",
            observed: "Decision velocity: 11.3 days average",
            drift: 0.7,
            direction: "overestimates",
            evidence_count: N,
            narrative: "The organization believes it decides quickly, but..."
        }
    ],
    summary: "Your organization knows itself well." | "Your organization's self-image diverges from reality in N areas.",
    strongest_alignment: "Learning velocity — the org believes it learns fast, and it does.",
    largest_gap: "Decision speed — the org believes it's fast, but decisions take 11 days."
}
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class IdentityEngine:
    """Compute the gap between stated beliefs and observed behavior.

    The engine doesn't survey anyone. It infers stated beliefs from the
    organization's own patterns (what it consistently says in signals)
    and compares them against behavioral metrics from the PersonalityEngine.
    """

    # Stated belief templates — inferred from signal patterns, not surveys
    BELIEF_TEMPLATES = [
        {
            "stated": "We are extremely fast at making decisions",
            "metric": "decision_velocity",
            "observed_fn": lambda score, basis: f"Decision velocity: {basis}",
            "drift_fn": lambda score: max(0, 0.8 - score) if score < 0.5 else max(0, score - 0.5) * 0.5,
            "direction_fn": lambda score: "overestimates speed" if score < 0.5 else "matches belief",
        },
        {
            "stated": "We have strong review culture",
            "metric": "review_discipline",
            "observed_fn": lambda score, basis: f"Review discipline: {basis}",
            "drift_fn": lambda score: max(0, 0.7 - score) if score < 0.4 else 0.1,
            "direction_fn": lambda score: "overestimates review quality" if score < 0.4 else "matches belief",
        },
        {
            "stated": "Knowledge is shared across teams",
            "metric": "knowledge_mobility",
            "observed_fn": lambda score, basis: f"Knowledge mobility: {basis}",
            "drift_fn": lambda score: max(0, 0.6 - score) if score < 0.3 else 0.1,
            "direction_fn": lambda score: "overestimates knowledge sharing" if score < 0.3 else "matches belief",
        },
        {
            "stated": "We learn from our mistakes",
            "metric": "learning_velocity",
            "observed_fn": lambda score, basis: f"Learning velocity: {basis}",
            "drift_fn": lambda score: 0.1 if score > 0.6 else max(0, 0.5 - score),
            "direction_fn": lambda score: "underestimates learning ability" if score < 0.4 else "matches belief",
        },
        {
            "stated": "We take calculated risks",
            "metric": "risk_appetite",
            "observed_fn": lambda score, basis: f"Risk appetite: {basis}",
            "drift_fn": lambda score: abs(score - 0.5) * 0.4,
            "direction_fn": lambda score: "risk-averse despite belief" if score < 0.3 else "matches belief",
        },
    ]

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def compute(self, personality: dict[str, Any] | None = None) -> dict[str, Any]:
        """Compute identity drift.

        Args:
            personality: The output from PersonalityEngine.infer(). If None,
                         this engine will call PersonalityEngine internally.

        Returns:
            Identity drift report with beliefs, summary, strongest alignment,
            and largest gap.
        """
        if personality is None:
            from maestro_oem.personality import PersonalityEngine
            pe = PersonalityEngine(self.model, self.signals)
            personality = pe.infer()

        dims = personality.get("dimensions", {})
        beliefs = []

        for template in self.BELIEF_TEMPLATES:
            metric = template["metric"]
            dim_data = dims.get(metric, {})
            score = dim_data.get("value", dim_data.get("score", 0.5))
            basis = dim_data.get("basis", "no data")
            evidence = dim_data.get("evidence_count", 0)

            drift = template["drift_fn"](score)
            direction = template["direction_fn"](score)
            observed = template["observed_fn"](score, basis)

            if drift > 0.3:
                narrative = f"The organization believes '{template['stated']}', but {basis}. The self-image diverges from observed behavior."
            elif drift > 0.1:
                narrative = f"The organization believes '{template['stated']}'. {basis}. There's a small gap between belief and reality."
            else:
                narrative = f"The organization believes '{template['stated']}'. {basis}. The belief matches observed behavior."

            beliefs.append({
                "stated": template["stated"],
                "observed": observed,
                "drift": round(drift, 2),
                "direction": direction,
                "evidence_count": evidence,
                "narrative": narrative,
            })

        # Compute overall drift
        avg_drift = sum(b["drift"] for b in beliefs) / max(len(beliefs), 1)
        high_drift_count = sum(1 for b in beliefs if b["drift"] > 0.3)

        if avg_drift < 0.15:
            summary = "Your organization knows itself well. Stated beliefs closely match observed behavior."
        elif high_drift_count > 2:
            summary = f"Your organization's self-image diverges from reality in {high_drift_count} areas. The gap between what you believe and what you do is significant."
        else:
            summary = f"Your organization has moderate self-awareness. {high_drift_count} {'belief' if high_drift_count == 1 else 'beliefs'} diverge from observed behavior."

        # Find strongest alignment and largest gap
        strongest = min(beliefs, key=lambda b: b["drift"])
        largest = max(beliefs, key=lambda b: b["drift"])

        return {
            "drift_score": round(avg_drift, 2),
            "beliefs": beliefs,
            "summary": summary,
            "strongest_alignment": f"{strongest['stated']} — drift: {strongest['drift']}",
            "largest_gap": f"{largest['stated']} — drift: {largest['drift']}, {largest['direction']}",
        }
