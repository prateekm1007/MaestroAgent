# Maestro 9/10 Roadmap Across Every Audit Parameter

**Starting point:** World-class mobile audit at commit `72b4606cc088d0209bdb0732bc1062b4b38488c8` scored **2.75 / 10** and classified the product as **NOT READY**.  
**Target:** Achieve **≥9.0 / 10 independently on every scoring category**, with all major investor/product claims verified by execution, not documentation.

---

## 0. What “9/10” Means

A 9/10 Maestro is not “all tests pass.” It means:

1. A normal user can install, launch, onboard, authenticate, connect data, ask, track commitments, use Copilot, recover from errors, export/delete data, and trust the product without reading documentation.
2. Every core claim has a repeatable execution proof.
3. No P0 launch blockers exist.
4. No major privacy/security contradictions exist.
5. Mobile UX feels premium compared with category leaders.
6. AI behavior is measurably better than simple LLM + retrieval and simple BM25 baselines.
7. Connectors are real production integrations, not demo mocks.
8. Copilot demonstrably improves live meetings in noisy, realistic conditions.
9. The product can survive degraded network, backend, OAuth, LLM, storage, and permission failures without data loss or user confusion.
10. An external auditor can reproduce results from a clean clone.

---

## 1. Roadmap Summary

| Phase | Duration | Goal | Exit Gate |
|---|---:|---|---|
| Phase 0 | 3 days | Truth freeze and audit harness | No false public claims; reproducible audit scripts exist |
| Phase 1 | 2 weeks | Make mobile launchable and trustworthy | Expo starts, app runs on iOS/Android, no P0 install/startup blockers |
| Phase 2 | 2 weeks | Core mobile UX/UI rebuild | First-minute experience scores ≥9 in internal test rubric |
| Phase 3 | 3 weeks | Backend correctness, reliability, and data integrity | Backend tests pass cleanly; no raw SQLite violations; rate limits active |
| Phase 4 | 4 weeks | Real OAuth connectors | Gmail, Slack, GitHub, Calendar verified end-to-end with sandbox/live accounts |
| Phase 5 | 4 weeks | AI quality and cognitive-engine proof | Maestro beats BM25 and simple RAG by required margins |
| Phase 6 | 4 weeks | Copilot productionization | 30-meeting benchmark passes latency, accuracy, usefulness gates |
| Phase 7 | 3 weeks | Security, privacy, accessibility hardening | External security/privacy/a11y gates pass |
| Phase 8 | 2 weeks | Performance, scalability, polish | Meets mobile and backend SLOs under load |
| Phase 9 | 4 weeks | Private beta and independent re-audit | ≥9/10 in all categories, no P0/P1 blockers |

Total realistic duration: **20–24 weeks** for a genuine 9/10 product.

---

## 2. Category-by-Category 9/10 Roadmap

# A. Mobile UX — Target 9/10

## Current blockers

- App does not launch with `npx expo start` because of invalid Expo plugin config.
- No verified first launch, onboarding, account creation, reconnect, offline, or startup behavior.
- Defaults to `http://localhost:8766`, unsuitable for normal mobile users.
- Password-only login, no real account lifecycle.

## Required work

### A1. Fix launch and install path

- Remove invalid Expo config plugins or replace with correct Expo-compatible plugin usage.
- Make `npx expo start`, `npx expo start --ios`, `npx expo start --android`, and EAS preview builds work.
- Add CI job that runs:
  - `npm ci --legacy-peer-deps`
  - `npm run typecheck`
  - `npx jest --runInBand`
  - `npx expo config --json --full`
  - `npx expo-doctor`
  - EAS local build or equivalent smoke build.

### A2. Build premium first-minute path

- Replace password-only login with:
  - email/password or magic link,
  - OAuth login option,
  - account creation,
  - forgot password,
  - local biometric unlock after login.
- Add a guided onboarding sequence:
  1. What Maestro does.
  2. What data it needs.
  3. Privacy promise.
  4. Choose first connector or manual mode.
  5. First value moment.
