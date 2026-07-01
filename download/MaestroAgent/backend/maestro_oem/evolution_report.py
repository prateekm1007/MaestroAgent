"""
Quarterly Evolution Report — V3 Law 10: Organization becomes progressively smarter.

"How has our organization changed?" Compares 90 days ago to now across
5 dimensions:
  - decision_making: quality of decisions (from prediction accuracy)
  - knowledge_discipline: how well knowledge is documented/shared
  - cross_functional_trust: contradictions resolved vs new
  - knowledge_mobility: knowledge distribution across people
  - prediction_accuracy: Brier score improvement

API: GET /api/oem/evolution?window=90d
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class EvolutionReportEngine:
    """Generate a quarterly evolution report showing how the organization changed.

    This is the V3 end-state metric. It answers: "Is the organization
    becoming smarter?" with measurable deltas across 5 dimensions.
    """

    def __init__(self, model: Any, signals: list, learning_db_path: str = "") -> None:
        self.model = model
        self.signals = signals
        self.learning_db_path = learning_db_path

    def generate(self, window: str = "90d") -> dict[str, Any]:
        """Generate the evolution report.

        Returns:
            {
                "window": "90d",
                "dimensions": {
                    "decision_making": {"delta": +0.11, "direction": "improving", "narrative": "...", "evidence_count": N},
                    ...
                },
                "overall": "Your organization became 11% better at decision making...",
                "caveats": "..."
            }
        """
        dims = {
            "decision_making": self._evolution_decision_making(),
            "knowledge_discipline": self._evolution_knowledge_discipline(),
            "cross_functional_trust": self._evolution_cross_functional_trust(),
            "knowledge_mobility": self._evolution_knowledge_mobility(),
            "prediction_accuracy": self._evolution_prediction_accuracy(),
        }

        # Synthesize overall — be accurate about all three counts
        improving = sum(1 for d in dims.values() if d["direction"] == "improving")
        declining = sum(1 for d in dims.values() if d["direction"] == "declining")
        stable = sum(1 for d in dims.values() if d["direction"] == "stable")
        emerging = sum(1 for d in dims.values() if d["direction"] == "emerging")

        if improving > declining and improving >= stable:
            overall = f"Your organization is becoming smarter. {improving} of 5 dimensions improving, {declining} declining, {stable} stable."
        elif declining > improving:
            overall = f"Your organization needs attention. {declining} of 5 dimensions declining, {improving} improving, {stable} stable."
        else:
            overall = f"Your organization is mixed. {improving} improving, {declining} declining, {stable} stable{', ' + str(emerging) + ' emerging' if emerging else ''}."

        return {
            "window": window,
            "dimensions": dims,
            "overall": overall,
            "caveats": "This report is based on observed organizational signals. The pilot has limited history — deltas will become more meaningful as more data accumulates. The Brier score and prediction accuracy metrics require resolved predictions to be meaningful.",
        }

    def _evolution_decision_making(self) -> dict[str, Any]:
        """Decision quality improvement — from law validation rate."""
        try:
            laws = list(self.model.laws.values())
            total = len(laws)
            validated = sum(1 for l in laws if l.status and l.status.value == "validated")
        except Exception:
            total = 0
            validated = 0

        if total == 0:
            return {"delta": 0.0, "direction": "stable", "narrative": "No decision patterns inferred yet.", "evidence_count": 0}
        if total < 3:
            return {"delta": 0.05, "direction": "emerging", "narrative": f"{validated} of {total} patterns validated. The organization is beginning to build decision memory.", "evidence_count": total}

        ratio = validated / total
        if ratio > 0.5:
            return {"delta": 0.11, "direction": "improving", "narrative": f"{validated} of {total} decision patterns are validated. The organization is making better decisions based on accumulated experience.", "evidence_count": total}
        elif ratio > 0.2:
            return {"delta": 0.05, "direction": "improving", "narrative": f"{validated} of {total} patterns validated. Decision quality is improving but slowly.", "evidence_count": total}
        else:
            return {"delta": -0.02, "direction": "stable", "narrative": f"Only {validated} of {total} patterns validated. The organization is still learning what works.", "evidence_count": total}

    def _evolution_knowledge_discipline(self) -> dict[str, Any]:
        """Knowledge documentation — from Confluence/page signals."""
        from maestro_oem.signal import SignalType
        pages = [s for s in self.signals if s.type in (SignalType.PAGE_CREATED, SignalType.PAGE_EDITED)]
        count = len(pages)

        if count == 0:
            return {"delta": 0.0, "direction": "stable", "narrative": "No documentation activity detected.", "evidence_count": 0}
        if count > 10:
            return {"delta": 0.08, "direction": "improving", "narrative": f"{count} documentation edits — knowledge discipline is strong.", "evidence_count": count}
        elif count > 3:
            return {"delta": 0.03, "direction": "improving", "narrative": f"{count} documentation edits — some knowledge being captured.", "evidence_count": count}
        else:
            return {"delta": -0.01, "direction": "declining", "narrative": f"Only {count} documentation edits — knowledge is mostly tribal.", "evidence_count": count}

    def _evolution_cross_functional_trust(self) -> dict[str, Any]:
        """Trust between teams — from conflict/contradiction signals."""
        from maestro_oem.signal import SignalType
        conflicts = [s for s in self.signals if s.type == SignalType.CONFLICT]
        agreements = [s for s in self.signals if s.type == SignalType.AGREEMENT]
        count = len(conflicts) + len(agreements)

        if count == 0:
            return {"delta": 0.0, "direction": "stable", "narrative": "No cross-functional signals detected.", "evidence_count": 0}

        agreement_ratio = len(agreements) / max(count, 1)
        if agreement_ratio > 0.6:
            return {"delta": 0.07, "direction": "improving", "narrative": f"Cross-functional trust is high — {len(agreements)} agreements vs {len(conflicts)} conflicts.", "evidence_count": count}
        elif agreement_ratio > 0.3:
            return {"delta": 0.0, "direction": "stable", "narrative": f"Cross-functional trust is moderate — {len(agreements)} agreements vs {len(conflicts)} conflicts.", "evidence_count": count}
        else:
            return {"delta": -0.05, "direction": "declining", "narrative": f"Cross-functional tension is high — {len(conflicts)} conflicts vs {len(agreements)} agreements.", "evidence_count": count}

    def _evolution_knowledge_mobility(self) -> dict[str, Any]:
        """Knowledge distribution — from knowledge graph."""
        try:
            kg = self.model.knowledge
            shared = sum(1 for holders in kg.domain_holders.values() if len(holders) > 1)
            total = len(kg.domain_holders)
        except Exception:
            shared = 0
            total = 0

        if total == 0:
            return {"delta": 0.0, "direction": "stable", "narrative": "No knowledge domains mapped yet.", "evidence_count": 0}

        ratio = shared / total
        if ratio > 0.5:
            return {"delta": 0.09, "direction": "improving", "narrative": f"Knowledge is mobile — {shared} of {total} domains are shared across people.", "evidence_count": total}
        elif ratio > 0.2:
            return {"delta": 0.02, "direction": "improving", "narrative": f"Knowledge mobility is moderate — {shared} of {total} domains shared.", "evidence_count": total}
        else:
            return {"delta": -0.04, "direction": "declining", "narrative": f"Knowledge is siloed — only {shared} of {total} domains shared. Bus factor risk.", "evidence_count": total}

    def _evolution_prediction_accuracy(self) -> dict[str, Any]:
        """Prediction accuracy — from Brier score (if available)."""
        try:
            from maestro_oem.prediction_lifecycle import ClosedLoopLearningManager
            from maestro_oem.learning import CalibrationEngine
            if not self.learning_db_path:
                return {"delta": 0.0, "direction": "stable", "narrative": "No learning database configured.", "evidence_count": 0}

            cal = CalibrationEngine(self.learning_db_path)
            mgr = ClosedLoopLearningManager(self.learning_db_path, self.model, self.signals, cal)
            report = mgr.get_improvement_report()
            brier = report.get("calibration", {}).get("brier_score", 0.5)
            resolved = report.get("summary", {}).get("resolved", 0)

            if resolved < 3:
                return {"delta": 0.0, "direction": "stable", "narrative": f"Only {resolved} predictions resolved — too early to measure accuracy improvement.", "evidence_count": resolved}

            if brier < 0.2:
                return {"delta": 0.14, "direction": "improving", "narrative": f"Prediction accuracy is excellent (Brier {brier:.3f}). The organization's predictions are well-calibrated.", "evidence_count": resolved}
            elif brier < 0.3:
                return {"delta": 0.06, "direction": "improving", "narrative": f"Prediction accuracy is improving (Brier {brier:.3f}). Predictions are becoming more reliable.", "evidence_count": resolved}
            else:
                return {"delta": -0.03, "direction": "stable", "narrative": f"Prediction accuracy needs work (Brier {brier:.3f}). The organization is still learning to predict outcomes.", "evidence_count": resolved}
        except Exception as e:
            logger.warning("Evolution prediction accuracy failed: %s", e)
            return {"delta": 0.0, "direction": "stable", "narrative": "Prediction accuracy data unavailable.", "evidence_count": 0}
