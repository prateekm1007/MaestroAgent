# api.py Split Plan — Phase 8 Engineering Quality

**Goal:** Split the 5,300-line `api.py` god-module into domain-focused routers, each under ~800 lines. No behavior changes — pure file extraction.

**Current state:** `maestro-personal/src/maestro_personal_shell/api.py` is 5,300+ lines containing auth, signals, ask, commitments, copilot, graph, admin, observability, metrics, briefing, the-moment, ingest, devices, and push. This makes changes risky and review hard.

## Target structure

```
maestro_personal_shell/
├── api.py                    # ~200 lines: app construction, lifespan, CORS, mount routers
├── routers/
│   ├── __init__.py
│   ├── auth.py               # ~300 lines: login, revoke, rotate, verify_token, _hash_token, _create_user_token
│   ├── signals.py            # ~400 lines: create_signal, get_signals, correct_signal, ingest_slack, ingest_transcript
│   ├── ask.py                # ~500 lines: ask, ask_stream, ask_ranker integration
│   ├── commitments.py        # ~400 lines: commitments, the-one, ledger, transition, simulate
│   ├── surfaces.py           # ~300 lines: what-changed, the-shifts, prepare, whisper, the-moment, briefing
│   ├── copilot.py            # ~300 lines: transcript, post-call, talk-ratio, negotiation, ws
│   ├── graph.py              # ~200 lines: entity graph, risk graph, behavior patterns, agents
│   ├── learning.py           # ~200 lines: predictions, outcomes, calibration, calibration_history
│   ├── account.py            # ~200 lines: delete, export, devices, push
│   ├── observability.py      # ~200 lines: trace, traces, whisper-decisions, metrics, depth
│   └── admin.py              # ~100 lines: health, llm-status, privacy/mode, audit-log
└── _shared.py                # ~200 lines: build_shell, build_shell_async, load_signals_from_db, save_signal_to_db, _filter_* helpers, _compute_commitment_confidence
```

## Extraction order (lowest risk first)

| Step | What | Risk | Why this order |
|------|------|------|----------------|
| 1 | `_shared.py` (helpers) | Low | Pure functions, no routes. Other files import from here. |
| 2 | `routers/admin.py` (health, llm-status) | Low | 2 endpoints, no state, no shared deps. |
| 3 | `routers/auth.py` (login, revoke, rotate) | Medium | Token store is shared, but the functions are self-contained. |
| 4 | `routers/observability.py` | Low | Read-only endpoints, no mutations. |
| 5 | `routers/account.py` (delete, export) | Medium | Touches many tables but well-scoped. |
| 6 | `routers/graph.py` | Low | Read-only + PersonalGraph wrapper. |
| 7 | `routers/learning.py` | Low | Predictions/outcomes/calibration. |
| 8 | `routers/copilot.py` | Medium | WebSocket + REST. Most complex extraction. |
| 9 | `routers/commitments.py` | Medium | Shared filters with surfaces. |
| 10 | `routers/surfaces.py` | Medium | The masterpiece endpoints. |
| 11 | `routers/ask.py` | Medium | LLM bridge + ranker. |
| 12 | `routers/signals.py` | Low | CRUD + ingest. |

## Mechanism

FastAPI supports `APIRouter` for modular route definitions:

```python
# routers/auth.py
from fastapi import APIRouter, HTTPException, Depends, Header
router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/login")
async def login(req: LoginRequest):
    ...

# api.py
from .routers import auth, signals, ask, ...
app = FastAPI(...)
app.include_router(auth.router)
app.include_router(signals.router)
...
```

## First extract: `routers/admin.py` (Step 2)

This is the lowest-risk extract — 2 endpoints, no state, no shared deps. Once this lands, the pattern is proven and the remaining extracts are mechanical.

## What this is NOT

- Not a rewrite — every route keeps its exact path, method, request/response schema, and behavior
- Not a refactor of the helpers — `_filter_corrected_signals`, `build_shell`, etc. move to `_shared.py` verbatim
- Not a behavior change — the test suite must stay 100% green after each step

## Exit criteria (Phase 8)

- [ ] `api.py` ≤ 800 lines (just app construction + router mounts)
- [ ] Every router file ≤ 800 lines
- [ ] `pytest tests/ -q` still passes with 0 new failures
- [ ] No `except Exception: pass` on security/audit/auth paths (grep-verified)
- [ ] Mutation kill rate ≥ 90% on critical modules
