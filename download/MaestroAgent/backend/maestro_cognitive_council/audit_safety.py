"""
Maestro Cognitive Council — Audit Fix: Falsified pattern tombstone + prompt injection + transcript classification + entity rename + replay timestamp.

Fixes 5 remaining audit findings:
  #7: Falsified pattern still influences advice → tombstone enforcement
  #8: Prompt injection in council routes → defense on council path
  #9: Future information in historical replay → timestamp-bounded retrieval
  #10: Meeting transcript treated as truth → epistemic classification
  #11: Entity resolution fails on renames → fuzzy matching
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# #7: Falsified pattern tombstone — falsified patterns don't influence advice
# ════════════════════════════════════════════════════════════════════════════

def is_falsified(situation: Any) -> bool:
    """Check if a situation's learning state is FALSIFIED.

    Per audit #7: "A pattern declared FALSIFIED after independent
    contradiction continues to appear as precedent in Ask."

    This function provides tombstone enforcement — any surface that
    surfaces a situation as precedent must check this first.
    """
    # Check the 4D learning dimension
    learning_dim = getattr(situation, "learning_dimension", None)
    if learning_dim is not None:
        val = getattr(learning_dim, "value", str(learning_dim))
        if val == "falsified":
            return True

    # Check the legacy learning_state
    learning_state = getattr(situation, "learning_state", None)
    if learning_state is not None:
        val = getattr(learning_state, "value", str(learning_state))
        if val in ("falsified", "FALSIFIED"):
            return True

    return False


def filter_falsified_situations(situations: list) -> list:
    """Filter out falsified situations from a list.

    Per audit #7: falsified patterns must NOT influence advice.
    This is the tombstone enforcement point.
    """
    return [s for s in situations if not is_falsified(s)]


# ════════════════════════════════════════════════════════════════════════════
# #8: Prompt injection defense for council routes
# ════════════════════════════════════════════════════════════════════════════

def check_prompt_injection(text: str) -> tuple[bool, str]:
    """Check if text contains prompt injection patterns.

    Per audit #8: "Untrusted source text can influence classification
    and routing."

    Returns (is_injected, reason).
    """
    if not text:
        return False, ""

    text_lower = text.lower()

    injection_patterns = [
        ("ignore prior", "Instruction to ignore prior context"),
        ("ignore previous", "Instruction to ignore previous instructions"),
        ("ignore all", "Instruction to ignore all instructions"),
        ("disregard the above", "Instruction to disregard prior context"),
        ("you are now", "Identity manipulation attempt"),
        ("new instructions:", "Instruction injection attempt"),
        ("system prompt:", "System prompt extraction attempt"),
        ("forget everything", "Memory wipe attempt"),
        ("override", "Override attempt"),
        ("escalate to ceo", "Routing manipulation via injection"),
        ("route to", "Routing manipulation via injection"),
        ("act as if", "Role manipulation attempt"),
    ]

    for pattern, reason in injection_patterns:
        if pattern in text_lower:
            logger.warning(
                "PROMPT INJECTION DETECTED: pattern='%s' reason='%s' text='%.80s'",
                pattern, reason, text,
            )
            return True, reason

    return False, ""


def sanitize_signal_for_council(signal: Any) -> Any:
    """Sanitize a signal before the Cognitive Council processes it.

    Per audit #8: council routes don't go through the same prompt
    injection defense as the OEM path. This function provides that defense.
    """
    text = getattr(signal, "text", "") or ""
    is_injected, reason = check_prompt_injection(text)

    if is_injected:
        # Tag the signal as prompt-injected (OutcomeResolver will skip it)
        if not hasattr(signal, "metadata") or signal.metadata is None:
            signal.metadata = {}
        signal.metadata["prompt_injection_risk"] = True
        signal.metadata["injection_reason"] = reason
        logger.info("Signal %s tagged as prompt-injected: %s",
                     getattr(signal, "signal_id", "unknown"), reason)

    return signal


# ════════════════════════════════════════════════════════════════════════════
# #9: Timestamp-bounded retrieval for historical replay
# ════════════════════════════════════════════════════════════════════════════

def filter_signals_by_timestamp(
    signals: list,
    as_of: datetime,
) -> list:
    """Filter signals to only those that existed at or before `as_of`.

    Per audit #9: "At Day 20 replay, evidence tagged Day 45 surfaces
    in retrieval context. Replay is not strictly timestamp-bounded."

    This function provides the timestamp boundary.
    """
    result = []
    for sig in signals:
        sig_time = getattr(sig, "timestamp", None)
        if sig_time is None:
            continue
        if not isinstance(sig_time, datetime):
            try:
                sig_time = datetime.fromisoformat(str(sig_time).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
        if sig_time <= as_of:
            result.append(sig)
    return result


# ════════════════════════════════════════════════════════════════════════════
# #10: Meeting transcript epistemic classification
# ════════════════════════════════════════════════════════════════════════════

def classify_transcript_chunk(text: str) -> str:
    """Classify a meeting transcript chunk by epistemic type.

    Per audit #10: "Sarcasm and hedging in meeting transcripts are
    recorded as commitments. No epistemic downgrade for transcription
    uncertainty."

    Returns the epistemic type: "observed_fact", "reported_statement",
    "commitment", "tentative", "sarcasm", or "unclassified".
    """
    if not text:
        return "unclassified"

    text_lower = text.lower()

    # Sarcasm patterns
    sarcasm_markers = ["sure, right", "oh great", "just perfect", "that's just great",
                       "yeah, because that worked so well", "thanks a lot"]
    for marker in sarcasm_markers:
        if marker in text_lower:
            return "sarcasm"

    # Hedging / tentative
    tentative_markers = ["maybe", "might", "possibly", "i think", "perhaps",
                         "we could", "we might", "i'm not sure", "probably"]
    for marker in tentative_markers:
        if marker in text_lower:
            return "tentative"

    # Commitment — includes first-person AND third-person forms
    # Third-person forms catch connector-ingested commitments like
    # "Alex committed to delivering the design review by Wednesday"
    commitment_markers = [
        # First-person
        "i will", "we will", "i'll", "we'll", "i promise", "we promise",
        "i commit to", "we commit to", "i'm going to", "i need to",
        # Third-person (from connector ingestion)
        "committed to", "promised to", "agreed to", "will deliver",
        "will send", "will follow up", "will finalize", "will review",
        "will complete", "will provide", "will share",
        # Generic commitment patterns
        "commit to", "promise", "deliver by", "ship by", "by friday",
        "by monday", "by tuesday", "by wednesday", "by thursday",
        "by the end of", "deadline",
    ]
    for marker in commitment_markers:
        if marker in text_lower:
            return "commitment"

    # Reported statement (someone said something)
    reported_markers = ["he said", "she said", "they said", "according to",
                        "i heard", "the customer said"]
    for marker in reported_markers:
        if marker in text_lower:
            return "reported_statement"

    # Observed fact (past tense, factual)
    fact_markers = ["we shipped", "we deployed", "the test passed", "the build failed",
                    "we completed", "we finished"]
    for marker in fact_markers:
        if marker in text_lower:
            return "observed_fact"

    return "unclassified"


def should_treat_as_commitment(text: str) -> bool:
    """Should this transcript text be treated as a commitment?

    Per audit #10: only classify as commitment if it's NOT sarcasm
    or tentative. Sarcasm and hedging should be downgraded.
    """
    epistemic_type = classify_transcript_chunk(text)
    return epistemic_type == "commitment"


# ════════════════════════════════════════════════════════════════════════════
# #11: Entity rename detection
# ════════════════════════════════════════════════════════════════════════════

def entities_likely_renamed(
    entity_a: str,
    entity_b: str,
    shared_signals: list,
    threshold: float = 0.7,
) -> bool:
    """Check if two entity names are likely a rename of the same entity.

    Per audit #11: "Project 'Helios' renamed to 'Helios-2' creates a new
    situation. Historical continuity breaks."

    This function checks:
      1. Name similarity (e.g., "Helios" vs "Helios-2" = 87% similar)
      2. Shared signal text (if 70%+ of signals mention both names, likely rename)

    Args:
        entity_a: first entity name
        entity_b: second entity name
        shared_signals: signals that mention either entity
        threshold: similarity threshold (0.0-1.0)

    Returns True if likely a rename.
    """
    # Check name similarity
    name_similarity = SequenceMatcher(None, entity_a.lower(), entity_b.lower()).ratio()
    # For short names (≤12 chars), require higher threshold (0.85) to avoid
    # false positives like "CustomerA" vs "CustomerB" (89% similar)
    min_len = min(len(entity_a), len(entity_b))
    effective_threshold = 0.85 if min_len <= 12 else threshold
    if name_similarity >= effective_threshold:
        # But exclude cases where only the last char differs (A vs B, 1 vs 2)
        if entity_a.lower()[:-1] == entity_b.lower()[:-1] and \
           entity_a.lower()[-1] != entity_b.lower()[-1]:
            return False  # "CustomerA" vs "CustomerB" — different entities
        return True

    # Check if one name is a substring of the other (common rename pattern)
    if entity_a.lower() in entity_b.lower() or entity_b.lower() in entity_a.lower():
        return True

    # Check shared signal text
    if shared_signals:
        texts_a = set()
        texts_b = set()
        for sig in shared_signals:
            text = (getattr(sig, "text", "") or "").lower()
            if entity_a.lower() in text:
                texts_a.add(text[:100])
            if entity_b.lower() in text:
                texts_b.add(text[:100])

        # If 70%+ of texts mention both entities, likely a rename
        if texts_a and texts_b:
            overlap = len(texts_a & texts_b)
            smaller = min(len(texts_a), len(texts_b))
            if smaller > 0 and (overlap / smaller) >= threshold:
                return True

    return False


def find_renamed_entity(
    new_entity: str,
    existing_entities: list[str],
    signals: list,
) -> Optional[str]:
    """Find if a new entity name is a rename of an existing entity.

    Returns the existing entity name if a rename is detected, None otherwise.
    """
    for existing in existing_entities:
        if existing.lower() == new_entity.lower():
            continue  # exact match, not a rename
        if entities_likely_renamed(new_entity, existing, signals):
            logger.info(
                "ENTITY RENAME DETECTED: '%s' appears to be a rename of '%s'",
                new_entity, existing,
            )
            return existing
    return None
