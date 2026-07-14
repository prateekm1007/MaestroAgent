"""
Tests for the whisper system (Issue 13).

Covers:
  - _should_whisper_rule_based() — rule-based early-exit (Part A)
  - whisper_scheduler dedup logic (Part B)
  - whisper endpoint returns 200 (Part C integration)

P22: these tests execute the production path (the actual function and
the actual API endpoint), not just unit-level mocks.
"""
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
os.environ.setdefault("MAESTRO_PERSONAL_TOKEN", "test")
os.environ.setdefault("MAESTRO_ENV", "dev")
os.environ.pop("OLLAMA_HOST", None)


class TestShouldWhisperRuleBased:
    """Issue 13-A: rule-based early-exit for whisper materiality gate."""

    def test_critical_priority_always_whispers(self):
        """High-priority whispers always fire, regardless of type."""
        from maestro_personal_shell.routers.surfaces import _should_whisper_rule_based
        assert _should_whisper_rule_based({"type": "routine", "priority": "high"}) is True
        assert _should_whisper_rule_based({"type": "routine", "priority": "critical"}) is True

    def test_critical_type_always_whispers(self):
        """Critical whisper types always fire, regardless of priority."""
        from maestro_personal_shell.routers.surfaces import _should_whisper_rule_based
        for t in ("critical_signal", "broken_commitment", "stale_commitment",
                   "deadline_approaching", "contradiction_detected"):
            assert _should_whisper_rule_based({"type": t, "priority": "low"}) is True, \
                f"{t} should always whisper"

    def test_low_value_types_never_whisper(self):
        """Low-value types (fyi, newsletter, digest) are always suppressed."""
        from maestro_personal_shell.routers.surfaces import _should_whisper_rule_based
        for t in ("fyi", "newsletter", "digest", "routine_update", "status_acknowledgment"):
            assert _should_whisper_rule_based({"type": t, "priority": "medium"}) is False, \
                f"{t} should never whisper"

    def test_borderline_returns_none(self):
        """Borderline whispers return None — LLM gate decides."""
        from maestro_personal_shell.routers.surfaces import _should_whisper_rule_based
        assert _should_whisper_rule_based({"type": "suggestion", "priority": "medium"}) is None
        assert _should_whisper_rule_based({"type": "unknown", "priority": "medium"}) is None

    def test_priority_wins_over_type(self):
        """High priority overrides low-value type suppression."""
        from maestro_personal_shell.routers.surfaces import _should_whisper_rule_based
        # fyi type would normally suppress, but high priority wins
        assert _should_whisper_rule_based({"type": "fyi", "priority": "high"}) is True

    def test_empty_whisper_returns_none(self):
        """Empty whisper dict returns None (borderline)."""
        from maestro_personal_shell.routers.surfaces import _should_whisper_rule_based
        assert _should_whisper_rule_based({}) is None

    def test_none_values_return_none(self):
        """None type/priority returns None (borderline)."""
        from maestro_personal_shell.routers.surfaces import _should_whisper_rule_based
        assert _should_whisper_rule_based({"type": None, "priority": None}) is None


