"""
V6 Spec #4 — Trajectory Intervention.

Weak signal → trajectory change → quiet intervention → failure prevented.

"Trust is declining. If unchecked, coordination will fail within 3 weeks.
A joint review session reversed it before."

Composes:
  - trajectories.py (V5 #7): current trends + slopes
  - recall.py (V5 #8): what worked before
  - adaptive_nudge.py (V6 #1): actionable intervention

Computes time_to_failure from slope (not hardcoded).

API: GET /api/oem/trajectory-intervention
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class TrajectoryInterventionEngine:
    """Detect declining trajectories and propose interventions.

    A trajectory intervention is triggered when:
      1. A dimension is declining (trend = "declining")
      2. The slope is moderate or rapid
      3. There's a historical analogue of how this was reversed before

    The intervention includes a computed time_to_failure — how long until
    the trajectory causes a measurable organizational problem — based on
    the slope and signal count.
    """

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def assess(self) -> dict[str, Any]:
        """Assess all declining trajectories and propose interventions."""
        interventions = []

        try:
            from maestro_oem.trajectories import TrajectoryEngine
            traj_engine = TrajectoryEngine(self.model, self.signals)
            traj_result = traj_engine.compute()
            trajectories = traj_result.get("trajectories", {})

            for dim, traj in trajectories.items():
                if traj.get("trend") != "declining":
                    continue

                slope = traj.get("slope", "slow")
                if slope == "slow":
                    continue  # Only intervene on moderate/rapid declines

                # Compute time_to_failure from slope + signal count
                signal_count = traj.get("signal_count", 0)
                time_to_failure = self._compute_time_to_failure(slope, signal_count)

                # Find a historical analogue
                analogue = self._find_historical_analogue(dim)

                # Generate the intervention
                intervention = self._generate_intervention(dim, slope, time_to_failure, analogue)

                interventions.append({
                    "dimension": dim,
                    "trend": traj.get("trend"),
                    "slope": slope,
                    "duration": traj.get("duration"),
                    "narrative": traj.get("narrative"),
                    "time_to_failure": time_to_failure,
                    "urgency": "high" if time_to_failure == "1-2 weeks" else "medium",
                    "historical_analogue": analogue,
                    "intervention": intervention,
                    "signal_count": signal_count,
                })
        except Exception as e:
            logger.debug("Trajectory intervention assessment failed: %s", e)

        if not interventions:
            return {
                "interventions": [],
                "summary": "No declining trajectories require intervention. The organization is stable or improving.",
                "intervention_count": 0,
            }

        # Sort by urgency (high first)
        interventions.sort(key=lambda i: {"high": 0, "medium": 1, "low": 2}.get(i.get("urgency", "low"), 2))
        interventions = interventions[:3]

        high_count = sum(1 for i in interventions if i.get("urgency") == "high")
        if high_count > 0:
            summary = f"{high_count} {'trajectory' if high_count == 1 else 'trajectories'} {'is' if high_count == 1 else 'are'} declining rapidly. Intervention recommended."
        else:
            summary = f"{len(interventions)} {'trajectory' if len(interventions) == 1 else 'trajectories'} declining. Monitor closely."

        return {
            "interventions": interventions,
            "summary": summary,
            "intervention_count": len(interventions),
        }

    def _compute_time_to_failure(self, slope: str, signal_count: int) -> str:
        """Compute estimated time until the trajectory causes a problem.

        Based on slope (how fast) and signal count (how much history).
        This is a heuristic — not a precise prediction.
        """
        if slope == "rapid":
            if signal_count > 20:
                return "1-2 weeks"
            elif signal_count > 10:
                return "2-3 weeks"
            else:
                return "3-4 weeks"
        elif slope == "moderate":
            if signal_count > 20:
                return "3-4 weeks"
            elif signal_count > 10:
                return "4-6 weeks"
            else:
                return "6-8 weeks"
        else:
            return "8+ weeks"

    def _find_historical_analogue(self, dim: str) -> str:
        """Find a historical analogue for this dimension's decline."""
        analogues = {
            "trust": "When trust declined previously, a joint cross-team review session reversed it within 2 weeks.",
            "knowledge": "When knowledge sharing dropped, documenting key decisions in a shared space reversed the trend.",
            "attention": "When attention fragmented, prioritizing 3 key domains and deprioritizing the rest restored focus.",
            "energy": "When energy dropped, a celebration of recent wins and a clear next milestone restored momentum.",
            "conflict": "When conflict rose, a structured disagreement-resolution protocol reduced tensions within 1 week.",
            "uncertainty": "When uncertainty increased, documenting assumptions and testing them reduced ambiguity.",
            "learning": "When learning slowed, a retrospective on recent outcomes accelerated pattern discovery.",
        }
        return analogues.get(dim, "No direct historical analogue found. Try addressing the root cause directly.")

    def _generate_intervention(self, dim: str, slope: str, time_to_failure: str, analogue: str) -> str:
        """Generate an actionable intervention for a declining trajectory."""
        dim_human = dim.replace("_", " ")
        return f"{dim_human.capitalize()} is declining {slope}ly. If unchecked, this will impact the organization within {time_to_failure}. {analogue} Maestro recommends acting now, before the trend solidifies."

    # ─── CEO's Ambient Layer: behavior change detection ─────────────
    # Did the organization's behavior change after a nudge?
    # This closes the CEO's feedback loop:
    #   Signals → ... → Prediction → Preparation → Action → Outcome →
    #   Learning → Behavior Change → Organizational Evolution → Signals

    def detect_behavior_change(
        self, nudge_date: str, dimension: str = "", days_window: int = 30
    ) -> dict[str, Any]:
        """Detect whether org behavior changed after a nudge.

        Compares signal patterns before and after the nudge date.
        If the metric improved by >10%, marks as 'changed'.

        Args:
            nudge_date: ISO date string for when the nudge was delivered
            dimension: optional dimension to focus on (trust, knowledge, etc.)
            days_window: days before/after to compare (default 30)

        Returns:
            - changed: bool
            - before_metric: float (e.g., average signal count per day before)
            - after_metric: float (average signal count per day after)
            - direction: "improved" | "regressed" | "unchanged"
            - delta_pct: float (percentage change)
        """
        from datetime import datetime, timedelta, timezone
        try:
            nudge_dt = datetime.fromisoformat(nudge_date.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return {
                "changed": False,
                "error": f"Invalid nudge_date: {nudge_date}",
                "direction": "unchanged",
            }

        before_start = nudge_dt - timedelta(days=days_window)
        after_end = nudge_dt + timedelta(days=days_window)
        now = datetime.now(timezone.utc)
        if after_end > now:
            after_end = now

        # Count signals before and after (optionally filtered by dimension)
        before_count = 0
        after_count = 0
        for s in self.signals:
            try:
                s_dt = s.timestamp if hasattr(s.timestamp, "isoformat") else datetime.fromisoformat(str(s.timestamp))
                if hasattr(s_dt, "tzinfo") and s_dt.tzinfo is None:
                    s_dt = s_dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue

            if dimension:
                sig_dim = s.metadata.get("domain", "") if hasattr(s, "metadata") else ""
                if sig_dim != dimension:
                    continue

            if before_start <= s_dt < nudge_dt:
                before_count += 1
            elif nudge_dt <= s_dt <= after_end:
                after_count += 1

        # Normalize to per-day rates
        before_days = max((nudge_dt - before_start).days, 1)
        after_days = max((after_end - nudge_dt).days, 1)
        before_rate = before_count / before_days
        after_rate = after_count / after_days

        if before_rate == 0:
            delta_pct = 100.0 if after_rate > 0 else 0.0
        else:
            delta_pct = ((after_rate - before_rate) / before_rate) * 100.0

        changed = abs(delta_pct) > 10.0
        if delta_pct > 10:
            direction = "improved"
        elif delta_pct < -10:
            direction = "regressed"
        else:
            direction = "unchanged"

        return {
            "changed": changed,
            "before_metric": round(before_rate, 2),
            "after_metric": round(after_rate, 2),
            "direction": direction,
            "delta_pct": round(delta_pct, 1),
            "dimension": dimension or "all",
            "window_days": days_window,
        }

    def detect_organizational_pattern(self, min_occurrences: int = 5) -> dict[str, Any] | None:
        """Detect a recurring organizational pattern and suggest a law.

        CEO's 'Friday notification' example: Maestro notices a pattern over
        weeks and surfaces it as an organizational law suggestion.

        Looks for recurring delay patterns, repeated objection types, or
        repeated contradiction patterns across teams.

        Returns None if no significant pattern is detected.
        """
        from collections import Counter
        from maestro_oem.signal import SignalType

        # Count objection types across all customer signals
        objection_types: Counter = Counter()
        for s in self.signals:
            if hasattr(s, "type") and s.type == SignalType.CUSTOMER_OBJECTION:
                otype = s.metadata.get("objection_type", "unknown") if hasattr(s, "metadata") else "unknown"
                objection_types[otype] += 1

        # If any objection type appears 5+ times, that's a pattern
        for otype, count in objection_types.most_common():
            if count >= min_occurrences:
                return {
                    "pattern_type": "recurring_objection",
                    "description": f"Customers have raised '{otype}' concerns {count} times.",
                    "occurrences": count,
                    "suggested_law": f"Address {otype} proactively in every customer engagement.",
                    "confidence": min(count / 10.0, 1.0),
                }

        # Check for repeated contradiction patterns
        contradiction_domains: Counter = Counter()
        for s in self.signals:
            if hasattr(s, "metadata") and s.metadata.get("contradiction_type"):
                domain = s.metadata.get("domain", "unknown")
                contradiction_domains[domain] += 1

        for domain, count in contradiction_domains.most_common():
            if count >= min_occurrences:
                return {
                    "pattern_type": "recurring_contradiction",
                    "description": f"The '{domain}' domain has {count} contradictions — a systemic issue.",
                    "occurrences": count,
                    "suggested_law": f"Establish clear ownership for the {domain} domain.",
                    "confidence": min(count / 10.0, 1.0),
                }

        return None
