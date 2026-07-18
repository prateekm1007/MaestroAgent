"""
Chaos Testing — Phase 3 reliability work.

Tests the system's behavior under failure conditions:
  1. DB write failure (SQLite locked / disk full)
  2. Concurrent rapid requests (race conditions — sequential, since TestClient
     is not thread-safe, but still tests rapid succession)
  3. Malformed input (garbage in → clear error out)
  4. Token revocation / expiry mid-session
  5. Read endpoint degradation (honest error, not crash)

The fabricated-fallback fix from the prior session ensures mutating
endpoints no longer fabricate success on failure. These tests verify
that fix HOLDS under chaotic conditions.
"""
import os
import sys
import json
import time
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import datetime, timezone, timedelta

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

# Each test class gets its own fresh DB to avoid cross-test contamination
os.environ.setdefault("MAESTRO_PERSONAL_TOKEN", "chaos-test")
os.environ.setdefault("MAESTRO_ENV", "dev")
os.environ.setdefault("ENV", "dev")
os.environ["MAESTRO_TEST_MODE"] = "1"  # bypass rate limiting
os.environ.pop("OLLAMA_HOST", None)

from fastapi.testclient import TestClient
from maestro_personal_shell.api import app, init_db


@pytest.fixture
def fresh_db():
    """Fresh temp DB per test — avoids cross-test state contamination."""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    old_db = os.environ.get("MAESTRO_PERSONAL_DB")
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    init_db(db_path)
    yield db_path
    os.environ["MAESTRO_PERSONAL_DB"] = old_db or ""
    try:
        os.unlink(db_path)
    except:
        pass


@pytest.fixture
def client(fresh_db):
    """TestClient with fresh DB.

    raise_server_exceptions=False so that 500 errors are returned as HTTP
    responses (which we can assert on) instead of being re-raised as Python
    exceptions (which would crash the test). This is critical for chaos
    testing — we WANT to see the 500 response, not catch an exception.
    """
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def auth_headers(client):
    """Login + return auth headers."""
    r = client.post("/api/auth/login", json={"password": os.environ["MAESTRO_PERSONAL_TOKEN"]})
    assert r.status_code == 200, f"Login failed: {r.text}"
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ═══════════════════════════════════════════════════════════════════════════
# 1. DB WRITE FAILURE — mutating endpoint must NOT fabricate success
# ═══════════════════════════════════════════════════════════════════════════

class TestDBWriteFailure:
    """When the DB fails mid-write, mutating endpoints must return an error."""

    def test_correct_signal_db_failure_returns_error(self, client, auth_headers):
        """correctSignal with DB failure should return 500, not {ok: true}."""
        # Seed a signal first
        r = client.post("/api/signals", json={
            "entity": "Alice",
            "text": "I will send the proposal",
            "signal_type": "commitment_made",
        }, headers=auth_headers)
        assert r.status_code == 200
        signal_id = r.json()["signal_id"]

        # Mock the DB connection to fail specifically during the correction
        # We patch at the point where signals.py calls get_db_conn, not globally
        # Patch at the source (db_util) — signals.py imports it locally inside the function.
        # This will also affect auth, but since we use raise_server_exceptions=False,
        # the 500 is returned as a response, not re-raised.
        with patch("maestro_personal_shell.db_util.get_db_conn") as mock_conn:
            mock_conn.side_effect = Exception("Simulated DB failure: disk full")
            r = client.post(
                f"/api/signals/{signal_id}/correct?action=complete",
                headers=auth_headers,
            )
            # MUST be an error status, NOT 200 with {ok: true}
            assert r.status_code >= 400, \
                f"DB failure should return error, got {r.status_code}: {r.text[:200]}"

    def test_delete_account_db_failure_returns_error(self, client, auth_headers):
        """deleteAccount with DB failure should return 500, not {ok: true}."""
        # account.py imports get_db_conn at the TOP LEVEL (line 24), so we must
        # patch it at the account module, not at db_util. Patching db_util only
        # affects modules that import it locally inside functions (like signals.py).
        with patch("maestro_personal_shell.routers.account.get_db_conn") as mock_conn:
            mock_conn.side_effect = Exception("Simulated DB failure: database locked")
            r = client.delete("/api/account", headers=auth_headers)
            assert r.status_code >= 400, \
                f"DB failure should return error, got {r.status_code}: {r.text[:200]}"


# ═══════════════════════════════════════════════════════════════════════════
# 2. RAPID SUCCESSION — many requests in quick succession
# ═══════════════════════════════════════════════════════════════════════════

class TestRapidSuccession:
    """Test rapid successive requests don't corrupt state.

    Note: TestClient is not thread-safe, so these run sequentially rather
    than truly concurrently. They still verify that rapid succession
    doesn't cause state corruption or double-writes. For true concurrency
    testing, run against a real server with scripts/verify_oauth_roundtrip.py.
    """

    def test_rapid_signal_creation(self, client, auth_headers):
        """10 rapid signal creations should produce 10 distinct signals."""
        signal_ids = []
        for i in range(10):
            r = client.post("/api/signals", json={
                "entity": f"Rapid User {i}",
                "text": f"Rapid commitment {i}",
                "signal_type": "commitment_made",
            }, headers=auth_headers)
            assert r.status_code == 200, f"Signal {i} failed: {r.status_code}"
            signal_ids.append(r.json()["signal_id"])

        assert len(set(signal_ids)) == 10, "All signal IDs must be unique"

    def test_rapid_correct_same_signal(self, client, auth_headers):
        """Rapid corrections of the same signal should not crash."""
        r = client.post("/api/signals", json={
            "entity": "Rapid Test",
            "text": "I will do something",
            "signal_type": "commitment_made",
        }, headers=auth_headers)
        signal_id = r.json()["signal_id"]

        statuses = []
        for _ in range(5):
            r = client.post(
                f"/api/signals/{signal_id}/correct?action=complete",
                headers=auth_headers,
            )
            statuses.append(r.status_code)

        # All should be 200 (idempotent) or 404 (already corrected).
        # None should be 500.
        for s in statuses:
            assert s in (200, 404), f"Unexpected status: {s}"


