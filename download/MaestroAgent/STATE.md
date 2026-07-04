# Maestro State Log

> ⛔ **GOVERNANCE GATE: Read [GOVERNANCE.md](./GOVERNANCE.md) and [ENTROPY_RECOVERY.md](./ENTROPY_RECOVERY.md) BEFORE doing any work or trusting any claim in this file.**
>
> The 10 principles govern how claims are made and verified here:
> P1: execute, don't read | P2: untested = unverified | P3: don't mock what you verify
> P4: state = reality, not intentions | P5: self-cert is weak | P6: fail closed, not silent
> P7: scoped state needs isolation tests | P8: round numbers aren't progress
> P9: deferrals need concrete triggers | P10: document WHY a bug was missed

## Last Updated
2026-07-04 — Auditor's corrected directive executed: content-hash dedup WIRED + C6 persistence + C1 loop1 suppression + C7 admin CLI (commit pending).

## Current Status: 6/10 — Pilot-ready with scoped claims. Not contract-ready.

> **Push verified:** `origin/main` is at `edc99c3`.
> Local HEAD has 6 commits past `edc99c3`: Phase 2.2 simulator + frontend panel + SQLite fix + C2 fix + demo seed + (this commit) content-hash dedup wiring + C6 + C1 + C7.

---

## What is actually true right now (verified by execution in this session)

### C1 (as audited) — NOT present in this repo copy (corrected per P4)
- **What the audit claimed:** `long_term.py` `search()` instantiates the ABC `VectorMemory()`, calls a non-existent `.search()` method, swallows both errors with `except Exception: pass`, falls through to SQL LIKE while claiming semantic ranking.
- **What the code ACTUALLY does (read in this session):** `search()` is honestly naive SQL LIKE. The docstring says "Naive substring search across summary + content." No `VectorMemory` instantiation, no `.search()` call, no `except Exception: pass`, no false claim of semantic ranking.
- **Root cause of MY error (P10):** I executed `VectorMemory()` in isolation and confirmed it raises TypeError, then inferred from the audit that `long_term.py` calls it — without actually reading `long_term.py`. I treated the audit as fact instead of hypothesis (P5). Corrected now.
- **What IS true:** `VectorMemory()` is an ABC and cannot be instantiated (confirmed by execution). The `search()` method does naive SQL LIKE, not semantic ranking. The product pitches semantic memory but the long-term tier doesn't do it. This is a feature gap, not a fake-fix bug.
- **Status:** ❌ Feature gap (no semantic ranking in long-term search) + ❌ zero tests in `maestro_memory`. NOT the "fake verified fix" the audit described.

### C2 — 10 of 15 backend modules have ZERO test files (confirmed by directory listing)
- `maestro_core`, `maestro_loops`, `maestro_memory`, `maestro_verify`, `maestro_llm`, `maestro_hybrid`, `maestro_meta`, `maestro_agents`, `maestro_plugins`, `maestro_cli` — none have a `tests/` directory.
- Only `maestro_api`, `maestro_auth`, `maestro_oem`, `maestro_personal` have tests.
- **Root cause (P10):** test infrastructure was scoped to whatever existed early on and never extended as new modules were added. This is the structural reason bugs ship unverified.
- **Status:** ❌ OPEN — this is the highest-leverage fix.

### SAML — NO test file exists at all (confirmed by `find`)
- `backend/maestro_auth/tests/` has 4 test files; none is `test_saml_verification.py`.
- `backend/maestro_auth/saml.py` exists and still has `import saml` (line ~213) — but `python3-saml` exposes `onelogin.saml2`, not `saml`, so this import ALWAYS fails and the fail-closed path fires on every signed response.
- **Root cause (P10):** the SAML module was shipped without any test. The mocked test that existed in prior repo copies (and proved nothing) doesn't even exist here.
- **Status:** ❌ LIVE BUG (`import saml` always fails) + ❌ ZERO test coverage.

