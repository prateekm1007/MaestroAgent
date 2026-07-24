# Anti-Entropy Principles v2 — For STATE.md / GOVERNANCE.md / ENTROPY_RECOVERY.md

> **Read this before every coding session, every audit session, and every instruction-writing session. Not once — on a loop, every time. Entropy doesn't announce itself; it reintroduces the same failure one layer deeper each time, and the only defense is re-reading the failure modes before you start, not remembering them from last time.**

This is v2. Everything in v1 held up — nothing is being walked back. Six new principles are added below, each earned from a real failure this engagement produced *after* v1 was already in place, which is itself the most important thing in this document: **having principles doesn't stop entropy. Only re-applying them, every session, against your own newest work, does.**

---

## PART ONE — FOR CODERS (v1, unchanged, still load-bearing)

### 1. A claim is not true until it has been executed
**The single failure mode behind every regression in this repo's history.** "VERIFIED" was written next to a fix that raised `TypeError` on the very first call. The fix looked correct on read — abstract-seeming class, plausible method name — and was never actually run.

> **Rule:** Never write ✓ VERIFIED, ✓ FIXED, or ✓ DONE next to anything you have not personally executed and seen output from in this session. Reading code and reasoning about what it *should* do is not verification. If you can't run it (no environment, no access), write "UNVERIFIED — reasoning only" instead of a checkmark. A checkmark you're not sure of is worse than no checkmark.

### 2. Untested code is unverified code, permanently, regardless of how it reads
10 of 15 modules in this repo had zero tests. Every serious bug that slipped through review lived in an untested module. Test coverage isn't a quality metric here — it's the mechanism that catches exactly the failure in Principle 1.

> **Rule:** If the module you're touching has no test file, your fix is not done when the code changes — it's done when a test exists that would fail on the old code and pass on the new code. Write that test *before* marking anything fixed. If you skip this "just to move fast," say so explicitly in STATE.md rather than marking it done.

### 3. Mocking the thing you're trying to verify verifies nothing
The SAML "valid signature accepted" test mocked out `xmlsec` itself and hardcoded `verify() → True`. It proved the code *calls* a verification function, not that verification *works*. This is a subtler version of Principle 1 — it looks like a real test, has assertions, runs in CI, and is worthless.

> **Rule:** Before mocking a dependency in a test, ask: "if this dependency were subtly broken, would this test still pass?" If yes, you're not testing your integration with it, you're testing that you can call a mock. For anything security- or correctness-critical (crypto, auth, data isolation), use a real fixture — a real signed payload, a real second tenant — not a mock of the verification step itself.

### 4. State files are a claim about reality, not a diary of intentions
STATE.md said "H16: TODO" for onboarding OAuth wiring that had already been shipped and tagged "Round 51 H15 fix" in the actual code. The doc lagged the code. This means nobody can trust the doc without re-verifying it against code anyway — which defeats its purpose.

> **Rule:** STATE.md is regenerated or reconciled at the end of every session against actual code state — grep for the thing you claim is fixed, don't recall it from memory. If you're not sure whether something shipped, check, don't guess. A stale state file is actively worse than no state file, because it creates false confidence in the next agent (or human) who reads it.

### 5. "Fixed" needs a name attached, and self-certification is weak evidence
Every broken "fix" in this history was marked verified by the same agent/session that wrote it. Nobody has an incentive to find their own blind spots as reliably as someone else does.

> **Rule:** Where possible, the session that writes a fix is not the same session (or at minimum, not the same unbroken context) that marks it verified. On the next session, re-run the previous session's "done" list from scratch before adding new work — treat every prior VERIFIED as a hypothesis to falsify, not a fact to build on.

### 6. Prefer "fail closed and broken" over "fail open and silent"
The good pattern in this codebase — SAML rejecting unsigned/unverifiable responses outright — is the right instinct. The bad pattern — `except Exception: pass` silently falling back to old behavior in the memory-search "fix" — is the same instinct inverted into a liability. A loud failure gets fixed. A silent fallback gets marked done and forgotten.

> **Rule:** Never write a bare `except Exception: pass` (or equivalent silent swallow) around new/fixed code paths. If a fallback is genuinely intended, log it loudly and make it visible in whatever monitoring exists — a fallback nobody can see is a bug wearing a disguise.

