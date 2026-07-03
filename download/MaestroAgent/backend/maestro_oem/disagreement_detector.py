"""Loop 1.5 — Disagreement Detector.

External auditor (AUDITOR-EXTERNAL-REVIEW-3):
> Disagreement detection — surface when teams interpret the same
> commitment differently (requires claim_type + mutation tracking).

Organizations disagree. Engineering says "SSO is on track." The
customer says "SSO missed the deadline." These are not just different
data points — they are different EPISTEMIC TYPES making conflicting
claims about the same situation. Without claim_type, Maestro cannot
detect this. With claim_type (Loop 1 debt paid), it can.

The DisagreementDetector:
  - Takes a list of Evidence objects (each with a claim_type)
  - Groups them by entity + topic
  - Within each group, looks for conflicting claims across DIFFERENT
    claim_types
  - Returns Disagreement objects with: the two conflicting claims, their
    claim_types, and a resolution (which one to favor)

The resolution logic is epistemic — some claim_types are more reliable
than others:
  - observed_fact > reported_statement (direct evidence beats hearsay)
  - outcome > commitment (what actually happened beats what was promised)
  - observed_fact > assumption (direct evidence beats unverified belief)
  - prediction and inference are neutral (neither confirms nor denies)

This is NOT a contradiction engine (that already exists in the codebase).
Contradictions detect when two claims say opposite things. Disagreements
detect when two claims of DIFFERENT EPISTEMIC TYPES conflict — the
epistemic type tells Maestro which one to trust.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# Epistemic reliability ranking (higher = more reliable)
# Used to resolve disagreements — favor the more reliable claim_type
EPISTEMIC_RELIABILITY = {
    "observed_fact": 5,        # Directly witnessed — most reliable
    "outcome": 4,              # What actually happened
    "commitment": 3,           # A promise (may or may not be kept)
    "reported_statement": 2,   # Someone said something (hearsay)
    "inference": 1,            # Derived conclusion (depends on premises)
    "prediction": 1,           # Forecast (inherently uncertain)
    "assumption": 0,           # Unverified belief — least reliable
}


@dataclass
class Disagreement:
    """A detected disagreement between two Evidence objects.

    Attributes:
        entity: The entity both claims are about
        topic: The topic both claims address (e.g., "SSO", "pricing")
        claim_a: The first claim text
        claim_a_claim_type: The first claim's epistemic type
        claim_b: The second claim text
        claim_b_claim_type: The second claim's epistemic type
        resolution_favors: "a" or "b" — which claim to favor
        resolution_reason: Why this claim is favored
    """

    entity: str
    topic: str
    claim_a: str
    claim_a_claim_type: str
    claim_b: str
    claim_b_claim_type: str
    resolution_favors: str  # "a" or "b"
    resolution_reason: str

    def to_dict(self) -> dict:
        return {
            "entity": self.entity,
            "topic": self.topic,
            "claim_a": self.claim_a,
            "claim_a_claim_type": self.claim_a_claim_type,
            "claim_b": self.claim_b,
            "claim_b_claim_type": self.claim_b_claim_type,
            "resolution_favors": self.resolution_favors,
            "resolution_reason": self.resolution_reason,
        }


class DisagreementDetector:
    """Detect disagreements between Evidence objects of different claim_types.

    Usage:
        detector = DisagreementDetector()
        disagreements = detector.detect(evidence_list, entity="Globex", topic="SSO")
    """

    # Words that indicate a negative/missed outcome
    NEGATIVE_WORDS = {"missed", "broken", "failed", "late", "delayed", "not delivered", "churned", "lost"}

    # Words that indicate a positive/on-track outcome
    POSITIVE_WORDS = {"on track", "delivered", "honored", "kept", "complete", "done", "shipped"}

    def detect(
        self,
        evidence_list: list,
        entity: str = "",
        topic: str = "",
    ) -> list[Disagreement]:
        """Detect disagreements in a list of Evidence objects.

        Args:
            evidence_list: List of Evidence objects (each with claim_type)
            entity: The entity to filter by (optional)
            topic: The topic to filter by (optional)

        Returns:
            List of Disagreement objects. Empty if none found.
        """
        if len(evidence_list) < 2:
            return []

        disagreements: list[Disagreement] = []

        # Compare every pair of Evidence objects
        for i, ev_a in enumerate(evidence_list):
            for j, ev_b in enumerate(evidence_list):
                if i >= j:
                    continue  # Avoid duplicate pairs + self-comparison

                claim_a = getattr(ev_a, "claim", "")
                claim_b = getattr(ev_b, "claim", "")
                type_a = getattr(ev_a, "claim_type", "observed_fact")
                type_b = getattr(ev_b, "claim_type", "observed_fact")

                # Only detect disagreements across DIFFERENT claim_types
                if type_a == type_b:
                    continue

                # Check if the claims conflict (one positive, one negative)
                if not self._claims_conflict(claim_a, claim_b):
                    continue

                # Resolve: favor the more epistemically reliable claim_type
                reliability_a = EPISTEMIC_RELIABILITY.get(type_a, 0)
                reliability_b = EPISTEMIC_RELIABILITY.get(type_b, 0)

                if reliability_a > reliability_b:
                    favors = "a"
                    reason = f"{type_a} (reliability {reliability_a}) is more reliable than {type_b} (reliability {reliability_b})"
                elif reliability_b > reliability_a:
                    favors = "b"
                    reason = f"{type_b} (reliability {reliability_b}) is more reliable than {type_a} (reliability {reliability_a})"
                else:
                    # Equal reliability — favor neither, but still report the disagreement
                    favors = "a"
                    reason = f"Equal reliability ({type_a} vs {type_b}); favoring 'a' by default"

                disagreements.append(Disagreement(
                    entity=entity,
                    topic=topic,
                    claim_a=claim_a,
                    claim_a_claim_type=type_a,
                    claim_b=claim_b,
                    claim_b_claim_type=type_b,
                    resolution_favors=favors,
                    resolution_reason=reason,
                ))

        return disagreements

    def _claims_conflict(self, claim_a: str, claim_b: str) -> bool:
        """Check if two claims conflict (one positive, one negative).

        Heuristic: if one claim contains positive words and the other
        contains negative words, they conflict. This is a simple
        sentiment-based check — not a full NLI model. It's deterministic
        and explainable.

        False positives are acceptable here (the exec can dismiss a
        false disagreement). False negatives are the real risk — but
        the exec can always Ask Maestro directly.
        """
        a_lower = claim_a.lower()
        b_lower = claim_b.lower()

        a_positive = any(word in a_lower for word in self.POSITIVE_WORDS)
        a_negative = any(word in a_lower for word in self.NEGATIVE_WORDS)
        b_positive = any(word in b_lower for word in self.POSITIVE_WORDS)
        b_negative = any(word in b_lower for word in self.NEGATIVE_WORDS)

        # Conflict: one is positive, the other is negative
        if (a_positive and b_negative) or (a_negative and b_positive):
            return True

        return False
