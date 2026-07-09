"""
Gmail adapter — extracts personal signals from Gmail messages.

Per revised roadmap v2: Gmail + Calendar adapters. This adapter takes
Gmail message data (from the Gmail API or mock data) and converts it
to PersonalSignal objects that the shell can ingest.

The adapter does NOT call the Gmail API directly — that requires OAuth
credentials configured externally. Instead, it provides:
  - extract_signals_from_message(): converts one Gmail message to signals
  - extract_signals_from_thread(): converts a thread (message + replies)
  - detect_commitments_in_text(): finds "I will..." / "I'll..." patterns

This separation lets us test the extraction logic without real Gmail
credentials, and lets the OAuth wiring be added later without changing
the extraction code.
"""

from __future__ import annotations

import re
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Commitment detection patterns
# ---------------------------------------------------------------------------

# First-person commitment patterns ("I will", "I'll", "I promise", "I'll send")
COMMITMENT_PATTERNS = [
    r"\bI will\b\s+(\w.+)",
    r"\bI'll\b\s+(\w.+)",
    r"\bI promise\b\s+(?:to\s+)?(\w.+)",
    r"\bI'm going to\b\s+(\w.+)",
    r"\bI plan to\b\s+(\w.+)",
    r"\bI aim to\b\s+(\w.+)",
    r"\bI commit to\b\s+(\w.+)",
]

# Follow-up patterns ("following up", "did you get", "any update")
FOLLOWUP_PATTERNS = [
    r"\bfollowing up\b",
    r"\bdid you get\b",
    r"\bany update\b",
    r"\bchecking in\b",
    r"\bcircling back\b",
    r"\bhaven't heard\b",
]

# Deadline patterns ("by Friday", "by EOD", "before next week")
DEADLINE_PATTERNS = [
    r"\bby\b\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
    r"\bby\b\s+(eod|end of day|cob|close of business)",
    r"\bby\b\s+(tomorrow|tonight|next week|end of week)",
    r"\bbefore\b\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
    r"\bdeadline\b",
    r"\bdue\b\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
]

# Meeting change patterns ("moved to", "rescheduled", "postponed")
MEETING_CHANGE_PATTERNS = [
    r"\bmoved\b\s+(?:to|from)\b",
    r"\brescheduled\b",
    r"\bpostponed\b",
    r"\bcancelled\b\s+(?:meeting|sync|call)",
    r"\bnew time\b",
]


def _extract_entity_from_headers(headers: dict[str, str], user_email: str = "me") -> str:
    """Extract the entity (the OTHER party) from email headers.

    For a received email (From != user), the entity is the sender (From).
    For a sent email (From == user), the entity is the recipient (To).
    Falls back to Cc if neither is available.
    """
    def _parse_address(val: str) -> str:
        if not val:
            return ""
        # Try "Name <email>" format
        match = re.match(r'^"?([^"<]+)"?\s*<', val)
        if match:
            return match.group(1).strip()
        # Fall back to email local part
        match = re.match(r'([^\s@]+)@', val)
        if match:
            return match.group(1).strip()
        return val.strip().split(",")[0].strip()

    from_val = headers.get("From", "")
    to_val = headers.get("To", "")
    cc_val = headers.get("Cc", "")

    # If From is NOT the user, the entity is the sender
    from_addr = from_val.lower()
    if user_email.lower() not in from_addr and from_val:
        return _parse_address(from_val)

    # If From IS the user (sent email), the entity is the recipient
    if to_val:
        return _parse_address(to_val)

    # Fall back to Cc
    if cc_val:
        return _parse_address(cc_val)

    return "unknown"


def detect_commitments_in_text(text: str) -> list[dict[str, str]]:
    """Detect commitment patterns in text using CORE's classifier.

    Per auditor finding (caabb7f dilution): this function MUST call Core's
    should_treat_as_commitment + classify_transcript_chunk, NOT reimplement
    commitment detection with regex. The regex patterns are now used ONLY
    for sentence splitting (to extract the commitment text after Core
    confirms it IS a commitment), not for commitment detection itself.

    Returns a list of dicts with:
      - text: the commitment text
      - claim_type: Core's classification (commitment, proposal, etc.)
      - deadline: extracted deadline (if any)
    """
    # Call CORE's classifier — do NOT reimplement
    from maestro_cognitive_council.audit_safety import (
        classify_transcript_chunk,
        should_treat_as_commitment,
    )

    commitments = []

    # Split text into sentences for per-sentence classification
    sentences = re.split(r'[.!?]\s+', text)

    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) < 5:
            continue

        # CORE decides if this is a commitment — not regex
        if not should_treat_as_commitment(sentence):
            continue

        # CORE classifies the claim type (commitment, proposal, etc.)
        claim_type = classify_transcript_chunk(sentence)

        # Extract deadline from the sentence (deadline extraction is NOT
        # a Core capability — it's Personal-specific formatting)
        deadline = None
        for dp in DEADLINE_PATTERNS:
            dmatch = re.search(dp, sentence, re.IGNORECASE)
            if dmatch:
                deadline = dmatch.group(0)
                break

        commitments.append({
            "text": sentence,
            "claim_type": claim_type,
            "deadline": deadline,
        })

    return commitments


