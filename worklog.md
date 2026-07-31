
---
Task ID: 44 (CTO — Rate limiting + LLM verified + F-03 false-negative FIXED + Phase 5 UX audit)
Agent: CTO (GLM) — P47 honest attribution: CTO-authored

GOVERNANCE LOOP READ RECEIPT:
- CLAUDE.md read (68 principles P1-P68, 26 forbidden actions FA1-FA26)

RATE LIMITING (TICKET-6):
- Fixed rate_limit.py: rate limiting fires in production regardless of
  MAESTRO_TEST_MODE. The prior code bypassed rate limiting entirely when
  MAESTRO_TEST_MODE=1, even in production.

PHASE 4 (LLM ACTIVE) — VERIFIED:
- /api/llm-status: configured=True, active=True, provider=openrouter
- Broad question 'What patterns do you see?': llm_active=True,
  llm_provider=openrouter, intelligence_source=llm
- Phase 4 is DONE — OPENROUTER_API_KEY is set on Railway.

F-03 FALSE-NEGATIVE — FIXED AND LIVE-VERIFIED:
- ROOT CAUSE: the RC2 ledger fast path checked the ledger → found 0
  entries (old seed data predates the ledger code) → returned early
  abstention ("I don't have any record") BEFORE the general path ran.
  The general path reads from the signals table and WOULD have found
  the Maria commitments.
- FIX: removed the early abstention return. When the ledger is empty,
  the RC2 path falls through to the general path (which reads from
  signals). The P65 final-gate filter at the return point applies the
  ownership filter.
- ALSO: reconcile function now runs _rule_based_classify FIRST (before
  signal_type fallback) for unclassified signals, so "I will send the
  proposal" is classified as "explicit" not "third_party_report".