- Add skeleton states and native-feeling transitions.
- Add real offline launch screen with cached last-known state.

### A3. Normal-user backend discovery

- Remove localhost default from production app.
- Use environment-based backend config.
- Add QR/deep-link developer backend config only in debug builds.
- Production build must only use HTTPS endpoints.

## 9/10 acceptance criteria

| Test | Required result |
|---|---|
| Clean clone mobile start | Works with documented command |
| iOS simulator launch | Cold launch to first screen < 1.8s p50, < 2.8s p95 |
| Android emulator launch | Cold launch to first screen < 2.2s p50, < 3.2s p95 |
| First-user onboarding | ≥90% of 10 test users understand product value in first minute |
| Auth recovery | Login/logout/token expiry/revocation all recover cleanly |
| Offline launch | Cached app shell and last-known state render without crash |
| Reconnect | Auto-refetch with visible but non-annoying status |

---

# B. Mobile UI — Target 9/10

## Current blockers

- Mobile app could not be visually audited on device.
- `SignalsScreen` exists but is not in tab navigation.
- Fixed phone-centric layouts; no verified tablet/landscape/foldable behavior.
- Dark mode is custom, while `app.json` declares light-only interface style.

## Required work

### B1. Establish a real design system

- Define tokens for:
  - colors,
  - spacing,
  - typography,
  - radii,
  - elevation,
  - semantic states,
  - motion,
  - touch targets.
- Use a small set of reusable components:
  - ScreenShell,
  - TopBar,
  - Card,
  - PrimaryButton,
  - SecondaryButton,
  - EmptyState,
  - ErrorState,
  - LoadingSkeleton,
  - EvidencePill,
  - ConfidenceIndicator,
  - ConnectorCard.

### B2. Redesign every primary surface

Surfaces that must feel intentional:

1. The Moment
2. Ask
3. Commitments
4. What Changed
5. Copilot
6. Connectors
7. Settings
8. Signals or remove Signals as a claimed primary screen

### B3. Responsive layout

- Phone portrait: optimized bottom tabs.
- Phone landscape: no broken clipped content.
- Tablet: two-pane layout for Ask, Commitments, Connectors.
- Foldable: adaptive width classes.

### B4. Visual state coverage

Every screen must have:

- loading state,
- empty state,
- partial-data state,
- error state,
- permission-denied state,
- offline state,
- stale-cache state,
- retry state,
- success confirmation.

## 9/10 acceptance criteria

| Test | Required result |
|---|---|
| Screen inventory | 100% primary screens reachable and understandable |
| UI consistency | No one-off visual styles except intentionally documented variants |
| Layout matrix | iPhone SE, iPhone Pro Max, Android small, Android large, iPad, foldable pass |
| Dark mode | WCAG contrast and visual parity pass |
| Loading/error/empty states | 100% coverage across primary screens |
| Usability test | ≥8/10 users complete core tasks without assistance |

---

# C. Product Design — Target 9/10

## Current blockers

- Strong concept, but execution does not prove reduced cognitive load.
- Too many claims and surfaces without validated workflow value.
- Connectors and Copilot overpromise.

## Required work

### C1. Define one core product promise

Recommended promise:

> Maestro helps you notice, track, and follow through on commitments across work tools, with evidence and restraint.

Everything must support this.

### C2. Simplify primary navigation

Recommended mobile IA:

1. Today — The Moment + What Changed
2. Ask
3. Commitments
4. Copilot
5. More — Connectors, Signals, Settings, Privacy, Audit Log

### C3. Define core jobs-to-be-done

- “What do I need to act on now?”
- “What did I promise?”
- “What changed since I last checked?”
- “What should I ask/follow up on?”
- “What did this meeting produce?”

### C4. Instrument value outcomes

Track only privacy-safe product metrics:

