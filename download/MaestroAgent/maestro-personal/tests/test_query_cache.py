"""Phase 4a — Query Cache regression tests (P75).

Tests the in-memory TTL cache for Ask responses. On cache hit, returns
the stored response in <10ms — zero LLM calls.

Governance citations:
- P1: every assertion verified by execution
- P2: this IS the test file for query_cache.py
- P10: root cause documented — Ask latency is 33-45s because every query
  calls the LLM. Caching eliminates the LLM call for repeated queries.
- P22: the cache stores the FULL response dict — no partial caching
- P75: target is <3s p95. Cache hit should be <10ms.
- P85: cache failures never raise — get() returns None, set() logs
"""
from __future__ import annotations

import time
import json

import pytest

from maestro_personal_shell.query_cache import (
    QueryCache,
    get_cache,
    _compute_cache_key,
    _normalize_question,
    _hash_evidence,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_cache():
    """Yield a fresh QueryCache with 1s TTL for fast testing."""
    return QueryCache(ttl_seconds=1, max_entries=10)


SAMPLE_EVIDENCE = [
    {
        "commitment_id": "c1",
        "entity": "Maria",
        "text": "I will send the proposal to Maria by Friday.",
        "actor": "user",
        "state": "active",
        "confidence": 0.9,
    }
]

SAMPLE_RESPONSE = {
    "answer": "You promised to send the proposal to Maria by Friday.",
    "confidence": 0.85,
    "evidence_count": 1,
    "llm_active": True,
}


# ---------------------------------------------------------------------------
# Basic cache operations
# ---------------------------------------------------------------------------

def test_cache_miss_returns_none(fresh_cache):
    """P75: a cache miss returns None (not an error)."""
    result = fresh_cache.get("What did I promise Maria?", "user@test", SAMPLE_EVIDENCE)
    assert result is None


def test_cache_hit_returns_response(fresh_cache):
    """P75: after set(), a cache hit returns the stored response."""
    fresh_cache.set("What did I promise Maria?", "user@test", SAMPLE_EVIDENCE, SAMPLE_RESPONSE)
    result = fresh_cache.get("What did I promise Maria?", "user@test", SAMPLE_EVIDENCE)
    assert result is not None
    assert result["answer"] == SAMPLE_RESPONSE["answer"]
    assert result["confidence"] == SAMPLE_RESPONSE["confidence"]


def test_cache_hit_is_fast(fresh_cache):
    """P75: cache hit should be <10ms (target <3s p95 overall)."""
    fresh_cache.set("What did I promise Maria?", "user@test", SAMPLE_EVIDENCE, SAMPLE_RESPONSE)
    t0 = time.monotonic()
    for _ in range(100):
        fresh_cache.get("What did I promise Maria?", "user@test", SAMPLE_EVIDENCE)
    elapsed = time.monotonic() - t0
    per_call_ms = (elapsed / 100) * 1000
    assert per_call_ms < 10, f"cache hit took {per_call_ms:.2f}ms per call (target <10ms)"


def test_cache_returns_deep_copy(fresh_cache):
    """The cached response is a deep copy — callers can't mutate the cache."""
    fresh_cache.set("Q", "u", SAMPLE_EVIDENCE, {"answer": "original", "nested": {"key": "val"}})
    result = fresh_cache.get("Q", "u", SAMPLE_EVIDENCE)
    result["answer"] = "mutated"
    result["nested"]["key"] = "mutated"
    # Get again — should still be the original
    result2 = fresh_cache.get("Q", "u", SAMPLE_EVIDENCE)
    assert result2["answer"] == "original"
    assert result2["nested"]["key"] == "val"


# ---------------------------------------------------------------------------
# TTL expiry
# ---------------------------------------------------------------------------

def test_cache_expires_after_ttl(fresh_cache):
    """P75: cache entries expire after the TTL."""
    fresh_cache.set("Q", "u", SAMPLE_EVIDENCE, SAMPLE_RESPONSE)
    # Wait for TTL to expire (1s)
    time.sleep(1.5)
    result = fresh_cache.get("Q", "u", SAMPLE_EVIDENCE)
    assert result is None


def test_cache_hit_before_ttl(fresh_cache):
    """P75: cache entries are valid before the TTL expires."""
    fresh_cache.set("Q", "u", SAMPLE_EVIDENCE, SAMPLE_RESPONSE)
    time.sleep(0.5)  # less than 1s TTL
    result = fresh_cache.get("Q", "u", SAMPLE_EVIDENCE)
    assert result is not None


# ---------------------------------------------------------------------------
# Cache key computation
# ---------------------------------------------------------------------------

def test_question_normalization():
    """Cache key normalizes question text (case + whitespace)."""
    q1 = "What did I promise Maria?"
    q2 = "  what did i promise maria?  "
    q3 = "What  did  I  promise  Maria?"
    assert _normalize_question(q1) == _normalize_question(q2) == _normalize_question(q3)


def test_different_users_different_keys(fresh_cache):
    """Same question + different users = different cache entries."""
    fresh_cache.set("Q", "user1", SAMPLE_EVIDENCE, {"answer": "for user1"})
    fresh_cache.set("Q", "user2", SAMPLE_EVIDENCE, {"answer": "for user2"})
    r1 = fresh_cache.get("Q", "user1", SAMPLE_EVIDENCE)
    r2 = fresh_cache.get("Q", "user2", SAMPLE_EVIDENCE)
    assert r1["answer"] == "for user1"
    assert r2["answer"] == "for user2"


def test_different_evidence_different_keys(fresh_cache):
    """Same question + same user + different evidence = different cache entries.

    This is the key P75 invariant: when the ledger changes (new signal ingested),
    the evidence changes, and the cache misses — forcing a fresh LLM call.
    """
    ev1 = [{"commitment_id": "c1", "entity": "Maria", "text": "promise 1", "actor": "user", "state": "active", "confidence": 0.9}]
    ev2 = [{"commitment_id": "c2", "entity": "Maria", "text": "promise 2", "actor": "user", "state": "active", "confidence": 0.9}]
    fresh_cache.set("Q", "u", ev1, {"answer": "response for ev1"})
    fresh_cache.set("Q", "u", ev2, {"answer": "response for ev2"})
    r1 = fresh_cache.get("Q", "u", ev1)
    r2 = fresh_cache.get("Q", "u", ev2)
    assert r1["answer"] == "response for ev1"
    assert r2["answer"] == "response for ev2"


def test_same_evidence_different_order_same_key(fresh_cache):
    """Evidence ordering doesn't matter — the hash is order-independent."""
    ev_a = [
        {"commitment_id": "c1", "entity": "Maria", "text": "promise 1", "actor": "user", "state": "active", "confidence": 0.9},
        {"commitment_id": "c2", "entity": "Nora", "text": "promise 2", "actor": "user", "state": "active", "confidence": 0.85},
    ]
    ev_b = list(reversed(ev_a))  # same evidence, different order
    fresh_cache.set("Q", "u", ev_a, {"answer": "response"})
    # Same question + same user + same evidence (different order) → should hit
    r = fresh_cache.get("Q", "u", ev_b)
    assert r is not None
    assert r["answer"] == "response"


# ---------------------------------------------------------------------------
# LRU eviction
# ---------------------------------------------------------------------------

def test_lru_eviction(fresh_cache):
    """P75: when max_entries is exceeded, the least-recently-used entry is evicted."""
    cache = QueryCache(ttl_seconds=60, max_entries=3)
    cache.set("Q1", "u", SAMPLE_EVIDENCE, {"answer": "1"})
    cache.set("Q2", "u", SAMPLE_EVIDENCE, {"answer": "2"})
    cache.set("Q3", "u", SAMPLE_EVIDENCE, {"answer": "3"})
    # Access Q1 to make it recently used
    cache.get("Q1", "u", SAMPLE_EVIDENCE)
    # Add Q4 — should evict Q2 (the least recently used)
    cache.set("Q4", "u", SAMPLE_EVIDENCE, {"answer": "4"})
    assert cache.get("Q1", "u", SAMPLE_EVIDENCE) is not None  # Q1 survives
    assert cache.get("Q2", "u", SAMPLE_EVIDENCE) is None      # Q2 evicted
    assert cache.get("Q3", "u", SAMPLE_EVIDENCE) is not None  # Q3 survives
    assert cache.get("Q4", "u", SAMPLE_EVIDENCE) is not None  # Q4 exists


# ---------------------------------------------------------------------------
# User invalidation
# ---------------------------------------------------------------------------

def test_invalidate_user(fresh_cache):
    """P75: invalidate_user removes all entries for a user."""
    fresh_cache.set("Q1", "user1", SAMPLE_EVIDENCE, {"answer": "1"})
    fresh_cache.set("Q2", "user1", SAMPLE_EVIDENCE, {"answer": "2"})
    fresh_cache.set("Q3", "user2", SAMPLE_EVIDENCE, {"answer": "3"})
    count = fresh_cache.invalidate_user("user1")
    assert count == 2
    assert fresh_cache.get("Q1", "user1", SAMPLE_EVIDENCE) is None
    assert fresh_cache.get("Q2", "user1", SAMPLE_EVIDENCE) is None
    assert fresh_cache.get("Q3", "user2", SAMPLE_EVIDENCE) is not None  # user2 unaffected


def test_invalidate_nonexistent_user_returns_zero(fresh_cache):
    """Invalidating a user with no cache entries returns 0."""
    count = fresh_cache.invalidate_user("nobody@user")
    assert count == 0


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def test_stats_track_hits_and_misses(fresh_cache):
    """P75: stats() returns hit/miss counts and hit_rate."""
    fresh_cache.set("Q", "u", SAMPLE_EVIDENCE, SAMPLE_RESPONSE)
    fresh_cache.get("Q", "u", SAMPLE_EVIDENCE)  # hit
    fresh_cache.get("Q", "u", SAMPLE_EVIDENCE)  # hit
    fresh_cache.get("miss", "u", SAMPLE_EVIDENCE)  # miss
    stats = fresh_cache.stats()
    assert stats["hits"] == 2
    assert stats["misses"] == 1
    assert stats["hit_rate"] == round(2/3, 4)
    assert stats["entries"] == 1


# ---------------------------------------------------------------------------
# P85: never raises
# ---------------------------------------------------------------------------

def test_get_with_bad_inputs_never_raises(fresh_cache):
    """P85: get() with bad inputs returns None, never raises."""
    assert fresh_cache.get("", "u", []) is None
    assert fresh_cache.get(None, "u", []) is None  # type: ignore
    assert fresh_cache.get("Q", "", []) is None
    assert fresh_cache.get("Q", "u", None) is None  # type: ignore


def test_set_with_bad_inputs_never_raises(fresh_cache):
    """P85: set() with bad inputs logs and continues, never raises."""
    fresh_cache.set(None, "u", [], {"answer": "x"})  # type: ignore
    fresh_cache.set("Q", None, [], {"answer": "x"})  # type: ignore
    fresh_cache.set("Q", "u", None, {"answer": "x"})  # type: ignore
    fresh_cache.set("Q", "u", [], None)
    # Cache should still work for valid inputs
    fresh_cache.set("Q", "u", SAMPLE_EVIDENCE, SAMPLE_RESPONSE)
    assert fresh_cache.get("Q", "u", SAMPLE_EVIDENCE) is not None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

def test_get_cache_singleton():
    """get_cache() returns the same instance across calls."""
    c1 = get_cache()
    c2 = get_cache()
    assert c1 is c2
