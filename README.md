# Maestro Personal

**Personal commitment intelligence.**

Maestro remembers what you promised, surfaces what changed,
and tells you what to do next — with provenance.

---

## Live Product

| Component | URL |
|---|---|
| Backend API | https://maestroagent-production.up.railway.app |
| Health | https://maestroagent-production.up.railway.app/api/health |
| OpenAPI | https://maestroagent-production.up.railway.app/api/openapi.json |

## Stack

- **Backend:** Python, FastAPI, SQLite, OpenRouter LLM (Gemma 3 12B)
- **Frontend:** Next.js 16, React, TypeScript, Tailwind CSS, shadcn/ui
- **Deploy:** Railway (Docker)

## Architecture

```
maestro-personal/
├── src/maestro_personal_shell/
│   ├── api.py              # FastAPI app
│   ├── routers/
│   │   ├── admin.py        # Health + version canary
│   │   ├── ask.py          # Evidence-backed Q&A
│   │   ├── auth.py         # Register + login
│   │   ├── inbox.py        # Synthetic inbox
│   │   └── ...
│   └── ...
├── web/                    # Next.js frontend
├── pyproject.toml
└── Dockerfile
```

## API

- `POST /api/auth/register` — create account
- `POST /api/auth/login` — get JWT token
- `POST /api/ask` — evidence-backed question answering
- `GET /api/inbox/synthetic` — 20 demo emails, 6 categories
- `POST /api/inbox/synthetic/{id}/receive` — ingest email as signal
- `GET /api/commitments` — commitment ledger
- `GET /api/health` — version canary + build identity
- `GET /api/openapi.json` — OpenAPI 3.1 contract

## Local Development

```bash
cd download/MaestroAgent/maestro-personal
pip install -e ".[dev]"
PYTHONPATH=src MAESTRO_PERSONAL_TOKEN=maestro-demo MAESTRO_DEMO_MODE=1 \
  python -m maestro_personal_shell.api
```

Backend runs on http://localhost:8766.

## Key Features

- **Ask**: Evidence-backed Q&A with provenance (signal IDs, timestamps, confidence, unknowns)
- **Commitments**: Automatic commitment extraction with lifecycle tracking (active → completed → cancelled)
- **Multi-turn conversation**: Session-based follow-up questions with entity context
- **Synthetic Inbox**: 20 categorized demo emails to experience the full lifecycle without OAuth

## Governance

The repo includes governance files (`GOVERNANCE.md`, `ENTROPY_RECOVERY.md`, `AUDITOR_GOVERNANCE.md`) that define the development protocol: execute before claiming, read assertions not names, and never trust a claim without reproduction.
