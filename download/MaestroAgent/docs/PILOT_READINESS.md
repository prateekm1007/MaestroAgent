# Maestro Pilot Readiness

## Quick Start

```bash
# 1. Install dependencies
cd download/MaestroAgent/backend
pip install -e ".[dev]"

# 2. Set environment variables
export MAESTRO_LOCAL_DEV=true
export MAESTRO_DEMO_SEED=true
export MAESTRO_APP_DIR=$(dirname $(pwd))
export MAESTRO_AUTH_DB=/tmp/maestro_auth.db
export MAESTRO_ADMIN_PASSWORD=your-admin-password

# 3. Start the server
cd backend
python -m maestro_api.main
# Server runs on port 8765 by default

# 4. Verify in 5 minutes
curl http://localhost:8765/api/health
curl http://localhost:8765/api/council/situations
curl -X POST http://localhost:8765/api/council/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "What is happening with Globex?"}'
```

## Environment Variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `MAESTRO_LOCAL_DEV` | unset | No | Set to `true` to disable auth (dev only) |
| `MAESTRO_DEMO_SEED` | `true` | No | Load acme-corp demo data on startup |
| `MAESTRO_APP_DIR` | `.` | Yes | Path to directory containing `app.html` and `static/` |
| `MAESTRO_AUTH_DB` | `auth.db` | Yes | SQLite path for auth database |
| `MAESTRO_ADMIN_PASSWORD` | unset | Yes | Admin password for CLI |
| `MAESTRO_USE_COUNCIL` | `true` | No | Use Cognitive Council as default (recommended) |
| `MAESTRO_SITUATION_DB` | `situations.db` | No | SQLite path for situation persistence |

## Default Port

The server runs on **port 8765** (not 8000).

## Council Mode (Default)

Council mode is the **default product path**. All executive surfaces (Ask, Briefing, Prepare, Whisper) route through the Cognitive Council's Situation Engine. Legacy `/api/oem/*` routes remain for backward compatibility.

To disable council mode: `export MAESTRO_USE_COUNCIL=false`

## Demo Mode

Demo mode loads the acme-corp dataset (66 organizational signals) through the real ingestion pipeline. This provides:
- 3+ situations (Globex, Hooli, Initech)
- Evidence-backed Ask answers
- Morning briefing content
- Preparation materials

To disable demo mode: `export MAESTRO_DEMO_SEED=false`

## Running Tests

```bash
# Cognitive council suite (hermetic, fast)
cd backend
python -m pytest maestro_cognitive_council/tests/ -q

# Pilot smoke test (fresh app, no warmup)
python -m pytest maestro_api/tests/test_pilot_smoke_fresh_app.py -v

# Security tests
python -m pytest maestro_api/tests/test_tenant_isolation.py -q
python -m pytest maestro_api/tests/test_auth_coverage_matrix.py -q

# Behavioral validation (run from repo root)
python scripts/test1_world_model_benchmark.py
python scripts/test2_behavioral_coherence.py
```
