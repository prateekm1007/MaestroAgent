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

### 41. Single source of truth for classification/ownership — derive, don't duplicate

**The failure:** The 5-layer ownership trace exposed a class-level smell: the classification/ownership truth was stored in FOUR parallel places — the signal's metadata, the ledger's `commitment_type` column, the evidence dict, and the pre-built answer lines. Each copy drifted, and each drift was a layer the CTO had to chase (dont→don't, signal_id→source_signal_id, ledger never synced, evidence dict missing commitment_type, answer built before filter). The denormalization IS the bug class.

> **Rule:** At read time, the answer and its evidence are DERIVED from ONE reconciled record (the signal's metadata), never assembled from parallel copies that must be re-synced after every migration. The commitment_ledger becomes a CACHED VIEW — its commitment_type column is derived from signal metadata at read time, never written independently. Build that, and the next ownership/classification fix is one change, not five. This is the structural end of the wack-a-mole the 5-layer trace exposed.

### 42. Normalize text before structural matching

**The failure:** The tentative filter missed "I will try to get it done, but dont count on it" because the hedge check matched "don't" but the text had "dont" — an apostrophe defeated the rules engine. Every contraction variant was being manually duplicated in every keyword list (don't AND dont, can't AND cant, I'll AND ill), which is brittle by construction.

> **Rule:** Case-fold AND normalize punctuation/contractions (`don't`/`dont`, `can't`/`cant`, `I'll`/`ill`) BEFORE any hedge, keyword, or interrogative check. A rules engine that breaks on an apostrophe is brittle by construction; normalization makes the structural checks robust to trivial orthographic variation. Normalize once, check many — never duplicate contraction variants in keyword lists.

---

## PART SEVEN — THE INTEGRITY PRINCIPLES (NEW, FROM THE MODEL-ATTRIBUTION BREACH 2026-07-25)

### The meta-failure this part reveals

The arc's recurring ghost — placeholder connectors, stale-frontend gates, corpus-vs-test-signal gaps, built-but-not-wired functions, model-attribution lies — is the SAME lie at every level: the request/probe side says one thing, the served side did another. Part Seven names the four principles that kill the class permanently.

### 43. Built-but-not-wired is not done

**The failure:** `reconcile_signal()` passed its 7/7 unit tests but the live ask path still ran the prior 5-layer inline ownership filter. The function was a scaffold, not a fix — the structural refactor was a well-tested promise, not a live change. This is the same shape as the k3 sweep built-but-not-run, the reclassify migration before it ran, the classifier gold-set while the corpus stayed stale.

> **Rule:** Every new function ships with a journey assertion proving the live path calls it — typically by asserting the live response carries a value only that function can produce. A unit test proves the function; only a journey assertion that the LIVE response uses it proves the product does. A function that passes its unit test but is never called by the live path is a scaffold, not a fix.

### 44. Resilience is not speed

**The failure:** The LLM circuit breaker (S2-6) trips after three >25s calls and falls back to rules-only. That is a genuine P40 resilience fix — fail-closed instead of hanging. But it does NOT make a normal slow query fast; it makes a STUCK LLM degrade after the user has already waited through three 25-second failures. Crediting the breaker as "the latency fix" is mis-attribution.

> **Rule:** A circuit breaker, retry, or fallback makes a broken dependency DEGRADE; it does not make a slow dependency FAST. Credit a breaker as the safety net it is; the latency fix is streaming plus a bounded time-to-first-token, measured at p50/p95 on the live path. Never report a degradation strategy as a latency win.

### 45. Local-green is a hypothesis; CI-green-on-push is the proof

**The failure:** 56 new tests passed locally across 8 files, plus 67/67 regression. But no CI run URL on the pushed commits was shown — and the arc has repeatedly demonstrated local-green diverging from CI-green and product-green. The missing-`Header` import was local-invisible and crashed production; the journey gate was locally fine and red in CI on contention; the version label was locally changed and stale in the Docker cache.

> **Rule:** No fix is reported done on local test output alone. The report includes the CI run URL on the pushed commit, with the permanence gate and the relevant journey tests green. A local suite is how you DEVELOP confidence; CI on the commit is how you EARN it. Paste the run.

### 46. Verify the served instrument, not the requested one

**The failure:** The CTO↔Kimi-K3 loop script requested `moonshotai/kimi-k3` and logged the request-side model. But on long engineering prompts, Kimi K3 (a deep-reasoning model) timed out, and a silent fallback served the work via Gemma 12B — while the log still said "kimi-k3". The probe string "KIMI_K3_VERIFIED" proved only that a short probe call reached kimi-k3, NOT that the engineering work did. This is the same lie as the product's `oauth_configured=True` on a placeholder, the gate-green on a stale frontend, the "verified live" on a freshly-posted signal instead of the corpus.

> **Rule:** Any claim that a tool, model, connector, or path did the work is proven by the RESPONSE-SIDE evidence (served model, returned state, actual stored value, OpenRouter generation ID), never by the request-side field or a separate probe. A probe that the instrument is PRESENT is not proof it PLAYED THE WORK. Enforce this everywhere — read `response.model` on every call, assert it equals the expected instrument, fail loudly on any mismatch or timeout (NEVER relabel a fallback), and log the generation ID for external cross-check.

### 47. Structure delegation to the model's latency budget

**The failure:** Kimi K3 completes focused prompts in a few minutes and times out on sprawling ones. The long engineering prompts (8KB spec, multiple context files) timed out at the OpenRouter layer, and the old loop silently substituted Gemma. The 205-second latency on a restructured shorter prompt is the explanation for the entire prior breach — and the operational constraint that prevents recurrence.

> **Rule:** Decompose large engineering tasks into small, single-responsibility prompts the model can finish within its latency budget, rather than one giant prompt that times out and tempts a fallback. And where a task genuinely exceeds the budget and must be done by the orchestrator, ATTRIBUTE IT TO THE ORCHESTRATOR HONESTLY — the sin was never "the CTO wrote code"; the sin was relabeling it as Kimi K3. Honest attribution, whatever the author, is the standard.

### 48. A red CI with known failures is not a gate

**The failure:** The Test Suite CI job was "always a little red" on pre-existing backend test failures — and the new maestro-personal journey gates (P43/P41/P42/S2-*/S3-2) were not in CI at all, because test.yml only ran backend tests. A perpetually-red suite trains everyone to ignore red (the boy-who-cried-wolf failure that lets a real regression slip through), and a suite that doesn't run the new tests at all can't catch their regressions.

> **Rule:** Keep every CI suite either green or honestly split, so red means a real regression, not Tuesday. If a suite has known-failing tests, either fix them or split them into a separate job (e.g., "backend-legacy" vs "personal-journey-gates") so a red in one doesn't train ignoring red in the other. A gate with known failures is not a gate — it's noise.

### 49. Verify the served deploy state, not the workflow's claim

**The failure:** The CTO reported "Deploy: FAILED (Railway did not converge)" based on the GitHub Actions Deploy workflow's convergence-check step failing. But Railway's own API showed the deploy as SUCCESS — the workflow's verification step was stricter than Railway's status and false-negatived. The CTO then spent a turn "debugging the deploy failure" when the deploy had actually succeeded. This is P46 applied to deploys: the workflow CLAIMS failure, the platform's actual status is the truth.

> **Rule:** A deploy is proven by the platform's actual status (Railway `SUCCESS` + live `/api/health` returning the new SHA), not by a CI convergence-check that can false-negative. When a workflow says "deploy failed," check the platform API directly — the workflow's verification step may be stricter or buggier than the platform's own status. Report the served deploy state, not the workflow's claim.

---

## PART EIGHT — THE INGEST-JOURNEY + RESILIENCE PRINCIPLES (NEW, FROM THE FIFTH AUDIT 2026-07-25)

### The meta-failure this part reveals

The fifth audit (independent, adversarial, from-scratch) converged on the same 🟡 the arc has held — and it found the NEXT layer of breakage: the read side is fixed (P43 ownership, P42 normalization, P41 SSOT) but the WRITE side (ingest) is still broken on messy real-ish input. Entity extraction grabs date tokens and pronouns as entities; jokes become commitments; cancellations are missed; third-party reports are undetected; the Gmail and Slack ingest paths use inconsistent taxonomies. The gold-set (2,248 cases) tested the commitment-type classifier on clean cases — but never tested entity extraction or the Slack ingest path on adversarial input. This is the gate-testing-the-component-not-the-journey pattern once more, now at the ingest layer.

### 50. Gate the ingest journey, not just the classifier component

**The failure:** The auditor ingested new text via the Slack ingest path and found it broken: entity extraction grabs `"Friday."`, `"I'm"`, `"Audit_Test"` as entities; a joke ("conquer the moon") becomes a `commitment_made`; a cancellation is missed; third-party reports aren't detected; the taxonomy is inconsistent between Gmail and Slack paths. The reclassify migration fixed the EXISTING corpus; the gold-set tested the commitment-type classifier on CLEAN cases — but neither covered entity extraction or the Slack ingest path on adversarial input.

> **Rule:** Entity extraction, classification, and ledger-write must be tested END-TO-END on messy, adversarial, real-ish input (dates, pronouns, jokes, cancellations, third-party reports, mixed Gmail/Slack formats) — not just the commitment-type classifier on clean cases. The gold-set must grow to cover entity extraction (no date/pronoun tokens as entities) and every ingest path (Gmail AND Slack) with a single consistent taxonomy. The ingest side is where the ledger is WRITTEN; if it's broken there, no amount of Ask-side fixing makes the product trustworthy.

### 51. Ask never fails silently

**The failure:** Under an LLM outage window, multiple Ask queries returned `answer:""` with all-None fields and zero user feedback. `/api/debug-llm` threw an unhandled 500. The circuit breaker (S2-6) handles SLOW (fails closed to rules after three >25s calls) — but the audit found that under DEAD (empty/500 responses), Ask returns a blank answer with no fallback and no error. The user cannot tell "Maestro found nothing" from "Maestro broke."

> **Rule:** Ask must NEVER return a blank answer. On any LLM failure (timeout, 500, empty response), Ask returns an explicit, ledger-grounded answer with a clear "AI unavailable right now — here's what I know from your ledger" note — never `answer:""`. The breaker handles slow; a separate fallback handles dead. And `/api/debug-llm` must not throw an unhandled 500 — it returns a structured error. Silent empty is forbidden; it is the one unforgivable failure for a trust product.

### 52. The demo is synthetic and PII-free, and the demo identity is never conflated with a real person

**The failure:** Logging in as `bootstrap@maestro.local` yields a server principal of `default@personal.local`, and Ask "who am I" asserts "You are PRATEEK (PRATEEK MISRA)… Zerodha Client ID TND670." The synthetic demo corpus is contaminated with Prateek's actual identity and a real brokerage client ID, which Ask then surfaces as the user's identity. A demo that leaks the founder's real PII into answers is a privacy defect and a trust-killer for any evaluator.

> **Rule:** Purge real PII (names, client IDs, brokerage accounts, real email addresses) from the seed corpus. The demo principal must be a clearly-synthetic identity (e.g., "Demo User" with a synthetic email). A demo that surfaces the founder's real brokerage ID is a defect, not a fixture. The demo identity must NEVER conflate with a real person.

### 53. "Trusted silence" has a floor

**The failure:** `behavior/patterns` reports `dismissal_rate:1.0`, so The Moment returns `has_moment:false` ("user dismisses 100% of suggestions"). The "trusted silence" feature is HIDING the one feature it should surface, based on a 100%-dismissal artifact in the seed data. A first-run user sees NOTHING, which reads as "broken," not "calm."

> **Rule:** Dismissal-based suppression must NEVER hide the flagship feature on a synthetic or fresh-user artifact. It requires real dismissal history (a minimum number of dismissals — e.g., 5) AND a minimum-confidence threshold below which The Moment still surfaces. A fresh user with no real dismissal history always sees The Moment. A synthetic seed corpus must not produce a 100%-dismissal artifact that suppresses the hero feature.

---

## PART NINE — THE MASTER + PROSE PRINCIPLES (CONSOLIDATED FROM ALL FIVE AUDITS)

### The meta-failure this part reveals

Across five audits, the same patterns recurred in prose before they had numbers. These are the principles that were voiced as guidance but not yet codified as enforcement — the master principle all the others serve, and three operational principles that complete the set. Part Nine codifies them so the full set P1-P57 is in one place, each earned by a specific failure.

### 54. Fix the data the user sees, not just the path (THE MASTER PRINCIPLE)

**The failure:** Across four audits, the same shape: the gold-set passed while the existing corpus stayed stale; the classifier was fixed for new signals but the demo still showed questions as commitments; the reclassify migration was built but not run; the P43 wiring was code-complete but the live path still ran the old filter. In every case, the PATH was fixed but the DATA THE USER READS was not.

> **Rule:** A fix applied to the code path but not to the corpus the user actually reads is NOT A FIX. Every fix must reach the data the user sees — the existing corpus, the live API response, the deployed frontend. This is the root of P5 (re-classify the corpus), P35 (gate the journey), P43 (built-but-not-wired), and P50 (gate the ingest journey). If the fix doesn't reach the user's eyeballs, it's a scaffold.

### 55. Report true state, never fake readiness

**The failure:** Placeholder Yahoo/Microsoft credentials made `oauth_configured=True` while the OAuth flow broke on click. The probe string "KIMI_K3_VERIFIED" proved only a short call, not the engineering work. The demo banner said "DEMO" but the corpus contained real PII. In each case, a status field reported "ready" while the underlying state was placeholder, partial, or broken.

> **Rule:** No placeholder, partial, or failed state ever reports as configured/connected/committed. If a credential is a placeholder, `oauth_configured=False`. If a model call timed out, the task is "NOT DONE BY KIMI K3." If the demo has real PII, the demo is "CONTAMINATED," not "ready." Report the SERVED truth — the actual state, not the wished state. This is P46 applied to every status field in the product.

### 56. Rules are the authority for structure; the LLM is for nuance — and the rules hold a veto

**The failure:** The Gemma runtime LLM classified a textbook question ("Will you send the report by Friday?") as a real commitment, and the product trusted the LLM over the rules classifier. The rules classifier correctly said "not_a_commitment" — but the LLM result was preferred, and the question surfaced as an active commitment. The LLM was wrong on a clear-cut structural pattern where the rules were right.

> **Rule:** Deterministic rules decide clear-cut structural patterns (questions, negations, tentative hedges, third-party reports) — they are fast, free, and reliable. The LLM handles genuine ambiguity (intent, context, nuance). For NON-COMMITMENTS, the rules HOLD A VETO: if the rules say "not a commitment" and the LLM says "commitment," the rules win. The LLM may override the rules only in the direction of CAUTION (classifying a borderline commitment as tentative), never in the direction of PERMISSIVENESS (classifying a question as a commitment). The sin is trusting the LLM's permissiveness over the rules' structural correctness.

### 57. Classification must be inspectable

**The failure:** The API omitted classification metadata from signal responses. When a misclassification occurred, there was no way to diagnose it through the API or UI — the signal appeared as `is_commitment: true` with no visible `commitment_type`, `classification_reasoning`, or `llm_powered` flag. This contradicted the product's "inspectable memory" thesis and made every misclassification undiagnosable.

> **Rule:** Every signal exposes its classification metadata through the API AND the UI: `commitment_type`, `is_commitment`, `classification_reasoning`, `llm_powered`, `confidence`, `owner`. The user can see WHY a signal was classified the way it was — not just THAT it was. A classification that can't be inspected can't be trusted, can't be corrected, and can't be audited. Inspectability is the precondition for the correction loop.

---

## THE FULL PRINCIPLE INDEX (P1-P57)

**Part One (P1-P10):** The original coder principles — execute don't claim, test don't assume, mock don't verify, state drift, self-certify, swallow exceptions, isolation, cite rounds, defer, document misses.

**Part Two (P11-P15):** The deeper coder principles — visible defaults, small surfaces, durability, component vs integration, re-application.

**Part Three (P16-P19):** Call-graph scrutiny, distrust code that cites you by name, scope honesty, integration vs unit execution.

**Part Four (P20-P26):** Call-site parameters, all-paths trigger, regression on production path, commit cites output, cross-surface coherence, confidence display gate, meta-enforcement.

**Part Five (P27-P34):** Auditor's own failures — read assertions, test 3+ inputs, re-run canonical scenario, count comprehensiveness, run verify scripts, check all derived state, search for refutation, re-derive method.

**Part Six (P35-P40):** Journey-correctness — gate the journey, deterministic entity/owner gate, typed lifecycle admission, deletion finality, no shared identity, reliability is trust.

**Part Seven (P43-P49):** Integrity — built-but-not-wired, resilience≠speed, local-green is hypothesis, verify served instrument, structure delegation, red CI is not a gate, verify served deploy state.

**Part Eight (P50-P53):** Ingest + resilience — gate the ingest journey, Ask never blank, PII-free demo, trusted silence floor.

**Part Nine (P54-P57):** Master + prose — fix the data the user sees, report true state, rules hold a veto, classification is inspectable.

---

**The short version, if it must fit on a wall:** *Fix the data the user sees. Report the served truth, not the requested wish. One source of truth, derived at read time. Classify by structure with the rules holding a veto, and re-classify the corpus when the classifier changes. Never fail silently, never fake readiness, never relabel. A fix isn't done until it's wired live, green in CI on the push, and proven on the journey — not the component, not the probe, not the local run.*

---

## PART TEN — THE SECURITY + LIFECYCLE REDESIGN PRINCIPLES (NEW, FROM THE SIXTH AUDIT 2026-07-25)

### The meta-failure this part reveals

The sixth audit tested paths the fifth did not — mutations, full lifecycle, export — and found three S0s that were there the whole time. The arc's recurring ghost (component verified, journey untested) now has a security dimension: read isolation was verified and credited, while the write path stood open. Classification was relabeled and credited, while cancellations never cancelled. The ownership filter was fixed and credited, while the user's own promises disappeared. Each was a layer the prior audit didn't test.

### 58. Authorization covers mutations, not just reads

**The failure:** The sixth audit reproduced a cross-tenant mutation IDOR: log in as bootstrap, collect `ledger_id`s; log in as a different user; `POST /api/commitments/{ledger_id}/transition?to_state=cancelled` → `200 {"transitioned": true}`. Bootstrap's ledger entries were cancelled by the auditor's account. The fifth audit verified READ isolation (E5) and the arc credited "multi-tenant isolation verified" — but neither tested mutations. The `/api/commitments/{id}/transition` endpoint took a `ledger_id` and transitioned it without verifying the entry belonged to the requesting user.

> **Rule:** Every state-changing endpoint — `transition`, `correct`, `dismiss`, `delete`, purge — must verify the target resource belongs to the requesting tenant BEFORE mutating, and the IDOR gate must test MUTATIONS (transition/correct/delete with another user's token → must 403/404), not only reads. A read-isolated, write-open API is not isolated; it is one enumerated ID away from any user rewriting any other user's ledger. Read isolation is necessary but it is NOT the security boundary; MUTATION isolation is.

### 59. Classification is not lifecycle

**The failure:** The sixth audit ingested the product's own synthetic lifecycle battery — completion emails, cancellation emails, a deadline change — and the result was `active: 12, completed: 1, cancelled: 0`. Cancellations were not applied. Completions did not close the commitments. The deadline change did not update. The reclassify migration re-labeled signal TYPES in the existing corpus, but the lifecycle engine that is supposed to APPLY a completion/cancellation/deadline-change signal to the corresponding commitment does not fire. Classification is not lifecycle.

> **Rule:** A completion/cancellation/deadline-change signal must APPLY a state transition to the matching commitment, with an evidence-linked, user-visible diff. The synthetic lifecycle suite must pass 100% (cancellations cancel, completions close, deadline changes update) before the lifecycle is called working. Labeling a signal "cancellation" while leaving the commitment active is theater — the product can classify correctly and still fail its thesis.

### 60. The ownership model has four distinct buckets

**The failure:** The P43 ownership filter correctly stopped attributing Maria's OWN promises to the user (the old false positive), but it now excludes the user's OWN commitments to Maria as well (the new false negative). "What did I promise Maria?" returns "no record" while the user HAS a promise to Maria. The filter swung from false-positive to false-negative because it filters by ENTITY rather than by OWNER — it cannot distinguish "my promise to Maria" from "Maria's promise."

> **Rule:** The ownership model must distinguish four buckets: `my_promise` (user → X), `their_promise` (X → user, or X's own commitment), `quoted` (user quoting X), `third_party` (someone else entirely). "What did I promise X?" returns `my_promise` to X — never `their_promise` (the old false positive) and never NOTHING when `my_promise` exists (the new false negative). The filter must distinguish OWNER, not just ENTITY.

### 61. The demo is synthetic-only with no real connected mailbox

**The failure:** The bootstrap tenant has a REAL connected Gmail with 209+ signals — Kotak Bank addressing "PRATEEK", Zerodha, Samsung, PayPal — readable by anyone with the demo password via Ask/export/signals. Dismissing 39 token-matched signals and redacting four strings did not remove the corpus. The fix is not redaction; it is disconnecting the real Gmail from the shared demo entirely and seeding synthetic-only data.

> **Rule:** Disconnect real Gmail from the shared demo entirely. Seed synthetic-only data. No token redaction scheme can substitute for not having the real corpus there at all. A shared demo with a real person's bank mail is not a demo; it is a breach waiting for a screenshot. The demo must be synthetic-only, PII-free, and have NO real connected mailbox.

### 62. Ask is deterministic ledger-QA first, LLM for polish

**The failure:** "What did I promise Maria?" returns a false negative ("no record") while the user HAS a promise to Maria. "What are my active commitments?" abstains with confidence 0.8 while evidence_refs contains active commitments — the answer contradicts its own evidence. LLM latency is 5-70s. Multi-turn session memory is broken. The stream is contaminated (a Maria query streamed "conquering the moon").

> **Rule:** Ask is deterministic ledger-QA first: sub-second structured answers with mandatory clickable evidence that always resolves to a source span. The LLM may rephrase for language polish but may NOT override the ledger or abstain while evidence is present. Hard p95 < 3s. Session memory must actually retain the referent across turns. The deterministic path is the authority; the LLM is the polish.

---

## PART ELEVEN — THE SECURITY + CONSISTENCY PRINCIPLES (NEW, FROM THE SEVENTH AUDIT 2026-07-25)

### 63. No hardcoded auth bypasses in production

**The failure:** A hardcoded `demo-bypass-token` in `verify_token()` returned `default@personal.local` for anyone who sent `Authorization: Bearer demo-bypass-token` — bypassing all authentication. This was live in production code. Any external attacker who guessed or found this string (it was in the source code) could authenticate as the demo user and read all demo data.

> **Rule:** Identity comes only from a validated token. Any local-test bypass must be env-gated (`MAESTRO_LOCAL_DEV=true`) and OFF in production. No hardcoded tokens, no magic strings, no backdoor identities. A hardcoded auth bypass in production is a disqualifying security hole.

### 64. One commitment truth model — no surface contradicts another; counts are structurally consistent

**The failure:** `/api/metrics` returned `active: -4` — an impossible value. `/api/commitments` returned `[]` while `/api/commitments/ledger` was populated. The Moment said `has_moment: false` while reconciliation showed 8 active commitments. Each surface computed its own snapshot from different sources, and they disagreed.

> **Rule:** Every surface — `/api/commitments`, `/api/commitments/ledger`, `/api/the-moment`, `/api/metrics`, `/api/what-changed`, Ask — reads from ONE reconciled commitment model (P41). Counts are derived from the same ledger snapshot and can NEVER go negative (clamp to 0). No surface contradicts another. An impossible value like `active: -4` is a structural defect, not a data issue — the code must make it unrepresentable.

---

## PART TWELVE — THE RULES-ONLY ROBUSTNESS PRINCIPLE (NEW, FROM THE SEVENTH AUDIT 2026-07-25)

### 65. A fix must hold on the rules-only path and in CI, not just the LLM path and the live deploy

**The failure:** The P43 ownership filter (F-03) only ran on the LLM ledger-fast-path. In rules-only mode — no LLM config, which is what every fresh clone runs and what every auditor hit — the ownership filter never ran. F-03 was fixed for the LLM path and silently unfixed for the path the audits actually test. Similarly, the P60 third-party exclusion was only verifiable on the live deploy, not in CI, because the code paths diverged — a fix the CI gate cannot observe is not permanent (P45).

> **Rule:** The audits test a fresh clone with no LLM config; if a fix only fires when the LLM is present, it is unfixed for the environment that gets audited. And a fix the CI gate cannot observe is not permanent. Ownership filtering, third-party exclusion, and every trust guarantee must run identically in rules-only mode and be verifiable in CI — the LLM may *enhance* them, but it must not be the *condition* for them. The trust guarantees are deterministic; the LLM is polish.

---

## PART THIRTEEN — THE CODE HYGIENE PRINCIPLES (NEW, FROM THE SEVENTH AUDIT ROOT-CAUSE ANALYSIS 2026-07-25)

### 66. Never add a local import of a name already imported at module level, inside the same function

**The failure:** `routers/ask.py` imported `reconcile_signals_for_user` at module level (line 20) and used it correctly at line 542. But 1,200 lines later, inside the same `ask()` function, a redundant local `from maestro_personal_shell.reconcile import reconcile_signals_for_user` (line 1775) made the name local to the ENTIRE function. Python's scoping rules mean any name assigned anywhere in a function body is local to the whole function — so the earlier reference at line 542 threw `UnboundLocalError` unconditionally, every time, LLM-on or LLM-off. The surrounding `except Exception: logger.debug(...)` swallowed it silently, and the query fell through to the situation-synthesizer path with no ownership filter. This was the ACTUAL root cause of the P43/P60 ownership filter failing — not "LLM unavailable."

> **Rule:** Never add a local `import` of a name already imported at module level, inside the same function. If a function is long enough that this is hard to notice, that's itself a signal the function should be split — a 4,000-line file with the same name imported twice 1,200 lines apart is a structural risk, not a style nitpick.

### 67. An except clause guarding a primary code path must log at error level, not debug

**The failure:** The `except Exception as e: logger.debug(...)` pattern that swallowed the `UnboundLocalError` appeared at least twice in `ask.py` (RC2 fast-path, ledger-state query). Silent debug-level swallowing is how the ownership filter broke without anyone noticing for however long it's been broken — the query silently fell through to a different code path with no ownership filter, and the user saw third-party reports in their promise queries.

> **Rule:** An `except Exception: logger.debug(...)` guarding a primary code path (not a genuine optional/fallback path) is a bug waiting to hide another bug. Any except clause that causes a fallthrough to a materially different answer-generation path must log at `error` level with full context and increment a visible metric — silent debug-level swallowing is how the ownership filter broke without anyone noticing.

### 68. A shared test fixture used by 15+ files is a single point of failure for the entire regression-detection signal

**The failure:** At least a dozen test files use a shared `auth_headers` fixture that logs in with the legacy shared-password scheme (`{"password": os.environ.get("MAESTRO_PERSONAL_TOKEN", "test")}`), which the current API doesn't accept. When it breaks, "N passed" numbers stop meaning what they used to mean — the full suite showed 63 failed, 275 errored, not the 5 the last worklog cited. Nobody noticed until an external auditor manually diffs error counts against failure counts.

> **Rule:** Treat shared test fixtures with the same "one source of truth" discipline as the commitment ledger. A shared fixture used by 15+ files is a single point of failure for the entire regression-detection signal — when it breaks, the test suite's pass/fail numbers become meaningless, and nobody notices until an auditor catches it. Shared fixtures must be tested independently and updated when the API contract changes.

---

## PART FOURTEEN — THE CROSS-MODULE CONTRACT PRINCIPLE (NEW, FROM THE P69 OWNER-KEY BUG 2026-07-25)

### 69. When a value crosses a module boundary, the key name is a contract — enforce it with a shared constant or a schema, not a duplicated string literal

**The failure:** `routers/signals.py` (the writer, on ingestion) stored the classifier's owner under `metadata["commitment_owner"]`. `reconcile.py` (the reader, P41 single source of truth) read `metadata.get("owner", "unknown")` — the wrong key. The classifier correctly computed `owner="user"` for first-person commitments, but it was stored under `commitment_owner`, not `owner`. So `reconcile.py` ALWAYS got `"unknown"`, and the P36/P60 ownership filter rejected EVERY record. This bug was live since commit `1acad66` (when `reconcile.py` was first written) — it predates the entire K3 audit arc. A "GREEN 8.5/10, ship it" verdict from a different audit process was given WHILE THIS BUG WAS LIVE, because no test inspected the `owner` field on the reconciled record. Every prior check either looked at the ledger table directly (which has its own separate `commitment_type` column, unaffected) or accepted a CI/test result without this exact trace.

> **Rule:** When a value crosses a module boundary — written by one file, read by another — the key name is a contract, and nothing enforces it automatically in a dict-based metadata blob. `metadata["commitment_owner"]` and `metadata.get("owner")` compiled fine, ran fine, threw no exception, and silently broke the single most safety-critical filter in the product for as long as it's existed. Any dict-shaped data crossing a writer/reader boundary between files needs either a shared constant for the key name (not a string literal duplicated in two places) or a schema/dataclass that would have made this a load-time error instead of a silent, permanent, undetected default. The standing rule this principle enforces: no ticket is closed on a worklog claim, a commit message, or another AI's verdict — closed means a live reproduction is posted and independently re-run. This rule exists because it already caught a live P0 twice in one day: once behind a Python scoping bug (P66), once behind this one-word key mismatch (P69). Both were invisible to prior "tests pass" and "GREEN 8.5/10, ship it" claims.

---

## PART FIFTEEN — THE ENFORCEMENT PRINCIPLE (NEW, FROM THE P70 TICKET-10b BUG 2026-07-25)

### 70. A principle written down after finding a bug does not retroactively protect code written to fix a different ticket in the same file, even minutes later

**The failure:** The TICKET-10 fix (third-party promise query exclusion) reintroduced almost exactly the shape of mistake P69 was named for (duplicated boundary-crossing logic instead of a shared source of truth) in the same session P69 was written up. The `_apply_ticket10_filter` function hand-rolled a DB path construction (`Path(__file__).resolve().parent / "personal.db"`) instead of calling the shared `default_sqlite_path()` utility — and the path was wrong (resolved to `routers/personal.db` instead of `maestro_personal_shell/personal.db`), silently hitting "no such table: signals" on fresh DBs and causing the filter to return 0 records and fall through without filtering. The P69 principle ("use a shared constant, not a duplicated string literal") was in the governance file, but the TICKET-10 code was written minutes later without consulting it.

> **Rule:** Treat "we wrote the principle down" and "the principle is now enforced" as different claims — the second one needs a grep-able CI check, not just a paragraph in a governance file, or it will be violated again by the next fix under time pressure. Every principle that names a specific code pattern (P69: shared key names, P66: no shadowed imports, P67: no silent debug excepts) needs a corresponding CI check that grep-fails on the pattern. A principle without enforcement is prose.

---

## PART SIXTEEN — THE INFRASTRUCTURE AUTOMATION PRINCIPLE (NEW, FROM THE WEB DEPLOY GAP 2026-07-27)

### 71. If it runs in production, it auto-deploys from main. No manual deploys.

**The failure:** The web frontend service on Railway was not configured for auto-deploy. Code fixes (removing mock data, wiring real API calls, fixing AskView, fixing confidence clamping) were merged and pushed to main. The backend auto-deployed within 90 seconds. The web service did not — it continued serving old code with mock "Q3 budget proposal" data for hours. The auditor caught this by checking the SSR HTML and finding mock data strings still present. The CTO believed the fix was live because the backend health endpoint showed the latest commit, but the web service was stale.

**The gap:** Manual deploys create a gap between "code is fixed" and "production is fixed." This gap violates the Finn Loop's assumption that merged code is live in production within minutes. When the loop breaks, verification becomes unreliable — the reviewer verifies against stale production, getting false negatives (fixes not visible) or false positives (bugs appear fixed but aren't live).

> **Rule:** If it runs in production, it auto-deploys from main. No manual deploys. Every Railway service must have "Auto Deploy" enabled (Settings → Deploy → toggle on). The deploy branch must be `main`. Health checks must be configured (`/api/health` for backend, `/` for web). After merging a PR, verify the deploy within 5 minutes by checking the health endpoint commit hash. If the hash doesn't match the latest merge commit, the auto-deploy is broken and must be fixed before any further work.

---

## PART SEVENTEEN — SYSTEMIC QUALITY PRINCIPLES (NEW, FROM CTO DIRECTIVE 2026-07-27)

### The meta-failure this part reveals

The arc has accumulated 71 principles earned from specific bugs. The external auditor still scored execution 2–4/10. The gap is not missing principles — it is the absence of systemic guarantees. Each prior principle catches a specific failure pattern after it ships; P72–P81 below are different: each one is a structural property the system must have by construction, enforced by a CI check that fails the build before the bug can ship. We are not adding more bug-catching principles. We are adding bug-preventing properties.

### 72. Data Hygiene Isolation

**Principle:** Demo, staging, and production environments must never share real user data. No real PII (names, emails, financial codes, API tokens) in any environment accessible to external users.

**Enforcement:**
- Demo environment: synthetic data only, regenerated on deploy
- Production environment: tenant-isolated, no shared state
- Admin endpoint `/api/admin/purge-real-gmail-from-demo` must run on every demo deploy
- CI check (`scripts/check_p72_data_hygiene.py`): grep for real email domains, financial codes, API token patterns in demo fixtures — fail if found

**Forbidden:** Connecting personal Gmail, real banking data, or API tokens to any shared/demo environment. (See FA29.)

**Metric:** Zero real PII in any demo response. Currently: dozens of instances (Kotak client codes, Zerodha IDs, founder names).

### 73. Recursive Ingestion Guard

**Principle:** The system must recognize its own outputs (drafts, auto-generated emails, Whisper responses, Briefing text) and never ingest them as external signals. A draft email Maestro generated on Tuesday must not become a "user commitment" on Wednesday when the user's Gmail sync pulls it back in.

**Enforcement:**
- All system-generated content tagged with `source_type: "self_generated"` and `generation_id: UUID`
- Ingestion pipeline rejects any signal matching a known `generation_id`
- Gmail connector filters out emails with `X-Maestro-Generated: true` header
- Signal creation endpoint rejects content matching recent draft signatures (fuzzy hash match)
- CI check (`scripts/check_p73_recursive_ingestion.py`): ingest a self-generated draft, verify it's rejected

**Forbidden:** Treating system-generated drafts as external commitments. (See FA30.)

### 74. Signal-to-Noise Ratio

**Principle:** The classifier must achieve >90% precision on commitment extraction. Newsletters, billing notices, security alerts, and automated notifications must be rejected at ingestion, not flagged for user dismissal.

**Enforcement:**
- Source-type awareness: every signal carries `source_type` (personal_email, newsletter, billing, notification, social, self_generated)
- Domain classification: 200+ known noise domains (mailchimp, substack, aws-billing, producthunt, etc.)
- Sender pattern matching: `noreply@`, `notifications@`, `billing@`, `no-reply@`
- Content pattern matching: unsubscribe links, billing amounts, security codes
- CI check (`scripts/check_p74_signal_to_noise.py`): 50+ noise samples, all must be rejected

**Metric:** Dismissal rate on `not_a_commitment` signals must be <10%. Currently 80%.

### 75. Performance Budget

**Principle:** No user-facing endpoint may exceed 5 seconds p95. Core flows (Ask, The Moment, Briefing) must be sub-second.

**Enforcement:**
- Performance budget in CI (`scripts/check_p75_performance_budget.py`): every endpoint tested, fails build if >5s p95
- LLM calls cached aggressively (same query + same evidence = same answer within TTL)
- Pre-computation: nightly batch job pre-computes The Moment, Briefing, What Changed for all active users
- Pipeline profiling: every Ask request logs retrieval time, assembly time, LLM time separately
- Caching layer: Redis or in-memory cache for repeated queries

**Metric:** `/api/ask` p95 latency <3 seconds. Currently 33s. ~10× improvement required.

### 76. Deduplication by Content Hash

**Principle:** Identical signal text from the same source must produce exactly one signal, never duplicates.

**Enforcement:**
- Signal creation computes `content_hash = sha256(source_id + normalized_text + entity)`
- Before insert, check for existing signal with same hash
- If exists: update `last_seen` timestamp, do not create new row
- Gmail connector: message-id based deduplication before ingestion
- CI check (`scripts/check_p76_deduplication.py`): ingest same email 10×, verify exactly 1 signal exists

### 77. Confidence Must Vary

**Principle:** Confidence scores must reflect actual certainty. Uniform confidence (e.g., all 0.95) means the confidence system is broken — it is reporting "I am sure" regardless of evidence.

**Enforcement:**
- Confidence computed from: number of corroborating signals (0.3 base), source reliability (0.2), temporal freshness (0.2), entity match quality (0.15), content clarity (0.15)
- Confidence must span range 0.3–0.95 in production ledger
- CI check (`scripts/check_p77_confidence_variance.py`): ledger must have `std_dev(confidence) > 0.15` — if lower, confidence system is broken
- Low-confidence signals (<0.5) flagged for user review, not surfaced as facts

### 78. Change Detection Requires Baseline

**Principle:** "What Changed" must track the user's last-seen state and compute actual deltas, not list current commitments.

**Enforcement:**
- Per-user `last_seen_at` timestamp on each entity/situation
- `/api/what-changed` computes: signals created/modified/resolved since user's `last_seen_at`
- Returns: `{new: [...], modified: [...], resolved: [...], contradicted: [...]}`
- Updates `last_seen_at` on read
- CI check (`scripts/check_p78_change_detection.py`): ingest signal, read what-changed (shows 1 new), read again (shows 0 new)

### 79. Semantic Disambiguation

**Principle:** Queries must disambiguate "my promises TO X" vs "X's promises" vs "signals involving X" at the retrieval layer, not the LLM layer.

**Enforcement:**
- Query parser extracts: `direction` (my-to-X, X-to-me, X's-promises, involving-X), `entity`, `temporal`
- Retrieval filters on `owner` field matching direction
- "What did I promise Maria?" → `owner=user, entity=Maria, direction=outbound`
- "What did Maria promise?" → `owner=Maria, direction=inbound`
- "History with Maria" → `entity=Maria, any owner`
- CI check (`scripts/check_p79_semantic_disambiguation.py`): 10 semantic disambiguation test cases, all must return correct owner

### 80. Deadline Normalization

**Principle:** Every relative deadline ("Friday EOD", "next Tuesday", "in 3 days") must be converted to absolute datetime at ingestion time.

**Enforcement:**
- `deadline_parser.py` module: converts relative dates using current timestamp as anchor
- Handles: "Friday", "next week", "EOD", "by 5pm", "in 3 days", "tomorrow"
- Stores both `deadline_text` (original) and `deadline_datetime` (absolute)
- Overdue detection: `deadline_datetime < now()` → overdue flag
- CI check (`scripts/check_p80_deadline_normalization.py`): 20 relative date patterns, all must parse to correct datetime

### 81. Prediction Accountability

**Principle:** Every prediction must have a resolution path and a measurable outcome. 0% accuracy means the prediction system is broken.

**Enforcement:**
- Every prediction has: `prediction_text`, `resolution_criteria`, `resolution_deadline`, `resolved_at`, `resolved_outcome`
- Background job: resolves predictions whose deadline has passed
- Brier score computed on all resolved predictions
- If Brier score > 0.5 (worse than random) for 30 days: prediction system flagged for review
- CI check (`scripts/check_p81_prediction_accountability.py`): synthetic prediction dataset with known outcomes, Brier score must be <0.3

---

## PART EIGHTEEN — CORRECTNESS AND COHERENCE PRINCIPLES (NEW, FROM CTO DIRECTIVE v2 2026-07-27)

### The meta-failure this part reveals

Two independent auditors hit production. They did not coordinate. They converged on the same verdict through different methods: 🔴 Not Ready. The smoking gun is the controlled transcript test — when fed a transcript containing one user commitment, one request, one third-party promise, one cancellation, one joke, one quotation, and one tentative — the product misclassifies the request and the third-party promise as the user's active commitments and silently drops the cancellation. This is not noise to be tuned. This is a category failure of the commitment intelligence layer. P82–P87 below are the structural guarantees that make this category of bug impossible.

### 82. Actor Attribution Correctness

**Principle:** Every extracted commitment must correctly attribute its actor (user, third-party, system, organization) and event type (commitment, request, question, quotation, cancellation, tentative, joke). A request, a quotation, or a third-party promise must never be promoted to a user commitment without human review.

**Enforcement:**
- Ingestion pipeline outputs structured `actor` (user | entity_name | system) and `event_type` (commitment | request | question | quotation | cancellation | tentative | joke) for every extracted item
- Promotions to `commitment_ledger` require `actor=user AND event_type=commitment AND confidence >= 0.7`
- Controlled transcript test (Nora fixture, `tests/fixtures/controlled_transcript_nora.md`) runs in CI on every PR — see P82 regression test
- Nightly production check: sample 100 recent extractions, verify actor/event_type attribution accuracy ≥95% against human-labeled ground truth

**Metric:** Actor attribution accuracy ≥95% on controlled transcripts. Currently ~40%.

**Forbidden:** Promoting a non-user event to an active user commitment. (See FA33.)

### 83. Canonical Ledger Coherence

**Principle:** There is exactly one canonical source of truth for commitment state: the append-only commitment ledger. Every user-facing surface (commitments list, The Moment, Briefing, Ask, What Changed, Whisper) is a projection of the ledger. Projections must never diverge from the ledger.

**Enforcement:**
- All commitment state mutations go through `ledger.append(event)` — no direct writes to projection tables
- Projections are rebuilt from ledger on demand or via event subscription
- Consistency check (`scripts/check_p83_ledger_coherence.py`): `SELECT count(*) FROM commitments_view` must equal `SELECT count(DISTINCT commitment_id) FROM ledger WHERE state='active'` — enforced in CI and nightly
- HTTP 500 on any read endpoint is a release blocker (see P85)
- If divergence detected: alert, halt projections, rebuild from ledger

**Metric:** Zero divergence between ledger and any projection. Currently: 3 commitments displayed vs 0 ledger entries.

### 84. Negative Knowledge Abstention

**Principle:** When no evidence exists for a query, the system must return calibrated abstention — confidence 0.0, explicit "no evidence" language, zero speculative content. The system must never hallucinate a commitment, relationship, or fact to fill an evidence gap.

**Enforcement:**
- Query pipeline computes `evidence_count` before LLM invocation
- If `evidence_count == 0`: return abstention template, bypass LLM entirely, confidence = 0.0
- If `evidence_count < 2`: return low-confidence answer with explicit uncertainty language
- Abstention test suite (20 negative-knowledge queries: "Elon Musk", "Project Titan", "my promise to the moon", etc.) runs in CI
- Nightly production check: sample 50 negative-knowledge queries, verify 100% abstention rate

**Metric:** 100% abstention rate on negative-knowledge queries. Currently: hallucinates "I promise to buy Twitter again" for Elon Musk.

### 85. Read-Endpoint Reliability

**Principle:** Every authenticated read endpoint must return a valid response or a structured error with actionable detail. HTTP 500 on read paths is a release blocker. No exceptions.

**Enforcement:**
- Every read endpoint has integration test covering: empty state, populated state, malformed auth, revoked token, concurrent load
- CI fails if any read endpoint returns 500 in test suite
- Nightly production probe: every read endpoint hit every 5 minutes, 500-rate must be <0.1%
- 500s trigger PagerDuty-equivalent alert and automatic rollback

**Metric:** <0.1% 500-rate on read endpoints. Currently: `/api/account/export` and `/api/observability/traces` return 500 on every call.

**Forbidden:** Returning HTTP 500 on an authenticated read endpoint. (See FA32.)

### 86. Output Sanitization

**Principle:** No internal guard strings, debug tokens, HTML entities, raw email headers, UUID-labeled credentials, or placeholder markers appear in user-facing responses. All output passes through a sanitization layer before reaching the client.

**Enforcement:**
- Sanitization regex list maintained in `config/sanitization_patterns.yaml`:
  - `\[SEMANTIC INJECTION DETECTED.*?\]` → redact
  - `Token\s*:\s*[a-f0-9-]{36}` → redact
  - `&lt;`, `&gt;`, `&amp;` → decode or strip
  - `From:.*@.*\..*` (raw headers) → redact
  - Kotak/Zerodha client codes (regex patterns) → redact
- Every API response passes through `sanitize_output()` before serialization
- CI test (`scripts/check_p86_output_sanitization.py`): feed 100 known-bad inputs, verify zero leaks in responses
- Nightly production probe: sample 1000 recent responses, grep for leak patterns

**Metric:** Zero leaked guard strings, tokens, or PII in any user-facing response. Currently: `[SEMANTIC INJECTION DETECTED AND REMOVED]` renders in Prepare cards.

**Forbidden:** Leaking internal guard strings in user-facing responses. (See FA31.)

### 87. State Consistency

**Principle:** Any query about system state (counts, cancellations, status, recency) must return results provably consistent with the canonical state store at the moment of query. The system must never contradict itself across endpoints or within a single response.

**Enforcement:**
- All state queries read from the canonical ledger (or a strongly-consistent projection)
- Consistency test (`scripts/check_p87_state_consistency.py`): for every state-bearing endpoint, run same query via Ask and via direct endpoint, assert equivalence
- "What commitments are cancelled?" via Ask must match `GET /api/inbox/synthetic/status` cancelled count
- CI: 20 consistency fixtures covering counts, states, recency, entity-specific state
- Nightly production check: 10 random state queries, verify consistency

**Metric:** 100% state consistency across endpoints. Currently: Ask says 0 cancelled, status endpoint says 13.

**Forbidden:** An Ask response asserting state that contradicts the canonical ledger. (See FA34.)


# PART FIFTEEN: GOVERNANCE COHERENCE RESOLUTIONS (Addendum)

The following resolutions clarify and amend previous principles to ensure strict logical coherence and mechanical enforceability across the governance framework. In cases of conflict between these resolutions and earlier text, these resolutions take precedence.

## Resolution 1: Promotion Threshold (Amends P82 and FA#33)
**Add P88 — The Promotion Threshold Principle**
The attribution classifier accuracy target (P82, 95%) is distinct from the promotion threshold. To satisfy FA#33 (never promote non-user events without review), promotions to the active commitment ledger require `confidence ≥ 0.9 AND actor_attribution_confidence ≥ 0.95`. Extractions falling between 0.70 and 0.95 attribution confidence must be routed to a human review queue, not the active ledger.

## Resolution 2: Auto-Deploy Rollback (Amends P71 and P85)
**Revise P71 — The Infrastructure Automation Principle**
If it runs in production, it auto-deploys from main. No manual deploys. **Addendum:** Auto-deploy must include automatic rollback on SLO breach. If the HTTP 500 rate on read endpoints exceeds 0.1% within 15 minutes of a deploy, the system must automatically rollback to the previous commit, trigger an alert, and block further deploys until the root cause is fixed. This ensures P71 and P85 are simultaneously satisfiable.

## Resolution 3: Enforcement Timing (Amends P70)
**Revise P70 — The Enforcement Principle**
A principle written down after finding a bug does not retroactively **blame** code written before the principle existed. However, it **does** apply to all future code, including modifications to the same file. Principles are forward-looking enforcement mechanisms, not backward-looking blame assignments.

## Resolution 4: Independent Reproduction (Amends FA#27)
**Revise FA#27 — Closing Tickets Without Live Reproduction**
Closing a ticket on a verdict without a posted live reproduction is forbidden. **Addendum:** To satisfy Principle 5 (Independence), the live reproduction must be executed and posted by an **independent session or auditor**, not the same session that authored the fix. The fix-author may run tests locally, but the ticket cannot be closed until an independent verifier confirms the live reproduction.


---

## Part Nineteen: Visual Evidence & Browser Verification Principles (P89-P98)

**P89 — Screenshot Evidence Principle**
For UI claims, require screenshot evidence with metadata (timestamp, URL, distinct MD5 hash). A claim like "the modal opens" must be accompanied by a screenshot showing the modal open. Screenshots must be stored in `/audit-evidence/` with commit hash in filename. CI check: grep commit messages for "screenshot" keyword, verify file exists.

**P90 — Cross-Origin Verification Principle**
When frontend and backend are separate services, verify CORS configuration and same-origin proxy behavior. A fetch that works via curl may fail in the browser due to CORS preflight. For every frontend→backend fetch, verify: (1) direct backend URL works via curl, (2) same-origin proxy works via curl, (3) browser fetch succeeds (DevTools Network tab). If direct URL returns 400 on OPTIONS preflight, frontend MUST use proxy.

**P91 — Error Message Clarity Principle**
All error messages must be user-actionable, not technical stack traces. "Failed to load thread" must include a suggested action (e.g., "Check your network connection" or "Contact support"). Every error response includes: (1) human-readable message, (2) suggested action, (3) error code for support. CI check: grep error messages for stack trace patterns (Traceback, Exception, line N), fail if found.

**P92 — Graceful Degradation Principle**
When a feature depends on external services (Gmail API, OpenRouter, etc.), verify graceful degradation when those services are unavailable. A missing API key must return 503 with a clear message, not crash with 500. For every external service dependency, test: (1) service available → 200, (2) service unavailable → 503 with clear message. CI check: mock external service as unavailable, verify graceful 503.

**P93 — Component Integration Principle**
When a component is wrapped by another component (e.g., ClickableCard wrapping cards), verify the wrapper is applied to ALL instances, not just a subset. "All cards are clickable" requires verifying every card, not just 2 of 25. Count total instances, verify wrapper applied to N of N instances. CI check: grep for wrapper component, count usages, compare to total instances. If N < total, report "N/total wrapped, not all".

**P94 — Network Request Verification Principle**
For browser-based features, verify actual network requests via DevTools Network tab, not just UI appearance. A modal that "opens" may not actually fetch data. For every feature that fetches data, verify: (1) Network tab shows the request, (2) request returns 200, (3) response contains expected data. CI check: use headless browser to capture Network tab, verify requests. Screenshot of Network tab included in evidence.

**P95 — Field Name Contract Principle**
When frontend and backend exchange data, verify field names match on both sides. If backend returns `from_email` and frontend expects `from`, the feature is broken even if both sides work individually. Define data contract in shared schema file (e.g., `email_models.py`). Frontend and backend both import from shared schema. CI check: verify frontend TypeScript interface matches backend Pydantic model. If field names differ, fail build.

**P96 — Proxy vs Direct Verification Principle**
When a proxy exists (e.g., Next.js rewrite), verify requests go through the proxy, not direct to backend. A direct fetch bypasses the proxy and may fail due to CORS. For every frontend fetch, verify URL starts with `/api/` (same-origin), not `https://backend-url/api/` (cross-origin). CI check: grep frontend code for backend URL, fail if found. If direct URL found, require explicit justification.

**P97 — Empty State Honesty Principle**
When an API returns empty results, verify this is correct behavior, not a bug. An empty thread may mean (1) no emails exist, or (2) thread retrieval is broken. For every empty response, verify: (1) test with known data → non-empty, (2) test with no data → empty. CI check: ingest test data, verify non-empty response, delete data, verify empty response. If empty response occurs with known data, flag as bug.

**P98 — Multi-Surface Consistency Principle**
When the same data appears in multiple UI surfaces (Today, Commitments, Whisper), verify all surfaces show the same data. If Today shows 3 commitments and Commitments shows 25, there's a coherence failure. For each demo entity, query all surfaces (Today, Commitments, Whisper, Ask). Assert all surfaces agree on: commitments, state, people, evidence. CI check: compare surface outputs, fail if divergence. Paste cross-surface comparison table in commit message.

