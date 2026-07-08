"""
Maestro Cognitive Council — N1 + N2 Fixes: Scope discipline + Governance operator surface.

N1: Scope expansion requires evidence, not just absence of contradiction.
    A pattern validated in engineering cannot influence sales advice
    without independent sales-side evidence.

N2: Governance operator surface — a human-facing API where operators can
    review, override, suspend, or falsify any pattern, and where every
    governance action is auditable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# N1: Scope expansion requires evidence
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class ScopeExpansionRequest:
    """A request to expand a pattern's scope to a new domain.

    Per N1: scope expansion requires EVIDENCE in the new domain,
    not just absence of contradiction.
    """
    pattern_id: str
    current_scope: str               # e.g., "engineering"
    requested_scope: str             # e.g., "sales"
    evidence_in_new_scope: list[dict] = field(default_factory=list)
    approved: bool = False
    reason: str = ""
    requested_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    requested_by: str = ""


def can_expand_scope(
    pattern_id: str,
    current_scope: str,
    requested_scope: str,
    evidence_in_new_scope: list[dict],
) -> tuple[bool, str]:
    """Check if a pattern's scope can be expanded to a new domain.

    Per N1: "A pattern validated in engineering cannot influence sales
    advice without independent sales-side evidence."

    Returns (can_expand, reason).
    """
    if current_scope == requested_scope:
        return True, "Same scope — no expansion needed"

    if not evidence_in_new_scope:
        return False, (
            f"Scope expansion from {current_scope} to {requested_scope} denied: "
            f"no evidence in {requested_scope} scope. Per N1: scope expansion "
            f"requires evidence in the new domain, not just absence of contradiction."
        )

    if len(evidence_in_new_scope) < 2:
        return False, (
            f"Scope expansion from {current_scope} to {requested_scope} denied: "
            f"only {len(evidence_in_new_scope)} evidence item(s) in {requested_scope} scope. "
            f"Minimum 2 independent evidence items required for scope expansion."
        )

    return True, (
        f"Scope expansion from {current_scope} to {requested_scope} approved: "
        f"{len(evidence_in_new_scope)} evidence items in new scope."
    )


# ════════════════════════════════════════════════════════════════════════════
# N2: Governance operator surface
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class GovernanceAction:
    """An auditable governance action taken by a human operator.

    Per N2: "A governance operator surface where a human can review,
    override, suspend, or falsify any pattern, and where every governance
    action is auditable."
    """
    action_id: str = field(default_factory=lambda: f"gov-{uuid4().hex[:12]}")
    action_type: str = ""            # promote | suspend | falsify | narrow_scope | expand_scope | override
    pattern_id: str = ""
    operator: str = ""               # who made the decision
    reason: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "pattern_id": self.pattern_id,
            "operator": self.operator,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


class GovernanceOperatorSurface:
    """Human-facing governance surface for pattern management.

    Per N2: operators can review, override, suspend, or falsify any pattern.
    Every action is auditable.

    Usage:
        surface = GovernanceOperatorSurface()
        surface.review_patterns(candidate_store)
        surface.suspend_pattern("pattern-123", operator="ceo@company.com", reason="Needs investigation")
        surface.falsify_pattern("pattern-456", operator="ceo@company.com", reason="Contradicted by outcome")
        actions = surface.get_audit_log()
    """

    def __init__(self):
        self._actions: list[GovernanceAction] = []

    def review_patterns(self, candidate_store: Any) -> list[dict]:
        """List all patterns for operator review.

        Returns patterns with their status, evidence, and replication metrics.
        """
        patterns = []
        if hasattr(candidate_store, "_candidates"):
            for cid, candidate in candidate_store._candidates.items():
                patterns.append({
                    "pattern_id": str(cid),
                    "hypothesis": candidate.hypothesis,
                    "status": getattr(getattr(candidate, "status", None), "value", str(getattr(candidate, "status", ""))),
                    "supporting_outcomes": getattr(candidate, "supporting_outcomes", 0),
                    "contradicting_outcomes": getattr(candidate, "contradicting_outcomes", 0),
                    "prospective_predictions": getattr(candidate, "prospective_predictions", 0),
                    "valid_scope": getattr(candidate, "valid_scope", {}),
                    "unproven_scope": getattr(candidate, "unproven_scope", {}),
                    "invalid_scope": getattr(candidate, "invalid_scope", {}),
                    "governance_approved_by": getattr(candidate, "governance_approved_by", ""),
                })
        return patterns

    def suspend_pattern(self, pattern_id: str, operator: str, reason: str) -> GovernanceAction:
        """Suspend a pattern (temporarily disable its influence on advice).

        Per N2: operators can suspend patterns pending investigation.
        """
        action = GovernanceAction(
            action_type="suspend",
            pattern_id=pattern_id,
            operator=operator,
            reason=reason,
        )
        self._actions.append(action)
        logger.info("N2 GOVERNANCE: pattern %s suspended by %s: %s", pattern_id, operator, reason)
        return action

    def falsify_pattern(self, pattern_id: str, operator: str, reason: str) -> GovernanceAction:
        """Falsify a pattern (permanently — tombstone enforced).

        Per N2: operators can falsify patterns. Once falsified, the pattern
        cannot influence advice (C7 tombstone enforcement).
        """
        action = GovernanceAction(
            action_type="falsify",
            pattern_id=pattern_id,
            operator=operator,
            reason=reason,
        )
        self._actions.append(action)
        logger.info("N2 GOVERNANCE: pattern %s falsified by %s: %s", pattern_id, operator, reason)
        return action

    def promote_pattern(self, pattern_id: str, operator: str, reason: str) -> GovernanceAction:
        """Promote a pattern to ACTIVE_PATTERN status.

        Per N2: only operators can finalize promotion.
        """
        action = GovernanceAction(
            action_type="promote",
            pattern_id=pattern_id,
            operator=operator,
            reason=reason,
        )
        self._actions.append(action)
        logger.info("N2 GOVERNANCE: pattern %s promoted by %s: %s", pattern_id, operator, reason)
        return action

    def narrow_scope(self, pattern_id: str, scope: dict, operator: str, reason: str) -> GovernanceAction:
        """Narrow a pattern's scope (restrict where it can influence advice).

        Per N1: scope discipline — a pattern shouldn't influence domains
        where it hasn't been validated.
        """
        action = GovernanceAction(
            action_type="narrow_scope",
            pattern_id=pattern_id,
            operator=operator,
            reason=reason,
            metadata={"scope": scope},
        )
        self._actions.append(action)
        logger.info("N2 GOVERNANCE: pattern %s scope narrowed by %s: %s", pattern_id, operator, reason)
        return action

    def expand_scope(self, request: ScopeExpansionRequest, operator: str) -> GovernanceAction:
        """Expand a pattern's scope (requires evidence in new domain per N1).

        Per N1: scope expansion requires evidence, not just absence of contradiction.
        """
        can_expand, reason = can_expand_scope(
            request.pattern_id,
            request.current_scope,
            request.requested_scope,
            request.evidence_in_new_scope,
        )

        action = GovernanceAction(
            action_type="expand_scope",
            pattern_id=request.pattern_id,
            operator=operator,
            reason=reason,
            metadata={
                "current_scope": request.current_scope,
                "requested_scope": request.requested_scope,
                "evidence_count": len(request.evidence_in_new_scope),
                "approved": can_expand,
            },
        )
        self._actions.append(action)

        if can_expand:
            logger.info("N2 GOVERNANCE: pattern %s scope expanded to %s by %s",
                       request.pattern_id, request.requested_scope, operator)
        else:
            logger.warning("N2 GOVERNANCE: pattern %s scope expansion to %s DENIED: %s",
                          request.pattern_id, request.requested_scope, reason)

        return action

    def override(self, pattern_id: str, decision: str, operator: str, reason: str) -> GovernanceAction:
        """Override any system governance decision.

        Per N2: operators can override system decisions. This is the
        human-in-the-loop safety valve.
        """
        action = GovernanceAction(
            action_type="override",
            pattern_id=pattern_id,
            operator=operator,
            reason=f"Override: {decision}. {reason}",
        )
        self._actions.append(action)
        logger.info("N2 GOVERNANCE: pattern %s decision overridden by %s: %s",
                    pattern_id, operator, decision)
        return action

    def get_audit_log(self) -> list[dict]:
        """Get the full audit log of all governance actions.

        Per N2: "every governance action is auditable."
        """
        return [a.to_dict() for a in self._actions]

    def get_actions_for_pattern(self, pattern_id: str) -> list[dict]:
        """Get all governance actions for a specific pattern."""
        return [a.to_dict() for a in self._actions if a.pattern_id == pattern_id]
