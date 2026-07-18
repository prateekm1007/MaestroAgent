# Maestro Personal

A FastAPI HTTP service that wraps the Cognitive Council Core (`maestro_cognitive_council`)
to provide a personal intelligence API on port 8766. SQLite persistence, FTS5 semantic
retrieval, bearer token auth, and 85+ REST endpoints across 6 surfaces.

## Monorepo Structure

This is a monorepo containing the backend, mobile app, and web app:

```
maestro-personal/
├── src/                   ← Backend (FastAPI, Python 3.12)
├── tests/                 ← Backend tests (1350+ tests, most passing)
├── evaluation/            ← Benchmarks + scoring scripts
├── mobile/                ← Expo React Native app (4-tab, Bumble theme)
├── web/                   ← Next.js web app (Bumble theme, Connectors)
└── docs/                  ← Documentation
```

### Quick Start

```bash
# Clone
git clone https://github.com/prateekm1007/MaestroAgent.git
cd MaestroAgent/maestro-personal

# Backend setup
pip install -e .          # installs package + CLI (no PYTHONPATH needed)
python -m pytest tests/   # run tests

# Start backend API (port 8766)
python -m maestro_personal_shell.api

# Mobile app (Expo)
cd mobile && npm install && npx expo start

# Web app (Next.js, port 3000)
cd web && npm install && npm run dev
```

### Environment Variables

The backend works out-of-the-box in **demo mode** (rule-based AI, mock connectors,
no transcription). To activate real intelligence, set these env vars:

```bash
# ── LLM (for AI-powered Ask answers) ──
# Option A: Local Ollama (free, needs GPU)
export MAESTRO_WHISPER_MODEL=base          # or: tiny, small, medium, large
# Option B: Remote Ollama (free, cloud GPU like Kaggle P100)
export OLLAMA_HOST=https://your-tunnel.trycloudflare.com

# ── Speech-to-Text (for Copilot transcription) ──
# Option A: Wit.ai (RECOMMENDED — free, scalable, cloud-based)
#   Get token at https://wit.ai → create app → Settings → Server Access Token
export MAESTRO_WITAI_TOKEN=your-witai-token
# Option B: Local Whisper (free, not scalable — needs pip install openai-whisper)
export MAESTRO_WHISPER_MODEL=base
# Option C: OpenAI Whisper API (paid)
export MAESTRO_OPENAI_API_KEY=sk-...

# ── OAuth Connectors (for Gmail/Calendar/Slack/GitHub ingestion) ──
# Gmail + Calendar share the same Google Cloud OAuth client
export MAESTRO_GMAIL_CLIENT_ID=your-client-id.apps.googleusercontent.com
export MAESTRO_GMAIL_CLIENT_SECRET=GOCSPX-...
export MAESTRO_CALENDAR_CLIENT_ID=same-as-gmail
export MAESTRO_CALENDAR_CLIENT_SECRET=same-as-gmail
# Slack (https://api.slack.com/apps → create app → OAuth & Permissions)
export MAESTRO_SLACK_CLIENT_ID=your-slack-id
export MAESTRO_SLACK_CLIENT_SECRET=your-slack-secret
# GitHub (https://github.com/settings/developers → New OAuth App)
export MAESTRO_GITHUB_CLIENT_ID=your-github-id
export MAESTRO_GITHUB_CLIENT_SECRET=your-github-secret

# ── Security ──
# Auth token (if not set, auto-generated on first run)
export MAESTRO_PERSONAL_TOKEN=your-secret-token
# Production mode (disables bootstrap token, requires real auth)
export MAESTRO_PERSONAL_ENV=production
# Rate limiting (pip install slowapi)
# Rate limiting is auto-enabled when slowapi is installed

# ── Encryption (for OAuth token storage) ──
# If not set, falls back to dev-mode (plaintext prefix)
export MAESTRO_ENCRYPTION_KEY=your-fernet-key
```

**Without any env vars:** the app runs in demo mode — rule-based AI, mock
connector data, no transcription. All endpoints work, just with sample data.

**With LLM + Wit.ai + OAuth:** the full moat is real — LLM-powered answers,
real Gmail/Calendar ingestion, real speech-to-text, real draft generation.

## What this is

