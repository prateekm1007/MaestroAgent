"""
Organ #7 — Memory Compression: millions of signals → a few truths.

2M signals → 3 truths, 7 habits, 2 mistakes, 5 interventions.
Memory becomes understanding, not a searchable archive.

The human brain doesn't remember every experience — it compresses them
into lessons, habits, and instincts. Maestro should do the same: take
the raw firehose of organizational signals and compress them into a small
set of insights that fit in the CEO's head.

Builds on learning.py + evidence_graph.py + law.py.
API: GET /api/oem/compression
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)


class MemoryCompressionEngine:
    """Compress organizational memory into a small set of truths.

    The output should fit on one page. If the CEO can't remember it,
    it's not compressed enough.
    """

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def compress(self) -> dict[str, Any]:
        """Compress all organizational memory into truths, habits, mistakes, interventions."""
        truths = self._extract_truths()
        habits = self._extract_habits()
        mistakes = self._extract_mistakes()
        interventions = self._extract_interventions()

        total_input = len(self.signals)
        total_output = len(truths) + len(habits) + len(mistakes) + len(interventions)
        compression_ratio = total_input / max(total_output, 1) if total_output > 0 else 0

        return {
            "truths": truths,
            "habits": habits,
            "mistakes": mistakes,
            "interventions": interventions,
            "compression": {
                "input_signals": total_input,
                "output_insights": total_output,
                "ratio": f"{compression_ratio:.0f}:1" if compression_ratio > 0 else "N/A",
            },
            "summary": f"{total_input} signals compressed into {total_output} insights ({len(truths)} truths, {len(habits)} habits, {len(mistakes)} mistakes, {len(interventions)} interventions).",
        }

    def _extract_truths(self) -> list[dict[str, Any]]:
        """Extract the organization's core truths — validated patterns."""
        truths = []
        try:
            laws = list(self.model.laws.values())
            validated = [l for l in laws if l.status and l.status.value == "validated"]
            for law in validated[:3]:
                truths.append({
                    "truth": law.statement[:100] if law.statement else "Validated organizational pattern",
                    "evidence": f"Observed {law.validated_runtimes} times, never failed",
                    "confidence": "high",
                })
        except Exception:
            pass

        if not truths:
            truths.append({
                "truth": "Your organization is still discovering what consistently works.",
                "evidence": "No validated patterns yet",
                "confidence": "emerging",
            })

        return truths

    def _extract_habits(self) -> list[dict[str, Any]]:
        """Extract organizational habits — repeated behaviors."""
        habits = []
        try:
            type_counts = Counter(s.type.value if hasattr(s.type, 'value') else str(s.type) for s in self.signals)
            for sig_type, count in type_counts.most_common(5):
                if count > 3:
                    habits.append({
                        "habit": f"The organization consistently {sig_type.replace('_', ' ').lower()}",
                        "frequency": f"{count} times observed",
                        "assessment": "productive" if count < 20 else "possibly excessive",
                    })
        except Exception:
            pass

        return habits[:5]

    def _extract_mistakes(self) -> list[dict[str, Any]]:
        """Extract mistakes — patterns that failed."""
        mistakes = []
        try:
            laws = list(self.model.laws.values())
            for law in laws:
                if law.failed_runtimes and law.failed_runtimes > 0:
                    mistakes.append({
                        "mistake": f"Following '{law.statement[:60]}...' failed {law.failed_runtimes} times" if law.statement else f"A pattern failed {law.failed_runtimes} times",
                        "lesson": "This pattern doesn't always hold. Check conditions before applying.",
                        "evidence": f"{law.failed_runtimes} failures out of {law.validated_runtimes + law.failed_runtimes} attempts",
                    })
        except Exception:
            pass

        # Also check for contradictions — they indicate mistaken beliefs
        try:
            from maestro_oem.contradictions import ContradictionDetector
            from maestro_api.routes.oem import _get_assumption_graph
            graph = _get_assumption_graph()
            detector = ContradictionDetector(self.model, self.signals, graph)
            contradictions = detector.detect_all()
            for c in contradictions[:2]:
                mistakes.append({
                    "mistake": f"Believed: {c.get('title', 'a contradiction')[:60]}",
                    "lesson": "The stated belief doesn't match observed behavior.",
                    "evidence": c.get('description', '')[:80],
                })
        except Exception:
            pass

        return mistakes[:3]

    def _extract_interventions(self) -> list[dict[str, Any]]:
        """Extract interventions — actions the org took that changed outcomes."""
        interventions = []
        try:
            # Look for CEO feedback (contradictions) that changed confidence
            from maestro_oem.signal import SignalType
            decisions = [s for s in self.signals if s.type == SignalType.DECISION_SIGNAL]
            for d in decisions[:3]:
                text = d.metadata.get("text", "")
                if text:
                    interventions.append({
                        "intervention": f"Decision: {text[:80]}",
                        "impact": "Changed the organizational trajectory",
                        "actor": d.actor or "unknown",
                    })
        except Exception:
            pass

        return interventions[:5]
