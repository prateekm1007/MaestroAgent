"""Loop 4 — Delivery Policy Learner.

CEO directive (auditor recommendation, CEO-validated): "Loop 4 —
Organizational Learning: cross-case pattern detection and delivery-policy
learning. This is where the moat compounds — the system learning about
its own delivery effectiveness."

The DeliveryPolicyLearner learns about Maestro's own delivery
effectiveness. It answers: "when Maestro delivers Whispers in context X,
does the exec act on them? When Maestro delivers in context Y, does the
exec ignore them?"

This is the system learning about itself — not about the organization,
but about its own delivery. This is the moat: a system that learns which
delivery contexts work and which don't.

Current policies learned:
  1. Timing effectiveness: "commitment warnings delivered before account
     meetings are more effective than during weekly planning" (when the
     data supports it)

The learner is honest about sample size. If there are only 2 data points,
it says "preliminary" — not "proven." No fake precision.

Future policies (deferred):
  - Depth effectiveness: "full Evidence Spine is more effective than headline"
  - Recipient effectiveness: "delivering to the internal expert is more
    effective than delivering to the meeting attendee"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DeliveryPolicy:
    """A learned delivery policy.

    Attributes:
        policy_type: The policy identifier ("timing_effectiveness")
        description: A human-readable sentence about the policy
        evidence_count: How many data points support this policy
        confidence: "preliminary" (2-4 data points) | "moderate" (5-9) | "strong" (10+)
    """

    policy_type: str
    description: str
    evidence_count: int
    confidence: str  # "preliminary" | "moderate" | "strong"

    def to_dict(self) -> dict:
        return {
            "policy_type": self.policy_type,
            "description": self.description,
            "evidence_count": self.evidence_count,
            "confidence": self.confidence,
        }


class DeliveryPolicyLearner:
    """Learn delivery policies from the Organizational Learning Ledger.

    Usage:
        learner = DeliveryPolicyLearner()
        policies = learner.learn(ledger)
    """

    def learn(self, ledger: Any) -> list[DeliveryPolicy]:
        """Learn delivery policies from the ledger.

        Args:
            ledger: An OrganizationalLearningLedger with entries from all 3 loops.

        Returns:
            List of DeliveryPolicy objects.
        """
        policies: list[DeliveryPolicy] = []
        entries = ledger.get_all_entries() if hasattr(ledger, "get_all_entries") else []
        commitment_entries = [e for e in entries if e.source_loop == "commitment"]

        # Policy 1: Timing effectiveness
        # Compare "before_account_meeting" vs "weekly_planning" delivery contexts
        meeting_entries = [
            e for e in commitment_entries
            if e.delivery_context == "before_account_meeting"
        ]
        planning_entries = [
            e for e in commitment_entries
            if e.delivery_context == "weekly_planning"
        ]

        if len(meeting_entries) >= 2 and len(planning_entries) >= 2:
            meeting_acted = sum(1 for e in meeting_entries if e.action == "acted")
            planning_acted = sum(1 for e in planning_entries if e.action == "acted")
            meeting_rate = meeting_acted / len(meeting_entries)
            planning_rate = planning_acted / len(planning_entries)

            total_evidence = len(meeting_entries) + len(planning_entries)
            confidence = self._confidence_level(total_evidence)

            if meeting_rate > planning_rate:
                description = (
                    f"commitment warnings delivered before account meetings are more "
                    f"effective than during weekly planning (exec acted in "
                    f"{meeting_acted}/{len(meeting_entries)} meeting cases vs "
                    f"{planning_acted}/{len(planning_entries)} planning cases). "
                    f"Confidence: {confidence} ({total_evidence} data points)."
                )
                policies.append(DeliveryPolicy(
                    policy_type="timing_effectiveness",
                    description=description,
                    evidence_count=total_evidence,
                    confidence=confidence,
                ))
            elif planning_rate > meeting_rate:
                description = (
                    f"commitment warnings delivered during weekly planning are more "
                    f"effective than before account meetings (exec acted in "
                    f"{planning_acted}/{len(planning_entries)} planning cases vs "
                    f"{meeting_acted}/{len(meeting_entries)} meeting cases). "
                    f"Confidence: {confidence} ({total_evidence} data points)."
                )
                policies.append(DeliveryPolicy(
                    policy_type="timing_effectiveness",
                    description=description,
                    evidence_count=total_evidence,
                    confidence=confidence,
                ))

        return policies

    def _confidence_level(self, data_points: int) -> str:
        """Determine confidence level from sample size.

        Honest about sample size — no fake precision.
          - 2-4 data points: "preliminary"
          - 5-9 data points: "moderate"
          - 10+ data points: "strong"
        """
        if data_points < 5:
            return "preliminary"
        if data_points < 10:
            return "moderate"
        return "strong"
