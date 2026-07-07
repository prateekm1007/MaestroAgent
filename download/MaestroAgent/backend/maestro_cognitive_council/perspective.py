"""
Maestro Cognitive Council — Phase 2: Perspective Contract.

A Perspective is a structured contribution from a specialist to a
situation. It is NOT a free-form "insight." It has a strict epistemic
schema:

  situation_id          # which situation this pertains to
  specialist            # which specialist produced it
  observation           # what does this specialist see?
  implication           # why might it matter?
  evidence              # which records support it?
  counterevidence       # what weakens this interpretation?
  unknowns              # what must still be established?
  scope                 # where is this interpretation applicable?
  urgency               # why now, rather than later?
  recommended_next_step # what is the smallest useful action?
  epistemic_status      # observed | reported | inferred | disputed | unknown
  delivery_recommendation # silent | briefing | whisper | prepare | urgent

Constitutional rule: a specialist may RECOMMEND delivery. It cannot
DECIDE delivery. That belongs to the Delivery Governor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from .situation_engine import EpistemicState, DeliveryRoute

logger = logging.getLogger(__name__)


@dataclass
class Perspective:
    """A structured contribution from a specialist to a situation.

    This replaces the free-form AgentInsight from the Nerve integration.
    Every perspective must declare its epistemic status and acknowledge
    its counterevidence and unknowns — no bare claims.
    """

    # Identity
    perspective_id: str = field(default_factory=lambda: f"persp-{uuid4().hex[:8]}")
    situation_id: str = ""
    specialist: str = ""

    # The perspective content
    observation: str = ""           # what does this specialist see?
    implication: str = ""           # why might it matter?
    recommended_next_step: str = "" # what is the smallest useful action?

    # Epistemic discipline (P4 — honest disclosure)
    evidence: list[dict] = field(default_factory=list)         # what supports this?
    counterevidence: list[dict] = field(default_factory=list)  # what weakens this?
    unknowns: list[str] = field(default_factory=list)          # what must still be established?

    # Scope and urgency
    scope: str = ""                 # where is this interpretation applicable?
    urgency: str = "normal"         # why now? "low" | "normal" | "high" | "critical"

    # Epistemic status
    epistemic_status: EpistemicState = EpistemicState.REPORTED

    # Delivery recommendation (the specialist recommends; the Governor decides)
    delivery_recommendation: DeliveryRoute = DeliveryRoute.BRIEFING

    # Metadata
    confidence: float = 0.0  # 0.0-1.0 — calibrated against evidence strength
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "perspective_id": self.perspective_id,
            "situation_id": self.situation_id,
            "specialist": self.specialist,
            "observation": self.observation,
            "implication": self.implication,
            "recommended_next_step": self.recommended_next_step,
            "evidence": self.evidence,
            "counterevidence": self.counterevidence,
            "unknowns": self.unknowns,
            "scope": self.scope,
            "urgency": self.urgency,
            "epistemic_status": self.epistemic_status.value,
            "delivery_recommendation": self.delivery_recommendation.value,
            "confidence": round(self.confidence, 3),
            "created_at": self.created_at,
        }

    def has_counterevidence(self) -> bool:
        """Does this perspective acknowledge counterevidence? (P4)"""
        return len(self.counterevidence) > 0

    def has_unknowns(self) -> bool:
        """Does this perspective acknowledge unknowns? (P4)"""
        return len(self.unknowns) > 0

    def is_epistemically_honest(self) -> bool:
        """A perspective is epistemically honest if it cites evidence AND
        acknowledges either counterevidence or unknowns.

        Perspectives that claim certainty without acknowledging what could
        weaken them are NOT epistemically honest and should be flagged.
        """
        has_evidence = len(self.evidence) > 0
        acknowledges_limits = self.has_counterevidence() or self.has_unknowns()
        return has_evidence and acknowledges_limits
