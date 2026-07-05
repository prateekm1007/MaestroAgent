"""
Organ #8 — Consciousness: Always knows where the organization's
attention, knowledge, trust, conflict, energy, uncertainty, and learning are.

Maintains a real-time organizational state vector, updated on every
signal ingest. The Organizational Dot draws from this state vector.

Consciousness is not a dashboard. It's a continuous awareness of the
organization's state — like how you know you're tired without checking
a fatigue meter. The organization should know it's in tension without
opening a contradictions page.

Builds on all 7 previous organs + pulse.py + feed.py.
API: GET /api/oem/consciousness
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class ConsciousnessEngine:
    """Maintain a real-time organizational state vector.

    The state vector has 7 dimensions, each 0.0-1.0:
      - attention: how focused the organization is (signal recency + density)
      - knowledge: how much the organization knows (validated patterns)
      - trust: cross-functional alignment (agreement vs conflict ratio)
      - conflict: active tensions (contradictions + conflicts)
      - energy: organizational momentum (signal velocity)
      - uncertainty: unresolved predictions + open assumptions
      - learning: rate of new pattern discovery

    The Organizational Dot color is derived from this vector.
    """

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def state_vector(self) -> dict[str, Any]:
        """Compute the real-time organizational state vector."""
        dimensions = {
            "attention": self._compute_attention(),
            "knowledge": self._compute_knowledge(),
            "trust": self._compute_trust(),
            "conflict": self._compute_conflict(),
            "energy": self._compute_energy(),
            "uncertainty": self._compute_uncertainty(),
            "learning": self._compute_learning(),
        }

        # Derive overall state
        avg = sum(d["score"] for d in dimensions.values()) / max(len(dimensions), 1)
        dominant = max(dimensions.items(), key=lambda x: x[1]["score"])

        # Derive dot color from state vector
        dot_color = self._derive_dot_color(dimensions)

        # Generate a one-sentence state description
        state_sentence = self._describe_state(dimensions)

        return {
            "dimensions": dimensions,
            "overall_score": round(avg, 2),
            "dominant_dimension": dominant[0],
            "dot_color": dot_color,
            "state": state_sentence,
            "summary": f"The organization is currently {state_sentence}.",
        }

    def _compute_attention(self) -> dict[str, Any]:
        """How focused is the organization? Based on signal recency + density."""
        if not self.signals:
            return {"score": 0.3, "label": "dormant", "basis": "no recent signals"}
        recent = [s for s in self.signals if s.timestamp]
        if not recent:
            return {"score": 0.5, "label": "moderate", "basis": "signals present but no timestamps"}
        try:
            latest = max(s.timestamp for s in recent if s.timestamp)
            if isinstance(latest, str):
                latest_dt = datetime.fromisoformat(latest.replace("Z", "+00:00"))
            else:
                latest_dt = latest
            hours_ago = (datetime.now(timezone.utc) - latest_dt).total_seconds() / 3600
            if hours_ago < 24:
                return {"score": 0.8, "label": "highly focused", "basis": f"last signal {hours_ago:.0f}h ago"}
            elif hours_ago < 72:
                return {"score": 0.5, "label": "moderately attentive", "basis": f"last signal {hours_ago:.0f}h ago"}
            else:
                return {"score": 0.2, "label": "dormant", "basis": f"last signal {hours_ago:.0f}h ago"}
        except Exception:
            return {"score": 0.5, "label": "moderate", "basis": "unable to determine recency"}

    def _compute_knowledge(self) -> dict[str, Any]:
        """How much does the organization know? Based on validated patterns."""
        try:
            laws = list(self.model.laws.values())
            validated = sum(1 for l in laws if l.status and l.status.value == "validated")
            total = len(laws)
            score = validated / max(total, 1) if total > 0 else 0.2
            label = "deep" if score > 0.5 else "building" if score > 0.2 else "shallow"
            return {"score": round(score, 2), "label": label, "basis": f"{validated}/{total} patterns validated"}
        except Exception:
            return {"score": 0.2, "label": "shallow", "basis": "no pattern data"}

    def _compute_trust(self) -> dict[str, Any]:
        """Cross-functional alignment — agreement vs conflict ratio."""
        try:
            from maestro_oem.signal import SignalType
            agreements = sum(1 for s in self.signals if s.type == SignalType.AGREEMENT)
            conflicts = sum(1 for s in self.signals if s.type == SignalType.CONFLICT)
            total = agreements + conflicts
            if total == 0:
                return {"score": 0.5, "label": "neutral", "basis": "no trust signals"}
            score = agreements / total
            label = "high" if score > 0.6 else "moderate" if score > 0.3 else "low"
            return {"score": round(score, 2), "label": label, "basis": f"{agreements} agreements, {conflicts} conflicts"}
        except Exception:
            return {"score": 0.5, "label": "neutral", "basis": "no trust data"}

    def _compute_conflict(self) -> dict[str, Any]:
        """Active tensions — contradictions + conflicts (inverted: high conflict = low score)."""
        try:
            from maestro_oem.contradictions import ContradictionDetector
            from maestro_api.routes.oem import _get_assumption_graph
            graph = _get_assumption_graph()
            detector = ContradictionDetector(self.model, self.signals, graph)
            contradictions = detector.detect_all()
            count = len(contradictions)
            score = max(0, 1 - count * 0.15)
            label = "calm" if count == 0 else "tense" if count < 3 else "volatile"
            return {"score": round(score, 2), "label": label, "basis": f"{count} active contradictions"}
        except Exception:
            return {"score": 0.5, "label": "neutral", "basis": "no contradiction data"}

    def _compute_energy(self) -> dict[str, Any]:
        """Organizational momentum — signal volume."""
        count = len(self.signals)
        if count > 50:
            return {"score": 0.8, "label": "high energy", "basis": f"{count} signals"}
        elif count > 20:
            return {"score": 0.6, "label": "active", "basis": f"{count} signals"}
        elif count > 5:
            return {"score": 0.4, "label": "moderate", "basis": f"{count} signals"}
        else:
            return {"score": 0.2, "label": "low energy", "basis": f"{count} signals"}

    def _compute_uncertainty(self) -> dict[str, Any]:
        """Unresolved predictions + open assumptions (inverted)."""
        try:
            from maestro_api.routes.oem import _get_assumption_graph
            graph = _get_assumption_graph()
            open_assumptions = sum(1 for a in graph.list_assumptions() if a.get("status") in ("open", None, ""))
            score = max(0, 1 - open_assumptions * 0.1)
            label = "certain" if score > 0.7 else "exploring" if score > 0.4 else "uncertain"
            return {"score": round(score, 2), "label": label, "basis": f"{open_assumptions} open assumptions"}
        except Exception:
            return {"score": 0.5, "label": "neutral", "basis": "no assumption data"}

    def _compute_learning(self) -> dict[str, Any]:
        """Rate of new pattern discovery."""
        try:
            laws = list(self.model.laws.values())
            total = len(laws)
            if total > 10:
                return {"score": 0.8, "label": "fast learning", "basis": f"{total} patterns discovered"}
            elif total > 3:
                return {"score": 0.6, "label": "learning steadily", "basis": f"{total} patterns"}
            else:
                return {"score": 0.3, "label": "early stage", "basis": f"{total} patterns"}
        except Exception:
            return {"score": 0.3, "label": "early stage", "basis": "no pattern data"}

    def _derive_dot_color(self, dims: dict[str, dict]) -> str:
        """Derive the Organizational Dot color from the state vector."""
        conflict_score = dims.get("conflict", {}).get("score", 0.5)
        trust_score = dims.get("trust", {}).get("score", 0.5)
        attention_score = dims.get("attention", {}).get("score", 0.5)

        if conflict_score < 0.3:
            return "red"
        if conflict_score < 0.5:
            return "orange"
        if attention_score > 0.7 and trust_score > 0.5:
            return "green"
        return "yellow"

    def _describe_state(self, dims: dict[str, dict]) -> str:
        """Generate a one-sentence description of the organizational state."""
        dominant = max(dims.items(), key=lambda x: x[1]["score"])
        weakest = min(dims.items(), key=lambda x: x[1]["score"])

        dom_name = dominant[0]
        dom_label = dominant[1]["label"]
        weak_name = weakest[0]
        weak_label = weakest[1]["label"]

        return f"strong in {dom_name} ({dom_label}), weak in {weak_name} ({weak_label})"
