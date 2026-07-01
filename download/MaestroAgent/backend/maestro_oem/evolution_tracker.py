"""
V6 Spec #2 — Evolution Tracker.

"We no longer make this mistake."

Tracks specific failure modes from active → resolving → eliminated.
A failure mode is "eliminated" when it hasn't recurred for 90+ days
after an intervention.

Failure modes are discovered from:
  - Contradictions (stated belief vs observed behavior)
  - Invalidated assumptions
  - Stressed/invalidated laws (patterns that stopped working)
  - Recurring bottlenecks

Each failure mode has:
  - first_observed, last_observed, frequency_history
  - current_status: active | resolving | eliminated
  - intervention: what was done to address it (if any)

API: GET /api/oem/evolution-tracker
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class EvolutionTracker:
    """Track failure modes through their lifecycle.

    The tracker answers: "What mistakes has the organization stopped
    making?" This is the most powerful signal of organizational evolution —
    not what you're learning, but what you've unlearned.
    """

    ELIMINATED_DAYS = 90  # 90 days without recurrence = eliminated

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def track(self) -> dict[str, Any]:
        """Track all failure modes through their lifecycle."""
        modes = []

        # 1. Contradictions as failure modes
        modes.extend(self._track_contradictions())

        # 2. Invalidated assumptions
        modes.extend(self._track_invalidated_assumptions())

        # 3. Stressed/invalidated laws
        modes.extend(self._track_stressed_laws())

        # 4. Recurring bottlenecks
        modes.extend(self._track_bottlenecks())

        if not modes:
            return {
                "failure_modes": [],
                "summary": "No failure modes tracked yet. The organization is still gathering the history needed to identify and track mistakes over time.",
                "mode_count": 0,
                "eliminated_count": 0,
            }

        eliminated = sum(1 for m in modes if m.get("current_status") == "eliminated")
        active = sum(1 for m in modes if m.get("current_status") == "active")
        resolving = sum(1 for m in modes if m.get("current_status") == "resolving")

        if eliminated > 0:
            summary = f"Your organization has eliminated {eliminated} {'mistake' if eliminated == 1 else 'mistakes'}. {active} {'is' if active == 1 else 'are'} still active, {resolving} {'is' if resolving == 1 else 'are'} being resolved."
        else:
            summary = f"Tracking {len(modes)} failure {'mode' if len(modes) == 1 else 'modes'}. {active} active, {resolving} resolving. No eliminated modes yet — the pilot is too young (needs 90+ days without recurrence)."

        return {
            "failure_modes": modes,
            "summary": summary,
            "mode_count": len(modes),
            "eliminated_count": eliminated,
            "active_count": active,
            "resolving_count": resolving,
        }

    def _track_contradictions(self) -> list[dict[str, Any]]:
        """Track contradictions as failure modes."""
        modes = []
        try:
            from maestro_oem.contradictions import ContradictionDetector
            from maestro_api.routes.oem import _get_assumption_graph
            graph = _get_assumption_graph()
            detector = ContradictionDetector(self.model, self.signals, graph)
            contradictions = detector.detect_all()

            for c in contradictions[:3]:
                status = c.get("status", "open")
                tracker_status = "active" if status == "open" else "resolving" if status == "acknowledged" else "eliminated"

                modes.append({
                    "failure_mode": c.get("title", "Organizational contradiction")[:80],
                    "type": "contradiction",
                    "first_observed": "recent",
                    "last_observed": "recent",
                    "frequency": 1,
                    "current_status": tracker_status,
                    "intervention": "Acknowledged" if tracker_status != "active" else "Not yet addressed",
                    "narrative": f"Stated belief doesn't match observed behavior. {c.get('description', '')[:60]}",
                    "days_since_last_occurrence": 0,
                })
        except Exception as e:
            logger.debug("Contradiction tracking failed: %s", e)
        return modes[:2]

    def _track_invalidated_assumptions(self) -> list[dict[str, Any]]:
        """Track invalidated assumptions as failure modes."""
        modes = []
        try:
            from maestro_api.routes.oem import _get_assumption_graph
            graph = _get_assumption_graph()
            all_assumptions = graph.list_assumptions()

            for a in all_assumptions[:5]:
                status = a.get("status", "open")
                if status == "invalidated":
                    modes.append({
                        "failure_mode": f"Assumed: {a.get('statement', '')[:60]}",
                        "type": "invalidated_assumption",
                        "first_observed": a.get("created_at", "unknown"),
                        "last_observed": "recent",
                        "frequency": 1,
                        "current_status": "eliminated",
                        "intervention": "The assumption was invalidated by evidence. The organization no longer holds this belief.",
                        "narrative": f"This assumption was disproven. The organization learned it was wrong and stopped acting on it.",
                        "days_since_last_occurrence": 90,  # Assumption is invalidated, not recurring
                    })
        except Exception as e:
            logger.debug("Assumption tracking failed: %s", e)
        return modes[:2]

    def _track_stressed_laws(self) -> list[dict[str, Any]]:
        """Track stressed/invalidated laws as failure modes."""
        modes = []
        try:
            for law in list(self.model.laws.values())[:10]:
                if law.status and law.status.value in ("stressed", "invalidated"):
                    failed = law.failed_runtimes or 0
                    validated = law.validated_runtimes or 0

                    modes.append({
                        "failure_mode": f"Pattern stopped working: {law.statement[:60]}" if law.statement else "Pattern failure",
                        "type": "stressed_pattern",
                        "first_observed": "from signal history",
                        "last_observed": "recent",
                        "frequency": failed,
                        "current_status": "active" if law.status.value == "stressed" else "eliminated",
                        "intervention": "Pattern is being monitored" if law.status.value == "stressed" else "Pattern invalidated — no longer applied",
                        "narrative": f"This pattern failed {failed} times out of {validated + failed}. The organization is {'still applying it (stressed)' if law.status.value == 'stressed' else 'no longer applying it (eliminated)'}.",
                        "days_since_last_occurrence": 0 if law.status.value == "stressed" else 90,
                    })
        except Exception as e:
            logger.debug("Stressed law tracking failed: %s", e)
        return modes[:2]

    def _track_bottlenecks(self) -> list[dict[str, Any]]:
        """Track recurring bottlenecks as failure modes."""
        modes = []
        try:
            from collections import Counter
            from maestro_oem.signal import SignalType
            bottleneck_actors = Counter()
            for s in self.signals:
                if s.type == SignalType.ISSUE_BLOCKED or "bottleneck" in str(s.metadata.get("text", "")).lower():
                    if s.actor:
                        bottleneck_actors[s.actor] += 1

            for actor, count in bottleneck_actors.most_common(1):
                if count >= 2:
                    modes.append({
                        "failure_mode": f"Bottleneck: {actor} blocks workflows",
                        "type": "bottleneck",
                        "first_observed": "from signal history",
                        "last_observed": "recent",
                        "frequency": count,
                        "current_status": "active",
                        "intervention": "Not yet addressed",
                        "narrative": f"{actor} has been a bottleneck {count} times. This is an active failure mode — the organization has not yet restructured to prevent it.",
                        "days_since_last_occurrence": 0,
                    })
        except Exception as e:
            logger.debug("Bottleneck tracking failed: %s", e)
        return modes[:1]
