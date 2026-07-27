# Forbidden Actions — Drawn From Real Incidents

Each forbidden action below is grounded in a specific incident from this audit arc. The swarm must NEVER take these actions, and the GovernanceEnforcer must BLOCK them.

## 1. Lowering a gate threshold to silence a red

**Incident:** The scorer isolation_rate was computed incorrectly (used overall pass instead of isolation-specific pass). The fix corrected the metric, but a tempting alternative would have been to lower the isolation threshold from 0.95 to 0.80 to make the old metric read green.

**Rule:** Never lower a threshold in `benchmark.yml` or any gate config to make a failing metric pass. If a threshold genuinely needs adjustment, escalate to human.

**Enforcement:** `GovernanceEnforcer` Layer 1 (deterministic) — any action that modifies a threshold constant in `benchmark.yml` is BLOCKED.

## 2. Claiming "live" without a fresh fetch

**Incident:** The SSR first-paint was claimed "live" based on a local build artifact, but the external auditor's fresh fetch showed `Loading…` (later resolved as a non-JS tool blind spot, but the claim was made without the right instrument).

**Rule:** Never state something is "live" without a fresh, independent fetch of the public endpoint at the moment of the claim. For client-rendered content, use a JS-executing instrument.

**Enforcement:** `GovernanceEnforcer` Layer 2 (LLM critic) — reviews reports for live-claims without evidence.

## 3. Seeding synthetic data and presenting it as real

**Incident:** Temptation to seed the calibration report with synthetic benchmark predictions to show a Brier score before real usage accumulated.

**Rule:** Never present synthetic/demo data as real calibration, real evidence, or real usage. If demo data is needed for dogfood, label it explicitly ("demo/synthetic, not real usage").

**Enforcement:** `GovernanceEnforcer` Layer 2 (LLM critic) — reviews calibration/evidence outputs for synthetic data presented as real.

## 4. Modifying governance files without human ratification

**Incident:** (Preventive) — an autonomous agent could weaken the constitution to escape constraints.

**Rule:** The swarm's file-write tool CANNOT touch `governance/` without a human ratification token. Governance amendments require human approval.

**Enforcement:** `GovernanceEnforcer` Layer 1 (deterministic) — any action that writes to `governance/` is BLOCKED.

## 5. Gaming a metric by narrowing scope

**Incident:** The old isolation_rate only inspected the entity_specific category. Widening to all categories revealed 98.86% (more honest) instead of 100% (narrow). The temptation would have been to keep the narrow scope to preserve the headline 100%.

**Rule:** Never narrow a metric's scope to exclude failures and make it read greener. Metrics must measure what they claim to measure, across the full applicable domain.

**Enforcement:** `GovernanceEnforcer` Layer 2 (LLM critic) — reviews metric changes for scope-narrowing.

## 6. Accepting "exists" for "works"

**Incident:** The correction endpoint existed and recorded `metadata["correction"]`, but specialist retrievers didn't read it — so correction was write-only. The temptation was to say "correction works" because the endpoint existed.

**Rule:** Never claim a capability works based on the endpoint existing. Trace the full path: does the data flow downstream? Does it actually change behavior? "Exists" ≠ "works."

**Enforcement:** `GovernanceEnforcer` Layer 3 (outcome verification) — after a fix, verify the full loop, not just the entry point.

## 7. Spraying a fix before all return paths

**Incident:** `_fix_source_types` was inserted before all 12 `return AskResponse` statements, including early-return abstention paths where `evidence_refs` was undefined → `UnboundLocalError` → safety dropped to 0%.

**Rule:** When adding a fix that touches multiple return paths, verify the variable is defined on ALL paths — including early returns, error paths, and abstention paths. Never spray a fix blindly.

**Enforcement:** `GovernanceEnforcer` Layer 3 (outcome verification) — after the fix, re-run the benchmark subset to confirm no regression on abstention/safety paths.

## 8. Headless-browser OAuth to install a third-party GitHub App

**Incident:** The Railway GitHub App required browser OAuth. The temptation was to automate it with a headless browser + stored credentials.

**Rule:** Never automate browser-based OAuth for third-party app installation. GitHub gates this behind a consent screen deliberately. Route around it (e.g., deploy from GitHub Actions) instead of fighting it.

**Enforcement:** `GovernanceEnforcer` Layer 2 (LLM critic) — reviews actions for headless-browser OAuth attempts.

