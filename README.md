# MaestroAgent

**Maestro — Personal Intelligence.** Remembers what you promised, surfaces what changed, and tells you what to do next — with provenance.

---

## What is in this repo

This repo contains exactly one live product: **Maestro Personal**, a personal commitment intelligence system.

### The live app

| Component | Location | Stack |
|---|---|---|
| **Frontend** | `download/MaestroAgent/maestro-personal/web/` | Next.js 16, React, TypeScript, Tailwind CSS, shadcn/ui |
| **Backend** | `download/MaestroAgent/maestro-personal/src/maestro_personal_shell/` | Python, FastAPI, SQLite |
| **Mobile** | `download/MaestroAgent/maestro-personal/mobile/` | Expo React Native |

The frontend is a Next.js app that proxies `/api/*` to the FastAPI backend via `next.config.ts` rewrites. The backend serves the API on port 8766 (local) or Railway's PORT (production).

### Live deployment

| Service | URL | Purpose |
|---|---|---|
| Frontend | `https://web-production-d5c26.up.railway.app/` | Next.js web app |
| Backend | `https://maestroagent-production.up.railway.app/` | FastAPI REST API |

Login with password `maestro-demo` to see demo data.

### How to run locally

```bash
# Terminal 1 — backend (API on port 8766)
cd download/MaestroAgent/maestro-personal
pip install -e ".[dev]"
PYTHONPATH=src MAESTRO_PERSONAL_TOKEN=maestro-demo MAESTRO_DEMO_MODE=1 \
  python -m maestro_personal_shell.api

# Terminal 2 — web app (UI on port 3000)
cd download/MaestroAgent/maestro-personal/web
npm install
npm run dev
```

Open http://localhost:3000. Login with password `maestro-demo`.

### Key features

- **Ask**: Evidence-backed Q&A with provenance (signal IDs, timestamps, confidence, unknowns)
- **Commitments**: Automatic commitment extraction with lifecycle tracking (active → resolved → cancelled)
- **Prepare**: Pre-meeting intelligence with contradiction detection
- **What Changed**: Meaningful delta detection (not activity summaries)
- **Synthetic Inbox**: 20 categorized demo emails to experience the full lifecycle without OAuth
- **Multi-turn conversation**: Session-based follow-up questions with entity context

### Architecture

```
Signals (Gmail, Calendar, manual entry, synthetic inbox)
    ↓
Commitment Classifier (15 types, lifecycle states)
    ↓
Commitment Ledger (state machine: active → completed → cancelled)
    ↓
5-Stage Retrieval (BM25 → specialists → RRF → Cohere rerank → LLM grounding)
    ↓
Ask / Dashboard / Prepare / What Changed / Ambient
```

### Deprecated code

The old `app.html` (vanilla JS frontend) and enterprise surfaces (Executive Cognition Center, Organizational Pulse) are **no longer the product**. The current product is the personal-focused Next.js app described above.

### Governance

The repo includes governance files (`GOVERNANCE.md`, `ENTROPY_RECOVERY.md`, `AUDITOR_GOVERNANCE.md`) that define the development protocol: execute before claiming, read assertions not names, and never trust a claim without reproduction.
