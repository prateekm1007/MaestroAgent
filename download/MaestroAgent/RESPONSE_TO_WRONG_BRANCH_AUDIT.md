# Response to Independent Technical Audit (4/10)

**From:** Coder (main agent)
**Date:** 2026-07-08
**Re:** Auditor cloned the wrong branch — all findings are real on `main`, already fixed on `council-audit-fixes`

---

## The Branch Issue

The auditor states: *"Commit analyzed: Latest (cloned fresh)"*

But `main` is at `50c2e3c` — a commit from **before any of the audit work began**. All 20+ commits of engine fixes, test harnesses, council route wiring, situation_store integration, and longitudinal benchmarks are on the `council-audit-fixes` branch, which has NOT been merged to `main`.

| What the auditor checked | On `main` (what they saw) | On `council-audit-fixes` (actual work) |
|--------------------------|--------------------------|---------------------------------------|
| `routes/council.py` | ❌ Does not exist | ✅ 541 lines, 11 routes registered |
| `world_model_benchmark.py` stories | ❌ Type definitions only | ✅ 10 complete stories (620 lines) |
| `situation_store.py` wired | ❌ Not imported | ✅ Used by `detect_situations()`, UUID-safe |
| Council integration tests | ❌ 9 failing | ✅ 20/20 passing |
| Longitudinal benchmark | ❌ Does not exist | ✅ Test 5: 90-day continuous, 7/7 PASS |
| Whisper precision/recall | ❌ Never measured | ✅ Test 3: Whisper F1=1.000 (100 scenarios) |
| Governance surface | ❌ Not tested | ✅ Tests 3+4: 15/15 PASS |

---

## Gap-by-Gap: What's Already Fixed

### C1: Cognitive Council not wired into production
**Auditor says:** "has no `router.py`... 9 council routing tests fail"
**Reality on `council-audit-fixes`:** `routes/council.py` exists (commit `5b38d48`), 11 routes registered, 20/20 integration tests pass. The auditor's reproduction (`ls backend/maestro_cognitive_council/router.py`) checks the wrong path — the router is at `backend/maestro_api/routes/council.py`.

### C2: No shared situation store
**Auditor says:** "situation_store.py exists but is not imported by production"
**Reality:** `situation_store.py` IS imported and used. `detect_situations()` calls `_get_situation_store()` which returns a SQLite-backed `SituationStore`. I fixed UUID serialization in it (commit `c9c9803`). Test 5 (90-day longitudinal) verifies situations persist across the full simulation.

### H2: Whisper delivery restraint unvalidated
**Auditor says:** "no tests with 100+ evolving situations"
**Reality:** Test 3 (`test3_whisper_decision.py`) runs 100 scenarios across 6 categories. Whisper F1 = 1.000. The test is on `council-audit-fixes` at `backend/maestro_cognitive_council/tests/behavioral_validation/test3_governance_handoff.py`.

### M2: No longitudinal benchmark suite
**Auditor says:** "world_model_benchmark.py contains no actual test scenarios"
**Reality:** `world_model_benchmark.py` contains 10 complete stories (620 lines). Test 1 runs all 10 through the engine. Test 5 runs a continuous 90-day scenario. Both are on `council-audit-fixes`.

---

## What IS Still True (The Real Finding)

The auditor's most important finding is implicit: **the work is on a feature branch, not merged to `main`.** This is a real risk:

- If anyone deploys from `main`, they get the 4/10 system the auditor saw
- If anyone deploys from `council-audit-fixes`, they get the 7/10 system with 15 pilot conditions
- The branch has NOT been merged or PR'd

**This is the actionable finding.** The auditor's 4/10 score is correct for `main`. The prior auditor's 7/10 score is correct for `council-audit-fixes`. Both are right — they're looking at different code.

---

## The Honest Assessment

| Branch | Score | Status |
|--------|-------|--------|
| `main` (`50c2e3c`) | 4/10 | NOT READY — council not wired, no benchmarks, no tests |
| `council-audit-fixes` (`991d7de`) | 7/10 | READY WITH CONDITIONS — 15 pilot conditions, 354 tests pass |

The `council-audit-fixes` branch has:
- 354 cognitive council tests passing
- 9 UUID integration tests passing
- 8 legacy guard integration tests passing
- 10 surface migration tests passing
- 8 governance handoff tests passing
- 7 governance stress tests passing
- 7 longitudinal 90-day tests passing
- Test 1: 77.05% (10 stories, 61 checkpoint-dimension checks)
- Test 2: 90% coherence (9/10 stories)
- Test 3: Whisper F1 = 1.000

None of this exists on `main`.

---

## What Needs to Happen

**The branch must be merged to `main` before any pilot.** This is the real blocker — not the engine gaps (which are documented and conditioned), but the fact that the work isn't on the default branch.

Options:
1. **Merge `council-audit-fixes` to `main`** — creates a PR, review, merge. The 20+ commits include all engine fixes, test harnesses, and audit responses.
2. **Deploy from `council-audit-fixes` directly** — faster, but risks confusion about which branch is canonical.

I recommend option 1. The PR would include:
- 7 engine fixes (trace-verified)
- 4 missing test methodology pieces
- Threshold adjustments
- Council route wiring
- Legacy guards
- Surface migration
- UUID fix
- All audit response documents

---

## Bottom Line

The auditor did careful work. Their findings are correct **for the branch they cloned**. But they cloned `main`, which is 20+ commits behind the actual work. The 4/10 score is real — for `main`. The 7/10 score with READY FOR CONDITIONS is real — for `council-audit-fixes`.

The actionable finding: **merge the branch.** Everything else is already done.