The 6 surfaces of Maestro Personal:

| Surface | Endpoint(s) | Core capability called | What the shell adds |
|---------|-------------|------------------------|---------------------|
| **Ask** | `POST /api/ask` | `SituationAwareAskBridge.ask()` + FTS5 + ask_ranker | Personal-data Q&A with provenance |
| **Commitments** | `GET /api/commitments`, `/the-one`, `/ledger` | `classify_commitment()` + commitment_ledger | Personal commitment tracking + lifecycle |
| **Prepare** | `GET /api/prepare` | `SituationPreparationBridge.prepare_for_situation()` | Personal meeting context |
| **What Changed** | `GET /api/what-changed`, `/the-shifts` | `SituationEngine.apply_signal()` → `SituationDelta` | Material delta surfacing (2 cards, not a feed) |
| **Whisper** | `GET /api/whisper` | `DeliveryGovernor` + `WhisperSituationBridge` | Trusted silence — speaks only when it matters |
| **Copilot** | `WS /ws/copilot`, `POST /api/copilot/transcript` | `CopilotSituationBridge` + context fuser | Real-time call intelligence |

## Architecture

```
maestro-personal/
├── src/maestro_personal_shell/
│   ├── api.py                          ← FastAPI app (4,900+ lines, 50+ routes, port 8766)
│   ├── shell.py                        ← PersonalShell: builds SituationEngine with personal signals
│   ├── personal_oem_state.py           ← PersonalOemState: has .signals, passes to Core
│   ├── semantic_retrieval.py           ← FTS5 + BM25 + ask_ranker for evidence retrieval
│   ├── commitment_ledger.py            ← Normalized commitment state machine
│   ├── learning_loop_v2.py             ← Behavior patterns + dismissal rate + auto-resolve
│   ├── outcome_tracker.py              ← Predictions + Brier score calibration
│   ├── personal_graph.py               ← Knowledge graph (entities, edges, completion rates)
│   ├── materiality_gate.py             ← Rule-based + LLM-powered materiality scoring
│   ├── dynamic_agents.py               ← 8 specialist agents + dynamic routing
│   ├── copilot_live.py                 ← Live copilot + ambient intelligence
│   ├── copilot_context_fuser.py        ← Multi-signal fusion for proactive coaching
│   ├── llm_bridge.py                   ← LLM provider abstraction + injection defense
│   ├── llm_output_guardrail.py         ← Output safety filtering
│   ├── claim_verifier.py               ← Answer verification against evidence
│   ├── db_util.py                      ← Shared SQLite connection helper (busy_timeout + WAL)
│   ├── audit_trust.py                  ← Audit log + calibration history
│   ├── observability.py                ← Trace events + per-request logging
│   ├── success_metrics.py              ← Product metrics (commitment rate, silence, calibration)
│   ├── behavior_change.py              ← Behavior change tracking
│   ├── entity_resolver.py              ← Entity alias normalization (fuzzy matching)
│   ├── temporal_query.py               ← Natural language temporal parsing
│   ├── push.py                         ← Cross-device push notifications
│   ├── signal_adapters/                ← Gmail, Calendar, Slack payload adapters
│   └── surfaces/
│       ├── ask.py                      ← calls SituationAwareAskBridge
│       ├── commitments.py              ← calls commitment_ledger
│       ├── prepare.py                  ← calls SituationPreparationBridge
│       ├── what_changed.py             ← calls SituationEngine + detect_stale_commitments
│       └── whisper.py                  ← calls DeliveryGovernor + stale detection
└── tests/
    ├── test_personal_shell_works.py    ← smoke test + no-dilution guard
    ├── test_30_day_benchmark.py        ← the Life-of-Work Benchmark
    ├── test_p0_1_dismissal_learning.py ← A/B test: learning alters behavior
    ├── test_p0_2_websocket_copilot.py  ← WebSocket route proof
    ├── test_p0_3_10k_performance.py    ← Ask p95 ≤ 500ms at 10K signals
    ├── test_p1_1_memory_quality.py     ← Temporal + entity + abstention
    ├── test_p1_2_injection_expansion.py← 30 injection bypass tests
    ├── test_p1_3_db_lock_timeout.py    ← busy_timeout + 503 handler
    ├── test_p1_4_token_security.py     ← SHA-256 hashing + revoke + rotate
    ├── test_audit_f1_verification.py   ← Cross-user prediction isolation
    ├── test_audit_f2_f3_ask_and_token.py ← Ranker-driven answer + no token leak
    ├── test_audit_f4_f10_remaining.py  ← Completion, graph, silence, routing, copilot
    ├── test_audit_round2_findings.py   ← Copilot quiet acks, critical recall, graph count
    └── conftest.py                     ← sys.path setup
```