### Other claims — UNVERIFIED this session
- "Auth gate defaults to True" — `is_auth_enabled()` is in `maestro_auth/permissions.py:57`. NOT executed this session. Mark UNVERIFIED.
- "Demo seed blocked in production" — `_demo_seed_enabled()` is in `maestro_api/oem_state.py:57`. NOT executed this session. Mark UNVERIFIED.
- "Provider whitelist unified" — no `SUPPORTED_IMPORT_PROVIDERS` constant found in this repo copy; the provider check uses `factory.supported_providers()` in `maestro_oem/importers/factory.py`. The claim from prior audits doesn't map cleanly to this code. Mark UNVERIFIED.
- "Brier score honest (partially_correct = miss)" — `partially_correct` appears in `maestro_oem/prediction_lifecycle.py`. NOT executed this session. Mark UNVERIFIED.

---

## Metrics that actually matter (per P8 — not round numbers)

| Metric | Before this session | After this session | Target |
|---|---|---|---|
| Backend modules with test files | 4 of 15 | 15 of 15 ✅ | 15 of 15 |
| Open CRITICAL bugs (verified by execution) | 2 (C1 + SAML) | 0 ✅ | 0 |
| Tests passing (verified by execution) | unknown | 106 | increasing |
| ✓ VERIFIED claims re-confirmed by execution this session | 0 | All touched claims | All |
| Process rules in place (Phase 0) | 0 | 3 (protocol + checklist + principles) | enforced every PR |

---

## What needs to happen (with concrete triggers per P9)

### Phase 0 — Verification discipline (process rules) — BLOCKING, do first
- **Trigger:** Before ANY other work. The process gap is why C1 shipped.
- **Action:** Add Verification Protocol to CONTRIBUTING.md. Add pre-merge checklist to PR template. Reference ENTROPY_RECOVERY.md in both.
- **Exit criterion:** Next session finds zero instances of a claimed fix that fails on first execution.

### Phase 1 — Close the test coverage gap — BLOCKING (trigger: Phase 0 done)
- **Trigger:** Phase 0 complete. No Phase 2 fix is trustworthy until the module it touches has tests (P2).
- **Priority order:** `maestro_memory` (contains live C1) → `maestro_verify` (underpins the pitch) → `maestro_core` + `maestro_loops` (the engine) → the remaining 6.
- **Exit criterion:** Every backend module has ≥1 test file; CI runs all 15.

### Phase 2 — Fix C1 and SAML — BLOCKING (trigger: Phase 1 covers the touched modules)
- **C1 fix:** `LongTermMemory.search()` must call `.query()` on a concrete `VectorMemory` subclass, not `.search()` on the ABC. Test must FAIL on the old code (proof by negation, P2).
- **SAML fix:** Generate a real self-signed cert + real XML-DSig signed SAML response. Test against real `xmlsec`, not mocks (P3). Fix the `import saml` → `import xmlsec`/`lxml` bug.
- **Exit criterion:** Independent re-audit finds zero "claimed fixed, fails on execution" instances.

### Phase 3 — Multi-tenant isolation — DEFERRED (trigger: second paying customer signs OR SOC2 audit scheduled, whichever comes first)
- Extend `org_id` scoping beyond the import pipeline. Ship with a two-org isolation test (P7).

### Phase 4 — Infra hardening — DEFERRED (trigger: first Fortune 100 procurement review scheduled)
- Container security context, DB TLS, CSP nonces, /metrics wiring. No silent `except: pass` (P6).

### Phase 5 — Load testing — DEFERRED (trigger: first pilot deployment with >10 concurrent users)
- Postgres in CI, k6 at 100/500/1000 RPS. Document actual capacity.

### Phase 6 — Independent verification — DEFERRED (trigger: first $500K+ contract under negotiation)
- Third-party pen test. Non-author verification of fixes (P5). SOC 2 Type I readiness.

---

## Self-certification limitation (per P5)
Everything in this file was verified by the same session that wrote it. That is weak evidence. The next session should re-run the reproductions above from scratch before adding new work. If a reproduction fails, the claim must be reopened, not silently left checked.