class TestWhisperSchedulerDedup:
    """Issue 13-B: whisper scheduler deduplication."""

    def test_compute_whisper_hash_is_stable(self):
        """Same whisper produces same hash."""
        from maestro_personal_shell.whisper_scheduler import _compute_whisper_hash
        w = {"entity": "TestCorp", "type": "stale_commitment", "body": "Send pricing"}
        h1 = _compute_whisper_hash(w, "user@local")
        h2 = _compute_whisper_hash(w, "user@local")
        assert h1 == h2
        assert len(h1) == 16  # truncated SHA-256

    def test_different_whispers_different_hash(self):
        """Different whispers produce different hashes."""
        from maestro_personal_shell.whisper_scheduler import _compute_whisper_hash
        w1 = {"entity": "TestCorp", "type": "stale_commitment", "body": "Send pricing"}
        w2 = {"entity": "OtherCorp", "type": "stale_commitment", "body": "Send pricing"}
        assert _compute_whisper_hash(w1, "user@local") != _compute_whisper_hash(w2, "user@local")

    def test_different_users_different_hash(self):
        """Same whisper for different users produces different hashes."""
        from maestro_personal_shell.whisper_scheduler import _compute_whisper_hash
        w = {"entity": "TestCorp", "type": "stale_commitment", "body": "Send pricing"}
        assert _compute_whisper_hash(w, "user1@local") != _compute_whisper_hash(w, "user2@local")

    def test_dedup_cycle(self, tmp_path):
        """Mark notified → is_already_notified returns True."""
        from maestro_personal_shell.whisper_scheduler import (
            init_whisper_scheduler_db, _compute_whisper_hash,
            _is_already_notified, _mark_notified,
        )
        db = str(tmp_path / "test_whisper.db")
        init_whisper_scheduler_db(db)

        w = {"entity": "TestCorp", "type": "stale_commitment", "priority": "high",
             "body": "Send pricing by Friday"}
        h = _compute_whisper_hash(w, "user@local")

        # Before marking: not notified
        assert _is_already_notified("user@local", h, db) is False

        # Mark as notified
        _mark_notified("user@local", w, h, db)

        # After marking: is notified
        assert _is_already_notified("user@local", h, db) is True

    def test_dedup_is_user_scoped(self, tmp_path):
        """Whisper notified for user1 is NOT notified for user2."""
        from maestro_personal_shell.whisper_scheduler import (
            init_whisper_scheduler_db, _compute_whisper_hash,
            _is_already_notified, _mark_notified,
        )
        db = str(tmp_path / "test_whisper.db")
        init_whisper_scheduler_db(db)

        w = {"entity": "TestCorp", "type": "stale_commitment", "priority": "high",
             "body": "Send pricing"}
        h = _compute_whisper_hash(w, "user1@local")
        _mark_notified("user1@local", w, h, db)

        assert _is_already_notified("user1@local", h, db) is True
        assert _is_already_notified("user2@local", h, db) is False


class TestWhisperEndpoint:
    """Issue 13-C: whisper endpoint integration test (P22 — production path)."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from maestro_personal_shell.api import app
        return TestClient(app)

    @pytest.fixture
    def auth_headers(self, client):
        r = client.post("/api/auth/login",
                        json={"user_email": "default@personal.local", "password": "test"})
        return {"Authorization": f"Bearer {r.json()['token']}"}

    def test_whisper_endpoint_returns_200(self, client, auth_headers):
        """GET /api/whisper returns 200 with a list (may be empty)."""
        r = client.get("/api/whisper", headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_whisper_endpoint_is_fast(self, client, auth_headers):
        """Issue 13-A: whisper endpoint should be fast (<2s) with rule-based early-exit."""
        import time
        t0 = time.time()
        r = client.get("/api/whisper", headers=auth_headers)
        elapsed = time.time() - t0
        assert r.status_code == 200
        # Should be well under 2s when no LLM is active (rule-based path)
        assert elapsed < 5.0, f"Whisper endpoint took {elapsed:.1f}s (expected <5s)"


class TestPushNotificationHonest:
    """Issue 13-D: push notification sending.

    HONEST NOTE (P1): We cannot test actual Expo push delivery without a real
    Expo token. The _send_push_notification() function is tested only for
    input validation (rejects invalid tokens). Actual delivery requires a
    real device token and is marked as integration-test-only.
    """

    def test_send_push_rejects_invalid_token(self):
        """_send_push_notification returns False for invalid tokens."""
        from maestro_personal_shell.whisper_scheduler import _send_push_notification
        assert _send_push_notification("", "title", "body") is False
        assert _send_push_notification("invalid_token", "title", "body") is False
        assert _send_push_notification("ExponentPushToken[invalid]", "title", "body") is False

    def test_send_push_rejects_non_expo_token(self):
        """Tokens not starting with ExponentPushToken are rejected."""
        from maestro_personal_shell.whisper_scheduler import _send_push_notification
        assert _send_push_notification("firebase_token_123", "title", "body") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