## Running

```bash
# Install
pip install -e backend/
pip install fastapi uvicorn pytest

# Set auth token
export MAESTRO_PERSONAL_TOKEN="your-secret-token"

# Run the API
python -m maestro_personal_shell.api
# → http://localhost:8766/api/health

# Run tests
cd maestro-personal && python -m pytest tests/ -q
```

## Auth

- **Dev mode** (default): shared bootstrap token from `MAESTRO_PERSONAL_TOKEN` env var
- **Production mode** (`MAESTRO_PERSONAL_ENV=production`): bootstrap disabled; per-user tokens only
- `POST /api/auth/login` with password → returns bearer token
- `POST /api/auth/revoke` — revokes all tokens for the caller
- `POST /api/auth/rotate` — issues new token, revokes old ones
- Tokens stored as SHA-256 hashes (not plaintext)
- 30-day TTL on all tokens

## LLM Integration

### Provider Priority (automatic — tries in order)

1. **ZAI HTTP Router** (if `/etc/.z-ai-config` or `~/.z-ai-config` exists) — Python-native, no Node.js needed. Calls the ZAI GLM API via httpx. Rate-limited to 30 req/10min. When rate-limited, automatically falls through to Ollama.
2. **ZAI CLI** (if `z-ai` is on PATH) — requires `npm install -g z-ai-web-dev-sdk`.
3. **Cloud providers** (if `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `OPENROUTER_API_KEY` / `XAI_API_KEY` is set) — production deployments.
4. **Local Ollama** (if running on `http://127.0.0.1:11434`) — offline / on-prem. No rate limits.

When no LLM is available: `llm_active: false`, `mode: "Rule-based (keyword fallback)"`.
All user text sanitized via `sanitize_for_llm()` before entering LLM prompts.
Homoglyph + leetspeak normalization + 60+ injection patterns.
Semantic injection check (LLM-based defense in depth).

### Setting up Ollama (reproducible — works on any machine)

```bash
# 1. Install Ollama (Linux)
curl -fsSL https://ollama.com/install.sh | sh

# 2. Start the Ollama server
ollama serve &

# 3. Pull a small model (qwen2.5:0.5b = 397MB, runs on CPU)
ollama pull qwen2.5:0.5b

# 4. Set env vars + start the backend
export OLLAMA_HOST=http://127.0.0.1:11434
export OLLAMA_MODEL=qwen2.5:0.5b
cd maestro-personal
PYTHONPATH=src python -m maestro_personal_shell.api

# 5. Verify LLM is active
curl -s http://localhost:8766/api/llm-status | python -m json.tool
# Expected: {"active": true, "provider": "ollama", ...}
```

For larger models (better quality, needs GPU):
```bash
ollama pull llama3:8b    # 4.7GB, needs 8GB+ RAM or GPU
ollama pull qwen2.5:7b   # 4.7GB, good quality/size ratio
```

### Running the Ablation Benchmark

```bash
# With LLM active (Ollama or ZAI):
cd maestro-personal
PYTHONPATH=src python ../scripts/run_ablation_benchmark.py

# Or via pytest (marked as llm_integration — skipped by default):
PYTHONPATH=src python -m pytest tests/test_ablation_benchmark.py -v -m "llm_integration"
```

The benchmark tests 30 questions across 5 categories (factual, entity-specific,
abstract, contradiction, temporal) and compares Full Maestro vs LLM-only.

## What this is NOT

- No mobile app (hosted web first)
- No live Gmail/Calendar/Slack OAuth (payload adapters only — manual signal entry)
- No enterprise SaaS features (no SAML, SCIM, RBAC, multi-tenant Postgres)
- No dilution (every Personal module imports Core, never reimplements)
