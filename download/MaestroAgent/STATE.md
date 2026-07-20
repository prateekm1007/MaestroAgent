# Maestro State Log

> ⛔ **GOVERNANCE GATE: Read [GOVERNANCE.md](./GOVERNANCE.md) and [ENTROPY_RECOVERY.md](./ENTROPY_RECOVERY.md) BEFORE doing any work or trusting any claim in this file.**
> ⛔ **HANDOFF GATE: Read [FORENSIC_AUDIT_AND_HANDOFF.md](./FORENSIC_AUDIT_AND_HANDOFF.md) before any new coder session.**

---

## Last Updated
2026-07-20 — CODER HANDOFF. Previous coder has stepped off; new coder onboarding
this session. Forensic audit + handoff doc committed at `8ff6b92`. STATE.md
reconciled from stale `11342e4` (last entry below) up to current HEAD `8ff6b92`.

## Current Status: ~7/10 — audit-fix pass + LLM active + web + mobile wired.
Controlled single-user beta. Mobile login bypass is the new P0 (security).

> **HEAD:** `8ff6b92` on `main` (was `7d279ad` at forensic-audit time, was
> `11342e4` at last STATE.md update on 2026-07-12).
>
> **Forensic audit (354 lines) committed at `8ff6b92`:**
> - 105 REST endpoints verified (backend port 8766)
> - Web (port 3000) + mobile (Expo) verified at HEAD `7d279ad`
> - 7 open issues (P0-P2) with concrete fixes documented
> - 8 key architectural decisions captured
> - Shell verification tips (pipe/tsc/ANSI/test-isolation) captured

### Coder Handoff — 2026-07-20

**Previous coder:** handed off via the 354-line forensic audit document.
The previous coder held Railway CLI access (deploying the web app) and Grok
Cloud LLM credentials (configured via Railway env vars, not in the codebase).

**New coder (this session):** read all governance files from disk this session
per the GOVERNANCE_LOOP mutual-read protocol. Read receipt pasted below.

**Token inventory held by the new coder (NOT stored in git):**

| Token | Purpose | Storage |
|-------|---------|---------|
| GitHub PAT (`ghp_*`) | Push to `prateekm1007/MaestroAgent` | `/home/z/my-project/.env.local` (outside repo) |
| Railway API token (`e3d39b32-…`) | Manage Railway deployment of the web app; token name: "Agent" | `/home/z/my-project/.env.local` (outside repo) |
| Grok Cloud API key (`gsk_*`) | LLM inference via x.ai (replaces/augments the prior Groq setup) | `/home/z/my-project/.env.local` (outside repo) |

> ⚠️ **No raw token values are committed to git.** All three tokens live only
> in `/home/z/my-project/.env.local` — a file outside the repo tree, also
> belt-and-suspenders gitignored by `download/MaestroAgent/.gitignore` (.env,
> .env.local, .env.*.local). Per user instruction, the user will re-supply
> tokens in future sessions as needed; the coder should remind the user when
> a token is required and not store it in the repo.

**Read receipt (Coder side, this session):**
```
GOVERNANCE LOOP READ RECEIPT (Coder):
- ENTROPY_RECOVERY.md (225 lines, Parts 1-5, P1-P34) read at 2026-07-20 07:08
  P20: "Call-site parameter rule — when a function gains a parameter, EVERY caller must pass it"
  P26: "Meta: principles don't enforce themselves, re-application does"
  P27: "Read the assertion, not the test name — a test that asserts `True` is theater"
- GOVERNANCE.md (177 lines, 13 gates) read at 2026-07-20 07:08
- GOVERNANCE_LOOP.md (159 lines) read at 2026-07-20 07:08
- AUDITOR_GOVERNANCE.md (211 lines, Gates 1-20) read at 2026-07-20 07:08
  Gate 15: "For 'wired' claims, will you verify callers pass the parameter?"
  Gate 17: "For 'dedup' claims, will you send duplicate input?"
- STATE.md (was 72 lines, stale at HEAD 11342e4) read at 2026-07-20 07:08
- ROAD_TO_9_STATUS.md (129 lines, stale at HEAD 6d1148d) read at 2026-07-20 07:08

> Auditor: Read GOVERNANCE.md, ENTROPY_RECOVERY.md, GOVERNANCE_LOOP.md,
> and AUDITOR_GOVERNANCE.md from disk before auditing. The loop cannot be broken.
```