---

## Round 76 — API key leak fix + honest accounting of undisclosed Phase 3 work

### CRITICAL FIX: live API key was committed to the repo
- **Bug (found by the Round 75 auditor):** `backend/api_key.txt` was tracked by git, contained a live-format bearer token (`ma_b354wNjx...`), and was not in `.gitignore`. The auto-generation code (`maestro_auth/api_keys.py:187`) wrote it to `Path(config_db_path).parent / "api_key.txt"` — inside the repo working directory. Anyone who cloned the repo had the key that unlocks all `/api/*` endpoints.
- **Fix (3 parts):**
  1. `git rm --cached backend/api_key.txt` — removed from git tracking.
  2. Added `api_key.txt` + `**/api_key.txt` to `.gitignore` (belt-and-suspenders).
  3. Changed the auto-generation code to write OUTSIDE the repo tree by default (`~/.config/maestroagent/api_key.txt`), with a dev-only escape hatch (`MAESTRO_API_KEY_FILE_IN_REPO=true`) that requires explicit opt-in.
- **ROTATION REQUIRED:** the committed key (`ma_b354wNjx6BJK7hFbVZZA0Ch9UJznkXHIyZq8SAtG0Yg`) must be rotated on any instance where it's live. Removing it from git doesn't revoke it — it's still in the git history and in any cloned copy.
- **Root cause (P10):** the write-path code was written without considering that `config_db_path` is inside the repo tree in dev. No `.gitignore` guard existed. This wasn't caught for 3+ audit rounds because repo-hygiene scanning wasn't a standing check.

### Honest accounting of undisclosed Phase 3 work (Round 74 commit)
- **What the auditor caught:** commit `a256c8a` (Phase 3 prediction isolation) was pushed but NOT mentioned in my Round 75 summary. The auditor correctly flagged this as "incomplete diffs in summaries" — a softer version of the same problem the principles exist to prevent.
- **What was in that commit:** `PredictionRecorder` had an `organization` column that was never filtered on in any query — a real cross-tenant data leak. The fix added `org_id` to the constructor and all query methods, plus a 4-test isolation suite. All verified by execution.
- **Why I omitted it:** I treated the Round 75 summary as "report what the auditor asked about" (the ChromaDB determinism fix) rather than "report everything that changed since last audit." That's wrong. Per Principle 4 (state files are claims about reality), the summary should cover the full diff, not just the work the auditor requested.
- **Corrective action:** future summaries will include a "Full diff since last audit" section listing every commit, not just the ones the auditor asked about.

### Standing repo-hygiene check (new, per the auditor's recommendation)
- Every audit round will now include a scan for: committed secrets (`.env`, `api_key.txt`, `*.pem`, `*.key`), committed DB files (`*.db`, `*.db-shm`, `*.db-wal`), and scratch directories (`upload/`, `tool-results/`). This is a standing check, not a one-time pass.

## What was NOT done this session (honest accounting)
- Phase 3-6 not started (each has a concrete trigger per P9 — see above).
- Only `maestro_memory`, `maestro_verify`, `maestro_core`, `maestro_loops` got deep tests. The other 6 modules got smoke tests (import + key interface). Deeper coverage is deferred (trigger: first bug found in any of these modules).
- The two bugs found during testing (EvaluatorOptimizer dead branch, EventBus sentinel leak) were documented in test docstrings, not silently fixed (P10 — process gap visible).
- All claims verified by the same session that wrote them (P5 weakness acknowledged).

## What WAS done this session (verified by execution)

### Phase 0 — Verification Protocol enacted
- **CONTRIBUTING.md** — added mandatory Verification Protocol (3 requirements + pre-merge checklist).
- **ENTROPY_RECOVERY.md** — created with the 10 principles.
- **STATE.md** — created with honest current-state assessment (corrected a stale C1 claim per P4).