- commitments captured,
- commitments completed,
- false commitment corrections,
- useful whispers,
- dismissed whispers,
- answered asks with evidence,
- abstentions where evidence was insufficient,
- connector sync health,
- export/delete success.

## 9/10 acceptance criteria

| Test | Required result |
|---|---|
| Core workflow completion | Top 5 workflows complete in ≤3 taps after setup |
| Cognitive load study | ≥70% of beta users say Maestro reduced follow-up anxiety |
| Retention proxy | ≥50% of beta users use it 4+ days/week after week 3 |
| Willingness to pay | ≥30% of design partners say they would pay now |
| Surface discipline | Every screen has a clearly measured job |

---

# D. AI Intelligence — Target 9/10

## Current blockers

- LLM inactive in audit.
- Ablation benchmark: Full Maestro 0.500 vs BM25 0.550.
- Ask answers sometimes awkward and internally inconsistent.
- Evidence/counterevidence quality not yet reliable.

## Required work

### D1. Make LLM path production-real

- Configure OpenAI/Anthropic/local fallback in test and staging.
- Health-check provider at startup and expose clear degraded mode.
- Add circuit breakers, timeouts, and fallback tiers.
- Never silently claim AI when rule-based mode is active.

### D2. Build gold evaluation sets

Minimum datasets:

- 500 commitment extraction examples.
- 300 Ask Q&A examples.
- 150 abstention/impossible-question examples.
- 150 misleading/prompt-injection examples.
- 100 multi-turn memory/reasoning examples.
- 100 What Changed materiality examples.
- 50 Copilot meeting transcripts.

Each item needs expected answer, evidence, acceptable variants, and failure labels.

### D3. Fix evidence reasoning

- Separate supporting evidence from counterevidence.
- Never list the same item as both support and counterevidence unless explicitly explained.
- Add answer contract:
  - answer,
  - confidence,
  - evidence refs,
  - unknowns,
  - counterevidence,
  - what would change the answer,
  - decision boundary.

### D4. Prove cognitive-engine lift

Benchmarks must compare:

1. BM25 baseline.
2. Simple vector retrieval + LLM.
3. Maestro without Cognitive Council.
4. Maestro without Ask Ranker.
5. Maestro without Materiality Gate.
6. Full Maestro.

## 9/10 acceptance criteria

| Test | Required result |
|---|---|
| Ask benchmark | Full Maestro ≥15 points above BM25 |
| Simple RAG comparison | Full Maestro ≥8 points above simple RAG |
| Commitment extraction | Precision ≥0.90, recall ≥0.88 |
| Abstention | ≥0.92 correct abstention on impossible/unanswerable questions |
| Hallucination | ≤2% unsupported factual claims in gold set |
| Evidence accuracy | ≥0.92 cited evidence actually supports answer |
| Injection resistance | 0 critical prompt-injection leaks in 200-case suite |
| Latency with AI | p95 Ask ≤2.5s for normal questions, ≤5s for complex questions |

---

# E. Backend — Target 9/10

## Current blockers

- Personal backend tests fail.
- Monorepo backend tests fail/time out.
- Raw SQLite usage remains in connectors/copilot modules.
- Rate limiting disabled because `slowapi` missing.
- Demo mode and production behavior are mixed.

## Required work

### E1. Make tests clean and meaningful

- Fix all failing Personal backend tests.
- Fix monorepo backend test failure and timeout.
- Split suites:
  - unit,
  - integration,
  - live connectors,
  - load,
  - security,
  - mobile contract.
- CI must fail on any default-suite failure.

### E2. Formalize API contracts

- Generate OpenAPI schema.
- Validate mobile client against schema in CI.
- Add contract tests for every endpoint used by mobile.
- Version API paths.

### E3. Data integrity

- Replace raw SQLite calls with shared DB helper.
- Add WAL/busy timeout everywhere.
- Add migrations.
- Add transactional writes for signal ingestion and commitment ledger updates.
- Add idempotency keys for ingestion and draft actions.

