# ROADMAP COMPLETION PLAN — Step-by-Step to 9/10

> **Created:** 2026-07-14 (Task 64)
> **Based on:** ROADMAP_TO_9_OF_10_V2.md (auditor's upgraded roadmap)
> **Current score:** ~3.5/10 | **Target:** 9.0/10
> **Method:** every step is verified by execution (P1), not by reading

## Current State (verified by execution, 2026-07-14)

| Phase | Items | ✅ Done | ⚠️ Partial | ❌ Not Done | % |
|-------|-------|---------|------------|-------------|---|
| Phase 0 | 6 | 3 | 2 | 1 | 67% |
| Phase 1 | 7 | 3 | 3 | 1 | 64% |
| Phase 2 | 5 | 0 | 0 | 5 | 0% |
| Phase 3 | 5 | 0 | 1 | 4 | 10% |
| Phase 4 | 3 | 0 | 0 | 3 | 0% |
| Phase 5 | 4 | 0 | 2 | 2 | 25% |
| §9 CI | 5 | 5 | 0 | 0 | 100% ✅ |
| **Total** | **35** | **11** | **8** | **16** | **34%** |

## Step-by-Step Plan

### STEP 1: Fix the 9 test-isolation failures (Phase 0.4) — 1 day

**Problem:** 9 tests pass individually but fail in the full suite due to shared-SQLite pollution.
**Work:**
1. Run `pytest tests/ -x --tb=short` to identify each failure
2. For each failing test, add a `tmp_path` fixture (temp DB per test)
3. Re-run full suite until green
**Done when:** `python ci_checks/check_full_suite.py` exits 0
**Score impact:** Reliability 2.5 → 5.5, Backend 3.5 → 6.0

### STEP 2: Fix mobile dependency mismatch (Phase 2.1) — 0.5 days

**Problem:** `react 18.3.1` + `react-dom 19.0.0` mismatch; `--legacy-peer-deps` required
**Work:**
1. Align react and react-dom to the same version (19.0.0)
2. Align expo 53 and jest-expo 53 (was jest-expo 52)
3. Remove `--legacy-peer-deps` from all install commands
4. Verify `npm install` works without the flag
**Done when:** `npm install` succeeds without `--legacy-peer-deps`; `npx tsc --noEmit` exits 0
**Score impact:** Mobile UI 4.5 → 5.5

### STEP 3: Remove Copilot + restructure to 4 tabs (Issue 5) — 2 days

**Problem:** App has 6 tabs, Copilot still present (instructions said remove it)
**Work:**
1. Delete `mobile/src/screens/CopilotScreen.tsx`
2. Create `MemoryScreen.tsx` (commitments + drafts + compose button)
3. Create `MoreScreen.tsx` (connectors, settings, privacy)
4. Create `DraftApprovalModal.tsx`
5. Update `App.tsx` tab navigator: Today, Memory, Ask, More (4 tabs)
6. Update all tests
**Done when:** `grep -c "Tab.Screen" App.tsx` = 4; CopilotScreen.tsx does not exist; all tests pass
**Score impact:** Mobile UX 3.0 → 5.0, Mobile UI 5.5 → 6.5

### STEP 4: Install push notifications (Issue 6) — 2 days

**Problem:** `expo-notifications` not installed; no push infrastructure
**Work:**
1. `npm install expo-notifications`
2. Create `mobile/src/services/notifications.ts` (permission, token, handler)
3. Add `POST /api/auth/push-token` backend endpoint
4. Create `notification_scheduler.py` (stale commitment checker)
5. Add `push_tokens` + `notified_stale` tables
6. Wire into onboarding + login
**Done when:** `grep "expo-notifications" package.json` returns a match; push token registration endpoint exists; scheduler wired
**Score impact:** Mobile UX 5.0 → 6.0

### STEP 5: Proactive email drafting (Issue 7) — 2 days

**Problem:** No MemoryScreen, no DraftApprovalModal, no auto-draft generation
**Work:**
1. Build `MemoryScreen.tsx` with draft buttons on every commitment
2. Build `DraftApprovalModal.tsx` (3-action modal with provenance)
3. Wire `generateAutoDraft` API method
4. Wire `resolveDraft` API method
5. Add "Draft" button to TodayScreen
**Done when:** MemoryScreen.tsx exists; DraftApprovalModal.tsx exists; auto-draft API works end-to-end
**Score impact:** Mobile UX 6.0 → 7.0, Product Design 4.5 → 6.5

### STEP 6: Expand injection tests to 200+ (Issue 9) — 1 day

**Problem:** Only 1 injection test exists
**Work:**
1. Generate 200+ injection test cases (homoglyph, leetspeak, prompt injection, XSS, SQL injection)
2. Add `tests/test_injection_200.py`
3. Run against the 3-layer sanitization (regex + semantic + HTML escape)
**Done when:** `pytest tests/test_injection_200.py` passes with 200+ cases
**Score impact:** Security 4.0 → 6.5

### STEP 7: Run 30-meeting copilot benchmark with LLM (Issue 10) — 1 day

**Problem:** Benchmark ran but 0 whispers detected (REST copilot returns state transitions, not fused coaching)
**Work:**
1. Start LLM tunnel
2. Run benchmark with `OLLAMA_HOST` set
3. Verify whispers are generated (LLM fusion fires)
4. Commit results
**Done when:** Results file shows >0 whispers with `llm_active=True`
**Score impact:** AI Intelligence 1.5 → 3.0 (partial — needs real embeddings for full lift)

### STEP 8: Learning loop ≥30 predictions (Phase 1.5) — 0.5 days

**Problem:** Only 10 predictions verified (Brier=0.0718), target is ≥30
**Work:**
1. Extend `verify_brier_live.py` to generate 30 predictions
2. Compute Brier score
3. Commit results
**Done when:** Brier computed from ≥30 resolved predictions
**Score impact:** AI Intelligence 3.0 → 4.0

### STEP 9: AI-path latency measurement (Phase 1.4) — 0.5 days

**Problem:** Whisper endpoint is fast (113ms) but AI-path latency not measured
**Work:**
1. Write latency benchmark script
2. Measure TTFT (time to first token) and p95 for `/api/ask` with LLM active
3. Commit results
**Done when:** Latency results file committed; TTFT <1.5s or honestly labeled
**Score impact:** Performance 4.0 → 5.5

### STEP 10: Ablation study (Phase 1.7) — 1 day

**Problem:** No ablation study exists
**Work:**
1. For each AI module (ask_ranker, cognitive_council, materiality_gate, etc.), run Gold-150 with it disabled
2. Record per-module lift contribution
3. Delete modules that don't lift ≥2 pts
**Done when:** Ablation results file committed; only ≥2-pt modules remain on default path
**Score impact:** AI Intelligence 4.0 → 5.0

### STEP 11: Device validation (Phase 2.2) — BLOCKED on hardware

**Problem:** App has never run on a device
**Work:** Requires iOS Simulator (macOS) or Android Emulator (Android SDK) or physical device
**Blocker:** No macOS or Android SDK in sandbox
**Score impact:** Cannot score Mobile UX above 5.0 without this

### STEP 12: Real OAuth connectors (Phase 4) — BLOCKED on credentials

**Problem:** All 8 connectors still `demo_mode: true`
**Work:** Requires real SLACK_CLIENT_ID, GITHUB_CLIENT_ID, etc.
**Blocker:** User must provide OAuth credentials
**Score impact:** Cannot score Connectors above 0 without this

### STEP 13: Postgres + observability (Phase 3.2) — 3 days

**Problem:** SQLite only; no Postgres, no RED metrics, no tracing
**Work:**
1. Add Postgres support to db_util.py (dual-write or migration)
2. Add prometheus metrics endpoint
3. Add OpenTelemetry tracing
4. Add alerting rules
**Done when:** App runs on Postgres; metrics endpoint returns data
**Score impact:** Backend 6.0 → 7.5, Performance 5.5 → 7.0

### STEP 14: Chaos/fault matrix (Phase 3.1) — 2 days

**Problem:** No fault testing
**Work:**
1. Write chaos test suite (network, auth, LLM, DB, OAuth failures)
2. Run in CI
3. Fix any crashes
**Done when:** Chaos suite green; crash-free ≥99.9%
**Score impact:** Reliability 5.5 → 7.5

### STEP 15: Privacy TTLs + GDPR (Phase 5.2) — 1 day

**Problem:** Retention TTLs not enforced
**Work:**
1. Add retention TTL enforcement to data deletion
2. Add GDPR export/delete flow tests
3. Verify egress minimization
**Done when:** TTLs enforced + tested; GDPR flows verified by execution
**Score impact:** Privacy 6.0 → 8.5

### STEP 16: Accessibility audit (Phase 5.3) — BLOCKED on device

**Problem:** No WCAG 2.1 AA audit
**Work:** Requires device with VoiceOver/TalkBack
**Blocker:** No device in sandbox
**Score impact:** Cannot score Accessibility above 4.0 without this

### STEP 17: Polish + delight (Phase 5.4) — 2 days

**Problem:** No motion/haptic grammar; no empty-state craft
**Work:**
1. Add motion grammar (spring animations, transitions)
2. Add haptic feedback (expo-haptics)
3. Polish empty states
4. Heuristic review against Linear/Things/Superhuman
**Done when:** Motion/haptics implemented; heuristic review ≥9
**Score impact:** Product Design 6.5 → 8.0, Mobile UI 6.5 → 8.0

## Execution Order (parallelized where possible)

```
Week 1:  Step 1 (test-isolation) + Step 2 (deps) + Step 6 (injection 200+)
Week 2:  Step 3 (4 tabs) + Step 4 (push notifications)
Week 3:  Step 5 (proactive drafting) + Step 7 (30-meeting benchmark)
Week 4:  Step 8 (learning loop 30+) + Step 9 (latency) + Step 10 (ablation)
Week 5:  Step 13 (Postgres) + Step 14 (chaos)
Week 6:  Step 15 (privacy TTLs) + Step 17 (polish)
BLOCKED: Step 11 (device) + Step 12 (OAuth creds) + Step 16 (a11y device)
```

## Score Trajectory

| Step | Score After | Key Change |
|------|-------------|------------|
| (now) | 3.5 | CI checks done, Phase 0 mostly done |
| Step 1 | 4.0 | Full suite green |
| Step 2-5 | 5.5 | Mobile restructured + push + drafting |
| Step 6-10 | 6.5 | AI hardened, security tested |
| Step 13-15 | 7.5 | Postgres + chaos + privacy |
| Step 11,12,16 | 9.0 | Device + OAuth + a11y (unblocks final 1.5) |

## What I Can Do Right Now (no blockers)

Steps 1-10 and 13-15, 17 — **15 of 17 steps** — are executable from this sandbox without hardware or credentials. The 2 blocked steps (11, 12, 16) require:
- A macOS machine or Android SDK (for device validation)
- Real OAuth credentials (for connectors)
- A device with VoiceOver/TalkBack (for accessibility)

**Estimated time to 7.5/10:** ~4 weeks of focused work (Steps 1-10, 13-15, 17).
**Estimated time to 9.0/10:** +2-4 weeks once hardware/credentials are available.
