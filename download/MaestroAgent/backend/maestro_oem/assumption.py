"""
Assumption Graph — the biggest moat nobody is building.

Every decision is based on assumptions. Nobody stores them. Nobody tracks
which assumptions came true and which bankrupted projects. This is
genuinely novel.

The AssumptionGraph stores assumptions explicitly and inferred, tracks
their validation status, and surfaces "dangerous assumptions" — ones
that are (a) still open, (b) support a high-stakes decision, and (c)
have conflicting evidence.

After 90 days of pilot, the system can say: "47% of our assumptions
were correct. These 3 assumptions cost us the most when they turned
out wrong."

Product law: eliminates REMEMBERING (what did we assume?) and
THINKING (is this assumption still valid?).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class Assumption:
    """An assumption that underpins a decision."""

    def __init__(
        self,
        assumption_id: str,
        statement: str,
        made_by: str = "system",
        made_at: datetime | None = None,
        context: str = "",
        stakes: str = "medium",  # low | medium | high | critical
        status: str = "open",  # open | validated | invalidated | forgotten
        validated_at: datetime | None = None,
        evidence: list[dict[str, Any]] | None = None,
        impact: str = "",
        linked_recommendation_id: str = "",
    ) -> None:
        self.assumption_id = assumption_id
        self.statement = statement
        self.made_by = made_by
        self.made_at = made_at or datetime.now(timezone.utc)
        self.context = context
        self.stakes = stakes
        self.status = status
        self.validated_at = validated_at
        self.evidence = evidence or []
        self.impact = impact
        self.linked_recommendation_id = linked_recommendation_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "assumption_id": self.assumption_id,
            "statement": self.statement,
            "made_by": self.made_by,
            "made_at": self.made_at.isoformat(),
            "context": self.context,
            "stakes": self.stakes,
            "status": self.status,
            "validated_at": self.validated_at.isoformat() if self.validated_at else None,
            "evidence": self.evidence,
            "impact": self.impact,
            "linked_recommendation_id": self.linked_recommendation_id,
        }


class AssumptionGraph:
    """Stores, tracks, and evaluates organizational assumptions.

    Usage:
        graph = AssumptionGraph()
        graph.create("Legal review takes 3 days", made_by="jane@acme.com", context="Q4 launch plan")
        graph.check_against_signals(signals)  # auto-validate/invalidate
        dangerous = graph.get_dangerous_assumptions()
    """

    def __init__(self) -> None:
        self._assumptions: dict[str, Assumption] = {}

    def create(
        self,
        statement: str,
        made_by: str = "system",
        context: str = "",
        stakes: str = "medium",
        linked_recommendation_id: str = "",
        intent_id: str = "",
    ) -> str:
        """Create an explicit assumption linked to an intent.

        Returns the assumption_id.
        """
        assumption_id = f"asmp-{uuid4().hex[:12]}"
        assumption = Assumption(
            assumption_id=assumption_id,
            statement=statement,
            made_by=made_by,
            context=context,
            stakes=stakes,
            linked_recommendation_id=linked_recommendation_id,
        )
        # Store intent_id in evidence as a linking reference
        if intent_id:
            assumption.evidence.append({
                "type": "intent_link",
                "intent_id": intent_id,
                "detail": f"Assumption supports intent {intent_id}",
            })
        self._assumptions[assumption_id] = assumption
        logger.info("Assumption created: %s — '%s' (intent: %s)", assumption_id, statement[:60], intent_id or "none")
        return assumption_id

    def infer_from_recommendations(self, recommendations: list[Any]) -> list[str]:
        """Infer assumptions from OEM recommendations.

        When the OEM says "address bottleneck: X gates Y items," the
        implicit assumption is "removing this gate will improve velocity."
        This method extracts and stores those assumptions.
        """
        inferred = []
        for rec in recommendations:
            title = getattr(rec, "title", str(rec))
            confidence = getattr(rec, "confidence", 0.5)
            rec_id = getattr(rec, "rec_id", "")

            # Infer the assumption from the recommendation
            if "bottleneck" in title.lower():
                stmt = f"Removing the bottleneck described in '{title[:50]}' will improve execution velocity"
                stakes = "high" if confidence > 0.7 else "medium"
            elif "expert" in title.lower():
                stmt = f"Formalizing the expert in '{title[:50]}' will reduce knowledge risk"
                stakes = "medium"
            elif "risk" in title.lower() or "bus-factor" in title.lower():
                stmt = f"The risk described in '{title[:50]}' will materialize if unaddressed"
                stakes = "high"
            elif "customer" in title.lower():
                stmt = f"The customer situation in '{title[:50]}' requires intervention"
                stakes = "high"
            else:
                stmt = f"Acting on '{title[:50]}' will produce the expected outcome"
                stakes = "medium" if confidence > 0.5 else "low"

            assumption_id = self.create(
                statement=stmt,
                made_by="system:inferred",
                context=f"Recommendation: {title[:60]}",
                stakes=stakes,
                linked_recommendation_id=rec_id,
            )
            inferred.append(assumption_id)

        return inferred

    def check_against_signals(self, signals: list) -> dict[str, int]:
        """Check all open assumptions against new signals.

        For each open assumption, look for signals that validate or
        invalidate it. This is the auto-validation loop.

        Returns: {validated: N, invalidated: N, unchanged: N}
        """
        from maestro_oem.signal import SignalType

        validated = 0
        invalidated = 0
        unchanged = 0

        for assumption in self._assumptions.values():
            if assumption.status != "open":
                continue

            stmt_lower = assumption.statement.lower()

            # Check for commitment kept → validates velocity assumptions
            for s in signals:
                if s.type == SignalType.CUSTOMER_COMMITMENT_KEPT:
                    if "commitment" in stmt_lower or "promise" in stmt_lower:
                        assumption.status = "validated"
                        assumption.validated_at = datetime.now(timezone.utc)
                        assumption.evidence.append({
                            "type": "signal",
                            "signal_type": s.type.value,
                            "artifact": s.artifact,
                            "detail": "Commitment was kept — assumption validated",
                        })
                        validated += 1
                        break

                # Check for commitment broken → invalidates trust assumptions
                if s.type == SignalType.CUSTOMER_COMMITMENT_BROKEN:
                    if "trust" in stmt_lower or "commitment" in stmt_lower or "promise" in stmt_lower:
                        assumption.status = "invalidated"
                        assumption.validated_at = datetime.now(timezone.utc)
                        assumption.evidence.append({
                            "type": "signal",
                            "signal_type": s.type.value,
                            "artifact": s.artifact,
                            "detail": "Commitment was broken — assumption invalidated",
                        })
                        assumption.impact = "Trust may have been damaged. Review affected decisions."
                        invalidated += 1
                        break

                # Check for sprint completion → validates velocity assumptions
                if s.type == SignalType.SPRINT_COMPLETED:
                    velocity = s.metadata.get("velocity", 0)
                    if velocity > 0 and "velocity" in stmt_lower:
                        assumption.status = "validated"
                        assumption.validated_at = datetime.now(timezone.utc)
                        assumption.evidence.append({
                            "type": "signal",
                            "signal_type": s.type.value,
                            "artifact": s.artifact,
                            "detail": f"Sprint completed with velocity {velocity} — velocity assumption validated",
                        })
                        validated += 1
                        break

                # Check for incident → invalidates stability assumptions
                if s.type == SignalType.INCIDENT:
                    if "stable" in stmt_lower or "reliable" in stmt_lower or "safe" in stmt_lower:
                        assumption.status = "invalidated"
                        assumption.validated_at = datetime.now(timezone.utc)
                        assumption.evidence.append({
                            "type": "signal",
                            "signal_type": s.type.value,
                            "artifact": s.artifact,
                            "detail": "Incident occurred — stability assumption invalidated",
                        })
                        assumption.impact = "Stability assumption was wrong. Review dependent decisions."
                        invalidated += 1
                        break

                # Check for champion quiet → invalidates relationship assumptions
                if s.type == SignalType.CUSTOMER_CHAMPION_QUIET:
                    if "champion" in stmt_lower or "relationship" in stmt_lower or "engaged" in stmt_lower:
                        assumption.status = "invalidated"
                        assumption.validated_at = datetime.now(timezone.utc)
                        assumption.evidence.append({
                            "type": "signal",
                            "signal_type": s.type.value,
                            "artifact": s.artifact,
                            "detail": "Champion went quiet — engagement assumption invalidated",
                        })
                        assumption.impact = "Relationship may be deteriorating. Review customer strategy."
                        invalidated += 1
                        break

                # Check for contract renewed → validates customer health assumptions
                if s.type == SignalType.CUSTOMER_CONTRACT_RENEWED:
                    if "renew" in stmt_lower or "customer" in stmt_lower or "healthy" in stmt_lower:
                        assumption.status = "validated"
                        assumption.validated_at = datetime.now(timezone.utc)
                        assumption.evidence.append({
                            "type": "signal",
                            "signal_type": s.type.value,
                            "artifact": s.artifact,
                            "detail": "Contract renewed — customer health assumption validated",
                        })
                        validated += 1
                        break

                # Check for contract churned → invalidates customer assumptions
                if s.type == SignalType.CUSTOMER_CONTRACT_CHURNED:
                    if "customer" in stmt_lower or "renew" in stmt_lower:
                        assumption.status = "invalidated"
                        assumption.validated_at = datetime.now(timezone.utc)
                        assumption.evidence.append({
                            "type": "signal",
                            "signal_type": s.type.value,
                            "artifact": s.artifact,
                            "detail": "Customer churned — assumption invalidated",
                        })
                        assumption.impact = "Customer was lost. The assumption that led to this decision was wrong."
                        invalidated += 1
                        break

            else:
                unchanged += 1

        logger.info("Assumption check: %d validated, %d invalidated, %d unchanged",
                     validated, invalidated, unchanged)
        return {"validated": validated, "invalidated": invalidated, "unchanged": unchanged}

    def get_dangerous_assumptions(self) -> list[dict[str, Any]]:
        """Get assumptions that are (a) still open, (b) high-stakes, and (c) have no evidence.

        These are the assumptions that could bankrupt a project if wrong.
        This is the 'what are we assuming that might be wrong?' view.
        No enterprise product has this.
        """
        dangerous = []
        for assumption in self._assumptions.values():
            if assumption.status != "open":
                continue
            if assumption.stakes not in ("high", "critical"):
                continue
            # An assumption is dangerous if it has no validating evidence
            # and supports a high-stakes decision
            has_supporting_evidence = any(
                "validated" in e.get("detail", "").lower()
                for e in assumption.evidence
            ) if assumption.evidence else False
            if not has_supporting_evidence:
                dangerous.append(assumption.to_dict())

        # Sort by stakes (critical first), then by age (oldest first)
        dangerous.sort(key=lambda a: (
            0 if a["stakes"] == "critical" else 1,
            a["made_at"],
        ))
        return dangerous

    def get_accuracy_report(self) -> dict[str, Any]:
        """Report on which assumptions came true and which didn't.

        After 90 days, this tells the org: '47% of our assumptions were
        correct. These 3 cost us the most when they turned out wrong.'
        """
        total = len(self._assumptions)
        if total == 0:
            return {
                "total_assumptions": 0,
                "validated": 0,
                "invalidated": 0,
                "open": 0,
                "accuracy_rate": 0,
                "most_costly_failures": [],
            }

        validated = sum(1 for a in self._assumptions.values() if a.status == "validated")
        invalidated = sum(1 for a in self._assumptions.values() if a.status == "invalidated")
        open_count = sum(1 for a in self._assumptions.values() if a.status == "open")
        resolved = validated + invalidated
        accuracy = validated / resolved if resolved > 0 else 0

        # Most costly failures: invalidated assumptions with impact text
        costly = [
            a.to_dict() for a in self._assumptions.values()
            if a.status == "invalidated" and a.impact
        ]
        costly.sort(key=lambda a: 0 if a["stakes"] == "critical" else 1 if a["stakes"] == "high" else 2)

        return {
            "total_assumptions": total,
            "validated": validated,
            "invalidated": invalidated,
            "open": open_count,
            "accuracy_rate": round(accuracy, 4),
            "most_costly_failures": costly[:5],
            "narrative": (
                f"{accuracy:.0%} of resolved assumptions were correct. "
                f"{invalidated} assumptions were invalidated, {validated} validated, "
                f"{open_count} still open."
            ),
        }

    def list_assumptions(self, status: str | None = None) -> list[dict[str, Any]]:
        """List all assumptions, optionally filtered by status."""
        if status:
            return [a.to_dict() for a in self._assumptions.values() if a.status == status]
        return [a.to_dict() for a in self._assumptions.values()]

    def get_assumption(self, assumption_id: str) -> dict[str, Any] | None:
        """Get a single assumption by ID."""
        a = self._assumptions.get(assumption_id)
        return a.to_dict() if a else None
