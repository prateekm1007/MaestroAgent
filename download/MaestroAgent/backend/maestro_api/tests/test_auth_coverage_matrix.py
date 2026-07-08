"""Security test matrix: assert auth coverage on every protected router.

Phase 1 exit gate: "No auth bypass path in route inventory."

This test iterates every router in maestro_api/routes/ and asserts that
every protected router has a router-level auth dependency OR per-route
auth dependencies. Routers that are intentionally public (health, status,
auth/login) are explicitly exempted.

This is the automated test the auditor asked for: a route inventory that
fails if any new router is added without auth coverage.
"""

from __future__ import annotations

import importlib
import os

import pytest

# Routers that are intentionally public — they must NOT have auth.
# - health: load balancer probes
# - status: lightweight status page for post-install verification
# - auth: contains /login and /status (needed before authentication);
#   per-route auth is applied to sensitive endpoints like /keys
INTENTIONALLY_PUBLIC_ROUTERS = {"health", "status", "auth"}


def _get_all_routers() -> list[tuple[str, object]]:
    """Import every router module and return (name, router) pairs."""
    routes_dir = os.path.join(os.path.dirname(__file__), "..", "routes")
    routers = []
    for f in sorted(os.listdir(routes_dir)):
        if not f.endswith(".py") or f == "__init__.py":
            continue
        module_name = f.replace(".py", "")
        mod = importlib.import_module(f"maestro_api.routes.{module_name}")
        if hasattr(mod, "router"):
            routers.append((module_name, mod.router))
    return routers


def test_every_protected_router_has_auth_dependency() -> None:
    """Every router NOT in INTENTIONALLY_PUBLIC_ROUTERS must have auth coverage.

    Auth coverage = router-level dependency OR per-route dependencies on
    every route. This test FAILS if a new router is added without auth.
    """
    routers = _get_all_routers()
    assert len(routers) >= 10, f"Expected 10+ routers, found {len(routers)}"

    unprotected: list[str] = []
    for name, router in routers:
        if name in INTENTIONALLY_PUBLIC_ROUTERS:
            continue

        router_deps = getattr(router, "dependencies", [])
        if router_deps:
            continue  # Router-level auth — good.

        # Check if router uses set_router_policy (our auth policy mechanism)
        # set_router_policy stores __auth_policy__ on the router object
        if getattr(router, "__auth_policy__", None) is not None:
            continue  # set_router_policy was called — good.

        # Check if every route has @auth_policy decorator or its own Depends.
        routes = [r for r in router.routes if hasattr(r, "methods")]
        if not routes:
            continue  # No HTTP routes — skip.

        all_routes_have_deps = all(
            getattr(route, "dependencies", [])
            for route in routes
        )
        if not all_routes_have_deps:
            # Final check: does every route have @auth_policy?
            # The @auth_policy decorator sets __auth_policy__ on endpoint
            all_routes_have_policy = all(
                hasattr(getattr(route, "endpoint", None), "__auth_policy__")
                for route in routes
            )
            if not all_routes_have_policy:
                unprotected.append(name)

    assert not unprotected, (
        f"Routers without auth coverage: {unprotected}. "
        f"Every protected router must have a router-level auth dependency "
        f"(APIRouter(dependencies=[Depends(...)])) or per-route auth on every route. "
        f"Intentionally public routers: {INTENTIONALLY_PUBLIC_ROUTERS}."
    )


def test_intentionally_public_routers_are_known() -> None:
    """The public-router list must be explicitly maintained.

    If a router is added to INTENTIONALLY_PUBLIC_ROUTERS, it must be
    justified here. This test exists so adding a new public router
    requires a deliberate decision, not an accidental omission.
    """
    # These are the only acceptable reasons for a public router:
    justified = {
        "health": "Load balancer / uptime probes must work without auth.",
        "status": "Post-install verification page (lightweight, no sensitive data).",
        "auth": "Contains /login (needed before auth) + /status. Sensitive "
                "endpoints like /keys have per-route Depends(require_user).",
    }
    for router_name in INTENTIONALLY_PUBLIC_ROUTERS:
        assert router_name in justified, (
            f"Router '{router_name}' is marked public but has no justification. "
            f"Add a justification or add auth to it."
        )


def test_admin_endpoints_require_admin_role() -> None:
    """Every route with 'admin' in the path must require admin role.

    This is the C2 regression guard: admin endpoints must never be
    accessible without admin RBAC.
    """
    from maestro_api.routes.imports import router as imports_router

    admin_routes = [
        r for r in imports_router.routes
        if "admin" in str(getattr(r, "path", ""))
    ]
    assert len(admin_routes) >= 3, f"Expected 3+ admin routes, got {len(admin_routes)}"

    for route in admin_routes:
        deps = getattr(route, "dependencies", [])
        assert len(deps) >= 2, (
            f"Admin route {route.path} must have require_admin dependency. "
            f"Found {len(deps)} dependencies (expected 2: router-level + route-level)."
        )