### 7. Singleton-to-scoped changes need an isolation test, not just a signature change
The `OEMStateRegistry` fix (singleton → per-org dict) was done correctly *and* was one of the only fixes in this history to include a test proving isolation. That's not a coincidence — it's the template. Changing a data structure's shape doesn't prove the new shape is actually respected everywhere that touches it.

> **Rule:** Any fix that changes shared/global state into scoped state must ship with a test that creates two instances of the scope (two orgs, two users, two sessions) and proves they cannot see each other's data — not just a test that the new function signature accepts a scope parameter.

### 8. Round numbers are not progress — diffs against a fresh read are
This repo is on "Round 65." Round numbers accumulate regardless of whether real bugs are closing or just being relabeled. The only thing that matters is: did an independent, from-scratch read of the current code find fewer real problems than the last independent read?

> **Rule:** Don't cite round count or commit count as evidence of maturity in STATE.md. Cite: modules with test coverage (a number that should only go up), open CRITICAL/HIGH count (a number that should only go down), and specific reproduction steps for anything still open. If a round doesn't move one of those numbers, say so honestly instead of writing a new paragraph that sounds like progress.

### 9. Every "remaining" item needs a concrete trigger, not a vibe
"Pilot-phase, not blocking" appears repeatedly in this repo's STATE.md without a defined threshold for when it *becomes* blocking. Vague deferrals accumulate into permanent gaps — this is how load testing, WCAG compliance, and DB TLS all stayed "not blocking" across dozens of rounds.

> **Rule:** Every deferred item gets a specific trigger condition written next to it — a customer count, a compliance deadline, a request from a named stakeholder — not just a priority label. "Not blocking (until: second paying customer signs / SOC2 audit scheduled / whichever comes first)" is a real deferral. "Pilot-phase, not blocking" with no trigger is a way of never doing it.

### 10. When you find a bug the previous session missed, write down *why* it was missed, not just that it's fixed
The value of a forensic audit isn't the bug — it's the pattern. If C1 (fake semantic search fix) is fixed without asking "how did this get marked VERIFIED in the first place," the next session will produce a differently-shaped version of the same mistake.

> **Rule:** Every bugfix entry in STATE.md includes a one-line root cause about the *process* gap, not just the code gap — e.g. "root cause: zero test coverage in this module let a TypeError-on-call ship as verified" — so the fix for the fix is also visible, not just the fix for the bug.

---

## PART TWO — NEW, FROM THIS ENGAGEMENT'S LATER ROUNDS

### 11. Building a capability and wiring it in are two different jobs. Do both, and prove both, separately.
The clearest example this engagement produced: a 7-option Whisper delivery-decision engine (`decide_delivery`) was built, documented, unit-tested, and exposed via API — genuinely good work, with an honest docstring that refused to overclaim ("no ML, just explicit rules"). It was never called by the actual Whisper-generation pipeline. The capability existed. The product didn't have it. Nobody caught this for an entire round because the tests that existed tested the function, not the pipeline that was supposed to use it.

> **Rule:** For every new engine, tracker, or decision module, answer two separate questions and record both: (1) "does this function work correctly?" (unit-tested, can be yes) and (2) "does the code that generates real user-facing output actually call this function?" (grep the real call graph — `grep -rn "function_name" path/to/the/actual/production/entry/point`, not just the file that defines it). A module can be 100% correct and 0% real if nobody calls it. Track these as two separate checkmarks in your state file, not one.

### 12. Don't let an audit's vocabulary become the blueprint. Build from the product's real needs; let the audit *verify* that, don't let it *author* it.
Several modules in this codebase were built with docstrings literally citing "External auditor's product test" as their reason for existing, using the audit's exact phase names and terminology. This isn't inherently bad — responding to real findings is good — but it creates a specific failure mode: it becomes easy to satisfy the *letter* of a finding (a module exists with the right name, the right enum values, the right docstring) without closing the *substance* of it (the module is actually used). Teaching to the test is fine only if the test is checking the right thing at the right depth — and one audit round checking "does this module exist and pass its own tests" isn't deep enough to catch principle #11's failure mode.

