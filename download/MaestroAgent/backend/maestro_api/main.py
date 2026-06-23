"""FastAPI app factory and route registration.

Browser-first: in self-host mode, this server also serves the built
PWA bundle from `frontend/dist/`. In dev mode, Vite runs separately
on port 1420 and proxies /api and /ws here.

v1.0 adds production security: API key auth, rate limiting, audit
logging, and tighter CORS. All gated behind `MAESTRO_AUTH_ENABLED=true`
so local dev stays zero-config.
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

from maestro_api.routes import runs, agents, loops, memory, templates, costs, health, live, auth, meta, projects
from maestro_api.websocket import register_ws_routes
from maestro_api.state import AppState

logger = logging.getLogger(__name__)


def create_app(
    db_path: str | Path = "maestro.db",
    chroma_path: str | Path = ".maestro/chroma",
    graph_path: str | Path = ".maestro/graph.json",
    frontend_dist: str | Path | None = None,
) -> FastAPI:
    """Build the FastAPI app with all routes + security middleware wired up."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.maestro = AppState(
            db_path=str(db_path),
            chroma_path=str(chroma_path),
            graph_path=str(graph_path),
        )
        await app.state.maestro.start()
        # Initialize auth (after AppState so we can reuse its DB).
        await _init_auth(app)
        try:
            yield
        finally:
            await app.state.maestro.stop()

    app = FastAPI(
        title="MaestroAgent",
        description="The open-source, browser-first conductor for AI agents.",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS — tightened when auth is enabled.
    from maestro_auth.config import AuthConfig
    auth_config = AuthConfig.from_env()
    cors_origins = auth_config.cors_origins or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=cors_origins != ["*"],
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"] if cors_origins != ["*"] else ["*"],
        allow_headers=["Authorization", "Content-Type"] if cors_origins != ["*"] else ["*"],
    )

    # Security middleware (added in reverse execution order).
    # Execution order: Auth → RateLimit → Audit → CORS → route.
    if auth_config.enabled:
        from maestro_auth.middleware import AuditMiddleware, RateLimitMiddleware, AuthMiddleware
        app.add_middleware(AuditMiddleware, store=None)  # store set in _init_auth
        app.add_middleware(RateLimitMiddleware, config=auth_config)
        # AuthMiddleware added in _init_auth (needs key_store).
        logger.info("Auth enabled: API key required, rate limit=%d rpm", auth_config.rate_limit_rpm)
    else:
        # Even with auth off, audit logging is useful.
        from maestro_auth.middleware import AuditMiddleware
        app.add_middleware(AuditMiddleware, store=None)
        logger.info("Auth disabled (local dev mode). Set MAESTRO_AUTH_ENABLED=true to enable.")

    # Register API routes.
    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(runs.router, prefix="/api/runs", tags=["runs"])
    app.include_router(live.router, prefix="/api/runs", tags=["live"])
    app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
    app.include_router(loops.router, prefix="/api/loops", tags=["loops"])
    app.include_router(memory.router, prefix="/api/memory", tags=["memory"])
    app.include_router(templates.router, prefix="/api/templates", tags=["templates"])
    app.include_router(costs.router, prefix="/api/costs", tags=["costs"])
    app.include_router(meta.router, prefix="/api/meta", tags=["meta"])
    app.include_router(projects.router, prefix="/api/projects", tags=["projects"])

    # WebSocket for live event streaming.
    register_ws_routes(app)

    # Serve the PWA bundle if frontend_dist is set and exists.
    dist_path = (
        Path(frontend_dist)
        if frontend_dist
        else Path(os.environ.get("MAESTRO_FRONTEND_DIST", "frontend/dist"))
    )
    if dist_path.exists() and (dist_path / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=dist_path / "assets"), name="assets")
        static_files_dir = dist_path
        for static_file in ["manifest.webmanifest", "sw.js", "registerSW.js", "favicon.ico"]:
            f = dist_path / static_file
            if f.exists():
                app.mount(f"/{static_file}", StaticFiles(file=f), name=f"static-{static_file}")
        icons_dir = dist_path / "icons"
        if icons_dir.exists():
            app.mount("/icons", StaticFiles(directory=icons_dir), name="icons")

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str):
            if full_path.startswith("api/") or full_path.startswith("ws/"):
                return {"detail": "Not Found"}
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


async def _init_auth(app: FastAPI) -> None:
    """Initialize auth subsystem and inject middleware that needs the store."""
    from maestro_auth.config import AuthConfig
    from maestro_auth.api_keys import SQLiteApiKeyStore, ensure_default_key
    from maestro_auth.oauth import make_provider
    from maestro_auth.middleware import AuthMiddleware

    state: AppState = app.state.maestro
    config = AuthConfig.from_env()
    state.auth_config = config

    if config.enabled:
        state.api_key_store = SQLiteApiKeyStore(db_path=state.db_path)
        state.oauth_provider = make_provider(config)
        # Ensure a default key exists (auto-generate if none configured).
        key = await ensure_default_key(state.api_key_store, state.db_path)
        if key and not os.environ.get("MAESTRO_API_KEY"):
            logger.warning(
                "Generated API key (saved to keyring + %s/api_key.txt): %s...",
                Path(state.db_path).parent, key[:12],
            )
        # Wire the key_store + oauth_provider into the AuthMiddleware.
        # We use the app's user_middleware list to find the AuthMiddleware
        # we haven't added yet (it needs the store), then add it.
        app.add_middleware(
            AuthMiddleware,
            config=config,
            key_store=state.api_key_store,
            oauth_provider=state.oauth_provider,
        )
    else:
        state.api_key_store = None
        state.oauth_provider = None
