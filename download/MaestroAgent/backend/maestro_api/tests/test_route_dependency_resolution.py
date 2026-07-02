"""Integration test: every route resolves without spurious query params.

This test would have caught the lambda 422 bug (CRITICAL). It constructs
the real FastAPI app, generates the OpenAPI schema, and asserts no route
has a spurious 'r' query parameter — which indicates a lambda dependency
that FastAPI couldn't resolve as a Request injection.

Root cause (P10): 7 routers used `Depends(lambda r: ...)` instead of a
named function with `request: Request` type annotation. FastAPI treated
`r` as a required query parameter, causing 422 errors on every affected
route. The fix: replace each lambda with a typed function.

Principle 7: test the real object graph — construct the real app and
inspect its schema, not just import the router modules.
"""

from __future__ import annotations

import os

# Set MAESTRO_APP_DIR so create_app() can find app.html
os.environ.setdefault("MAESTRO_APP_DIR", os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

import pytest


# The `app` fixture is provided by conftest.py (session-scoped, shared).


def test_no_route_has_spurious_r_query_param(app) -> None:
    """No route should have a spurious 'r' query parameter.

    A spurious 'r' param indicates a lambda dependency like
    `Depends(lambda r: ...)` that FastAPI couldn't resolve as a Request
    injection. This causes 422 Unprocessable Entity on every call to the
    affected route.
    """
    schema = app.openapi()
    spurious: list[str] = []
    for path, methods in schema.get("paths", {}).items():
        for method, info in methods.items():
            for param in info.get("parameters", []):
                if param.get("name") == "r" and param.get("in") == "query":
                    spurious.append(f"{method.upper()} {path}")
    assert spurious == [], (
        f"Routes with spurious 'r' query param (lambda 422 bug): {spurious}. "
        f"Replace `Depends(lambda r: ...)` with a named function that has "
        f"`request: Request` as a typed parameter."
    )


def test_personal_routes_resolve_without_422(app) -> None:
    """Personal routes must not return 422 (the lambda bug symptom).

    This is the behavioral test — actually call a personal route through
    FastAPI's test client and assert it doesn't 422.
    """
    from starlette.testclient import TestClient

    client = TestClient(app)
    # With auth disabled (dev mode), /api/personal/briefing should return
    # something other than 422. It might 500 (no state initialized) or
    # return data — but 422 means the lambda bug is present.
    response = client.get("/api/personal/briefing")
    assert response.status_code != 422, (
        f"Lambda 422 bug: /api/personal/briefing returned 422. "
        f"Body: {response.text[:200]}"
    )
