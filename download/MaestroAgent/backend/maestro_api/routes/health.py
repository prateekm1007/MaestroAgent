"""Health & diagnostics endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from maestro_api.security.policy import set_router_policy, auth_policy, AuthPolicy
from maestro_auth.permissions import is_auth_enabled, require_user

router = APIRouter()


def _require_user_if_auth_enabled(request: Request) -> None:
    if is_auth_enabled():
        require_user(request)


@router.get("/health")
@auth_policy(AuthPolicy.PUBLIC)
async def health(request: Request) -> dict:
    state = request.app.state.maestro
    return {
        "status": "ok",
        "version": "0.1.0",
        "providers": state.llm.available_providers() if state.llm else [],
        "default_provider": state.llm.default_provider if state.llm else None,
        "default_model": state.llm.default_model if state.llm else None,
        "verifiers": state.verifiers.names() if state.verifiers else [],
        "plugins": state.plugins.list() if state.plugins else [],
    }


@router.get("/doctor", dependencies=[Depends(_require_user_if_auth_enabled)])
@auth_policy(AuthPolicy.USER)
async def doctor(request: Request) -> dict:
    """Deeper diagnostics — provider connectivity, DB writability, etc."""
    state = request.app.state.maestro
    results: dict[str, bool] = {}
    # Check each provider via the router's health_check_all.
    if state.llm:
        try:
            results.update(await state.llm.health_check_all())
        except Exception as exc:
            results["llm_router"] = False
    # Check DB.
    try:
        await state.checkpoints.audit("__doctor__", "ping", {"ts": "now"})
        results["db"] = True
    except Exception:
        results["db"] = False
    # Check Chroma (vector memory).
    try:
        if state.memory and state.memory.semantic:
            # A no-op add+query to verify the vector store is alive.
            await state.memory.semantic.add("__doctor__", None, "doctor", "ping", {})
            results["chroma"] = True
        else:
            results["chroma"] = False
    except Exception:
        results["chroma"] = False
    return results


@router.get("/models", dependencies=[Depends(_require_user_if_auth_enabled)])
@auth_policy(AuthPolicy.USER)
async def list_models(request: Request) -> dict:
    """List available models per provider.

    Used by the StartRunModal to populate the model picker with real
    models from the user's Ollama / LM Studio / cloud providers.
    """
    state = request.app.state.maestro
    if not state.llm:
        return {"models": {}}
    models = await state.llm.list_all_models()
    return {
        "models": models,
        "default_provider": state.llm.default_provider,
        "default_model": state.llm.default_model,
    }

# Only /health is PUBLIC; /doctor and /models are USER (per-route deps above).
# Don't stamp the router with PUBLIC — that would override the per-route deps.

