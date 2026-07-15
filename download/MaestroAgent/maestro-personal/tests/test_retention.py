"""
Step 15: Privacy TTL enforcement tests.

Tests the retention_enforcer module:
  - TTL configuration is correct
  - enforce_retention() purges old data
  - enforce_retention() preserves recent data
  - get_retention_policy() returns correct config
  - The retention-status endpoint works
"""
import os
import sys
import asyncio
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
os.environ.setdefault("MAESTRO_PERSONAL_TOKEN", "test")
os.environ.setdefault("MAESTRO_ENV", "dev")
os.environ.pop("OLLAMA_HOST", None)


class TestRetentionPolicy:
    """Test the retention TTL configuration."""

    def test_policy_returns_all_ttls(self):
        """get_retention_policy() returns all 5 TTL categories."""
        from maestro_personal_shell.retention_enforcer import get_retention_policy
        policy = get_retention_policy()
        assert "auth_tokens_days" in policy
        assert "audit_log_days" in policy
        assert "pending_drafts_days" in policy
        assert "notified_stale_days" in policy
        assert "inactive_push_tokens_days" in policy
        assert "signals" in policy
        assert "oauth_tokens" in policy

    def test_signals_have_no_ttl(self):
        """Signals (user's core data) must NOT have a TTL."""
        from maestro_personal_shell.retention_enforcer import get_retention_policy
        policy = get_retention_policy()
        assert "no TTL" in policy["signals"], "Signals must not have a TTL"

    def test_oauth_tokens_have_no_ttl(self):
        """OAuth tokens must NOT have a TTL (kept until disconnect)."""
        from maestro_personal_shell.retention_enforcer import get_retention_policy
        policy = get_retention_policy()
        assert "no TTL" in policy["oauth_tokens"], "OAuth tokens must not have a TTL"

    def test_ttls_are_reasonable(self):
        """TTLs should be reasonable (not 0, not 10000)."""
        from maestro_personal_shell.retention_enforcer import (
            TTL_AUTH_TOKENS_DAYS, TTL_AUDIT_LOG_DAYS, TTL_PENDING_DRAFTS_DAYS,
            TTL_NOTIFIED_STALE_DAYS, TTL_INACTIVE_PUSH_TOKENS_DAYS,
        )
        for ttl in [TTL_AUTH_TOKENS_DAYS, TTL_AUDIT_LOG_DAYS, TTL_PENDING_DRAFTS_DAYS,
                     TTL_NOTIFIED_STALE_DAYS, TTL_INACTIVE_PUSH_TOKENS_DAYS]:
            assert 1 <= ttl <= 365, f"TTL {ttl} is out of reasonable range"