### E4. Production readiness

- Enable rate limiting.
- Add background job queue for connector ingestion and AI processing.
- Add retry with backoff for provider APIs.
- Add observability:
  - request IDs,
  - trace IDs,
  - structured logs,
  - metrics,
  - alerts,
  - SLO dashboards.

## 9/10 acceptance criteria

| Test | Required result |
|---|---|
| Backend tests | 100% default suite pass |
| Mobile contract tests | 100% endpoints pass against current mobile client |
| Rate limiting | Active and tested for auth, Ask, connector ingestion, Copilot |
| DB consistency | No duplicate commitments under repeated ingestion |
| Conflict handling | Multi-device update conflicts resolve predictably |
| Observability | Every request traceable without leaking PII |
| Error recovery | Backend/DB/LLM/provider failure modes return actionable errors |

---

# F. Performance — Target 9/10

## Current blockers

- Backend rule-based local 10K Ask path is good, but mobile startup fails.
- Real LLM path inactive.
- No device FPS, CPU, memory, battery, or network benchmarks.

## Required work

### F1. Mobile performance instrumentation

Measure on real devices:

- cold launch,
- warm launch,
- time to interactive,
- tab switch latency,
- Ask submit-to-first-token,
- Ask submit-to-final-answer,
- connector sync state updates,
- Copilot whisper latency,
- memory usage,
- CPU,
- battery drain,
- network bytes.

### F2. Backend performance

- Keep 10K local Ask p95 <500ms in rule-based/retrieval path.
- Add AI latency budgets.
- Cache stable retrieval results.
- Stream long AI answers.
- Use async connector jobs.

## 9/10 acceptance criteria

| Metric | Target |
|---|---:|
| Mobile cold launch p95 | ≤3.0s |
| Mobile warm launch p95 | ≤1.0s |
| Tab transition p95 | ≤150ms |
| Screen API skeleton visible | ≤300ms |
| Ask rule/retrieval p95 | ≤700ms backend |
| Ask AI p95 | ≤2.5s simple, ≤5s complex |
| Copilot whisper p95 | ≤1.5s after relevant transcript chunk |
| Scroll FPS | 55–60 fps on mid-tier devices |
| Crash-free sessions | ≥99.8% beta |
| Battery drain during Copilot | acceptable vs Zoom/Meet benchmark, measured explicitly |

---

# G. Reliability — Target 9/10

## Current blockers

- Mobile does not launch.
- Backend tests fail.
- Copilot WS test fails.
- Connectors can silently fall back to mock data.

## Required work

### G1. Failure-mode matrix

Test each system with:

- network disabled,
- backend down,
- database locked,
- LLM unavailable,
- OAuth provider unavailable,
- token expired,
- refresh token revoked,
- microphone denied,
- storage denied/full,
- websocket disconnect,
- duplicate ingestion,
- multi-device writes.

### G2. User-visible recovery

- No silent failures for primary actions.
- Every failure gives:
  - what happened,
  - whether data was saved,
  - how to retry,
  - what Maestro will do automatically.

## 9/10 acceptance criteria

| Test | Required result |
|---|---|
| Crash-free beta sessions | ≥99.8% |
| Data loss | 0 known data-loss bugs in beta |
| Offline/reconnect | 100% primary screens degrade gracefully |
| Connector failures | Provider failures do not create false connected/synced states |
| Copilot disconnect | Reconnect or clear fallback mode shown within 2s |
| LLM failure | No hallucinated answer; fallback/abstain clearly shown |

---

# H. Security — Target 9/10

## Current blockers

- 14 mobile npm vulnerabilities.
- Rate limiting disabled.
- Demo connector connect with no OAuth.
- Token encryption fallback in dev path.
- OAuth state handling needs hardening.

## Required work

### H1. Dependency and supply-chain hardening

- Resolve high and moderate npm vulnerabilities.
- Add `npm audit --audit-level=high` CI gate.
- Add Python dependency scanning.
- Pin dependency ranges.
- Add SBOM.

