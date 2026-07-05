"""Explicit auth policy metadata for route-level authorization.

Every API and WebSocket route must declare its auth policy via the
``@auth_policy`` decorator. This creates a compile-time inventory that
``test_route_auth_inventory.py`` checks — if a new route is added without
a policy, CI fails.

Usage::

    from maestro_api.security.policy import auth_policy, AuthPolicy

    @router.get("/api/whatever")
    @auth_policy(AuthPolicy.USER)
    async def whatever():
        ...

The decorator sets ``fn.__auth_policy__`` — it does NOT enforce auth at
runtime (that's the job of FastAPI dependencies). The policy is metadata
for inventory tests; the actual enforcement is the named dependency
(``require_user``, ``require_admin``, etc.) on the route or router.

This separation is deliberate: the decorator documents intent, the
dependency enforces it, and the inventory test verifies both exist.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable)


class AuthPolicy(str, Enum):
    """Auth policy levels for route inventory.

    - PUBLIC:  No auth required (health checks, login, docs).
    - USER:    Any authenticated user.
    - ADMIN:   Admin role required.
    - SERVICE: Service-to-service auth (API key / internal token).
    """

    PUBLIC = "public"
    USER = "user"
    ADMIN = "admin"
    SERVICE = "service"


def auth_policy(policy: AuthPolicy) -> Callable[[F], F]:
    """Decorator that marks a route function with its auth policy.

    This is metadata only — it does NOT enforce auth at runtime.
    Use FastAPI ``Depends(require_user)`` / ``Depends(require_admin)``
    for actual enforcement.
    """

    def _decorator(fn: F) -> F:
        setattr(fn, "__auth_policy__", policy)
        return fn

    return _decorator


def get_auth_policy(fn: Callable) -> AuthPolicy | None:
    """Return the auth policy declared on a route function, or None."""
    return getattr(fn, "__auth_policy__", None)


def set_router_policy(router: Any, policy: AuthPolicy) -> Any:
    """Stamp a default auth policy on a router and all its existing routes.

    This is the router-level equivalent of ``@auth_policy``. It sets
    ``router.__auth_policy__`` and also stamps ``__auth_policy__`` on every
    route endpoint already registered on the router. New routes added after
    this call will NOT inherit the policy — call this after all routes are
    defined, OR use ``@auth_policy`` on individual routes.

    Usage::

        from maestro_api.security.policy import set_router_policy, AuthPolicy

        router = APIRouter(dependencies=[Depends(require_user)])
        # ... define routes ...
        set_router_policy(router, AuthPolicy.USER)

    This exists because some routers (oem: 160 routes) are impractical to
    decorate individually. The router-level policy is a default; individual
    ``@auth_policy`` decorators on specific routes override it.
    """
    setattr(router, "__auth_policy__", policy)
    # Also stamp each existing route's endpoint so get_auth_policy() finds it.
    for route in getattr(router, "routes", []):
        endpoint = getattr(route, "endpoint", None)
        if endpoint is not None and not hasattr(endpoint, "__auth_policy__"):
            setattr(endpoint, "__auth_policy__", policy)
    return router


def get_route_policy(route: Any) -> AuthPolicy | None:
    """Return the auth policy for a route, checking route-level then router-level.

    This is what the inventory test calls. It checks:
    1. The route endpoint's ``__auth_policy__`` (set by @auth_policy or set_router_policy)
    2. Falls back to the router's ``__auth_policy__`` (set by set_router_policy)
    """
    endpoint = getattr(route, "endpoint", None)
    if endpoint is not None:
        policy = getattr(endpoint, "__auth_policy__", None)
        if policy is not None:
            return policy
    # Check router-level policy
    router = getattr(route, "router", None) or getattr(route, "api_router", None)
    if router is not None:
        return getattr(router, "__auth_policy__", None)
    return None
