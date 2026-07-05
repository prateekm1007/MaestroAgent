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
    "question", "negation", "retraction", "unclassified",
}


# ─── Classification patterns (ordered by priority — first match wins) ──────
# Each pattern is (regex, epistemic_type, confidence).
# Patterns are ordered so that more specific types are checked before
# more general ones. For example, "we should" (proposal) must be checked
# before "we will" (commitment) because "we should" is a suggestion, not
# a promise — even though both start with "we."

_PATTERNS: list[tuple[re.Pattern, str, float]] = [
    # ─── Phase 3.1a: Questions — never classify as any claim type ────────
    # A sentence ending in "?" or starting with a question word is not a claim
    (
        re.compile(r"\?\s*$"),
        "question",
        0.95,
    ),
    (
        re.compile(r"^\s*(?:what|when|where|who|why|how|which|is|are|can|could|would|will|do|does|did|have|has)\b|^\s*should\s+(?:we|i|you|they)\b", re.IGNORECASE),
        "question",
        0.90,
    ),

    # ─── Phase 3.1c: Retraction / correction / sarcasm ───────────────────
    # "Just kidding", "wait, no", "actually, scrap that" — the speaker is
    # retracting or correcting a prior statement, not making a new claim
    (
        re.compile(
            r"\b(?:just\s+kidding|wait,?\s+no|actually,?\s+(?:no|scrap|never\s+mind|forget\s+it)|"
            r"scratch\s+that|disregard\s+that|on\s+second\s+thought|"
            r"actually,?\s+we\s+haven't|just\s+joking)\b",
            re.IGNORECASE,
        ),
        "retraction",
        0.85,
    ),

    # ─── Phase 3.1b: Negation — "nobody has ever said", "we haven't shipped" ─
    # A negated statement is NOT the same as an affirmative. "We haven't shipped"
    # is an observed_fact about a negative state, not a commitment to ship.
    # AUDITOR-FIX: added "is still conditional", "is conditional", "still pending"
    (
        re.compile(
            r"\b(?:nobody\s+(?:has|have)\s+ever|no\s+one\s+has\s+ever|"
            r"we\s+haven't|we\s+have\s+not|we\s+don't|we\s+do\s+not|"
            r"has\s+not\s+been|have\s+not\s+been|is\s+not\s+(?:ready|available|complete)|"
            r"remains?\s+conditional|is\s+still\s+(?:pending|conditional)|is\s+conditional|"
            r"still\s+(?:pending|conditional|under\s+review)|"
            r"hasn't|haven't|didn't|doesn't|isn't|wasn't|won't)\b",
            re.IGNORECASE,
        ),
        "negation",
        0.80,
    ),

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
    # AUDITOR-FIX: also catch "should be able to" (cautious proposal, not commitment)
    (
        re.compile(
            r"\b(?:we\s+should|we\s+could|we\s+ought\s+to|we\s+need\s+to\s+consider|"
            r"i\s+suggest|let'?s\s+consider|let'?s\s+think\s+about|"
            r"we\s+might\s+want\s+to|it\s+might\s+be\s+worth|"
            r"should\s+be\s+able\s+to|ought\s+to\s+be\s+able\s+to)\b",
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
    # H-01 fix: also catch:
    #   "[team] says we promised..." (Sales says, Product says, etc.)
    #   "The customer expects/considers/believes..."
    #   "considers the commitment unmet"
    # AUDITOR-FIX: also catch "we understood the commitment as" (customer reinterpretation)
    (
        re.compile(
            r"\b(?:\w+\s+(?:believes|said|reports?|mentioned|stated|claims?|says?))\b|"
            r"\b(?:the\s+team\s+reports?)\b|"
            r"\b(?:the\s+customer\s+(?:expects?|considers?|believes?|stated?|says?))\b|"
            r"\b(?:customer\s+(?:expects?|considers?|believes?))\b|"
            r"\b(?:considers?\s+the\s+(?:commitment|agreement|delivery)\s+(?:unmet|met|broken|honored))\b|"
            r"\b(?:we\s+understood\s+the\s+(?:commitment|agreement|promise)\s+as)\b|"
            r"\b(?:understood\s+(?:the\s+)?(?:commitment|agreement)\s+(?:as|to\s+(?:mean|be)))\b",
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
    # H-01 fix: also catch deployment/release outcomes:
    #   "deployed successfully" / "shipped" / "launched" / "completed"
    #   "rolled out" / "went live"
    # AUDITOR-FIX: also catch "work is complete", "is done", "is finished"
    (
        re.compile(
            r"\b(?:was\s+(?:broken|honored|kept)|"
            r"customer\s+(?:churned|renewed|cancelled)|"
            r"commitment\s+(?:was\s+broken|was\s+honored|broke)|"
            r"(?:deployed|shipped|launched|completed|rolled\s+out|went\s+live)\s+successfully|"
            r"successfully\s+(?:deployed|shipped|launched|completed|rolled\s+out)|"
            r"(?:work\s+)?is\s+(?:complete|done|finished)|"
            r"\w+\s+is\s+complete)\b",
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
    # H-01 fix: also catch:
    #   "I'll confirm/deliver/ship/send..." (first-person commitment)
    #   "We will have SSO ready before renewal" (have + noun + ready)
    #   "I'll have it ready by..." (first-person have + ready)
    # AUDITOR-FIX: also catch "we will have X available" (available, not just ready)
    #   and "target: before renewal" (commitment target with date)
    (
        re.compile(
            r"\b(?:we\s+will\s+(?:deliver|ship|build|provide|implement|have\s+\w+\s+(?:ready|available))|"
            r"we['']?ll\s+(?:deliver|ship|build|provide|implement|have\s+\w+\s+(?:ready|available))|"
            r"we\s+promise\s+to|we\s+commit\s+to\s+(?:delivering|shipping|building)|"
            r"i['']?ll\s+(?:confirm|deliver|ship|send|build|provide|implement|have\s+\w+\s+ready|get\s+\w+\s+ready|follow\s+up)|"
            r"i\s+will\s+(?:confirm|deliver|ship|send|build|provide|implement|have\s+\w+\s+ready)|"
            r"we\s+will\s+have\s+\w+\s+(?:ready|available|before|by)|"
            r"target:\s*\w+|target\s+date:\s*\w+|due\s+(?:by|date))\b",
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

    def classify(self, text: str, fallback: str = "unclassified") -> str:
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
            return fallback if fallback in VALID_TYPES else "unclassified"

        # Try each pattern in order — first match wins
        for pattern, epistemic_type, confidence in _PATTERNS:
            if pattern.search(text):
                logger.debug(
                    "ContentEpistemicClassifier: classified %r as %s (confidence: %.2f)",
                    text[:60], epistemic_type, confidence,
                )
                return epistemic_type

        # No pattern matched — return the fallback (backward-compatible)
        return fallback if fallback in VALID_TYPES else "unclassified"

    def classify_with_confidence(
        self, text: str, fallback: str = "unclassified",
    ) -> tuple[str, float]:
        """Classify and return (type, confidence).

        ISSUE-01 fix: fallback default changed from OBSERVED_FACT to
        'unclassified'. Before this fix, classify() defaulted to
        'unclassified' but classify_with_confidence() defaulted to
        'observed_fact' — the two methods DISAGREED on unclassified text.
        A tentative statement ('we might') was recorded as a directly-
        witnessed fact with 0.0 confidence. This is epistemically wrong
        and internally inconsistent. Now both methods default to
        'unclassified' — they agree.

        Confidence is 0.0 for fallback (no pattern matched).
        """
        if not text or not isinstance(text, str):
            return (fallback if fallback in VALID_TYPES else "unclassified", 0.0)

        for pattern, epistemic_type, confidence in _PATTERNS:
            if pattern.search(text):
                return (epistemic_type, confidence)

        return (fallback if fallback in VALID_TYPES else "unclassified", 0.0)
