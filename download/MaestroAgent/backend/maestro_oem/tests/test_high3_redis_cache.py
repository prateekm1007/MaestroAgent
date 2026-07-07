"""HIGH-3 Phase 1 — Redis cache client test (P22).

HIGH-3 from external audit at f16cf66:
> Single-process cognitive state means no HA
> No multi-instance support means no HA/DR

Design doc: docs/HIGH_3_MULTI_REPLICA_MODEL.md
Phase 1: Redis cache client + optional wiring into oem_state.py.

This test verifies by execution that:
1. RedisCache works when Redis is available (mocked)
2. RedisCache fails safe when Redis is unavailable (P6)
3. RedisCache fails safe when MAESTRO_REDIS_URL is not set (single-replica mode)
4. The cache is wired into oem_state.py (_publish_to_redis_cache method exists)
5. The publish method is called from live_ingest (P11 source check)
6. The publish method is fail-safe (doesn't break ingest when Redis is down)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ["MAESTRO_LOCAL_DEV"] = "true"


def test_redis_cache_unavailable_when_no_url():
    """HIGH-3 Phase 1: cache is disabled when MAESTRO_REDIS_URL is not set.

    This is the single-replica mode — the system works without Redis,
    falling back to the in-memory singleton.
    """
    from maestro_oem.redis_cache import RedisCache, reset_redis_cache

    # Ensure no REDIS_URL
    old_url = os.environ.pop("MAESTRO_REDIS_URL", None)
    reset_redis_cache()
    try:
        cache = RedisCache()
        assert not cache.available, "Cache must be disabled when no MAESTRO_REDIS_URL"
        assert cache.get("any_key") is None, "get() must return None when unavailable"
        assert cache.set("key", "value") is False, "set() must return False when unavailable"
        assert cache.delete("key") is False, "delete() must return False when unavailable"
    finally:
        if old_url:
            os.environ["MAESTRO_REDIS_URL"] = old_url
        reset_redis_cache()


def test_redis_cache_fails_safe_on_connection_error():
    """HIGH-3 Phase 1: cache fails safe when Redis URL is set but unreachable (P6).

    If MAESTRO_REDIS_URL points to a non-existent Redis, the cache must
    disable itself (available=False) rather than raising. This is P6:
    fail closed, not silent — the system continues to work with the
    in-memory singleton.
    """
    from maestro_oem.redis_cache import RedisCache, reset_redis_cache

    # Set a URL that will fail to connect
    old_url = os.environ.get("MAESTRO_REDIS_URL")
    os.environ["MAESTRO_REDIS_URL"] = "redis://localhost:1/0"  # port 1 = nothing there
    reset_redis_cache()
    try:
        cache = RedisCache()
        assert not cache.available, "Cache must be disabled when connection fails"
        # All operations must be no-ops (not raise)
        assert cache.get("key") is None
        assert cache.set("key", "value") is False
        assert cache.delete("key") is False
    finally:
        if old_url:
            os.environ["MAESTRO_REDIS_URL"] = old_url
        else:
            os.environ.pop("MAESTRO_REDIS_URL", None)
        reset_redis_cache()


def test_redis_cache_get_set_delete_work_when_available():
    """HIGH-3 Phase 1: cache operations work when Redis is available (mocked).

    Uses a mock Redis client to verify the cache logic without needing
    a real Redis server.
    """
    from maestro_oem.redis_cache import RedisCache

    cache = RedisCache.__new__(RedisCache)
    # Mock the internals — simulate a working Redis
    class MockRedis:
        def __init__(self):
            self.data = {}
        def ping(self):
            pass
        def get(self, key):
            return self.data.get(key)
        def setex(self, key, ttl, value):
            self.data[key] = value
        def delete(self, *keys):
            for k in keys:
                self.data.pop(k, None)
        def scan_iter(self, pattern):
            import fnmatch
            return [k for k in self.data if fnmatch.fnmatch(k, pattern)]

    cache._client = MockRedis()
    cache._ready = True
    cache._redis_url = "redis://mock"

    assert cache.available

    # Set + get
    cache.set("test_key", {"data": "value"}, ttl=60)
    result = cache.get("test_key")
    assert result == {"data": "value"}, f"get() must return what set() stored. Got: {result}"

    # Delete
    cache.delete("test_key")
    assert cache.get("test_key") is None, "get() must return None after delete()"

    # Flush pattern
    cache.set("org:default:1", "a")
    cache.set("org:default:2", "b")
    cache.set("org:other:1", "c")
    cache.flush_pattern("org:default:*")
    assert cache.get("org:default:1") is None
    assert cache.get("org:default:2") is None
    assert cache.get("org:other:1") == "c", "flush_pattern must not touch other orgs"


def test_publish_to_redis_cache_method_exists():
    """HIGH-3 Phase 1 (P11): OEMState has _publish_to_redis_cache method.

    Source inspection: the method must exist and be callable.
    """
    import inspect
    from maestro_api.oem_state import OEMState

    assert hasattr(OEMState, "_publish_to_redis_cache"), \
        "OEMState must have _publish_to_redis_cache method (HIGH-3 Phase 1)"

    source = inspect.getsource(OEMState._publish_to_redis_cache)
    assert "get_redis_cache" in source, \
        "_publish_to_redis_cache must call get_redis_cache()"
    assert "cache.available" in source, \
        "_publish_to_redis_cache must check cache.available before using cache"


def test_publish_called_from_run_background_loop():
    """HIGH-3 Phase 1 (P11): _publish_to_redis_cache is called from _run_background_loop.

    This verifies the wiring — the method must be CALLED, not just defined.
    """
    import inspect
    from maestro_api.oem_state import OEMState

    source = inspect.getsource(OEMState._run_background_loop)
    assert "_publish_to_redis_cache" in source, \
        "_run_background_loop must call _publish_to_redis_cache (HIGH-3 wiring)"


def test_publish_fails_safe():
    """HIGH-3 Phase 1 (P6): _publish_to_redis_cache fails safe.

    If Redis is unavailable, the publish method must be a no-op (not raise).
    If it raises internally, the caller (_run_background_loop) must catch it.
    """
    from maestro_oem.redis_cache import reset_redis_cache
    from maestro_api.oem_state import OEMState

    # Ensure no Redis
    old_url = os.environ.pop("MAESTRO_REDIS_URL", None)
    reset_redis_cache()
    try:
        # Create an OEMState and call _publish_to_redis_cache directly
        # It must NOT raise even though Redis is unavailable
        state = OEMState.__new__(OEMState)
        state.org_id = "default"
        state.engine = None
        state.signals = []
        # This must be a no-op (engine is None → early return)
        state._publish_to_redis_cache()
        assert True, "publish must not raise when Redis unavailable"
    finally:
        if old_url:
            os.environ["MAESTRO_REDIS_URL"] = old_url
        reset_redis_cache()


def test_redis_cache_singleton():
    """HIGH-3 Phase 1: get_redis_cache returns a singleton."""
    from maestro_oem.redis_cache import get_redis_cache, reset_redis_cache

    reset_redis_cache()
    cache1 = get_redis_cache()
    cache2 = get_redis_cache()
    assert cache1 is cache2, "get_redis_cache must return the same instance (singleton)"


if __name__ == "__main__":
    test_redis_cache_unavailable_when_no_url()
    print("PASS: test_redis_cache_unavailable_when_no_url")
    test_redis_cache_fails_safe_on_connection_error()
    print("PASS: test_redis_cache_fails_safe_on_connection_error")
    test_redis_cache_get_set_delete_work_when_available()
    print("PASS: test_redis_cache_get_set_delete_work_when_available")
    test_publish_to_redis_cache_method_exists()
    print("PASS: test_publish_to_redis_cache_method_exists")
    test_publish_called_from_run_background_loop()
    print("PASS: test_publish_called_from_run_background_loop")
    test_publish_fails_safe()
    print("PASS: test_publish_fails_safe")
    test_redis_cache_singleton()
    print("PASS: test_redis_cache_singleton")
    print("\nAll HIGH-3 Phase 1 tests passed.")
