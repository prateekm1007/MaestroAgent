"""Auth routes — login, key management, status."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel

# Round 65 CTO Blocker 8: Admin endpoints (keys, revoke) require auth.
# /status and /login are public (needed to check auth state and authenticate).
from maestro_auth.permissions import require_user

router = APIRouter()


class LoginRequest(BaseModel):
    """Login with an API key (or OAuth code)."""
    api_key: str | None = None
    oauth_code: str | None = None


class LoginResponse(BaseModel):
    authenticated: bool
    method: str = ""
    user: dict[str, Any] | None = None


@router.get("/status")
async def auth_status(request: Request) -> dict[str, Any]:
    """Check if auth is enabled and the current request is authenticated."""
    state: Any = request.app.state.maestro
    config = state.auth_config
    user = getattr(request.state, "user", None) if hasattr(request, "state") else None
    return {
        "enabled": config.enabled,
        "oauth_provider": config.oauth_provider,
        "authenticated": user is not None,
        "user": user,
    }


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, request: Request) -> LoginResponse:
    """Verify an API key (or OAuth code) and return auth status.

    The browser stores the returned API key in localStorage and sends
    it as `Authorization: Bearer <key>` on subsequent requests.
    """
    state: Any = request.app.state.maestro
    config = state.auth_config

    if not config.enabled:
        return LoginResponse(authenticated=True, method="disabled", user={"name": "anonymous"})

    # API key auth.
    if req.api_key and state.api_key_store:
        ok, key_info = await state.api_key_store.verify(req.api_key)
        if ok:
            return LoginResponse(
                authenticated=True,
                method="api_key",
                user={"name": key_info.get("name", ""), "scopes": key_info.get("scopes", [])},
            )
        raise HTTPException(status_code=401, detail="Invalid API key")

    # OAuth auth (v1.1).
    if req.oauth_code and state.oauth_provider:
        result = await state.oauth_provider.exchange_code(req.oauth_code)
        if result:
            token, user = result
            return LoginResponse(
                authenticated=True,
                method="oauth",
                user={"name": user.name or user.email or user.id, "token": token},
            )
        raise HTTPException(status_code=401, detail="OAuth code exchange failed")

    raise HTTPException(status_code=400, detail="Provide api_key or oauth_code")


@router.get("/keys")
async def list_api_keys(request: Request, user: dict = Depends(require_user)) -> list[dict[str, Any]]:
    """List all API keys (metadata only — no plaintext). Requires auth."""
    state: Any = request.app.state.maestro
    if state.api_key_store is None:
        return []
    return await state.api_key_store.list_keys()


class CreateKeyRequest(BaseModel):
    name: str
    scopes: list[str] = ["*"]


@router.post("/keys")
async def create_api_key(req: CreateKeyRequest, request: Request, user: dict = Depends(require_user)) -> dict[str, Any]:
    """Generate a new API key. Returns the plaintext ONCE."""
    state: Any = request.app.state.maestro
    if state.api_key_store is None:
        raise HTTPException(status_code=503, detail="API key store not initialized")
    from maestro_auth import generate_api_key
    key = generate_api_key()
    # Sanitize name.
    name = (req.name or "unnamed")[:100]
    await state.api_key_store.create(key, name, req.scopes)
    return {"api_key": key, "name": name, "scopes": req.scopes, "warning": "Save this key — it won't be shown again."}


class RevokeKeyRequest(BaseModel):
    api_key: str


@router.post("/keys/revoke")
async def revoke_api_key(req: RevokeKeyRequest, request: Request, user: dict = Depends(require_user)) -> dict[str, Any]:
    """Revoke an API key."""
    state: Any = request.app.state.maestro
    if state.api_key_store is None:
        raise HTTPException(status_code=503, detail="API key store not initialized")
    ok = await state.api_key_store.revoke(req.api_key)
    return {"revoked": ok}
