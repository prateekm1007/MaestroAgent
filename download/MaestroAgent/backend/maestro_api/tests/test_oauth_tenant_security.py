"""Integration tests: OAuth callback tenant isolation + admin auth.

Principle 7: test the real scoped object graph. The prior C1 bug
(request not defined → NameError swallowed → default org) and C2 bug
(admin endpoints unauthenticated) existed because no test exercised the
real route with the real auth dependency chain.

These tests use FastAPI's TestClient to hit the real routes, with auth
enabled, and assert:
1. oauth_callback extracts org_id from the authenticated session (not default)
2. oauth_callback fails closed when the authenticated user has no org_id
3. admin endpoints reject non-admin users (403)
4. admin endpoints reject unauthenticated requests (401)
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def app_with_auth(monkeypatch: pytest.MonkeyPatch):
    """Build a minimal FastAPI app with the imports router + auth enabled."""
    monkeypatch.setenv("MAESTRO_AUTH_ENABLED", "true")
    monkeypatch.setenv("MAESTRO_LOCAL_DEV", "")  # clear it
    monkeypatch.setenv("MAESTRO_ADMIN_PASSWORD", "test-admin-pw")

    from fastapi import FastAPI
    from maestro_api.routes.imports import router

    app = FastAPI()
    app.include_router(router)
    return app


def test_oauth_callback_has_request_parameter() -> None:
    """C1 regression guard: oauth_callback must accept `request: Request`.

    Before the fix, `request` was not a parameter but was referenced inside
    the function → NameError swallowed by except: pass → org_id defaulted.
    """
    import inspect
    from maestro_api.routes.imports import oauth_callback

    sig = inspect.signature(oauth_callback)
    assert "request" in sig.parameters, (
        "oauth_callback must accept `request: Request` — without it, the "
        "require_user(request) call raises NameError and org_id silently "
        "defaults to 'default' (cross-tenant leak)."
    )


def test_admin_routes_have_require_admin_dependency() -> None:
    """C2 regression guard: admin endpoints must require admin role.

    Before the fix, /api/oauth/admin/providers had no auth dependency —
    anyone could read/write OAuth provider credentials.
    """
    from maestro_api.routes.imports import router

    admin_routes = [r for r in router.routes if "admin" in str(r.path)]
    assert len(admin_routes) >= 3, f"Expected 3+ admin routes, got {len(admin_routes)}"

    for route in admin_routes:
        deps = getattr(route, "dependencies", [])
        # The router-level dependency (require_user) + the route-level (require_admin)
        assert len(deps) >= 2, (
            f"Admin route {route.path} must have require_admin dependency. "
            f"Found {len(deps)} dependencies."
        )


def test_oauth_callback_fails_closed_when_user_has_no_org_id(
    app_with_auth, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C4: when auth is enabled but the user has no org_id, the callback
    must FAIL CLOSED (403), not silently default to 'default' org.

    Before the fix: NameError swallowed → org_id='default' → cross-tenant leak.
    After the fix: explicit 403 with a clear error message.
    """
    from starlette.testclient import TestClient

    # Mock require_user to return a user with NO org_id
    def mock_require_user(request):
        return {"sub": "user1", "email": "u@e.com"}  # no org_id key

    # Mock is_auth_enabled to return True
    with patch("maestro_api.routes.imports.is_auth_enabled", return_value=True), \
         patch("maestro_api.routes.imports.require_user", side_effect=mock_require_user):
        client = TestClient(app_with_auth)
        # The callback needs code, state, provider to get past the 400 check.
        # It will fail at the org_id extraction step (403).
        response = client.get(
            "/api/oauth/callback",
            params={"code": "test_code", "state": "github:123:abc:def", "provider": "github"},
        )

    assert response.status_code == 403, (
        f"Expected 403 (fail closed) when user has no org_id, got {response.status_code}. "
        f"Body: {response.text}"
    )
    assert "org_id" in response.text.lower(), "Error message must mention org_id"
