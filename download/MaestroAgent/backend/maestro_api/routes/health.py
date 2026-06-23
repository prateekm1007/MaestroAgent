"""Health & diagnostics endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict:
    state = request.app.state.maestro
    return {
        "status": "ok",
        "version": "0.1.0",
        "providers": state.llm.available_providers() if state.llm else [],
        "verifiers": state.verifiers.names() if state.verifiers else [],
        "plugins": state.plugins.list() if state.plugins else [],
    }


@router.get("/doctor")
async def doctor(request: Request) -> dict:
    """Deeper diagnostics — provider connectivity, DB writability, etc."""
    state = request.app.state.maestro
    results: dict[str, bool] = {}
    # Check each provider.
    if state.llm:
        for name, prov in state.llm.providers.items():
            try:
                results[name] = await prov.health()
            except Exception:
                results[name] = False
    # Check DB.
    try:
        await state.checkpoints.audit("__doctor__", "ping", {"ts": "now"})
        results["db"] = True
    except Exception:
        results["db"] = False
    return results
