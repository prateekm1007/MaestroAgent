# Release Notes — v1.0.0

**MaestroAgent v1.0** — the first production-ready release. Browser-first PWA, self-hostable, open-source, with security hardening and a self-improving meta-agent.

## Highlights

### Security & Production Hardening
- **API key authentication** — opt-in via `MAESTRO_AUTH_ENABLED=true`. Auto-generates a key on first startup, saves it to the OS keyring + `/data/api_key.txt`. All `/api/*` and `/ws/*` endpoints require `Authorization: Bearer <key>`.
- **OAuth stub** — `MAESTRO_OAUTH_PROVIDER=supabase|auth0` configures the provider (full integration in v1.1).
- **Rate limiting** — per-IP token bucket (default 100 rpm, configurable via `MAESTRO_RATE_LIMIT_RPM`).
- **Input sanitization** — strips control characters + truncates long inputs to prevent prompt injection via template args.
- **Audit logging** — every authenticated API call is written to the tamper-evident audit log.
- **CORS tightening** — when auth is enabled, CORS defaults to explicit origins instead of `*`.
- **Docker hardening** — non-root user, `no-new-privileges`, `cap_drop: ALL`, resource limits (2 CPU / 2GB RAM), tmpfs for `/tmp`.

### Advanced Autonomy
- **Self-improving meta-agent** (`maestro_meta`) — analyzes recent runs (cost data + audit log) and proposes concrete optimizations: adjust LLM hints, tighten loop budgets, promote memory entries, quarantine failing agents. Exposed via `/api/meta/recommendations` and the Metrics panel.
- **Hybrid CrewAI ↔ LangGraph** (`maestro_hybrid`) — `crew_to_graph()` compiles a CrewAI Crew into a MaestroAgent stateful graph, with each agent individually checkpointed and streamable.

### PWA & UX
- **LoginModal** — shown automatically when auth is enabled and the user isn't authenticated.
- **Project export/import** — download a full run (graph + state + cost + audit) as portable JSON via the Metrics panel or `/api/projects/{id}/export`.
- **Meta-agent recommendations panel** in Metrics with severity badges, expected savings, and confidence scores.
- **WebSocket auth** — WS connections pass the API key as a `?token=` query param (browsers can't set custom headers on WS).

### Backend
- **`/api/auth/*`** routes — login, status, key management (create/list/revoke).
- **`/api/meta/recommendations`** — run the meta-agent analysis.
- **`/api/projects/{id}/export`** + `/import` + `/graph` — portable project bundles.
- **`/api/models`** — lists real models from each provider.
- **`/api/doctor`** — checks providers, DB, and Chroma.
- **Ollama auto-detect** — `LLMRouter.auto_detect()` probes local providers at startup and picks a default model.

### Self-Hosting
- **`update.sh`** — one-click zero-downtime updates (git pull → rebuild → rolling restart → health check).
- **`test_e2e.sh`** — 11-step smoke test.
- **Caddy + nginx examples** — production HTTPS with security headers + WebSocket support.
- **`.env.example`** — documents all security + LLM env vars.

### Release Assets
- **GitHub CI** (`.github/workflows/ci.yml`) — Python 3.11/3.12 matrix, frontend build, Docker image build + smoke test.
- **Issue templates** — bug report + feature request.
- **`CONTRIBUTING.md`** — full contributor guide.

## New environment variables

| Variable | Default | Purpose |
|---|---|---|
| `MAESTRO_AUTH_ENABLED` | `false` | Enable API key auth |
| `MAESTRO_API_KEY` | (auto) | Explicit API key (overrides auto-gen) |
| `MAESTRO_RATE_LIMIT_RPM` | `100` | Per-IP requests per minute |
| `MAESTRO_CORS_ORIGINS` | `*` | Comma-separated allowed origins |
| `MAESTRO_OAUTH_PROVIDER` | (none) | `supabase` or `auth0` (v1.1) |
| `MAESTRO_OAUTH_CLIENT_ID` | — | OAuth client ID |
| `MAESTRO_OAUTH_CLIENT_SECRET` | — | OAuth client secret |
| `MAESTRO_OAUTH_REDIRECT_URL` | — | OAuth callback URL |

## New API endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/auth/status` | Check if auth is enabled |
| POST | `/api/auth/login` | Verify API key / OAuth code |
| GET | `/api/auth/keys` | List API keys (metadata) |
| POST | `/api/auth/keys` | Generate a new API key |
| POST | `/api/auth/keys/revoke` | Revoke an API key |
| GET | `/api/models` | List models per provider |
| GET | `/api/meta/recommendations` | Meta-agent optimization analysis |
| GET | `/api/projects/{id}/export` | Export full run as JSON |
| POST | `/api/projects/import` | Import a project (read-only in v1.0) |
| GET | `/api/projects/{id}/graph` | Export graph structure |

## Breaking changes

- The `version` field in `/api/health` is now `1.0.0`.
- WebSocket connections require `?token=<key>` when auth is enabled.
- CORS is no longer `*` when `MAESTRO_AUTH_ENABLED=true` (must set `MAESTRO_CORS_ORIGINS`).

## Migration from v0.1

1. `git pull && ./update.sh`
2. (Optional) enable auth: `echo "MAESTRO_AUTH_ENABLED=true" >> .env && ./update.sh`
3. Your existing runs, memory, and templates are preserved (SQLite + Chroma volumes persist).

## What's next (v1.1)

- OAuth full integration (Supabase + Auth0 token verification)
- Multi-user collaboration (shared runs, RBAC)
- Plugin marketplace (signed plugins, sandboxed trials)
- Background sync + push notifications (PWA)
- Mobile-responsive polish + touch support
- Self-improving meta-agent with `--self-improve` flag (applies recommendations behind review)