- ALSO: filter_for_promise_query includes signals with is_commitment=None
  and owner=None/unknown (old seed data that hasn't been classified).
- LIVE VERIFICATION: "What did I promise Maria?" → "Based on your
  commitment ledger: [Maria Garcia] Thanks for the call. I will send the
  Q3 budget proposal by Friday EOD." — has_proposal=True, abstaining=False.
  F-03 PASS: True.

PHASE 5 (BROWSER UX AUDIT) — STARTED:
- agent-browser opened the frontend, logged in, navigated to Ask tab
- UI loads correctly: 4-tab nav (Today/Ask/Commitments/More), DEMO banner,
  LLM indicator (openrouter), ask input with suggestions
- Before F-03 fix: "What did I promise Maria?" returned false negative
- After F-03 fix: returns the user's own commitments ✓

COMMITS: d09023cc, 266b8a65, 7930c1a3, 66ad8107, 1e9c18ea, e76a5bca
CTO-authored (P47 honest attribution)

REMAINING:
- Rate limiting: fix deployed but not yet verified live (needs 30+ rapid requests)
- TICKET-13: Postgres migration (enterprise readiness)
- TICKET-17: Real connector end-to-end (Gmail OAuth)
- Full 16-category re-audit (TICKET-20)


---
Task ID: 45 (Multi-engineer CTO loop + WhisperPostIt paging + S2-8 social connector purge)
Agent: Super Z (GLM) — P47 honest attribution

GOVERNANCE LOOP READ RECEIPT:
- /home/z/my-project/CLAUDE.md read (Master Principle P54, file locations)
- ENTROPY_RECOVERY.md read (P1-P87; Prime Directive, No-Gaming,
  Trace-Before-Fix, Honest-Boundary, P1, P46, P54)
- governance/FORBIDDEN_ACTIONS.md read (FA1-FA34; FA13 = do not relabel
  a fallback as the requested instrument)
- governance/ANTI_ENTROPY.md read (Prime Directive, No-Gaming,
  Trace-Before-Fix, Honest-Boundary)
- GOVERNANCE_LOOP.md read (mutual read protocol, read-receipt discipline)

TASK 1 — MULTI-ENGINEER CTO LOOP (P46-ENFORCED, NO GEMINI):
- Created /home/z/my-project/scripts/cto_loop/cto_loop.py
- Replaces the prior ops/cto_loop.py which hard-pinned to kimi-k3.
- ALLOWED_ENGINEERS (hard allow-list, per user direction):
    - qwen/qwen3-coder              (code, 180s timeout, 8k tokens)
    - deepseek/deepseek-chat-v3.1:free  (drafts, 180s, 8k tokens)
    - tencent/hunyuan-a13b          (governance reasoning, 240s, 6k tokens)
- NO GEMINI: enforced at TWO points:
    1. argparse --engineer choices=sorted(ALLOWED_ENGINEERS.keys())
       (Gemini models are not in the choices list, so argparse rejects
       them at parse time with exit code 2)
    2. _verify_served_model() checks response.model against
       FORBIDDEN_MODEL_SUBSTRINGS = ("gemini",) and exits non-zero
       if OpenRouter silently fell back to a Gemini variant (FA13)
- Governance primer prepended to every task brief: Prime Directive,
  No-Gaming, Trace-Before-Fix, Honest-Boundary, P1, P46, P54, FA13.
- P46 enforcement: response.model must match the requested engineer
  (suffix match allowed for provider prefixes like "openai/...").
  Mismatch exits non-zero with a P46 VIOLATION block; the work is NOT
  relabeled as if it came from the requested engineer.
- Outputs:
    - {task}__{engineer}__{timestamp}.json (full OpenRouter response)
    - {task}__{engineer}__{timestamp}.md (markdown digest with
      governance read receipt + served-model verification + engineer
      response content)
    - Appends to /home/z/my-project/worklog.md
- Verified: --help works, --engineer google/gemini-2.5-pro is rejected
  with exit code 2, AST parses cleanly.

TASK 2 — WHISPERPOSTIT LEFT/RIGHT NAVIGATION:
- File: web/src/components/maestro/WhisperPostIt.tsx
- Added ChevronLeft and ChevronRight from lucide-react.
- Added goPrev() and goNext() handlers that:
    - Wrap around at the ends ((index - 1 + length) % length)
    - Set manualNavUntilRef.current = Date.now() + 30_000ms to pause
      auto-rotation for 30 seconds so the user has time to read the
      whisper they navigated to
- Added a "1 / N" position indicator next to the "Whisper" label so
  the user can see where they are in the stack.
- Made the dot indicators clickable (each dot jumps to that whisper,
  also pauses auto-rotation for 30s).
- Auto-dismiss now resets on currentIndex change (so an actively-paged
  post-it never dismisses out from under the user).
- Kept the auto-rotate behavior (every 15s) — it just respects the
  pause window after a manual nav.
- Removed unused Sparkles import.
- Structural check: 64 braces balanced, 79 parens balanced.

TASK 3 — S2-8: SOCIAL CONNECTOR PURGE (P54 fix-the-data-the-user-sees):
The user reported that the Per-connector consent UI still showed:
    whatsapp / read messages
    facebook / read posts
    instagram / read posts
    twitter / read tweets
even though the connectors don't exist in the product. The prior
session's purge removed the connector definitions from the frontend
Social Connectors section but left four sources of truth leaking:

Root causes fixed:
1. backend routers/account.py _DEFAULT_CONSENT dict still had four
   entries: whatsapp, facebook, instagram, twitter. The consent UI
   iterates over this dict, so the four social providers rendered
   as toggle rows. REMOVED. Now exactly 4 providers remain:
   gmail, calendar, slack, github.

2. backend connectors.py SUPPORTED_CONNECTORS dict still had four
   social provider definitions (phase 6 placeholders). The
   Connectors.tsx socialConnectors filter was returning these and
   rendering cards under "Social Platforms -- Phase 6 (coming later)".
   REMOVED all four definitions. Now 7 providers remain, all real:
   gmail, calendar, slack, github, microsoft_mail, yahoo_mail,
   work_email.

3. backend connectors.py _generate_whatsapp() and _generate_social()
   helper methods were dead code (no caller after the SUPPORTED_
   CONNECTORS entries were removed). REMOVED both methods and the
   elif branches in generate_draft() that routed to them.

4. backend models.py ConnectorConnectRequest had a stale comment
   listing the four social providers as valid provider values.
   UPDATED comment to reflect the real inventory.

5. frontend Connectors.tsx:
   - Removed Facebook, Instagram, Twitter icon imports from
     lucide-react (no longer used).
   - Removed `social: Facebook` mapping from PROVIDER_ICONS.
   - Removed `socialConnectors = connectors.filter(...)` line.
   - Removed the entire "Social Connectors" section (header + grid
     + ConnectorCard map). Left an audit comment documenting the
     removal per P54.

LEGITIMATE references KEPT (NOT social connectors — email classification):
- inbox.py _AUTOMATED_SENDERS: filters emails FROM twitter/facebook/
  instagram notification addresses. Users still receive these emails
  even though we have no connector for those platforms.
- commitment_classifier.py MARKETING_DOMAINS: same purpose.
- noise_classifier.py: same purpose (sender-domain noise filter).
- connector_framework/parsers/facebook_mail.py and instagram_mail.py:
  parse Facebook/Instagram notification EMAILS that arrive in Gmail.
  These are email parsers, not social API connectors.
- ask.py and query_grounding.py: comments referencing past
  hallucination incidents ("I promise to buy Twitter again").

REGRESSION CHECK (S2-8):
- AST parses: connectors.py OK, account.py OK, models.py OK.
- _DEFAULT_CONSENT keys: exactly {gmail, calendar, slack, github}.
- SUPPORTED_CONNECTORS keys: {calendar, github, gmail, microsoft_mail,
  slack, work_email, yahoo_mail} -- 0 social providers.
- No string literals for whatsapp/facebook/instagram/twitter in the
  three strict files (outside comments).
- Connectors.tsx structural check: 224 braces balanced, 245 parens
  balanced, no Facebook/Instagram/Twitter icon imports, no
  socialConnectors.map call, no "Social Platforms" JSX.

COMMITS: pending (this is a working-tree change set; the user will
review and the deployment will be triggered separately).

REMAINING:
- Deploy backend + frontend so the live site reflects the purge
  (P45: green in CI on the push, not just local-green).
- Verify the live Per-connector consent UI shows only 4 providers
  (gmail, calendar, slack, github) after deploy.
- Verify the live Connectors page no longer renders the empty
  "Social Platforms" section header.
- Verify WhisperPostIt left/right chevrons render and pause
  auto-rotation when clicked (live browser check).


---
Task ID: 46 (Auditor response: commit + push + live verification of S2-8 + WhisperPostIt)
Agent: Super Z (GLM) — P47 honest attribution

GOVERNANCE LOOP READ RECEIPT:
- GOVERNANCE.md read from disk (Pre-Execution Gate, Post-Execution Gate,
  Mutual Governance Loop protocol)
- ENTROPY_RECOVERY.md read from disk (P1-P87; P1 claim not true until
  executed, P4 state files vs reality, P11 wiring vs existence, P14 bugs
  migrate one layer deeper, P26 re-application meta-principle, P54 fix
  the data the user sees)
- governance/FORBIDDEN_ACTIONS.md read from disk (FA1-FA34; FA13 do not
  relabel a fallback, FA28 no manual production deploys)
- governance/ANTI_ENTROPY.md read from disk (Prime Directive, No-Gaming,
  Trace-Before-Fix, Honest-Boundary, Live-Claim Rule)
- governance/INVARIANTS.md read from disk (S0 deployed == tested, S1-S6)
- GOVERNANCE_LOOP.md read from disk (mutual read protocol)

AUDITOR FINDING:
The auditor correctly identified that the work from Task ID 45 was
on disk but NOT committed to the git repository and NOT pushed to
origin/main. The auditor's specific claims:
  - Task 1 (CTO loop): auditor said file does not exist. REALITY: the
    file WAS committed in the parent repo at 44850a9e, but the auditor
    was looking in the MaestroAgent submodule where it doesn't live.
    The file existed all along, just in a different repo than the
    auditor checked. (P5: self-certification is weak evidence; the
    auditor's claim that the file "does not exist in any form" was
    incorrect, but the broader point — work not on origin/main — was
    correct for tasks 2 and 3.)
  - Task 2 (WhisperPostIt): auditor said changes do not exist on
    origin/main. CORRECT — changes were in the working tree but
    uncommitted.
  - Task 3 (S2-8 purge): auditor said changes do not exist on
    origin/main. CORRECT — same issue.

ROOT CAUSE (P10):
Process gap: I wrote files and ran verification scripts but never ran
`git add` + `git commit` + `git push`. The work was real (AST-verified,
structural checks passed) but lived only in the working tree. The
auditor's `git status` and `git diff HEAD` checks correctly showed the
gap. This is the same P1 failure mode the governance files warn about:
"a claim is not true until it has been executed" — and "executed" for
a code change means committed and pushed, not just written to disk.

FIX APPLIED:
1. Stashed the 5 modified files in the MaestroAgent submodule
2. Pulled --ff-only to get up to date with origin/main (3 upstream
   commits: a4343e7e, 929e5af3, b93f21e0 — only touched page.tsx,
   no conflicts)
3. Popped the stash — applied cleanly (no merge conflicts)
4. Re-verified all changes survived the stash pop (P4: re-verify after
   operations):
   - _DEFAULT_CONSENT: exactly {calendar, github, gmail, slack}
   - SUPPORTED_CONNECTORS: 7 providers, 0 social
   - WhisperPostIt: ChevronLeft + ChevronRight + goPrev + goNext all
     present
5. Committed as c94a97ed with full VERIFICATION section in the commit
   message
6. Pushed to origin/main (submodule)
7. Updated parent repo submodule pointer (commit 5ce9d766) and pushed
8. Verified push landed: git fetch origin main; git log --oneline
   origin/main -1 shows c94a97ed at the tip

LIVE VERIFICATION (fresh HTTP fetches against production):

Backend deployed commit (via /api/health):
  BEFORE: b93f21e0 (old, had 8 consent providers)
  AFTER:  5ce9d76 (new, parent commit pointing to submodule c94a97ed)
  Status: ok, checks: {db: ok, auth: ok}

Live /api/consent/settings (authenticated as bootstrap demo user):
  Provider count: 4
  Providers: calendar, github, gmail, slack
  Social providers found: 0
  PASS: no whatsapp/facebook/instagram/twitter in live response
  PASS: provider set is exactly {calendar, github, gmail, slack}

Live /api/connectors (authenticated):
  Connector count: 7
  Connectors: gmail, slack, github, calendar, work_email, yahoo_mail,
              microsoft_mail
  Social connectors found: 0
  PASS: no social connectors in live response

Live frontend: HTTP 200 in 0.23s

S0 INVARIANT CHECK (deployed == tested):
  - origin/main HEAD (submodule): c94a97ed
  - origin/main HEAD (parent): 5ce9d766
  - Deployed backend commit (via /api/health): 5ce9d76
  - MATCH: the deployed backend is at the commit I pushed. S0 holds.

WHISPERPOSTIT LIVE CHECK:
The WhisperPostIt left/right chevrons are in the deployed frontend
bundle (the frontend auto-deployed from the same commit). A full live
browser check (opening the Today page, waiting for whispers to load,
clicking the chevrons) was not performed in this session because the
demo account may not have multiple whispers queued today. The source
code is verified correct and deployed; the runtime behavior is
structurally sound (goPrev/goNext wrap around, manual nav pauses
auto-rotation for 30s, dot indicators are clickable). Marking as
UNVERIFIED at the browser-interaction level — needs a human or
headless-browser check to confirm the chevrons render and respond
to clicks.

COMMITS:
  - c94a97ed (submodule): fix(S2-8 + WhisperPostIt): purge social
    connectors + add whisper paging
  - 5ce9d766 (parent): chore: bump MaestroAgent submodule to c94a97ed

REMAINING:
  - WhisperPostIt chevrons need a live browser interaction check
    (source is verified + deployed, but no headless-browser click test
    was run this session)
  - CTO loop script (parent 44850a9e) is committed but not yet used
    to dispatch a real engineering task — the script's --help and
    Gemini-rejection were verified, but an end-to-end dispatch to
    qwen3-coder / deepseek / hunyuan has not been run

---
Task ID: 47 (Independent audit: latency reduction commit a9914a7e)
Agent: Independent External Reviewer (GLM)

GOVERNANCE LOOP READ RECEIPT:
- GOVERNANCE.md read from disk (Pre/Post-Execution Gate, Mutual Loop)
- ENTROPY_RECOVERY.md read from disk (P1-P87; P1, P14, P35, P43, P44,
  P46, P54, P55 specifically applied)
- governance/FORBIDDEN_ACTIONS.md read from disk (FA1-FA34)
- governance/ANTI_ENTROPY.md read from disk (Prime Directive, No-Gaming,
  Live-Claim Rule)
- governance/INVARIANTS.md read from disk (S0-S6)
- GOVERNANCE_LOOP.md read from disk

AUDIT SCOPE: Coder claimed three latency fixes in commit a9914a7e:
  1. DNS preconnect in layout.tsx
  2. Stale-while-revalidate (SWR) sessionStorage cache in maestro-api.ts
  3. Shell pre-warm at login in page.tsx
Coder claimed: the-moment 2.5s → 0.28s (9x), page revisit 2.5s → <0.1s
(25x), no functionality lost.

VERIFICATION METHOD:
- Source code review (git show a9914a7e, working tree inspection)
- Live HTTP fetches (fresh, independent — P1/P46 enforcement)
- Independent latency measurement script (scripts/latency_audit.py)
- Adjacent-failure check (P14)

============================================================
VERDICT: 🟡 PARTIALLY VERIFIED — fixes work, but 3 correctness gaps
============================================================

WHAT VERIFIED GREEN:

1. Commit + deploy:
   - origin/main HEAD (submodule): a9914a7e ✓
   - origin/main HEAD (parent): a9914a7e ✓ (after rebase)
   - Deployed backend /api/health commit: fb820db (old parent — benign,
     backend code unchanged; latency work is frontend-only)
   - Frontend deployed: HTTP 200 in 0.24s ✓
   - Live HTML contains preconnect + dns-prefetch tags ✓ (P54 PASS)

2. Preconnect (layout.tsx):
   - Source: <link rel="preconnect"> and <link rel="dns-prefetch"> for
     https://maestroagent-production.up.railway.app ✓
   - Live HTML: both tags present in served HTML ✓
   - Frontend load: 0.24s ✓

3. SWR cache (maestro-api.ts):
   - Source: sessionStorage cache with 60s TTL, GET-only, background
     revalidation ✓
   - Live JS bundle: sessionStorage references present ✓
   - Cache key includes token prefix (partial user isolation) ✓

4. Shell pre-warm (page.tsx):
   - Source: useEffect fires maestroApi.getTheMoment() if getToken()
     exists ✓
   - Only fires for authenticated users ✓

5. Independent latency measurement (fresh HTTP fetches):
   | Endpoint | Cold | Warm | Coder claimed |
   |---|---|---|---|
   | the-moment | 2.99s | 0.28s | 2.5s→0.28s ✓ |
   | the-shifts | 0.32s | 0.29s | 0.3s ✓ |
   | commitments | 0.32s | 0.28s | 0.4s ✓ |
   | whisper | 1.48s | 0.34s | 0.35s ✓ |
   | Frontend HTML | 0.24s | — | 0.21s ✓ |
   The backend shell cache works: the-moment cold 3s → warm 0.28s.

6. No regression (S2-8 + WhisperPostIt still live):
   - /api/consent/settings: 4 providers, 0 social ✓
   - /api/connectors: 7 providers, 0 social ✓
   - WhisperPostIt chevrons in deployed JS bundle ✓ ("Previous whisper"
     and "Next whisper" aria-labels found in chunk 2z3e-eoa8ul4o)

WHAT FOUND YELLOW (3 correctness gaps):

GAP-1: No mutation cache invalidation (P54 violation — stale data after
       mutations).
  The SWR cache caches GET responses for 60s, but NONE of the ~30
  POST/PUT/DELETE methods invalidate the cache. After a mutation:
    - User approves a draft → /api/drafts cache shows old "pending"
      for up to 60s
    - User connects a connector → /api/connectors cache shows
      "connected: false" for up to 60s
    - User toggles consent → /api/consent/settings cache shows old
      value for up to 60s
    - User resolves a commitment → /api/commitments cache shows old
      state for up to 60s
  This is confusing: the user takes an action, then sees the old state
  for up to a minute. The fix is to clear relevant cache entries after
  each mutation (e.g., after setConsentSetting, remove the
  /api/consent/settings cache entry).

GAP-2: SWR returns live:true even when backend is down (P55 violation —
       fake readiness).
  On cache hit, maestroFetch returns {data, live: true} unconditionally.
  If the backend is unreachable, the background fetch silently fails
  (maestroFetchBackground catches and swallows all errors), and the UI
  shows stale data with live:true — no "backend unreachable" warning.
  The user cannot tell "Maestro is showing fresh data" from "Maestro is
  showing stale cached data because the backend is down." The live flag
  should distinguish "served fresh" from "served from cache" — or the
  UI needs a "showing cached data" indicator when the background fetch
  fails.

GAP-3: Logout does not clear the SWR cache (minor data hygiene).
  clearToken() only removes the localStorage token. It does NOT clear
  sessionStorage. After logout, cached API responses remain in
  sessionStorage until the tab closes. The cache key includes the token
  prefix, so a different user logging in won't see the old user's data
  (different key). But the old user's data persists, which is a minor
  leak on shared computers. The fix is to call sessionStorage.clear()
  (or remove maestro:* keys) in clearToken().

GAP-4 (minor): Pre-warm fires on every page load, not just at login.
  The comment says "immediately after auth" but the code fires in the
  Home component's useEffect on every mount (every navigation to /).
  This is idempotent (GET request, SWR deduplicates), so it's not
  harmful — but it's redundant with the SWR cache. A more precise fix
  would be to fire the pre-warm only once per session (e.g., in the
  Login component's onLoggedIn callback, or guarded by a sessionStorage
  flag).

WHAT NOT MEASURED (honest boundary — P18):
  The coder's claim of "<0.1s page revisit (25x faster)" refers to the
  browser sessionStorage SWR cache. This cannot be measured with curl
  because curl has no sessionStorage. A real browser (or headless
  browser like Playwright) is required to verify this claim. The
  source code is structurally correct (cache hit returns in <1ms), but
  the runtime claim is UNVERIFIED at the browser level.

OVERALL ASSESSMENT:
  The three fixes are real, deployed, and structurally sound. The
  preconnect and shell pre-warm are genuine latency wins (verified:
  the-moment cold 3s → warm 0.28s). The SWR cache is architecturally
  correct but has three correctness gaps that need fixing before this
  is "world class":
    - GAP-1 (mutation invalidation) is the most user-visible — stale
      data after actions is confusing
    - GAP-2 (fake live:true) is the most dangerous — hides backend
      outages
    - GAP-3 (logout cache clearing) is minor but should be fixed for
      shared-computer hygiene
  The work is NOT world class yet, but it's a solid foundation. The
  gaps are fixable in a single follow-up commit.

COMMITS:
  - a9914a7e (submodule + parent): fix(LATENCY): preconnect + SWR +
    shell pre-warm
  - Audit script: scripts/latency_audit.py (this session)

---
Task ID: 48 (Deep audit: unwired modules — P11/P43 inventory + value/latency assessment)
Agent: Independent External Reviewer (GLM)

GOVERNANCE LOOP READ RECEIPT:
- GOVERNANCE.md, ENTROPY_RECOVERY.md (P1-P87), FORBIDDEN_ACTIONS.md,
  ANTI_ENTROPY.md, INVARIANTS.md, GOVERNANCE_LOOP.md,
  QUALITY_BARS.md, AUTONOMY_LADDER.md — all read from disk this session.
- Key principles applied: P11 (built-but-not-wired is not done), P14
  (bugs migrate one layer deeper), P15 (three states: exists /
  unit-tested / wired), P43 (journey assertion required), P54 (fix the
  data the user sees), P60 (four-bucket ownership model), P35 (gate the
  journey not the component).

AUDIT SCOPE: Deep audit of ALL modules in the codebase to find unwired
capabilities. For each, assess: (1) is it truly unwired in the DEPLOYED
product? (2) would wiring it add latency? (3) would it add user value?
AUDIT ONLY — no wiring performed.

METHODOLOGY:
1. Enumerated all .py modules in backend/maestro_oem/ and
   maestro-personal/src/maestro_personal_shell/ (excluding tests).
2. Built an import graph and computed transitive closure from the
   production entry point (maestro_personal_shell.api:app, confirmed
   via Procfile + Dockerfile).
3. For each module not in the transitive closure, grepped for
   references in the deployed codebase to confirm zero wiring.
4. Distinguished between modules referenced only by the UNDEPLOYED
   maestro_api package (not in the Docker image) vs truly orphaned.
5. For each unwired module, read the docstring and assessed latency
   impact (LLM calls? DB queries? pure rules?).

CRITICAL CONTEXT — TWO BACKENDS:
The codebase has TWO backend packages:
  - maestro_personal_shell/ — the DEPLOYED backend (Procfile:
    `uvicorn maestro_personal_shell.api:app`)
  - maestro_api/ — an UNDEPLOYED backend (NOT in the Dockerfile COPY
    list, NOT in the Procfile). It has its own routes/oem.py with ~50
    endpoints that import maestro_oem modules.
This means maestro_oem modules that appear "wired" via maestro_api
are actually 0% wired in the deployed product. The Dockerfile only
copies: maestro-personal/src/, maestro_oem/, maestro_cognitive_council/,
maestro_llm/, maestro_db/, maestro_nerve/. NOT maestro_api.

============================================================
TIER 1: HIGH-VALUE, ZERO-LATENCY UNWIRED MODULES (rules-only)
============================================================

These 3 modules are pure regex/keyword rules (no LLM, no DB, no network).
Wiring them would add microsecond-scale latency and significant user value.

1. noise_classifier.py (254 lines) — P74
   WHAT: Rejects newsletters, billing notices, security alerts, and
   automated notifications at ingestion (66% of ambient alerts are noise).
   WHY BUILT: "80% dismissal rate because no noise filter at ingestion.
   Every newsletter became a signal the user had to dismiss manually."
   WIRED?: NO — 0 production references. The function is_noise() is
   defined but never called from any ingestion path.
   LATENCY IMPACT: Zero — pure rules (regex + domain matching).
   USER VALUE: HIGH — would eliminate the #1 source of signal noise.
     The product currently has an 80% dismissal rate; this module was
     built specifically to fix that.
   ADJACENT FAILURE (P14): signals.py has its OWN inline _is_machine_sender()
   function (line 106) that duplicates a SUBSET of this logic. The
   unwired module is more comprehensive (216 noise domains by category).
   This is a P11/P54 violation: the better implementation exists but
   the production path uses the worse one.

2. sender_classifier.py (164 lines) — Phase 3.2
   WHAT: Classifies senders as machine vs human at ingestion time.
   WHY BUILT: "66% of ambient alerts are noise (AWS, GitHub, LinkedIn).
   Machine senders must never become commitments."
   WIRED?: NO — 0 production references. signals.py has an inline
   _is_machine_sender() that duplicates part of this.
   LATENCY IMPACT: Zero — pure rules.
   USER VALUE: MEDIUM — overlaps with noise_classifier but is more
     focused on sender identity (entity-based) vs content-based.
   RECOMMENDATION: Merge into noise_classifier (they do complementary
   things) and wire the combined module into the ingestion path.

3. actor_classifier.py (240 lines) — P82 / FA33
   WHAT: Distinguishes "I will..." (user commitment) from "Can you...?"
   (request) from "Nora: I will..." (third-party) from "I will not..."
   (cancellation). Implements the P60 four-bucket ownership model:
   my_promise, their_promise, quoted, third_party.
   WHY BUILT: "Without this module, ingestion had no way to distinguish
   'I will' from 'Can you?' from 'Nora: I will' — every sentence
   collapsed into a user commitment. That was the audit's smoking gun."
   WIRED?: NO — 0 production references.
   LATENCY IMPACT: Zero — pure rules.
   USER VALUE: CRITICAL — this is the P60/P82/FA33 fix. The commitment_classifier
     handles third_party_report classification, but NOT the full 4-bucket
     ownership model. "What did I promise Maria?" can still return
     Maria's promises (false positive) or nothing (false negative)
     because the ownership filter can't distinguish my_promise from
     their_promise. This module was built to fix exactly that.
   ADJACENT FAILURE (P14): This is the deepest gap in the product. The
     module exists, is unit-tested, and was authored via the CTO↔K3 loop
     (P46 verified), but was never wired into the ingestion path. Every
     Ask query that asks "what did I promise X?" is affected.

============================================================
TIER 2: HIGH-VALUE, MINIMAL-LATENCY UNWIRED MODULES (DB-only)
============================================================

These modules make DB queries but no LLM calls. Wiring them would add
~50-200ms (one indexed DB query) and significant user value.

4. change_detection.py (195 lines) — P78
   WHAT: Tracks last_seen_at baseline and computes actual deltas (new,
   modified, resolved, contradicted since last read).
   WHY BUILT: "/api/what-changed was listing current commitments instead
   of computing actual changes. The user can't tell 'what's new' from
   'what exists' without a baseline."
   WIRED?: NO — 0 production references. The live /api/what-changed
     endpoint uses surfaces/what_changed.py with a simple 24h window
     instead of baseline tracking.
   LATENCY IMPACT: ~50ms (one DB query for last_seen_at + one for
     deltas since that timestamp).
   USER VALUE: HIGH — the current implementation shows "everything in
     the last 24 hours" which is NOT the same as "what changed since
     you last looked." A user who checks twice in 10 minutes sees the
     same list both times. The unwired module would show 0 changes on
     the second read (correct behavior).

5. confidence_system.py (354 lines) — P77
   WHAT: Multi-factor confidence computation (5 factors: evidence count,
     recency, source authority, classification confidence, contradiction
     count). Replaces the legacy uniform 0.85-0.9 confidence.
   WHY BUILT: "Legacy confidence was uniform (0.85-0.9) because every
     value came from a single rule-based pattern. This module derives
     confidence from five independent factors so the value tracks
     actual evidence quality."
   WIRED?: NO — 0 production references. /api/confidence returns 404.
   LATENCY IMPACT: ~100-200ms (reads the ledger + computes 5 factors
     per entry).
   USER VALUE: HIGH — the P25 "confidence display gate" principle says
     confidence must be honest. The current uniform 0.85-0.9 is
     decorative precision (P25 violation). This module would make
     confidence a real measurement.
   ADJACENT FAILURE (P14): P25 (confidence display gate) was codified
     but the module that enforces it was never wired. The Today page
     still shows uniform confidence values.

6. behavior_change.py (206 lines) — Phase 9
   WHAT: Tracks entity track records — did this entity keep promises
   before? Did they deliver late? Uses past outcomes to inform future
     interactions.
   WIRED?: NO — 0 production references. /api/behavior-change returns 404.
   LATENCY IMPACT: ~50-100ms (one DB query for entity history).
   USER VALUE: MEDIUM — would let the Whisper engine say "Maria has
     delivered on 3 of 4 past commitments" instead of just "Maria has
     an open commitment." Adds context but isn't the core thesis.
   RECOMMENDATION: Defer until the core ingestion quality (Tier 1) is
     fixed. This is a "nice to have" layer on top of a working system.

7. material_transitions.py (411 lines) — Phase 6
   WHAT: Ranks material transitions (new high-consequence commitment,
     state change, contradiction, etc.) by consequence weight.
   WIRED?: NO — 0 production references. /api/material-transitions
     returns 404.
   LATENCY IMPACT: ~50ms (in-memory ranking, no DB).
   USER VALUE: MEDIUM — would let the Today page prioritize what to
     show first. Currently the Today page shows commitments in
     creation order, not by materiality.
   RECOMMENDATION: Wire after change_detection (they're complementary —
     change_detection finds what's new, material_transitions ranks it).

============================================================
TIER 3: UNWIRED OEM MODULES (only in undeployed maestro_api)
============================================================

These 14 modules exist in backend/maestro_oem/ but are ONLY imported
by backend/maestro_api/routes/oem.py — which is NOT in the Docker
image and NOT deployed. They are 0% wired in the deployed product.

Module | Value if wired | Latency impact
---|---|---
coordination | LOW (org coordination viz) | MEDIUM (model build)
curiosity | LOW (asks probing questions) | HIGH (LLM call)
decision_intelligence_loop | MEDIUM (decision tracking) | MEDIUM
digital_twin | HIGH ("what if?" scenario sim) | HIGH (clone + sim)
gps | HIGH (personalized nav) | MEDIUM (per-user query)
intent | MEDIUM (infer user intent) | HIGH (LLM call)
meeting_intelligence_loop | MEDIUM (meeting patterns) | MEDIUM
pulse | LOW (org health metrics) | MEDIUM
canvas | LOW (visualization) | LOW
consciousness | LOW (state vector) | MEDIUM
executive_function | LOW (cognitive control) | MEDIUM
mcp_server | MEDIUM (external agent tools) | LOW (read-only)
prediction_market | LOW (prediction trading) | MEDIUM
workplace_signal_fusion | MEDIUM (cross-source fusion) | MEDIUM

VERDICT ON TIER 3: These are ENTERPRISE features built for the
undeployed maestro_api backend. Wiring them into maestro_personal_shell
would be a significant integration effort (they expect the full OEM
model, not the personal shell's simplified state). Most add latency
(model building, LLM calls). None are appropriate for the personal
product's current stage. They should be documented as "enterprise
roadmap, not for personal shell" rather than wired.

The ONE exception is mcp_server — it's read-only and low-latency and
could expose the personal shell's data to external agents (Claude,
GPT, etc.) via MCP. But that's a Phase 5+ enterprise feature.

============================================================
TIER 4: UNWIRED PERSONAL SHELL MODULES (niche/deferred)
============================================================

audio_transcription.py — pluggable speech-to-text for the Copilot.
  Copilot is not deployed (the /api/copilot/* routes are commented out
  in api.py). Wiring this is blocked by the Copilot feature itself.
  ZERO latency impact on the core product.

copilot_enterprise.py — enterprise Copilot features (SSO, audit).
  Not relevant to the personal product. Enterprise roadmap only.

copilot_postcall_features.py — post-call analysis features.
  Same as above — Copilot is not deployed.

============================================================
SUMMARY: WHAT TO WIRE (in priority order)
============================================================

IMMEDIATE (zero latency, high value):
1. actor_classifier.py → wire into ingestion path (signals.py + gmail_connector.py)
   Fixes: P60 (4-bucket ownership), P82 (actor attribution), FA33
   Latency: +0ms (pure regex rules)
   Risk: LOW — rules hold a veto, can't make things worse

2. noise_classifier.py → wire into ingestion path, REPLACE the inline
   _is_machine_sender in signals.py
   Fixes: P74 (noise rejection), reduces 80% dismissal rate
   Latency: +0ms (pure rules)
   Risk: LOW — more comprehensive than the inline version

3. sender_classifier.py → merge into noise_classifier (they're
   complementary) and wire the combined module
   Latency: +0ms
   Risk: LOW

NEXT (minimal latency, high value):
4. change_detection.py → wire into /api/what-changed (replace the
   24h-window approach with baseline tracking)
   Fixes: P78 (baseline deltas), P54 (user sees real changes)
   Latency: +50ms (one DB query)
   Risk: MEDIUM — changes the semantics of /api/what-changed

5. confidence_system.py → wire into the commitment ledger read path
   Fixes: P25 (honest confidence), P77 (confidence variance)
   Latency: +100-200ms (5-factor computation per entry)
   Risk: MEDIUM — confidence values will change, need to verify the
   UI doesn't break

DEFER (higher latency, lower immediate value):
6. material_transitions.py — wire after #4 (they're complementary)
7. behavior_change.py — wire after core quality is fixed

DO NOT WIRE (enterprise, high latency, wrong product stage):
- All Tier 3 OEM modules (coordination, curiosity, digital_twin, gps,
  intent, meeting_intelligence_loop, pulse, canvas, consciousness,
  executive_function, prediction_market, workplace_signal_fusion)
- All Tier 4 Copilot modules (audio_transcription, copilot_enterprise,
  copilot_postcall_features)

AUDIT ONLY — NO WIRING PERFORMED. This is a recommendation list, not
a work log. The coder should evaluate each recommendation, trace the
call graph themselves (P16), and wire in priority order with journey
assertions (P43) for each.
