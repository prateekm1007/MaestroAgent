# Architecture Report — Maestro v1.0

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Browser (CEO)                            │
│  app.html (48 KB) + static/app.js (92 KB, deferred)        │
│  + static/app.css (16.5 KB, compiled Tailwind)             │
│  SWR cache (stale-while-revalidate, retry, offline)        │
│  Drill-down modal (8 tabs: Why/Where/Evidence/Timeline/     │
│  People/Prediction/Simulation/Recommendation)               │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTPS (HttpOnly cookies)
┌──────────────────────────▼──────────────────────────────────┐
│              FastAPI Application (Python)                    │
│                                                              │
│  ┌──────────────────────────────────────────────────┐       │
│  │  Middleware Stack (execution order):              │       │
│  │  1. SecurityHeadersMiddleware (CSP, HSTS, nosniff)│       │
│  │  2. CSRFMiddleware (double-submit cookie)         │       │
│  │  3. EnhancedRateLimitMiddleware (per-IP+user)     │       │
│  │  4. TenantIsolationMiddleware (org_id context)    │       │
│  │  5. AuditMiddleware (all API calls logged)        │       │
│  └──────────────────────────────────────────────────┘       │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐     │
│  │  OEM Routes  │  │  Auth Routes  │  │  Import Routes  │     │
│  │  /api/oem/*  │  │ /api/auth/*   │  │ /api/imports/*  │     │
│  │  /api/oem/   │  │ /api/auth/    │  │ /api/oauth/*    │     │
│  │  learning/*  │  │ soc2/*        │  │ /scim/v2/*      │     │
│  └──────┬───────┘  └──────┬───────┘  └───────┬────────┘     │
│         │                 │                  │               │
│  ┌──────▼─────────────────▼──────────────────▼───────┐      │
│  │              OEM Engine (maestro_oem)               │      │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │      │
│  │  │ OEMEngine │ │ Decision │ │ ContinuousLearning│  │      │
│  │  │ (ingest)  │ │ Engine   │ │ Engine            │  │      │
│  │  └────┬─────┘ └────┬─────┘ └───────┬──────────┘  │      │
│  │       │            │               │              │      │
│  │  ┌────▼────┐ ┌────▼─────┐ ┌───────▼──────────┐  │      │
│  │  │Execution│ │Knowledge │ │CalibrationEngine  │  │      │
│  │  │Model    │ │Graph     │ │(10-bucket, Brier) │  │      │
│  │  └────┬────┘ └────┬─────┘ └───────┬──────────┘  │      │
│  │       │            │               │              │      │
│  │  ┌────▼────┐ ┌────▼─────┐ ┌───────▼──────────┐  │      │
│  │  │Evidence │ │Semantic  │ │DriftDetection     │  │      │
│  │  │Graph    │ │Auto-     │ │Engine             │  │      │
│  │  │(115 nodes)│ complete │ │(concept+org drift)│  │      │
│  │  └─────────┘ └──────────┘ └───────────────────┘  │      │
│  └────────────────────────────────────────────────────┘      │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Auth System (maestro_auth)                          │    │
│  │  ┌──────────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ │    │
│  │  │OIDC (5   │ │SAML  │ │SCIM  │ │RBAC  │ │MFA   │ │    │
│  │  │providers)│ │2.0   │ │2.0   │ │(5    │ │(TOTP │ │    │
│  │  │          │ │      │ │      │ │roles)│ │+back)│ │    │
│  │  └──────────┘ └──────┘ └──────┘ └──────┘ └──────┘ │    │
│  │  ┌──────────────────────────────────────────────┐  │    │
│  │  │  Security: CSRF, CSP, Rate Limit, Encryption, │  │    │
│  │  │  Key Rotation, Audit Chain, Session Expiry    │  │    │
│  │  └──────────────────────────────────────────────┘  │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Import Pipeline (maestro_oem/importers)             │    │
│  │  ┌──────┐ ┌────┐ ┌──────┐ ┌───────────┐ ┌──────┐  │    │
│  │  │GitHub│ │Jira│ │Slack │ │Confluence  │ │Gmail │  │    │
│  │  │Fetcher│ │Fetch│ │Fetch│ │Fetcher    │ │Fetch│  │    │
│  │  └──┬───┘ └──┬─┘ └──┬───┘ └─────┬─────┘ └──┬───┘  │    │
│  │     └────────┴───────┴───────────┴──────────┘       │    │
│  │           HistoricalImportEngine (parallel)          │    │
│  │           CheckpointStore (SQLite, resume)            │    │
│  │           ProgressTracker (WebSocket, 4Hz)            │    │
│  └─────────────────────────────────────────────────────┘    │
└──────────────────────────┬──────────────────────────────────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
    ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
    │  SQLite DBs │ │  SQLite DBs │ │  SQLite DBs │
    │  maestro.db │ │  auth.db    │ │  learning.db│
    │  (OEM state)│ │  (users,    │ │  (calibration│
    │             │ │   sessions, │ │   predictions,│
    │             │ │   RBAC)     │ │   drift)     │
    └─────────────┘ └─────────────┘ └─────────────┘
```

## Component Summary

| Component | Lines | Tests | Purpose |
|-----------|-------|-------|---------|
| `app.html` | 48 KB | 19 | Executive Cognition Center (9 sections) |
| `static/app.js` | 92 KB | 17 | SWR cache, drill-down, all 9 ECC renderers |
| `static/app.css` | 16.5 KB | — | Compiled Tailwind CSS |
| `maestro_oem/` | ~5,000 | 297 | OEM engine, learning, autocomplete, importers |
| `maestro_auth/` | ~3,500 | 109 | Enterprise auth, security, RBAC, OIDC/SAML/SCIM |
| `maestro_api/` | ~2,000 | 38 | FastAPI routes, CEO briefing, drill-down, SOC2 |

## Key Architectural Decisions

1. **Single-file frontend** — app.html + external JS/CSS (no build step needed)
2. **SQLite everywhere** — no external DB dependency (Postgres optional)
3. **OEM as single source of truth** — UI is pure renderer, no fake data
4. **SWR cache** — stale-while-revalidate with retry, offline, AbortController
5. **HttpOnly cookies** — no localStorage tokens (XSS-safe)
6. **Compiled Tailwind** — no CDN dependency (firewall-safe)
7. **Continuous learning** — every prediction calibrated, every feedback learned
