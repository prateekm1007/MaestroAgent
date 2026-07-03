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

## HOW TO USE THIS

Read Part One and Part Two before writing code. Read Part Three before auditing. Read the whole thing before writing instructions for either. Every N rounds, pick one item marked "done" at random — not the one you're worried about, the one you're confident is fine — and re-verify it at the deepest level (principle #15's third checkbox). That's where entropy hides: not in the things anyone is still worried about, but in the things everyone stopped checking because they were marked done two rounds ago.
