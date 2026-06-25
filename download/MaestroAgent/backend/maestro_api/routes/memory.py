"""Memory routes — recall, promote, list episodes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class RecallRequest(BaseModel):
    query: str
    run_id: str | None = None
    agent_id: str | None = None
    scope: str | None = None
    top_k: int = 5


@router.post("/recall")
async def recall(req: RecallRequest, request: Request) -> list[dict[str, Any]]:
    state: Any = request.app.state.maestro
    entries = await state.memory.recall(
        query=req.query,
        run_id=req.run_id,
        agent_id=req.agent_id,
        scope=req.scope,
        top_k=req.top_k,
    )
    return [e.__dict__ for e in entries]


@router.get("/episodes/{run_id}")
async def list_episodes(run_id: str, request: Request) -> list[dict[str, Any]]:
    state: Any = request.app.state.maestro
    if state.memory.long_term is None:
        return []
    return await state.memory.long_term.list_by_run(run_id)


class PromoteRequest(BaseModel):
    agent_id: str
    content: str | None = None
    summary: str | None = None
    run_id: str | None = None
    scope: str = "shared"
    tags: list[str] | None = None


@router.post("/promote")
async def promote(req: PromoteRequest, request: Request) -> dict[str, Any]:
    state: Any = request.app.state.maestro
    eid = await state.memory.promote(
        agent_id=req.agent_id,
        content=req.content,
        summary=req.summary,
        run_id=req.run_id,
        scope=req.scope,
        tags=req.tags,
    )
    return {"episode_id": eid}
