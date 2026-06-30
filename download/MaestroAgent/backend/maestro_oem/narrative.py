"""Organizational Narrative — tell the company story, not show a dashboard.

Every morning, Maestro should tell the company's story:

  Yesterday
  Engineering accelerated.
  Legal slowed.
  Knowledge moved from Platform to Security.
  Stripe became healthier.
  Microsoft became riskier.
  Two execution laws strengthened.
  One organizational assumption was proven wrong.

Executives think in narratives, not dashboards. This engine compresses
the organization's recent activity into a human-readable story.

The narrative is NOT a summary of metrics. It's a causal story:
  - What changed
  - Why it changed
  - What it means
  - What to watch for

It covers:
  - Execution changes (velocity, incidents, releases)
  - Knowledge shifts (who gained/lost expertise)
  - Customer movements (renewals, churns, drift)
  - Law evolution (strengthened, challenged, invalidated)
  - Prediction outcomes (correct, incorrect)
  - Organizational pulse changes
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


class NarrativeEngine:
    """Generates a daily organizational narrative.

    Usage:
        engine = NarrativeEngine(model, signals)
        story = engine.daily()
        # story = {title, body, highlights, watch_for, date}
    """

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def daily(self) -> dict[str, Any]:
        """Generate the daily organizational narrative.

        Returns:
          - date: the date of the narrative
          - title: one-line headline
          - body: multi-paragraph story
          - highlights: key events as bullet points
          - watch_for: what to watch for today
          - pulse_summary: organizational pulse state
        """
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)
        yesterday_signals = [s for s in self.signals if s.timestamp > yesterday]

        highlights = []
        highlights.extend(self._execution_highlights(yesterday_signals))
        highlights.extend(self._knowledge_highlights(yesterday_signals))
        highlights.extend(self._customer_highlights(yesterday_signals))
        highlights.extend(self._law_highlights())
        highlights.extend(self._prediction_highlights())

        body = self._compose_body(highlights)
        title = self._compose_title(highlights)
        watch_for = self._watch_for_today()

        return {
            "date": now.date().isoformat(),
            "generated_at": now.isoformat(),
            "title": title,
            "body": body,
            "highlights": highlights,
            "watch_for": watch_for,
            "signals_analyzed": len(yesterday_signals),
        }

    def _execution_highlights(self, recent: list) -> list[dict[str, Any]]:
        from maestro_oem.signal import SignalType
        highlights = []

        merges = sum(1 for s in recent if s.type == SignalType.PR_MERGED)
        incidents = sum(1 for s in recent if s.type == SignalType.INCIDENT
                        or (s.type == SignalType.ISSUE_CREATED
                            and s.metadata.get("priority", "").upper() in ("P1", "P0")))
        releases = sum(1 for s in recent if s.type == SignalType.RELEASE
                       or s.type == SignalType.PR_MERGED)

        if merges > 5:
            highlights.append({
                "category": "execution",
                "text": f"Engineering shipped {merges} merges — execution accelerated.",
                "impact": "positive",
            })
        elif merges == 0 and recent:
            highlights.append({
                "category": "execution",
                "text": "No merges yesterday — engineering may be blocked.",
                "impact": "warning",
            })

        if incidents > 0:
            highlights.append({
                "category": "execution",
                "text": f"{incidents} P1 incident(s) occurred.",
                "impact": "negative",
            })

        return highlights

    def _knowledge_highlights(self, recent: list) -> list[dict[str, Any]]:
        from maestro_oem.signal import SignalType
        highlights = []

        # Pages created = knowledge documented
        pages = sum(1 for s in recent if s.type == SignalType.PAGE_CREATED)
        if pages > 0:
            highlights.append({
                "category": "knowledge",
                "text": f"{pages} documentation page(s) created — knowledge is being captured.",
                "impact": "positive",
            })

        # Postmortems without owners = knowledge death
        postmortems = [s for s in recent if s.type == SignalType.POSTMORTEM_CREATED]
        for pm in postmortems:
            if not pm.metadata.get("has_owner", False):
                highlights.append({
                    "category": "knowledge",
                    "text": f"Postmortem created without an owner — lesson may not be acted on.",
                    "impact": "warning",
                })

        # RFCs = formal proposals
        rfcs = sum(1 for s in recent if s.type == SignalType.RFC_CREATED)
        if rfcs > 0:
            highlights.append({
                "category": "knowledge",
                "text": f"{rfcs} RFC(s) proposed — formal decision-making in progress.",
                "impact": "neutral",
            })

        return highlights

    def _customer_highlights(self, recent: list) -> list[dict[str, Any]]:
        from maestro_oem.signal import SignalType
        highlights = []

        renewed = sum(1 for s in recent if s.type == SignalType.CUSTOMER_CONTRACT_RENEWED)
        churned = sum(1 for s in recent if s.type == SignalType.CUSTOMER_CONTRACT_CHURNED)
        drift = sum(1 for s in recent if s.type == SignalType.CUSTOMER_CHAMPION_QUIET)
        objections = sum(1 for s in recent if s.type == SignalType.CUSTOMER_OBJECTION)

        if renewed > 0:
            customers = [s.metadata.get("customer", "") for s in recent
                        if s.type == SignalType.CUSTOMER_CONTRACT_RENEWED]
            highlights.append({
                "category": "customer",
                "text": f"{', '.join(customers)} renewed — relationship health confirmed.",
                "impact": "positive",
            })

        if churned > 0:
            customers = [s.metadata.get("customer", "") for s in recent
                        if s.type == SignalType.CUSTOMER_CONTRACT_CHURNED]
            highlights.append({
                "category": "customer",
                "text": f"{', '.join(customers)} churned — pattern should be analyzed.",
                "impact": "negative",
            })

        if drift > 0:
            customers = [s.metadata.get("customer", "") for s in recent
                        if s.type == SignalType.CUSTOMER_CHAMPION_QUIET]
            highlights.append({
                "category": "customer",
                "text": f"Champion went quiet at {', '.join(set(customers))} — relationship drift risk.",
                "impact": "warning",
            })

        if objections > 0:
            highlights.append({
                "category": "customer",
                "text": f"{objections} customer objection(s) raised — needs attention.",
                "impact": "warning",
            })

        return highlights

    def _law_highlights(self) -> list[dict[str, Any]]:
        highlights = []

        for law in self.model.laws.values():
            if law.validated_runtimes >= 5 and law.failed_runtimes == 0:
                highlights.append({
                    "category": "law",
                    "text": f"Law {law.code} strengthened — validated {law.validated_runtimes} times with 0 failures.",
                    "impact": "positive",
                })
            if law.failed_runtimes > 0 and hasattr(law, 'status') and law.status.value in ("stressed", "invalidated"):
                highlights.append({
                    "category": "law",
                    "text": f"Law {law.code} {law.status.value} — {law.failed_runtimes} failures detected.",
                    "impact": "warning" if law.status.value == "stressed" else "negative",
                })

        return highlights

    def _prediction_highlights(self) -> list[dict[str, Any]]:
        highlights = []
        try:
            import os
            from pathlib import Path
            from maestro_oem.prediction_lifecycle import PredictionRecorder

            db_path = os.environ.get(
                "MAESTRO_LEARNING_DB",
                get_db_url_for_learning(),
            )
            recorder = PredictionRecorder(db_path)
            preds = recorder.list_predictions(limit=10)

            correct = sum(1 for p in preds if p.get("status") == "correct")
            incorrect = sum(1 for p in preds if p.get("status") == "incorrect")

            if correct > 0:
                highlights.append({
                    "category": "learning",
                    "text": f"{correct} prediction(s) resolved as correct — Maestro is well-calibrated for these patterns.",
                    "impact": "positive",
                })
            if incorrect > 0:
                highlights.append({
                    "category": "learning",
                    "text": f"{incorrect} prediction(s) resolved as incorrect — calibration has adjusted.",
                    "impact": "neutral",
                })
        except Exception:
            pass

        return highlights

    def _compose_title(self, highlights: list) -> str:
        """Compose a one-line headline from the highlights."""
        if not highlights:
            return "The organization was quiet yesterday."

        positive = [h for h in highlights if h["impact"] == "positive"]
        negative = [h for h in highlights if h["impact"] in ("negative", "warning")]

        if positive and not negative:
            return "The organization had a strong day."
        if negative and not positive:
            return "The organization faced headwinds."
        if positive and negative:
            return "The organization had a mixed day — progress and challenges."

        return "The organization was active."

    def _compose_body(self, highlights: list) -> str:
        """Compose a multi-paragraph narrative from the highlights."""
        if not highlights:
            return (
                "No significant events were recorded yesterday. "
                "The organization may be between cycles, or signal ingestion may be delayed. "
                "Check that all providers are connected."
            )

        paragraphs = []
        by_category: dict[str, list] = {}
        for h in highlights:
            by_category.setdefault(h["category"], []).append(h["text"])

        if "execution" in by_category:
            paragraphs.append("Execution: " + " ".join(by_category["execution"]))

        if "knowledge" in by_category:
            paragraphs.append("Knowledge: " + " ".join(by_category["knowledge"]))

        if "customer" in by_category:
            paragraphs.append("Customer relationships: " + " ".join(by_category["customer"]))

        if "law" in by_category:
            paragraphs.append("Organizational laws: " + " ".join(by_category["law"]))

        if "learning" in by_category:
            paragraphs.append("Learning loop: " + " ".join(by_category["learning"]))

        return "\n\n".join(paragraphs)

    def _watch_for_today(self) -> list[str]:
        """What to watch for today."""
        watch = []

        # Customers with drift signals
        from maestro_oem.signal import SignalType
        drift_customers = set()
        for s in self.signals:
            if s.type == SignalType.CUSTOMER_CHAMPION_QUIET:
                drift_customers.add(s.metadata.get("customer", ""))
        if drift_customers:
            watch.append(f"Watch: {', '.join(drift_customers)} — champion drift may escalate.")

        # Bottlenecks
        try:
            bottlenecks = self.model.approvals.get_bottlenecks(min_count=3)
            for bn in bottlenecks[:2]:
                watch.append(f"Watch: {bn['gate']} is gating {bn['items_gated']} items — may need intervention.")
        except Exception:
            pass

        # Concentration risks
        try:
            risks = self.model.knowledge.get_concentration_risk()
            for domain in list(risks.keys())[:2]:
                watch.append(f"Watch: {domain} knowledge is concentrated — bus-factor risk.")
        except Exception:
            pass

        if not watch:
            watch.append("No specific risks flagged. The organization is in a steady state.")

        return watch
