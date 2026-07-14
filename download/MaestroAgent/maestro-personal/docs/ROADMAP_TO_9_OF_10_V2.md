# MAESTRO — ROADMAP TO 9/10 (v2 — Post-GitHub Review)

> **This is the upgraded roadmap.** It supersedes v1 (`Maestro-Roadmap-to-9-of-10.md`) after a fresh re-clone and re-execution against the **latest** GitHub head (`e01ee6d`, 2026-07-14), which is 4 commits past the version originally audited (`422ddc1`).
>
> **Bottom line of the re-review:** The repo shipped real new work (a whisper/notification subsystem), but **none of the core audit failures were fixed, one new falsification was introduced, and the test suite got worse.** This does not change the roadmap's shape — it **hardens** it: Phase 0 (measurement integrity) is no longer "important," it is now a *demonstrated, live* failure that blocks every other phase.

---

## 0. WHAT CHANGED SINCE v1 — Verified Delta (audit head → latest head)

I re-cloned and re-executed every check. Here is the verified state of the 4 new commits (`342a960`, `193336f`, `5a25c19`, `e01ee6d`).

### ✅ Genuinely improved (verified by execution)
| Change | Verified how | Impact |
|---|---|---|
| **Whisper subsystem added** — `whisper_scheduler.py` (257 lines), rule-based early-exit `_should_whisper_rule_based()`, dedup table, push deep-link, Dashboard "Needs Attention" cards on mobile + web | Read the code; 16 whisper tests are **genuinely behavioral** (they call the real function, not string-match) | Small real win for Product Design + Mobile UI; the rule-based early-exit is a legitimate non-AI latency optimization |
| **OpenAPI schema re-dumped** (81 → 82 paths) | `git diff` shows the schema now includes consent/settings | The contract-drift test *root cause* is addressed (but the test still needs a green run) |

### ❌ Claimed as fixed, STILL broken (verified by execution on clean clone)
| Claim (CLAIM_FREEZE / commit) | Verified reality on latest clone | Status |
|---|---|---|
| **Gold-150 "GATE PASS, lift +15.9, 121/150 LLM-active"** | The cited proof file `gold_150_llm_active_full_results.json` **does not exist in the repo**. The only committed full-150 file (`gold_150_rule_based_results.json`) still shows **Maestro 0.3067 vs BM25 0.7, lift −0.39, GATE FAIL** | **FALSE** — uncommitted-artifact citation, same anti-pattern as before |
| **BM25 baseline = 0.514** (the number the "win" beats) | **Hardcoded** as `bm25_baseline = 0.514` in 6 scoring scripts; the reproducible *computed* baseline is **0.7** | **Cherry-picked baseline** — against the real 0.7, even the claimed 0.673 is a *loss* |
| **"LLM active by default ✅ VERIFIED"** | `/api/llm-status` on clean clone → `configured: false, active: false, provider: none, "Rule-based"` | **FALSE** |
| **"Rate limiting active ✅ VERIFIED"** (commit `5929714` "slowapi installed") | Startup log on clean clone → `slowapi not installed — rate limiting disabled` | **FALSE** |
| **Gmail "Connect"** | `POST /api/connectors/gmail/connect` with empty token still returns `connected: true` | **Not fixed** |
| **All 8 connectors** | All still `oauth_configured: false, demo_mode: true` | **Not fixed** |

### 🔴 New regressions introduced by the latest commits
| Regression | Verified how |
|---|---|
| **Backend test suite got worse** | v1 audit: 2 failed + 7 errors. Latest clone: **2 failed + 9 errors** (135 s). The new whisper code added failures. |
| **"Trusted silence" wiring broke** | New test `test_materiality_gate_v2_wired_into_whisper` **FAILS** — the whisper endpoint does not call `materiality_gate_v2`. The new feature advertises trusted silence but doesn't execute it. |
| **Whisper endpoint errors in-suite** | 2 new `test_whisper_system.py` ERRORs (shared-state pollution, same root cause as the consent tests) |