### H2. Auth hardening

- Production must require per-user auth only.
- No bootstrap/shared token in production.
- Token rotation and revocation tested.
- SecureStore on mobile with optional biometric unlock.
- Enforce HTTPS in production.

### H3. OAuth hardening

- Use cryptographically random state nonce.
- Bind OAuth state to user session and expiration.
- Store OAuth tokens encrypted with production KMS/key.
- Test refresh, revocation, replay, disconnect, reconnect.

### H4. Abuse and injection defense

- Rate limit auth, Ask, connectors, Copilot.
- Prompt-injection suite against emails, Slack messages, GitHub issues, transcripts.
- Ensure malicious connector content cannot override system instructions.

## 9/10 acceptance criteria

| Test | Required result |
|---|---|
| High vulnerabilities | 0 high/critical in production deps |
| Rate limiting | Active and tested |
| OAuth CSRF | State replay/cross-user callback blocked |
| Cross-user isolation | 100% negative tests pass |
| Token storage | No plaintext production tokens |
| Prompt injection | 0 critical leaks/executions in 200+ adversarial cases |
| External pentest | No unresolved critical/high findings |

---

# I. Privacy — Target 9/10

## Current blockers

- Copilot consent says audio never leaves device, while audio uploads to backend.
- Demo/mock connector behavior can confuse user trust.
- Export/delete not fully execution-verified.

## Required work

### I1. Truthful consent and data flows

- Rewrite privacy copy to match actual behavior.
- If audio is uploaded, state:
  - what is uploaded,
  - where it goes,
  - how long it is retained,
  - whether it is used for model training,
  - how to delete it.
- Or actually perform on-device transcription and prove no audio egress.

### I2. Privacy controls

- Build visible Privacy Center:
  - connected data sources,
  - data categories,
  - last sync,
  - stored tokens status,
  - export data,
  - delete account,
  - revoke connector,
  - delete connector data,
  - Copilot consent history.

### I3. Data minimization

- Store extracted commitments and evidence refs, not unnecessary raw message bodies.
- User can inspect raw source snippets only when needed.
- Retention defaults are explicit.

## 9/10 acceptance criteria

| Test | Required result |
|---|---|
| Consent copy | Matches packet-level/data-flow reality |
| Delete account | Removes user data and tokens; verified by DB inspection/API |
| Export data | Complete, readable, available from mobile |
| Revoke connector | Stops sync and deletes/invalidates tokens |
| Mic permission | Denied permission produces safe fallback |
| Privacy review | No material undisclosed egress |

---

# J. Accessibility — Target 9/10

## Current blockers

- Some labels exist, but no real VoiceOver/TalkBack/Dynamic Type validation.
- Fixed layouts may break with large fonts.

## Required work

### J1. Accessibility implementation

- All touch targets ≥44x44 pt.
- All controls have meaningful labels/hints.
- Headings and landmarks structured.
- Support Dynamic Type / font scaling.
- Support reduced motion.
- Ensure contrast in light and dark modes.
- Keyboard/switch navigation for tablets.

### J2. Assistive tech testing

- VoiceOver on iOS.
- TalkBack on Android.
- Large text sizes.
- Reduced motion.
- High contrast.
- External keyboard.

## 9/10 acceptance criteria

| Test | Required result |
|---|---|
| WCAG contrast | AA minimum, AAA for primary text where feasible |
| VoiceOver | Top 5 workflows complete without sight |
| TalkBack | Top 5 workflows complete without sight |
| Dynamic Type | No clipped primary content at largest accessibility sizes |
| Reduced motion | No essential info depends on animation |
| Touch targets | 100% primary controls meet minimum size |

---

# K. Connectors — Target 9/10

## Current blockers

- Connectors mark connected with no OAuth.
- `oauth_configured: false` in audit.
- Ingestion used mock/demo data.

## Required work

### K1. Split demo and production modes

