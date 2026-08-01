"""TICKET-9 / P68 regression test — shared auth fixture must use the current API schema.

The original TICKET-9 bug: the shared `auth_headers` fixture (and 51 per-file
copies) used the legacy `{"password": ...}` login schema, which the current
API rejects with HTTP 401/422. This caused 1244 pytest ERRORS (fixture setup
failures) that hid the real regression rate.

The fix (commits 43cc0e7 + 085ceb1, 2026-07-25):
  1. Added a shared `client` + `auth_headers` fixture to conftest.py using the
     CURRENT register schema (`user_email + password → token`).
  2. Migrated all 51 per-file `auth_headers` fixtures from the legacy login
     call to the current register call.

This test file codifies the fix so it cannot silently regress. If any of the
following break, the TICKET-9 bug class has returned:

  * The shared `auth_headers` fixture must return valid `Bearer <token>` headers.
  * The legacy `{"password": ...}` login call must be rejected (HTTP 401 or 422).
  * The current `{"user_email": ..., "password": ...}` register call must
    succeed (HTTP 200) and return a `token` field.

P47 honest attribution: CTO-authored, P68 enforced via grep-able regression
test rather than governance prose.
"""

import pytest


class TestTicket9AuthFixture:
    """TICKET-9 regression: shared auth fixture must use current API schema."""

    def test_shared_auth_headers_fixture_returns_bearer_token(self, client, auth_headers):
        """The shared `auth_headers` fixture (from conftest.py) must succeed.

        This is the canonical fixture all test files SHOULD use. If it breaks,
        every test that depends on it will error out — reproducing the
        original 1244-error TICKET-9 bug.
        """
        assert isinstance(auth_headers, dict), \
            f"auth_headers must be a dict, got {type(auth_headers)}"
        assert "Authorization" in auth_headers, \
            f"auth_headers must contain 'Authorization' key, got keys: {list(auth_headers)}"
        auth_value = auth_headers["Authorization"]
        assert auth_value.startswith("Bearer "), \
            f"Authorization header must be 'Bearer <token>', got: {auth_value[:30]}"
        token = auth_value[len("Bearer "):]
        assert len(token) > 10, \
            f"Token must be non-trivially long, got len={len(token)}"

    def test_shared_auth_headers_fixture_token_works(self, client, auth_headers):
        """The token from the shared fixture must authenticate to a protected endpoint.

        If the token is malformed or invalid, protected endpoints return 401.
        This catches the case where the register call succeeds but the token
        is broken (e.g. wrong signing key, missing fields).
        """
        # /api/connectors requires auth — should return 200, not 401/403
        r = client.get("/api/connectors", headers=auth_headers)
        assert r.status_code == 200, \
            f"Token from shared fixture must authenticate (expected 200, got {r.status_code}): {r.text[:200]}"

    def test_legacy_password_only_login_is_rejected(self, client):
        """The legacy `{"password": ...}` login schema MUST be rejected.

        This is the schema that caused TICKET-9. If the API ever accepts it
        again, the shared fixture's register call could be silently swapped
        back to login, reintroducing the bug class.
        """
        # The legacy call used MAESTRO_PERSONAL_TOKEN env var as password
        # with no user_email field. Current API must reject this with a
        # 4xx (400/401/422 — exact code depends on validation layer).
        r = client.post("/api/auth/login", json={"password": "maestro-demo"})
        assert r.status_code in (400, 401, 422), \
            f"Legacy password-only login must be rejected (400/401/422), got {r.status_code}: {r.text[:200]}"

    def test_current_register_schema_returns_token(self, client):
        """The current `user_email + password` register schema MUST work.

        This is the schema the shared fixture depends on. If the register
        endpoint ever changes its payload contract without updating conftest.py,
        this test will fail before the 1244-error cascade can recur.
        """
        import uuid
        email = f"ticket9-reg-{uuid.uuid4().hex[:8]}@example.com"
        r = client.post("/api/auth/register", json={
            "user_email": email,
            "password": "TestPassword123!",
            "name": "Ticket9",
        })
        assert r.status_code == 200, \
            f"Register with current schema must succeed (200), got {r.status_code}: {r.text[:200]}"
        data = r.json()
        assert "token" in data, \
            f"Register response must contain 'token' field, got keys: {list(data.keys())}"
        assert len(data["token"]) > 10, \
            f"Token must be non-trivially long, got len={len(data['token'])}"

    def test_register_then_login_roundtrip(self, client):
        """Register a user, then log in with the same creds — must succeed.

        Catches the case where register works but login is broken (or vice
        versa). Both endpoints must accept the same `user_email + password`
        payload shape.
        """
        import uuid
        email = f"ticket9-roundtrip-{uuid.uuid4().hex[:8]}@example.com"
        password = "TestPassword123!"

        # Register
        r1 = client.post("/api/auth/register", json={
            "user_email": email,
            "password": password,
            "name": "Roundtrip",
        })
        assert r1.status_code == 200, f"Register failed: {r1.status_code} {r1.text[:200]}"

        # Login with same creds
        r2 = client.post("/api/auth/login", json={
            "user_email": email,
            "password": password,
        })
        assert r2.status_code == 200, f"Login failed: {r2.status_code} {r2.text[:200]}"
        assert r2.json().get("token"), "Login response missing token"
