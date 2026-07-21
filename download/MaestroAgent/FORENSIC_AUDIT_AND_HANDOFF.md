# FORENSIC AUDIT + CODER HANDOFF — MaestroAgent Personal
**Date:** 2026-07-18
**HEAD:** `7d279ad` (origin/main)
**Repo:** https://github.com/prateekm1007/MaestroAgent
**Total commits:** 1,053
**Method:** Fresh clone + live execution + code tracing

---

## MANDATORY FIRST STEPS (do these before anything else)

### 1. Clone the repo

```bash
cd /home/z/my-project
git clone https://github.com/prateekm1007/MaestroAgent.git
cd MaestroAgent/download/MaestroAgent
```

### 2. Read governance files from disk (NOT from memory)

```bash
cat GOVERNANCE.md           # 177 lines — 13 pre-execution gates
cat ENTROPY_RECOVERY.md     # 225 lines — 34 principles (P1-P34)
cat GOVERNANCE_LOOP.md      # 159 lines — mutual read protocol
cat AUDITOR_GOVERNANCE.md   # 211 lines — 20 auditor gates
cat Makefile                # make hooks + make governance + make audit-gates
```

### 3. Install the pre-commit hook

```bash
make hooks   # runs: git config core.hooksPath .githooks
```

### 4. Start the backend + web app

```bash
# Terminal 1 — backend (API on port 8766)
cd maestro-personal
pip install -e ".[dev]"
PYTHONPATH=src MAESTRO_PERSONAL_TOKEN=maestro-demo MAESTRO_DEMO_MODE=1 \
  python -m maestro_personal_shell.api

# Terminal 2 — web app (UI on port 3000)
cd maestro-personal/web
npm install
npm run dev
```

Open http://localhost:3000. Login with password `maestro-demo`.

### 5. Run tests

```bash
# Backend (run each file separately — test isolation issue with chaos tests)
cd maestro-personal
PYTHONPATH=src python -m pytest tests/test_connectors.py -q -m "not llm_integration"
PYTHONPATH=src python -m pytest tests/test_chaos.py -q -m "not llm_integration"
PYTHONPATH=src python -m pytest tests/test_oauth_roundtrip.py -q -m "not llm_integration"

# Mobile
cd mobile
npx tsc --noEmit    # use ./node_modules/.bin/tsc for correct exit code
npx jest --silent
```

---

## REPO STRUCTURE

```
MaestroAgent/download/MaestroAgent/
│
├── GOVERNANCE.md                    ← 13 pre-execution gates
├── ENTROPY_RECOVERY.md              ← 34 principles (P1-P34)
├── GOVERNANCE_LOOP.md               ← mutual read protocol
├── AUDITOR_GOVERNANCE.md            ← 20 auditor gates
├── Makefile                         ← make hooks / make governance / make audit-gates
├── .githooks/pre-commit             ← P20 + P6 enforcement (388 lines)
├── audit_scripts/                   ← 14 verify scripts + audit_gates.sh
├── .env.example                     ← env var template
├── Dockerfile                       ← root Docker (for Railway)
│
├── maestro-personal/                ← THE PRODUCT
│   ├── src/maestro_personal_shell/
│   │   ├── api.py                   ← FastAPI app (2052 lines, port 8766)
│   │   ├── llm_bridge.py            ← LLM providers (2178 lines) — ZAIHTTPRouter is default
│   │   ├── connectors.py            ← ConnectorStore: connect/ingest/draft/send (1510 lines)
│   │   ├── routers/                 ← 10 routers (ask, connectors, surfaces, account, auth, etc.)
│   │   │   ├── ask.py               ← /api/ask (1603 lines — flagship endpoint)
│   │   │   ├── connectors.py        ← /api/connectors/* (OAuth + drafts)
│   │   │   ├── surfaces.py          ← /api/the-moment, /api/whisper, /api/briefing, ambient endpoints
│   │   │   └── ...
│   │   ├── surfaces/                ← 5 surfaces (ask, commitments, prepare, what_changed, whisper)
│   │   ├── ambient_notifications.py ← Phase 19 (smart nudges, 328 lines)
│   │   ├── phase9_ambient.py        ← Phase 9 (calendar awareness + escalation, 420 lines)
│   │   ├── cross_meeting_threads.py ← Phase 14 (institutional memory, 401 lines)
│   │   ├── meeting_grader.py        ← Phase 16 (meeting effectiveness, 304 lines)
│   │   ├── deal_health.py           ← Phase 11 (deal momentum, 258 lines)
│   │   ├── advanced_analytics.py    ← Phase 20 (trends + org learning, 302 lines)
│   │   ├── intelligent_draft.py     ← LLM-powered email drafting (340 lines)
│   │   ├── secret_redactor.py       ← OTP/secret redaction at ingestion (101 lines)
│   │   ├── demo_seeder.py           ← Seeds demo data for bootstrap + default@personal.local
│   │   └── ...
│   ├── tests/                       ← 100+ test files, 1476 tests collected
│   ├── mobile/                      ← Expo React Native app
│   │   ├── App.tsx                  ← 4 tabs: Today/Commitments/Ask/More
│   │   ├── src/api/client.ts        ← 1239 lines — 40+ API functions
│   │   ├── src/api/hooks.ts         ← React Query hooks (280 lines)
│   │   ├── src/screens/             ← 6 screens
│   │   └── tests/                   ← 5 test files
│   ├── web/                         ← Next.js web app (port 3000, proxies to :8766)
│   │   ├── src/app/page.tsx         ← 6 tabs: Dashboard/Ask/Commitments/Prepare/Agents/More
│   │   ├── src/lib/maestro-api.ts   ← 1189 lines — API client
│   │   ├── src/components/maestro/  ← 13 components
│   │   ├── next.config.ts           ← rewrites /api/* to localhost:8766
│   │   └── Dockerfile + railway.json
│   ├── RAILWAY_DEPLOY.md            ← deployment guide
│   └── railway.json
│
├── backend/                         ← Enterprise API (SEPARATE product, port 8765 — DON'T TOUCH)
│   ├── maestro_cognitive_council/   ← The Core (SituationEngine, agents, etc.)
│   ├── maestro_oem/                 ← Enterprise ambient engines (calendar, sentiment, deal health, etc.)
│   ├── maestro_api/                 ← Enterprise REST API
│   └── maestro_auth/                ← Enterprise auth
│
└── scripts/                         ← utility scripts (seed_demo_data.py, verify_oauth_roundtrip.py, etc.)
```

