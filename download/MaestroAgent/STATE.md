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
The previous coder held Railway CLI access (deploying the web app) and Groq
Cloud LLM credentials (configured via Railway env vars, not in the codebase).
NOTE (2026-07-20 correction): the provider is **Groq** (the fast-inference
chip company — `gsk_` key prefix, models like `llama-3.3-70b-versatile`,
`deepseek-r1-distill-llama-70b`), NOT **Grok** (xAI's chatbot). Confirmed
from commits `7d279ad`, `8258c49`, `ea7612d` which reference real Groq-hosted
model names.

**New coder (this session):** read all governance files from disk this session
per the GOVERNANCE_LOOP mutual-read protocol. Read receipt pasted below.

**Token inventory held by the new coder (NOT stored in git):**

| Token | Purpose | Storage |
|-------|---------|---------|
| GitHub PAT (`ghp_*`) | Push to `prateekm1007/MaestroAgent` | `/home/z/my-project/.env.local` (outside repo) |
| Railway API token (`e3d39b32-…`) | Manage Railway deployment of the web app; token name: "Agent" | `/home/z/my-project/.env.local` (outside repo) |
| Groq API key (`gsk_*`) | LLM inference via Groq.com (llama-3.3-70b-versatile, deepseek-r1-distill-llama-70b) | `/home/z/my-project/.env.local` (outside repo) |

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

### Second-session corrections (2026-07-20, senior auditor review)

A senior auditor reviewed the first coder session's work and flagged five
issues. All verified by execution this session. Recorded here so the next
session doesn't re-derive them.

**1. `SCORING_SYSTEM_v2.md` does NOT exist in the repo.**
- The auditor instructed me to read it before my first commit; I looked,
  it's not there. `find . -iname 'scoring_system*'` returns nothing.
  `audit_scripts/verify_benchmark.sh` references "SCORING_SYSTEM.md" in a
  comment but that file also doesn't exist.
- The auditor has owned this as their error: they created it as a
  downloadable artifact for Prateek via `present_files` but never pushed
  it into git. Going forward, **`STATE.md` + `FORENSIC_AUDIT_AND_HANDOFF.md`
  are the canonical handoff record** — what's in the repo is what counts.
- Governance gap to flag to Prateek: the Rosetta Stone that was supposed
  to reconcile three different "AI Quality" definitions (Gate 1 BM25
  ablation, the parallel auditor's Ask-correctness definition, the
  roadmap's LLM-orchestration definition) is not in the repo. Three
  different threads have each invented their own "AI Quality" — the
  pattern of confusion it causes is exactly what that document was
  supposed to prevent.

**2. Route wiring is NOT 100%. Verified by execution.**
- The previous coder's commit `01e321e` claimed "100% of routes wired."
  False. Recomputed this session by walking `routers/*.py`, extracting
  every `@router.<method>(...)` decorator, resolving the prefix, then
  grepping `web/src/lib/maestro-api.ts` and `mobile/src/api/client.ts`
  for literal references to each route path.
- **Methodology (use this going forward — registered routes only, not
  source-exists):** the `/api/copilot/*` router exists in source
  (`routers/copilot.py`, 21 route decorators) but is COMMENTED OUT in
  `api.py` line 991 per commit `2987f60` ("Day 1 cuts: hide copilot").
  Excluding unregistered routers, the honest denominator is **84
  registered `(method, path)` pairs** across 8 routers (admin, auth,
  ask, commitments, connectors, signals, surfaces, account).
- Recompute script: `/home/z/my-project/scripts/count_route_wiring.py`
  (persisted per Rule 9). Run it with:
  `python3 /home/z/my-project/scripts/count_route_wiring.py`
- **Verified numbers (this session):** 97 unique paths (path-params
  normalized) → web 61/97 (62.9%), mobile 50/97 (51.5%). The senior
  auditor's count was 99 routes / 59.6% web / 47.5% mobile — small
  discrepancy explained by the copilot-router question and by my
  matcher counting any literal substring (slightly liberal). Either
  way, **wiring is in the 50-65% range, not 100%**. The "100% wired"
  claim in commit `01e321e` is false and must not be repeated.
- 36 routes are wired on NEITHER platform. Full table in the script
  output. The biggest clusters: 16 `/api/copilot/*` routes (intentionally
  unwired — disabled), 4 OAuth callback routes (server-side only, no
  client call needed), observability/trace routes, device registration,
  whisper push, ask/stream.

**3. Joke classifier is PARTIAL, not done. Verified by execution.**
- Commit `43a5539` ("fix: structural joke detection + completion query
  dimension") claims both directions #2 and #3 from the senior auditor's
  roadmap review. Both are PARTIAL.
- **Joke classifier:** ran `classify_commitment()` against 8 cases (the
  auditor's riddle + 5 novel joke structures + 2 real-commitment
  controls). Result: **6/8 pass**. PASSES on riddle, knock-knock,
  what-do-you-call, absurd-hypothetical-via-negation. FAILS on
  puns/wordplay ("I'd tell you a chemistry joke but I know I wouldn't
  get a reaction. I promise it's funny." → classified as real
  commitment) and sarcasm-without-slang ("Oh sure, I promise I'll get
  right on that." → classified as real commitment). The classifier
  catches STRUCTURE (riddle format) but not SEMANTIC non-literalness
  (puns, sarcasm). Per direction #2: bar was "riddle + 2 other
  unrelated structures" — MET for patterns in code; does NOT generalize.
  Verification script: `/home/z/my-project/scripts/verify_43a5539_fixes.py`.
- Auditor's transparency note (worth keeping): their first attempt at
  the negation case used the wrong construction (hypothetical without
  a negation keyword) and got a false failure. They checked
  `negation_keywords = ["won't", "can't", "cannot", "not able to",
  "unable to"]` before concluding anything, reconstructed the test, and
  got the same 6/8. Same discipline asked of everyone — verify test
  constructions against the actual code before publishing numbers.

**4. Completion-state Ask dimension is source-wired but NOT end-to-end
   verified. Verified by source inspection.**
- `43a5539` added 'completed' intent to `ask.py` line 178-179 (broad
  patterns: "completed", "fulfilled", "already done", "already sent"),
  `ledger_routing.py` line 62-71 (`get_completed_commitments()` returns
  `completed_claimed` + `completed_verified` ledger entries), and
  `ledger_routing.py` line 123-125 (`elif intent == "completed": return
  get_completed_commitments(...)`).
- Full /api/ask end-to-end test NOT yet run. The intent-detection
  import path failed in my verification script (`_INTENT_BROAD_PATTERNS`
  not exported) — fell back to source inspection. A live test through
  the actual `/api/ask` endpoint is needed before this is closed.
- **Critically: does NOT yet serve the ablation's `recurring` /
  `relational` question types.** The senior auditor's key insight was
  that this same tool-call layer is structurally the fix Gate 1's
  `recurring`/`relational` types need (they score 0.0 across every arm
  including LLM because pure-text retrieval can't answer them).
  `43a5539` only wired `completed`. Extending to `recurring` +
  `relational` is the most likely path to actually moving Gate 1.

**5. Real Gate 1 movement happened in commit `6167675`.**
- Before this session, Gate 1 (BM25 ablation) was at -3.9pts lift
  (B_full_maestro=0.45 vs A_bm25=0.55). Commit `6167675` ("benchmark:
  Groq LLM-active ablation, n=30, 23/30 LLM active") ran the first
  genuinely LLM-active ablation on stable infrastructure (no tunnel,
  no circuit-breaker flapping). Result: **lift -0.6pts**
  (B_full_maestro=0.5333 vs A_bm25=0.55). Real movement, honestly
  diagnosed in the commit message: "lift is still -0.6pts — same as
  rules-only... this confirms the retrieval architecture is the
  bottleneck, not the LLM."
- Concrete failing example in the commit: the RRF ranker puts Alex
  Chen's pricing deck above Riley's actual answer for a `broken`-type
  query — the LLM then faithfully reports the wrong evidence it was
  handed. That's a precise, actionable root cause.
- **Hygiene gap (new, found this session):** the block is internally
  labeled "Rules-only retrieval ensemble... LLM was off" in its own
  `notes` field, while the same block's `llm_active: 23` and the commit
  message both say LLM was active on 23/30 calls. `verify_benchmark.sh`
  Check 5 passes clean (37/37) because Check 5 only checks NUMERIC
  notes-vs-structured consistency, not DESCRIPTIVE claims like "LLM was
  off" against the `llm_active` count sitting right next to it. Same
  family as the bugs Check 5 was built to catch — different shape
  (qualitative claim vs numeric claim). Worth a Check 6, not urgent
  because the commit message itself is accurate.
- **Unexplained:** 7/30 queries fell back to rules. Commit correctly
  flags this as needing investigation rather than papering over it.
  Root cause (entity gate blocking vs circuit breaker) not yet
  determined. Worth root-causing before any future run because a
  partial-activation rate that isn't understood makes every number
  after it slightly uncertain.

**6. RRF bug reproduction (this session, by execution).**
- Wrote `/home/z/my-project/scripts/reproduce_rrf_bug.py` (LLM-disabled,
  fresh temp DB with controlled 10-signal corpus). Ran it. **Result:
  NO BUG at the retrieval-ensemble layer.** Riley's "Never sent"
  signal ranked #1 for both "What did I fail to deliver?" and "Which
  promises are now overdue?". Alex Chen ranked #7 or absent.
- Wrote `/home/z/my-project/scripts/reproduce_rrf_bug_with_llm.py`
  (HTTP /api/ask with Groq env vars set). Ran it. **Result: BUG
  CONFIRMED in production API path.** For "What did I fail to
  deliver?", evidence_refs returned 3 Alex Chen signals, Riley absent.
  For "Which commitments are at risk?", Alex Chen at rank 4, Riley's
  "Never sent" absent. For "Which promises are now overdue?" (TEST 2),
  no bug — Riley at rank 1.
- **Root cause traced (P1: by execution, not by reading):** there are
  TWO retrieval paths in the codebase, and they behave differently:
    * Path A — `maestro-personal/src/maestro_personal_shell/retrieval_ensemble.py`
      (`retrieve()` function, the 5-stage BM25+specialists+RRF pipeline).
      This is what the ablation script tests. This path WORKS — Riley
      ranks #1.
    * Path B — `backend/maestro_cognitive_council/ask_bridge.py`
      (`SituationAwareAskBridge.ask()`). This is what `/api/ask` ACTUALLY
      calls when LLM is unavailable (via `AskSurface.ask()` →
      `SituationAwareAskBridge`). This path does entity-detection-first:
      it picks an entity from the query (or from `_detect_entity_from_signals()`
      when no entity is named), then returns the situation for THAT
      entity. For "What did I fail to deliver?" — no entity named →
      `_detect_entity_from_signals()` picks Alex Chen (first in demo
      seeder) → returns Alex Chen's situation → Riley never surfaces.
- **This is a structural disconnect the ablation can't see.** The
  ablation tests Path A (retrieval_ensemble.py) and shows it works.
  Production uses Path B (SituationAwareAskBridge) which doesn't use
  the ensemble at all when LLM is off. So the "lift -0.6pts" result in
  `6167675` is measuring Path A, while the actual user-facing behavior
  is Path B. Fixing Path A's RRF won't move the user-facing bug.
- **The auditor's connection is now sharper.** The senior auditor
  flagged that the tool-call layer (`get_completed_commitments`) is
  structurally the fix Gate 1's `recurring`/`relational` types need.
  But the bigger structural finding is that the production Ask path
  (Path B) doesn't even USE the retrieval ensemble (Path A) when LLM
  is off. So the question isn't just "extend the tool-call layer to
  recurring/relational" — it's "make Path B actually call Path A for
  intent queries, instead of doing entity-detection-first." That's the
  real unblock.
- **Groq API key issue (this session).** The `gsk_*` key supplied
  returns `{"error":{"message":"Forbidden"}}` on both
  `GET /v1/models` and `POST /v1/chat/completions`. Verified by
  direct curl. So the LLM-active path was never actually exercised
  in my reproduction either — all 3 tests fell back to rules. This
  means the commit `6167675`'s "23/30 LLM active" claim may also be
  questionable (Railway env may have had a working key then; the key
  supplied to me now is not working). **User: the Groq key needs to
  be re-supplied** for any LLM-active work going forward.
- Reproduction scripts persisted:
  - `/home/z/my-project/scripts/reproduce_rrf_bug.py` — LLM-disabled,
    controlled corpus. Proves retrieval ensemble works in isolation.
  - `/home/z/my-project/scripts/reproduce_rrf_bug_with_llm.py` — HTTP
    /api/ask with Groq env. Proves the bug is in the production path
    (Path B), not the ensemble (Path A).

**7. Path B → Path A fix LANDED (commit `c448459`) + n=47 ablation run.**
- Commit `c448459` ("fix: wire Path B → Path A for intent queries
  (broken-type 0.00 → 1.00)") injected a 194-line block in
  `maestro-personal/src/maestro_personal_shell/routers/ask.py` that
  delegates intent queries directly to `retrieval_ensemble.retrieve()`
  BEFORE the AskSurface.ask() call. Three iterations to land (see
  commit message): simple delegation → filter synthetic rows →
  normalize synthetic rows + dedupe.
- Senior auditor direction #4 was "n=100, 3 distinct question sets,
  via Groq." **Honest delivery: n=47, 1 question set.** The repo only
  has 47 questions in `memory_v1.py` (across 16 types). `gold_150.py`
  has 150 questions but they're all untyped PersonN lookups — can't
  compute per-type scores. Per P18 (scope honesty), I did NOT fabricate
  53 more questions or pretend 3 distinct sets exist. Surfaced gap to
  user. Used OpenRouter (not Groq — see #8 below).
- **n=47 ablation results (this session, by execution):**
  - A_bm25: 0.5142 (was 0.5500 in n=30 — small drop, broader question set)
  - B_full_maestro: **0.7411** (was 0.5333 — **+20.8pts improvement**)
  - C_rule_based: 0.3227 (was 0.4500 — see note below)
  - lift_B_vs_A: **+22.7pts** (was -1.7pts — **+24.4pts swing**)
  - llm_active: 11/47 = 23% (was 10/10 = 100% in the top-level
    results_B of n=30; n=30's ensemble_rules_only block had 23/30=77%)
  - Wall time: 105.1s (1.8 min) via OpenRouter
- **Per-type wins (n=47 B vs n=30 B):**
  - broken: 0.00 → 1.00 (+100.0pts) — THE BUG FROM 6167675, FIXED
  - conditional: 0.33 → 1.00 (+66.7pts)
  - recurring: 0.50 → 1.00 (+50.0pts) — auditor's connection validated
  - relational: 0.00 → 0.40 (+40.0pts) — auditor's connection validated
- **Per-type still weak:**
  - cross_entity: 0.25 (was unmeasured) — needs investigation
  - critical: 0.50 (was unmeasured)
  - temporal: 0.50 (was unmeasured)
  - prepare, priority: 0.50 each
- **Gate 1 assessment:** B_full_maestro = 0.7411 = **7.4/10**, above
  the 5/10 floor. **GATE 1 CLEARED.** Composite can now move above 6.5.
- **Three caveats (P18: scope honesty):**
  1. **LLM activation is only 11/47 (23%).** The +22.7pts lift is
     mostly from the Path B → Path A rule-based delegation, NOT from
     the LLM. The LLM only fires on direct_lookup (6/7), multilingual
     (2/2), and a few others. Most intent-type queries (broken, overdue,
     at_risk, recurring, relational, abstention) never reach the LLM.
     This is the 7/30 fallback issue from `6167675` at scale — needs
     root-causing (senior auditor direction #3, still open).
  2. **C_rule_based dropped from 0.45 to 0.32.** Not caused by my fix
     (C arm calls `surface.ask()` directly, bypassing the intent-
     delegation block). Mostly from types that weren't in n=30 at all
     (abstention, at_risk, critical, cross_entity) now being measured
     at their actual rule-based level (0.00-0.33). Real regressions:
     conditional 1.00→0.50, recurring 0.50→0.33 — likely from broader
     question set, not from my fix.
  3. **n=47, not n=100.** Senior auditor's bar not met. Repo needs
     more questions to actually run n=100. Surfaced to user.
- **Results persisted:**
  - `evaluation/scoreboard/ablation_n47_results.json` — full 47-question
    A/B/C results + per-type breakdown
  - `evaluation/scoreboard/ablation_n47_log.txt` — comparison log
    (n=30 vs n=47, Gate 1 assessment, direction #4 status)
- Reproduction wrapper: `/home/z/my-project/scripts/run_ablation_n47.py`
  (patches INDICES in ablation_matrix.py, runs all 47 questions,
  restores the original file, copies results to a clearly-named path).

**8. Three follow-up fixes + n=100 ablation (this session, by execution).**
Senior auditor said "do all 3 sequentially":
  (1) root-cause 23% LLM activation, (2) write more questions for n=100,
  (3) fix context_engineer chronological sort. All three landed.

**(1) LLM activation 23% → 63% (direction #3 root cause + fix).**
- Root cause: intent queries (broken/overdue/at_risk/recurring/relational/
  abstention) NEVER reached the LLM because (a) my Path B → Path A fix
  (commit `c448459`) returns early for intent queries BEFORE the LLM gate
  at line ~614, and (b) the LLM gate at line ~1097 requires
  `matching_situation` which requires an entity match. For intent queries
  that don't name an entity, no LLM fired.
- Fix: in the intent-delegation block, when LLM is available, call
  `llm_complete()` directly with the ensemble evidence as grounding context.
  If LLM returns a usable answer, use it (llm_active=True). If LLM times
  out or fails, fall back to the rule-based answer (P6: fail closed).
  Added ~80 lines to `routers/ask.py`.
- Verified by execution: n=47 re-run went from 11/47 LLM-active to 34/47.
  n=100 run achieved 63/100 LLM-active.

**(2) Question expansion 47 → 100 (direction #4 n=100 bar).**
- Added 53 new questions to `evaluation/scoreboard/memory_v1.py`,
  all grounded in the existing 32-signal corpus. No fabrication — every
  question references only entities/facts that actually exist in SIGNALS.
- Type distribution after expansion (was → now):
  broken 1→5, overdue 1→5, at_risk 1→5, direct_lookup 7→15, relational
  5→10, temporal 4→8, critical 4→8, abstention 4→8, contradiction 3→6,
  recurring 3→6, noise_lookup 3→6, priority 2→4, multilingual 2→3,
  disputed 2→3, conditional 2→3, cross_entity 2→3, prepare 1→2.
  Total: 47 → 100.
- Per P18 (scope honesty): still 1 question set, not 3. Did NOT pretend
  3 distinct sets exist. Surfaced gap to user.

**(3) context_engineer intent-aware sort (repro TEST 2/3 fix).**
- Root cause: `context_engineer` sorted ALL evidence chronologically
  (oldest first). For intent queries like "Which promises are now
  overdue?", this put Riley's original commitment (May 21) ABOVE
  Riley's "Never sent" signal (July 10) — the wrong ranking for this
  intent. The broken-fulfillment signal should rank higher.
- Fix: in `retrieval_ensemble.py` `context_engineer()`, detect intent
  queries via a substring list (mirrors `_INTENT_BROAD_PATTERNS` in
  ask.py). For intent queries, preserve RRF rank order (don't sort
  chronologically). For timeline-reasoning queries (direct_lookup,
  contradiction, temporal, prepare), keep chronological sort.

**n=100 ablation results (this session, by execution):**
- A_bm25: 0.5033 (n=47 was 0.5142, n=30 was 0.5500)
- B_full_maestro: **0.6850 = 6.9/10** (n=47 was 0.7411, n=30 was 0.5333)
- C_rule_based: 0.2750 (n=47 was 0.3227, n=30 was 0.4500)
- llm_active: **63/100 = 63%** (n=47 was 34/47=72%, n=30 was 10/10=100%)
- lift_B_vs_A: **+18.2pts** (n=47 was +22.7pts, n=30 was -1.7pts)
- Wall time: ~7 min via OpenRouter meta-llama/llama-3.3-70b-instruct
- **GATE 1 STILL CLEARED** at n=100. B_full_maestro = 6.9/10, above 5/10 floor.

**Per-type B (Full Maestro) n=100 (worst → best):**
- priority: 0.38 (1/4 LLM) — needs investigation
- temporal: 0.38 (1/8 LLM) — LLM rarely fires on temporal
- disputed: 0.33 (2/3 LLM)
- relational: 0.47 (7/10 LLM)
- recurring: 0.50 (3/6 LLM)
- cross_entity: 0.50 (2/3 LLM)
- at_risk: 0.53 (3/5 LLM)
- broken: 0.60 (3/5 LLM) — down from 1.00 in n=47 (only 1 question then)
- overdue: 0.67 (2/5 LLM)
- critical: 0.69 (7/8 LLM)
- noise_lookup: 0.75 (5/6 LLM)
- prepare: 0.75 (1/2 LLM)
- conditional: 0.78 (3/3 LLM)
- direct_lookup: 0.93 (14/15 LLM)
- contradiction: 1.00 (6/6 LLM)
- multilingual: 1.00 (3/3 LLM)
- abstention: 1.00 (0/8 LLM — by design, abstention doesn't need LLM)

**Three honest caveats (P18):**
1. **B_full_maestro dropped 0.7411 → 0.6850 at n=100.** This is NOT a
   regression from my fixes — it's the broader question set exposing
   weaker types. n=47 only had 1 broken question (which scored 1.00);
   n=100 has 5 broken questions averaging 0.60. The fix didn't get
   worse; the test got more honest.
2. **LLM activation 63%, not higher.** The LLM-grounding fix tripled
   activation (23% → 63%) but 37 queries still fall back to rules.
   Remaining gap: some intent queries return empty ensemble evidence
   (no matching signals), so the LLM-grounding block never fires.
3. **Still 1 question set, not 3.** Senior auditor's full bar not met.
   The 100 questions are grounded in 1 corpus; a true 3-set test would
   need 3 distinct corpora. Surfaced to user.

**Files changed (this session, not yet committed as a unit):**
- `maestro-personal/src/maestro_personal_shell/routers/ask.py` — LLM
  grounding block for intent queries (+80 lines, on top of c448459's +194)
- `maestro-personal/src/maestro_personal_shell/retrieval_ensemble.py` —
  intent-aware sort in context_engineer (+~60 lines)
- `maestro-personal/evaluation/scoreboard/memory_v1.py` — 53 new questions
  (+95 lines)
- `evaluation/scoreboard/ablation_n100_results.json` — new, 100-row results
- `evaluation/scoreboard/ablation_n100_log.txt` — new, comparison log

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