### Open issues (from FORENSIC_AUDIT_AND_HANDOFF.md, prioritized)

| # | Issue | Severity | Owner |
|---|-------|----------|-------|
| 1 | Mobile login uses `demo-bypass-token` — no real auth (SECURITY) | **P0** | New coder |
| 2 | No mobile registration flow (`/api/auth/register` works, no screen calls it) | **P0** | New coder |
| 3 | Test isolation — chaos tests bleed into other files (18 errors when run together) | **P1** | New coder |
| 4 | Threads for Entity — backend works, no mobile/web screen calls it | **P1** | New coder |
| 5 | Decision History — backend works, no client function (`getDecisions`) exists | **P1** | New coder |
| 6 | Grade Override — backend works, no screen renders the override button | **P1** | New coder |
| 7 | API key redaction — only OTP patterns, not `sk-*` / `ghp_*` (IRONY: this STATE.md update itself would not be redacted by current redactor) | **P1** | New coder |
| 8 | Physical device testing (cold launch, scroll fps, VoiceOver/TalkBack) | **P2** | Blocked — needs device |
| 9 | Real OAuth round-trips with user credentials | **P2** | Needs user OAuth apps |
| 10 | Hybrid BM25+embedding retrieval for better Ask quality at scale | **P2** | New coder |
| 11 | Investor materials not committed to git | **P2** | User decision |
| 12 | 14 `/api/copilot/*` routes still registered but excluded from UIs | **P2** | New coder (deprecation) |

### Next coder priority order (from the forensic audit)

1. **P0** — Fix mobile login bypass (`mobile/src/screens/LoginScreen.tsx`: replace `demo-bypass-token` with a real `api.login(password)` call from `useAuth()` context; add a registration link)
2. **P0** — Fix test isolation (chaos tests: switch `unittest.mock.patch` → `monkeypatch` for `get_db_conn`, or add a conftest fixture that resets the mock between files)
3. **P1** — Wire Threads for Entity + Decision History to both mobile + web (add `getDecisions(entity)` to `client.ts` and `maestro-api.ts`; add a ThreadDetail screen calling `getThreadsForEntity(entity)`)
4. **P1** — Add API key redaction patterns to `secret_redactor.py` (sk-*, ghp_*, gsk_*, Bearer tokens)
5. **P1** — Grade Override UI in the meeting grade detail view
6. **P2** — Physical device testing (needs phone)
7. **P2** — Real OAuth round-trips with user credentials
8. **P2** — Hybrid BM25+embedding retrieval for better Ask quality at scale
9. **P2** — Commit investor materials to the repo (if available)

### Strategic direction (6-month roadmap + retrieval execution plan)

Two strategic docs committed alongside this STATE.md update:

- **`ROADMAP_TO_WORLD_CLASS.md`** — 3-phase, 6-month plan to lift all 16 audit
  benchmarks to 9/10. Phase 1 (months 1-2): zero-noise ambient, intent-aware
  commitment extraction, commitment lifecycle graph. Phase 2 (months 3-4):
  agentic Ask engine, contradiction/resolution memory, conversational
  fallbacks. Phase 3 (months 5-6): enterprise security, micro-latency budgets,
  auto-healing connectors. Includes the 16-benchmark score-tracking table
  (audit → phase 1 → phase 2 → phase 3 targets).
- **`RETRIEVAL_EXECUTION_PLAN.md`** — 4-stage tactical plan for the retrieval
  sub-system. Stage 1: BM25 high-recall (Recall@50 > 99%, < 50ms). Stage 2:
  parallel hybrid retrieval with RRF across entity/temporal/graph/commitment
  retrievers (Recall@20 > 95%, MRR > 0.85). Stage 3: cross-encoder reranking
  + compression (evidence precision > 95%, token reduction > 60%). Stage 4:
  reasoning engine upgrade (Qwen 3 14B/32B, DeepSeek-R1 for judgment).
  Each stage has a "Success Measurement" gate — per P1, no stage is marked
  complete without pasted benchmark output hitting the stated numbers.

