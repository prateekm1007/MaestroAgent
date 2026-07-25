"""P50 — Gate the ingest journey, not just the classifier component (fifth audit F2).

The fifth audit found the Slack ingest path broken:
- Entity extraction grabs "Friday." and "I'm" as entities
- A joke ("conquer the moon") becomes commitment_made
- The Gmail and Slack paths use inconsistent taxonomies

This test posts adversarial Slack messages through the REAL ingest path
(parse_slack_message) and asserts at the product surface — entity
extraction and classification must be correct on messy real-ish input.

Design: Kimi K3 (moonshotai/kimi-k3), P46-verified,
generation_id=gen-1784955840-ouKoivkkKVDZn3RQRGud.

Run:
  cd /home/z/my-project/MaestroAgent/download/MaestroAgent/maestro-personal
  python -m pytest tests/test_P50_slack_ingest_journey.py -v
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
os.environ.setdefault("MAESTRO_ENV", "dev")


from maestro_personal_shell.signal_adapters.slack import (
    parse_slack_message,
    _extract_entity_from_slack,
    _classify_slack_message,
)


# ---------------------------------------------------------------------------
# P50 (a): entity extraction — no date tokens, pronouns, or stop-words
# ---------------------------------------------------------------------------

def test_friday_is_not_an_entity():
    """P50: 'Friday.' must NOT be extracted as an entity (the audit found this)."""
    entity = _extract_entity_from_slack("I'm free on Friday.", "eng")
    assert entity.lower() != "friday", (
        f"P50 violation: 'Friday.' was extracted as an entity. "
        f"Date tokens must never be entities. Got: {entity!r}"
    )


def test_im_is_not_an_entity():
    """P50: 'I'm' must NOT be extracted as an entity (the audit found this)."""
    entity = _extract_entity_from_slack("I'm going to send the report.", "eng")
    assert entity.lower() not in ("i'm", "im", "i"), (
        f"P50 violation: 'I'm' was extracted as an entity. "
        f"Pronouns must never be entities. Got: {entity!r}"
    )


def test_question_words_are_not_entities():
    """P50: 'What', 'When', 'How' must NOT be extracted as entities."""
    for word in ["What", "When", "How", "Why", "Who"]:
        entity = _extract_entity_from_slack(f"{word} about the deadline?", "eng")
        assert entity.lower() != word.lower(), (
            f"P50 violation: '{word}' was extracted as an entity. "
            f"Question words must never be entities. Got: {entity!r}"
        )


def test_real_entity_survives_punctuation():
    """P50: a real entity (Alice) must survive trailing punctuation."""
    entity = _extract_entity_from_slack("Spoke with Alice, she's on it.", "eng")
    assert entity == "Alice", (
        f"P50: real entity 'Alice' was not extracted. Got: {entity!r}"
    )


def test_falls_back_to_channel_when_no_entity():
    """P50: when no valid entity is found, fall back to channel name."""
    entity = _extract_entity_from_slack("I will send it tomorrow.", "engineering")
    assert entity == "Engineering", (
        f"P50: should fall back to channel name 'Engineering'. Got: {entity!r}"
    )


# ---------------------------------------------------------------------------
# P50 (b): classification — unified taxonomy, no local keyword list
# ---------------------------------------------------------------------------

def test_joke_is_not_a_commitment():
    """P50/P56: a joke ('I will conquer the moon') must NOT be commitment_made.

    The audit found the old Slack keyword list classified this as
    commitment_made because it matched 'i will'. The unified rules
    classifier must reject it (P56 — rules hold a veto).
    """
    sig_type = _classify_slack_message("I will conquer the moon haha")
    assert sig_type != "commitment_made", (
        f"P50 violation: a joke was classified as commitment_made. "
        f"Got: {sig_type!r}"
    )


