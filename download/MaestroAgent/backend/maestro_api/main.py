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

from maestro_api.routes import runs, agents, loops, memory, templates, costs, health, live, auth, meta, projects, status, oem, imports
from maestro_auth.routes import router as enterprise_auth_router, scim_router as scim_router_v2
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
        # Initialize the OEM from real signal data (idempotent, ~100ms).
        from maestro_api.oem_state import oem_state, import_state
        oem_state.initialize()
        # Initialize the import pipeline (Checkpoints, OAuth, Connections).
        import_state.ensure_initialized()
        # Initialize enterprise auth (users, sessions, RBAC, OIDC, SAML, SCIM).
        from maestro_auth.models import AuthStore
        from maestro_auth.permissions import init_auth
        import os as _os
        _auth_db_dir = Path(_os.environ.get("DATABASE_URL", "file:maestro.db").replace("file:", "")).parent
        _auth_db_dir.mkdir(parents=True, exist_ok=True)
        auth_db = _os.environ.get("MAESTRO_AUTH_DB", str(_auth_db_dir / "auth.db"))
        _auth_store = AuthStore(auth_db)
        init_auth(_auth_store)
        # Seed a default admin user if no users exist (dev convenience).
        if not _auth_store.list_users(limit=1):
            admin = _auth_store.create_user(
                email="admin@maestro.local",
                display_name="Default Admin",
                password=_os.environ.get("MAESTRO_ADMIN_PASSWORD", "changeme-now"),
                is_admin=True,
            )
            _auth_store.assign_role(admin["id"], "admin")
            logger.info("Seeded default admin user (admin@maestro.local) — change the password!")
        # Resume any incomplete jobs from before the restart.
        try:
            assert import_state.engine is not None
            resumed = await import_state.engine.resume_incomplete_jobs()
            if resumed:
                logger.info("Resumed %d incomplete import job(s) after restart", len(resumed))
        except Exception as e:
            logger.warning("Failed to resume incomplete jobs: %s", e)
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
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"] if cors_origins != ["*"] else ["*"],
    )

    # Security hardening middleware (from the security audit fixes).
    # Execution order (last added = outermost = runs first):
    #   SecurityHeaders → CSRF → EnhancedRateLimit → TenantIsolation → CORS → route
    from maestro_auth.security import (
        SecurityHeadersMiddleware,
        CSRFMiddleware,
        EnhancedRateLimitMiddleware,
        TenantIsolationMiddleware,
        TrustedProxyConfig,
    )
    trusted_proxy_config = TrustedProxyConfig()
    app.add_middleware(TenantIsolationMiddleware)
    app.add_middleware(EnhancedRateLimitMiddleware,
                       global_rpm=auth_config.rate_limit_rpm,
                       trusted_config=trusted_proxy_config)
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    logger.info("Security middleware enabled: CSP, CSRF, rate-limiting, tenant isolation, trusted-proxy validation")

    # Legacy audit middleware (best-effort logging).
    if auth_config.enabled:
        from maestro_auth.middleware import AuditMiddleware, RateLimitMiddleware, AuthMiddleware
        app.add_middleware(AuditMiddleware, store=None)  # store set in _init_auth
        logger.info("Auth enabled: API key required, rate limit=%d rpm", auth_config.rate_limit_rpm)
    else:
        # Even with auth off, audit logging is useful.
        from maestro_auth.middleware import AuditMiddleware
        app.add_middleware(AuditMiddleware, store=None)
        logger.info("Auth disabled (local dev mode). Set MAESTRO_AUTH_ENABLED=true to enable.")

    # Register API routes.
    # Enterprise auth router registered FIRST so its /api/auth/login takes
    # precedence over the legacy auth.router (which is kept for backward
    # compatibility with API-key status endpoints).
    app.include_router(enterprise_auth_router, tags=["enterprise-auth", "oidc", "saml", "scim", "mfa", "rbac"])
    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(scim_router_v2, tags=["scim"])
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
    app.include_router(oem.router, prefix="/api/oem", tags=["oem"])
    app.include_router(imports.router, tags=["imports", "oauth"])
    # Status dashboard (HTML at /status — NOT part of /api).
    app.include_router(status.router, tags=["status"])

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
            # Don't intercept API, WS, or status paths.
            if full_path.startswith("api/") or full_path.startswith("ws/") or full_path == "status":
                return {"detail": "Not Found"}
            candidate = static_files_dir / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(static_files_dir / "index.html")

        logger.info("Serving PWA bundle from %s", dist_path)
    else:
        # Serve static assets (compiled CSS, JS) from the app directory.
        app_static_dir = Path(os.environ.get("MAESTRO_APP_DIR", ".")).resolve() / "static"
        if app_static_dir.exists():
            app.mount("/static", StaticFiles(directory=app_static_dir), name="static")
            logger.info("Serving static assets from %s", app_static_dir)

        # Serve app.html at root if it exists.
        app_html = Path(os.environ.get("MAESTRO_APP_DIR", ".")).resolve() / "app.html"
        if app_html.exists():
            @app.get("/")
            async def serve_app():
                return FileResponse(app_html)

            @app.get("/app.html")
            async def serve_app_html():
                return FileResponse(app_html)
        logger.info(
            "Frontend dist not found at %s — API-only mode. "
            "Run `cd frontend && pnpm build` to enable self-host mode.",
            dist_path,
        )

    # Serve the executive app (app.html) from the repo root if it exists.
    # This lets users visit http://localhost:8765/app.html to see the OEM-wired UI.
    app_html_path = Path(__file__).resolve().parent.parent.parent / "app.html"
    if app_html_path.exists():
        @app.get("/app.html")
        async def serve_app_html():
            return FileResponse(app_html_path, media_type="text/html")
        @app.get("/")
        async def serve_root():
            return FileResponse(app_html_path, media_type="text/html")
        logger.info("Serving executive app from %s", app_html_path)

    return app


async def _init_auth(app: FastAPI) -> None:
    """Initialize auth subsystem and inject middleware that needs the store.

    Note: The new enterprise auth system (maestro_auth.models + permissions + routes)
    is initialized separately in the lifespan and does NOT use middleware-based auth.
    This function only runs for the legacy API-key flow when MAESTRO_AUTH_ENABLED
    is NOT set (backward compatibility).
    """
    from maestro_auth.config import AuthConfig
    from maestro_auth.api_keys import SQLiteApiKeyStore, ensure_default_key
    from maestro_auth.oauth import make_provider

    state: AppState = app.state.maestro
    config = AuthConfig.from_env()
    state.auth_config = config

    if config.enabled:
        state.api_key_store = SQLiteApiKeyStore(db_path=state.db_path)
        state.oauth_provider = make_provider(config)
        key = await ensure_default_key(state.api_key_store, state.db_path)
        if key and not os.environ.get("MAESTRO_API_KEY"):
            logger.warning(
                "Generated API key (saved to keyring + %s/api_key.txt): %s...",
                Path(state.db_path).parent, key[:12],
            )
        # Note: We do NOT add AuthMiddleware here because it can't be added after
        # the app starts (TestClient constraint). The enterprise auth system uses
        # FastAPI dependencies (require_user, require_permission) instead of middleware.
        # The middleware was already added in create_app() above if config.enabled.
    else:
        state.api_key_store = None
        state.oauth_provider = None
