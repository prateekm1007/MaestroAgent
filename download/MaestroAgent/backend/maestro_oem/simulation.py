"""SimulationEngine — the single source of truth for what-if simulations.

Consolidates the previously duplicated simulator logic that lived inline in
three different route handlers (/simulator POST, /simulate POST, and the
drilldown "simulation" tab). All three now delegate here.

There is exactly one confidence calculation, one input-adjustment model,
and one response shape. The /twin/simulate endpoint is intentionally
separate because it runs organizational what-if scenarios (person leaves,
team merges) via the DigitalTwin — a fundamentally different operation
than the metric-level what-if this engine performs.

The response shape includes BOTH `inputs` (the user's submitted payload)
and `inputs_applied` (the same, post-validation) for backward
compatibility with existing UIs and tests.

HONESTY NOTE: The current model is intentionally simple — it adjusts
two metrics (P1 cluster risk, decision velocity) based on a single
input (hire_count) via two linear formulas. The UI implies multiple
adjustable levers (team moves, meeting cadence, org mergers), but only
hire_count is actually modeled. This is documented honestly because
the product's pitch mentions "Decision Simulator" as a feature. The
pilot will determine whether more inputs and non-linear models are
needed. Until then, the simulator's predictions are bounded by the
linear hire_count adjustment.
"""

from __future__ import annotations

from typing import Any


class SimulationEngine:
    """Run metric-level what-if simulations against the OEM.

    Usage:
        engine = SimulationEngine(model, decisions)
        result = engine.simulate(inputs={"hire_count": 3}, law_code="L-0001")
        # result["predicted"]["p1_cluster_risk"], result["confidence"], ...
    """

    def __init__(self, model: Any, decisions: Any) -> None:
        self.model = model
        self.decisions = decisions

    def simulate(
        self,
        inputs: dict[str, Any] | None = None,
        law_code: str | None = None,
        recommendation_id: str | None = None,
    ) -> dict[str, Any]:
        """Run a what-if simulation.

        Args:
            inputs: User-adjustable inputs (e.g. {"hire_count": 3}).
            law_code: Optional law to scope the simulation to.
            recommendation_id: Optional recommendation to scope to.

        Returns a dict with:
            base_health, predicted, confidence, linked_laws, inputs, inputs_applied
        """
        inputs = inputs or {}
        model = self.model

        # Base health from the model
        base_p1 = model.health.p1_cluster_risk
        base_incident = model.health.incident_rate
        base_velocity = model.health.decision_velocity_days
        base_release = model.health.release_frequency

        # Apply input adjustments. Currently only hire_count is modeled;
        # other inputs are accepted but do not change the prediction yet.
        hire_count = inputs.get("hire_count", 0)
        try:
            hire_count = int(hire_count)
        except (TypeError, ValueError):
            hire_count = 0
        adjusted_p1 = max(0.0, base_p1 - (hire_count * 0.02))
        adjusted_velocity = max(0.5, base_velocity - (hire_count * 0.1))

        # Find linked laws
        linked_laws: list[str] = []
        if law_code and law_code in model.laws:
            linked_laws.append(law_code)
        elif recommendation_id:
            rec = next(
                (r for r in self.decisions.get_recommendations()
                 if r.rec_id == recommendation_id),
                None,
            )
            if rec:
                linked_laws = rec.linked_laws or []

        # Compute confidence from linked laws. If no specific law/rec was
        # given, use ALL laws (the org-wide average confidence).
        if linked_laws:
            law_objs = [model.laws[lc] for lc in linked_laws if lc in model.laws]
        else:
            law_objs = list(model.laws.values())
        confidence = (
            sum(l.confidence for l in law_objs) / max(len(law_objs), 1)
            if law_objs else 0.0
        )
        all_linked = [l.code for l in law_objs]

        return {
            "base_health": {
                "p1_cluster_risk": round(base_p1, 4),
                "incident_rate": base_incident,
                "decision_velocity_days": round(base_velocity, 2),
                "release_frequency": round(base_release, 2),
            },
            "predicted": {
                "p1_cluster_risk": round(adjusted_p1, 4),
                "incident_rate": base_incident,
                "decision_velocity_days": round(adjusted_velocity, 2),
                "release_frequency": round(base_release, 2),
            },
            "confidence": round(confidence, 4),
            "linked_laws": all_linked,
            # Both keys present for backward compatibility:
            #   - `inputs` is what the UI/test submits and expects back.
            #   - `inputs_applied` is the validated version (ints coerced, etc.).
            "inputs": inputs,
            "inputs_applied": {**inputs, "hire_count": hire_count},
        }
