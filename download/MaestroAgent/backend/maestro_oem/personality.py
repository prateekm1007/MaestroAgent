"""
Organizational Personality — V3 Law 6: Organizations evolve; infer personality.

Infer 6 dimensions from behavior (never survey):
  - decision_velocity: how fast the org makes decisions
  - risk_appetite: how much risk the org tolerates
  - knowledge_mobility: how easily knowledge crosses team boundaries
  - meeting_dependency: how much the org relies on meetings vs async
  - review_discipline: how consistently the org reviews work
  - learning_velocity: how fast the org learns from outcomes

Each dimension is 0.0-1.0 with a human label + evidence_count + basis
string referencing real model data.

API: GET /api/oem/personality
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class PersonalityEngine:
    """Infer organizational personality from behavioral signals.

    No surveys. No forms. Pure inference from the OEM's observed data:
    signal types, actor distributions, decision patterns, knowledge graph
    structure, and learning outcomes.
    """

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def infer(self) -> dict[str, Any]:
        """Infer all 6 personality dimensions.

        Returns:
            {
                "dimensions": {
                    "decision_velocity": {"score": 0.7, "label": "moderate", "evidence_count": N, "basis": "..."},
                    ...
                },
                "summary": "Your organization decides quickly, tolerates moderate risk, and learns steadily.",
                "inferred_from": "behavioral signals (no surveys)"
            }
        """
        dims = {
            "decision_velocity": self._infer_decision_velocity(),
            "risk_appetite": self._infer_risk_appetite(),
            "knowledge_mobility": self._infer_knowledge_mobility(),
            "meeting_dependency": self._infer_meeting_dependency(),
            "review_discipline": self._infer_review_discipline(),
            "learning_velocity": self._infer_learning_velocity(),
        }

        # Synthesize a one-line summary
        parts = []
        dv = dims["decision_velocity"]["label"]
        ra = dims["risk_appetite"]["label"]
        lv = dims["learning_velocity"]["label"]
        parts.append(f"decides {dv}")
        parts.append(f"tolerates {ra} risk")
        parts.append(f"learns {lv}")
        summary = f"Your organization {parts[0]}, {parts[1]}, and {parts[2]}."

        return {
            "dimensions": dims,
            "summary": summary,
            "inferred_from": "behavioral signals (no surveys)",
        }

    def _infer_decision_velocity(self) -> dict[str, Any]:
        """How fast does the org make decisions? Based on issue transition times."""
        # Count ISSUE_TRANSITIONED signals as a proxy for decision flow
        from maestro_oem.signal import SignalType
        transitions = [s for s in self.signals if s.type == SignalType.ISSUE_TRANSITIONED]
        count = len(transitions)

        if count == 0:
            score = 0.5
            label = "moderate"
            basis = "no issue-transition data available"
        elif count > 20:
            score = 0.8
            label = "quickly"
            basis = f"{count} issue transitions observed — active decision flow"
        elif count > 5:
            score = 0.6
            label = "at a moderate pace"
            basis = f"{count} issue transitions — steady but not rapid"
        else:
            score = 0.3
            label = "slowly"
            basis = f"only {count} issue transitions — decisions appear bottlenecked"

        return {"value": round(score, 2), "score": round(score, 2), "label": label, "evidence_count": count, "basis": basis}

    def _infer_risk_appetite(self) -> dict[str, Any]:
        """How much risk does the org tolerate? Based on PR merge patterns."""
        from maestro_oem.signal import SignalType
        merged = [s for s in self.signals if s.type == SignalType.PR_MERGED]
        opened = [s for s in self.signals if s.type == SignalType.PR_OPENED]
        count = len(merged) + len(opened)

        if count == 0:
            score = 0.5
            label = "moderate"
            basis = "no PR data available"
        else:
            ratio = len(merged) / max(count, 1)
            if ratio > 0.7:
                score = 0.8
                label = "high"
                basis = f"{len(merged)} of {count} PRs merged — fast iteration suggests high risk tolerance"
            elif ratio > 0.4:
                score = 0.5
                label = "moderate"
                basis = f"{len(merged)} of {count} PRs merged — balanced approach"
            else:
                score = 0.3
                label = "low"
                basis = f"{len(merged)} of {count} PRs merged — cautious approach"

        return {"value": round(score, 2), "score": round(score, 2), "label": label, "evidence_count": count, "basis": basis}

    def _infer_knowledge_mobility(self) -> dict[str, Any]:
        """How easily does knowledge cross team boundaries?"""
        try:
            kg = self.model.knowledge
            # Count domains held by >1 person (shared knowledge)
            shared = sum(1 for holders in kg.domain_holders.values() if len(holders) > 1)
            total = len(kg.domain_holders)
            count = total
        except Exception:
            shared = 0
            total = 0
            count = 0

        if total == 0:
            score = 0.5
            label = "moderate"
            basis = "no knowledge domain data available"
        else:
            ratio = shared / total
            if ratio > 0.5:
                score = 0.8
                label = "easily"
                basis = f"{shared} of {total} knowledge domains are shared across people"
            elif ratio > 0.2:
                score = 0.5
                label = "with some friction"
                basis = f"{shared} of {total} domains are shared — some silos exist"
            else:
                score = 0.2
                label = "with difficulty"
                basis = f"only {shared} of {total} domains are shared — knowledge is siloed"

        return {"value": round(score, 2), "score": round(score, 2), "label": label, "evidence_count": count, "basis": basis}

    def _infer_meeting_dependency(self) -> dict[str, Any]:
        """How much does the org rely on meetings vs async?"""
        from maestro_oem.signal import SignalType
        messages = [s for s in self.signals if s.type in (SignalType.MESSAGE_SENT, SignalType.THREAD_STARTED)]
        count = len(messages)

        if count == 0:
            score = 0.5
            label = "moderate"
            basis = "no communication data available"
        elif count > 30:
            score = 0.7
            label = "heavily"
            basis = f"{count} messages/threads — high communication volume suggests meeting dependency"
        elif count > 10:
            score = 0.5
            label = "moderately"
            basis = f"{count} messages/threads — balanced communication"
        else:
            score = 0.3
            label = "lightly"
            basis = f"{count} messages/threads — async-first culture"

        return {"value": round(score, 2), "score": round(score, 2), "label": label, "evidence_count": count, "basis": basis}

    def _infer_review_discipline(self) -> dict[str, Any]:
        """How consistently does the org review work?"""
        from maestro_oem.signal import SignalType
        reviews = [s for s in self.signals if s.type == SignalType.PR_REVIEWED]
        opened = [s for s in self.signals if s.type == SignalType.PR_OPENED]
        count = len(reviews)

        if len(opened) == 0:
            score = 0.5
            label = "moderate"
            basis = "no PR data available"
        else:
            ratio = len(reviews) / len(opened)
            if ratio > 0.8:
                score = 0.9
                label = "rigorously"
                basis = f"{len(reviews)} reviews for {len(opened)} PRs — strong review culture"
            elif ratio > 0.4:
                score = 0.6
                label = "consistently"
                basis = f"{len(reviews)} reviews for {len(opened)} PRs — adequate review"
            else:
                score = 0.3
                label = "inconsistently"
                basis = f"{len(reviews)} reviews for {len(opened)} PRs — review gaps"

        return {"value": round(score, 2), "score": round(score, 2), "label": label, "evidence_count": count, "basis": basis}

    def _infer_learning_velocity(self) -> dict[str, Any]:
        """How fast does the org learn from outcomes?"""
        try:
            laws_count = len(self.model.laws)
            validated = sum(1 for l in self.model.laws.values() if l.status and l.status.value == "validated")
            count = laws_count
        except Exception:
            laws_count = 0
            validated = 0
            count = 0

        if laws_count == 0:
            score = 0.3
            label = "slowly"
            basis = "no patterns inferred yet — organization is still gathering experience"
        else:
            ratio = validated / laws_count
            if ratio > 0.5:
                score = 0.8
                label = "quickly"
                basis = f"{validated} of {laws_count} patterns validated — fast learning"
            elif ratio > 0.2:
                score = 0.6
                label = "steadily"
                basis = f"{validated} of {laws_count} patterns validated — learning in progress"
            else:
                score = 0.4
                label = "slowly"
                basis = f"{validated} of {laws_count} patterns validated — early stage"

        return {"value": round(score, 2), "score": round(score, 2), "label": label, "evidence_count": count, "basis": basis}
