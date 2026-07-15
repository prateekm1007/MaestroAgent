"""
P1-4 regression test — Finding S7: "Plaintext tokens."

THE BUG (independent product audit):
    Tokens were stored in plaintext in the user_tokens table. If the
    database is compromised, attackers can use the tokens directly.
    There was also no revocation endpoint and no token rotation.

THE FIX:
    1. Hash tokens with SHA-256 before storing. The DB stores
       token_hash (64-char hex), not the plaintext token.
    2. At verification, the incoming token is hashed and compared.
    3. Added POST /api/auth/revoke — revokes all tokens for the caller.
    4. Added POST /api/auth/rotate — issues a new token, revokes old ones.

THE PROOF (this test):
    1. Tokens are stored as SHA-256 hashes (not plaintext)
    2. The plaintext token cannot be found in the DB
    3. Revocation works — revoked tokens are rejected
    4. Rotation works — old token invalid, new token valid

Governance: P1 (execute), P2 (tests fail on old code), P22 (integration
test through REAL production entry points: /api/auth/login, /api/auth/
revoke, /api/auth/rotate).
"""

import sys
import os
import tempfile
import sqlite3
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


@pytest.fixture
def isolated_api():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-p1-4"
    os.environ.pop("MAESTRO_PERSONAL_ENV", None)

    import importlib
    import maestro_personal_shell.api as api_module
    importlib.reload(api_module)
    api_module.init_db(db_path)

    yield api_module

    os.unlink(db_path)
    os.environ.pop("MAESTRO_PERSONAL_DB", None)
    os.environ.pop("MAESTRO_PERSONAL_TOKEN", None)


@pytest.fixture
def client(isolated_api):
    return TestClient(isolated_api.app)


