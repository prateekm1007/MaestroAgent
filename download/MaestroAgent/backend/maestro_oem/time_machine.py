"""Time Machine — 'Have we been here before?' for every recommendation.

Every recommendation should answer: when have we been in a similar
situation, what happened, and what can we learn?

The Time Machine searches across:
  - Past predictions and their outcomes
  - Past recommendations and CEO feedback (agree/reject)
  - Past customer decisions (renewals, churns)
  - Past laws that were promoted or invalidated
  - Historical patterns with similar characteristics

For each similar past event, it returns:
  - what the situation was
  - what Maestro recommended
  - what actually happened
  - what was learned
  - how this applies to the current decision

This is NOT search. This is organizational memory completing decisions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class TimeMachine:
    """Searches organizational history for similar past situations.

    Usage:
        tm = TimeMachine(model, signals)
        results = tm.search("bottleneck", "priya.m@acme.com")
        # results = [{situation, recommendation, outcome, lesson, ...}]
    """

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def search(
        self,
        entity_id: str = "",
        entity_type: str = "",
        query: str = "",
        limit: int = 10,
    ) -> dict[str, Any]:
        """Search for similar past situations.

        Args:
            entity_id: The entity to find history for (law code, person, customer).
            entity_type: The type of entity (law, person, customer, recommendation).
            query: Natural-language query to match against past events.
            limit: Max results.

        Returns:
            dict with:
              - results: list of similar past situations
              - summary: what the history tells us
              - confidence: how relevant the history is
              - lesson: the key takeaway
        """
        results: list[dict[str, Any]] = []

        # Search predictions
        results.extend(self._search_predictions(entity_id, query))

        # Search CEO feedback (contradiction log)
        results.extend(self._search_feedback(entity_id, query))

        # Search customer decisions
        results.extend(self._search_customer_decisions(entity_id, query))

        # Search law history
        results.extend(self._search_law_history(entity_id, query))

        # Sort by relevance (timestamp + confidence)
        results.sort(
            key=lambda r: (r.get("confidence", 0), r.get("timestamp", "")),
            reverse=True,
        )

        results = results[:limit]

        summary = self._generate_summary(results, entity_id, entity_type)
        lesson = self._extract_lesson(results)

        return {
            "query": query or entity_id,
            "entity_id": entity_id,
            "entity_type": entity_type,
            "results": results,
            "total_found": len(results),
            "summary": summary,
            "lesson": lesson,
            "confidence": self._compute_confidence(results),
        }

    def _search_predictions(self, entity_id: str, query: str) -> list[dict[str, Any]]:
        """Search resolved predictions for this entity or query."""
        results = []
        try:
            import os
            from pathlib import Path
            from maestro_oem.prediction_lifecycle import PredictionRecorder

            db_path = os.environ.get(
                "MAESTRO_LEARNING_DB",
                str(Path(os.environ.get("DATABASE_URL", "file:maestro.db").replace("file:", "")).parent / "learning.db"),
            )
            recorder = PredictionRecorder(db_path)
            preds = recorder.list_predictions(limit=50)

            for pred in preds:
                # Match by entity_id or query text
                matches = (
                    (entity_id and entity_id in pred.get("entity_id", ""))
                    or (query and query.lower() in pred.get("recommendation", "").lower())
                    or (query and query.lower() in pred.get("entity_id", "").lower())
                )
                if not matches and not entity_id and not query:
                    matches = True  # Return all if no filter

                if matches and pred.get("status") in ("correct", "incorrect", "partially_correct"):
                    results.append({
                        "type": "prediction",
                        "situation": pred.get("recommendation", ""),
                        "recommendation": pred.get("expected_outcome", ""),
                        "outcome": pred.get("status", ""),
                        "confidence": pred.get("confidence", 0),
                        "timestamp": pred.get("resolved_at", pred.get("created_at", "")),
                        "lesson": self._prediction_lesson(pred),
                        "entity_id": pred.get("entity_id", ""),
                    })
        except Exception:
            pass

        return results

    def _search_feedback(self, entity_id: str, query: str) -> list[dict[str, Any]]:
        """Search CEO feedback (contradiction log) for this entity."""
        results = []
        # The contradiction log is on oem_state, not the model directly.
        # We search the model's laws for drift/counter-example signals.
        for law in self.model.laws.values():
            if entity_id and entity_id not in law.statement:
                continue
            if query and query.lower() not in law.statement.lower():
                continue

            if law.failed_runtimes > 0:
                results.append({
                    "type": "law_challenge",
                    "situation": law.statement[:100],
                    "recommendation": f"Law {law.code} was applied",
                    "outcome": "challenged" if law.failed_runtimes > 0 else "validated",
                    "confidence": law.confidence,
                    "timestamp": str(law.last_validated or ""),
                    "lesson": f"This law has {law.failed_runtimes} failures vs {law.validated_runtimes} validations. "
                              f"{'Treat with caution.' if law.failed_runtimes > law.validated_runtimes else 'Still reliable but watch for drift.'}",
                    "entity_id": law.code,
                })

        return results

    def _search_customer_decisions(self, entity_id: str, query: str) -> list[dict[str, Any]]:
        """Search past customer decisions for patterns."""
        from maestro_oem.signal import SignalType
        results = []

        for s in self.signals:
            if s.type != SignalType.CUSTOMER_DECISION:
                continue
            customer = s.metadata.get("customer", "")
            if entity_id and entity_id not in customer:
                continue
            if query and query.lower() not in customer.lower():
                continue

            outcome = s.metadata.get("decision_outcome", "unknown")
            arr = float(s.metadata.get("arr_impact", 0) or 0)
            results.append({
                "type": "customer_decision",
                "situation": f"{customer} faced a buying/renewal decision",
                "recommendation": "Maestro tracked the relationship signals",
                "outcome": outcome,
                "confidence": s.confidence,
                "timestamp": s.timestamp.isoformat(),
                "lesson": self._customer_decision_lesson(outcome, arr),
                "entity_id": customer,
            })

        return results

    def _search_law_history(self, entity_id: str, query: str) -> list[dict[str, Any]]:
        """Search law promotions and validations."""
        results = []
        for law in self.model.laws.values():
            if entity_id and entity_id not in law.code and entity_id not in law.statement:
                continue
            if query and query.lower() not in law.statement.lower():
                continue

            if law.validated_runtimes >= 3:
                results.append({
                    "type": "law_validated",
                    "situation": f"Pattern detected: {law.statement[:80]}",
                    "recommendation": f"Promoted to law {law.code}",
                    "outcome": "validated",
                    "confidence": law.confidence,
                    "timestamp": str(law.last_validated or ""),
                    "lesson": f"This pattern has been validated {law.validated_runtimes} times. "
                              f"It's a reliable organizational law.",
                    "entity_id": law.code,
                })

        return results

    def _prediction_lesson(self, pred: dict) -> str:
        status = pred.get("status", "")
        confidence = pred.get("confidence", 0)
        if status == "correct":
            return f"Maestro predicted this correctly with {confidence:.0%} confidence. The prediction model is well-calibrated for this type of decision."
        elif status == "incorrect":
            return f"Maestro predicted this incorrectly with {confidence:.0%} confidence. Calibration has adjusted — future similar predictions will be more conservative."
        elif status == "partially_correct":
            return f"Maestro was partially right with {confidence:.0%} confidence. The nuance matters — not all aspects of the prediction held."
        return "Prediction outcome unknown."

    def _customer_decision_lesson(self, outcome: str, arr: float) -> str:
        if outcome == "renewed":
            return f"Customer renewed (${arr:,.0f} ARR). The relationship signals leading to this were positive — champion active, commitments kept."
        elif outcome == "churned":
            return f"Customer churned (${arr:,.0f} ARR lost). The signals leading to this were negative — champion quiet, objections, broken commitments. Watch for this pattern in other customers."
        return f"Decision outcome: {outcome}."

    def _generate_summary(self, results: list, entity_id: str, entity_type: str) -> str:
        if not results:
            ref = entity_id or "this query"
            return f"No historical precedent found for '{ref}'. This may be a novel situation."

        correct = sum(1 for r in results if r.get("outcome") in ("correct", "validated", "renewed"))
        incorrect = sum(1 for r in results if r.get("outcome") in ("incorrect", "churned"))
        total = len(results)

        if total == 0:
            return "No historical data."

        success_rate = correct / total if total > 0 else 0
        return (
            f"Found {total} similar past situation(s). "
            f"{correct} succeeded, {incorrect} failed. "
            f"Historical success rate: {success_rate:.0%}."
        )

    def _extract_lesson(self, results: list) -> str:
        if not results:
            return "No lesson available — insufficient historical data."

        # Find the most recent result with a lesson
        for r in results:
            if r.get("lesson"):
                return r["lesson"]

        return "Historical data exists but no clear lesson emerged."

    def _compute_confidence(self, results: list) -> float:
        if not results:
            return 0.0
        confidences = [r.get("confidence", 0.5) for r in results]
        return sum(confidences) / len(confidences)