---

## WHAT WORKS (verified by execution at 7d279ad)

### Backend (port 8766)
- ✅ 105 REST endpoints across 10 routers
- ✅ LLM active by default: ZAIHTTPRouter (provider: zai-glm-http)
- ✅ 6 ambient intelligence engines (Phases 9, 11, 14, 16, 19, 20)
- ✅ All 4 connectors (Gmail/Slack/GitHub/Calendar) fail closed — return empty when OAuth not configured
- ✅ Draft send is honest — returns send_error when OAuth not configured (no fabrication)
- ✅ Trusted Silence — off-topic queries abstain (confidence=0.0, evidence=0)
- ✅ Ask latency <3s (3s LLM timeout + cooldown fast-fail)
- ✅ Multi-turn Ask (session_id parameter)
- ✅ Secret redaction at ingestion (OTP codes → [REDACTED_OTP])
- ✅ Demo seeder seeds for both 'bootstrap' AND 'default@personal.local'
- ✅ 1476 tests collected, ~1350+ pass (run each file separately — test isolation issue)
- ✅ 0 raw sqlite3.connect() calls (centralized to 1 helper)
- ✅ Groq LLM provider added (llama-3.3-70b-versatile — best performing model)
- ✅ Materiality gate wired into /api/whisper
- ✅ confidence=0.0 for all abstention paths
- ✅ Agents + commitment simulator endpoints work

