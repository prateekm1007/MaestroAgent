"""P2 fix (audit R68): disposable-account privacy flow tests.

The audit noted: 'Destructive privacy flows (DELETE /api/account,
POST /api/account/export) — verify against a disposable test account.'

This test file exercises the full account lifecycle against a disposable
test account:
  1. Register a new account
  2. Seed signals
  3. Export the data (verify signals appear in export)
  4. Delete the account (verify all data is wiped)
  5. Verify the account can no longer authenticate

Each test uses a fresh disposable account so there's no risk to real data.
"""
from __future__ import annotations

import os
import sys
import secrets
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


@pytest.fixture(autouse=True)
def _clean_db():
    """Use a fresh temp DB for each test, bypassing conftest's _fresh_db_per_test.

    The conftest fixture changes MAESTRO_PERSONAL_DB after module import,
    which causes a mismatch: save_signal_to_db uses the module-level DB_PATH
    (cached at import), while /api/account/export reads the env var fresh.
    This fixture sets the env var BEFORE importing the app module, so both
    paths point to the same fresh DB.
    """
    import tempfile
    _saved_db = os.environ.get("MAESTRO_PERSONAL_DB")
    _saved_token = os.environ.pop("MAESTRO_PERSONAL_TOKEN", None)
    _saved_env = os.environ.get("MAESTRO_PERSONAL_ENV")

    # Create a fresh temp DB
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="maestro_p2_")
    tmp.close()
    os.environ["MAESTRO_PERSONAL_DB"] = tmp.name
    os.environ["MAESTRO_PERSONAL_ENV"] = "production"  # disable bootstrap token

    # Reimport the api module so DB_PATH picks up the new env var
    import importlib
    import maestro_personal_shell.api as _api
    importlib.reload(_api)
    _api.init_db(tmp.name)

    yield

    # Restore
    if _saved_db is not None:
        os.environ["MAESTRO_PERSONAL_DB"] = _saved_db
    else:
        os.environ.pop("MAESTRO_PERSONAL_DB", None)
    if _saved_token is not None:
        os.environ["MAESTRO_PERSONAL_TOKEN"] = _saved_token
    if _saved_env is not None:
        os.environ["MAESTRO_PERSONAL_ENV"] = _saved_env
    else:
        os.environ.pop("MAESTRO_PERSONAL_ENV", None)

    try:
        os.unlink(tmp.name)
    except OSError:
        pass


# Import app AFTER the fixture is defined so tests use the reloaded module
from maestro_personal_shell.api import app  # noqa: E402
client = TestClient(app)


def _register_disposable_account() -> tuple[str, str]:
    """Register a fresh disposable account and return (email, bearer_token)."""
    email = f"disposable_{secrets.token_hex(8)}@example.com"
    r = client.post("/api/auth/register", json={"user_email": email, "password": "TestPass123!"})
    assert r.status_code in (200, 201), f"Register failed: {r.status_code} {r.text}"
    token = r.json()["token"]
    return email, token


def _seed_signals(token: str, count: int = 3) -> None:
    """Seed `count` signals for the given user."""
    headers = {"Authorization": f"Bearer {token}"}
    for i in range(count):
        client.post("/api/signals", headers=headers, json={
            "entity": f"TestEntity{i}",
            "text": f"I will deliver item {i} by Friday",
            "signal_type": "commitment_made",
        })


class TestDisposableAccountLifecycle:
    """Test the full account lifecycle with disposable accounts."""

    def test_register_seed_export_delete_lifecycle(self):
        """Full lifecycle: register → seed → export → delete → verify gone."""
        # 1. Register
        email, token = _register_disposable_account()
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Seed signals
        _seed_signals(token, count=3)

        # Verify signals exist
        r = client.get("/api/signals", headers=headers)
        assert r.status_code == 200
        signals = r.json()
        assert len(signals) >= 3, f"Expected 3+ signals, got {len(signals)}"

        # 3. Export the data
        r = client.get("/api/account/export", headers=headers)
        assert r.status_code == 200
        export = r.json()
        assert export["signal_count"] >= 3, f"Export should have 3+ signals, got {export['signal_count']}"
        assert len(export["signals"]) >= 3
        assert export["exported_at"]  # timestamp present

        # 4. Delete the account
        r = client.delete("/api/account", headers=headers)
        assert r.status_code == 200, f"Delete failed: {r.status_code} {r.text}"

        # 5. Verify the token no longer works
        r = client.get("/api/signals", headers=headers)
        assert r.status_code == 401, f"Token should be revoked after delete, got {r.status_code}"

    def test_export_contains_correct_user_data_only(self):
        """Export should only contain the requesting user's data, not other users'."""
        # Register two users
        email_a, token_a = _register_disposable_account()
        email_b, token_b = _register_disposable_account()

        # Seed signals for both
        _seed_signals(token_a, count=2)
        _seed_signals(token_b, count=3)

        # Export user A — should only have A's 2 signals
        r = client.get("/api/account/export", headers={"Authorization": f"Bearer {token_a}"})
        assert r.status_code == 200
        export_a = r.json()
        assert export_a["signal_count"] == 2, f"User A should have 2 signals, got {export_a['signal_count']}"

        # Export user B — should only have B's 3 signals
        r = client.get("/api/account/export", headers={"Authorization": f"Bearer {token_b}"})
        assert r.status_code == 200
        export_b = r.json()
        assert export_b["signal_count"] == 3, f"User B should have 3 signals, got {export_b['signal_count']}"

    def test_delete_wipes_all_user_data(self):
        """After delete, the user's signals should be gone from the DB."""
        email, token = _register_disposable_account()
        headers = {"Authorization": f"Bearer {token}"}

        # Seed signals
        _seed_signals(token, count=5)

        # Verify they exist
        r = client.get("/api/signals", headers=headers)
        assert len(r.json()) >= 5

        # Delete account
        r = client.delete("/api/account", headers=headers)
        assert r.status_code == 200

        # Verify the signals are gone — register a new account and check
        # that the deleted user's signals don't appear for anyone else.
        # (The deleted user's token is revoked, so we can't query as them.)
        # Instead, verify directly via the DB that the user's signals are gone.
        from maestro_personal_shell.db_util import get_db_conn
        db_path = os.environ.get("MAESTRO_PERSONAL_DB")
        db = get_db_conn(db_path)
        count = db.execute(
            "SELECT COUNT(*) FROM signals WHERE user_email = ?", (email,)
        ).fetchone()[0]
        db.close()
        assert count == 0, f"Deleted user's signals should be gone, found {count}"

    def test_delete_account_idempotent_after_revoke(self):
        """A second delete call with the revoked token should return 401."""
        email, token = _register_disposable_account()
        headers = {"Authorization": f"Bearer {token}"}

        # First delete — should succeed
        r = client.delete("/api/account", headers=headers)
        assert r.status_code == 200

        # Second delete — token is revoked, should 401
        r = client.delete("/api/account", headers=headers)
        assert r.status_code == 401

    def test_export_requires_auth(self):
        """Export without a token should return 401."""
        r = client.get("/api/account/export")
        assert r.status_code == 401

    def test_delete_requires_auth(self):
        """Delete without a token should return 401."""
        r = client.delete("/api/account")
        assert r.status_code == 401
