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
    """Classify a Slack message into a signal type.

    P41 (fifth audit F2): the Slack ingest path MUST use the SAME
    classifier as the Ask path — _rule_based_classify from
    commitment_classifier.py. This unifies the taxonomy across Gmail
    and Slack, so the same sentence classifies the same way regardless
    of which connector ingested it. No local keyword list — that was
    the source of the taxonomy drift the audit found.

    P56 (rules hold a veto): for non-commitments, the rules classifier
    is the authority. A joke ("conquer the moon") that the old keyword
    list classified as commitment_made is now correctly classified by
    the rules as not_a_commitment.
    """
    from maestro_personal_shell.commitment_classifier import _rule_based_classify
    result = _rule_based_classify(text)
    # Map the reconciled classifier result to the Slack signal_type vocabulary.
    # P36/P37: third_party_report IS a commitment (is_commitment=True) but
    # owner="other" — it's someone ELSE's promise. It must NOT surface as
    # the user's commitment_made. Only owner="user" commitments are
    # commitment_made; everything else is a reported_statement.
    ct = (result.get("commitment_type") or "").lower()
    owner = (result.get("owner") or "").lower()
    if result.get("is_commitment", False) and owner == "user":
        return "commitment_made"
    if ct in ("request", "not_a_commitment"):
        return "request"
    # third_party_report (owner=other), tentative, negation, aspiration, proposal
    # → reported_statement (not the user's commitment)
    return "reported_statement"


def _extract_entity_from_slack(text: str, channel: str) -> str:
    """Extract the entity (person/company) from a Slack message.

    Priority:
    1. @mentioned user
    2. Capitalized name in text (filtered by stopword set — P50)
    3. Channel name as fallback

    P50 (fifth audit F2): entity extraction must NOT grab date tokens
    ("Friday."), pronouns ("I'm"), question words, or common words.
    Token-class awareness via a stopword set, plus punctuation stripping
    BEFORE matching (P42 — normalize before structural matching).
    """
    # Check for @user mentions
    mention_match = re.search(r'@(\w+)', text)
    if mention_match:
        return mention_match.group(1)

    # P50: stopword set — dates, pronouns, question words, common words,
    # and common verbs that must NEVER be extracted as entities.
    _ENTITY_STOPWORDS = frozenset({
        # dates
        'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday',
        'sunday', 'today', 'tomorrow', 'yesterday', 'tonight',
        # pronouns + contractions
        'i', "i'm", 'im', 'me', 'my', 'you', 'your', 'he', 'she', 'they',
        'we', 'it', 'him', 'her', 'them', 'us', 'its',
        # question words
        'what', 'when', 'where', 'how', 'why', 'who', 'whom', 'which',
        # common words
        'the', 'a', 'an', 'and', 'or', 'but', 'if', 'then', 'this', 'that',
        'these', 'those', 'yes', 'no', 'ok', 'okay', 'sure', 'thanks',
        'thank', 'please', 'hi', 'hello', 'hey', 'will', 'would', 'can',
        'could', 'should', 'do', 'does', 'did', 'is', 'are', 'was', 'were',
        'be', 'been', 'not', "don't", 'dont', "can't", 'cant', "won't",
        'wont', 'let', "let's", 'lets', 'just', 'also', 'really', 'very',
        'so', 'too', 'about',
        # common verbs (sentence-starting capitalized forms)
        'spoke', 'talked', 'said', 'told', 'asked', 'called', 'sent',
        'got', 'made', 'went', 'came', 'saw', 'gave', 'took', 'found',
        'need', 'want', 'think', 'know', 'feel', 'look', 'seem',
        'let', 'see', 'try', 'help', 'work', 'play', 'run', 'set',
        'put', 'get', 'go', 'come', 'make', 'take', 'give', 'find',
    })

    # P42: strip trailing punctuation BEFORE matching, lowercase for stopword check
    for m in re.finditer(r'\b([A-Z][a-zA-Z0-9_&.\'-]*)', text):
        token = m.group(1).rstrip(".,!?:;'\"").strip()
        if len(token) < 2:
            continue
        if token.lower() in _ENTITY_STOPWORDS:
            continue
        return token

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
    except Exception as e:
        logger.debug("sanitize_for_llm failed: %s", e)
    return text