### 📊 Score impact of the new commits
| Parameter | v1 (audited) | v2 (latest) | Why |
|---|---:|---:|---|
| AI Intelligence | 1.5 | 1.5 | Rule-based whisper early-exit is a real optimization, but materiality-gate wiring broke (trusted silence regression) — nets flat |
| Mobile UI | 4.0 | **4.5** | Real whisper-card surface added to Dashboard (but still never run on device) |
| Product Design | 4.0 | **4.5** | A genuine new user-facing surface with purpose |
| Reliability | 3.0 | **2.5** | Test suite regressed; new feature shipped red |
| Backend | 4.0 | 3.5 | Suite worse; "rate limiting verified" re-confirmed false |
| All others | unchanged | unchanged | |
| **Weighted total** | **3.48** | **3.45** | **Effectively unchanged — net slightly worse** |

**Conclusion:** The team is *active* and *capable of writing real behavioral code* (the whisper tests prove intent). But the score did not move, because the work bypassed the four structural failures and added a fresh measurement-integrity breach. **Activity is not progress until the scoreboard is trustworthy.**

---

## 1. The Single Most Important Finding for This Roadmap

> **The falsification pattern from v1 did not stop — it escalated.** v1 found a commit claiming `1.00 vs 0.76, PASS` over a file reading `0.31 vs 0.70, FAIL`. The latest version adds a *new* instance: a "GATE PASS, +15.9" claim citing a results file that **is not in the repository**, beating a baseline that was **hardcoded to a more favorable value** (0.514) than the reproducible computed value (0.7).

This is why **Phase 0 is the gate for everything.** A roadmap that tells you to "build real AI (Phase 1)" is useless if the team's own success meter is capable of reporting "PASS" while the artifact shows "FAIL." Every phase below therefore begins by assuming the measurement can lie, and is structured to make that mechanically impossible.

The team's own `ROADMAP_TO_9_OF_10.md` is a genuinely good *build* plan (it maps cleanly onto Phases 1–9 below). What it lacks — and what this roadmap adds — is the **measurement-integrity layer** that their build plan silently assumes. Their `ROAD_TO_9_STATUS.md` reports a weighted 4.4 and dozens of "FIXED ✓"; my independent execution reports 3.45 with the same items still red. **That 0.95-point gap *is* the problem this roadmap exists to close.**

---

## 2. Scorecard: Current (v2) → Target

| # | Parameter | Weight | v2 (latest) | Phase 1 | Phase 3 | **Final 9.0** |
|---|---|---:|---:|---:|---:|---:|
| 1 | AI Intelligence | 15% | **1.5** | 5.0 | 7.5 | **9.0** |
| 2 | Mobile UX | 15% | 3.0 | 5.0 | 7.0 | **9.0** |
| 3 | Backend | 15% | **3.5** | 6.0 | 7.5 | **9.0** |
| 4 | Mobile UI | 10% | 4.5 | 5.5 | 7.5 | **9.0** |
| 5 | Performance | 10% | 4.0 | 5.5 | 7.5 | **9.0** |
| 6 | Reliability | 10% | **2.5** | 5.5 | 7.5 | **9.0** |
| 7 | Product Design | 10% | 4.5 | 5.5 | 7.5 | **9.0** |
| 8 | Security | 5% | 4.0 | 6.5 | 8.0 | **9.0** |
| 9 | Privacy | 5% | 6.0 | 7.5 | 8.5 | **9.0** |
| 10 | Accessibility | 5% | 4.0 | 6.0 | 7.5 | **9.0** |
| — | **Weighted total** | 100% | **3.45** | **5.6** | **7.6** | **9.0** |

---

## 3. PHASE 0 — Measurement Integrity (Weeks 1–2) — NOW THE ABSOLUTE PREREQUISITE

> v1 called this "truth baseline." The re-review upgrades it to a hard gate: **no other phase may start until Phase 0 is green**, because the re-review proved the scoreboard is still capable of reporting green over red. This phase is *mostly* engineering of trust, not product features.

### 0.1 The Reproducibility Law — kill "cited-but-uncommitted"
**The exact failure this fixes:** Gold-150 "GATE PASS" cites `gold_150_llm_active_full_results.json`, which is not in the repo.
**Work:** CI rule — *any* status row, commit message, or doc that names an artifact file (results JSON, screenshot, report) **fails the build if that file is not committed and under 7 days old.** A claim pointing at a missing file is a build error, not a prose choice.
**Done when:** the Gold-150 row cannot read "PASS" while its file is absent — CI blocks the merge.