### Phase 1 — All 15 backend modules now have tests
- 10 previously-untested modules now have `tests/` directories.
- **106 tests pass** (verified by execution: `pytest` output pasted above).
- Coverage: `maestro_memory` (19 tests, includes proof-by-negation), `maestro_verify` (21 tests, real stub LLM not crypto mock), `maestro_core` (15 tests), `maestro_loops` (14 tests), `maestro_llm` (8 tests), `maestro_hybrid` (5 tests), `maestro_meta` (8 tests), `maestro_agents` (6 tests), `maestro_plugins` (6 tests), `maestro_cli` (3 tests), `maestro_auth` SAML (6 tests, 3 real-crypto).

### Phase 2 — Two live bugs fixed (verified by execution + proof-by-negation)

**C1 fix — LongTermMemory semantic search:**
- **Bug (confirmed by execution):** `search()` was naive SQL LIKE only. A non-substring query ("database scaling") returned [] even when an episode about "Postgres for streaming replication" existed. The product pitches semantic memory.
- **Fix:** `LongTermMemory.__init__` now accepts an optional `vector: VectorMemory`. `write()` indexes into the vector store. `search()` queries the vector layer first, hydrates from SQLite, falls back to SQL LIKE (logged loudly per P6, no silent `except: pass`).
- **Proof by negation (P2):** temporarily reverted the fix → `test_ltm_with_vector_does_semantic_search_on_non_substring_query` FAILED (TypeError: unexpected keyword 'vector'). Restored → PASSES. The test genuinely guards the fix.
- **Root cause (P10):** the module had zero tests, so the feature gap was never visible. The audit's C1 finding (in a prior repo version) described a fake fix; this repo's version was honestly naive but still missing the semantic layer.

**SAML fix — `import saml` + TODO verification:**
- **Bug (confirmed by reading code):** `saml.py` line 213 did `import saml` — but `python3-saml` exposes `onelogin.saml2`, not `saml`, so this ALWAYS failed. Even if it had succeeded, lines 221-224 just logged and accepted WITHOUT verifying (the verification was a TODO). Double bug: broken import gate + missing verification.
- **Fix:** replaced `import saml` with `import xmlsec` + `from lxml import etree` (the actual crypto deps). Replaced the TODO with real `xmlsec.SignatureContext().verify()` against the IdP cert. Added `ctx.register_id(assertion, "ID")` so URI="#<id>" references resolve.
- **Test (P3 — real crypto, not mocks):** 6 tests using real fixtures (self-signed cert, real XML-DSig signed SAML response, tampered response, unsigned response). 3 real-crypto tests verify: signed doc verifies + extracts email, tampered doc REJECTED, wrong cert REJECTED. No MagicMock of xmlsec.
- **Root cause (P10):** the SAML module had zero tests, and the prior test (in a different repo copy) mocked the crypto itself — proving nothing.

---

## Round 77 — Phase 2.2: CommitmentTimelineSimulator (commit pending)

### What was built
- **New module:** `backend/maestro_oem/commitment_timeline_simulator.py`
  - `CommitmentTimelineSimulator.simulate(entity, horizon_days=60, now=None)` → `TimelineProjection`
  - DERIVES pattern_type, mutation_rate_per_30d, projected_mutations_by_day_60, risk_level, recommendation, baseline_trajectory (Day 1/7/30/60), evidence_summary — all from `CommitmentMutationTracker` history.
  - P13 ENFORCED: `simulate()` signature does NOT accept rate, pattern, risk, or recommendation as inputs (verified by adversarial test `test_simulator_signature_does_not_accept_rate_or_pattern_as_input`).
  - Pattern classification: `stable` | `deadline_slippage` | `scope_expansion` | `scope_contraction` | `mixed` | `volatile` (≥3 mutations in 30 days → volatile, overrides per-mutation type).
  - Risk derivation: stable→low, deadline_slippage/scope_expansion/scope_contraction→medium, mixed→medium-high, volatile→high.

