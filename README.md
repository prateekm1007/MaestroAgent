# MaestroAgent

**The Organizational Judgment System.**

Foundation models generate intelligence. Maestro institutionalizes judgment.

---

## What is in this repo

This repo is a curated product repository. There is exactly one live product:

### The live app

| Component | Location | Stack |
|---|---|---|
| **Frontend** | `download/MaestroAgent/app.html` + `static/app.js` + `static/app.css` | Vanilla JS, compiled Tailwind CSS, no CDN |
| **Backend** | `download/MaestroAgent/backend/maestro_oem/` + `backend/maestro_api/` | Python, FastAPI, SQLite |

The backend serves `app.html` at `/`. That is the product. Everything else in
this repo is either infrastructure, tests, or deprecated.

### How to run it

```bash
cd download/MaestroAgent
pip install -e backend/
python -m maestro_api.main  # serves on http://localhost:8000
```

The OEM is seeded with a demo dataset (acme-corp + 3 enterprise customers)
so the product is evaluable without OAuth credentials. Set
`MAESTRO_DEMO_SEED=false` to start with an empty OEM.

### Deprecated code

The `_deprecated/` folder contains abandoned frontends and a Node.js backend
from earlier iterations. They are kept for reference but are NOT the product:

- `_deprecated/desktop/` — Tauri + React (abandoned Jun 25)
- `_deprecated/frontend/` — Vite + React (abandoned Jun 25)
- `_deprecated/frontend-next/` — Next.js (stalled Jun 28)
- `_deprecated/v6-production/` — Next.js + Prisma + Redis (stalled Jun 28)
- `_deprecated/realtime-server/` — Node.js backend (duplicate connectors, abandoned)
- `_deprecated/app-mock.html`, `app-v6.html`, `app-v7.html` — old mockups

**Do not run anything in `_deprecated/`.** It is not maintained, not tested,
and not the product.

---

## Architecture

```
Signals (GitHub, Jira, Slack, Confluence, Gmail, Customer/CRM)
    ↓
ExecutionSignals (normalized)
    ↓
LearningObjects (evidence units)
    ↓
Patterns (regularities across LOs)
    ↓
OrganizationalLaws (validated patterns)
    ↓
DecisionEngine (recommendations with evidence)
    ↓
OEM Surfaces (Executive Cognition, Customer Judgment, Simulator, etc.)
```

Every recommendation is evidence-backed. Every confidence value is explainable.
The learning loop is closed: predictions auto-create, auto-resolve, and
auto-calibrate.

See `download/MaestroAgent/docs/ARCHITECTURE.md` for the full design.

---

## Security

- **KMS:** The local file-based KMS is for development only. In production,
  set `KMS_PROVIDER=aws` and `KMS_MASTER_KEY_ID=<arn>`. The server refuses to
  start in production (`NODE_ENV=production`) with the local provider.
- **Auth:** OIDC (Azure AD, Okta, Google, Auth0, Supabase), SAML 2.0, SCIM 2.0,
  RBAC (5 roles, 13 permissions), MFA, HttpOnly cookies with rotating refresh
  tokens.
- **Hardening:** CSRF, CSP, HSTS, rate limiting, tenant isolation, AES-256-GCM
  encryption, key rotation, tamper-evident audit, session expiry, SOC2 monitoring.

See `download/MaestroAgent/docs/THREAT_MODEL.md` and
`download/MaestroAgent/docs/PEN_TEST_CHECKLIST.md`.

---

## Tests

```bash
cd download/MaestroAgent
python -m pytest backend/maestro_oem/tests/ backend/maestro_api/tests/ backend/maestro_auth/tests/
```

837+ tests pass on a clean clone. The learning loop verification:

```bash
python scripts/verify_loop_closed.py
```

---

## License

See `download/MaestroAgent/LICENSE`.
