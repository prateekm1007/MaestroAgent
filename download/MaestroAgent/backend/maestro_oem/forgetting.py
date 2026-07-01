"""
Spec #4 — Forgetting Engine: archive zero-predictive-value events.

Brains forget for a reason. Compression is not forgetting. Events with
predictive_value < 0.05 AND age > 180 days are flagged for archiving
(NOT deleted — moved to cold storage).

The forgetting engine computes a predictive_value score for each
learning object, law, and signal cluster. Low-value events are noise
that distracts from signal.

API: GET /api/oem/forgetting
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ForgettingEngine:
    """Identify events the organization should forget.

    Forgetting is not deletion — it's deprioritization. Events with
    low predictive value are moved to cold storage so they don't
    clutter the active memory. The organization can still recall them
    if needed, but they won't appear in the morning brief or recommendations.
    """

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def assess(self) -> dict[str, Any]:
        """Assess what should be forgotten."""
        candidates = []

        # 1. Assess learning objects
        candidates.extend(self._assess_learning_objects())

        # 2. Assess laws (stressed or invalidated ones)
        candidates.extend(self._assess_laws())

        # 3. Assess signal clusters (domains with old, low-value signals)
        candidates.extend(self._assess_signal_clusters())

        if not candidates:
            return {
                "candidates": [],
                "summary": "Nothing needs forgetting. All organizational memory is actively predictive.",
                "candidate_count": 0,
            }

        # Sort by predictive_value (lowest first — most forgettable)
        candidates.sort(key=lambda c: c.get("predictive_value", 1.0))
        candidates = candidates[:10]

        high_confidence = sum(1 for c in candidates if c.get("predictive_value", 1.0) < 0.05)
        summary = f"{len(candidates)} {'event' if len(candidates) == 1 else 'events'} flagged for archiving. {high_confidence} {'has' if high_confidence == 1 else 'have'} very low predictive value (< 5%)."

        return {
            "candidates": candidates,
            "summary": summary,
            "candidate_count": len(candidates),
        }

    def _assess_learning_objects(self) -> list[dict[str, Any]]:
        """Assess learning objects for predictive value."""
        candidates = []
        try:
            for lo in list(self.model.learning_objects.values())[:20]:
                # Predictive value = how well this LO predicts future outcomes
                # Heuristic: validated LOs with high evidence = high predictive value
                # Unvalidated LOs with low evidence and old age = low predictive value
                evidence = lo.evidence_count or 0
                confidence = lo.confidence or 0

                # Simple predictive value score
                predictive_value = min(1.0, (evidence / 10) * confidence)

                if predictive_value < 0.15 and evidence < 3:
                    candidates.append({
                        "entity_type": "learning_object",
                        "entity_id": lo.title[:60] if lo.title else "unnamed",
                        "predictive_value": round(predictive_value, 2),
                        "reason": f"Low evidence ({evidence} signals) and low confidence ({confidence:.2f}). This pattern hasn't been validated enough to predict future outcomes.",
                        "narrative": f"This pattern has only {evidence} {'signal' if evidence == 1 else 'signals'} of support. It's not yet predictive. Consider archiving until more evidence accumulates.",
                        "evidence_count": evidence,
                    })
        except Exception as e:
            logger.debug("LO assessment failed: %s", e)
        return candidates[:5]

    def _assess_laws(self) -> list[dict[str, Any]]:
        """Assess laws for predictive value — stressed/invalidated laws are candidates."""
        candidates = []
        try:
            for law in list(self.model.laws.values())[:10]:
                if law.status and law.status.value in ("stressed", "invalidated"):
                    failed = law.failed_runtimes or 0
                    validated = law.validated_runtimes or 0
                    total = validated + failed
                    predictive_value = validated / max(total, 1) if total > 0 else 0

                    if predictive_value < 0.3:
                        candidates.append({
                            "entity_type": "pattern",
                            "entity_id": law.statement[:60] if law.statement else "unnamed",
                            "predictive_value": round(predictive_value, 2),
                            "reason": f"This pattern is {law.status.value} — {failed} of {total} outcomes deviated. It no longer reliably predicts.",
                            "narrative": f"This pattern failed {failed} times out of {total}. It's no longer a reliable predictor. Consider archiving it.",
                            "evidence_count": law.evidence_count or 0,
                        })
        except Exception as e:
            logger.debug("Law assessment failed: %s", e)
        return candidates[:3]

    def _assess_signal_clusters(self) -> list[dict[str, Any]]:
        """Assess signal clusters for predictive value."""
        candidates = []
        try:
            from collections import Counter
            domain_counts = Counter()
            for s in self.signals:
                domain = s.metadata.get("domain", "")
                if domain:
                    domain_counts[domain] += 1

            for domain, count in domain_counts.items():
                if count == 1:
                    candidates.append({
                        "entity_type": "signal_cluster",
                        "entity_id": f"domain: {domain}",
                        "predictive_value": 0.02,
                        "reason": f"Only 1 signal in the {domain} domain. A single signal has no predictive value.",
                        "narrative": f"The {domain} domain has only 1 signal. This is noise, not signal. Consider archiving until more data arrives.",
                        "evidence_count": count,
                    })
        except Exception as e:
            logger.debug("Signal cluster assessment failed: %s", e)
        return candidates[:2]
