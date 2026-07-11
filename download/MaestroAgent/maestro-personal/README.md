# Maestro Personal

A FastAPI HTTP service that wraps the Cognitive Council Core (`maestro_cognitive_council`)
to provide a personal intelligence API on port 8766. SQLite persistence, FTS5 semantic
retrieval, bearer token auth, WebSocket live copilot, and 50+ REST endpoints across 6 surfaces.

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

- Cloud (OpenAI/Anthropic), local (Ollama), and rule-based fallback
- When no LLM is available: `llm_active: false`, `mode: "Rule-based"`
- All user text sanitized via `sanitize_for_llm()` before entering LLM prompts
- Homoglyph + leetspeak normalization + 60+ injection patterns
- Semantic injection check (LLM-based defense in depth)

## What this is NOT

- No mobile app (hosted web first)
- No live Gmail/Calendar/Slack OAuth (payload adapters only — manual signal entry)
- No enterprise SaaS features (no SAML, SCIM, RBAC, multi-tenant Postgres)
- No dilution (every Personal module imports Core, never reimplements)
