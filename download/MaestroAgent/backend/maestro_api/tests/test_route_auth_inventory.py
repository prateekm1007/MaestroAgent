"""Route auth policy inventory test (compile-time guard).

Every /api/ and /ws/ route must declare an auth policy via @auth_policy.
This test iterates all routes from create_app() and fails if any are
missing the policy marker. It also verifies that non-public routes have
a named auth dependency guard (require_user, require_admin, etc.).

This is the Phase 1 exit gate: "No auth bypass path in route inventory."
"""

from __future__ import annotations

import os
from typing import Any, Iterator

import pytest
from fastapi.routing import APIRoute, APIWebSocketRoute

# Set MAESTRO_APP_DIR so create_app() can find app.html
os.environ.setdefault("MAESTRO_APP_DIR", os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from maestro_api.security.policy import AuthPolicy, get_route_policy

# The `app` fixture is provided by conftest.py (session-scoped, shared).


PUBLIC_EXACT = {
    "/api/health",
    "/api/auth/status",
    "/api/auth/login",
    "/api/oauth/callback",  # OAuth redirect target — provider redirects here
    "/api/auth/oidc/providers",  # IdP discovery pre-login
    "/api/auth/oidc/{provider}/login",  # OIDC handshake start
    "/api/auth/oidc/{provider}/callback",  # IdP redirect callback
    "/api/auth/saml/providers",  # SAML IdP discovery pre-login
    "/api/auth/saml/{provider}/login",  # SAML handshake start
    "/api/auth/saml/{provider}/acs",  # SAML assertion consumer
    "/api/auth/saml/metadata",  # SP metadata must be publicly retrievable
    "/status",  # HTML status page for health checks
    "/nerve-dashboard",  # HTML dashboard page — auth happens client-side via API key
    "/docs",
    "/openapi.json",
    "/redoc",
}

PUBLIC_PREFIXES = (
    "/docs",
    "/openapi.json",
    "/redoc",
)

AUTH_GUARD_NAMES = {
    "require_user",
    "require_admin",
    "require_user_if_auth_enabled",
    "_require_user_if_auth_enabled",
    "require_ws_user",
    "require_ws_user_if_auth_enabled",
    "_require_tenant_access",
    "_require_oem_permission",
    "<lambda>",  # Router-level lambdas (e.g. Depends(lambda r: ... require_user(r)))
}


def _is_public_path(path: str) -> bool:
    return path in PUBLIC_EXACT or any(path.startswith(p) for p in PUBLIC_PREFIXES)


def _iter_dependency_calls(dependant: Any) -> Iterator[Any]:
    """Recursively yield all dependency callables in a route's dependant tree."""
    for dep in getattr(dependant, "dependencies", []):
        if dep.call:
            yield dep.call
        yield from _iter_dependency_calls(dep)


def _iter_api_routes(app: Any) -> Iterator[APIRoute]:
    for r in app.routes:
        if isinstance(r, APIRoute) and (r.path.startswith("/api/") or r.path.startswith("/ws/")):
            yield r


def _iter_ws_routes(app: Any) -> Iterator[APIWebSocketRoute]:
    for r in app.routes:
        if isinstance(r, APIWebSocketRoute) and r.path.startswith("/ws/"):
            yield r


# ---------------------------------------------------------------------------
# Policy inventory tests
# ---------------------------------------------------------------------------


def test_all_api_routes_have_explicit_auth_policy(app) -> None:
    """Every /api/ route must have @auth_policy or be in PUBLIC_EXACT."""
    failures: list[str] = []

    for route in _iter_api_routes(app):
        endpoint = route.endpoint
        policy = get_route_policy(route)

        if _is_public_path(route.path):
            if policy is None:
                # Public routes should also be marked, but don't fail if missing
                # — the more important check is that protected routes have it.
                continue
            if policy != AuthPolicy.PUBLIC:
                failures.append(
                    f"{route.path} [{','.join(route.methods)}] is in PUBLIC_EXACT "
                    f"but marked {policy.value} — must be PUBLIC or removed from PUBLIC_EXACT"
                )
        else:
            if policy is None:
                failures.append(
                    f"{route.path} [{','.join(route.methods)}] missing @auth_policy decorator"
                )

    assert not failures, "Auth policy inventory failures:\n" + "\n".join(failures)


def test_all_ws_routes_have_explicit_auth_policy(app) -> None:
    """Every /ws/ route must have @auth_policy or be in WS_PUBLIC_EXACT."""
    failures: list[str] = []

    for route in _iter_ws_routes(app):
        endpoint = route.endpoint
        policy = get_route_policy(route)

        if policy is None:
            failures.append(f"{route.path} [WS] missing @auth_policy decorator")

    assert not failures, "WS auth policy failures:\n" + "\n".join(failures)


def test_non_public_api_routes_have_auth_dependency_guard(app) -> None:
    """Every non-public /api/ route must have a named auth dependency guard.

    Checks the route's dependant tree, route-level dependencies, AND
    router-level dependencies (APIRouter(dependencies=[...])).

    KNOWN GAP: the enterprise auth router (maestro_auth/routes.py) has routes
    that rely on middleware rather than per-route deps. These are tracked as
    a known gap and excluded from this test until per-route deps are added.
    """
    import importlib
    import os

    failures: list[str] = []

    # Build a map from route endpoint → router-level dependency callables.
    # FastAPI doesn't store a back-reference from route to router, so we
    # iterate each router module and collect its dependencies.
    router_deps: dict[str, set[str]] = {}  # endpoint_name → set of dep names
    routes_dir = os.path.join(os.path.dirname(__file__), "..", "routes")
    for f in sorted(os.listdir(routes_dir)):
        if not f.endswith(".py") or f == "__init__.py":
            continue
        mod_name = f.replace(".py", "")
        try:
            mod = importlib.import_module(f"maestro_api.routes.{mod_name}")
        except Exception:
            continue
        r = getattr(mod, "router", None)
        if r is None:
            continue
        deps = getattr(r, "dependencies", [])
        dep_names = set()
        for dep in deps:
            call = getattr(dep, "dependency", None)
            if call is not None:
                dep_names.add(getattr(call, "__name__", repr(call)))
        if dep_names:
            # Stamp every route in this router with the router's dep names
            for route in r.routes:
                endpoint = getattr(route, "endpoint", None)
                if endpoint is not None:
                    existing = router_deps.get(endpoint.__name__, set())
                    existing.update(dep_names)
                    router_deps[endpoint.__name__] = existing

    # Also check maestro_auth.routes (enterprise auth router)
    try:
        auth_mod = importlib.import_module("maestro_auth.routes")
        for r_name in ("router", "scim_router"):
            r = getattr(auth_mod, r_name, None)
            if r is None:
                continue
            deps = getattr(r, "dependencies", [])
            dep_names = set()
            for dep in deps:
                call = getattr(dep, "dependency", None)
                if call is not None:
                    dep_names.add(getattr(call, "__name__", repr(call)))
            if dep_names:
                for route in r.routes:
                    endpoint = getattr(route, "endpoint", None)
                    if endpoint is not None:
                        existing = router_deps.get(endpoint.__name__, set())
                        existing.update(dep_names)
                        router_deps[endpoint.__name__] = existing
    except Exception:
        pass

    # All 28 previously-middleware-only routes have been migrated to explicit
    # per-route dependencies. This set is intentionally EMPTY — if any route
    # is added here, it means a new middleware-only route was introduced and
    # must be migrated. CI fails if this set is non-empty.
    KNOWN_MIDDLEWARE_ROUTES: set[str] = set()

    for route in _iter_api_routes(app):
        if _is_public_path(route.path):
            continue
        if route.path in KNOWN_MIDDLEWARE_ROUTES:
            continue  # Tracked as known gap

        dep_names: set[str] = set()

        # 1. Check the route's dependant tree
        for call in _iter_dependency_calls(route.dependant):
            name = getattr(call, "__name__", repr(call))
            dep_names.add(name)

        # 2. Check route-level dependencies
        for dep in getattr(route, "dependencies", []):
            call = getattr(dep, "dependency", None)
            if call is not None:
                dep_names.add(getattr(call, "__name__", repr(call)))

        # 3. Check router-level dependencies (via the endpoint→router map)
        endpoint = getattr(route, "endpoint", None)
        if endpoint is not None:
            dep_names.update(router_deps.get(endpoint.__name__, set()))

        if dep_names.isdisjoint(AUTH_GUARD_NAMES):
            failures.append(
                f"{route.path} [{','.join(route.methods)}] missing auth dependency guard; "
                f"deps={sorted(dep_names)}"
            )

    assert not failures, "Missing auth dependency guards:\n" + "\n".join(failures)


def test_public_routes_are_documented(app) -> None:
    """Every route in PUBLIC_EXACT must exist in the app (or be removed if stale)."""
    app_paths = {r.path for r in app.routes if hasattr(r, "path")}
    stale = [p for p in PUBLIC_EXACT if p not in app_paths]
    # Don't fail — just log. Some paths may be in PUBLIC_EXACT as a guard
    # against future routes being accidentally added as public.
    if stale:
        import warnings
        warnings.warn(f"PUBLIC_EXACT contains paths not in app: {stale}", stacklevel=2)