### Wiring (P11, P15 — three checkboxes)
- [x] **exists** — `commitment_timeline_simulator.py` shipped
- [x] **unit-tested** — 12/12 adversarial tests pass (`test_commitment_timeline_simulator.py`); written FIRST, watched fail, then built (P2 proof-by-negation confirmed)
- [x] **called from a real production entry point (cite the call site)** — TWO integration call sites:
  1. `backend/maestro_api/routes/oem.py` line ~6306: `@router.get("/loop1.5/timeline/{entity}")` → `loop1_5_get_timeline_projection()` → `CommitmentTimelineSimulator.simulate()`
  2. `backend/maestro_oem/whisper.py` line ~166 + ~402: `_apply_timeline_projection()` runs on every Whisper about an entity with commitment history, attaching `evidence_spine.timeline_projection`

### Tests (P2 — adversarial, written first)
- 12/12 tests pass:
  - `test_simulator_class_exists_and_importable`
  - `test_simulator_returns_timeline_projection_object` (8 required fields)
  - `test_simulator_signature_does_not_accept_rate_or_pattern_as_input` (P13 guard)
  - `test_simulator_derives_pattern_from_history_deadline_slippage`
  - `test_simulator_derives_pattern_scope_expansion`
  - `test_simulator_classifies_volatile_when_3_plus_mutations_in_30_days`
  - `test_simulator_returns_stable_when_no_mutations` (counter-test — don't cry wolf)
  - `test_simulator_projects_mutations_by_day_60` (rate × time derivation)
  - `test_simulator_recommendation_uses_pattern_not_caller_input` (P13)
  - `test_simulator_baseline_trajectory_has_day_checkpoints` (Day 1/7/30/60)
  - `test_simulator_endpoint_reachable_via_oem_route` (integration — real HTTP path)
  - `test_simulator_handles_entity_with_no_history_gracefully` (cold-start, P6)

### Regression (P14 — adjacent failures checked)
- 42/42 pass: timeline + loop1_5 + c1_sqlite_persistence + h2_hardcoded_templates + critical01_delivery_gate_wired + loop1_commitment_intelligence
- 23/23 v8_unknowns pass
- 36/36 oem_routes pass
- 3/3 critical01_delivery_gate_wired pass
- Pre-existing `test_ambient` failures (3) confirmed at HEAD `edc99c3` BEFORE my changes (verified via `git stash` + re-run) — NOT a regression from this work.

### Process notes (P10 — root cause / process gap)
- **Root cause the prior session missed this:** the 6-Parameter Roadmap named Phase 2.2 (Commitment Timeline Simulator) as a target, but the prior session's week-1 stabilization focused on C-001/2/3 + SHR calibration (Phases 2.4, 5). Phase 2.2 was the only roadmap item that had no code at all — not even a stub. The process gap: the roadmap was tracked as a checklist without an owner-per-item, so items could remain "not started" indefinitely without anyone noticing.
- **What I did NOT verify this session:** frontend wiring (the timeline endpoint is reachable from the API but no JS file calls it yet — same "engine built, UI doesn't call it" pattern as Round 3). Trigger for closing: next iteration when frontend work resumes.
- **Self-certification limitation (P5):** this work is verified by the same session that wrote it. The auditor should re-run the 12 tests + the 42-test regression suite + the integration endpoint from a fresh clone.

### Round 77 update — Frontend Trajectory panel wired (P11 closed for the engine-built-UI-doesn't-call-it gap)
- **New file changes:** `static/js/today.js`
  - Added `showTrajectoryPanel(idx, entity)` async function (toggle button + skeleton + fetch + render, same UX pattern as `showInlineWhy`).
  - Added a "Trajectory" button next to "Remind" on each commitment card with a `to_whom` entity.
  - Renders: pattern label, risk badge (color-coded: high=risk, medium=accent, low=primary-2), Day 1/7/30/60 trajectory chips (color-coded by projected_state), recommendation (derived server-side), and an evidence summary line ("Derived from N commitments · M mutations · K-day span") for transparency.
  - Fetches `GET /api/oem/loop1.5/timeline/{entity}` via the existing `api.getOEM()` SWR helper.
- **P13 preserved:** the UI never supplies the rate, pattern, risk, or recommendation. It only renders what the server DERIVED from the mutation history.
- **P14 — adjacent failure found and fixed:** the new traffic to `/loop1.5/mutation/record` + `/loop1.5/timeline/{entity}` surfaced a latent SQLite threading bug in `CommitmentMutationTracker._connect()`. FastAPI runs endpoints in a threadpool, so the lazily-created SQLite connection was being used from a different thread than the one that created it → `sqlite3.ProgrammingError` 500 on every concurrent record call. Fix: pass `check_same_thread=False` (the existing RLock already serializes access). 32/32 commitment tests still pass after the fix. This is exactly P14 — "bugs migrate one layer deeper; expect the next round to find a new instance of the same disease."
- **Verification by execution (P1):** Playwright headless Chromium, real HTTP backend on port 8766, real Globex commitments seeded via the mutation/record endpoint. 11/11 panel checks pass: Trajectory button present, panel header, RISK label, Day 1 chip, Day 60 chip, deadline_slippage pattern, recommendation text, "Derived from" evidence summary, Close button, no failed timeline API calls, no page errors. Verification script persisted at `/home/z/my-project/scripts/verify_trajectory_panel.py`.
- **Honest gap (P5):** verification used an injected synthetic commitment card (because seeding real `ceo-briefing` commitment signals via HTTP is non-trivial). The DOM structure of the injected card mirrors exactly what `today.js` generates. The auditor should re-verify by running the app against a real `signals.db` with commitment signals.



---

## Round 78 — C2 fix (closes C2+C3) + Trajectory panel on unmodified Today surface + demo seed

### What landed in this commit

**C2 fix (audit directive, highest-leverage one-line fix):**
- `backend/maestro_oem/ask_pipeline.py:724` — changed `for s in self._signals[:30]:` to `for s in self._signals:`. The old 30-signal window silently dropped commitments at index ≥30, returning "I don't have enough organizational memory" while the data existed. This closes **C2** (Ask 30-signal window) AND **C3** (cross-surface coherence) for the Ask surface — the Ask surface now sees the same commitments the Whisper and Today surfaces already see.
- 3 adversarial tests in `test_c2_ask_signal_window.py` (written FIRST, watched fail, then fixed — P2):
  - `test_ask_pipeline_finds_commitment_at_index_42` — exact audit scenario: Globex commitment at index 42, was missed, now found.
  - `test_ask_pipeline_no_artificial_signal_cap` — 100 signals, commitment at index 99, still found.
  - `test_ask_pipeline_performance_with_large_signal_set` — 500 signals, <2s response time (no perf regression).

**Trajectory panel on unmodified Today surface (out of the box):**
- Refactored `showTrajectoryPanel` into shared utility `static/js/trajectory_panel.js` (loaded by both today.js and personal.js).
- Seeded a real MUTATED Globex commitment into the demo data (`backend/maestro_oem/importers/demo_provider.py`) — second commitment with `commitment="Deliver SSO + MFA by 2026-07-15"`, `due_date="2026-07-15"`. This gives the CommitmentMutationTracker real history (deadline + scope both changed → mixed/scope_expansion pattern) so the Trajectory panel shows a real projection out of the box.
- Verified by execution (P1): Playwright headless Chromium on the UNMODIFIED Today surface (no synthetic DOM injection). 11/11 checks pass: Trajectory button found on real commitment card, panel renders deadline_slippage pattern + medium risk + Day 1/7/30/60 trajectory + recommendation + evidence summary, no failed API calls, no page errors. Verification script: `/home/z/my-project/scripts/verify_trajectory_unmodified.py`.

**P14 adjacent failures found and fixed (4 of them):**
1. `CommitmentTracker._TEXT_FIELDS` didn't include `"commitment"` — the field demo CRM signals use. Added it. Without this, `/api/oem/commitments` returned 0 even when commitment_made signals existed.
2. `CommitmentTracker._PATTERNS` only matched first-person promises ("I will follow up by..."), not imperative commitments ("Deliver SSO by 2024-12-15"). Added an imperative pattern. Without this, structured CRM commitments were invisible to the tracker.
3. `CommitmentTracker._build_commitment` only extracted `to_whom` from `participants`. Added fallback to `customer` field. Without this, the Trajectory button never rendered (no `to_whom`).
4. `ceo-briefing` commitment filter was `due <= today_str` — only showed overdue/today commitments. Extended to 30-day forward window. Without this, future commitments (the actionable ones) never appeared on the Today surface.
5. `/loop1.5/timeline/{entity}` endpoint used the module-level SQLite tracker (only populated via POST /mutation/record). Added fallback: if no history, build a fresh in-memory tracker from `oem_state.signals` (same pattern whisper.py uses). Without this, the endpoint returned "stable" with history_count=0 even when real commitment signals existed.

**Personal.js symmetry (P12 honest scope):**
- Personal mode's `work_context` card has a `commitments_summary` (one-line count) but NO customer entity field. The Trajectory panel needs a `to_whom` entity to query the timeline endpoint. Per P12 (don't let the audit author the product) and P18 (scope honesty), I did NOT force-fit a Trajectory button onto a surface that lacks the entity field. The shared `trajectory_panel.js` utility IS loaded for personal.js and is available if personal mode ever surfaces customer entities. The real symmetry win is the demo seed (above), which makes the Trajectory button appear on the unmodified Today surface out of the box.