class TestRetentionEnforcement:
    """Test the enforce_retention() function."""

    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create a temp DB with test data."""
        db_path = str(tmp_path / "test_retention.db")
        os.environ["MAESTRO_PERSONAL_DB"] = db_path

        from maestro_personal_shell.db_util import get_db_conn
        from maestro_personal_shell.api import init_db
        init_db(db_path)

        db = get_db_conn(db_path)

        # Insert old auth token (should be purged — inactive + >30 days)
        old_date = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
        db.execute(
            "INSERT INTO auth_tokens (token, created_at, active) VALUES (?, ?, 0)",
            ("old-inactive-token", old_date),
        )

        # Insert recent auth token (should be kept — active)
        recent_date = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT INTO auth_tokens (token, created_at, active) VALUES (?, ?, 1)",
            ("recent-active-token", recent_date),
        )

        # Insert old notified_stale entry (should be purged — >30 days)
        db.execute(
            "INSERT INTO notified_stale (signal_id, notified_at) VALUES (?, ?)",
            ("old-signal-1", old_date),
        )

        # Insert recent notified_stale entry (should be kept)
        db.execute(
            "INSERT INTO notified_stale (signal_id, notified_at) VALUES (?, ?)",
            ("recent-signal-1", recent_date),
        )

        db.commit()
        db.close()

        yield db_path

        # Cleanup
        try:
            os.unlink(db_path)
        except OSError:
            pass

    def test_enforce_retention_purges_old_data(self, temp_db):
        """enforce_retention() purges data older than the TTL."""
        from maestro_personal_shell.retention_enforcer import enforce_retention
        from maestro_personal_shell.db_util import get_db_conn

        result = asyncio.run(enforce_retention(temp_db))

        # Old inactive auth token should be purged
        assert result["auth_tokens_purged"] >= 1, "Old inactive auth token should be purged"

        # Old notified_stale entry should be purged
        assert result["notified_stale_purged"] >= 1, "Old notified_stale entry should be purged"

        # Verify the old data is actually gone
        db = get_db_conn(temp_db)
        old_token = db.execute(
            "SELECT 1 FROM auth_tokens WHERE token = ?", ("old-inactive-token",)
        ).fetchone()
        assert old_token is None, "Old inactive token should be deleted"

        old_stale = db.execute(
            "SELECT 1 FROM notified_stale WHERE signal_id = ?", ("old-signal-1",)
        ).fetchone()
        assert old_stale is None, "Old notified_stale entry should be deleted"
        db.close()

    def test_enforce_retention_preserves_recent_data(self, temp_db):
        """enforce_retention() does NOT purge recent data."""
        from maestro_personal_shell.retention_enforcer import enforce_retention
        from maestro_personal_shell.db_util import get_db_conn

        asyncio.run(enforce_retention(temp_db))

        db = get_db_conn(temp_db)
        # Recent active token should still exist
        recent_token = db.execute(
            "SELECT 1 FROM auth_tokens WHERE token = ?", ("recent-active-token",)
        ).fetchone()
        assert recent_token is not None, "Recent active token should be preserved"

        # Recent notified_stale entry should still exist
        recent_stale = db.execute(
            "SELECT 1 FROM notified_stale WHERE signal_id = ?", ("recent-signal-1",)
        ).fetchone()
        assert recent_stale is not None, "Recent notified_stale entry should be preserved"
        db.close()

    def test_enforce_retention_returns_summary(self, temp_db):
        """enforce_retention() returns a summary dict with counts."""
        from maestro_personal_shell.retention_enforcer import enforce_retention

        result = asyncio.run(enforce_retention(temp_db))

        assert "auth_tokens_purged" in result
        assert "audit_log_purged" in result
        assert "pending_drafts_purged" in result
        assert "notified_stale_purged" in result
        assert "inactive_push_tokens_purged" in result
        assert "timestamp" in result


class TestRetentionEndpoint:
    """Test the GET /api/privacy/retention-status endpoint."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from maestro_personal_shell.api import app, init_db
        os.environ["MAESTRO_PERSONAL_TOKEN"] = "test"
        os.environ["MAESTRO_ENV"] = "dev"
        init_db()
        return TestClient(app)

    @pytest.fixture
    def auth_headers(self, client):
        r = client.post("/api/auth/login",
                        json={"user_email": "default@personal.local", "password": "test"})
        assert r.status_code == 200, f"Login failed: {r.status_code}"
        return {"Authorization": f"Bearer {r.json()['token']}"}

    def test_retention_status_returns_200(self, client, auth_headers):
        """GET /api/privacy/retention-status returns 200 with TTL config."""
        r = client.get("/api/privacy/retention-status", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "policy" in data
        assert "enforcement" in data
        assert "user_controls" in data

    def test_retention_status_shows_ttls(self, client, auth_headers):
        """The response includes all TTL values."""
        r = client.get("/api/privacy/retention-status", headers=auth_headers)
        policy = r.json()["policy"]
        assert policy["auth_tokens_days"] > 0
        assert policy["audit_log_days"] > 0
        assert "no TTL" in policy["signals"]

    def test_retention_status_shows_user_controls(self, client, auth_headers):
        """The response includes user controls (export, delete, disconnect)."""
        r = client.get("/api/privacy/retention-status", headers=auth_headers)
        controls = r.json()["user_controls"]
        assert "export_all_data" in controls
        assert "delete_all_data" in controls
        assert "disconnect_connector" in controls


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
