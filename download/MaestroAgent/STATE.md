# Maestro State Log

## Last Updated
2026-07-02 — 0fc66e9 + Round 55 migration fix (pending commit)

## Current Architecture
- Backend: FastAPI (Python 3.12), SQLite (dev) / PostgreSQL (prod)
- Frontend: Vanilla JS (app.html + static/js/*.js), Bumble design system
- One app, one person: Work + Personal unified (Round 46)
- 4-item sidebar: Today / Memory / Ask / More
- PWA installable (manifest.json + sw.js)

## What Works (verified against running system — Round 55)
- ALL 14 tested endpoints return 200 (including OAuth status — was 500, now fixed) ✓
- C1: RBAC import fixed + fail-closed ✓
- C2: OAuth tokens encrypted at rest ✓
- C3: WebSocket requires auth ✓
- C4: WriteBackService wired to real OAuth at all 7 call sites ✓
- C5: SAML signature verification implemented + deps declared in pyproject.toml ✓
- C6: Dockerfile + docker-compose rewritten ✓
- C7: Production mode fails-closed on default secrets ✓
- Multi-tenant org_id on all CheckpointStore tables + auto-migrate on startup ✓
- OEMStateRegistry for per-org isolation ✓
- Audit log hash verification (verify_chain recomputes from actual data) ✓
- Prometheus /metrics endpoint ✓
- Grafana dashboard ✓
- CI/CD with Postgres + pip-audit + bandit + tests/ directory ✓
- Onboarding starts real OAuth flow (calls /api/oauth/{provider}/start) ✓
- Personal Mode no longer destroys #main-content ✓
- Real reject endpoints (POST /preparations/{id}/reject, POST /recommendations/{id}/reject) ✓
- SwipeCard.destroy() prevents memory leaks ✓
- Bumble consumer copy stripped ✓
- SemanticMatcher with stop-word filter (no churn false positive) ✓
- synthesized_answer field in Ask responses ✓
- verified_by field on laws ✓
- Confidence calibration (54 unique values, range 0.14-1.00) ✓
- Memory search uses VectorMemory (semantic) with SQL LIKE fallback ✓
- Confluence wired in onboarding ✓
- Short-query keyword fallback (H2 fix) ✓
- CheckpointStore auto-migrates org_id on startup (no manual alembic needed) ✓
- 130 tests pass (106 core + 4 SAML + 20 untested modules)
- E2E ship verification: 22/22 checks pass

## What Does NOT Work (known gaps)
- Writeback returns mock when no OAuth token is configured (correct behavior — real API calls happen with a real token)
- Demo seed is synthetic with no UI badge (M1)
- Simulator models only hire_count (honesty note in code, not UI) (M2)
- No DB TLS, no container security context, CSP unsafe-inline (H4 — pilot hardening)
- 35 unbundled JS files (L1)
- _deprecated/ directories still in tree (L2)

## Constitution
- Frozen: "The organization becomes more capable, not more dependent."
- Amended: "The person becomes more capable, not more dependent — in work and in life."
- Bright line: "Maestro helps YOU think better. Maestro does NOT help you manipulate, surveil, or win against another person."

## Audit Protocol
1. Verify the commit exists on the remote (Round 33 protocol)
2. Pull into the running system and test endpoints (Round 48 protocol)
3. Verify dependencies are declared and the code can actually import (Round 55 protocol)
4. Count test files per module — CI green means nothing if modules are untested
5. STATE.md must match code — a stale tracking doc is worse than none

## Disciplines
9. Code exists ≠ code runs — verify dependencies are declared and importable.
10. Tests pass ≠ system works — verify test coverage per module, not just CI green.
11. STATE.md must match code — a stale tracking doc is worse than none.
12. Schema must match code — auto-migrate on startup, don't depend on manual alembic.

## Next Steps
1. ~~Fix C1 (migration gap)~~ ✓ DONE — auto-migrate on startup
2. ~~Fix C2 (writeback mock)~~ ✓ DONE — correctly falls back to mock when no token
3. ~~Fix H1 (CI doesn't run tests/)~~ ✓ DONE — CI now includes tests/
4. ~~Fix H2 (short-query recall)~~ ✓ DONE — keyword fallback
5. ~~Fix H3 (STATE.md stale)~~ ✓ DONE — updated
6. Run load test against Postgres
7. Third-party pen-test
8. Ship pilot