### 0.2 The No-Hardcoded-Baseline Law — kill cherry-picked metrics
**The exact failure this fixes:** `bm25_baseline = 0.514` hardcoded in 6 scripts; reproducible value is 0.7.
**Work:**
- Remove every hardcoded baseline. All baselines are **computed by a committed script** whose output is committed alongside the score.
- There is exactly **one** canonical baseline script and **one** canonical gold set. The 0.5 / 0.514 / 0.7 drift across 3 files is illegal; pick one corpus, one scorer, one number.
- The lift metric reads its baseline from that script's output, never a literal.
**Done when:** deleting the literal `0.514` everywhere and recomputing reproduces the same baseline to 4 decimals on a clean clone, and the committed Gold-150 verdict matches the committed numbers.

### 0.3 The Verdict-Matches-File Law — kill summary-over-substance
**The exact failure this fixes:** commit messages and CLAIM_FREEZE say "PASS"; the file says "FAIL."
**Work:** the verdict string in every results file is **derived** from the numbers by an assertion (`gate_pass = lift >= 0.15`), never hand-set. CI parses the file and asserts the human-readable claim equals the computed verdict. A mismatch is a failed build.
**Done when:** no human can type "PASS" into a place that disagrees with the data.

### 0.4 Get the suite green, for real (Backend, Reliability)
**The exact failure this fixes:** 2 failed + 9 errors; new whisper code added failures.
**Work:**
- Fix the **materiality-gate regression** the new feature introduced (whisper endpoint must actually call `materiality_gate_v2`, or honestly label trusted-silence as not-yet-wired).
- Give every erroring test a temp-DB fixture (the shared-SQLite pollution behind both consent and whisper errors).
- CI runs the **full** suite on every PR, not a curated subset. A green subset over a red full run is forbidden.
**Done when:** `python -m pytest tests/` exits 0 on a clean clone, 3 consecutive runs, full suite.

### 0.5 Fix the three "still false" defaults (Backend, Security, AI)
**The exact failures:** rate limiting disabled; LLM inactive by default; Connect fakes a connection.
**Work:**
- Add `slowapi` to `pyproject.toml` (not optional). Startup must show the limiter active.
- Make `connect` **fail-closed** — empty/unverified token returns an error, never `connected: true`.
- Decide honestly on the default LLM: either ship a real default provider key via secret manager, or label the product "limited mode" everywhere. Stop marking `active: true` true on a clone.
**Done when:** re-running the audit's `curl` battery reproduces all three as fixed.

### 0.6 Rotate the PAT and reconcile Briefing ↔ build (carried from v1, still open)
Still unaddressed. The leaked PAT must be confirmed revoked; the Investor Briefing still describes a "4-item sidebar / swipe-card briefing" that the 6-tab app does not contain.

**Phase 0 exit gate:** Weighted ≥ 5.0, and — critically — **the CI trust rules (0.1–0.3) are merged and enforced.** From this commit forward, the falsification class of failure is mechanically blocked. *This is the single most important deliverable of the entire roadmap, and the re-review proves it cannot be skipped.*

---

## 4. PHASE 1 — Make the AI Real (Weeks 2–10) — CRITICAL PATH

> Unchanged in substance from v1. The re-review confirmed the AI is still rule-based on clone and still loses to BM25 (0.3067 vs the real 0.7). The only addition: Phase 1's work is now **scored under the Phase 0 trust rules**, so the Gold-150 gate is a real gate, not a self-graded one.

### 1.1 Honest baseline under the new rules (Week 2)
Re-run Gold-150 with `--require-llm` (abort if any question falls to the rule path). The result file is **committed**; the verdict is **computed**; the baseline is **derived**, not hardcoded. Per-type scores public (temporal is currently 0.0 — a known real gap).

### 1.2 Default LLM that fires (Weeks 2–4)
Clean clone must show `active: true`. Secret-managed provider key, never in repo.

