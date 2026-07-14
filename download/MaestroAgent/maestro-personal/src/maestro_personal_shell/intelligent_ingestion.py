"""
Intelligent ingestion — combines regex candidate detection with LLM classification.

This module bridges the gap between the regex-based detect_commitments_in_text()
(which catches "I will..." patterns) and the LLM-powered classify_commitment()
(which determines if a candidate is really a commitment, and what type).

The result: high-precision ingestion that catches explicit + implicit commitments,
rejects tentative/proposal/aspiration, and assigns lifecycle state.
"""

from __future__ import annotations

import logging
from typing import Any

from maestro_personal_shell.signal_adapters.gmail import detect_commitments_in_text
from maestro_personal_shell.commitment_classifier import classify_commitment

logger = logging.getLogger(__name__)


async def extract_signals_intelligently(
    message_text: str,
    entity: str = "",
    source: str = "gmail",
    timestamp: str = "",
) -> list[dict[str, Any]]:
    """Extract commitments using regex + LLM classification.

    Args:
        message_text: The raw text from an email, Slack message, or issue body.
        entity: The entity (person/company) this message is about.
        source: "gmail", "slack", "github", or "manual".
        timestamp: ISO timestamp of the original message.

    Returns:
        List of signal dicts ready for ingestion. Each dict has:
        - entity, text, signal_type, commitment_type, state, confidence, timestamp, source
    """
    # Step 1: Regex finds candidates
    candidates = detect_commitments_in_text(message_text)

    if not candidates:
        return []

    signals = []
    for candidate in candidates:
        candidate_text = candidate.get("text", "")

        # Step 2: LLM classifies each candidate
        try:
            classification = await classify_commitment(
                text=candidate_text,
                entity=entity,
                context=message_text[:500],
            )
        except Exception as e:
            logger.warning("LLM classification failed, using regex-only: %s", e)
            classification = {
                "commitment_type": "explicit",
                "is_commitment": True,
                "confidence": 0.5,
                "state": "active",
            }

        # Step 3: Only ingest if it's a real commitment
        commitment_type = classification.get("commitment_type", "explicit")
        is_commitment = classification.get("is_commitment", True)

        # Reject non-commitments, tentative, aspirations, and proposals
        REJECT_TYPES = {"not_a_commitment", "tentative", "aspiration", "proposal"}

        if not is_commitment or commitment_type in REJECT_TYPES:
            logger.debug(
                "Rejected candidate (type=%s): %s",
                commitment_type, candidate_text[:80]
            )
            continue

        # Step 4: Build the signal with classification metadata
        signal = {
            "entity": entity or candidate.get("entity", ""),
            "text": candidate_text,
            "signal_type": "commitment_made",
            "commitment_type": commitment_type,
            "state": classification.get("state", "active"),
            "confidence": classification.get("confidence", 0.5),
            "timestamp": timestamp or candidate.get("timestamp", ""),
            "source": source,
            "metadata": {
                "classification": commitment_type,
                "classifier_confidence": classification.get("confidence", 0.5),
            },
        }

        # Handle negations and completions
        if commitment_type == "negation":
            signal["signal_type"] = "reported_statement"
            signal["state"] = "cancelled"
        elif commitment_type == "completed":
            signal["signal_type"] = "reported_statement"
            signal["state"] = "completed_verified"
        elif commitment_type == "disputed":
            signal["signal_type"] = "reported_statement"
            signal["state"] = "disputed"

        signals.append(signal)

    return signals