## 9. Crediting a component gate as a product fix (P35)

**Incident:** Three independent audits found the same structural gap: a component gate (the 2,248-case classifier gold-set) passed while the product still surfaced questions as active commitments. The gate tested `_rule_based_classify` in isolation; the real API didn't honor the classifier's rejection.

**Rule:** Never claim a component is "fixed" or "permanent" without a corresponding JOURNEY gate that tests the same input through the real API and asserts at the product surface. A component gate without a journey gate is a necessary-but-not-sufficient half-measure.

**Enforcement:** `GovernanceEnforcer` Layer 3 (outcome verification) — after a component fix, verify the FULL journey, not just the component's return value.

## 10. Shipping an answer not constrained to the query's entity/owner (P36)

**Incident:** "What did I promise Maria?" returned Maria's statements (not what I promised). "What did Dana promise?" answered about Alex. Unrelated PayPal/RBI perspectives contaminated answers.

**Rule:** Every answer must pass entity, speaker/owner, temporal, and source consistency checks deterministically BEFORE it ships. Never allow an LLM fallback to elaborate on unrelated context.

**Enforcement:** Journey gate — adversarial Ask battery asserting answers are entity/owner/temporal/source-constrained.

## 11. Admitting non-commitments to the active commitment surface (P37)

**Incident:** Questions, tentative language, and jokes appeared as `is_commitment: true, state: active` in `/api/commitments` despite the classifier typing them correctly.

**Rule:** Classification without admission control is theater. The commitment surface must hard-filter on `is_commitment: true` — if the classifier says `false`, the signal MUST NOT appear.

**Enforcement:** Journey gate — insert controlled signal taxonomy, assert only real commitments surface.

## 12. Allowing re-login after account deletion (P38)

**Incident:** `DELETE /api/account` succeeded, then re-login with the same credentials returned 200 with a new token.

**Rule:** Deletion is final. After deletion, re-login MUST fail. The identity, credentials, signals, connectors, and audit trail are all gone.

**Enforcement:** Deletion-finality test — register → delete → re-login must fail.

## 13. Relabeling a fallback model as the requested model (P46)

**Incident:** The CTO↔Kimi-K3 loop script requested `moonshotai/kimi-k3` and logged the request-side model. On long engineering prompts, Kimi K3 timed out, a silent fallback served the work via Gemma 12B, and the log still said "kimi-k3". The probe string "KIMI_K3_VERIFIED" proved only a short probe reached kimi-k3, not the engineering work. 8 commits carried "Kimi K3 design" in their messages but were CTO/GLM-authored.

**Rule:** Never relabel a fallback as the requested instrument. Read `response.model` (served) on every call, assert it equals the expected instrument, fail loudly on any mismatch or timeout. Log the OpenRouter generation ID for external cross-check. A probe that the instrument is present is not proof it played the work.

**Enforcement:** `ops/cto_loop.py` reads `response.model`, asserts `== moonshotai/kimi-k3`, captures `response.id`, and FAILS LOUDLY on any mismatch or timeout — never relabels. Every "Kimi K3 did X" claim must carry a generation ID cross-checkable on the OpenRouter dashboard.

## 14. Claiming "done" on a function the live path doesn't call (P43)

**Incident:** `reconcile_signal()` passed its 7/7 unit tests but the live ask path still ran the prior 5-layer inline ownership filter. The function was a scaffold, not a fix.

**Rule:** Never claim a new function is "done" or "wired" without a journey assertion proving the live path calls it — typically by asserting the live response carries a value only that function can produce. A unit test proves the function; only a journey assertion that the LIVE response uses it proves the product does.

**Enforcement:** `test_P43_reconcile_wired_live.py` spies on `reconcile_signals_for_user` and asserts the live `/api/ask` path calls it; asserts the live response carries `reconcile_source='signal.metadata'`; greps the source for old filter tokens and asserts they're gone.

## 15. Reporting a degradation strategy as a latency win (P44)

**Incident:** The LLM circuit breaker (S2-6) was credited as "the latency fix" — but a breaker makes a stuck LLM degrade to rules after three 25-second failures; it does not make a normal slow query fast. The actual latency fix (streaming + bounded time-to-first-token) was not yet in the frontend.

**Rule:** Never report a circuit breaker, retry, or fallback as a latency fix. Credit a breaker as the safety net it is; the latency fix is streaming plus a bounded time-to-first-token, measured at p50/p95 on the live path.