# ---------------------------------------------------------------------------


def detect_follow_ups_in_text(text: str) -> bool:
    """Detect if the text is a follow-up (checking in, circling back)."""
    text_lower = text.lower()
    return any(re.search(p, text_lower, re.IGNORECASE) for p in FOLLOWUP_PATTERNS)


def detect_meeting_changes_in_text(text: str) -> list[str]:
    """Detect meeting change patterns in text."""
    text_lower = text.lower()
    changes = []
    for pattern in MEETING_CHANGE_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            changes.append(pattern)
    return changes


def extract_signals_from_message(
    message: dict[str, Any],
    user_email: str = "me",
) -> list[dict[str, Any]]:
    """Extract personal signals from a single Gmail message.

    Args:
        message: Gmail message dict with keys:
            - headers: dict with From, To, Cc, Subject, Date
            - body: str (plain text body)
            - message_id: str
        user_email: the user's email (to determine direction — sent vs received)

    Returns:
        List of signal dicts ready to be converted to PersonalSignal:
          - entity, text, signal_type, timestamp, metadata
    """
    headers = message.get("headers", {})
    body = message.get("body", "")
    msg_id = message.get("message_id", str(uuid4()))
    entity = _extract_entity_from_headers(headers, user_email)

    # Parse timestamp from Date header
    date_str = headers.get("Date", "")
    try:
        from email.utils import parsedate_to_datetime
        timestamp = parsedate_to_datetime(date_str)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
    except Exception:
        timestamp = datetime.now(timezone.utc)

    signals = []

    # Determine if this is sent or received
    from_header = headers.get("From", "").lower()
    is_sent = user_email.lower() in from_header

    # 1. Detect commitments in the body
    commitments = detect_commitments_in_text(body)
    for c in commitments:
        signals.append({
            "entity": entity,
            "text": c["text"],
            "signal_type": "commitment_made" if is_sent else "personal.promise",
            "timestamp": timestamp.isoformat(),
            "metadata": {
                "message_id": msg_id,
                "deadline": c["deadline"],
                "source": "gmail",
                "subject": headers.get("Subject", ""),
            },
        })

    # 2. Detect follow-ups
    if detect_follow_ups_in_text(body):
        signals.append({
            "entity": entity,
            "text": body[:200],
            "signal_type": "follow_up.required",
            "timestamp": timestamp.isoformat(),
            "metadata": {
                "message_id": msg_id,
                "source": "gmail",
                "subject": headers.get("Subject", ""),
            },
        })

    # 3. Detect meeting changes
    meeting_changes = detect_meeting_changes_in_text(body)
    for change in meeting_changes:
        if "cancel" in change:
            sig_type = "meeting.cancelled"
        elif "moved" in change or "rescheduled" in change or "postponed" in change:
            sig_type = "meeting.moved"
        else:
            sig_type = "calendar_change"

        signals.append({
            "entity": entity,
            "text": body[:200],
            "signal_type": sig_type,
            "timestamp": timestamp.isoformat(),
            "metadata": {
                "message_id": msg_id,
                "source": "gmail",
                "subject": headers.get("Subject", ""),
                "change_type": change,
            },
        })

    # 4. If no specific patterns found, create a reported_statement
    if not signals and body.strip():
        signals.append({
            "entity": entity,
            "text": body[:500],
            "signal_type": "reported_statement",
            "timestamp": timestamp.isoformat(),
            "metadata": {
                "message_id": msg_id,
                "source": "gmail",
                "subject": headers.get("Subject", ""),
            },
        })

    return signals


def extract_signals_from_thread(
    thread: list[dict[str, Any]],
    user_email: str = "me",
) -> list[dict[str, Any]]:
    """Extract signals from a Gmail thread (list of messages).

    Threads are useful because they show the evolution of a conversation:
    Day 1: commitment made → Day 3: follow-up → Day 7: meeting moved.
    """
    all_signals = []
    for message in thread:
        signals = extract_signals_from_message(message, user_email)
        all_signals.extend(signals)
    return all_signals
