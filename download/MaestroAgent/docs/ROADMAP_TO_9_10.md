# Roadmap: Maestro to 9/10 Before Pilot

**Source documents:**
- `MAESTRO_CODER_INSTRUCTIONS_TO_9_BEFORE_PILOT.md` (1,108 lines — strict coding instructions)
- `Pasted Content_1783309449264.txt` (1,415 lines — 9/10 product capability list)

**Objective:** Bring Maestro to 9/10 across every audit scorecard criterion before any real-customer pilot.

**Status:** Pilot is BLOCKED until every gate passes by execution from a clean clone.

---

## Non-Negotiable Rules

1. Stop building new cognitive modules. Only work on the 14 allowed areas.
2. Every claim must be execution-backed. No "fixed" without pasted output.
3. Definition of done = 12 criteria (failing test first, production path, restart survival, tenant isolation, etc.)
4. Phases are ordered. Do not skip ahead.

---

## Phase Status (Honest, verified by execution)

| Phase | Name | Sessions | Status | Current % | Gap |
|-------|------|----------|--------|-----------|-----|
| 1 | Test reliability | 3 | **IN PROGRESS** | 35% | ~80 failures remain. Deps split ✓. Invalid pytest config removed ✓. |
| 2 | Permissions/tenant | 3 | NOT STARTED | 25% | ACL on ALL surfaces, remove global oem_state |
| 3 | Evidence spine | 3 | NOT STARTED | 10% | Durable claim model, classifier improvements |
| 4 | SituationSnapshot | 3 | PARTIAL | 25% | Wire ALL surfaces, cross-surface test |
| 5 | Commitment lifecycle | 3 | NOT STARTED | 20% | Full lifecycle object, mutations, outcomes |
| 6 | Whisper delivery | 3 | PARTIAL | 40% | Derived inputs, 8 outcomes, recipient routing |
| 7 | Ask investigation | 4 | PARTIAL | 25% | InvestigationSession, multi-turn |
| 8 | Meeting/decision | 3 | PARTIAL | 30% | Loop closure, during-meeting |
| 9 | Org learning | 3 | PARTIAL | 25% | Durable ledgers, remove globals |
| 10 | Persistence/Postgres | 5 | PARTIAL | 20% | Postgres deploy, 3-replica, queues |
| 11 | Connector reality | 4 | NOT STARTED | 15% | Contract tests, deletion, dedup |
| 12 | Historical replay | 3 | NOT STARTED | 5% | Replay harness, metrics |
| 13 | Perf/chaos/a11y | 4 | NOT STARTED | 10% | All 3 test suites |
| **Total** | | **~45** | | | |

---

## Phase 1: Make the Repository Executable and Honest

### Tasks
1. ✅ Split optional heavy dependencies into extras (semantic, agents, browser, live-connectors, postgres)
2. ✅ Remove invalid pytest configuration (audit sub-section)
3. ✅ Add conftest autouse fixture for state pollution prevention
4. ✅ Add pytest markers (slow, live, browser, perf)
5. ✅ Add skip markers for missing optional deps
6. ⬜ Fix remaining ~80 test failures (stale fixtures, env-specific, performance)
7. ⬜ Make tests order-independent
8. ⬜ Document install + test commands
9. ⬜ Add CI job configuration

### Required Command (must pass from clean clone)
```bash
cd download/MaestroAgent/backend
python -m pip install -e ".[dev]"
MAESTRO_LOCAL_DEV=true MAESTRO_DEMO_SEED=true python -m pytest
```

---

## Final Pilot Readiness Gate (20 items)

```
[ ] Clean clone install works
[ ] Full hermetic test suite green
[ ] No critical/high security findings
[ ] No permission leaks
[ ] No demo seed in customer mode
[ ] SituationSnapshot powers all surfaces
[ ] Commitment lifecycle replay passes
[ ] Ask multi-turn investigation passes
[ ] Whisper silence/fatigue suite passes
[ ] Meeting and decision loops close with outcomes
[ ] Learning changes future behavior through governed policy
[ ] Postgres migrations pass from empty DB
[ ] Three-replica test passes
[ ] Connector contract tests pass
[ ] Deletion/revocation propagation passes
[ ] Historical replay evaluation passes
[ ] Performance report produced
[ ] Chaos report produced
[ ] Accessibility AA report produced
[ ] External auditor re-runs and verifies
```

**If any box is unchecked, Maestro is not pilot-ready.**