- Demo connectors must be clearly labeled “Demo.”
- Production builds must not show demo connector state as real connected state.
- If OAuth is not configured, the Connect button should say “Not available in this build,” not connect.

### K2. Real connector certification

For Gmail, Slack, GitHub, and Calendar:

- OAuth authorization URL.
- Callback exchange.
- Token encrypted storage.
- Refresh token flow where applicable.
- Disconnect.
- Provider revocation detection.
- Reconnect.
- Ingestion.
- Deduplication.
- Audit log.
- Approval-only write/draft flow.
- Provider-specific failure handling.

## 9/10 acceptance criteria

| Connector | Required proof |
|---|---|
| Gmail | Real OAuth, read messages, create draft only, no auto-send unless explicitly approved and policy allows |
| Slack | Real OAuth, read DMs/mentions, draft/send approval flow, revocation detection |
| GitHub | Real OAuth, read assigned issues/PRs, comment draft approval flow |
| Google Calendar | Real OAuth, read upcoming events, no write path if read-only |
| All | Token refresh/revoke/disconnect/reconnect/dedup/audit tests pass |

---

# L. Copilot — Target 9/10

## Current blockers

- Mobile could not launch.
- Backend Copilot WS test failed.
- Privacy copy contradicts audio upload.
- No live meeting benchmark executed.

## Required work

### L1. Stabilize transport

- Fix WebSocket lifecycle.
- Auth handshake must be reliable.
- REST fallback must be clearly shown.
- Reconnect should not duplicate transcript chunks.

### L2. Real transcription path

Choose one:

1. **On-device transcription** — then prove audio does not leave device.
2. **Server transcription** — then update consent and privacy controls.

### L3. Meeting benchmark

Run at least 30 meetings across:

- high-noise,
- technical discussion,
- sales call,
- executive meeting,
- multiple speakers,
- interruptions,
- poor internet,
- background noise.

Measure:

- transcript WER,
- commitment precision/recall,
- whisper usefulness,
- false interruptions,
- missed opportunities,
- summary quality,
- follow-up draft quality,
- latency,
- battery.

## 9/10 acceptance criteria

| Metric | Target |
|---|---:|
| Whisper latency p95 | ≤1.5s after relevant transcript chunk |
| Commitment extraction precision | ≥0.88 |
| Commitment extraction recall | ≥0.85 |
| Useful whisper rate | ≥80% human-rated useful |
| False interruption rate | ≤10% of whispers |
| Post-call summary usefulness | ≥4.2 / 5 average rating |
| Follow-up draft usefulness | ≥4.0 / 5 average rating |
| Reconnect duplication | 0 duplicate transcript chunks in failure tests |

---

# M. Scalability — Target 9/10

## Current blockers

- Local SQLite-oriented architecture needs clear production story.
- No verified 10, 100, 1,000, 10,000 user benchmark for the Personal mobile product.

## Required work

### M1. Define production architecture

- Decide SQLite-local vs hosted Postgres vs hybrid.
- Define sync model.
- Define job queue.
- Define vector/search storage.
- Define per-user encryption and tenant isolation.

### M2. Load tests

- 10 users: local sanity.
- 100 users: staging.
- 1,000 users: load/stress.
- 10,000 users: capacity planning.

## 9/10 acceptance criteria

| Load | Required result |
|---|---|
| 100 concurrent users | p95 API latency within SLO, no error spike |
| 1,000 users | Queue remains healthy; connector jobs backpressure correctly |
| 10,000 users | Capacity model validated; cost per active user known |
| Multi-device sync | Conflicts resolved without data loss |

---

# N. Competitive Positioning — Target 9/10

## Current blockers

- No fair competitor benchmark was executed.
- Current product cannot be compared because mobile does not launch.

## Required work

Create a blind evaluation against:

- ChatGPT,
- Claude,
- Perplexity,
- Notion,
- Apple Reminders,
- Apple Notes,
- Gmail,
- Slack,
- Superhuman,
- Linear,
- meeting intelligence tools.