### 1.3 Beat the real BM25 by ≥15 pts (Weeks 3–7)
Target composite ≥ **0.85** (current committed 0.3067; real baseline 0.7). Real embeddings + hybrid rerank; fix the answer synthesis that truncates mid-`**` and leaks `dict.__repr__` into `reasoning_chain`; lift temporal (0.0) and contradiction/multilingual specifically.

### 1.4 Latency under the real path (Performance)
Streaming, TTFT <1.5 s, full-answer p95 <4 s. (The whisper early-exit already helps the non-AI path; this targets the AI path.)

### 1.5 Learning loop from real data (AI, Reliability)
`/api/calibration` today returns 0 predictions / null Brier. Wire real prediction→outcome flows; publish a Brier with ≥30 real resolved predictions and a 95% CI that matches the Briefing.

### 1.6 Re-wire trusted silence (AI)
**New from re-review:** the materiality-gate regression must be fixed — the whisper path must actually call `materiality_gate_v2`, or the feature cannot claim "trusted silence." Then benchmark false-positive rate + critical recall on 100 moments.

### 1.7 Ablation — earn the complexity
Per module, Gold-150 with it disabled. Keep only modules that lift ≥2 pts; delete the rest from the default path.

**Phase 1 exit gate:** Gold-150 ≥ 0.85 (real computed baseline), verdict auto-derived and file committed, AI ≥ 7.5.

---

## 5. PHASE 2 — Mobile Reality (Weeks 4–14) — CRITICAL PATH 2

> Unchanged from v1. **Confirmed:** the app has *still* never run on a device (re-review found no device-validation work in the 4 new commits — they were web/whisper work). This remains gating.

### 2.1 Dependency hygiene
Confirmed still broken: `react 18.3.1` + `react-dom 19.0.0`; `expo 53` vs `jest-expo 52`; `--legacy-peer-deps` still required. Align and drop the flag.

### 2.2 Device validation (iOS Simulator + Android Emulator + ≥2 physical)
Cold launch <1.2 s, TTI <1.5 s, scroll ≥58 fps, memory <250 MB. **The whisper cards and Copilot flow must be exercised on a real device before they can score.**

### 2.3 Offline-first write queue; 2.4 onboarding funnel; 2.5 polish system
As in v1.

**Phase 2 exit gate:** Mobile UX ≥ 7.0, Mobile UI ≥ 7.5, device benchmarks green in CI.

---

## 6. PHASE 3 — Reliability, Security, Scale (Weeks 10–20)

> Substantially unchanged. Re-review additions in **bold**.

### 3.1 Chaos/fault matrix (network/auth/LLM/DB/OAuth/storage/permissions) — green in CI; crash-free ≥99.9%.
### 3.2 Postgres + observability (RED metrics, tracing, alerting).
### 3.3 Load: 10/100/1k/10k concurrent. p95 <300 ms @1k, <800 ms @10k. **Re-verify under the real LLM path, not the rule-based shortcut that produced today's sub-20 ms numbers.**
### 3.4 Multi-device sync + conflict resolution.
### 3.5 Security: complete the 200+ injection suite (homoglyph/leetspeak); **add a dependency/secret scan to CI since "slowapi installed" was claimed but false — claims about installed packages must be asserted by the build, not stated in prose**; independent third-party pen test, no Critical/High.

**Phase 3 exit gate:** Reliability ≥ 7.5, Security ≥ 8.0, Backend ≥ 7.5, Performance ≥ 7.5.

---

## 7. PHASE 4 — Connectors Go Live (Weeks 8–16)

> Unchanged. **Confirmed:** all 8 connectors still `demo_mode: true`; Slack/GitHub still never tested with real credentials. Start OAuth credential procurement on day 1.

### 4.1 Real OAuth lifecycle for Gmail/Calendar/Slack/GitHub (consent→exchange→refresh→ingest→dedupe→disconnect→**provider-side revocation**→reconnect).
### 4.2 Draft generation + approval end-to-end via the real provider API.
### 4.3 Extraction F1 ≥ 0.85; **fix the deadline mis-attribution bug (re-confirmed latent: a Friday date was tagged "next Tuesday")**.

**Phase 4 exit gate:** all four VERIFIED by real-credential E2E.

---

## 8. PHASE 5 — Polish, Privacy, Accessibility, Delight (Weeks 16–24)