**Enforcement:** When crediting a latency fix, name BOTH the streaming mechanism AND the breaker behind it. Do not let "latency cliff — circuit breaker" read as "latency fixed."

## 16. Reporting "done" on local-green without CI-green-on-push (P45)

**Incident:** 56 new tests passed locally across 8 files, plus 67/67 regression. But no CI run URL on the pushed commits was shown. The arc has repeatedly demonstrated local-green diverging from CI-green and product-green.

**Rule:** Never report a fix as "done" on local test output alone. The report includes the CI run URL on the pushed commit, with the permanence gate and the relevant journey tests green. A local suite is how you DEVELOP confidence; CI on the commit is how you EARN it.

**Enforcement:** Every "done" claim includes a CI run URL. If CI is red, the claim is "CI red, here's why" — not "done."

## 17. Returning a blank answer on LLM failure (P51)

**Incident:** Under an LLM outage window, multiple Ask queries returned `answer:""` with all-None fields and zero user feedback. The circuit breaker (S2-6) handles SLOW (fails closed to rules after three >25s calls) but not DEAD (empty/500 responses). The user cannot tell "Maestro found nothing" from "Maestro broke."

**Rule:** Ask must NEVER return a blank answer. On any LLM failure (timeout, 500, empty response), Ask returns an explicit, ledger-grounded answer with a clear "AI unavailable" note. `/api/debug-llm` must not throw an unhandled 500. Silent empty is forbidden.

**Enforcement:** Journey gate — simulate LLM outage (mock llm_complete to return None/empty/raise), assert Ask response has a non-empty answer grounded in the ledger with a calibration_note mentioning "AI unavailable."

## 18. Ingesting misclassified signals without entity-extraction validation (P50)

**Incident:** The Slack ingest path grabs date tokens ("Friday.") and pronouns ("I'm") as entities; a joke ("conquer the moon") becomes a commitment_made; a cancellation is missed; third-party reports are undetected; the Gmail and Slack paths use inconsistent taxonomies. The gold-set tested the commitment-type classifier on clean cases — but never tested entity extraction or the Slack ingest path on adversarial input.

**Rule:** Entity extraction, classification, and ledger-write must be tested end-to-end on messy, adversarial, real-ish input. No date tokens, pronouns, or test markers as entities. Jokes, cancellations, and third-party reports must be detected. A single consistent taxonomy across all ingest paths (Gmail AND Slack).

**Enforcement:** Journey gate — post adversarial Slack signals (jokes, cancellations, third-party, date-pronoun-entity attempts), assert the ledger receives correct entity + commitment_type + owner for each.

## 19. Surfacing real PII in the demo corpus (P52)

**Incident:** The demo corpus contains Prateek's real name ("PRATEEK MISRA") and a real brokerage client ID ("Zerodha Client ID TND670"). Ask "who am I" on the demo account surfaces this PII as the user's identity.

**Rule:** The demo corpus must be synthetic and PII-free. No real names, client IDs, brokerage accounts, or real email addresses. The demo principal must be a clearly-synthetic identity.

**Enforcement:** Journey gate — login as demo, ask "who am I", assert the answer does NOT contain any real person's name or any real account/client ID. Grep the demo seeder for real PII tokens.

## 20. Suppressing the flagship feature on a synthetic/fresh-user artifact (P53)

**Incident:** The Moment returns has_moment:false ("user dismisses 100% of suggestions") based on a dismissal_rate:1.0 artifact in the seed data. A first-run user sees nothing.

**Rule:** Dismissal-based suppression must NEVER hide The Moment on a synthetic or fresh-user artifact. It requires real dismissal history (minimum 5 dismissals) AND a minimum-confidence threshold. A fresh user always sees The Moment.

**Enforcement:** Journey gate — fresh user with 0 dismissals, post a commitment, assert /api/the-moment returns has_moment:true. Synthetic seed corpus must not produce a 100%-dismissal artifact.

## 21. Transitioning/correcting/deleting another user's commitment (P58)

**Incident:** The sixth audit reproduced a cross-tenant mutation IDOR: any user can cancel any other user's ledger entries via /api/commitments/{id}/transition. The fifth audit verified read isolation but did not test mutations.

**Rule:** Every state-changing endpoint must verify the target resource belongs to the requesting tenant before mutating. Cross-tenant mutations return 403, not 200.

