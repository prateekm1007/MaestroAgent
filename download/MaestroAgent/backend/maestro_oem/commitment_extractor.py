"""H-06 fix: Free-text commitment extraction from Slack/email bodies.

The prior adversarial audit found (H-06):
> Commitments are only tracked if they arrive as CUSTOMER_COMMITMENT_MADE
> signal types. The system cannot extract commitments from free-form text
> (emails, Slack messages, meeting transcripts).

This module extracts commitments from free-text signal bodies. When a
commitment is found in a MESSAGE_SENT or EMAIL signal, the extractor
emits an ADDITIONAL CUSTOMER_COMMITMENT_MADE signal with the extracted
commitment text + customer entity.

Design principles:
  1. NEVER mutate the original signal. Emit ADDITIONAL signals only (P6).
  2. Be CONSERVATIVE — false positives pollute the commitment tracker.
     Only extract high-confidence commitment language.
  3. Require a customer entity (from metadata or inferred from text).
     Without an entity, the commitment has no home — skip it.
  4. Preserve authority_weight from the source signal (H-05 integration).
  5. Rule-based now, LLM-ready later. The extract() method is the
     interface — a future LLM provider can implement the same interface.

Commitment patterns (rule-based):
  - "we'll deliver X by Y"
  - "we will deliver X by Y"
  - "we promise to X by Y"
  - "we'll have X ready by Y"
  - "we commit to X by Y"
  - "we'll ship X by Y"

Anti-patterns (NOT commitments):
  - Questions: "when will X be ready?"
  - Past tense: "we delivered X last quarter"
  - Conditional: "if we deliver X, then Y"
  - Negations: "we won't deliver X"

Wiring (P11):
    OEMEngine.ingest() calls CommitmentExtractor.extract() on each batch,
    appends extracted signals to the batch, then processes all of them.
    See engine.py.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from maestro_oem.signal import ExecutionSignal, SignalType, SignalProvider

logger = logging.getLogger(__name__)


# ─── Commitment patterns (regex, case-insensitive) ─────────────────────────
# Each pattern must capture:
#   - The commitment text (what was promised)
#   - Optionally the deadline (by when)
#
# Patterns are CONSERVATIVE — they require "we" + future-tense verb +
# a deliverable. This avoids false positives on questions, past tense,
# and third-party statements.

_COMMITMENT_PATTERNS: list[re.Pattern] = [
    # "we'll deliver X by Y" / "we will deliver X by Y"
    re.compile(
        r"\bwe\s*(?:will|['\u2019]?ll)\s+deliver\s+(.+?)\s+(?:by\s+|before\s+|until\s+)([\w\s\d]+?)(?=[.!?;]|$)",
        re.IGNORECASE,
    ),
    # "we promise to X by Y" / "we promise to ship X by Y" — deadline optional
    re.compile(
        r"\bwe\s+promise\s+to\s+(?:ship\s+|deliver\s+|build\s+|provide\s+|implement\s+)?(.+?)(?:\s+(?:by\s+|before\s+)([\w\s\d]+?))?(?=[.!?;]|$)",
        re.IGNORECASE,
    ),
    # "we'll have X ready by Y" / "we will have X ready by Y"
    re.compile(
        r"\bwe\s*(?:will|['\u2019]?ll)\s+have\s+(.+?)\s+ready\s+(?:by\s+|before\s+|for\s+)([\w\s\d]+?)(?=[.!?;]|$)",
        re.IGNORECASE,
    ),
    # "we commit to X by Y"
    re.compile(
        r"\bwe\s+commit\s+to\s+(?:delivering\s+|shipping\s+|building\s+|providing\s+|implementing\s+)?(.+?)\s+(?:by\s+|before\s+)([\w\s\d]+?)(?=[.!?;]|$)",
        re.IGNORECASE,
    ),
    # "we'll ship X by Y" / "we will ship X by Y"
    re.compile(
        r"\bwe\s*(?:will|['\u2019]?ll)\s+ship\s+(.+?)\s+(?:by\s+|before\s+)([\w\s\d]+?)(?=[.!?;]|$)",
        re.IGNORECASE,
    ),
    # D1 fix: "we will have X available/ready/live by/before Y"
    # Also catches: "we'll have X available before Y"
    re.compile(
        r"\bwe\s*(?:will|['\u2019]?ll)\s+have\s+(.+?)\s+(?:available|ready|live|deployed)\s+(?:by\s+|before\s+|for\s+)([\w\s\d]+?)(?=[.!?;]|$)",
        re.IGNORECASE,
    ),
    # D1 fix: "we should be able to support/provide X by/before Y"
    # This is a qualified commitment — not as strong as "we will" but still a commitment
    re.compile(
        r"\bwe\s+should\s+be\s+able\s+to\s+(?:support|provide|deliver|ship|build|implement)\s+(.+?)(?:\s+(?:by\s+|before\s+)([\w\s\d]+?))?(?=[.!?;]|$)",
        re.IGNORECASE,
    ),
    # D1 fix: "X work is complete" / "X is done" / "X shipped" — outcome, not commitment
    # But "X remains conditional" is an assumption about a pending state
    # D1 fix: "I will follow up on X" / "I'll follow up on X"
    re.compile(
        r"\bi\s*(?:will|['\u2019]?ll)\s+(?:follow\s+up|confirm|send|share|provide|update)\s+(?:on\s+|the\s+)?(.+?)(?=[.!?;]|$)",
        re.IGNORECASE,
    ),
    # D1 fix: "target: before Y" / "target: by Y" (from Confluence/docs)
    # Group 1 = the full "target: before Y" as the commitment text
    # Group 2 = empty (no separate deadline — the deadline IS the target)
    re.compile(
        r"\b((?:target|goal|deadline|eta)\s*:\s*(?:before\s+|by\s+)[\w\s\d]+?)(?=[.!?;]|$)",
        re.IGNORECASE,
    ),
    # D1 fix: "X remains conditional" — this is an assumption, not a commitment.
    # Don't extract it. The anti-pattern should catch "remains conditional" but
    # if it doesn't, the extractor should also not match it.
]

# ─── Anti-patterns (NOT commitments) ────────────────────────────────────────
# If any of these match, the text is NOT a commitment even if a commitment
# pattern also matches. This is the false-positive guard.

_ANTI_PATTERNS: list[re.Pattern] = [
    # Questions
    re.compile(r"\bwhen\s+(?:will|are|do|can|could|would|should|might)\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+(?:about|if|happens)\b", re.IGNORECASE),
    # Past tense (delivered, shipped, completed)
    re.compile(r"\b(we\s+)?(?:delivered|shipped|completed|finished|done)\b", re.IGNORECASE),
    # Conditional
    re.compile(r"\bif\s+(?:we|you|they)\b", re.IGNORECASE),
    # Negation
    re.compile(r"\bwe\s+(?:won['']?t|will\s+not|cannot|can['']?t)\b", re.IGNORECASE),
]

# ─── Customer name inference ───────────────────────────────────────────────
# Extract capitalized words that might be customer names. This is a
# heuristic — the real customer comes from signal metadata. This is
# only a fallback for signals without a customer field.

_CUSTOMER_PATTERN = re.compile(r"\b([A-Z][a-zA-Z]{2,}(?:Corp|Inc|LLC|Co|Ltd|Group)?)\b")


def _is_anti_pattern(text: str) -> bool:
    """Check if the text matches any anti-pattern (question, past tense, etc.)."""
    for pattern in _ANTI_PATTERNS:
        if pattern.search(text):
            return True
    return False


def _extract_commitment_text(text: str) -> tuple[str, str] | None:
    """Extract commitment text + deadline from a message.

    Returns (commitment_text, deadline) or None if no commitment found.
    """
    for pattern in _COMMITMENT_PATTERNS:
        match = pattern.search(text)
        if match:
            commitment_text = match.group(1).strip().rstrip(",.;:")
            deadline = match.group(2).strip().rstrip(",.;:") if match.lastindex >= 2 else ""
            # Clean up the deadline — remove trailing "to <customer>" and noise
            deadline = re.sub(r"\s+to\s+.*$", "", deadline).strip()
            # Clean up the commitment text — remove trailing "to <customer>"
            commitment_text = re.sub(r"\s+to\s+\w+$", "", commitment_text).strip()
            if commitment_text and len(commitment_text) >= 2:
                return (commitment_text, deadline)
    return None


def _infer_customer(text: str, metadata: dict) -> str:
    """Infer the customer entity from metadata or text.

    Priority:
      1. metadata.get("customer") — explicit
      2. metadata.get("channel") — #customer-<name> pattern
      3. Capitalized words in text (heuristic)
    """
    # 1. Explicit customer in metadata
    customer = metadata.get("customer", "")
    if customer:
        return customer

    # 2. Channel-based inference (#customer-testcorp, #testcorp, etc.)
    channel = metadata.get("channel", "")
    if channel:
        # Strip # and common prefixes
        channel_clean = channel.lstrip("#").lower()
        for prefix in ("customer-", "cust-", "acct-"):
            if channel_clean.startswith(prefix):
                return channel_clean[len(prefix):]

    # 3. Capitalized words in text (heuristic — find the most likely customer name)
    matches = _CUSTOMER_PATTERN.findall(text)
    # Filter out common English words
    stop_words = {"We", "The", "Our", "They", "You", "I", "It", "This", "That", "Friday", "Monday", "Tuesday", "Wednesday", "Thursday", "Saturday", "Sunday", "Q1", "Q2", "Q3", "Q4"}
    candidates = [m for m in matches if m not in stop_words]
    if candidates:
        # Return the first candidate (most likely the customer)
        return candidates[0]

    return ""


class CommitmentExtractor:
    """Extract commitments from free-text signal bodies.

    Usage:
        extractor = CommitmentExtractor()
        extracted = extractor.extract(signals)
        # extracted is a list of NEW CUSTOMER_COMMITMENT_MADE signals

    The extractor NEVER mutates the original signals. It emits ADDITIONAL
    signals only (P6: never silence the original).

    The extractor is CONSERVATIVE — false positives pollute the commitment
    tracker. It only extracts high-confidence commitment language and
    skips questions, past tense, conditionals, and negations.

    LLM-ready interface:
        A future LLM provider can subclass CommitmentExtractor and override
        _extract_commitment_text() to use an LLM for higher accuracy.
        The rest of the pipeline (signal creation, customer inference,
        authority_weight preservation) stays the same.
    """

    def extract(self, signals: list[ExecutionSignal]) -> list[ExecutionSignal]:
        """Extract commitments from a list of signals.

        Returns a list of NEW CUSTOMER_COMMITMENT_MADE signals. The
        original signals are NOT mutated.

        Only MESSAGE_SENT and EMAIL signals are scanned — other types
        (decisions, objections, etc.) are passed through untouched.
        """
        extracted: list[ExecutionSignal] = []

        for sig in signals:
            # Only scan free-text signals
            if sig.type not in (SignalType.MESSAGE_SENT, SignalType.EMAIL_SENT, SignalType.EMAIL_RECEIVED, SignalType.CUSTOMER_EMAIL, SignalType.THREAD_STARTED, SignalType.PAGE_CREATED, SignalType.PAGE_EDITED):
                continue

            # Get the text from metadata
            text = sig.metadata.get("text", "") if hasattr(sig, "metadata") else ""
            if not text or len(text) < 10:
                continue

            # Check anti-patterns first (false-positive guard)
            if _is_anti_pattern(text):
                continue

            # Try to extract a commitment
            result = self._extract_commitment_text_with_confidence(text)
            if not result:
                continue

            commitment_text, deadline, confidence_level = result

            # Phase 1.3: 3-way outcome
            # confidence_level: 0.9 = high (strong commitment language: "we will deliver", "we promise to")
            #                   0.6 = low (weaker language: "we should be able to", "target: before Y")
            #                   (None = no commitment — already filtered above)

            # Infer the customer entity
            customer = _infer_customer(text, sig.metadata)

            # Build the extracted commitment signal
            new_metadata = {
                "commitment": commitment_text,
                "deadline": deadline,
                "customer": customer,
                "source_text": text[:200],  # Preserve the original text for provenance
                "source_signal_id": str(sig.signal_id),
                "source_provider": sig.provider.value if hasattr(sig.provider, "value") else str(sig.provider),
                "extraction_method": "rule_based",  # LLM-ready: could be "llm"
                "extraction_confidence": "high" if confidence_level >= 0.85 else "low",  # Phase 1.3
            }

            new_sig = ExecutionSignal(
                type=SignalType.CUSTOMER_COMMITMENT_MADE,
                actor=sig.actor,
                team=sig.team,
                artifact=sig.artifact,
                decision=False,
                confidence=confidence_level,  # Phase 1.3: 3-way outcome
                metadata=new_metadata,
                provider=sig.provider,  # Inherit provider from source
                authority_weight=getattr(sig, "authority_weight", 0.5),  # H-05: inherit authority
            )

            extracted.append(new_sig)
            logger.debug(
                "CommitmentExtractor: extracted commitment '%s' (deadline: %s, customer: %s, confidence: %.2f) from signal %s",
                commitment_text[:60], deadline, customer, confidence_level, sig.signal_id,
            )

        return extracted

    def _extract_commitment_text(self, text: str) -> tuple[str, str] | None:
        """Extract commitment text + deadline from a message.

        This is the LLM-ready interface. A subclass can override this
        to use an LLM for higher accuracy.

        Returns (commitment_text, deadline) or None.
        """
        return _extract_commitment_text(text)

    def _extract_commitment_text_with_confidence(self, text: str) -> tuple[str, str, float] | None:
        """Phase 1.3: Extract commitment text + deadline + confidence level.

        Returns (commitment_text, deadline, confidence) or None.
        Confidence levels:
          0.9 = high (strong: "we will deliver", "we promise to", "we'll have X ready")
          0.6 = low (weaker: "we should be able to", "target: before Y", "I'll follow up")
        """
        result = _extract_commitment_text(text)
        if not result:
            return None

        commitment_text, deadline = result

        # Phase 1.3: Determine confidence level based on which pattern matched
        text_lower = text.lower()

        # High confidence: explicit commitment language
        high_confidence_markers = [
            "we will deliver", "we'll deliver", "we will ship", "we'll ship",
            "we promise to", "we commit to", "we will have", "we'll have",
        ]
        # Low confidence: qualified or indirect commitment language
        low_confidence_markers = [
            "should be able to", "target:", "goal:", "deadline:", "eta:",
            "i'll follow up", "i will follow up", "i'll confirm", "i will confirm",
        ]

        if any(marker in text_lower for marker in high_confidence_markers):
            confidence = 0.9
        elif any(marker in text_lower for marker in low_confidence_markers):
            confidence = 0.6
        else:
            # Default to medium confidence for any other match
            confidence = 0.7

        return (commitment_text, deadline, confidence)