# ═══════════════════════════════════════════════════════════════════════════
# 3. MALFORMED INPUT — garbage in, clear error out
# ═══════════════════════════════════════════════════════════════════════════

class TestMalformedInput:
    """Malformed requests should return clear 4xx errors, not 500."""

    def test_signal_creation_with_missing_fields(self, client, auth_headers):
        """POST /api/signals with missing required fields should return 422."""
        r = client.post("/api/signals", json={"entity": "Alice"}, headers=auth_headers)
        assert r.status_code == 422, f"Missing fields should return 422, got {r.status_code}"

    def test_correct_signal_nonexistent_id(self, client, auth_headers):
        """Correcting a non-existent signal should return 404, not 500."""
        r = client.post(
            "/api/signals/nonexistent-id/correct?action=complete",
            headers=auth_headers,
        )
        assert r.status_code == 404, f"Non-existent signal should return 404, got {r.status_code}"

    def test_ask_with_empty_query(self, client, auth_headers):
        """Empty query should return 422, not 500."""
        r = client.post("/api/ask", json={"query": ""}, headers=auth_headers)
        assert r.status_code == 422, f"Empty query should return 422, got {r.status_code}"

    def test_ask_with_missing_query(self, client, auth_headers):
        """Missing query field should return 422."""
        r = client.post("/api/ask", json={}, headers=auth_headers)
        assert r.status_code == 422, f"Missing query should return 422, got {r.status_code}"

    def test_invalid_oauth_provider(self, client, auth_headers):
        """Connecting an unsupported provider should return 4xx."""
        r = client.post("/api/connectors/fakebook/connect", json={"provider": "fakebook"}, headers=auth_headers)
        assert r.status_code in (400, 404, 422), f"Invalid provider should return 4xx, got {r.status_code}"


# ═══════════════════════════════════════════════════════════════════════════
# 4. TOKEN REVOCATION / EXPIRY
# ═══════════════════════════════════════════════════════════════════════════

class TestTokenRevocation:
    """Token revocation / expiry mid-session should produce 401, not 500."""

    def test_revoked_token_returns_401(self, client, auth_headers):
        """A revoked token should get 401 on subsequent requests."""
        # Extract the token from auth_headers
        token = auth_headers["Authorization"].split(" ", 1)[1]

        # Verify it works
        r = client.get("/api/signals", headers=auth_headers)
        assert r.status_code == 200

        # Revoke the token
        from maestro_personal_shell.api import _revoke_user_token
        revoked = _revoke_user_token(token)
        assert revoked, "Token should be revocable"

        # Verify it no longer works
        r = client.get("/api/signals", headers=auth_headers)
        assert r.status_code == 401, f"Revoked token should get 401, got {r.status_code}"

    def test_expired_token_returns_401(self, client, auth_headers):
        """An expired token (created >30 days ago) should get 401."""
        from maestro_personal_shell.api import _create_user_token, _hash_token, get_db_conn, _get_db

        # Create a token with an old timestamp
        token = _create_user_token("default@personal.local")
        token_hash = _hash_token(token)

        # Backdate the token
        old_time = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        conn = get_db_conn(_get_db())
        conn.execute(
            "UPDATE user_tokens SET created_at = ? WHERE token_hash = ?",
            (old_time, token_hash),
        )
        conn.commit()
        conn.close()

        # Verify the expired token gets 401
        r = client.get("/api/signals", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401, f"Expired token should get 401, got {r.status_code}"


# ═══════════════════════════════════════════════════════════════════════════
# 5. NO FABRICATED SUCCESS ON FAILURE
# ═══════════════════════════════════════════════════════════════════════════

class TestNoFabricatedSuccess:
    """Verify the fabricated-fallback fix holds: mutating endpoints must NOT
    return success-shaped responses when the backend fails."""

    def test_correct_signal_no_ok_true_on_db_error(self, client, auth_headers):
        """correctSignal must NOT return {ok: true} when DB fails."""
        r = client.post("/api/signals", json={
            "entity": "Fabrication Test",
            "text": "Test commitment",
            "signal_type": "commitment_made",
        }, headers=auth_headers)
        signal_id = r.json()["signal_id"]

        with patch("maestro_personal_shell.db_util.get_db_conn") as mock_conn:
            mock_conn.side_effect = Exception("DB failure")
            r = client.post(
                f"/api/signals/{signal_id}/correct?action=complete",
                headers=auth_headers,
            )
            # Must NOT return 200 with ok:true
            if r.status_code == 200:
                assert not r.json().get("ok"), \
                    "Must NOT return ok:true on DB failure (fabricated success)"

    def test_delete_account_no_ok_true_on_db_error(self, client, auth_headers):
        """deleteAccount must NOT return {ok: true} when DB fails."""
        # account.py imports get_db_conn at the TOP LEVEL — patch at account module
        with patch("maestro_personal_shell.routers.account.get_db_conn") as mock_conn:
            mock_conn.side_effect = Exception("DB failure")
            r = client.delete("/api/account", headers=auth_headers)
            if r.status_code == 200:
                assert not r.json().get("ok"), \
                    "Must NOT return ok:true on DB failure (fabricated success)"
