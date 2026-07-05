"""
Spec #8 — Institutional Memory Recall: "When have we been here before?"

Retrieves the top 3 most similar past moments from learning history +
resolved predictions + signal history. Each moment has:
  - when: timestamp
  - situation: what was happening
  - what_we_did: the action taken
  - what_we_learned: the lesson
  - outcome: what happened as a result

Not documents. Not search results. Organizational memories.

API: GET /api/oem/recall?situation=...
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class RecallEngine:
    """Retrieve organizational memories similar to a current situation.

    The engine doesn't search documents. It searches the organization's
    lived experience — decisions made, outcomes observed, lessons learned.
    Each memory is a moment, not a file.
    """

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def recall(self, situation: str = "") -> dict[str, Any]:
        """Retrieve similar past moments.

        Args:
            situation: The current situation to find analogues for.
        """
        moments = []

        # 1. Recall from resolved predictions (decisions that were made + outcomes)
        moments.extend(self._recall_from_predictions(situation))

        # 2. Recall from learning objects (patterns discovered)
        moments.extend(self._recall_from_learning_objects(situation))

        # 3. Recall from contradictions (past tensions and their resolution)
        moments.extend(self._recall_from_contradictions(situation))

        # 4. Recall from signal history (similar events)
        moments.extend(self._recall_from_signals(situation))

        if not moments:
            return {
                "moments": [],
                "summary": "No similar past moments found. This may be a novel situation for the organization.",
                "moment_count": 0,
                "novel": True,
            }

        # Sort by relevance (simple keyword overlap for now)
        sit_lower = situation.lower()
        sit_words = set(w for w in sit_lower.split() if len(w) > 3)
        for m in moments:
            m_text = f"{m.get('situation','')} {m.get('what_we_learned','')}".lower()
            m["relevance"] = sum(1 for w in sit_words if w in m_text) / max(len(sit_words), 1)

        moments.sort(key=lambda m: m.get("relevance", 0), reverse=True)
        moments = moments[:3]

        summary = f"Found {len(moments)} similar {'moment' if len(moments) == 1 else 'moments'} from organizational history."

        return {
            "moments": moments,
            "summary": summary,
            "moment_count": len(moments),
            "novel": False,
        }

    def _recall_from_predictions(self, situation: str) -> list[dict[str, Any]]:
        """Recall from resolved predictions (decisions + outcomes)."""
        moments = []
        try:
            # Use the learning DB to find resolved predictions
            import os
            from maestro_db.db_helper import get_db_url_for_learning
            from maestro_oem.prediction_lifecycle import PredictionRecorder

            db_path = os.environ.get("MAESTRO_LEARNING_DB", get_db_url_for_learning())
            recorder = PredictionRecorder(db_path)
            predictions = recorder.list_predictions(status="resolved", limit=20)

            for pred in predictions[:5]:
                recommendation = pred.get("recommendation", "")
                expected = pred.get("expected_outcome", "")
                resolution = pred.get("resolution_evidence", "")

                moments.append({
                    "when": pred.get("created_at", ""),
                    "situation": f"Prediction: {recommendation[:80]}" if recommendation else "Organizational prediction",
                    "what_we_did": f"Predicted: {expected[:60]}" if expected else "Made a prediction",
                    "what_we_learned": f"Outcome: {resolution[:80]}" if resolution else "Prediction was resolved",
                    "outcome": "resolved" if pred.get("status") == "resolved" else "unknown",
                    "source": "prediction_history",
                })
        except Exception as e:
            logger.debug("Prediction recall failed: %s", e)
        return moments[:3]

    def _recall_from_learning_objects(self, situation: str) -> list[dict[str, Any]]:
        """Recall from learning objects (patterns discovered)."""
        moments = []
        try:
            for lo in list(self.model.learning_objects.values())[:5]:
                lo_type = lo.type.value if hasattr(lo.type, "value") else str(lo.type)
                moments.append({
                    "when": "from signal history",
                    "situation": f"Pattern discovered: {lo.title[:60]}" if lo.title else f"Pattern: {lo_type}",
                    "what_we_did": f"Observed {lo.evidence_count} instances of this pattern",
                    "what_we_learned": lo.description[:80] if lo.description else "A recurring organizational pattern",
                    "outcome": "validated" if lo_type == "validated" else "observed",
                    "source": "learning_history",
                })
        except Exception as e:
            logger.debug("LO recall failed: %s", e)
        return moments[:2]

    def _recall_from_contradictions(self, situation: str) -> list[dict[str, Any]]:
        """Recall from past contradictions (tensions and their resolution)."""
        moments = []
        try:
            from maestro_oem.contradictions import ContradictionDetector
            from maestro_api.routes.oem import _get_assumption_graph
            graph = _get_assumption_graph()
            detector = ContradictionDetector(self.model, self.signals, graph)
            contradictions = detector.detect_all()

            for c in contradictions[:2]:
                moments.append({
                    "when": "recent",
                    "situation": f"Tension detected: {c.get('title', 'organizational contradiction')[:60]}",
                    "what_we_did": "Identified the gap between stated belief and observed behavior",
                    "what_we_learned": c.get("description", "The organization's stated beliefs don't always match its behavior.")[:80],
                    "outcome": c.get("status", "open"),
                    "source": "contradiction_history",
                })
        except Exception as e:
            logger.debug("Contradiction recall failed: %s", e)
        return moments[:1]

    def _recall_from_signals(self, situation: str) -> list[dict[str, Any]]:
        """Recall from signal history (similar past events)."""
        moments = []
        try:
            # Find signals with similar text to the situation
            sit_lower = situation.lower()
            sit_words = set(w for w in sit_lower.split() if len(w) > 3)

            if not sit_words:
                return moments

            matching = []
            for s in self.signals:
                text = s.metadata.get("text", "").lower()
                if not text:
                    continue
                overlap = sum(1 for w in sit_words if w in text)
                if overlap >= 2:
                    matching.append((s, overlap))

            matching.sort(key=lambda x: x[1], reverse=True)

            for s, _ in matching[:2]:
                moments.append({
                    "when": s.timestamp or "from signal history",
                    "situation": f"Similar event: {s.metadata.get('text', '')[:60]}",
                    "what_we_did": f"Signal from {s.actor or 'unknown'} via {s.provider or 'unknown'}",
                    "what_we_learned": "This event was part of the organizational signal history.",
                    "outcome": "observed",
                    "source": "signal_history",
                })
        except Exception as e:
            logger.debug("Signal recall failed: %s", e)
        return moments[:2]
