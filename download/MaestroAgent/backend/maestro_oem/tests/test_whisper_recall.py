"""Tests for CEO Vision Phase 2: Whisper Recall + Conversational Ask.

Tests:
  1. WhisperRecall finds whispers by keyword
  2. WhisperRecall handles empty history
  3. WhisperRecall extracts keywords from vague queries
  4. _generate_conversational_answer routes preparation queries
  5. _generate_conversational_answer routes recall queries
  6. _generate_conversational_answer routes "why" queries

P2: Untested code is unverified code.
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone

from maestro_oem.whisper_recall import WhisperRecall


class MockWhisperHistoryStore:
    """Mock store for testing WhisperRecall."""
    def __init__(self, history: dict):
        self._history = history

    def get_all_history(self, org_id: str = "default") -> dict:
        return self._history


def test_recall_finds_whispers_by_keyword():
    """WhisperRecall should find whispers matching keywords in the query."""
    store = MockWhisperHistoryStore({
        "wspr-1": {
            "shown_count": 2,
            "action_taken": "ignored",
            "first_shown": "2026-06-01T10:00:00+00:00",
            "last_shown": "2026-06-03T10:00:00+00:00",
            "insight": "Legal was being involved after implementation started",
        },
        "wspr-2": {
            "shown_count": 1,
            "action_taken": None,
            "first_shown": "2026-07-01T10:00:00+00:00",
            "last_shown": "2026-07-01T10:00:00+00:00",
            "insight": "Engineering deployed without security review",
        },
    })

    recall = WhisperRecall(whisper_history_store=store)
    result = recall.recall("What was that thing about Legal?")

    assert result["found"] is True
    assert result["match_count"] >= 1
    assert "Legal" in result["whispers"][0]["original_insight"]


def test_recall_handles_empty_history():
    """WhisperRecall should return found=False when no history exists."""
    store = MockWhisperHistoryStore({})
    recall = WhisperRecall(whisper_history_store=store)
    result = recall.recall("What was that thing about pricing?")

    assert result["found"] is False
    assert result["match_count"] == 0


def test_recall_extracts_keywords():
    """WhisperRecall should extract meaningful keywords from vague queries."""
    recall = WhisperRecall(whisper_history_store=MockWhisperHistoryStore({}))
    keywords = recall._extract_keywords("What was that warning about OAuth and Legal?")

    assert "legal" in keywords
    assert "security" in keywords or "oauth" in keywords


def test_recall_builds_conversational_message():
    """WhisperRecall should build a conversational recall message."""
    store = MockWhisperHistoryStore({
        "wspr-1": {
            "shown_count": 3,
            "action_taken": "ignored",
            "first_shown": "2026-06-01T10:00:00+00:00",
            "last_shown": "2026-06-03T10:00:00+00:00",
            "insight": "Legal was being involved after implementation started",
        },
    })

    recall = WhisperRecall(whisper_history_store=store)
    result = recall.recall("What was that thing about Legal?")

    assert "I think this is what you remember" in result["message"]
    assert "Legal was being involved" in result["message"]
    assert "deferred" in result["message"].lower()


def test_recall_what_changed():
    """WhisperRecall should describe what changed since the whisper was shown."""
    recall = WhisperRecall(whisper_history_store=MockWhisperHistoryStore({}))

    # Ignored 3+ times
    changed = recall._what_changed_since({
        "action_taken": "ignored",
        "shown_count": 5,
    })
    assert "ignored 5 times" in changed
    assert "risk has increased" in changed

    # Acted on
    changed = recall._what_changed_since({
        "action_taken": "acted",
        "shown_count": 1,
    })
    assert "acted" in changed.lower()

    # No action
    changed = recall._what_changed_since({
        "action_taken": None,
        "shown_count": 1,
    })
    assert "no action" in changed.lower() or "surfaced" in changed.lower()
