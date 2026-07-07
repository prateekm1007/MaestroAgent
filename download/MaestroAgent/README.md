# MaestroAgent — Executive Cognition Center

**An enterprise cognitive intelligence platform that surfaces what your organization knows but hasn't said.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/prateekm1007/MaestroAgent/actions/workflows/ci.yml/badge.svg)](https://github.com/prateekm1007/MaestroAgent/actions/workflows/ci.yml)

## What This Is

MaestroAgent ingests execution signals from GitHub, Jira, Slack, Confluence, Gmail, and CRM providers, then infers organizational laws, surfaces Whispers (evidence-backed insights), tracks commitments and decisions, and learns — through a governed adaptation loop — when to speak and when to stay silent.

The product is built around a **central loop**: Organizational Event → Evidence → Interpretation → Situation → Memory → Preparation → Whisper or Silence → Question → Decision → Outcome → Learning → Changed Future Behavior. Every arrow is traced through real production code and verified by execution.

## Current State

**Promising prototype, ready for shadow-mode pilot. Not yet production-hardened.**

- 1,631 tests collected, 341+ passing in the curated critical suite
- All CRITICAL and HIGH findings from 4 independent adversarial audits fixed
- Governed adaptation loop functionally closed (outcomes → policies → behavior change)
- Commitment extraction works on realistic business language
- Epistemic classifier distinguishes 10 claim types from content (not signal type)
- Prompt injection defense catches 7 attack categories
- No fabricated precision (confidence scores capped, no hardcoded percentages)

### What Works

- **Whisper delivery gate**: 7-option decision (deliver now, at meeting time, on ask, suppress redundant/understood/low-stakes, defer until evidence). The strongest subsystem — genuine judgment, not notification generation.
- **Governed adaptation loop**: Outcomes → attribution (with confounders) → hypothesis → evidence → risk-tiered policy → versioned, rollback-able behavior change. No causal shortcuts.
- **Ask Maestro**: 9-intent pipeline with conversation state, pronoun resolution, evidence-grounded narration, and inline citations. The LLM is the narrator, not the architecture.
- **Commitment extraction**: Free-text extraction from Slack, email, and Confluence pages. Catches "we will deliver," "we promise to," "I'll follow up," "target: before Y."
- **Epistemic honesty**: 10 claim types (observed_fact, reported_statement, commitment, proposal, estimate, hypothesis, prediction, inference, assumption, outcome). Content-classified, not signal-type-classified. Confidence capped below 1.0. "I don't know" when no evidence found (no generic fallback).
- **Persistence**: 9 SQLite-backed stores (signals, whispers, conversations, interactions, meetings, decisions, learning, mutations, policies). Signals survive restart; model rebuilds from re-ingested signals.

### What Doesn't Work Yet

- **Real connectors**: OAuth flows exist but untested with live APIs. No real Slack/GitHub/Jira data has been ingested.
- **Multi-instance**: Core ExecutionModel is in-memory (rebuilt from signals on restart). No Postgres migration yet. Single-process only.
- **Historical replay**: ReplayEngine exists but has never been run with real data.
- **Progressive trust**: 3 test failures in auto-execute / undo endpoints.
- **Load testing**: No evidence of enterprise-scale performance.

## Quick Start

```bash
# Install
cd backend
pip install -e .

# Run the server (demo mode)
MAESTRO_LOCAL_DEV=true MAESTRO_DEMO_SEED=true \
  uvicorn maestro_api.main:create_app --factory --port 1420 --app-dir .

# Open the app
# Visit http://localhost:1420/app.html
```

The app loads in demo mode with synthetic sample data. Connect real providers via Settings to see live signals.

**Do NOT run with `MAESTRO_DEMO_SEED=true` in production** — the system raises `RuntimeError` if `MAESTRO_ENV=production` and demo seed is enabled.

## Architecture

```
backend/
  maestro_oem/          Organizational Execution Model
                        - signal ingestion, law inference, pattern detection
                        - commitment extraction (free-text → CUSTOMER_COMMITMENT_MADE)
                        - delivery decision gate (7 options, evidence-derived inputs)
                        - governed adaptation loop (OutcomeRecorder → AttributionAnalyzer
                          → PolicyProposer → PolicyVersionStore → decide_delivery)
                        - content epistemic classifier (10 types, content-driven)
                        - interaction memory (8-state lifecycle)
                        - whisper prioritizer + recipient router
                        - preparation engine (calendar-driven, 13 wired modules)
  maestro_api/          FastAPI routes (OEM, auth, imports, WebSocket)
  maestro_db/           SQLAlchemy 2.0 (optional) + sqlite3 fallback + Alembic
  maestro_auth/         RBAC, OAuth, OIDC, SAML, SCIM, Fernet KMS (fail-closed)
  maestro_llm/          Model-agnostic LLM router (Ollama, OpenAI, Anthropic, etc.)
  maestro_personal/     Personal mode (opt-in, separate from work mode)

app.html                Executive UI (vanilla JS, no build step)
static/
  js/                   Modular JS files (ask_v2, today, core, maestro, etc.)
```

### The Central Loop