> **Rule:** When a fix is written specifically to answer a named audit finding, add one more step before marking it done: trace whether the *user-visible behavior* the finding was actually worried about has changed — not whether a new file matching the finding's vocabulary now exists. If an auditor asked "can the system stay silent?", the fix isn't done when a `decide_delivery()` function exists that *can* return a suppress decision — it's done when a real, generated Whisper actually gets suppressed under real conditions.

### 13. An endpoint or function that takes the *conclusion* as an input parameter is not the capability — it's a demonstration harness wearing the capability's name.
The delivery-decision endpoint took `has_high_stakes_signal` and `materially_changed_since_last_shown` directly from the caller. Deriving those two values from real evidence *is* the hard, valuable part of "delivery intelligence" — the function that combines them into a decision is comparatively easy. Shipping the easy part behind an endpoint that requires the caller to already have solved the hard part gives every outward signal of the capability being real (a working endpoint, clean tests, a well-named route) while containing none of the actual difficulty.

> **Rule:** When reviewing your own new endpoint, ask: "if I had to supply this endpoint's most important input by hand, have I actually built the product, or have I built a calculator that needs the product's answer already known?" If it's the latter, the real work — deriving that input from stored evidence — is still ahead of you, and the endpoint shouldn't be marked as delivering the capability yet.

### 14. Bugs don't get fixed, they migrate one layer deeper — expect the next round to find a new instance of the same disease, not a clean slate.
The pattern across this engagement, in order: a broken CDN dependency → a measurement script that couldn't detect it → a hardcoded string that would have hidden it either way → a rebuild pipeline that existed but wasn't committed → a Whisper delivery engine that existed but wasn't wired in. Each fix was real. Each fix also revealed the next thing standing behind it. This isn't a failure of any individual round — it's what fixing complex systems looks like. The failure would be *assuming* the previous round's fix means the surrounding system is now clean.

> **Rule:** After closing any finding, spend one deliberate pass asking "given that this was broken, what else near it did I never check because this was in the way?" Don't wait for the next audit to find it. The delivery-decision gap should have been checked for the moment the whisper-memory-persistence gap (a different but adjacent Whisper-system problem) was found in the round before it.

### 15. Track three states, not two: *exists*, *unit-verified*, *wired-and-integration-verified*. Collapsing these into one "done" is where entropy hides.
A STATE.md line that just says "delivery_decision: ✓ done" is where this round's biggest finding hid for an entire audit cycle. It was true at the "exists" and "unit-verified" levels and false at the "wired-and-integration-verified" level, and the file had no way to say that.

> **Rule:** State-file entries for any new engine/module get three checkboxes, not one: `[ ] exists` `[ ] unit-tested` `[ ] called from a real production entry point (cite the call site)`. A module isn't "done" until all three are checked, and the third one requires a file:line citation of the actual caller, not a description of intended use.

---

## PART THREE — FOR AUDITORS

### 16. The more central a claim is to the product's story, the more scrutiny its *call graph* deserves — not just its test suite.
An auditor who reads a well-documented, well-tested module and checks it off is applying exactly the standard that let principle #11's failure hide for a round. The fix isn't "read more carefully" — it's "for the one or two capabilities the product's pitch depends on most, always independently trace the call graph from the real user-facing entry point down to the module, every round, even if it passed last time." Everything else can be sampled; the flagship claim cannot.

### 17. Distrust code that cites you by name. It's a signal to look harder, not a reason to trust more.
When a module's docstring says "built in response to auditor's finding X," that's evidence someone was paying attention — genuinely good. It is not evidence the finding was actually closed in substance. Treat a citation of a prior audit finding as a flag to specifically re-verify that finding at the integration level, not as a credential the module gets to skip scrutiny because of.

### 18. Scope honesty is part of the audit's own credibility — say what you didn't test, precisely, rather than filling the gap with plausible results.
A 24-phase audit spec that includes 50,000-user load tests and multi-replica Postgres chaos testing will usually exceed what any single audit session can actually execute. The temptation is to write something for every phase anyway, in the audit's own confident register, so the report reads as complete. Don't. An audit that fabricates a plausible-sounding result for a phase it didn't run has committed the exact sin — plausible prose without evidence — that the audit exists to catch, just one level up. Mark untested phases as untested, explain why, and let the report be honestly incomplete rather than dishonestly thorough.