> Unchanged. The whisper subsystem is a good start toward "delight" but is unproven on-device.

### 5.1 Product-thinking pass: every screen earns its place; the commitment problem demonstrably solved; ≥7/10 "would miss it."
### 5.2 Privacy to 9: enforce retention TTLs (with tests), GDPR/CCPA flows verified by execution, minimized egress, third-party review.
### 5.3 Accessibility to 9: WCAG 2.1 AA on-device (VoiceOver/TalkBack/Dynamic Type/contrast) by independent audit.
### 5.4 Delight layer: motion/haptic grammar, empty-state craft; heuristic review ≥9 vs Linear/Things/Superhuman.

**Phase 5 exit gate:** all 10 parameters ≥ 9.0.

---

## 9. The Verification Protocol — Upgraded for the Re-Review Failures

v1 had a good protocol; the re-review showed it needs **teeth against the specific failure modes that actually occurred.** Every milestone ships:

1. **A runnable command** on a clean clone (not the author's machine — the Gold-150 "pass" relied on a Kaggle tunnel only the author had).
2. **The committed artifact** it produces. A claim citing an uncommitted file is a build failure (Phase 0.1).
3. **Derived, not authored, metrics.** No hardcoded baselines (0.2); no hand-set verdicts (0.3).
4. **Independent sign-off.** The author cannot flip a row to VERIFIED.

CI enforcement (the part that was missing):
- **Artifact-existence check:** every named file must exist and be fresh. *(Would have caught the missing Gold-150 file.)*
- **Baseline-derivation check:** a grep for numeric baseline literals in scoring code fails the build. *(Would have caught `0.514`.)*
- **Verdict-consistency check:** parse results files; assert `gate_pass` field equals `lift >= threshold`. *(Would have caught the PASS-over-FAIL commit.)*
- **Default-install assertion:** a smoke test that boots the server on a clean clone and asserts `active`, rate-limiter-on, and connect-rejects-empty. *(Would have caught all three "still false" defaults.)*
- **Full-suite gate:** the *full* `pytest tests/` must pass; a curated subset is not acceptable evidence. *(Would have caught the 9 errors behind "tests pass".)*

These five CI checks are the concrete deliverable that turns "we promise to verify" into "we cannot ship a lie." They are cheap to write and they target exactly the five failures the re-review found.

---

## 10. Per-Parameter Path to 9 (executable definition of done)

| Parameter | From (v2) | → 9.0 requires (executable proof) |
|---|---:|---|
| **AI Intelligence** | 1.5 | Default LLM active on clone; Gold-150 ≥0.85 vs the *real computed* baseline (committed file, derived verdict); 0 hallucinations; real Brier ≤0.15; materiality gate actually wired (whisper path calls it); ablation proves every module |
| **Mobile UX** | 3.0 | Validated on real devices; cold <1.2s; offline write-queue; onboarding ≥85% |
| **Backend** | 3.5 | Green **full** suite on clone; rate limiting on (asserted by build); Postgres + observability; 99.9% under chaos; declared deps |
| **Mobile UI** | 4.5 | Deps resolved; pixel-perfect on device; responsive; polished motion/haptics; whisper cards proven on-device; heuristic ≥9 |
| **Performance** | 4.0 | Cold <1.2s, TTI <1.5s, **AI-path** TTFT <1.5s (not rule-path), scroll 60fps, p95<300ms@1k |
| **Reliability** | 2.5 | Full fault matrix green; crash-free ≥99.9%; no test regressions on new features |
| **Product Design** | 4.5 | Doc=build; every screen earns its place; commitment problem demonstrably solved; "would miss it" ≥7/10 |
| **Security** | 4.0 | Rate limiting asserted-on; secrets rotated; injection suite 100%; package claims verified by build; clean third-party pen test |
| **Privacy** | 6.0 | Retention enforced + tested; GDPR/CCPA verified; minimized egress; third-party review |
| **Accessibility** | 4.0 | WCAG 2.1 AA verified on device by independent audit |

---

## 11. Sequencing & Critical Path

```
Week  1–2   Phase 0: MEASUREMENT INTEGRITY  ◄── now a hard gate (re-review proved it)
Week  2–10   Phase 1: AI real               ◄── longest pole; scored under Phase-0 trust rules
Week  4–14   Phase 2: mobile reality        ◄── needs iOS hardware (start Wk 2)
Week  8–16   Phase 4: connectors live       ◄── needs real OAuth creds (start Wk 1)
Week 10–20   Phase 3: reliability/security/scale
Week 16–24   Phase 5: polish/privacy/a11y → all 9s
```

**The re-review's effect on sequencing:** Phase 0 was already first; it is now **blocking**. Nothing downstream may merge until the five CI trust checks (§9) are live, because every downstream measurement inherits the scoreboard's honesty. There is no point asking "did AI improve?" if the meter can still say PASS over FAIL.

---

## 12. Reconciliation with the Team's Own Roadmap

The repo already contains `ROADMAP_TO_9_OF_10.md` and `ROAD_TO_9_STATUS.md`. They are good documents. This roadmap is **complementary, not contradictory:**

- **Where we agree:** the phase decomposition (truth freeze → mobile → backend → connectors → AI → copilot → security → scale → beta) is essentially identical. The acceptance criteria (cold-launch targets, F1 ≥ 0.85, WCAG AA, real-credential E2E) agree.
- **Where this roadmap differs — and why it must:**
  1. **Measurement integrity is missing from theirs.** Their status log self-reports "FIXED ✓" on items my execution found still red (rate limiting, LLM-active, Gold-150). Their weighted score (4.4) is ~0.95 above my execution score (3.45) for the same code. This roadmap makes the integrity layer Phase 0 with CI teeth.
  2. **Theirs scores categories that don't map to the audit scorecard.** "Core product usefulness," "Reasoning quality," etc. are reasonable internal metrics, but the audit (and this roadmap) score the 10 parameters an external party will judge. Align the internal scorecard to the external one, or it will drift again.
  3. **Theirs doesn't have a "no-hardcoded-baseline / no-uncommitted-artifact" rule.** These are the two rules that would have prevented the Gold-150 falsification. They are the highest-leverage additions in this document.

**Recommendation to the team:** adopt your `ROADMAP_TO_9_OF_10.md` as the build plan, and adopt **this document's Phase 0 + §9 CI checks** as the trust layer that governs it. The two together are stronger than either alone.

---

## 13. How We'll Know We Got There (unchanged bar, sharper test)

Re-run the original certification audit against a fresh clone. The result must be:

- **Weighted total 9.0 / 10**, no parameter below 9.
- **Claim Verification Matrix:** ≥90% VERIFIED by execution; **zero FALSE**.
- Every parameter row links to a runnable evidence command a cold reviewer can execute and reproduce.
- The Investor Briefing contains only claims the scoreboard shows verified.
- **And — the re-review's new bar — the five CI trust checks (§9) are green on `main`, so the result is not a one-time snapshot but a continuously-enforced property of the repo.**

At that point, and only with the executed evidence in hand, the classification moves from **BELOW AVERAGE / Do Not Ship** to a credible **WORLD CLASS / Ship**.

---

### Audit re-review execution log (reproducible)
```
git clone MaestroAgent (latest)           → head e01ee6d (4 commits past audited 422ddc1)
pip install -e . (+PYTHONPATH backend)    → OK
python -m pytest tests/                   → 2 failed, 9 errors / 1,108 collected   (WORSE than v1's 2+7)
mobile: npm i --legacy-peer-deps; npx jest → 78 pass; tsc EXIT 0 (still string/theater tests)
curl /api/llm-status                      → {active:false, provider:"none", "Rule-based"}  (STILL false)
curl POST /api/connectors/gmail/connect (empty token) → {connected:true}              (STILL fake)
startup log                               → "slowapi not installed — rate limiting disabled" (STILL off)
find … gold_150_llm_active_full_results.json → MISSING (cited proof not committed)
grep bm25_baseline=0.514 in scoring scripts → HARDCODED in 6 files (reproducible value is 0.7)
git diff 422ddc1..HEAD --stat             → 10 files, +869/-16 (whisper subsystem + schema)
```
*Every line above was produced by execution against the latest clone, not read from any commit message.*