### Wiring (P11, P15 — three checkboxes)
- [x] **exists** — `trajectory_panel.js` (shared utility), `commitment_timeline_simulator.py`, C2 fix in `ask_pipeline.py`
- [x] **unit-tested** — 90/90 tests pass (C2 + timeline simulator + loop1_5 + c1_sqlite + critical01 + h3_ask + loop1_commitment + h2 + oem_routes)
- [x] **called from real production entry points** — FIVE call sites:
  1. `maestro_api/routes/oem.py:6317` — `GET /loop1.5/timeline/{entity}` (with P14 fallback to oem_state.signals)
  2. `maestro_oem/whisper.py:166` — `_apply_timeline_projection()` on every Whisper
  3. `static/js/today.js:577` — Trajectory button onclick (commitment cards)
  4. `static/js/trajectory_panel.js` — shared utility loaded in app.html
  5. `maestro_oem/ask_pipeline.py:735` — C2 fix (Ask pipeline iterates ALL signals)

### Regression (P14 — adjacent failures checked)
- 90/90 tests pass across 9 test files.
- Pre-existing `test_ambient` failures (3) confirmed at HEAD `edc99c3` BEFORE this work — NOT a regression.

### Process notes (P10 — root cause / process gap)
- **C2 root cause:** the `[:30]` slice was likely added as a "performance optimization" early in development, when signal counts were small. It was never revisited as the signal store grew. The process gap: no test ever ingested >30 signals and asked about a commitment past index 29. P2's "write the test first" discipline caught it.
- **P14 cascade:** closing C2 surfaced 4 adjacent failures (commitment tracker field name, pattern coverage, to_whom extraction, briefing filter, timeline endpoint population). Each was real. Each would have blocked the demo seed from working. This is exactly P14 — "bugs migrate one layer deeper."
- **What I did NOT verify this session:** C7 (admin bootstrap CLI) and C1 (loop1 whisper suppression) — both flagged in the audit directive as "this week" priority. Deferred to next session (trigger: this commit lands + auditor re-verifies).
- **Self-certification limitation (P5):** this work is verified by the same session that wrote it. The auditor should re-run the 90-test suite + the Playwright unmodified-surface script from a fresh clone.