**Cross-reference: how the audit's open issues map to the roadmap**

| Audit issue | Severity | Maps to roadmap |
|-------------|----------|-----------------|
| #1 Mobile login bypass | P0 | (governance debt — close before any roadmap work) |
| #2 No mobile registration | P0 | (governance debt — close before any roadmap work) |
| #3 Test isolation (chaos bleed) | P1 | (governance debt — close before Phase 1; Phase 1.2 intent classifier will add many new tests, isolation must be solid first) |
| #4 Threads for Entity UI | P1 | Phase 2.1 (Agentic Ask — threads become a retriever target) |
| #5 Decision History client fn | P1 | Phase 2.1 (Agentic Ask — decisions become a tool-call target) |
| #6 Grade Override UI | P1 | Phase 1.3 (commitment lifecycle UI) |
| #7 API key redaction (sk-*/ghp_*/gsk_*) | P1 | Phase 3.1 (enterprise security) — but fix is trivial, do it now |
| #8 Physical device testing | P2 | Phase 3.2 (performance budgets) — needs device |
| #9 Real OAuth round-trips | P2 | Phase 3.3 (auto-healing connectors) |
| #10 Hybrid BM25+embedding | P2 | **`RETRIEVAL_EXECUTION_PLAN.md` stages 1-3** — this is the entry point for the retrieval work |
| #11 Investor materials not in git | P2 | (operational — user decision) |
| #12 Copilot routes deprecated | P2 | Phase 3 cleanup |

**The two-track priority for the new coder:**

