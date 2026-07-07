# CRITICAL-1 Design Doc: oem.py God File Refactor

**Finding:** `backend/maestro_api/routes/oem.py` — 7,003 lines, 204 `@router` decorators, 233+ functions. Single file contains ALL OEM API endpoints. Impossible to audit comprehensively.

**Severity:** CRITICAL (maintainability / audit risk)

**Status:** Design doc — implementation is a multi-session sprint.

---

## Current State

```
backend/maestro_api/routes/oem.py
  7,003 lines
  204 @router decorators
  233+ functions (including helpers)
  ALL OEM endpoints in one file:
    - Whisper (7 endpoints)
    - Ask (3 endpoints)
    - CEO Briefing (1 endpoint)
    - Timeline (3 endpoints)
    - Laws (5 endpoints)
    - Learning Objects (4 endpoints)
    - Loops 1-4 (20+ endpoints)
    - Connectors/Imports (8 endpoints)
    - OAuth (5 endpoints)
    - Dashboard/Tasks (6 endpoints)
    - Background loop (1 endpoint)
    - Trajectory intervention (2 endpoints)
    - Preparation (3 endpoints)
    - Intentions/Assumptions/Hypotheses (8 endpoints)
    - Predictions (4 endpoints)
    - Contradictions (3 endpoints)
    - And 100+ more
```

## Problem

1. **Unauditable:** No human can review 7,003 lines in one sitting. Bugs hide in the noise.
2. **Merge conflicts:** Any two developers working on different endpoints conflict on the same file.
3. **Import coupling:** All endpoints share the same import block. Adding a dependency for one endpoint pulls it into all.
4. **Test isolation:** Tests import from `oem.py` — changing one endpoint's helper can break tests for unrelated endpoints.
5. **Cognitive load:** New developers must read the entire file to understand where to add a new endpoint.

## Proposed Split

Split into domain-specific route modules under `backend/maestro_api/routes/`:

```
backend/maestro_api/routes/
  oem.py              → slimmed to shared helpers + router registration
  whisper_routes.py   → /whisper, /whisper/outcome, /whisper/outcomes, /loop1/whispers
  ask_routes.py       → /ask, /ask/conversation
  briefing_routes.py  → /ceo-briefing, /dashboard, /tasks
  timeline_routes.py  → /timeline, /loop1.5/timeline/{entity}
  law_routes.py       → /laws, /laws/{code}, /laws/{code}/verify
  learning_routes.py  → /learning-objects, /loop1/learning, /loop4/*
  loop2_routes.py     → /loop2/* (meeting intelligence)
  loop3_routes.py     → /loop3/* (decision intelligence)
  connector_routes.py → /imports/*, /oauth/*, /connections/*
  prediction_routes.py → /predictions, /predictions/*
  contradiction_routes.py → /contradictions, /contradictions/*
  intent_routes.py    → /intents, /assumptions, /hypotheses
  trajectory_routes.py → /trajectory-intervention, /org-pattern
  background_routes.py → /background-loop, /nudges, /evolution-tracker
```

Each module:
- Defines its own `router = APIRouter()`
- Imports shared helpers from `oem.py` (or a new `helpers.py`)
- Is registered in `oem.py` via `router.include_router(whisper_routes.router, prefix="/api/oem")`

## Migration Strategy

**Phase 1 (1 session):** Extract the smallest, most self-contained route group (e.g., trajectory_routes.py — 2 endpoints, minimal helper dependencies). Verify all tests still pass. Establish the pattern.

**Phase 2 (5-8 sessions):** Extract remaining route groups one at a time. Each extraction is a separate commit. After each extraction:
- Run full test suite
- Verify no import cycles
- Verify no missing helpers
- Verify route registration is correct

**Phase 3 (1 session):** Final cleanup — move shared helpers to `helpers.py`, remove dead imports from `oem.py`, update `oem.py` to be slim (just router registration + shared state).

## Risks

1. **Import cycles:** Route modules may need helpers from `oem.py` which needs the routers. Mitigation: use late imports or move helpers to a separate module.
2. **Shared state:** `oem_state` singleton, `_assumption_graph`, `_hypothesis_store` are module-level in `oem.py`. Mitigation: keep them in `oem.py` and import from there.
3. **Test breakage:** Tests that import from `oem.py` may break if endpoints move. Mitigation: keep the `router` object in `oem.py` and include sub-routers — tests can still import from `oem.py`.
4. **Route ordering:** FastAPI matches routes in registration order. If a generic route (`/whisper`) is registered before a specific one (`/whisper/outcome`), the generic may shadow the specific. Mitigation: register specific routes first.

## Success Criteria

- [ ] `oem.py` is under 1,000 lines (just router registration + shared state)
- [ ] Each route module is under 500 lines
- [ ] All 1,375+ tests pass after each extraction
- [ ] No import cycles
- [ ] No route registration errors
- [ ] `grep -rn "@router\." backend/maestro_api/routes/` shows routes distributed across modules

## What This Does NOT Fix

- The `oem_state` singleton (that's HIGH-3)
- The 6,987 lines of logic in the helper functions (those need their own refactoring)
- The test suite's test-pollution issues (pre-existing, separate work)

## Estimated Effort

- Phase 1: 1 session (proof-of-concept)
- Phase 2: 5-8 sessions (one per route group)
- Phase 3: 1 session (cleanup)
- **Total: 7-10 sessions**
