"""
V6 Spec #5 — Organizational DNA.

"This is what YOUR organization would do at its best."

7 chromosomes that evolve over time and FILTER recommendations:
  - decision_style: how the org makes decisions (consensus | top-down | data-driven | intuitive)
  - risk_appetite: how much risk the org tolerates (cautious | balanced | aggressive)
  - learning_velocity: how fast the org learns (slow | steady | rapid)
  - communication_style: how the org communicates (formal | informal | async-first)
  - conflict_style: how the org handles disagreement (avoidant | direct | structured)
  - innovation_style: how the org innovates (incremental | experimental | disruptive)
  - execution_style: how the org executes (methodical | agile | chaotic)

Each chromosome has: value (0.0-1.0), label, evidence_count, basis, narrative.
The DNA filters recommendations via wisdom.py — recommendations that don't
match the org's DNA are flagged as "against your nature."

API: GET /api/oem/dna
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class OrganizationalDNA:
    """Infer the organization's DNA from behavioral signals.

    DNA is not culture (what people say). DNA is character (what the org
    consistently chooses under pressure). The DNA is inferred from behavior,
    never surveyed.
    """

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def sequence(self) -> dict[str, Any]:
        """Sequence the organization's DNA — 7 chromosomes."""
        chromosomes = {
            "decision_style": self._decision_style(),
            "risk_appetite": self._risk_appetite(),
            "learning_velocity": self._learning_velocity(),
            "communication_style": self._communication_style(),
            "conflict_style": self._conflict_style(),
            "innovation_style": self._innovation_style(),
            "execution_style": self._execution_style(),
        }

        # Generate a summary
        labels = [c["label"] for c in chromosomes.values()]
        summary = f"Your organization is {', '.join(labels[:3])}, and {', '.join(labels[3:])}."

        return {
            "chromosomes": chromosomes,
            "summary": summary,
            "chromosome_count": len(chromosomes),
        }

    def _decision_style(self) -> dict[str, Any]:
        """How does the org make decisions?"""
        from collections import Counter
        from maestro_oem.signal import SignalType
        decisions = [s for s in self.signals if s.type in (SignalType.DECISION_SIGNAL, SignalType.AGREEMENT, SignalType.CONFLICT)]
        count = len(decisions)
        agreements = sum(1 for s in decisions if s.type == SignalType.AGREEMENT)
        conflicts = sum(1 for s in decisions if s.type == SignalType.CONFLICT)

        if count == 0:
            return {"value": 0.5, "label": "unknown", "evidence_count": 0, "basis": "no decision signals", "narrative": "Not enough data to infer decision style."}

        agreement_ratio = agreements / max(count, 1)
        if agreement_ratio > 0.6:
            return {"value": 0.8, "label": "consensus-driven", "evidence_count": count, "basis": f"{agreements} agreements vs {conflicts} conflicts", "narrative": "Your organization prefers consensus. Decisions are made collaboratively."}
        elif agreement_ratio > 0.3:
            return {"value": 0.5, "label": "balanced", "evidence_count": count, "basis": f"{agreements} agreements, {conflicts} conflicts", "narrative": "Your organization balances consensus with direct disagreement."}
        else:
            return {"value": 0.3, "label": "conflict-driven", "evidence_count": count, "basis": f"{conflicts} conflicts vs {agreements} agreements", "narrative": "Your organization tends to resolve decisions through conflict rather than consensus."}

    def _risk_appetite(self) -> dict[str, Any]:
        from maestro_oem.signal import SignalType
        merged = sum(1 for s in self.signals if s.type == SignalType.PR_MERGED)
        opened = sum(1 for s in self.signals if s.type == SignalType.PR_OPENED)
        count = merged + opened

        if count == 0:
            return {"value": 0.5, "label": "unknown", "evidence_count": 0, "basis": "no PR data", "narrative": "Not enough data to infer risk appetite."}

        ratio = merged / max(count, 1)
        if ratio > 0.7:
            return {"value": 0.8, "label": "aggressive", "evidence_count": count, "basis": f"{merged}/{count} PRs merged", "narrative": "Your organization ships fast and tolerates risk."}
        elif ratio > 0.4:
            return {"value": 0.5, "label": "balanced", "evidence_count": count, "basis": f"{merged}/{count} PRs merged", "narrative": "Your organization balances speed with caution."}
        else:
            return {"value": 0.3, "label": "cautious", "evidence_count": count, "basis": f"{merged}/{count} PRs merged", "narrative": "Your organization is cautious — it prefers certainty over speed."}

    def _learning_velocity(self) -> dict[str, Any]:
        try:
            laws = list(self.model.laws.values())
            total = len(laws)
            validated = sum(1 for l in laws if l.status and l.status.value == "validated")
        except Exception:
            total = 0
            validated = 0

        if total == 0:
            return {"value": 0.3, "label": "early", "evidence_count": 0, "basis": "no patterns", "narrative": "Still gathering experience."}
        ratio = validated / total
        if ratio > 0.5:
            return {"value": 0.8, "label": "rapid learner", "evidence_count": total, "basis": f"{validated}/{total} patterns validated", "narrative": "Your organization learns quickly from experience."}
        elif ratio > 0.2:
            return {"value": 0.5, "label": "steady learner", "evidence_count": total, "basis": f"{validated}/{total} validated", "narrative": "Your organization learns steadily."}
        else:
            return {"value": 0.3, "label": "slow learner", "evidence_count": total, "basis": f"{validated}/{total} validated", "narrative": "Your organization is still building its pattern library."}

    def _communication_style(self) -> dict[str, Any]:
        from maestro_oem.signal import SignalType
        messages = sum(1 for s in self.signals if s.type in (SignalType.MESSAGE_SENT, SignalType.THREAD_STARTED))
        docs = sum(1 for s in self.signals if s.type in (SignalType.PAGE_CREATED, SignalType.PAGE_EDITED))
        count = messages + docs

        if count == 0:
            return {"value": 0.5, "label": "unknown", "evidence_count": 0, "basis": "no communication data", "narrative": "Not enough data."}

        doc_ratio = docs / max(count, 1)
        if doc_ratio > 0.4:
            return {"value": 0.7, "label": "documentation-first", "evidence_count": count, "basis": f"{docs} docs, {messages} messages", "narrative": "Your organization prefers documented communication over real-time chat."}
        elif messages > 20:
            return {"value": 0.6, "label": "async-first", "evidence_count": count, "basis": f"{messages} messages", "narrative": "Your organization communicates primarily through async messages."}
        else:
            return {"value": 0.4, "label": "informal", "evidence_count": count, "basis": f"{messages} messages, {docs} docs", "narrative": "Your organization communicates informally."}

    def _conflict_style(self) -> dict[str, Any]:
        from maestro_oem.signal import SignalType
        conflicts = sum(1 for s in self.signals if s.type == SignalType.CONFLICT)
        agreements = sum(1 for s in self.signals if s.type == SignalType.AGREEMENT)
        count = conflicts + agreements

        if count == 0:
            return {"value": 0.5, "label": "unknown", "evidence_count": 0, "basis": "no conflict data", "narrative": "Not enough data."}

        conflict_ratio = conflicts / max(count, 1)
        if conflict_ratio > 0.5:
            return {"value": 0.7, "label": "direct", "evidence_count": count, "basis": f"{conflicts} conflicts", "narrative": "Your organization handles disagreement directly and openly."}
        elif conflict_ratio > 0.2:
            return {"value": 0.5, "label": "structured", "evidence_count": count, "basis": f"{conflicts} conflicts, {agreements} agreements", "narrative": "Your organization handles conflict through structured processes."}
        else:
            return {"value": 0.3, "label": "avoidant", "evidence_count": count, "basis": f"{agreements} agreements, {conflicts} conflicts", "narrative": "Your organization tends to avoid conflict."}

    def _innovation_style(self) -> dict[str, Any]:
        from maestro_oem.signal import SignalType
        new_prs = sum(1 for s in self.signals if s.type == SignalType.PR_OPENED)
        reviews = sum(1 for s in self.signals if s.type == SignalType.PR_REVIEWED)
        count = new_prs + reviews

        if count == 0:
            return {"value": 0.5, "label": "unknown", "evidence_count": 0, "basis": "no innovation data", "narrative": "Not enough data."}

        if new_prs > 15:
            return {"value": 0.8, "label": "experimental", "evidence_count": count, "basis": f"{new_prs} new PRs", "narrative": "Your organization experiments frequently."}
        elif new_prs > 5:
            return {"value": 0.5, "label": "incremental", "evidence_count": count, "basis": f"{new_prs} PRs", "narrative": "Your organization innovates incrementally."}
        else:
            return {"value": 0.3, "label": "conservative", "evidence_count": count, "basis": f"{new_prs} PRs", "narrative": "Your organization is conservative in its innovation."}

    def _execution_style(self) -> dict[str, Any]:
        from maestro_oem.signal import SignalType
        transitions = sum(1 for s in self.signals if s.type == SignalType.ISSUE_TRANSITIONED)
        blocked = sum(1 for s in self.signals if s.type == SignalType.ISSUE_TRANSITIONED and "block" in str(s.metadata.get("text", "")).lower())
        count = transitions + blocked

        if count == 0:
            return {"value": 0.5, "label": "unknown", "evidence_count": 0, "basis": "no execution data", "narrative": "Not enough data."}

        block_ratio = blocked / max(count, 1)
        if block_ratio < 0.1:
            return {"value": 0.8, "label": "agile", "evidence_count": count, "basis": f"{transitions} transitions, {blocked} blocked", "narrative": "Your organization executes smoothly with few blockages."}
        elif block_ratio < 0.3:
            return {"value": 0.5, "label": "methodical", "evidence_count": count, "basis": f"{transitions} transitions, {blocked} blocked", "narrative": "Your organization executes methodically with occasional blockages."}
        else:
            return {"value": 0.3, "label": "bottlenecked", "evidence_count": count, "basis": f"{blocked} blocked", "narrative": "Your organization struggles with execution bottlenecks."}
