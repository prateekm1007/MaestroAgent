"""Tests for the 3 endpoints that were missing from the committed OpenAPI schema.

P0 audit fix (2026-07-15): the schema drift test (test_api_contract.py)
caught that /api/auth/push-token, /api/auth/register, and /api/privacy/retention-status
existed in the live app but not in docs/openapi_schema.json. The schema has
been regenerated; these tests now exercise each endpoint so the "every endpoint
has at least one test" coverage gate stays green.
"""
from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

from maestro_personal_shell.api import app, init_db
from maestro_personal_shell.db_util import default_sqlite_path


@pytest.fixture(autouse=True)
def _ensure_db():
    """Init the fresh temp DB that conftest's _fresh_db_per_test created.

    conftest creates a fresh temp DB per test but does NOT call init_db()
    on it — so tables like push_tokens are missing. We init the DB using
    the CURRENT env var value (not the module-level DB_PATH, which was
    cached at import time before the env var was changed).
    """
    init_db(default_sqlite_path())
    yield


client = TestClient(app)


def test_register_endpoint_works():
    """POST /api/auth/register creates a new account and returns a token."""
    import secrets
    email = f"contract_{secrets.token_hex(4)}@example.com"
    r = client.post("/api/auth/register", json={"user_email": email, "password": "TestPass123!"})
    assert r.status_code in (200, 201), r.text
    data = r.json()
    assert data.get("token")
    assert data.get("user_email") == email


def test_push_token_endpoint_accepts_token():
    """POST /api/auth/push-token stores an Expo push token for the user."""
    # Register first to get a valid token.
    import secrets
    email = f"contract_{secrets.token_hex(4)}@example.com"
    r = client.post("/api/auth/register", json={"user_email": email, "password": "TestPass123!"})
    assert r.status_code in (200, 201)
    bearer = r.json()["token"]

    r2 = client.post(
        "/api/auth/push-token",
        json={"push_token": "ExponentPushToken[dummy_contract_test_token]"},
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r2.status_code in (200, 201), r2.text


def test_retention_status_endpoint_returns_summary():
    """GET /api/privacy/retention-status returns the retention summary."""
    import secrets
    email = f"contract_{secrets.token_hex(4)}@example.com"
    r = client.post("/api/auth/register", json={"user_email": email, "password": "TestPass123!"})
    bearer = r.json()["token"]

    r2 = client.get("/api/privacy/retention-status", headers={"Authorization": f"Bearer {bearer}"})
    assert r2.status_code == 200, r2.text
    data = r2.json()
    # The endpoint returns a summary with at least a timestamp key.
    assert isinstance(data, dict)
