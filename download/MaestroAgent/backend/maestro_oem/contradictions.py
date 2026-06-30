"""
Organizational Contradictions — detect gaps between stated beliefs and observed behavior.

The OEM tracks what the organization says (stated beliefs from assumptions,
hypotheses, laws) and what the organization does (observed behavior from
signals, patterns, outcomes). When these diverge, that's a contradiction.

Types of contradictions:
  - belief_vs_behavior: "We believe X, but our actions show Y"
    Example: Law says "postmortems require owners" but 60% of postmortems
    have no owner assigned.
  - stated_vs_observed: "We assume X takes 3 days" but the data shows 8 days
  - intent_vs_outcome: "Our intent was to reduce cycle time" but cycle time increased
  - team_vs_team: "Engineering believes the API is stable" but Support says it's fragile

Product law: eliminates THINKING ("is our belief still valid?") by
auto-detecting when beliefs and reality diverge.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class Contradiction:
    """A detected gap between stated beliefs and observed behavior."""

    def __init__(
        self,
        contradiction_id: str,
        contradiction_type: str,
        title: str,
        description: str,
        stated_belief: str,
        observed_behavior: str,
        evidence: list[dict[str, Any]],
        severity: str = "medium",  # low | medium | high | critical
        detected_at: datetime | None = None,
        status: str = "open",  # open | acknowledged | resolved
        linked_intent_id: str = "",
        linked_assumption_id: str = "",
    ) -> None:
        self.contradiction_id = contradiction_id
        self.contradiction_type = contradiction_type
        self.title = title
        self.description = description
        self.stated_belief = stated_belief
        self.observed_behavior = observed_behavior
        self.evidence = evidence
        self.severity = severity
        self.detected_at = detected_at or datetime.now(timezone.utc)
        self.status = status
        self.linked_intent_id = linked_intent_id
        self.linked_assumption_id = linked_assumption_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "contradiction_id": self.contradiction_id,
            "contradiction_type": self.contradiction_type,
            "title": self.title,
            "description": self.description,
            "stated_belief": self.stated_belief,
            "observed_behavior": self.observed_behavior,
            "evidence": self.evidence,
            "severity": self.severity,
            "detected_at": self.detected_at.isoformat(),
            "status": self.status,
            "linked_intent_id": self.linked_intent_id,
            "linked_assumption_id": self.linked_assumption_id,
        }


class ContradictionDetector:
    """Detects contradictions between stated beliefs and observed behavior.

    Usage:
        detector = ContradictionDetector(model, signals, assumption_graph)
        contradictions = detector.detect_all()
    """

    def __init__(self, model: Any, signals: list, assumption_graph=None) -> None:
        self.model = model
        self.signals = signals
        self.assumption_graph = assumption_graph
        self._contradictions: list[Contradiction] = []

    def detect_all(self) -> list[dict[str, Any]]:
        """Run all contradiction detectors."""
        self._contradictions = []
        self._detect_law_violations()
        self._detect_assumption_violations()
        self._detect_commitment_contradictions()
        self._detect_bottleneck_contradictions()
        return [c.to_dict() for c in self._contradictions]

    def _detect_law_violations(self) -> None:
        """Laws that are stated but violated by behavior."""
        from maestro_oem.learning_object import LearningObjectType

        for law in self.model.laws.values():
            # Laws with failed runtimes contradict their own statement
            if law.failed_runtimes > 0 and law.validated_runtimes > 0:
                self._contradictions.append(Contradiction(
                    contradiction_id=f"contr-{uuid4().hex[:12]}",
                    contradiction_type="belief_vs_behavior",
                    title=f"Law {law.code} contradicted by behavior",
                    description=f"'{law.statement[:60]}' has {law.failed_runtimes} failures vs {law.validated_runtimes} validations.",
                    stated_belief=law.statement[:100],
                    observed_behavior=f"{law.failed_runtimes} counter-examples detected",
                    evidence=[{
                        "type": "law",
                        "code": law.code,
                        "validated": law.validated_runtimes,
                        "failed": law.failed_runtimes,
                    }],
                    severity="high" if law.failed_runtimes > law.validated_runtimes else "medium",
                ))

    def _detect_assumption_violations(self) -> None:
        """Assumptions that were invalidated by signals."""
        if not self.assumption_graph:
            return

        for assumption in self.assumption_graph.list_assumptions():
            if assumption["status"] == "invalidated":
                self._contradictions.append(Contradiction(
                    contradiction_id=f"contr-{uuid4().hex[:12]}",
                    contradiction_type="stated_vs_observed",
                    title=f"Assumption invalidated: '{assumption['statement'][:50]}'",
                    description=f"The assumption '{assumption['statement'][:60]}' was invalidated by evidence.",
                    stated_belief=assumption["statement"],
                    observed_behavior=assumption.get("impact", "Assumption was proven wrong by organizational signals."),
                    evidence=assumption.get("evidence", []),
                    severity="high",
                    linked_assumption_id=assumption["assumption_id"],
                ))

    def _detect_commitment_contradictions(self) -> None:
        """Organizations that say they'll do X but don't."""
        from maestro_oem.signal import SignalType

        broken = [s for s in self.signals if s.type == SignalType.CUSTOMER_COMMITMENT_BROKEN]
        kept = [s for s in self.signals if s.type == SignalType.CUSTOMER_COMMITMENT_KEPT]

        if len(broken) > len(kept) and len(broken) > 0:
            self._contradictions.append(Contradiction(
                contradiction_id=f"contr-{uuid4().hex[:12]}",
                contradiction_type="intent_vs_outcome",
                title=f"Commitment integrity gap: {len(broken)} broken vs {len(kept)} kept",
                description=f"The organization breaks more commitments than it keeps ({len(broken)} broken, {len(kept)} kept).",
                stated_belief="We honor our commitments to customers",
                observed_behavior=f"{len(broken)} commitments broken, {len(kept)} kept",
                evidence=[{
                    "type": "signal_counts",
                    "broken": len(broken),
                    "kept": len(kept),
                }],
                severity="high",
            ))

    def _detect_bottleneck_contradictions(self) -> None:
        """Organizations that say they value speed but have growing bottlenecks."""
        try:
            bottlenecks = self.model.approvals.get_bottlenecks(min_count=3)
            if len(bottlenecks) > 2:
                self._contradictions.append(Contradiction(
                    contradiction_id=f"contr-{uuid4().hex[:12]}",
                    contradiction_type="belief_vs_behavior",
                    title=f"Speed culture contradicted by {len(bottlenecks)} bottlenecks",
                    description=f"The organization has {len(bottlenecks)} approval bottlenecks, contradicting a culture of fast execution.",
                    stated_belief="We value fast, autonomous execution",
                    observed_behavior=f"{len(bottlenecks)} approval gates with 3+ items each",
                    evidence=[{
                        "type": "bottleneck",
                        "gate": b["gate"],
                        "items_gated": b["items_gated"],
                    } for b in bottlenecks[:5]],
                    severity="medium",
                ))
        except Exception:
            pass

    def list_contradictions(self, status: str | None = None) -> list[dict[str, Any]]:
        if status:
            return [c.to_dict() for c in self._contradictions if c.status == status]
        return [c.to_dict() for c in self._contradictions]

    def acknowledge(self, contradiction_id: str) -> bool:
        for c in self._contradictions:
            if c.contradiction_id == contradiction_id:
                c.status = "acknowledged"
                return True
        return False
