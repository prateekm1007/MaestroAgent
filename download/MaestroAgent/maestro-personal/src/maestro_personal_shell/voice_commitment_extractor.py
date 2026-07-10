"""
Voice transcript implicit commitment extractor.

CEO Directive 3: Extract implicit commitments from voice transcripts.

Voice conversations contain implicit commitments that text-based
classifiers miss:
- "Let me take that" → implicit commitment
- "I'll own the follow-up" → implicit commitment
- "You'll have the numbers by Friday?" → implicit commitment (question form)
- "We're good for Tuesday" → implicit commitment
- "That's on me" → implicit commitment

This module processes transcript chunks and extracts commitments using
the commitment_classifier + voice-specific patterns.
"""

from __future__ import annotations

import logging
from typing import Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# Voice-specific commitment patterns (beyond text-based patterns)
# These are phrases that commonly appear in spoken conversation but
# may not appear in email/text.
VOICE_COMMITMENT_PATTERNS = [
    # Taking ownership
    "let me take that", "let me handle that", "let me take care of that",
    "i'll own that", "i'll own the", "that's on me", "i'm on it",
    "i'll take the lead on", "i'll drive that", "i'll spearhead",

    # Confirmation commitments
    "consider it done", "you got it", "you'll have it", "we're good for",
    "we are good for", "count on it", "absolutely", "for sure",
    "will do", "you bet", "sure thing", "no problem",

    # Question-form commitments (speaker commits by answering)
    "you'll have the", "you'll get the", "i can get that",
    "i can have that", "i can do that", "i can make that",

    # Time-based commitments
    "by end of day", "by tomorrow", "by friday", "by monday",
    "by next week", "by the end of the week", "first thing tomorrow",
    "by close of business", "by eod", "by cob",

    # Follow-up commitments
    "i'll follow up", "i'll circle back", "i'll loop back",
    "i'll get back to you", "i'll reach out", "i'll connect you",
    "i'll introduce you", "i'll set up a call", "i'll schedule",

    # Delivery commitments
    "i'll send over", "i'll share", "i'll pass along", "i'll forward",
    "i'll circulate", "i'll distribute", "i'll send out",

    # Review/approval commitments
    "i'll review", "i'll check", "i'll verify", "i'll look into",
    "i'll investigate", "i'll assess", "i'll evaluate",
]


def extract_commitments_from_transcript(
    transcript_chunks: list[dict[str, str]],
    meeting_entity: str = "",
) -> list[dict[str, Any]]:
    """Extract implicit commitments from voice transcript chunks.

    Args:
        transcript_chunks: [{"speaker": "...", "text": "...", "timestamp": "..."}]
        meeting_entity: The entity/person this meeting is with

    Returns: List of commitment signal dicts ready for ingestion
    """
    commitments = []

    for chunk in transcript_chunks:
        text = chunk.get("text", "")
        speaker = chunk.get("speaker", "")
        timestamp = chunk.get("timestamp", datetime.now(timezone.utc).isoformat())

        if not text or len(text) < 5:
            continue

        text_lower = text.lower()

        # Check for voice commitment patterns
        matched_patterns = [p for p in VOICE_COMMITMENT_PATTERNS if p in text_lower]

        if not matched_patterns:
            continue

        # Use the commitment classifier for type detection
        try:
            from maestro_personal_shell.commitment_classifier import _rule_based_classify
            classification = _rule_based_classify(text, meeting_entity)
        except Exception:
            classification = {
                "commitment_type": "implicit",
                "is_commitment": True,
                "confidence": 0.7,
                "state": "active",
                "owner": speaker or "unknown",
            }

        # Only extract if it's a commitment
        if not classification.get("is_commitment", False):
            # Check if voice patterns matched but classifier says no
            # Voice patterns are more aggressive — override for implicit
            if matched_patterns:
                classification = {
                    "commitment_type": "implicit",
                    "is_commitment": True,
                    "confidence": 0.7,
                    "state": "active",
                    "owner": speaker or "unknown",
                    "reasoning": f"voice pattern: {matched_patterns[0]}",
                    "llm_powered": False,
                }
            else:
                continue

        # Extract deadline if present
        deadline_text = _extract_deadline(text_lower)

        # Build the signal
        signal = {
            "entity": meeting_entity or speaker or "unknown",
            "text": text.strip(),
            "signal_type": "commitment_made",
            "timestamp": timestamp,
            "metadata": {
                "source": "voice_transcript",
                "speaker": speaker,
                "commitment_type": classification.get("commitment_type", "implicit"),
                "is_commitment": True,
                "commitment_state": classification.get("state", "active"),
                "commitment_confidence": classification.get("confidence", 0.7),
                "commitment_owner": classification.get("owner", speaker),
                "matched_patterns": matched_patterns[:3],
                "deadline_text": deadline_text,
                "classification_reasoning": classification.get("reasoning", ""),
            },
            "source_acl": "private",
        }

        commitments.append(signal)

    return commitments


def _extract_deadline(text_lower: str) -> str:
    """Extract deadline text from a commitment."""
    deadline_patterns = [
        "by end of day", "by eod", "by cob", "by close of business",
        "by tomorrow", "by friday", "by monday", "by tuesday",
        "by wednesday", "by thursday", "by the weekend",
        "by next week", "by next month",
        "first thing tomorrow", "first thing in the morning",
        "end of the week", "end of week",
        "this afternoon", "this evening", "tonight",
        "before the meeting", "before the call",
    ]

    for pattern in deadline_patterns:
        if pattern in text_lower:
            return pattern

    return ""


def process_meeting_transcript(
    transcript: list[dict[str, str]],
    meeting_entity: str = "",
) -> dict[str, Any]:
    """Process a full meeting transcript and extract all intelligence.

    Returns:
    {
        "commitments": [extracted commitments],
        "completion_signals": [detected completions],
        "requests": [detected requests],
        "action_items": [detected action items],
        "summary": "brief meeting summary",
    }
    """
    commitments = extract_commitments_from_transcript(transcript, meeting_entity)

    # Detect completion signals
    completion_signals = []
    request_signals = []

    for chunk in transcript:
        text = chunk.get("text", "").lower()
        speaker = chunk.get("speaker", "")

        # Completion detection
        completion_keywords = ["sent", "delivered", "completed", "done", "finished", "shipped"]
        negation = any(n in text for n in ["never", "didn't", "not ", "haven't", "won't", "will not"])
        if any(kw in text for kw in completion_keywords) and not negation:
            completion_signals.append({
                "text": chunk.get("text", ""),
                "speaker": speaker,
                "timestamp": chunk.get("timestamp", ""),
            })

        # Request detection
        request_patterns = ["can you", "could you", "would you", "need you to", "please"]
        if any(p in text for p in request_patterns):
            request_signals.append({
                "text": chunk.get("text", ""),
                "speaker": speaker,
                "timestamp": chunk.get("timestamp", ""),
            })

    # Build summary
    total_items = len(commitments) + len(completion_signals) + len(request_signals)
    summary = (
        f"Meeting with {meeting_entity or 'participant'}: "
        f"{len(commitments)} commitments, "
        f"{len(completion_signals)} completions, "
        f"{len(request_signals)} requests."
        if total_items > 0
        else f"Meeting with {meeting_entity or 'participant'}: no actionable items detected."
    )

    return {
        "commitments": commitments,
        "completion_signals": completion_signals,
        "requests": request_signals,
        "action_items": len(commitments) + len(request_signals),
        "summary": summary,
    }
