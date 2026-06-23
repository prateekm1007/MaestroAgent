"""FastAPI app factory and route registration."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from maestro_api.routes import runs, agents, loops, memory, templates, costs, health
from maestro_api.websocket import register_ws_routes
from maestro_api.state import AppState

logger = logging.getLogger(__name__)


def create_app(
    db_path: str | Path = "maestro.db",
    chroma_path: str | Path = ".maestro/chroma",
    graph_path: str | Path = ".maestro/graph.json",
) -> FastAPI:
    """Build the FastAPI app with all routes wired up."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Initialize shared state.
        app.state.maestro = AppState(
            db_path=str(db_path),
            chroma_path=str(chroma_path),
            graph_path=str(graph_path),
        )
        await app.state.maestro.start()
        try:
            yield
        finally:
            await app.state.maestro.stop()

    app = FastAPI(
        title="MaestroAgent",
        description="The ultimate conductor for AI agents. Local-first, model-agnostic.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS — the desktop app loads from tauri://, dev server from localhost.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes.
    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(runs.router, prefix="/api/runs", tags=["runs"])
    app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
    app.include_router(loops.router, prefix="/api/loops", tags=["loops"])
    app.include_router(memory.router, prefix="/api/memory", tags=["memory"])
    app.include_router(templates.router, prefix="/api/templates", tags=["templates"])
    app.include_router(costs.router, prefix="/api/costs", tags=["costs"])

    # WebSocket for live event streaming.
    register_ws_routes(app)

    return app
