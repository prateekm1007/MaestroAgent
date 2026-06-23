"""FastAPI app factory and route registration.

Browser-first: in self-host mode, this server also serves the built
PWA bundle from `frontend/dist/`. In dev mode, Vite runs separately
on port 1420 and proxies /api and /ws here.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from maestro_api.routes import runs, agents, loops, memory, templates, costs, health, live
from maestro_api.websocket import register_ws_routes
from maestro_api.state import AppState

logger = logging.getLogger(__name__)


def create_app(
    db_path: str | Path = "maestro.db",
    chroma_path: str | Path = ".maestro/chroma",
    graph_path: str | Path = ".maestro/graph.json",
    frontend_dist: str | Path | None = None,
) -> FastAPI:
    """Build the FastAPI app with all routes wired up.

    Args:
        db_path: SQLite database path.
        chroma_path: Chroma vector store path.
        graph_path: NetworkX graph persistence path.
        frontend_dist: Path to the built PWA bundle (frontend/dist).
            If set and exists, the server serves the PWA at / and the
            API at /api. If None, only the API is served (dev mode).
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
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
        description="The open-source, browser-first conductor for AI agents.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS — in dev, the Vite server (localhost:1420) calls this API
    # (localhost:8765). In self-host mode, the PWA is same-origin.
    # We allow all origins for ease of self-hosting; tighten in prod.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routes.
    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(runs.router, prefix="/api/runs", tags=["runs"])
    app.include_router(live.router, prefix="/api/runs", tags=["live"])
    app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
    app.include_router(loops.router, prefix="/api/loops", tags=["loops"])
    app.include_router(memory.router, prefix="/api/memory", tags=["memory"])
    app.include_router(templates.router, prefix="/api/templates", tags=["templates"])
    app.include_router(costs.router, prefix="/api/costs", tags=["costs"])

    # WebSocket for live event streaming.
    register_ws_routes(app)

    # Serve the PWA bundle if frontend_dist is set and exists.
    # This enables single-container self-hosting: one `docker run`
    # serves both the API and the installable PWA.
    dist_path = (
        Path(frontend_dist)
        if frontend_dist
        else Path(os.environ.get("MAESTRO_FRONTEND_DIST", "frontend/dist"))
    )
    if dist_path.exists() and (dist_path / "index.html").exists():
        # Mount static assets (JS, CSS, icons).
        app.mount("/assets", StaticFiles(directory=dist_path / "assets"), name="assets")

        # Serve other static files at root (manifest, icons, favicon).
        # We mount the whole dist dir but catch index.html separately
        # so SPA routing works (all unknown paths → index.html).
        static_files_dir = dist_path

        # Service worker + manifest + icons at root.
        for static_file in ["manifest.webmanifest", "sw.js", "registerSW.js", "favicon.ico"]:
            f = dist_path / static_file
            if f.exists():
                app.mount(f"/{static_file}", StaticFiles(file=f), name=f"static-{static_file}")

        # Icons directory.
        icons_dir = dist_path / "icons"
        if icons_dir.exists():
            app.mount("/icons", StaticFiles(directory=icons_dir), name="icons")

        # SPA fallback: any non-API path serves index.html.
        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str):
            # Don't intercept API or WS paths.
            if full_path.startswith("api/") or full_path.startswith("ws/"):
                return {"detail": "Not Found"}
            # Serve the file if it exists in dist, else index.html (SPA route).
            candidate = static_files_dir / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(static_files_dir / "index.html")

        logger.info("Serving PWA bundle from %s", dist_path)
    else:
        logger.info(
            "Frontend dist not found at %s — API-only mode. "
            "Run `cd frontend && pnpm build` to enable self-host mode.",
            dist_path,
        )

    return app
