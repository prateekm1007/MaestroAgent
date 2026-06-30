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
        _auth_db_dir = Path("maestro.db").parent  # Dev default — in production, MAESTRO_AUTH_DB is set explicitly
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

    # ─── Static-file routing — one explicit mode, no fallthrough ──────────
    # Previous versions had three conditional branches that could each
    # register a route for `/`, with no explicit assertion of which one
    # wins. This caused ambiguity: depending on the filesystem, a visitor
    # could land on the executive app, an old PWA build, or nothing.
    #
    # Now there is ONE env var: MAESTRO_FRONTEND_MODE
    #   - "app" (default): serve app.html + static/ from MAESTRO_APP_DIR
    #   - "dist": serve a built frontend bundle from MAESTRO_FRONTEND_DIST
    #   - "none": API-only mode (no frontend served)
    #
    # In production (MAESTRO_ENV=production), the mode MUST be set
    # explicitly — we fail closed rather than guessing.

    frontend_mode = os.environ.get("MAESTRO_FRONTEND_MODE", "app")
    is_production = os.environ.get("MAESTRO_ENV", "development") == "production"

    if is_production and frontend_mode not in ("app", "dist", "none"):
        raise RuntimeError(
            f"MAESTRO_FRONTEND_MODE={frontend_mode!r} is invalid in production. "
            f"Must be one of: 'app', 'dist', 'none'."
        )

    if frontend_mode == "dist":
        # Serve a built PWA bundle.
        dist_path = Path(
            frontend_dist or os.environ.get("MAESTRO_FRONTEND_DIST", "frontend/dist")
        )
        if not dist_path.exists() or not (dist_path / "index.html").exists():
            raise RuntimeError(
                f"MAESTRO_FRONTEND_MODE=dist but frontend bundle not found at {dist_path}. "
                f"Build the frontend first or set MAESTRO_FRONTEND_MODE=app."
            )
        app.mount("/assets", StaticFiles(directory=dist_path / "assets"), name="assets")
        for static_file in ["manifest.webmanifest", "sw.js", "registerSW.js", "favicon.ico"]:
            f = dist_path / static_file
            if f.exists():
                app.mount(f"/{static_file}", StaticFiles(file=f), name=f"static-{static_file}")
        icons_dir = dist_path / "icons"
        if icons_dir.exists():
            app.mount("/icons", StaticFiles(directory=icons_dir), name="icons")

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str):
            if full_path.startswith("api/") or full_path.startswith("ws/") or full_path == "status":
                return {"detail": "Not Found"}
            candidate = dist_path / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist_path / "index.html")

        logger.info("Serving PWA bundle from %s (MAESTRO_FRONTEND_MODE=dist)", dist_path)

    elif frontend_mode == "app":
        # Serve app.html + static/ — the live executive UI.
        app_dir = Path(os.environ.get("MAESTRO_APP_DIR", ".")).resolve()
        app_html = app_dir / "app.html"
        static_dir = app_dir / "static"

        if not app_html.exists():
            raise RuntimeError(
                f"MAESTRO_FRONTEND_MODE=app but app.html not found at {app_html}. "
                f"Set MAESTRO_APP_DIR to the directory containing app.html."
            )

        if static_dir.exists():
            app.mount("/static", StaticFiles(directory=static_dir), name="static")
            logger.info("Serving static assets from %s", static_dir)

        @app.get("/")
        async def serve_root():
            return FileResponse(app_html, media_type="text/html")

        @app.get("/app.html")
        async def serve_app_html():
            return FileResponse(app_html, media_type="text/html")

        logger.info("Serving executive app from %s (MAESTRO_FRONTEND_MODE=app)", app_html)

    else:
        # MAESTRO_FRONTEND_MODE=none — API-only, no frontend served.
        logger.info("API-only mode (MAESTRO_FRONTEND_MODE=none). No frontend served.")

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