**Enforcement:** Journey gate — register two users, create a commitment for user A, attempt to transition it as user B → must 403. (test_P58_cross_tenant_mutation.py)

## 22. Labeling a signal "cancellation" without applying the lifecycle transition (P59)

**Incident:** The sixth audit ingested the product's own synthetic lifecycle suite — cancellations were not applied, completions did not close commitments. The reclassify migration re-labeled signal types but the lifecycle engine doesn't fire.

**Rule:** A completion/cancellation/deadline-change signal must APPLY a state transition to the matching commitment. Classification without lifecycle application is theater.

**Enforcement:** Journey gate — post a cancellation signal for an active commitment, assert the commitment's state transitions to cancelled.

## 23. Returning "no record" when the user's own promise exists (P60)

**Incident:** The P43 ownership filter over-corrected: "What did I promise Maria?" returns "no record" while the user HAS a promise to Maria. The filter excludes by entity, not by owner.

**Rule:** The ownership model must distinguish my_promise/their_promise/quoted/third_party. "What did I promise X?" returns my_promise to X — never nothing when my_promise exists.

**Enforcement:** Journey gate — post a user-owned commitment to Maria, ask "What did I promise Maria?", assert the response includes the user's commitment.

## 24. Keeping a real connected mailbox on the shared demo (P61)

**Incident:** The bootstrap tenant has a real connected Gmail with 209+ signals including bank/brokerage PII, readable by anyone with the demo password.

**Rule:** Disconnect real Gmail from the shared demo entirely. Seed synthetic-only data. No token redaction substitutes for not having the corpus.

**Enforcement:** Journey gate — login as demo, check /api/connectors, assert no real Gmail connection; check /api/account/export, assert no real-person names or account IDs.

## 25. Hardcoded auth bypass tokens in production code (P63)

**Incident:** `verify_token()` accepted the literal string "demo-bypass-token" and returned "default@personal.local" — bypassing all authentication. Live in production.

**Rule:** Identity comes only from a validated token. Local-test bypasses must be env-gated (MAESTRO_LOCAL_DEV=true) and off in production. No hardcoded tokens.

**Enforcement:** Journey gate — POST /api/ask with `Authorization: Bearer demo-bypass-token` in production → must return 401.

## 26. Surfaces returning impossible or contradictory state (P64)

**Incident:** /api/metrics returned `active: -4`. /api/commitments returned `[]` while /api/commitments/ledger was populated.

**Rule:** Every surface reads from one reconciled model. Counts are clamped to non-negative. No surface contradicts another.

**Enforcement:** Journey gate — read /api/metrics, assert `commitments_active >= 0`.

## 27. Closing a ticket on a verdict without a posted live reproduction

**Incident:** A "GREEN 8.5/10, ship it" verdict from a different audit process (Kimi K3) was given while the P69 owner-key bug was live — the exact bug that made every first-person commitment invisible to its own ownership filter. That verdict was wrong not because the reviewer was careless, but because it never posted the one reproduction that would have caught it (ask "What did I promise Maria?" on a clean rules-only account and inspect the `owner` field). Every ticket in the roadmap now carries the "posted live reproduction" requirement explicitly for exactly this reason.

**Rule:** No ticket is closed on a worklog claim, a commit message, or another AI's verdict (including "Kimi K3" scores). Closed = a live reproduction is posted and independently re-run. A verdict without a posted reproduction is a hypothesis, not a finding.

**Enforcement:** Every "done" claim must include the exact reproduction command + the actual output from THIS session. "Tests pass" without the specific test that inspects the safety-critical field is not verification. A verdict from any AI (including this one) is treated as a hypothesis until a human or independent process posts the reproduction.

### FA28: Manual Production Deploys

**Forbidden:** Manually deploying to production from the Railway dashboard or any other manual interface, when auto-deploy could be configured.

**Reason:** Manual deploys create a gap between "code is fixed" and "production is fixed." If auto-deploy is not configured, fixes merged to main will not reach production until someone remembers to manually trigger a deploy. This violates P71 (infrastructure automation) and makes verification unreliable — the Finn Loop assumes merged code is live within minutes.

**Exception:** Emergency hotfixes that cannot wait for the CI/CD pipeline, but these must be followed by a proper commit to main and auto-deploy configuration verification.