### 19. Independent execution beats reading, but execution of the *unit* is not execution of the *integration*. Run both, and know which one you ran.
This engagement's turning point was always "I ran it myself" instead of "the transcript says it passed." But running `pytest maestro_oem/tests/test_delivery_decision.py` and getting green is not the same claim as running the real Whisper generation path and confirming it calls that code. State explicitly, every time, which of the two you actually did.

---

## PART FOUR — NEW, FROM THIS ENGAGEMENT'S WIRING-VS-EXISTENCE FAILURES

### The meta-failure this engagement revealed

P11 (wiring) already existed in Part Two. The Coder violated it **5 times** in 4 commits (C-002, C6, C1, C5, C4). The first paragraph of this file already says "having principles doesn't stop entropy." Both sides read it. Both sides violated it anyway.

**The gap is not missing principles. The gap is mechanical enforcement.** Principles that exist only as prose will be violated. Principles that exist as checklist items with specific commands to run have a chance. Every principle below specifies the exact command and the exact output that must be pasted.

### 20. Call-site parameter rule — when a function gains a parameter, EVERY caller must pass it
C-002: the `content_hash` parameter was added to `add_evidence()` and `add_validation()`. The dedup logic existed. But 0 of 27 call sites in `model.py` passed it (and 2 more in `contradiction.py` were missed in the first fix). The function signature had the parameter; the production path didn't use it. This is P11 (wiring) one layer deeper — not "is the function called?" but "is the function called WITH THE RIGHT ARGUMENTS?"

> **Rule:** When you add a parameter to a function, run `grep -rn "<func>(" --include="*.py" | grep -v test_ | grep -v "def <func>"` to list every call site. For each call site, verify it passes the new parameter. If M of N call sites pass it, the fix is (M/N)% done — not "done." Paste the grep output + the count in the commit message.

