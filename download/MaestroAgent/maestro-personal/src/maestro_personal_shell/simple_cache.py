"""Simple in-memory cache with TTL for API response caching.

Used by /api/ambient and other endpoints to avoid re-computing
expensive LLM calls on every request. The cache is per-process
(not shared across workers) and has a configurable TTL.

P0 fix (auditor v17): this module was referenced but never created,
causing /api/ambient to return 500 on every call. The cache wrapper
was stripped during a refactor and restored, but the module it
imports from didn't exist.
"""
from __future__ import annotations

import time
from typing import Any

# Simple dict-based cache: {key: (value, expiry_timestamp)}
_cache: dict[str, tuple[Any, float]] = {}

# Default TTL: 5 minutes (300 seconds)
DEFAULT_TTL = 300.0


def get_cached(key: str) -> Any | None:
    """Get a value from the cache. Returns None if not found or expired."""
    entry = _cache.get(key)
    if entry is None:
        return None
    value, expiry = entry
    if time.monotonic() > expiry:
        # Expired — remove and return None
        _cache.pop(key, None)
        return None
    return value


def set_cached(key: str, value: Any, ttl: float = DEFAULT_TTL) -> None:
    """Set a value in the cache with a TTL (in seconds)."""
    _cache[key] = (value, time.monotonic() + ttl)


def clear_cache() -> None:
    """Clear all cached values."""
    _cache.clear()


def cache_stats() -> dict[str, int]:
    """Return cache statistics."""
    now = time.monotonic()
    active = sum(1 for _, (_, exp) in _cache.items() if now <= exp)
    expired = len(_cache) - active
    return {"active_entries": active, "expired_entries": expired, "total_entries": len(_cache)}