**Enforcement:** Every Railway service must have "Auto Deploy" enabled in Settings → Deploy. Verify with: `railway status` or check the Railway dashboard. If auto-deploy is disabled, it must be enabled before merging any PR.

**Incident:** The web frontend service (`web-production-d5c26.up.railway.app`) was not configured for auto-deploy. Code fixes (removing mock data, adding real API calls, fixing AskView) were merged and pushed to main, but the web service continued serving old code with mock data. The backend auto-deployed correctly, creating a false impression that all fixes were live. The auditor caught this by checking the SSR HTML for mock data strings.

**Rule:** If it runs in production, it auto-deploys from main. No manual deploys. No exceptions except emergency hotfixes (which must be followed by auto-deploy enablement).

### FA29: Connecting Real User Data to a Shared/Demo Environment (P72)

**Forbidden:** Connecting personal Gmail, real banking data, brokerage accounts, or API tokens to any shared or demo environment accessible to external users. Real PII (founder names, client IDs, real email addresses) must never appear in demo fixtures.

**Reason:** The bootstrap tenant was found to have a real connected Gmail with 209+ signals including bank/brokerage PII, readable by anyone with the demo password. The demo corpus contained Prateek's real name ("PRATEEK MISRA") and a real brokerage client ID ("Zerodha Client ID TND670"). Ask "who am I" on the demo account surfaced this PII as the user's identity. A demo that leaks the founder's real brokerage ID is a privacy defect and a trust-killer for any evaluator.

**Remedy:**
- Demo environment: synthetic data only, regenerated on every deploy
- Admin endpoint `/api/admin/purge-real-gmail-from-demo` runs on every demo deploy
- CI check (`scripts/check_p72_data_hygiene.py`) greps demo fixtures for real PII patterns
- Production environment: tenant-isolated, no shared state
- Real OAuth tokens never stored against the demo/bootstrap identity

**Enforcement:** Journey gate — login as demo, check `/api/connectors` (assert no real Gmail), check `/api/account/export` (assert no real-person names or account IDs), ask "who am I" (assert no real PII in answer). CI gate fails the build if any PII pattern is found in demo fixtures.

### FA30: Ingesting System-Generated Drafts as External Signals (P73)