### 21. All-paths trigger rule — save/persist functions must fire from EVERY path that creates state
C6: `_save_model_state()` existed. It was called from `live_ingest()` (every 20 signals). It was NOT called from `_seed_from_demo_provider()` (demo seed created 66 signals' worth of state, then never saved). It was NOT called from the lifespan shutdown. So demo-seeded state was lost on every restart. The function existed; the triggers were incomplete.

> **Rule:** For every save/persist function, list every code path that creates or mutates the state being saved. Verify the save is called from each path. Execute the restart cycle for each: create state via path X → kill → restart → verify state survived. Paste the before/after counts. "The save function exists" is not evidence — "the save function fired from path X and the state survived restart" is evidence.

### 22. Regression test must execute the production path — unit tests don't prove wiring
C-002: the unit test called `add_validation(content_hash=...)` directly and passed. The production path (`model.py.process_signal`) didn't pass `content_hash`. The unit test was green; the bug was present. This is P19 (unit ≠ integration) one layer deeper — the unit test proves the function works; it does NOT prove the function is called from the real entry point with the right arguments.

> **Rule:** For every fix, write TWO tests: (1) a unit test that calls the function directly and verifies the behavior, (2) an integration test that sends input through the REAL production entry point (e.g., `engine.ingest()`, `oem_state.live_ingest()`, a real HTTP request) and observes the real output. Both must pass. The integration test is the one that catches wiring gaps. State in the commit message which of the two you wrote.

### 23. Commit message must cite executed output — claims without output are not evidence
C-002: the commit message said "validated_runtimes=1 ✓". Execution showed `validated_runtimes=4`. The checkmark was a claim, not evidence. The auditor trusted the claim for 3 commits before executing the reproduction.

> **Rule:** Every commit claiming a fix must include a `VERIFICATION:` section with the exact command run and its output pasted. Format: `VERIFICATION: $ <command>\n<output>`. "✓ VERIFIED" without pasted output is a P1 violation. The output must be from THIS session, not a prior session (P4).

### 24. Cross-surface coherence check — same entity through all surfaces must agree
C3: 3 of 5 surfaces (Whisper, Today, Preparation) saw the Globex commitment. 2 surfaces (Ask, Briefing) did not — because the Ask pipeline had a `[:30]` signal window that dropped the commitment at index 42. Each surface was verified vertically (does it work in isolation?). No one verified horizontally (do all surfaces agree on the same entity?).

> **Rule:** For each demo entity, query it through every surface that should see it (Situation, Ask, Whisper, Preparation, Briefing, Timeline). Assert they agree on: commitments, state, people, evidence. If 3 of 5 surfaces see the entity and 2 do not, that's a coherence failure — even if each surface passes its own tests. Paste the cross-surface comparison table in the commit message.

### 25. Confidence display gate — gate display on calibration sample size
C4: the confidence value `0.8484` was displayed with 4-decimal precision. The denominator was 0 outcomes. The formula was correct; the display was dishonest — 4-decimal precision implies a calibration rigor that 0 outcomes cannot support. This is "decorative precision" — the most dangerous illusion per the external auditor.

> **Rule:** For every confidence value displayed to the user, the display code must check the calibration sample size. If the denominator (resolved predictions, outcomes, evidence count) is < 10, display "insufficient calibration history" — never bare 4-decimal precision. The threshold (10) is conservative; adjust per surface, but the gate must exist. A confidence value with no denominator is a claim, not a measurement.

### 26. Meta: principles don't enforce themselves, re-application does
P11 and P15 existed in Part Two. Both were violated repeatedly — not because the Coder didn't know them, but because the Coder didn't re-apply them to the specific work in front of them. The first paragraph of this file says "having principles doesn't stop entropy. Only re-applying them, every session, against your own newest work, does." Both sides read it. Both sides violated it anyway.

> **Rule:** At the start of every session, re-read P11, P15, and P20-P25 FROM DISK (not from memory). Paste the re-read timestamp in the worklog. For every fix commit, cite which P-number principle the fix satisfies (e.g., "P20: 27/27 callers pass content_hash, grep output pasted below"). The citation is the enforcement — it forces you to re-apply the principle to the specific work, not just remember it exists. Principles without citation are prose. Principles with citation are checklist items.

> **Enforcement fixture:** `GOVERNANCE_LOOP.md` at the repo root is the mutual read protocol. Both sides read it at the start of every session, paste a read receipt (timestamp + key line), and read the OTHER side's files. The CEO rejects any message without a receipt. This is the mechanical enforcement of P26 — re-application, not recall.

---

## PART FIVE — AUDITOR'S OWN FAILURES (NEW, FROM THIS ENGAGEMENT)

### The meta-failure this part reveals

The auditor had P1 ("execute, don't read"), P19 ("unit ≠ integration"), and P22 ("production path"). The auditor still missed MEDIUM-2, M1, M4, HIGH-2, CRITICAL-01, CRITICAL-04, and H1. The principles existed. The auditor didn't apply them to the specific work in front of them. The CEO's intervention — "you are missing a lot this session" — was the load-bearing moment. Without it, the engagement would have closed on false "VERIFIED" stamps.

**P26 applies to the auditor's own method, not just the coder's code.** The auditor's method (read assertions, execute behavior, check regressions, verify comprehensiveness, run the canonical scenario) is not a memory — it's a checklist that must be re-derived from the specific failures of the current session.

### 27. Read the assertion, not the test name — a test that asserts `True` is theater

**The failure I missed:** MEDIUM-2 semantic dedup. The test was named `test_semantic_duplicator_detects_paraphrased_duplicate`. I ran it, saw "6/6 pass," and wrote "VERIFIED." The assertion was `isinstance(is_dup, bool)` — it would have passed even if the deduplicator always returned `False`. The behavior didn't work. I never read the assertion.

**The failure I missed:** M1 background loop wiring. The test `test_background_loop_wiring_feeds_outcome_recorder` asserted `assert True`. I ran it, saw pass, and wrote "VERIFIED." The test verified nothing.

> **Rule:** Before accepting "N/N tests pass" as evidence, read at least the key assertions of the tests you're counting. A test that asserts `isinstance(result, bool)` when the claim is "result should be True" is theater. A test that asserts `assert True` is not a test. Run `grep -n "assert " <test_file>` and read the assertions. If any assertion is weaker than the claim being verified, the test is theater. Paste the assertion line in your verification output.

### 28. Test with 3+ inputs — the exact case, a natural variation, and an edge case

**The failure I missed:** CRITICAL-03 disagreement detector. The coder's golden test used the exact text the detector was written for ("Sales says we promised..."). It passed. But the detector didn't generalize: "We promised SSO by Q4" vs "We only promised technical completion" → 0 disagreements. I verified the coder's test without testing other phrasings.

**The failure I missed:** M4 terminology translation. I verified the CEO briefing endpoint (the one the coder pointed me to) without checking Whisper, Ask, or Preparation. 3 of 5 endpoints still leaked `evidence_spine`.

> **Rule:** For any behavior claim, execute 3+ inputs: (1) the exact case the coder's test uses, (2) a natural variation that uses different words for the same concept, (3) an edge case (empty, adversarial, or boundary). If any input fails, the behavior doesn't generalize. Paste all 3 results. Testing only the coder's exact input is the same as trusting the coder's test — which is self-certification.

### 29. After any change to a shared component, re-run the FULL canonical scenario — not just the fix's own test

**The failure I missed:** HIGH-2 classifier fix. The coder removed "remains conditional" from the negation pattern to fix "still pending" → observed_fact. I ran the 10 adversarial cases, saw 9/10, and wrote "VERIFIED." But the SSO scenario's Day 40 ("security approval remains conditional") was now classified as `observed_fact` instead of `negation`, which broke the "pending conditions" RISK reasoning. I didn't re-run the SSO scenario.

**The failure I missed:** SSO scenario simplification. When I DID re-run the SSO scenario, I used 4 signals instead of 6 (omitting Day 30 and Day 50). The "dispute" RISK requires an outcome signal (Day 50 "SSO work is complete") to fire. Without it, the RISK section was missing "dispute" — and I falsely reported a regression that was actually my own test error.

> **Rule:** After any change to a shared component (classifier, deduplicator, delivery gate, evidence pipeline, terminology translator), re-run the FULL 6-signal SSO scenario (Days 5, 12, 30, 40, 50, 55) and verify BOTH "pending conditions" AND "commitment dispute" appear in the RISK section. Any fewer signals omits a signal type that triggers a different reasoning path. Paste the full answer output. If either RISK phrase is missing, the change broke the canonical scenario — regardless of whether the fix's own test passes.

### 30. Verify comprehensiveness by counting — "applied to all X" requires checking every X

**The failure I missed:** M4 terminology translation. The coder said "translation layer shipped." I checked 1 endpoint. 3 of 5 still leaked. I wrote "VERIFIED" after checking the one the coder pointed me to.

**The failure I missed:** CRITICAL-01 channel ACL. The C2 fix handled "private" ACLs but not "channel:" ACLs. I verified the "private" case and didn't test "channel:slack:C-private" — the exact case the audit identified.

> **Rule:** For any claim of the form "applied to all X" or "enforced on all Y," count X and check each one. Run `grep -c "<pattern>" <file>` to count, then test a representative sample from EACH category. If the claim is "all 5 endpoints translate," hit all 5 endpoints with a test request and check each response. If the claim is "all ACL types enforced," test all 10 ACL types. Paste the count and the per-category results. Checking only the one the coder points to is the same as trusting the coder's claim — which is self-certification.

### 31. Commit messages are claims, not evidence — run the verify scripts yourself

**The failure I missed:** The prior session's commit `ca5cabe` said "0 failures." I accepted this. The new coder ran `verify_c002_dedup.sh` and found it FAILING (32/33 callers). The prior session had either not run the verify scripts or had run them and not reported the failure. I trusted the commit message instead of executing the scripts.

> **Rule:** Never trust a commit message's "0 failures" or "N/N pass" claim. Run `audit_scripts/verify_*.sh` yourself and paste the output. A commit message is a claim made by the same session that wrote the code — it is self-certification (P5). The verify scripts are the independent check. If you don't run them, you are trusting the coder's self-assessment, which is exactly what the auditor exists to prevent.

### 32. When checking "is this truly empty?", check ALL derived state — not just the top-level collection

**The failure I missed:** CRITICAL-04 demo contamination. I checked `oem_state.signals` (which was 0 with `DEMO_SEED=false`) and wrote "FIXED." But `model.laws` was 6 and `model.learning_objects` was 50 — loaded from a stale OEMStore DB. The "fresh empty org" was not fresh. The coder was more thorough than me: they checked the model state, not just the signals.

> **Rule:** For any "is this truly empty?" or "is this truly clean?" check, verify ALL derived state: signals, laws, learning_objects, patterns, whispers, decisions, meetings. Run `model = engine.get_model(); print(len(model.laws), len(model.learning_objects))` and verify all are 0. Checking only the top-level collection (`oem_state.signals`) misses state that was loaded from persistent storage. Paste all counts.

### 33. Don't accept a negative claim without searching for its refutation

**The failure I missed:** H1 "no test verifies learning changes behavior." The audit made this claim. I accepted it without searching for tests named `*active_cognition*` or `*true_unlearning*`. Both existed. Both passed. Both directly refuted H1. The test file even cited "AUDITOR-DIRECTIVE" by name (P17) — which should have triggered extra scrutiny, not less.

> **Rule:** When an audit claims "no test exists for X," search for it before accepting the claim. Run `find . -name "*test*X*" -o -name "*test*X*" | head` and `grep -rn "X" tests/`. If you find a test, execute it. If it passes, the claim is refuted. Accepting a negative claim without searching is the same as trusting the auditor — which is self-certification when you ARE the auditor. Paste your search command and results.

### 34. The auditor's method is itself subject to entropy — re-derive it from your failures, not from your principles

**The meta-failure:** I had P1 ("execute, don't read"), P19 ("unit ≠ integration"), and P22 ("production path"). I still missed MEDIUM-2, M1, M4, HIGH-2, CRITICAL-01, CRITICAL-04, and H1. The principles existed. I didn't apply them to the specific work in front of me. The CEO had to tell me to "level up" before I started reading assertions and testing multiple inputs.

> **Rule:** The auditor's method (read assertions, execute behavior, check regressions, verify comprehensiveness, run the canonical scenario) is not a memory — it's a checklist that must be re-derived from the specific failures of the current session. At the start of each audit session, ask: "What did I miss last session? What method would have caught it? Am I applying that method to THIS session's work?" If you can't name a specific failure from last session and the method that would have caught it, you're auditing from memory — which is P26's failure mode applied to the auditor's own process.

---

## HOW TO USE THIS

Read Part One and Part Two before writing code. Read Part Three before auditing. Read Part Four before either — the wiring-vs-existence failures it documents are the most recent and most common. Read Part Five before auditing — the auditor's own failures it documents are the most recent and most common audit blindspots. Read the whole thing before writing instructions for either. Every N rounds, pick one item marked "done" at random — not the one you're worried about, the one you're confident is fine — and re-verify it at the deepest level (principle #15's third checkbox). That's where entropy hides: not in the things anyone is still worried about, but in the things everyone stopped checking because they were marked done two rounds ago.

