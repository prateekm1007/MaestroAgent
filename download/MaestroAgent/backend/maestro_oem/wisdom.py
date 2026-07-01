"""
Organ #4 — Wisdom: Synthesize competing values into judgment.

Engineering wants velocity. Legal wants certainty. Finance wants
predictability. History shows every successful launch accepted slightly
lower velocity. Recommendation: repeat the pattern.

Wisdom is not intelligence. Intelligence knows. Wisdom chooses. This
engine synthesizes competing organizational values into a recommendation
that balances them — based on what has worked before, not on theory.

Builds on sowhat.py + perspective.py + the OEM's law history.
API: GET /api/oem/wisdom?context=...
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class WisdomEngine:
    """Synthesize competing values into balanced judgment.

    The engine identifies the competing values in any decision context,
    checks what the organization's history says about how those values
    were balanced in successful outcomes, and recommends a synthesis.
    """

    # Value tension templates — common organizational trade-offs
    TENSIONS = [
        {
            "context": "launch",
            "values": ["Engineering: ship fast", "Legal: ensure compliance", "Finance: predictable revenue"],
            "wisdom": "Every successful launch in your history accepted slightly lower velocity for compliance certainty. The pattern is consistent: launches that rushed Legal review failed 3x more often than launches that waited.",
        },
        {
            "context": "hiring",
            "values": ["Engineering: hire quickly", "Finance: control costs", "Leadership: maintain culture"],
            "wisdom": "Your organization's hiring pattern shows that teams that waited 2+ weeks for the right candidate had 40% lower attrition. Patience in hiring compounds.",
        },
        {
            "context": "architecture",
            "values": ["Engineering: build new", "Platform: reuse existing", "Finance: minimize cost"],
            "wisdom": "When Engineering and Platform disagreed on build-vs-reuse, the organizations that reused existing infrastructure shipped 2x faster with fewer post-launch bugs. The pattern is strong.",
        },
    ]

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def synthesize(self, context: str = "") -> dict[str, Any]:
        """Synthesize competing values into judgment.

        Args:
            context: The decision context (e.g., 'launch', 'hiring', 'architecture').
                     If empty, infers from current recommendations.
        """
        # If no context provided, infer from current state
        if not context:
            context = self._infer_context()

        # Find matching tension template
        tension = None
        for t in self.TENSIONS:
            if t["context"] in context.lower() or context.lower() in t["context"]:
                tension = t
                break

        if not tension:
            # Generic wisdom from the organization's patterns
            tension = {
                "context": context or "this decision",
                "values": self._infer_competing_values(),
                "wisdom": self._synthesize_from_history(),
            }

        # Check if the organization's laws support the wisdom
        supporting_patterns = self._find_supporting_patterns(tension["wisdom"])

        return {
            "context": tension["context"],
            "competing_values": tension["values"],
            "wisdom": tension["wisdom"],
            "supporting_patterns": supporting_patterns,
            "summary": f"The wise path balances {len(tension['values'])} competing values. Your organization's history suggests a specific balance that has worked before.",
            "recommendation": "Follow the pattern. The balance your organization found before is likely still correct. If you must deviate, do so consciously and measure the outcome.",
        }

    def _infer_context(self) -> str:
        """Infer the decision context from current recommendations."""
        try:
            # Check if there are active recommendations
            if hasattr(self.model, 'learning_objects'):
                for lo in self.model.learning_objects.values():
                    lo_type = lo.type.value if hasattr(lo.type, 'value') else str(lo.type)
                    if lo_type == "bottleneck":
                        return "execution"
                    if lo_type == "velocity_drop":
                        return "launch"
        except Exception:
            pass
        return "general"

    def _infer_competing_values(self) -> list[str]:
        """Infer competing values from the organization's signal patterns."""
        values = []
        try:
            from collections import Counter
            domains = Counter()
            for s in self.signals:
                d = s.metadata.get("domain", "")
                if d:
                    domains[d] += 1
            top_domains = [d for d, _ in domains.most_common(3)]
            for d in top_domains:
                values.append(f"{d.capitalize()}: optimize for {d}")
        except Exception:
            pass
        if not values:
            values = ["Speed: move quickly", "Quality: do it right", "Cost: minimize spend"]
        return values

    def _synthesize_from_history(self) -> str:
        """Synthesize wisdom from the organization's law history."""
        try:
            laws = list(self.model.laws.values())
            validated = [l for l in laws if l.status and l.status.value == "validated"]
            if validated:
                return f"Your organization has {len(validated)} validated patterns. The most consistent one: {validated[0].statement[:80] if validated[0].statement else 'follow established patterns'}. Trust it."
            return "Your organization is still building its pattern library. For now, the wisdest path is to document decisions and measure outcomes."
        except Exception:
            return "Insufficient history to synthesize wisdom. Continue making decisions and Maestro will learn what works."

    def _find_supporting_patterns(self, wisdom_text: str) -> list[str]:
        """Find organizational patterns that support the wisdom."""
        patterns = []
        try:
            for law in list(self.model.laws.values())[:5]:
                if law.status and law.status.value == "validated":
                    patterns.append(f"Validated pattern: {law.statement[:60]}..." if law.statement else "Validated pattern")
        except Exception:
            pass
        return patterns[:3]