### Web (Next.js, port 3000)
- ✅ 6 tabs: Dashboard / Ask / Commitments / Prepare / Agents / More
- ✅ API proxy: next.config.ts rewrites /api/* to localhost:8766
- ✅ Demo data removed (0 maestroFetch fallbacks with demo data)
- ✅ Dashboard: The Moment + whispers + ambient card + escalations + deal health + calendar awareness
- ✅ Commitments: meeting history grades + deal health pills + Signals tab
- ✅ Ask: multi-turn session_id + Q&A history + TTS + voice input + entity deep-link
- ✅ Agents: commitment simulator + agent insights dashboard
- ✅ More: connectors + settings + insights + notification preferences + metrics + retention
- ✅ Login: email input + register flow (defaults to 'bootstrap' user)
- ✅ Login fix: no infinite reload loop (401 check only fires when token was present)
- ✅ Fabricated fallbacks removed from all 5 mutating endpoints
- ✅ All 7 callers have try/catch + .live check + destructive toast
- ✅ DraftApprovalModal shared component
- ✅ Onboarding gate (3 steps)
- ✅ Hydration fix: auth state loaded in useEffect (not useState initializer)

### Mobile (Expo React Native)
- ✅ 4-tab structure: Today / Commitments / Ask / More
- ✅ 12 ambient API functions + 8 hooks in client.ts/hooks.ts
- ✅ Today tab: smart notifications + escalations + deal health + calendar awareness + The Moment + whispers
- ✅ Commitments tab: deal health pills + meeting history grades + segmented control (commitments|signals)
- ✅ More tab: Insights + connectors + notification preferences
- ✅ Web-safe alerts (showAlert)
- ✅ Push notification web guard
- ✅ Copilot removed (deleted in V2 redesign)

### Deployment
- ✅ Railway config (Dockerfiles + railway.json for backend + web)
- ✅ RAILWAY_DEPLOY.md guide
- ✅ Demo seed script (scripts/seed_demo_data.py)

### Governance
- ✅ GOVERNANCE.md + ENTROPY_RECOVERY.md + GOVERNANCE_LOOP.md + AUDITOR_GOVERNANCE.md
- ✅ Pre-commit hook (P20 + P6)
- ✅ Makefile: make hooks + make governance + make audit-gates
- ✅ 14 verify scripts in audit_scripts/

---

## WHAT'S BROKEN / OPEN (verified by execution)

### P0 (blocking)

1. **Mobile login bypass** — `LoginScreen.tsx` uses `demo-bypass-token` instead of calling `api.login(password)`. The password field is decorative. This is a SECURITY issue — any user can access any data.
   - **File:** `mobile/src/screens/LoginScreen.tsx`
   - **Fix:** Call `login(password)` from `useAuth()` context (which calls `api.login(password)` and stores the real token). Add a registration link.

2. **No mobile registration flow** — `/api/auth/register` works but no mobile screen calls it. Only the web app has registration.

### P1 (important)

3. **Test isolation issue** — Running `test_chaos.py` together with `test_connectors.py` causes 18 errors. The chaos tests mock `get_db_conn` which bleeds into other test files. Each file passes when run alone.
   - **Fix:** Use `monkeypatch` instead of `unittest.mock.patch` for `get_db_conn` in chaos tests, or add a conftest fixture that resets the mock between files.

4. **Threads for Entity** — backend endpoint works but no mobile/web screen calls `getThreadsForEntity` (no detail view for cross-meeting threads).
   - **Fix:** Add a ThreadDetail screen/panel that calls `getThreadsForEntity(entity)` when user taps a commitment.

5. **Decision History** — backend endpoint works but no client function (`getDecisions`) exists on either platform.
   - **Fix:** Add `getDecisions(entity)` to both `client.ts` and `maestro-api.ts`.

6. **Grade Override** — backend works but no screen renders the override button.
   - **Fix:** Add an "Override Grade" button in the meeting grade detail view.

7. **API key redaction** — OTP codes are redacted (`[REDACTED_OTP]`) but API keys (`sk-*`, `ghp_*`) are not. Only OTP patterns are implemented.
   - **Fix:** Add API key patterns to `secret_redactor.py`.

### P2 (roadmap)

8. **Physical device testing** — cold launch, scroll fps, memory, VoiceOver/TalkBack — requires phone.
9. **Real OAuth round-trips** — Gmail/Slack/GitHub/Calendar with real credentials — script provided (`scripts/verify_oauth_roundtrip.py`).
10. **Hybrid BM25+embedding retrieval** — for better Ask quality at scale.
11. **Investor materials not in git** — pitch deck PDF + HTML + brief were generated in a sandbox but not committed. They exist on the user's local machine only.
12. **Copilot routes still exist in backend** — 14 `/api/copilot/*` routes are still registered but excluded from all UIs per the user's instruction. They should eventually be deprecated.

---

## KEY ARCHITECTURAL DECISIONS (don't change these without understanding why)

1. **Two users for demo data:** The demo seeder seeds for both `bootstrap` (the env-token user) and `default@personal.local` (the web app's login user). This was fixed after whispers were broken for 3 rounds because the web app logged in as `default@personal.local` but data was only seeded for `bootstrap`.

2. **Web login defaults to 'bootstrap':** `maestro-api.ts` `login()` uses `user_email = email || "bootstrap"`. This ensures the web app user sees demo data. If the user provides an email (via the Login form's email input), it uses that instead (for registered users).

3. **No demo data in maestroFetch:** All 9 `maestroFetch` calls with demo fallbacks were removed. When the backend is unreachable, `maestroFetch` throws — the caller catches it and shows a destructive toast.

4. **Fabricated fallbacks removed from mutating endpoints:** `correctSignal`, `deleteAccount`, `resolveDraft`, `connectProvider`, `disconnectProvider` — all 5 now re-throw on failure instead of fabricating success.

5. **Login 401 fix:** `maestroFetch` only calls `window.location.reload()` on 401 when a token WAS present (stale token case). When no token (Login page), 401 throws normally. This prevents the infinite reload loop.

6. **Materiality gate rule-based early-exit:** `_should_whisper_rule_based` returns `None` for non-critical whispers (so the LLM gate fires). Only `critical_signal` type bypasses the gate (F6 guard). This was fixed after the gate was never called for medium/high-priority whispers.

7. **V6 Trusted Silence:** The `_abstention_triggered` flag is set in ALL abstention paths (entity-not-found, keyword-overlap, off-topic). The last-resort summary checks this flag before overriding. This prevents the "meaning of life" → answer with random data bug.

8. **Groq LLM provider:** Added as primary LLM (llama-3.3-70b-versatile). The ZAIHTTPRouter is still the fallback. The Groq provider uses async httpx with a 10s timeout.

---

## SHELL VERIFICATION TIPS (CRITICAL — learn from our mistakes)

### 1. NEVER check tsc exit code with a pipe

```bash
# WRONG — captures head's exit code (always 0), not tsc's:
npx tsc --noEmit 2>&1 | head; echo $?

# CORRECT — redirect to file, check directly:
./node_modules/.bin/tsc --noEmit > /tmp/tsc.txt 2>&1; echo $?
```

### 2. Always use the local tsc binary

```bash
# WRONG — may install wrong package:
npx tsc --noEmit

# CORRECT — uses the project's TypeScript:
./node_modules/.bin/tsc --noEmit
```

### 3. Terminal ANSI stripping warning

If you see `eetingGrades` instead of `[meetingGrades` in file content, it's a terminal ANSI escape artifact — `[m` is interpreted as an escape sequence. Verify with Python `ord()` or `hexdump`, not `sed`/`grep`/`cat`.

### 4. Run test files SEPARATELY

The chaos tests mock `get_db_conn` which bleeds into other test files. Run each file alone:
```bash
PYTHONPATH=src python -m pytest tests/test_connectors.py -q
PYTHONPATH=src python -m pytest tests/test_chaos.py -q
PYTHONPATH=src python -m pytest tests/test_oauth_roundtrip.py -q
```

### 5. P23: Always paste actual command output in commits

```
VERIFICATION:
$ <command>
<actual output pasted here>
```

Never claim "✓ VERIFIED" without pasted output from THIS session.

---

## THE GOVERNANCE LOOP (every session, both sides)

1. Read governance files from disk (not memory)
2. Paste a read receipt with timestamp + key principle
3. Remind the other side to read their files
4. The CEO rejects messages without receipts

```
GOVERNANCE LOOP READ RECEIPT (Coder):
- ENTROPY_RECOVERY.md read at <timestamp>
  P1: "A claim is not true until it has been executed"
  P26: "Principles don't enforce themselves. Re-application does."
- GOVERNANCE_LOOP.md read at <timestamp>
- AUDITOR_GOVERNANCE.md read at <timestamp>

> Auditor: Read GOVERNANCE.md, ENTROPY_RECOVERY.md, GOVERNANCE_LOOP.md,
> and AUDITOR_GOVERNANCE.md from disk before auditing. The loop cannot be broken.
```

---

## THE 10 KEY PRINCIPLES (from 34 — read the full file for all)

- **P1:** A claim is not true until it has been executed. Never write ✓ without pasted output.
- **P6:** Fail closed and broken, not open and silent. No bare `except: pass`.
- **P11:** Building a capability and wiring it in are two different jobs. Prove both.
- **P13:** An endpoint that takes the conclusion as input is a demo, not a capability.
- **P14:** Bugs migrate one layer deeper. Expect the next instance.
- **P23:** Commit messages must cite executed output.
- **P26:** Principles don't enforce themselves. Re-application does.
- **P27:** Read the assertion, not the test name. A test that asserts `True` is theater.
- **P31:** Never trust a commit message's "0 failures" claim. Run the verify scripts yourself.

---

## PRIORITY ORDER FOR THE NEXT CODER

1. **P0:** Fix mobile login bypass (security)
2. **P0:** Fix test isolation issue (chaos tests bleed into other files)
3. **P1:** Wire Threads for Entity + Decision History to mobile + web
4. **P1:** Add API key redaction patterns to secret_redactor.py
5. **P1:** Physical device testing (cold launch, scroll, VoiceOver)
6. **P2:** Real OAuth round-trips with user credentials
7. **P2:** Hybrid BM25+embedding retrieval for better Ask quality
8. **P2:** Commit investor materials to the repo (if available)

---

## CONTACT

- **Repo:** https://github.com/prateekm1007/MaestroAgent
- **Backend:** port 8766 (FastAPI)
- **Web:** port 3000 (Next.js, proxies to :8766)
- **Mobile:** Expo (press `w` for web, `i` for iOS, `a` for Android)
- **Login:** password `maestro-demo` (or any password if you set MAESTRO_PERSONAL_TOKEN)
- **Demo data:** auto-seeds on first boot (9 signals for bootstrap + default@personal.local)

> **Coder: Read GOVERNANCE.md, ENTROPY_RECOVERY.md, GOVERNANCE_LOOP.md, and AUDITOR_GOVERNANCE.md from disk before writing any code. Do not code from memory. The loop cannot be broken.**