def test_question_is_not_a_commitment():
    """P50/P56: 'Will you send the report?' must NOT be commitment_made."""
    sig_type = _classify_slack_message("Will you send the report by Friday?")
    assert sig_type != "commitment_made", (
        f"P50 violation: a question was classified as commitment_made. "
        f"Got: {sig_type!r}"
    )


def test_real_commitment_is_classified():
    """P50: a real commitment ('I will send the proposal') IS commitment_made."""
    sig_type = _classify_slack_message("I will send the proposal to Maria by Friday.")
    assert sig_type == "commitment_made", (
        f"P50: a real commitment was not classified as commitment_made. "
        f"Got: {sig_type!r}"
    )


def test_cancellation_is_detected():
    """P50: a cancellation ('I will not send it') must NOT be commitment_made."""
    sig_type = _classify_slack_message("I will not send the report — cancelled.")
    assert sig_type != "commitment_made", (
        f"P50 violation: a cancellation was classified as commitment_made. "
        f"Got: {sig_type!r}"
    )


def test_third_party_report_is_detected():
    """P50: a third-party report ('Maria said she will send') must NOT be
    commitment_made — it's someone else's promise."""
    sig_type = _classify_slack_message("Maria said she will send the proposal tomorrow.")
    assert sig_type != "commitment_made", (
        f"P50 violation: a third-party report was classified as commitment_made. "
        f"Got: {sig_type!r}"
    )


def test_slack_uses_unified_classifier():
    """P41/P50 STRUCTURAL CHECK: _classify_slack_message MUST delegate to
    _rule_based_classify from commitment_classifier.py — no local keyword list.
    This unifies the taxonomy across Gmail and Slack."""
    import inspect
    src = inspect.getsource(_classify_slack_message)
    assert "_rule_based_classify" in src, (
        "P41 violation: _classify_slack_message does NOT call _rule_based_classify. "
        "The Slack path has its own local keyword list — taxonomy drift from Gmail."
    )
    # The old keyword list had these patterns; they must be GONE
    assert "commitment_patterns" not in src, (
        "P50 violation: _classify_slack_message still has a local commitment_patterns "
        "list — this is the taxonomy drift source the audit flagged."
    )


# ---------------------------------------------------------------------------
# P50 (c): full ingest journey — parse_slack_message end-to-end
# ---------------------------------------------------------------------------

def test_parse_slack_message_joke_not_commitment():
    """P50 JOURNEY: parse_slack_message on a joke must produce signal_type !=
    commitment_made. End-to-end ingest journey, not just the classifier."""
    msg = {
        "text": "I will conquer the moon haha",
        "user": "U123",
        "ts": "1690000000.000000",
        "channel": "general",
    }
    signal = parse_slack_message(msg)
    assert signal is not None
    assert signal["signal_type"] != "commitment_made", (
        f"P50 journey violation: a joke ingested via parse_slack_message "
        f"became commitment_made. signal_type={signal['signal_type']!r}"
    )


def test_parse_slack_message_real_commitment():
    """P50 JOURNEY: parse_slack_message on a real commitment produces
    commitment_made with a real entity."""
    msg = {
        "text": "I will send the proposal to Maria by Friday.",
        "user": "U123",
        "ts": "1690000000.000000",
        "channel": "general",
    }
    signal = parse_slack_message(msg)
    assert signal is not None
    assert signal["signal_type"] == "commitment_made"
    # Maria must be the entity, not Friday
    assert signal["entity"] == "Maria", (
        f"P50: entity should be 'Maria', got {signal['entity']!r}"
    )


def test_parse_slack_message_no_friday_entity():
    """P50 JOURNEY: 'I'm free on Friday.' must NOT have 'Friday' as entity."""
    msg = {
        "text": "I'm free on Friday.",
        "user": "U123",
        "ts": "1690000000.000000",
        "channel": "engineering",
    }
    signal = parse_slack_message(msg)
    assert signal is not None
    assert signal["entity"].lower() != "friday", (
        f"P50 journey violation: 'Friday' was extracted as entity. "
        f"entity={signal['entity']!r}"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
