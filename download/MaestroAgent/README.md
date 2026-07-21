# MaestroAgent — Personal Commitment Intelligence

**Maestro remembers what you promised, surfaces what changed, and tells you what to do next — with provenance.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## What This Is

Maestro is a **personal commitment intelligence system**. It tracks what you promised, to whom, by when, and whether you delivered — with evidence-backed provenance for every answer.

The product unit is not `Agent → Insight`. It is:

```
Signal (email, calendar, manual) →
Commitment Detection →
Lifecycle Tracking (active → resolved → cancelled) →
Evidence-Backed Q&A →
What Changed + Prepare + Dashboard
```

### Key Capabilities

- **Ask**: Evidence-backed Q&A with signal IDs, timestamps, confidence, and explicit unknowns
- **Commitments**: Automatic extraction with 15-type classifier + lifecycle state machine
- **Prepare**: Pre-meeting intelligence with contradiction detection
- **What Changed**: Meaningful delta detection (resolutions, cancellations, new commitments)
- **Synthetic Inbox**: 20 categorized demo emails for testing without OAuth
- **Multi-turn Conversation**: Session-based follow-up questions with entity context

## Live Deployment

| Service | URL |
|---|---|
| Frontend (Next.js) | `https://web-production-d5c26.up.railway.app/` |
| Backend (FastAPI) | `https://maestroagent-production.up.railway.app/` |

Login with password `maestro-demo` to see demo data.

## How to Run Locally

```bash
# Backend (port 8766)
cd maestro-personal
pip install -e ".[dev]"
PYTHONPATH=src MAESTRO_PERSONAL_TOKEN=maestro-demo MAESTRO_DEMO_MODE=1 \
  python -m maestro_personal_shell.api

# Frontend (port 3000)
cd maestro-personal/web
npm install && npm run dev
```

## Architecture

```
Signals (Gmail, Calendar, manual entry, synthetic inbox)
    ↓
Commitment Classifier (15 types, lifecycle states)
    ↓
Commitment Ledger (state machine: active → completed → cancelled)
    ↓
5-Stage Retrieval (BM25 → specialists → RRF → Cohere rerank → LLM grounding)
    ↓
Surfaces: Ask / Dashboard / Prepare / What Changed / Ambient
```

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16, React, TypeScript, Tailwind CSS, shadcn/ui |
| Backend | Python, FastAPI, SQLite |
| Mobile | Expo React Native |
| LLM | Gemma 3 12B via OpenRouter (production), ZAI-GLM (sandbox) |
| Retrieval | BM25 + 5 specialist retrievers + RRF + Cohere Rerank |
| Reranker | Cohere rerank-multilingual-v3.0 |

## Governance

This repo uses an audit-driven development protocol (GOVERNANCE.md, ENTROPY_RECOVERY.md, AUDITOR_GOVERNANCE.md). Every fix includes root cause analysis, before/after verification, and honest disclosure of limitations.

## Note on Legacy Code

The old `app.html` (vanilla JS frontend) and enterprise surfaces (Executive Cognition Center, Organizational Pulse, Nerve agents) are **deprecated**. The current product is the personal-focused Next.js app described above. The enterprise code remains in the repo for reference but is not deployed or maintained.
