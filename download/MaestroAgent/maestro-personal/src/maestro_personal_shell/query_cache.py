"""Query-level TTL cache for Ask responses (P75).

Caches the FULL response dict keyed by (question + user_email + evidence_hash).
On cache hit, returns the stored response in <10ms — zero LLM calls.

Root cause (P10): production Ask latency is 33-45s because every query calls
the LLM. The existing llm_bridge.py has a prompt-level cache, but the Ask
endpoint constructs slightly different prompts per request (evidence ordering,
timestamp variability), so the prompt-level cache rarely hits. A query-level
cache keyed on the user's actual question + the evidence list eliminates LLM
calls entirely for repeated queries within the TTL.

Authored by: CTO (direct — this module is straightforward enough to not
require Kimi K3 dispatch). The Phase 4b LLM call optimization will use K3.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from typing import Any

logger = logging.getLogger(__name__)


def _normalize_question(question: str) -> str:
    """Normalize a question for cache key computation.

    Lowercase, strip, collapse whitespace. This ensures
    "What did I promise Maria?" and "  what did i promise maria?  "
    hit the same cache entry.
    """
    if not question:
        return ""
    return " ".join(str(question).lower().split())


def _hash_evidence(evidence: list[dict]) -> str:
    """Hash the evidence list so cache invalidates when the ledger changes.

    Sorts the evidence by commitment_id (if present) before hashing so that
    different ordering of the same evidence set produces the same hash.
    """
    if not evidence:
        return "empty"
    try:
        # Sort by commitment_id (or text if no commitment_id) for deterministic ordering
        sorted_ev = sorted(
            evidence,
            key=lambda e: (e.get("commitment_id") or e.get("text") or "")[:100],
        )
        # Only hash the meaningful fields (not last_event_at which changes on every read)
        canonical = [
            {
                "commitment_id": e.get("commitment_id"),
                "entity": e.get("entity"),
                "text": e.get("text"),
                "actor": e.get("actor"),
                "state": e.get("state"),
                "confidence": e.get("confidence"),
            }
            for e in sorted_ev
        ]
        return hashlib.sha256(
            json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:16]
    except Exception as e:
        logger.warning("query_cache: failed to hash evidence (%s) — using len-based fallback", e)
        return f"len-{len(evidence)}"


def _compute_cache_key(question: str, user_email: str, evidence: list[dict]) -> str:
    """Compute a deterministic cache key.

    Key = sha256(normalized_question + user_email + evidence_hash)
    """
    norm_q = _normalize_question(question)
    ev_hash = _hash_evidence(evidence)
    raw = f"{norm_q}|{user_email}|{ev_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class QueryCache:
    """In-memory TTL cache for Ask responses (P75).

    Thread-safe via threading.Lock. LRU eviction when max_entries is exceeded.
    Cache key includes the evidence hash so that:
    - New signal ingested → evidence changes → cache miss → fresh LLM call
    - Same query repeated → evidence unchanged → cache hit → instant return

    P85: cache failures never raise. get() returns None on any error,
    set() logs and continues.
    """

    def __init__(self, ttl_seconds: int = 300, max_entries: int = 1000):
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._store: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self._lock = threading.Lock()
        # Metrics
        self._hits = 0
        self._misses = 0
        # Per-user index for fast invalidation
        self._user_index: dict[str, set[str]] = {}

    def get(self, question: str, user_email: str, evidence: list[dict]) -> dict | None:
        """Return cached response if hit and not expired, else None.

        P85: never raises — returns None on any error.
        """
        try:
            key = _compute_cache_key(question, user_email, evidence)
            now = time.monotonic()
            with self._lock:
                entry = self._store.get(key)
                if entry is None:
                    self._misses += 1
                    return None
                expires_at, response = entry
                if now > expires_at:
                    # Expired — remove and count as miss
                    del self._store[key]
                    self._misses += 1
                    # Also remove from user index
                    user_keys = self._user_index.get(user_email)
                    if user_keys and key in user_keys:
                        user_keys.discard(key)
                    return None
                # Hit — move to end (LRU)
                self._store.move_to_end(key)
                self._hits += 1
                # Return a deep copy so callers can't mutate the cached response
                return json.loads(json.dumps(response))
        except Exception as e:
            logger.warning("query_cache.get failed (%s) — returning None (cache miss)", e)
            return None

    def set(self, question: str, user_email: str, evidence: list[dict], response: dict) -> None:
        """Store a response in the cache.

        P85: never raises — logs on error and continues.
        """
        try:
            key = _compute_cache_key(question, user_email, evidence)
            expires_at = time.monotonic() + self._ttl_seconds
            with self._lock:
                # Evict if at capacity (LRU — remove oldest)
                while len(self._store) >= self._max_entries:
                    evicted_key, _ = self._store.popitem(last=False)
                    # Clean up user index
                    for user, keys in self._user_index.items():
                        if evicted_key in keys:
                            keys.discard(evicted_key)
                            break
                self._store[key] = (expires_at, response)
                self._store.move_to_end(key)
                # Update user index
                if user_email not in self._user_index:
                    self._user_index[user_email] = set()
                self._user_index[user_email].add(key)
        except Exception as e:
            logger.warning("query_cache.set failed (%s) — cache not updated", e)

    def invalidate_user(self, user_email: str) -> int:
        """Invalidate all cache entries for a user.

        Called when new signals are ingested for this user, so the next
        Ask query will get a fresh LLM call with updated evidence.

        Returns the number of entries invalidated.
        """
        try:
            with self._lock:
                keys = self._user_index.pop(user_email, set())
                count = 0
                for key in keys:
                    if key in self._store:
                        del self._store[key]
                        count += 1
                return count
        except Exception as e:
            logger.warning("query_cache.invalidate_user failed (%s) — returning 0", e)
            return 0

    def stats(self) -> dict:
        """Return cache statistics for observability."""
        with self._lock:
            total = self._hits + self._misses
            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 4) if total > 0 else 0.0,
                "entries": len(self._store),
                "max_entries": self._max_entries,
                "ttl_seconds": self._ttl_seconds,
                "users_tracked": len(self._user_index),
            }

    def clear(self) -> int:
        """Clear all cache entries. Returns the number cleared."""
        with self._lock:
            count = len(self._store)
            self._store.clear()
            self._user_index.clear()
            self._hits = 0
            self._misses = 0
            return count


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_cache: QueryCache | None = None
_cache_lock = threading.Lock()


def get_cache() -> QueryCache:
    """Get the process-wide cache singleton.

    TTL is configurable via MAESTRO_CACHE_TTL_SECONDS env var (default 300s = 5min).
    Max entries is configurable via MAESTRO_CACHE_MAX_ENTRIES (default 1000).
    """
    global _cache
    if _cache is not None:
        return _cache
    with _cache_lock:
        if _cache is None:
            ttl = int(os.environ.get("MAESTRO_CACHE_TTL_SECONDS", "300"))
            max_entries = int(os.environ.get("MAESTRO_CACHE_MAX_ENTRIES", "1000"))
            _cache = QueryCache(ttl_seconds=ttl, max_entries=max_entries)
            logger.info(
                "query_cache: initialized (ttl=%ds, max_entries=%d)",
                ttl, max_entries,
            )
        return _cache