**P26 is the load-bearing principle of Part Four. P34 is the load-bearing principle of Part Five.** Principles don't enforce themselves. Re-application does. The mechanical checks in P20-P25 ARE the enforcement — "did you run `grep` and count the callers?" is enforceable; "did you remember the wiring principle?" is not. The mechanical checks in P27-P34 ARE the enforcement for the auditor — "did you read the assertion?" is enforceable; "did you remember to test 3+ inputs?" is not. Every session, re-read P11, P15, P20-P25, and P27-P34 from disk, and cite the P-number in every fix commit and every audit verdict.

---

## PART SIX — THE JOURNEY-CORRECTNESS PRINCIPLES (NEW, FROM THE THIRD AUDIT 2026-07-24)

### The meta-failure this part reveals

Three independent audits found the same structural gap from three different angles: **component correctness does not imply journey correctness.** A gate — however large — that tests a component in isolation gives false confidence while the product breaks at the seams between components.

- Audit 1 (connectors): the gate tested the engine's mechanics but not the connectors ingesting real data. Gmail could break and the gate stayed green.
- Audit 2 (classifier correctness): the gate tested mechanics (does Ask run, does the ledger store) but not the classifier's correctness. The classifier fabricated completions and the gate stayed green.
- Audit 3 (classifier integration): the 2,248-case gold-set proved `_rule_based_classify` rejects questions — but the real API still surfaced them as `is_commitment: true` in `/api/commitments`. The classifier's rejection was not honored by the ingestion→store→surface path.