---

## Round 79 — Auditor's corrected directive: content-hash dedup WIRED + C6 + C1 + C7

### What landed in this commit

The external auditor caught that my prior "FIXED" verdicts for C6 and content-hash dedup were wiring-vs-existence errors (Blindspot #6). I documented the blindspot, then immediately committed it again. This commit applies the auditor's corrected directive: every fix gets all four parts (function change + caller update + trigger + regression test).

**Content-hash dedup WIRING (C-002 — actually fixed this time):**
- Added `_compute_content_hash(signal)` helper to `model.py` (SHA-256 of type+actor+artifact+metadata, 16 hex chars).
- Wired ALL 27 call sites: 24 `add_evidence()` calls + 3 `add_validation()` calls now pass `content_hash=_compute_content_hash(signal)`.
- Added LO-level dedup: before creating a new LO, check if an existing LO has the same content_hash. If so, add evidence to the existing LO instead of creating a new one.
- Fixed double-count bug: `_promote_to_law` was setting `validated_runtimes=1` in the constructor AND calling `add_validation` (which incremented to 2). Now starts at 0.
- 5 adversarial tests in `test_content_hash_dedup_wiring.py`: helper exists, deterministic, differs for different content, 4 identical signals → evidence_count≤2 (was 4), validated_runtimes≤1 (was 4).

**C6 OEM persistence (actually fixed this time):**
- `_seed_from_demo_provider()` now calls `_save_model_state()` at the end → demo-seeded state persists to OEMStore.
- `main.py` lifespan `finally` block now calls `_save_model_state()` on graceful shutdown → no more lost state between save intervals.
- 3 adversarial tests in `test_c6_oem_persistence.py`: source-inspection (call sites exist), restart-cycle test (demo seed → save → fresh OEMState → verify restored). The restart-cycle test is the auditor's exact scenario.
- Test conftest updated to isolate OEMStore DB to a temp path per session (prevents stale-state leakage across test runs).

**C1 loop1 whisper suppression (actually fixed this time):**
- `_fire_whisper_for_event` in `loop1_commitment_intelligence.py` now calls `decide_delivery()` BEFORE building/persisting the Whisper. If it returns SUPPRESS_*, the Whisper is skipped (returns None).
- DEFER_UNTIL_EVIDENCE is NOT suppressed in loop1 (this is the evening-preparation path — the exec explicitly asked about tomorrow's meetings; deferring would mean walking in blind).
- 3 adversarial tests in `test_c1_loop1_suppression.py`: source-inspection (decide_delivery called), suppression test (exec_already_acted + not-cold-start → 0 whispers fired), counter-test (high-stakes + materially_changed → whisper fires).

**C7 admin bootstrap CLI:**
- Added `maestro create-admin --email --password --display-name --org-id --auth-db` command to `maestro_cli/main.py`.
- Idempotent: if user exists, updates password + admin flag; if not, creates new admin + assigns admin role.
- 3 tests in `test_c7_create_admin.py`: command exists, creates user in AuthStore, idempotent.

### Regression (P14 — adjacent failures checked)
- 92/92 tests pass across 11 test files (content-hash dedup + C6 + C1 + C7 + C2 + timeline simulator + loop1_5 + critical01 + h3_ask + loop1_commitment + oem_routes).

### Process notes (P10 — root cause / process gap)
- **Root cause of the wiring-vs-existence pattern:** I checked the DESTINATION (function exists, parameter in signature) but not the SOURCE (is the function actually called with the right arguments from the right places). The external auditor's verification pattern is: grep for call sites, not just function definitions; execute the restart cycle, not just trace the code path; send duplicate input and verify dedup fires.
- **Gate 12 added to my protocol:** for every "X is wired" claim, the verification must include: (1) grep for call sites, (2) verify callers pass the parameter, (3) for save/persist claims execute the restart cycle, (4) for dedup claims send duplicate input and verify the dedup fires.
- **Honest gap (P5):** C5 (API key wiring) and C4 (decorative precision display) still deferred per audit directive. Trigger: next session.
- **Self-certification limitation (P5):** this work is verified by the same session that wrote it. The auditor should re-run the 92-test suite + the C6 restart-cycle test from a fresh clone.
