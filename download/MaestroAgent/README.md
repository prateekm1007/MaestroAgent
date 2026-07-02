# Maestro — Executive Cognition Center

**Organizational judgment infrastructure. Every insight derived from real execution signals.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

## What This Is

Maestro is an organizational judgment system that ingests execution signals from GitHub, Jira, Slack, Confluence, Gmail, and customer/CRM providers, then infers the organization's operating laws, surfaces contradictions, tracks assumptions and hypotheses, and calibrates individual prediction accuracy via a Brier-scored prediction market.

The product is built around a connected cognitive model: **Intent → Assumptions → Hypotheses → Predictions → Preparations → Contradictions → Perspectives → Calibration**. Every capability is backed by a real API endpoint and a UI surface.

## Quick Start

```bash
# Install
cd backend
pip install -e .

# Run the server
python -m maestro_cli.main serve --port 1420

# Open the app
# Visit http://localhost:1420/app.html
```

The app loads in demo mode with synthetic `acme-corp` sample data. Connect real providers via Settings to see live signals.

## Architecture

```
backend/
  maestro_oem/          Organizational Execution Model (signal ingestion, law inference,
                        prediction lifecycle, calibration, cognitive model)
  maestro_api/          FastAPI routes (OEM, auth, imports, WebSocket)
  maestro_db/           SQLAlchemy 2.0 + Alembic (SQLite dev, PostgreSQL production)
  maestro_auth/         RBAC, OAuth, OIDC, SAML, SCIM, Fernet KMS (fail-closed)
  maestro_core/         Agent orchestration (LangGraph + CrewAI hybrid)
  maestro_llm/          Model-agnostic LLM router
  maestro_memory/       Vector + graph memory
  alembic/              Database migrations (25 tables)

app.html                Executive UI (19 surfaces, vanilla JS, no build step)
static/
  app.css               Anthropic-style design system (dark + light themes)
  css/design-system.css Cognitive-model surface tokens
  js/                   19 modular JS files (core, maestro, swr_cache, home, ask,
                        physics, live_meeting, customer_judgment, intent_cascade,
                        contradictions, prediction_market, assumptions, etc.)
```

## Key Capabilities

| Capability | API | UI Surface |
|---|---|---|
| Intent Cascade | `GET /api/oem/intents/{id}` | Intent Cascade sidebar |
| Prepared Decisions | `GET /api/oem/preparations` | Home panel |
| Dangerous Assumptions | `GET /api/oem/assumptions/dangerous` | Assumptions sidebar |
| Hypothesis Resolution | `POST /api/oem/hypotheses/{id}/resolve` | Intent Cascade inline |
| Contradictions | `GET /api/oem/contradictions` | Contradictions sidebar |
| Perspectives (6 teams) | `GET /api/oem/perspectives` | Drill-down modal tab |
| Prediction Market | `GET /api/oem/predictions/market/calibration` | Prediction Market sidebar |
| Coordination Engine | `POST /api/oem/coordinate` | API (no dedicated UI yet) |

## Design System

- **Dark mode** (default): `#0A0A0F` background, `#F0F0F5` text, `#7C5CFF` accent
- **Light mode** (Claude.ai-inspired): `#FFFFFF` background, `#1A1A1A` text
- Toggle in sidebar footer, persists via localStorage, respects OS preference
- WCAG 2.1: skip-to-content, ARIA landmarks, focus-visible, prefers-reduced-motion

## Production Deployment

```bash
# 1. Set environment
export DATABASE_URL=postgresql://user:pass@host:5432/maestro
export MAESTRO_ENV=production
export MAESTRO_MASTER_KEY=<fernet-key>
export MAESTRO_MESSAGE_BROKER=redis
export REDIS_URL=redis://...
export MAESTRO_DEMO_SEED=false

# 2. Run migrations
cd backend && alembic upgrade head

# 3. Start 3+ instances behind a load balancer
uvicorn maestro_api.main:create_app --factory --port 8001
uvicorn maestro_api.main:create_app --factory --port 8002
uvicorn maestro_api.main:create_app --factory --port 8003
```

See `scripts/test_3_replica_scaling.py` for the horizontal scaling verification.

## Testing

```bash
cd backend

# Backend tests
python -m pytest maestro_oem/tests/ maestro_api/tests/ maestro_auth/tests/

# Frontend smoke tests (Playwright)
python -m pytest maestro_api/tests/test_frontend_smoke.py
python -m pytest maestro_api/tests/test_cognitive_surfaces.py

# Learning loop verification
python ../scripts/verify_loop_closed.py

# 3-replica scaling test
python ../scripts/test_3_replica_scaling.py
```

## License

MIT — see [LICENSE](LICENSE).
