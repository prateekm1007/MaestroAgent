"""
Organ #3 — Skepticism: Continuously challenge fossilized beliefs.

"You believe meetings improve alignment. Evidence from the last 90 days:
correlation -0.42. This belief is probably outdated."

Computes fossilization risk from assumption age + accuracy trend +
evidence recency. An assumption that's been held for a long time with
no recent validation is a fossilized belief — it may be wrong but nobody
has checked.

Builds on assumption.py + learning.py.
API: GET /api/oem/skepticism
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class SkepticismEngine:
    """Challenge beliefs the organization holds without evidence.

    Skepticism is not cynicism. It's the discipline of asking "how do we
    know this is still true?" for every belief the organization operates on.
    """

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def challenge(self) -> dict[str, Any]:
        """Find fossilized beliefs and challenge them with evidence."""
        challenges = []

        # 1. Challenge assumptions — find old, unvalidated ones
        challenges.extend(self._challenge_assumptions())

        # 2. Challenge laws — find patterns with declining evidence
        challenges.extend(self._challenge_laws())

        # 3. Challenge organizational habits — find repeated behaviors
        # that may no longer serve the organization
        challenges.extend(self._challenge_habits())

        challenges.sort(key=lambda c: c.get("fossilization_risk", 0), reverse=True)
        challenges = challenges[:5]

        if not challenges:
            summary = "No fossilized beliefs detected. The organization actively validates its assumptions."
        else:
            high_risk = sum(1 for c in challenges if c.get("fossilization_risk", 0) > 0.6)
            summary = f"Maestro is skeptical of {len(challenges)} {'belief' if len(challenges) == 1 else 'beliefs'}. {high_risk} {'is' if high_risk == 1 else 'are'} at high risk of being outdated."

        return {
            "challenges": challenges,
            "summary": summary,
            "fossilized_count": len(challenges),
        }

    def _challenge_assumptions(self) -> list[dict[str, Any]]:
        """Find old assumptions that haven't been validated recently."""
        results = []
        try:
            from maestro_api.routes.oem import _get_assumption_graph
            graph = _get_assumption_graph()
            all_assumptions = graph.list_assumptions()

            for a in all_assumptions[:10]:
                statement = a.get("statement", "")
                status = a.get("status", "open")
                created = a.get("created_at", "")
                supporting = len(a.get("supporting_signals", []))
                contradicting = len(a.get("contradicting_signals", []))

                # Fossilization risk: high if old + no recent evidence
                age_days = 90  # default
                if created:
                    try:
                        created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        age_days = (datetime.now(timezone.utc) - created_dt).days
                    except Exception:
                        pass

                evidence_recency = max(supporting, contradicting)
                fossilization_risk = 0.0
                if age_days > 30 and evidence_recency == 0:
                    fossilization_risk = 0.8
                elif age_days > 60 and supporting == 0:
                    fossilization_risk = 0.6
                elif status == "open" and evidence_recency == 0:
                    fossilization_risk = 0.5

                if fossilization_risk > 0.3 and len(statement) > 10:
                    # Clean truncation: strip quotes, cut at word boundary
                    clean = statement.replace("'", "").replace('"', '')
                    if len(clean) > 80:
                        clean = clean[:80].rsplit(' ', 1)[0]
                    results.append({
                        "belief": clean,
                        "challenge": f"This belief hasn't been tested in {age_days} days. Is it still true?",
                        "fossilization_risk": round(fossilization_risk, 2),
                        "evidence": f"{age_days} days old, {supporting} supporting, {contradicting} contradicting",
                        "type": "unvalidated_assumption",
                    })
        except Exception as e:
            logger.debug("Assumption challenge failed: %s", e)

        return results[:3]

    def _challenge_laws(self) -> list[dict[str, Any]]:
        """Find laws/patterns that may be outdated."""
        results = []
        try:
            for law in list(self.model.laws.values())[:10]:
                if law.status and law.status.value == "stressed":
                    results.append({
                        "belief": f"Pattern: {law.statement[:60].replace(chr(39), '').replace(chr(34), '')}" if law.statement else "Organizational pattern",
                        "challenge": f"This pattern is showing stress — {law.failed_runtimes} of {law.validated_runtimes + law.failed_runtimes} recent outcomes deviated. It may no longer hold.",
                        "fossilization_risk": 0.7,
                        "evidence": f"{law.evidence_count} signals, {law.failed_runtimes} failures",
                        "type": "stressed_pattern",
                    })
                elif law.evidence_count > 10 and law.validated_runtimes == 0:
                    results.append({
                        "belief": f"Pattern: {law.statement[:60]}..." if law.statement else "Organizational pattern",
                        "challenge": f"This pattern has {law.evidence_count} signals but has never been validated. Is it actually true, or just frequently observed?",
                        "fossilization_risk": 0.4,
                        "evidence": f"{law.evidence_count} signals, 0 validations",
                        "type": "unvalidated_pattern",
                    })
        except Exception as e:
            logger.debug("Law challenge failed: %s", e)

        return results[:2]

    def _challenge_habits(self) -> list[dict[str, Any]]:
        """Find organizational habits that may no longer serve the org."""
        results = []
        try:
            from collections import Counter
            # Find the most common signal types — these are habits
            type_counts = Counter(s.type.value if hasattr(s.type, 'value') else str(s.type) for s in self.signals)
            most_common = type_counts.most_common(1)
            if most_common:
                habit_type, count = most_common[0]
                if count > 15:
                    results.append({
                        "belief": f"We need {habit_type.replace('_', ' ')} for everything",
                        "challenge": f"The organization has generated {count} {habit_type.replace('_', ' ')} signals. Is this habit still necessary, or has it become automatic without value?",
                        "fossilization_risk": 0.3,
                        "evidence": f"{count} signals of type {habit_type}",
                        "type": "organizational_habit",
                    })
        except Exception as e:
            logger.debug("Habit challenge failed: %s", e)

        return results[:1]