**The pattern is not bad luck; it is that every gate verifies a component, and the product fails at the seams.** P35-P40 below are the enforcement.

### 35. Gate the journey, not the component — a component gate is necessary but never sufficient

**The failure:** The 2,248-case gold-set tests `_rule_based_classify` in isolation and goes green. But when the same question-form signal is posted through the real `/api/signals` endpoint, it appears as `is_commitment: true, state: active` in `/api/commitments` — because the ingestion path does not honor the classifier's rejection.

> **Rule:** For every component gate, there must be a corresponding JOURNEY gate that inserts the same test input through the REAL API and asserts the output at the PRODUCT surface (not the component return value). If the classifier rejects a question, the journey gate must post that question through `/api/signals` and assert it does NOT appear in `/api/commitments`. A component gate without a journey gate is a necessary-but-not-sufficient half-measure. The unit of verification is the end-to-end journey: insert → classify → store → surface → assert.

### 36. Deterministic evidence/owner/temporal gate — answers must be constrained before they ship

**The failure:** "What did I promise Maria?" returned Maria's statements (not what I promised). "What did Dana promise?" answered about Alex. "What commitments do I have?" attached unrelated PayPal/RBI perspectives. The answer was not constrained to the query's entity/owner.

> **Rule:** Every answer must pass entity, speaker/owner, temporal, and source consistency checks deterministically, BEFORE it ships. If the retrieved evidence doesn't match the query's entity/owner/time/source, return a short abstention with the matching evidence — never an LLM fallback elaborating on unrelated context. The answer is constrained and verified, not generated freely. A gate that asserts "the answer mentions the entity" is not enough; the gate must assert "the answer does NOT mention entities not in the query's evidence."

