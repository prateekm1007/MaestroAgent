"""Phase 2 — Actor Attribution Classifier regression tests (P82 / FA33).

Tests the rule-based classifier that takes raw signal text and outputs
(actor, event_type, confidence). The classifier feeds `append_event()` in
the canonical ledger — this is the ingestion-side intelligence.

Governance citations:
- P1: every assertion verified by execution
- P2: this IS the test file for actor_classifier.py
- P10: root cause documented — without this classifier, ingestion collapsed
  "I will" / "Can you?" / "Nora: I will" all into user commitments
- P22: classify_and_append calls the real append_event (no mocks)
- P28: 3+ inputs per behavior (exact Nora case + variations + edge cases)
- P56: rules hold veto over LLM; this module is rules-only
- P82: actor attribution ≥95% accuracy on Nora fixture (7/7 = 100%)
- P85: classify_signal never raises
- FA33: requests/questions/quotations/jokes/tentatives classified as such
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from maestro_personal_shell.actor_classifier import (
    classify_signal,
    classify_and_append,
)
from maestro_personal_shell.canonical_ledger import (
    LEDGER_DDL,
    append_event,
    reduce_commitments,
    check_ledger_projection_consistency,
    CommitmentEvent,
)


# ---------------------------------------------------------------------------
# The 7 Nora fixture sentences — exact classification assertions (P82 ≥95%)
# ---------------------------------------------------------------------------

NORA_FIXTURE = [
    # (text, expected_actor, expected_event_type, min_confidence)
    (
        "I will send the audit report to Nora by Friday.",
        "user", "commitment", 0.85,
    ),
    (
        "Maybe I can review it sometime next week.",
        "user", "tentative", 0.0,  # below 0.7 so won't surface
    ),
    (
        "Can you send the report by Friday?",
        "user", "request", 0.0,
    ),
    (
        "Just kidding, I will conquer Mars tomorrow.",
        "user", "joke", 0.0,
    ),
    (
        "Nora: I will send the pricing deck by Friday.",
        "entity_name", "commitment", 0.85,
    ),
    (
        "I will not send the audit report; the commitment is cancelled.",
        "user", "cancellation", 0.85,
    ),
    (
        "As Nora said, 'the Q3 numbers look strong.'",
        "user", "quotation", 0.0,
    ),
]


@pytest.mark.parametrize("text,expected_actor,expected_event,min_conf", NORA_FIXTURE)
def test_nora_classification(text, expected_actor, expected_event, min_conf):
    """P82: each Nora sentence classified correctly (actor + event_type + confidence)."""
    r = classify_signal(text)
    assert r["actor"] == expected_actor, (
        f"actor: expected {expected_actor!r}, got {r['actor']!r} — {r['reasoning']}"
    )
    assert r["event_type"] == expected_event, (
        f"event_type: expected {expected_event!r}, got {r['event_type']!r} — {r['reasoning']}"
    )
    if min_conf > 0:
        assert r["confidence"] >= min_conf, (
            f"confidence: expected >= {min_conf}, got {r['confidence']} — {r['reasoning']}"
        )
    else:
        # For non-commitment events, confidence should be below the 0.7 surfacing threshold
        assert r["confidence"] < 0.7, (
            f"confidence for {expected_event}: expected < 0.7, got {r['confidence']}"
        )


def test_nora_classification_accuracy():
    """P82 gate: ≥95% accuracy on the Nora fixture (7 sentences → 100%)."""
    correct = 0
    for text, exp_actor, exp_event, _ in NORA_FIXTURE:
        r = classify_signal(text)
        if r["actor"] == exp_actor and r["event_type"] == exp_event:
            correct += 1
    accuracy = correct / len(NORA_FIXTURE)
    assert accuracy >= 0.95, (
        f"P82 FAIL: accuracy {accuracy:.0%} < 95% ({correct}/{len(NORA_FIXTURE)})"
    )


# ---------------------------------------------------------------------------
# P85: classify_signal never raises (even on adversarial input)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_input", [
    "",
    None,
    "   ",
    "\n\n\n",
    12345,  # non-string
    "a" * 100000,  # very long
    "\x00\x01\x02binary\x00",  # binary garbage
    "🚀🎉💀 emoji-only",  # unicode
    "'unclosed quote",
    "<script>alert('xss')</script>",  # XSS attempt
    "'; DROP TABLE signals; --",  # SQL injection
])
def test_classify_signal_never_raises(bad_input):
    """P85: classify_signal returns a result on any input, never raises."""
    r = classify_signal(bad_input)
    assert "actor" in r
    assert "event_type" in r
    assert "confidence" in r
    assert "reasoning" in r
    assert r["actor"] in ("user", "entity_name", "system")
    assert r["event_type"] in (
        "commitment", "request", "question", "quotation",
        "cancellation", "completion", "tentative", "joke",
    )


# ---------------------------------------------------------------------------
# P28: 3+ inputs — natural variations (different words, same concept)
# ---------------------------------------------------------------------------

def test_commitment_variations():
    """P28: commitment classification generalizes across phrasings."""
    commitments = [
        "I will send the report by Friday.",
        "I'll deliver the mockups by Tuesday.",
        "I shall provide the proposal next week.",
        "I promise to review the PR by EOD.",
        "I commit to finishing the API by March 15.",
    ]
    for text in commitments:
        r = classify_signal(text)
        assert r["event_type"] == "commitment", (
            f"expected commitment for {text!r}, got {r['event_type']!r} — {r['reasoning']}"
        )
        assert r["actor"] == "user"
        assert r["confidence"] >= 0.7


def test_cancellation_variations():
    """P28: cancellation generalizes across phrasings."""
    cancellations = [
        "I will not send the report.",
        "I won't be able to deliver.",
        "The commitment is cancelled.",
        "Called off the meeting.",
        "Scratch that — never mind.",
        "No longer going to ship this.",
    ]
    for text in cancellations:
        r = classify_signal(text)
        assert r["event_type"] == "cancellation", (
            f"expected cancellation for {text!r}, got {r['event_type']!r} — {r['reasoning']}"
        )


def test_request_variations():
    """P28: request classification generalizes."""
    requests = [
        "Can you send the report by Friday?",
        "Could you review the PR?",
        "Will you provide the mockups?",
        "Would you share the pricing?",
        "Please send the deck by EOD.",
    ]
    for text in requests:
        r = classify_signal(text)
        assert r["event_type"] == "request", (
            f"expected request for {text!r}, got {r['event_type']!r} — {r['reasoning']}"
        )


def test_third_party_attribution_variations():
    """P28: third-party attribution via 'Name:' prefix generalizes."""
    third_party = [
        "Nora: I will send the pricing deck by Friday.",
        "Alex: I'll review the auth module by Tuesday.",
        "Sam: I will deliver the roadmap next Monday.",
    ]
    for text in third_party:
        r = classify_signal(text)
        assert r["actor"] == "entity_name", (
            f"expected entity_name for {text!r}, got {r['actor']!r}"
        )
        assert r["event_type"] == "commitment"


def test_quotation_variations():
    """P28: quotation detection generalizes."""
    quotations = [
        "As Nora said, 'the Q3 numbers look strong.'",
        "According to Alex, the PR is ready.",
        "Jamie wrote: 'the mockups are done.'",
        "Sam stated: delivery is on track.",
    ]
    for text in quotations:
        r = classify_signal(text)
        assert r["event_type"] == "quotation", (
            f"expected quotation for {text!r}, got {r['event_type']!r} — {r['reasoning']}"
        )


# ---------------------------------------------------------------------------
# P22: classify_and_append — production ingestion path (no mocks)
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_ledger_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name
    conn = sqlite3.connect(db_path)
    conn.executescript(LEDGER_DDL)
    conn.commit()
    conn.close()
    yield db_path
    if os.path.exists(db_path):
        os.unlink(db_path)


def test_classify_and_append_full_journey(fresh_ledger_db):
    """P22/P35: classify_and_append → append_event → reduce_commitments journey.

    Ingest the full Nora fixture via classify_and_append (the production path),
    then verify reduce_commitments returns 0 user-active commitments
    (matching the Nora fixture's expected behavior).

    Note: sentences #1 (commitment) and #6 (cancellation) share
    commitment_id='c1' so the reducer links them. In production, the
    reconciliation layer (Phase 3+) will derive this linkage automatically
    by entity + text similarity matching. Here we pass it explicitly to
    test the reducer's cancellation logic end-to-end.
    """
    USER = "demo@user.local"
    # Map sentence index → commitment_id (only #1 and #6 share 'c1')
    commitment_ids = ['c1', 'c2', 'c3', 'c4', 'c5', 'c1', 'c6']  # #6 cancels #1
    for i, (text, _, _, _) in enumerate(NORA_FIXTURE):
        classify_and_append(
            text=text,
            user_email=USER,
            entity="Nora",
            db_path=fresh_ledger_db,
            commitment_id=commitment_ids[i],
        )

    # The full Nora fixture should produce 0 user-active commitments
    # (c1 cancelled by #6, c2/c3/c4/c7 excluded by FA33, c5 is third-party)
    active = reduce_commitments(USER, db_path=fresh_ledger_db)
    assert len(active) == 0, (
        f"Nora fixture via classify_and_append: expected 0 active, got {len(active)}: "
        f"{[c['text'][:50] for c in active]}"
    )

    # P83: ledger is still append-only
    report = check_ledger_projection_consistency(db_path=fresh_ledger_db)
    assert report["consistent"], f"P83 violation: {report['divergences']}"
    assert report["total_events"] == 7


def test_classify_and_append_returns_event_id(fresh_ledger_db):
    """classify_and_append returns a string event_id (not None, not an object)."""
    event_id = classify_and_append(
        text="I will send the report by Friday.",
        user_email="test@user",
        entity="Alice",
        db_path=fresh_ledger_db,
    )
    assert isinstance(event_id, str)
    assert len(event_id) > 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_text_returns_system_tentative():
    """P85: empty input → system/tentative with 0.0 confidence, no crash."""
    r = classify_signal("")
    assert r["actor"] == "system"
    assert r["event_type"] == "tentative"
    assert r["confidence"] == 0.0


def test_speaker_hint_overrides_prefix():
    """If speaker_hint is provided, it overrides the 'Name:' prefix detection."""
    # Text has 'Nora:' prefix (would normally be entity_name)
    # but speaker_hint='user' forces actor=user
    r = classify_signal("Nora: I will send the deck.", speaker_hint="user")
    assert r["actor"] == "user"


def test_completion_classification():
    """Completion events (past-tense delivery) are classified correctly."""
    completions = [
        "I've sent the report.",
        "I've finished the mockups.",
        "Done with the PR review.",
        "Delivered the proposal.",
    ]
    for text in completions:
        r = classify_signal(text)
        assert r["event_type"] == "completion", (
            f"expected completion for {text!r}, got {r['event_type']!r}"
        )


def test_fallback_never_commits_on_ambiguity():
    """FA33: ambiguous text defaults to tentative, NEVER commitment."""
    ambiguous = [
        "The weather is nice today.",
        "I had lunch with the team.",
        "Interesting point about the architecture.",
    ]
    for text in ambiguous:
        r = classify_signal(text)
        assert r["event_type"] != "commitment", (
            f"FA33 violation: ambiguous text classified as commitment: {text!r}"
        )
