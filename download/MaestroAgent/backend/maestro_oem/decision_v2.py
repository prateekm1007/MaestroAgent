"""Loop 3 — Decision: a first-class object with a lifecycle.

CEO directive (auditor recommendation, CEO-validated): "Loop 3 — Decision
Intelligence. The Decision object is the natural next first-class citizen
after Commitment and Meeting. Decisions have intent (what we're trying
to do), assumptions (what we believe), hypotheses (what we predict), and
outcomes (what happened). This exercises the claim_type epistemic types
(assumption, inference, prediction, outcome) more deeply than Loops 1
and 2 did."

A Decision is NOT just a choice. A choice is a point in time. A Decision
is a cognitive object with a lifecycle:

  PROPOSED → ASSUMPTIONS_RECORDED → HYPOTHESIS_STATED → DECIDED →
  OUTCOME_OBSERVED → LEARNING_RECORDED

Each transition is meaningful:
  - PROPOSED: a decision is on the table (intent stated)
  - ASSUMPTIONS_RECORDED: the assumptions underpinning the decision are
    recorded (each with claim_type="assumption")
  - HYPOTHESIS_STATED: a falsifiable prediction is made (claim_type="prediction")
  - DECIDED: the decision is made (the chosen course of action)
  - OUTCOME_OBSERVED: what actually happened (claim_type="outcome")
  - LEARNING_RECORDED: a Decision Learning Ledger entry is written

This module is named decision_v2.py to avoid colliding with the existing
decision.py (which has different content). The Decision class here is
the Loop 3 first-class object.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class DecisionStatus(str, Enum):
    """The 6 lifecycle states of a Decision."""

    PROPOSED = "proposed"
    ASSUMPTIONS_RECORDED = "assumptions_recorded"
    HYPOTHESIS_STATED = "hypothesis_stated"
    DECIDED = "decided"
    OUTCOME_OBSERVED = "outcome_observed"
    LEARNING_RECORDED = "learning_recorded"


@dataclass
class Decision:
    """A first-class decision object with a lifecycle.

    Attributes:
        intent: What we're trying to achieve ("Prioritize SSO delivery to Globex")
        entity: The customer/org this decision affects
        status: Current lifecycle state (default: PROPOSED)
        assumptions: List of assumption dicts, each with claim_type="assumption"
        hypothesis: A falsifiable prediction dict with claim_type="prediction"
        decision_text: The chosen course of action (recorded when DECIDED)
        outcome: What actually happened dict with claim_type="outcome"
        learning_entry: The Decision Learning Ledger entry (honest sentence)
        decision_id: Deterministic ID (hashlib.sha256 of intent + entity + timestamp)
        created_at: When the decision was proposed
    """

    intent: str
    entity: str
    status: DecisionStatus = DecisionStatus.PROPOSED
    assumptions: list[dict] = field(default_factory=list)
    hypothesis: dict | None = None
    decision_text: str | None = None
    outcome: dict | None = None
    learning_entry: str | None = None
    decision_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        """Generate a deterministic decision_id if not provided."""
        if not self.decision_id:
            raw = f"decision-{self.intent}-{self.entity}-{self.created_at.isoformat()}"
            self.decision_id = f"dec-{hashlib.sha256(raw.encode()).hexdigest()[:8]}"

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API responses."""
        return {
            "decision_id": self.decision_id,
            "intent": self.intent,
            "entity": self.entity,
            "status": self.status.name,
            "assumptions": list(self.assumptions),
            "hypothesis": self.hypothesis,
            "decision_text": self.decision_text,
            "outcome": self.outcome,
            "learning_entry": self.learning_entry,
            "created_at": self.created_at.isoformat() if hasattr(self.created_at, "isoformat") else str(self.created_at),
        }