Evaluate:

- commitment capture,
- evidence-backed answer quality,
- meeting follow-up,
- cognitive load reduction,
- mobile polish,
- privacy/trust.

## 9/10 acceptance criteria

| Category | Required result |
|---|---|
| Commitment tracking | Maestro wins or ties category leader |
| Evidence-backed personal Ask | Maestro wins or ties simple ChatGPT + uploaded context baseline |
| Meeting follow-up | Maestro rated ≥4/5 vs leading alternatives |
| Mobile polish | Test users rate Maestro within 10% of top-tier apps |
| Trust | Users understand what data was used and why |

---

## 3. Claim Verification Gates

Before claiming 9/10, every claim must be locked to an execution proof.

| Claim | Required proof |
|---|---|
| Personal intelligence layer | End-to-end user workflow across data, Ask, commitments, and follow-up |
| Commitment tracking | 500-case benchmark with precision/recall and lifecycle tests |
| Situation Engine | Demonstrably improves prioritization vs chronological/feed baseline |
| Ask Ranker | Beats BM25 by ≥15 points and simple RAG by ≥8 points |
| Cognitive Council | Ablation proves measurable lift |
| Learning Loop | User corrections change future behavior in controlled A/B test |
| Trusted Silence | Low false-positive + high critical-recall benchmark |
| Copilot | 30-meeting benchmark passes latency/usefulness gates |
| Gmail connector | Real OAuth + live/sandbox ingestion + token refresh + revoke |
| Slack connector | Real OAuth + live/sandbox ingestion + token refresh/revoke where applicable |
| GitHub connector | Real OAuth + assigned issue/PR ingestion + comment draft flow |
| Google Calendar connector | Real OAuth + event ingestion + revoke/reconnect |
| Privacy-first | Data-flow audit matches UX copy and runtime behavior |
| World-class latency | Device and backend SLO dashboards pass |
| World-class reliability | Chaos/failure matrix passes |

---

## 4. Release Gates

## Gate 1 — P0 Recovery

Maestro may enter internal dogfood only when:

- mobile starts on iOS and Android,
- all P0 privacy contradictions fixed,
- backend default tests pass,
- no high/critical dependency vulnerabilities,
- demo connector mode is clearly separated.

## Gate 2 — Private Beta

Maestro may enter private beta only when:

- real auth/account lifecycle works,
- at least one real connector is production-ready,
- AI evidence quality benchmark passes minimum bar,
- delete/export/revoke are verified,
- crash-free dogfood sessions ≥99.5%,
- no unresolved P0/P1 security findings.

## Gate 3 — Public Launch Candidate

Maestro may be considered launch-ready only when:

- all four claimed connectors are real and verified,
- Copilot passes 30-meeting benchmark,
- all weighted categories score ≥8.5 internally,
- external audit scores ≥9/10 overall,
- no P0/P1 blockers remain,
- claim matrix has no FALSE/NOT VERIFIED for public claims.

## Gate 4 — World-Class Certification

Maestro may claim world-class only when:

- every audit category scores ≥9/10,
- independent evaluator reproduces all benchmarks,
- competitor comparison shows at least one clear category leadership position,
- beta users demonstrate retention and willingness to pay,
- privacy/security review passes with no unresolved high risks.

---

## 5. Weekly Execution Plan

## Weeks 1–2: Mobile Launch and Truth

- Fix Expo plugin/startup failure.
- Fix `expo config` and `expo-doctor`.
- Remove or qualify false claims in app/docs.
- Add CI audit harness.
- Resolve npm high vulnerabilities.
- Separate demo connector mode.

**Exit:** Mobile launches reliably on iOS/Android simulator.

## Weeks 3–4: Mobile UX/UI Foundation

- Redesign onboarding/login.
- Implement production backend config.
- Rebuild primary navigation.
- Add complete state coverage.
- Add first device performance traces.