def _login(client, user_email="p1-4@test.com"):
    resp = client.post("/api/auth/login", json={
        "user_email": user_email,
        "password": os.environ["MAESTRO_PERSONAL_TOKEN"],
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["token"]


class TestTokenHashing:
    """Tokens must be stored as SHA-256 hashes, not plaintext."""

    def test_token_stored_as_hash(self, client):
        """The user_tokens table must contain the SHA-256 hash, not the
        plaintext token."""
        token = _login(client, "hash-test@test.com")

        db_path = os.environ["MAESTRO_PERSONAL_DB"]
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT token_hash, user_email FROM user_tokens WHERE user_email = ?",
            ("hash-test@test.com",),
        ).fetchall()
        conn.close()

        assert len(rows) >= 1, "Token should be stored"
        stored_hash = rows[0][0]
        # The stored value must NOT be the plaintext token
        assert stored_hash != token, (
            "P1-4 FAIL: Token stored in plaintext! The DB contains the raw token. "
            "Should be a SHA-256 hash."
        )
        # The stored value must be a 64-char hex string (SHA-256)
        assert len(stored_hash) == 64, (
            f"P1-4 FAIL: Stored token hash should be 64 chars (SHA-256 hex), "
            f"got {len(stored_hash)} chars: {stored_hash[:20]}..."
        )
        # Verify it's the SHA-256 hash of the token
        import hashlib
        expected_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        assert stored_hash == expected_hash, (
            f"P1-4 FAIL: Stored hash doesn't match SHA-256(token). "
            f"Expected: {expected_hash}, Got: {stored_hash}"
        )

    def test_plaintext_token_not_in_db(self, client):
        """The plaintext token must NOT appear anywhere in the DB."""
        token = _login(client, "plaintext-test@test.com")

        db_path = os.environ["MAESTRO_PERSONAL_DB"]
        conn = sqlite3.connect(db_path)
        # Search ALL tables for the plaintext token
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        for (table_name,) in tables:
            if table_name == "sqlite_sequence":
                continue
            try:
                rows = conn.execute(f"SELECT * FROM {table_name}").fetchall()
                for row in rows:
                    for val in row:
                        if isinstance(val, str) and token in val:
                            conn.close()
                            pytest.fail(
                                f"P1-4 FAIL: Plaintext token found in table "
                                f"'{table_name}'! Token should only exist as a hash."
                            )
            except Exception:
                pass
        conn.close()

    def test_hash_token_function(self):
        """_hash_token must return a SHA-256 hex digest."""
        from maestro_personal_shell.api import _hash_token
        import hashlib
        token = "test-token-123"
        result = _hash_token(token)
        expected = hashlib.sha256(token.encode("utf-8")).hexdigest()
        assert result == expected
        assert len(result) == 64
        # Same input → same hash (deterministic)
        assert _hash_token(token) == result
        # Different input → different hash
        assert _hash_token("different-token") != result


class TestTokenRevocation:
    """POST /api/auth/revoke must invalidate the caller's token."""

    def test_revoke_invalidates_token(self, client):
        """After revocation, the token must be rejected (401)."""
        token = _login(client, "revoke-test@test.com")
        headers = {"Authorization": f"Bearer {token}"}

        # Verify token works before revocation
        resp = client.get("/api/signals", headers=headers)
        assert resp.status_code == 200, "Token should work before revocation"

        # Revoke
        resp = client.post("/api/auth/revoke", headers=headers)
        assert resp.status_code == 200, f"Revoke failed: {resp.text}"
        assert resp.json()["revoked"] is True
        assert resp.json()["tokens_revoked"] >= 1

        # Verify token is now rejected
        resp = client.get("/api/signals", headers=headers)
        assert resp.status_code == 401, (
            f"P1-4 FAIL: Token should be rejected after revocation, "
            f"got {resp.status_code}. The token is still valid!"
        )

    def test_revoke_logs_out_all_sessions(self, client):
        """Revoking should log out ALL tokens for the user, not just the
        current one."""
        token1 = _login(client, "multi-session@test.com")
        token2 = _login(client, "multi-session@test.com")
        headers1 = {"Authorization": f"Bearer {token1}"}
        headers2 = {"Authorization": f"Bearer {token2}"}

        # Both tokens work
        assert client.get("/api/signals", headers=headers1).status_code == 200
        assert client.get("/api/signals", headers=headers2).status_code == 200

        # Revoke using token1
        resp = client.post("/api/auth/revoke", headers=headers1)
        assert resp.status_code == 200
        assert resp.json()["tokens_revoked"] >= 2, (
            f"Should revoke ALL tokens for the user (at least 2), "
            f"got {resp.json()['tokens_revoked']}"
        )

        # Both tokens should now be invalid
        assert client.get("/api/signals", headers=headers1).status_code == 401
        assert client.get("/api/signals", headers=headers2).status_code == 401


class TestTokenRotation:
    """POST /api/auth/rotate must issue a new token and invalidate old ones."""

    def test_rotate_issues_new_token(self, client):
        """Rotation must return a new, different token."""
        old_token = _login(client, "rotate-test@test.com")
        headers = {"Authorization": f"Bearer {old_token}"}

        resp = client.post("/api/auth/rotate", headers=headers)
        assert resp.status_code == 200, f"Rotate failed: {resp.text}"
        data = resp.json()
        new_token = data["token"]
        assert new_token != old_token, (
            "P1-4 FAIL: Rotated token should be different from the old token"
        )
        assert data["old_tokens_revoked"] >= 1

    def test_rotate_invalidates_old_token(self, client):
        """After rotation, the old token must be rejected."""
        old_token = _login(client, "rotate-old@test.com")
        headers = {"Authorization": f"Bearer {old_token}"}

        resp = client.post("/api/auth/rotate", headers=headers)
        new_token = resp.json()["token"]

        # Old token should be rejected
        resp = client.get("/api/signals", headers=headers)
        assert resp.status_code == 401, (
            "P1-4 FAIL: Old token should be invalid after rotation"
        )

        # New token should work
        new_headers = {"Authorization": f"Bearer {new_token}"}
        resp = client.get("/api/signals", headers=new_headers)
        assert resp.status_code == 200, (
            f"P1-4 FAIL: New token should work after rotation, "
            f"got {resp.status_code}"
        )

    def test_rotate_preserves_user_email(self, client):
        """The new token must be for the same user_email."""
        token = _login(client, "rotate-identity@test.com")
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.post("/api/auth/rotate", headers=headers)
        data = resp.json()
        assert data["user_email"] == "rotate-identity@test.com", (
            f"Rotated token should be for the same user. "
            f"Got: {data['user_email']}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
