"""Priority 4: Content-level epistemic classification — analyze the actual
text, not just the signal type.

The prior adversarial audit found (H-02):
> Epistemic classification is signal-type-driven, not content-driven. A
> "proposal" in a commitment signal becomes a "commitment." No NLP/LLM
> classification of actual statement intent.

The ContentEpistemicClassifier analyzes the actual text of a statement
and returns its epistemic type. The EvidenceBuilder uses this classifier's
output instead of hardcoding claim_type per whisper type.

The 10 epistemic types:
  - observed_fact       — directly witnessed ("the release failed Tuesday")
  - reported_statement  — someone said something ("Engineering believes Legal caused the delay")
  - commitment          — a promise was made ("We will deliver SSO by Q4")
  - assumption          — an unverified belief ("The deadline has not been renegotiated")
  - inference           — a derived conclusion ("Moving Legal earlier may reduce delay")
  - prediction          — a forecast ("The release will likely slip")
  - outcome             — what actually happened ("Commitment was honored/broken")
  - proposal            — a suggestion, NOT a promise ("We should support SSO")
  - estimate            — a human-reported forecast ("Engineering thinks SSO can be ready by Q4")
  - hypothesis          — a conditional testable prediction ("If we prioritize SSO, <customer> will renew")

Design:
  - Rule-based now (regex + keywords), LLM-ready later
  - Conservative: when uncertain, returns the fallback type (backward-compatible)
  - Content classification only OVERRIDES when confident
  - The classifier never SILENCES evidence (P6) — it only relabels

Wiring (P11):
  - EvidenceBuilder calls ContentEpistemicClassifier.classify() to set
    claim_type based on the actual commitment/objection text
  - The fallback is the signal-type-based type (backward-compatible)
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# ─── Epistemic type constants ──────────────────────────────────────────────

OBSERVED_FACT = "observed_fact"
REPORTED_STATEMENT = "reported_statement"
COMMITMENT = "commitment"
ASSUMPTION = "assumption"
INFERENCE = "inference"
PREDICTION = "prediction"
OUTCOME = "outcome"
PROPOSAL = "proposal"
ESTIMATE = "estimate"
HYPOTHESIS = "hypothesis"

VALID_TYPES = {
    OBSERVED_FACT, REPORTED_STATEMENT, COMMITMENT, ASSUMPTION,
    INFERENCE, PREDICTION, OUTCOME, PROPOSAL, ESTIMATE, HYPOTHESIS,
}


# ─── Classification patterns (ordered by priority — first match wins) ──────
# Each pattern is (regex, epistemic_type, confidence).
# Patterns are ordered so that more specific types are checked before
# more general ones. For example, "we should" (proposal) must be checked
# before "we will" (commitment) because "we should" is a suggestion, not
# a promise — even though both start with "we."

_PATTERNS: list[tuple[re.Pattern, str, float]] = [
    # ─── Hypothesis: conditional falsifiable prediction ───────────────────
    # "If we prioritize SSO, TestCorp will renew"
    # "If we do X, then Y will happen"
    (
        re.compile(
            r"\bif\s+(?:we|you|they|the)\b.{1,80}\b(?:will|would|may|might|could)\b",
            re.IGNORECASE,
        ),
        HYPOTHESIS,
        0.9,
    ),

    # ─── Proposal: a suggestion, NOT a promise ────────────────────────────
    # "We should support SSO"
    # "We could deliver by Q4"
    # "We ought to prioritize security"
    # "I suggest we..."
    # "Let's consider..."
    (
        re.compile(
            r"\b(?:we\s+should|we\s+could|we\s+ought\s+to|we\s+need\s+to\s+consider|"
            r"i\s+suggest|let'?s\s+consider|let'?s\s+think\s+about|"
            r"we\s+might\s+want\s+to|it\s+might\s+be\s+worth)\b",
            re.IGNORECASE,
        ),
        PROPOSAL,
        0.85,
    ),

    # ─── Estimate: human-reported forecast ────────────────────────────────
    # "Engineering thinks SSO can be ready by Q4"
    # "The team estimates 2 weeks"
    # "Sarah estimates 2 weeks"
    # "According to Engineering, ..."
    # Note: "believes" is NOT included here — it's a reported_statement, not
    # an estimate. An estimate requires a forecast ("can be ready by Q4").
    (
        re.compile(
            r"\b(?:\w+\s+thinks?\s+\w+\s+can|\w+\s+estimates?|\w+\s+says?\s+(?:it\s+can|they\s+can)|"
            r"according\s+to\s+\w+|the\s+team\s+(?:thinks|estimates)|"
            r"engineering\s+(?:thinks|estimates))\b",
            re.IGNORECASE,
        ),
        ESTIMATE,
        0.8,
    ),

    # ─── Reported statement: someone said something ───────────────────────
    # "Engineering believes Legal caused the delay"
    # "Sarah said the deployment failed"
    # "The team reported that..."
    # "John mentioned that..."
    (
        re.compile(
            r"\b(?:\w+\s+(?:believes|said|reports?|mentioned|stated|claims?))\b|"
            r"\b(?:the\s+team\s+reports?)\b",
            re.IGNORECASE,
        ),
        REPORTED_STATEMENT,
        0.75,
    ),

    # ─── Prediction: a forecast (system-generated) ────────────────────────
    # "The release will likely slip"
    # "We expect the migration to take 3 weeks"
    # "The system predicts churn risk"
    (
        re.compile(
            r"\b(?:will\s+likely|expected\s+to|predicts?|forecast|"
            r"we\s+expect|likely\s+to|probably\s+will)\b",
            re.IGNORECASE,
        ),
        PREDICTION,
        0.8,
    ),

    # ─── Outcome: what actually happened ──────────────────────────────────
    # "The commitment was broken"
    # "The commitment was honored"
    # "The customer churned"
    # "The customer renewed"
    # Note: "The release failed Tuesday" is an observed_fact, not an outcome.
    # An outcome specifically refers to the resolution of a commitment/
    # prediction/decision — "was broken/honored/kept", "churned/renewed".
    (
        re.compile(
            r"\b(?:was\s+(?:broken|honored|kept)|"
            r"customer\s+(?:churned|renewed|cancelled)|"
            r"commitment\s+(?:was\s+broken|was\s+honored|broke))\b",
            re.IGNORECASE,
        ),
        OUTCOME,
        0.85,
    ),

    # ─── Commitment: a promise was made ───────────────────────────────────
    # "We will deliver SSO by Q4"
    # "We promise to ship the API"
    # "We commit to delivering by Friday"
    # "We'll have it ready by..."
    (
        re.compile(
            r"\b(?:we\s+will\s+(?:deliver|ship|build|provide|implement|have\s+\w+\s+ready)|"
            r"we['']?ll\s+(?:deliver|ship|build|provide|implement|have\s+\w+\s+ready)|"
            r"we\s+promise\s+to|we\s+commit\s+to\s+(?:delivering|shipping|building))\b",
            re.IGNORECASE,
        ),
        COMMITMENT,
        0.9,
    ),

    # ─── Inference: a derived conclusion ──────────────────────────────────
    # "Moving Legal earlier may reduce delay"
    # "This suggests that..."
    # "Based on the data, we conclude..."
    (
        re.compile(
            r"\b(?:may\s+reduce|may\s+increase|may\s+improve|suggests\s+that|"
            r"we\s+conclude|based\s+on\s+(?:the\s+)?data|this\s+implies|"
            r"this\s+indicates)\b",
            re.IGNORECASE,
        ),
        INFERENCE,
        0.7,
    ),

    # ─── Assumption: an unverified belief ─────────────────────────────────
    # "The deadline has not been renegotiated"
    # "We assume the API is stable"
    # "Assuming the migration completes..."
    (
        re.compile(
            r"\b(?:we\s+assume|assuming|the\s+(?:deadline|contract|agreement)\s+(?:has\s+not|is\s+still))\b",
            re.IGNORECASE,
        ),
        ASSUMPTION,
        0.7,
    ),

    # ─── Observed fact: directly witnessed ────────────────────────────────
    # "The release failed Tuesday"
    # "The meeting happened"
    # "The PR was merged"
    (
        re.compile(
            r"\b(?:the\s+\w+\s+(?:failed|happened|was\s+merged|was\s+deployed|was\s+closed)|"
            r"on\s+(?:monday|tuesday|wednesday|thursday|friday),\s+\w+\s+(?:failed|happened))\b",
            re.IGNORECASE,
        ),
        OBSERVED_FACT,
        0.65,
    ),
]


class ContentEpistemicClassifier:
    """Classify the epistemic type of a statement based on its content.

    Rule-based now, LLM-ready later. A future LLM provider can subclass
    and override classify() to use an LLM for higher accuracy.

    Usage:
        classifier = ContentEpistemicClassifier()
        epistemic_type = classifier.classify(
            "We should support SSO",
            fallback="commitment",  # what the signal type would say
        )
        # Returns "proposal" — the content overrides the signal type

    The classifier is CONSERVATIVE:
      - When confident (pattern matches with high confidence), it returns
        the content-derived type
      - When uncertain (no pattern matches), it returns the fallback type
        (backward-compatible with signal-type-based classification)
      - It NEVER silences evidence (P6) — it only relabels claim_type
    """

    def classify(self, text: str, fallback: str = OBSERVED_FACT) -> str:
        """Classify the epistemic type of a statement.

        Args:
            text: The statement text to classify
            fallback: The type to return if no pattern matches with
                sufficient confidence (default: observed_fact). This is
                typically the signal-type-based type, preserving backward
                compatibility.

        Returns:
            One of the 10 epistemic types. If no pattern matches, returns
            the fallback.
        """
        if not text or not isinstance(text, str):
            return fallback if fallback in VALID_TYPES else OBSERVED_FACT

        # Try each pattern in order — first match wins
        for pattern, epistemic_type, confidence in _PATTERNS:
            if pattern.search(text):
                logger.debug(
                    "ContentEpistemicClassifier: classified %r as %s (confidence: %.2f)",
                    text[:60], epistemic_type, confidence,
                )
                return epistemic_type

        # No pattern matched — return the fallback (backward-compatible)
        return fallback if fallback in VALID_TYPES else OBSERVED_FACT

    def classify_with_confidence(
        self, text: str, fallback: str = OBSERVED_FACT,
    ) -> tuple[str, float]:
        """Classify and return (type, confidence).

        Confidence is 0.0 for fallback (no pattern matched).
        """
        if not text or not isinstance(text, str):
            return (fallback if fallback in VALID_TYPES else OBSERVED_FACT, 0.0)

        for pattern, epistemic_type, confidence in _PATTERNS:
            if pattern.search(text):
                return (epistemic_type, confidence)

        return (fallback if fallback in VALID_TYPES else OBSERVED_FACT, 0.0)