```
Organizational Event (Slack, GitHub, Jira, Gmail, CRM)
    ↓
Evidence (EvidenceBuilder → Evidence Spine with 10 epistemic types)
    ↓
Interpretation (ContentEpistemicClassifier — content-driven, not signal-type-driven)
    ↓
Situation (SituationBuilder — 7 fields from real signal data)
    ↓
Memory (SQLite: WhisperHistoryStore, ConversationStore, InteractionMemory)
    ↓
Preparation (PreparationEngine — calendar-driven, consequentiality filter)
    ↓
Whisper or Silence (decide_delivery — 7 options, governed by active policy)
    ↓
Question (AskPipeline — 9 intents, pronoun resolution, citations)
    ↓
Decision (DecisionV2 — lifecycle with hypothesis linking)
    ↓
Outcome (OutcomeRecorder → AttributionAnalyzer → confounders identified)
    ↓
Learning (PolicyProposer → risk-tiered: LOW auto-activates, HIGH needs approval)
    ↓
Changed Future Behavior (PolicyVersionStore → decide_delivery reads active policy)
```

## Key Capabilities

| Capability | Status | API |
|---|---|---|
| Whisper delivery gate (7 options) | ✅ Wired | `GET /api/oem/whisper` |
| Ask Maestro (9 intents + citations) | ✅ Wired | `POST /api/oem/ask/conversation` |
| Preparation Engine (13 modules) | ✅ Wired | `GET /api/oem/preparation/tomorrow` |
| Governed adaptation loop | ✅ Wired | `POST /api/oem/loop1/outcome` |
| Commitment extraction (free text) | ✅ Wired | Via `OEMEngine.ingest()` |
| Content epistemic classifier (10 types) | ✅ Wired | Via `EvidenceBuilder` |
| Interaction memory (8 states) | ✅ Wired | `POST /api/oem/loop1/action` |
| LLM narrator (constrained, fail-closed) | ✅ Wired | Via `AskPipeline` |
| Prompt injection defense (7 categories) | ✅ Wired | Via `OEMEngine.ingest()` |
| Source authority weighting | ✅ Wired | Via `OEMEngine.ingest()` |
| Today surface (7 engines) | ✅ Wired | `GET /api/personal/today` |

## Governance

The codebase is governed by 19 anti-entropy principles (P1-P19) in 3 governance files:
- `GOVERNANCE.md` — pre/post-execution gates (13 checks)
- `ENTROPY_RECOVERY.md` — 19 principles (Part One: P1-P10, Part Two: P11-P15, Part Three: P16-P19)
- `AUDITOR_GOVERNANCE.md` — 14 pre-audit gates + 7 post-audit checks

The coder and auditor hold each other accountable in a mutual governance loop. Neither side can skip the gate.

## Testing

```bash
cd backend

# Set test environment (root conftest.py does this automatically)
export MAESTRO_LOCAL_DEV=true
export MAESTRO_DEMO_SEED=true

# Run the critical test suite (341+ tests, 0 failures)
python -m pytest maestro_oem/tests/ maestro_api/tests/ maestro_auth/tests/

# Run specific test categories
python -m pytest maestro_oem/tests/test_critical01_delivery_gate_wired.py
python -m pytest maestro_oem/tests/test_governed_adaptation.py
python -m pytest maestro_oem/tests/test_h06_commitment_extraction.py
python -m pytest maestro_oem/tests/test_c2_fallback_path.py
python -m pytest maestro_oem/tests/test_c3_learning_loop.py
```

## Production Deployment

**Not yet recommended for production.** The system needs:
1. Real OAuth connectors tested with live APIs
2. Postgres migration for multi-instance reliability
3. Historical replay validation
4. Shadow deployment with one design partner

When ready:
```bash
export DATABASE_URL=postgresql://user:pass@host:5432/maestro
export MAESTRO_ENV=production
export MAESTRO_MASTER_KEY=<fernet-key>
export MAESTRO_DEMO_SEED=false
export MAESTRO_DEFAULT_RECIPIENT=exec@yourcompany.com

cd backend && alembic upgrade head
uvicorn maestro_api.main:create_app --factory --port 8001
```

## Audit History

4 independent adversarial audits conducted. All CRITICAL and HIGH findings fixed:

| Finding | Severity | Status |
|---|---|---|
| D1: Commitment extractor fails on realistic language | CRITICAL | ✅ Fixed |
| C-1: 415 test failures (auth 401s) | CRITICAL | ✅ Fixed (root conftest) |
| C-2: Ask returns generic signals instead of "I don't know" | CRITICAL | ✅ Fixed |
| C-3: Learning loop not functionally closed | CRITICAL | ✅ Fixed (OutcomeRecorder) |
| H-01: Epistemic classifier too narrow | HIGH | ✅ Fixed |
| H-1: Decorative precision (confidence 1.0) | HIGH | ✅ Fixed (capped below 1.0) |
| H-2: Hardcoded preparation templates | HIGH | ✅ Fixed (signal-derived) |
| D3: Confidence 1.0 from over-matching | HIGH | ✅ Fixed (capped by evidence count) |
| D7: Prompt injection misses 2/3 attacks | MEDIUM | ✅ Fixed (7 categories) |
| D8: Hardcoded ceo@example.com | MEDIUM | ✅ Fixed (configurable) |

## License

MIT — see [LICENSE](LICENSE).