**Exit:** 10-user usability test: ≥8 complete top workflows without docs.

## Weeks 5–7: Backend Hardening

- Fix all Personal backend failures.
- Fix monorepo backend test failure or split unsupported code from launch scope.
- Remove raw SQLite violations.
- Enable rate limiting.
- Add API contract tests.
- Add structured observability.

**Exit:** Backend default CI green; mobile contract tests green.

## Weeks 8–11: Real Connectors

- Implement/verify Gmail OAuth end-to-end.
- Implement/verify Slack OAuth end-to-end.
- Implement/verify GitHub OAuth end-to-end.
- Implement/verify Google Calendar OAuth end-to-end.
- Add token refresh/revoke/disconnect/reconnect/dedup tests.
- Add connector-specific privacy controls.

**Exit:** All four connectors verified with real sandbox/live accounts.

## Weeks 12–15: AI and Cognitive Engine

- Activate real LLM provider in staging.
- Build gold datasets.
- Fix evidence/counterevidence contract.
- Run BM25/simple-RAG/full-Maestro ablations.
- Improve ranker/materiality/council until lift is real.
- Add hallucination, abstention, injection, and multi-turn tests.

**Exit:** Full Maestro beats BM25 and simple RAG by target margins.

## Weeks 16–19: Copilot

- Fix WS reliability.
- Resolve audio privacy implementation.
- Run 30-meeting benchmark.
- Improve whispers, summaries, follow-up drafts.
- Add poor network and noisy audio tests.

**Exit:** Copilot passes 30-meeting benchmark.

## Weeks 20–22: Security, Privacy, Accessibility, Performance

- External pentest pass.
- Privacy data-flow audit pass.
- VoiceOver/TalkBack/Dynamic Type pass.
- Device performance SLOs pass.
- Load tests to 1,000+ users and capacity model to 10,000 users.

**Exit:** No unresolved critical/high findings.

## Weeks 23–24: Private Beta and Re-Audit

- Recruit 20–50 real users.
- Measure retention, trust, usefulness, willingness to pay.
- Freeze claims to verified set.
- Run independent re-audit.

**Exit:** Every category ≥9/10 or do not ship.

---

## 6. Final Target Scorecard

| Category | Current audit score | 9/10 target condition |
|---|---:|---|
| Mobile UX | 1.0 | Launches reliably; first-minute experience is premium and clear |
| Mobile UI | 3.0 | Every screen polished, responsive, accessible, state-complete |
| Product Design | 3.0 | Core workflows measurably reduce cognitive load |
| AI Intelligence | 3.0 | Beats BM25/simple RAG, strong evidence, abstention, calibration |
| Backend | 4.0 | Clean tests, robust data integrity, rate limits, observability |
| Performance | 4.0 | Device/backend SLOs pass under realistic loads |
| Reliability | 2.0 | Chaos/failure matrix passes; no data loss/crash patterns |
| Security | 2.0 | No high vulns, hardened auth/OAuth, prompt-injection resistance |
| Privacy | 2.0 | Truthful consent, verified delete/export/revoke, no undisclosed egress |
| Accessibility | 3.0 | VoiceOver/TalkBack/Dynamic Type/contrast pass |

**Target:** every category ≥9.0, not merely weighted average ≥9.0.

---

## 7. Non-Negotiables

1. Do not claim “real OAuth connector” unless a real provider flow was executed.
2. Do not claim “audio never leaves device” if audio is uploaded.
3. Do not claim “AI” when the system is in rule-based fallback.
4. Do not claim “world-class latency” without device and real-AI measurements.
5. Do not claim “trusted silence” without false-positive and critical-recall benchmarks.
6. Do not ship with mobile startup failure.
7. Do not ship with known high vulnerabilities.
8. Do not ship with failing default backend tests.
9. Do not treat docs or architecture diagrams as evidence.
10. Do not optimize for feature count; optimize for trust, speed, reliability, and usefulness.
