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
from typing import Callable, TypeVar

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
