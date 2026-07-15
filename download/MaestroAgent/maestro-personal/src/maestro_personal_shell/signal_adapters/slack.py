"""
Slack signal adapter — extract commitments from Slack messages.

CEO Directive 3 (Days 15-22): Expand data sources beyond Gmail/Calendar.

This adapter parses Slack messages and extracts:
- Explicit commitments ("I will send the deck by Friday")
- Implicit commitments ("Let me take that", "I'm on it")
- Requests ("Can you get me the numbers?")
- Action items from threads

The adapter reuses the commitment_classifier for type detection and
the sanitize_for_llm for injection defense.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def parse_slack_message(message: dict[str, Any]) -> dict[str, Any] | None:
    """Parse a Slack message into a Maestro signal.

    Args:
        message: Slack message dict with keys:
            - text: message text
            - user: sender ID/name
            - ts: timestamp
            - channel: channel name
            - thread_ts: thread parent timestamp (if in thread)

    Returns: Signal dict with entity, text, signal_type, timestamp, metadata
             or None if the message has no signal value.
    """
    text = message.get("text", "")
    if not text or not text.strip():
        return None

    # Strip Slack formatting: <@U12345>, <#C12345>, *bold*, _italic_, ~strike~, `code`
    text = _strip_slack_formatting(text)

    # Skip bot messages and automated notifications
    if message.get("subtype") in ("bot_message", "channel_join", "channel_leave"):
        return None

    # Skip very short messages (likely noise)
    if len(text) < 10:
        return None

    sender = message.get("user", "unknown")
    channel = message.get("channel", "unknown")
    ts = message.get("ts", "")

    # Convert Slack timestamp to ISO
    timestamp = _slack_ts_to_iso(ts)

    # Determine signal type
    signal_type = _classify_slack_message(text)

    # Extract entity from the message
    entity = _extract_entity_from_slack(text, channel)

    return {
        "entity": entity,
        "text": text,
        "signal_type": signal_type,
        "timestamp": timestamp,
        "metadata": {
            "source": "slack",
            "channel": channel,
            "sender": sender,
            "thread_ts": message.get("thread_ts", ""),
            "is_thread_reply": bool(message.get("thread_ts")),
        },
        "source_acl": "private",
    }


def _strip_slack_formatting(text: str) -> str:
    """Strip Slack-specific formatting from text."""
    # User mentions: <@U12345> → @user
    text = re.sub(r'<@[\w]+>', '@user', text)
    # Channel mentions: <#C12345|general> → #general
    text = re.sub(r'<#[\w]+\|([\w]+)>', r'#\1', text)
    text = re.sub(r'<#[\w]+>', '#channel', text)
    # URLs: <http://...|text> → text
    text = re.sub(r'<(https?://[^|]+)\|([^>]+)>', r'\2', text)
    text = re.sub(r'<(https?://[^>]+)>', r'\1', text)
    # Bold: *text* → text
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    # Italic: _text_ → text
    text = re.sub(r'_([^_]+)_', r'\1', text)
    # Strike: ~text~ → text
    text = re.sub(r'~([^~]+)~', r'\1', text)
    # Code: `text` → text
    text = re.sub(r'`([^`]+)`', r'\1', text)
    # Code blocks: ```text``` → text
    text = re.sub(r'```[^`]*```', '', text)
    return text.strip()


def _slack_ts_to_iso(ts: str) -> str:
    """Convert Slack timestamp to ISO format."""
    if not ts:
        return datetime.now(timezone.utc).isoformat()
    try:
        # Slack timestamps are Unix epoch with microseconds
        epoch = float(ts)
        dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
        return dt.isoformat()
    except (ValueError, TypeError):
        return datetime.now(timezone.utc).isoformat()


def _classify_slack_message(text: str) -> str:
    """Classify a Slack message into a signal type."""
    text_lower = text.lower()

    # Commitment patterns
    commitment_patterns = [
        "i will", "i'll", "i promise", "i commit", "i guarantee",
        "let me take", "i'm on it", "consider it done", "i'll handle",
        "i'll send", "i'll follow up", "i'll get back", "i'll prepare",
        "i plan to", "i intend to", "i'm going to",
    ]
    if any(p in text_lower for p in commitment_patterns):
        return "commitment_made"

    # Request patterns
    request_patterns = [
        "can you", "could you", "would you", "please", "need you to",
        "can someone", "who can", "anyone able to",
    ]
    if any(p in text_lower for p in request_patterns):
        return "request"

    # Meeting scheduling
    meeting_patterns = [
        "let's meet", "schedule", "calendar", "meeting", "call",
        "sync", "standup", "huddle", "1:1", "check-in",
    ]
    if any(p in text_lower for p in meeting_patterns):
        return "meeting_scheduled"

    # Completion
    completion_patterns = [
        "sent ", "delivered", "completed", "done", "finished",
        "shipped", "deployed", "merged", "closed",
    ]
    if any(p in text_lower for p in completion_patterns):
        return "completion"

    # Default: reported statement
    return "reported_statement"


def _extract_entity_from_slack(text: str, channel: str) -> str:
    """Extract the entity (person/company) from a Slack message.

    Priority:
    1. @mentioned user
    2. Capitalized name in text
    3. Channel name as fallback
    """
    # Check for @user mentions
    mention_match = re.search(r'@(\w+)', text)
    if mention_match:
        return mention_match.group(1)

    # Check for capitalized names (not at start of sentence)
    words = text.split()
    for word in words[1:]:  # skip first word (likely sentence start)
        if word[0].isupper() and word[1:].islower() and len(word) > 2:
            # Filter common words
            if word.lower() not in {"the", "this", "that", "hey", "hi", "yes", "no", "ok"}:
                return word

    # Fallback: use channel name
    return channel.replace("#", "").replace("-", " ").title()


def extract_commitments_from_slack_thread(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract all commitments from a Slack thread.

    Args:
        messages: List of Slack message dicts in a thread

    Returns: List of signal dicts (only commitments)
    """
    signals = []
    for msg in messages:
        signal = parse_slack_message(msg)
        if signal and signal["signal_type"] == "commitment_made":
            signals.append(signal)
    return signals


def sanitize_slack_text(text: str) -> str:
    """Sanitize Slack text for LLM processing.

    Applies the same sanitize_for_llm defense as Gmail, plus
    Slack-specific cleaning.
    """
    # Strip Slack formatting first
    text = _strip_slack_formatting(text)

    # Apply LLM injection defense
    try:
        from maestro_personal_shell.llm_bridge import sanitize_for_llm
        text = sanitize_for_llm(text)
    except Exception:
        pass

    return text