**Forbidden:** Treating system-generated drafts (emails Maestro wrote and sent on the user's behalf, Whisper responses, Briefing text, auto-generated summaries) as external commitments when they re-enter the system through Gmail sync or any other ingestion path.

**Reason:** When the user sends a draft email Maestro generated on Tuesday, that email lands in the user's Sent folder. When Gmail sync runs on Wednesday, the email is fetched back into Maestro as if it were a fresh external signal. Maestro then classifies its own draft as a "user commitment," creating a recursive loop where the system's outputs become its inputs. This contaminates the commitment ledger with self-generated noise.

**Remedy:**
- All system-generated content is tagged with `source_type: "self_generated"` and `generation_id: UUID` at creation time
- Outbound emails include `X-Maestro-Generated: true` header
- Gmail connector filters out emails with that header
- Signal creation endpoint rejects content matching a known `generation_id`
- Fuzzy-hash match against recent drafts catches drafts that were edited before sending

**Enforcement:** Journey gate — generate a draft email, send it via Maestro's draft system, sync Gmail, verify the email does NOT appear as a new signal. CI check (`scripts/check_p73_recursive_ingestion.py`) ingests a self-generated draft and asserts rejection.

### FA31: Leaking Internal Guard Strings in User-Facing Responses (P86)

**Forbidden:** Returning `[SEMANTIC INJECTION DETECTED AND REMOVED]`, `[REDACTED]`, `[GUARD TRIGGERED]`, raw HTML entities (`&lt;`, `&gt;`, `&amp;`), raw email headers (`From: foo@bar.com`), UUID-labeled credentials (`Token: 550e8400-e29b-41d4-a716-446655440000`), or similar internal markers in user-facing API responses.

**Reason:** Audit #2 found that the Prepare card rendered the literal string `[SEMANTIC INJECTION DETECTED AND REMOVED]` to the user. The guard string is internal defensive machinery — it should never be exposed. Exposing it (a) confuses users who don't know what it means, (b) reveals defensive patterns an attacker could probe, and (c) signals that the system's output sanitization is incomplete. The same audit found UUID-labeled credentials and raw email headers in responses.

**Remedy:**
- Sanitize at the output layer. Replace internal markers with neutral language ("content redacted for safety") or omit entirely.
- Maintain `config/sanitization_patterns.yaml` with regex patterns for every known leak shape.
- Every API response passes through `sanitize_output()` before serialization.
- CI test feeds 100 known-bad inputs and verifies zero leaks in responses.

**Enforcement:** Journey gate — feed inputs containing `[SEMANTIC INJECTION...]`, UUID tokens, raw headers, HTML entities — assert the API response contains none of these patterns. CI gate (`scripts/check_p86_output_sanitization.py`) fails the build if any leak is detected.

### FA32: Returning HTTP 500 on Authenticated Read Endpoints (P85)

**Forbidden:** Any authenticated GET endpoint returning HTTP 500. 500 on read paths is a release blocker. No exceptions.

**Reason:** Audit #2 found that `/api/account/export` and `/api/observability/traces` returned HTTP 500 on every call. A read endpoint that 500s is a reliability failure that breaks the user's trust — the user cannot tell "the system is broken" from "I am not allowed to see this." Worse, the 500s were unhandled, meaning the stack trace leaked server-side state (file paths, library versions) to the client in some configurations. A system-of-record that 500s on read is not trustworthy.

**Remedy:**
- Return structured error with diagnostic ID (e.g., `{"error": "internal_error", "diagnostic_id": "abc123", "suggestion": "..."}`).
- Log full stack trace server-side with the diagnostic ID for correlation.
- Alert on-call on every 500.
- Never ship a release that 500s on read — block the release in CI.

**Enforcement:** Journey gate — every authenticated read endpoint tested with: empty state, populated state, malformed auth, revoked token, concurrent load. CI gate fails the build if any read endpoint returns 500 in the test suite. Nightly production probe hits every read endpoint every 5 minutes, 500-rate must be <0.1%.

### FA33: Promoting Non-User Events to Active User Commitments (P82)

**Forbidden:** Promoting a request, question, quotation, joke, tentative statement, or third-party promise to an active user commitment without explicit human review.

**Reason:** The controlled transcript test (Nora fixture) is the smoking gun. When fed a transcript containing seven different event types, the product misclassifies requests and third-party promises as the user's active commitments and silently drops the cancellation. A product that cannot tell "I will send X" from "Can you send X?" from "Nora: I will send X" from "I will not send X" is not a commitment intelligence product. This is a category failure, not a tuning problem.

**Remedy:**
- Actor attribution and event-type classification (P82) must precede any promotion.
- Promotions to `commitment_ledger` require `actor=user AND event_type=commitment AND confidence >= 0.7`.
- Low-confidence promotions go to a review queue, not the active ledger.
- The Nora controlled transcript test runs on every PR and must pass.

**Enforcement:** Journey gate — `tests/fixtures/controlled_transcript_nora.md` ingested, assert exactly 1 user commitment extracted (sentence #1), exactly 1 cancellation detected (sentence #6, resolves #1), exactly 0 user active commitments in the ledger, exactly 1 Nora active commitment (sentence #5). CI gate (`scripts/check_p82_actor_attribution.py`) fails the build if any non-user event is promoted.

### FA34: Contradicting Canonical State in Generated Answers (P87)

**Forbidden:** An Ask response asserting state (counts, statuses, cancellations, recency) that contradicts the canonical ledger or any state-bearing endpoint.

**Reason:** Audit #2 found that Ask said "0 commitments cancelled" while the `/api/inbox/synthetic/status` endpoint showed 13 cancelled. A system that contradicts itself across endpoints destroys trust. The user cannot tell which surface to believe. The contradiction happens because the LLM generates state claims freely without grounding them in a ledger query.

**Remedy:**
- All state assertions in generated answers must be grounded in a ledger query executed within the same request.
- If the LLM generates a state claim ("3 commitments cancelled", "5 active promises to Maria"), the claim is verified against the ledger before the response is sent.
- Unverifiable claims are redacted or replaced with the actual ledger value.
- The verification step is logged so auditors can trace which claims were grounded vs. redacted.

**Enforcement:** Journey gate — for every state-bearing endpoint, run the same query via Ask and via the direct endpoint, assert equivalence. CI gate (`scripts/check_p87_state_consistency.py`) covers 20 consistency fixtures: counts, states, recency, entity-specific state. Nightly production check runs 10 random state queries and verifies consistency.