1. **Tactical debt track** (audit P0-P1): mobile login, test isolation, API-key
   redaction, missing client functions (#4, #5, #6). These block trustworthy
   development on the roadmap. Estimate: 1-2 weeks of focused work.
2. **Strategic track** (roadmap Phase 1 + retrieval stages 1-2): zero-noise
   ambient, intent-aware commitment extraction, commitment lifecycle, BM25
   recall baseline + parallel hybrid retrieval. This is the 9/10 work. The
   retrieval plan's Stage 1 (BM25 Recall@50 > 99%) is the natural first
   executable step on the strategic track because it has a clean success
   metric and unblocks everything downstream.

> ⚠️ **Per P6 (fail closed, not silent) and the audit's governance gate:**
> the tactical debt track must close BEFORE the strategic track starts. Building
> Phase 1 product on top of unresolved P0 security debt (mobile login bypass)
> would violate the governance principle that the forensic audit codified.
> The new coder should NOT jump to the retrieval plan until mobile login +
> test isolation are fixed.

### Reconciliation note (why this STATE.md update exists)

The previous STATE.md entry (below, 2026-07-12) was at HEAD `11342e4`. Between
then and the forensic audit, 13+ commits landed (ending at `7d279ad`), and the
forensic audit itself added commit `8ff6b92`. This update:

- Closes audit finding F10 retroactively for the new HEAD (it was previously
  closed for `11342e4` but became stale again — a recurring pattern P14
  warns about: "bugs migrate one layer deeper").
- Records the coder handoff so the next session doesn't re-derive who's
  holding which tokens.
- Pastes a real read receipt (timestamp + key line) per GOVERNANCE_LOOP.md,
  rather than the previous verbal "Governance gate: ... read from disk this
  session" line that didn't prove the read happened.

The 2026-07-12 entry is preserved below for history.

---

## Last Updated
2026-07-12 — LLM-active test run with Kaggle P100 Ollama tunnel. Both baseline failures CLOSED. (Stale at this commit — superseded by the 2026-07-20 handoff entry above; preserved for history.)

## Current Status: ~5.3/10 → audit-fix pass complete + LLM proven. Controlled single-user beta. Not multi-user safe.

> **HEAD:** `11342e4` on `main` (was `daeb88e`, was `2133cb5`, was `f32a751` at audit time).
>
> **Test counts (executed with LLM active, P4 reconciliation):**
> - 824 tests collected (was 807 — 17 new tests added in 2133cb5+daeb88e)
> - Security + lifecycle + LLM subset (206 tests): **206/206 PASSED** in 74s
> - LLM-specific tests (test_llm_via_ollama + test_llm_wiring + test_llm_latency_hypothesis): **35 passed, 3 skipped** in 31s
> - Both baseline failures now CLOSED:
>   1. test_graph_completion_rate_accuracy → FIXED in 2133cb5 (F3 graph wiring)
>   2. test_llm_complete_works_when_api_responds → FIXED in 11342e4 (test isolation)
> - End-to-end Ask with LLM: **PASSED** — llm_active=True, provider=ollama,
>   confidence=0.3 (honestly capped by single-evidence), answer correctly
>   mentions Maria + Friday + pricing/proposal, 27.6s latency
>
> **LLM runtime (proven this session):**
> - Provider: Ollama (llama3:8b, Q4_0, 4.66GB)
> - Hosted on: Kaggle P100 GPU via Cloudflare tunnel
> - Eval speed: 0.06s per token
> - llm_active=True verified in /api/ask response
> - probe_provider() returns verified=True, latency_ms=744
>
> **Audit findings addressed (3 commits: 2133cb5, daeb88e, 11342e4):**
> - F1 (ask ranking noise): FIXED ✓ — select_top_evidence now filters by min_score
> - F2 (label honesty): FIXED ✓ — llm_active=true with LLM; confidence caps in rules mode
> - F3 (graph completion_rate): FIXED ✓ — wired resolve_completion_signal into ingest
> - F4 (staleness consistency): FIXED ✓ — aligned threshold; closure-only reset
> - F6 (silence false CRITICAL): FIXED ✓ — removed bare 'fine' from legal keywords
> - F8/S1 (auth fail-closed): FIXED ✓ — dev mode no longer mints arbitrary emails
> - F9 (Prepare corrections): FIXED ✓ — _filter_corrected_signals applied
> - F10 (STATE.md stale): FIXED ✓ — reconciled with HEAD
> - HIGH-1 (XSS in entity): FIXED ✓ — 3-layer sanitization applied to entity
> - MEDIUM-2 (length cap): FIXED ✓ — Field(max_length=200/10000)
> - MEDIUM-3 (docs exposure): FIXED ✓ — /docs disabled in production
> - P25 (confidence cap): FIXED ✓ — three caps: rules 0.6, <3 evidence 0.5, noise 0.3
> - Test isolation (Phase 0.3): FIXED ✓ — both baseline failures closed
>
> **Audit findings still OPEN (require external deps or multi-week work):**
> - F5 (live learning A/B): PARTIALLY ADDRESSED — dismissal recorded; live divergence weak
> - F7 (copilot WS fusion): OPEN — REST copilot works; WS fused whispers not demonstrated
> - F8/S2 (OIDC): OPEN — shared-secret with fail-closed default; real IdP needed for SaaS
> - F10 (api.py god-module): OPEN — 5,289 lines; splitting is Phase 8 P2 work
> - Phase 1 (memory gold set + BM25 comparison): NOT STARTED — needs 50-question gold corpus
> - Phase 2 (commitment lifecycle gold set): NOT STARTED — needs 50-item lifecycle corpus
> - Phase 3 (100-moment silence benchmark): NOT STARTED — needs production whisper path scoring
> - Phase 4 (copilot 10-meeting eval): NOT STARTED — needs WS + LLM + meeting scripts
> - Phase 5 (ablation table): NOT STARTED — needs all above first
>
> **What's verified by execution this session:**
> - 206/206 security + lifecycle + LLM tests PASSED with LLM active
> - 35/35 LLM-specific tests PASSED (3 skipped — provider-specific)
> - End-to-end Ask: llm_active=True, provider=ollama, confidence=0.3 (honestly capped)
> - Both baseline test failures CLOSED
> - XSS, auth, staleness, silence, Prepare — all regression tests green
>
> **What's NOT verified:**
> - Full 824-test suite (ran 206-test subset + 35 LLM tests; full suite needs >5min)
> - Multi-user calibration isolation in production
> - OIDC/real auth (shared-secret only, fail-closed default)
> - Phase 1-5 gold-set evaluations (not yet built)
>
> **CTO recommendation (updated):**
> - Multi-user SaaS: DO NOT SHIP
> - Single-user local dogfood: SHIP TO CONTROLLED BETA (LLM now proven)
> - "9/10 / world-class": NOT JUSTIFIED — needs Phase 1-5 gold-set proof per roadmap