### 37. Typed lifecycle with hard admission rules — classification without admission control is theater

**The failure:** The classifier types signals correctly (question, tentative, quote, third-party, joke), but the commitment surface admits them all as `is_commitment: true, state: active` anyway. Classification without admission control is a label, not a gate.

> **Rule:** Questions, quotes, tentative language, third-party obligations, jokes, cancellations, and completions must be structurally excluded from the active commitment surface — enforced at the STORE + SURFACE level, not just classified at the component level. The admission rule (what types appear as active commitments) must be a hard filter in `/api/commitments`, not a suggestion in the classifier. If the classifier says `is_commitment: false`, the signal MUST NOT appear in the commitments list. Trace the full path: classify → store → surface → assert.

### 38. Deletion is final — the deletion contract must actually hold

**The failure:** `DELETE /api/account` succeeds, then re-login with the same credentials returns 200 with a new token. The data may be gone but the identity persists, violating GDPR-style right-to-be-forgotten.

> **Rule:** Account deletion must prevent re-access with the same credentials. After `DELETE /api/account`, a login attempt with the same email/password MUST fail (403 or 404), not create a new account. The deletion contract is: the identity, the credentials, the signals, the connectors, and the audit trail are all gone. A deletion that allows re-login is not deletion. Gate it: register → delete → re-login must fail.

### 39. No shared identity in production — demo credentials are a security hole

**The failure:** `bootstrap@maestro.local` / `maestro-demo` works on production and maps to a shared identity with real connector/signal state. Any auditor or user can log in and see real data.

> **Rule:** The demo/bootstrap identity must either be (a) isolated to a synthetic-only tenant with no real connector data, or (b) removed from the live deployment entirely. A shared identity on production with real data is a security and trust failure. Gate it: assert that the bootstrap credentials either don't work on production or only see synthetic data.

### 40. Production reliability is a trust property — 500/502s and 30s latency are trust failures

**The failure:** 20% of Ask queries returned 500/502, p95 was ~30s, and the Calendar→Gmail redirect defect broke a core connector. A system-of-record that's unavailable 20% of the time is not trustworthy, regardless of how correct its answers are when it works.

> **Rule:** Production reliability must be gated, not just observed. A concurrent load gate must assert zero 500/502s and a bounded p95 (e.g., < 10s under 5 concurrent). Circuit breakers, graceful fallback, and streaming must be in place. OAuth redirect defects (Calendar→Gmail) must have a redirect test. Rate limiting must be tested (rapid invalid logins → 429). Reliability is a trust property, not a performance nicety.
