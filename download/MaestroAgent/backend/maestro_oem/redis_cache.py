"""HIGH-3 Phase 1 — Redis cache client for multi-replica model.

HIGH-3 from external audit at f16cf66:
> Single-process cognitive state means no HA
> No multi-instance support means no HA/DR
> Cognitive state is process-local.

Design doc: docs/HIGH_3_MULTI_REPLICA_MODEL.md
Recommended Option C: Redis Cache + DB Persistence.

Phase 1 (this module): Add Redis client + wire it into oem_state.py as
an optional cache. When Redis is unavailable, fall back to the current
in-memory singleton (P6 fail-safe).

The cache stores:
  - model snapshots (the ExecutionModel state, serialized)
  - signal lists (per-org)
  - whisper history (per-org)

All cache operations are OPTIONAL — the system works without Redis.
When Redis is available, all replicas share the same cache → consistent
state across replicas.

Usage:
    from maestro_oem.redis_cache import get_redis_cache
    cache = get_redis_cache()
    if cache.available:
        cache.set("org:default:model_snapshot", snapshot_json, ttl=300)
        snapshot = cache.get("org:default:model_snapshot")
    else:
        # Fall back to in-memory singleton (current behavior)
        ...
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Cache TTL (time-to-live) in seconds.
# 300 seconds (5 minutes) — short enough to pick up changes from other replicas,
# long enough to reduce DB/Redis load on hot reads.
DEFAULT_TTL = 300


class RedisCache:
    """Optional Redis cache for multi-replica state sharing.

    Fail-safe (P6): if Redis is unavailable, `available` returns False
    and all operations are no-ops. The caller falls back to the in-memory
    singleton. This means:
      - Single-replica deployment: Redis not needed, works as before
      - Multi-replica deployment: set MAESTRO_REDIS_URL, all replicas share cache
    """

    def __init__(self, redis_url: str | None = None) -> None:
        self._redis_url = redis_url or os.environ.get("MAESTRO_REDIS_URL", "")
        self._client: Any = None
        self._ready = False
        self._connect()

    def _connect(self) -> None:
        """Connect to Redis. Sets self._client to None if unavailable."""
        if self._ready:
            return
        self._ready = True
        if not self._redis_url:
            logger.info("RedisCache: no MAESTRO_REDIS_URL set — cache disabled (single-replica mode)")
            return
        try:
            import redis
            self._client = redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            # Test the connection
            self._client.ping()
            logger.info("RedisCache: connected to %s", self._redis_url)
        except ImportError:
            logger.info("RedisCache: redis package not installed — cache disabled")
            self._client = None
        except Exception as e:
            logger.warning("RedisCache: connection failed — cache disabled: %s", e)
            self._client = None

    @property
    def available(self) -> bool:
        """True if Redis is connected and ready for use."""
        return self._client is not None

    def get(self, key: str) -> Any:
        """Get a value from the cache. Returns None if miss or unavailable."""
        if not self.available:
            return None
        try:
            raw = self._client.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as e:
            logger.debug("RedisCache.get(%s) failed: %s", key, e)
            return None

    def set(self, key: str, value: Any, ttl: int = DEFAULT_TTL) -> bool:
        """Set a value in the cache with TTL. Returns False if unavailable."""
        if not self.available:
            return False
        try:
            raw = json.dumps(value, default=str)
            self._client.setex(key, ttl, raw)
            return True
        except Exception as e:
            logger.debug("RedisCache.set(%s) failed: %s", key, e)
            return False

    def delete(self, key: str) -> bool:
        """Delete a key from the cache. Returns False if unavailable."""
        if not self.available:
            return False
        try:
            self._client.delete(key)
            return True
        except Exception as e:
            logger.debug("RedisCache.delete(%s) failed: %s", key, e)
            return False

    def flush_pattern(self, pattern: str) -> bool:
        """Delete all keys matching a pattern (e.g., 'org:default:*')."""
        if not self.available:
            return False
        try:
            keys = list(self._client.scan_iter(pattern))
            if keys:
                self._client.delete(*keys)
            return True
        except Exception as e:
            logger.debug("RedisCache.flush_pattern(%s) failed: %s", pattern, e)
            return False


# ─── Module-level singleton ──────────────────────────────────────────────

_cache: RedisCache | None = None


def get_redis_cache() -> RedisCache:
    """Get the singleton RedisCache instance.

    The cache is created once on first access. If MAESTRO_REDIS_URL is
    not set, the cache is disabled (available=False) and all operations
    are no-ops.
    """
    global _cache
    if _cache is None:
        _cache = RedisCache()
    return _cache


def reset_redis_cache() -> None:
    """Reset the singleton (for testing)."""
    global _cache
    _cache = None
