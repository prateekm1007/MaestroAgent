# ENTROPY RECOVERY — Anti-Entropy Protocol for MaestroAgent

> **Read this at the start of every session, before looking at the task list.**
> The task list tells you what to do. This tells you how not to lie to yourself while doing it.

These principles are grounded in what actually broke across MaestroAgent's audit rounds — not generic advice. Every one of them exists because a specific regression happened in this repo's history.

---

## 1. A claim is not true until it has been executed
**The single failure mode behind every regression in this repo's history.** "VERIFIED" was written next to a fix that raised `TypeError` on the very first call. The fix looked correct on read — abstract-seeming class, plausible method name — and was never actually run.

> **Rule:** Never write ✓ VERIFIED, ✓ FIXED, or ✓ DONE next to anything you have not personally executed and seen output from in this session. Reading code and reasoning about what it *should* do is not verification. If you can't run it (no environment, no access), write "UNVERIFIED — reasoning only" instead of a checkmark. A checkmark you're not sure of is worse than no checkmark.

---

## 2. Untested code is unverified code, permanently, regardless of how it reads
10 of 15 modules in this repo had zero tests. Every serious bug that slipped through review lived in an untested module. Test coverage isn't a quality metric here — it's the mechanism that catches exactly the failure in Principle 1.

> **Rule:** If the module you're touching has no test file, your fix is not done when the code changes — it's done when a test exists that would fail on the old code and pass on the new code. Write that test *before* marking anything fixed. If you skip this "just to move fast," say so explicitly in STATE.md rather than marking it done.

---

## 3. Mocking the thing you're trying to verify verifies nothing
The SAML "valid signature accepted" test mocked out `xmlsec` itself and hardcoded `verify() → True`. It proved the code *calls* a verification function, not that verification *works*. This is a subtler version of Principle 1 — it looks like a real test, has assertions, runs in CI, and is worthless.

> **Rule:** Before mocking a dependency in a test, ask: "if this dependency were subtly broken, would this test still pass?" If yes, you're not testing your integration with it, you're testing that you can call a mock. For anything security- or correctness-critical (crypto, auth, data isolation), use a real fixture — a real signed payload, a real second tenant — not a mock of the verification step itself.

---

## 4. State files are a claim about reality, not a diary of intentions
STATE.md said "H16: TODO" for onboarding OAuth wiring that had already been shipped and tagged "Round 51 H15 fix" in the actual code. The doc lagged the code. This means nobody can trust the doc without re-verifying it against code anyway — which defeats its purpose.

> **Rule:** STATE.md is regenerated or reconciled at the end of every session against actual code state — grep for the thing you claim is fixed, don't recall it from memory. If you're not sure whether something shipped, check, don't guess. A stale state file is actively worse than no state file, because it creates false confidence in the next agent (or human) who reads it.

---

## 5. "Fixed" needs a name attached, and self-certification is weak evidence
Every broken "fix" in this history was marked verified by the same agent/session that wrote it. Nobody has an incentive to find their own blind spots as reliably as someone else does.

> **Rule:** Where possible, the session that writes a fix is not the same session (or at minimum, not the same unbroken context) that marks it verified. On the next session, re-run the previous session's "done" list from scratch before adding new work — treat every prior VERIFIED as a hypothesis to falsify, not a fact to build on.

---

## 6. Prefer "fail closed and broken" over "fail open and silent"
The good pattern in this codebase — SAML rejecting unsigned/unverifiable responses outright — is the right instinct. The bad pattern — `except Exception: pass` silently falling back to old behavior in the memory-search "fix" — is the same instinct inverted into a liability. A loud failure gets fixed. A silent fallback gets marked done and forgotten.

> **Rule:** Never write a bare `except Exception: pass` (or equivalent silent swallow) around new/fixed code paths. If a fallback is genuinely intended, log it loudly and make it visible in whatever monitoring exists — a fallback nobody can see is a bug wearing a disguise.

---

## 7. Singleton-to-scoped changes need an isolation test, not just a signature change
The `OEMStateRegistry` fix (singleton → per-org dict) was done correctly *and* was one of the only fixes in this history to include a test proving isolation. That's not a coincidence — it's the template. Changing a data structure's shape doesn't prove the new shape is actually respected everywhere that touches it.

> **Rule:** Any fix that changes shared/global state into scoped state must ship with a test that creates two instances of the scope (two orgs, two users, two sessions) and proves they cannot see each other's data — not just a test that the new function signature accepts a scope parameter.

---

## 8. Round numbers are not progress — diffs against a fresh read are
This repo is on "Round 65." Round numbers accumulate regardless of whether real bugs are closing or just being relabeled. The only thing that matters is: did an independent, from-scratch read of the current code find fewer real problems than the last independent read?

> **Rule:** Don't cite round count or commit count as evidence of maturity in STATE.md. Cite: modules with test coverage (a number that should only go up), open CRITICAL/HIGH count (a number that should only go down), and specific reproduction steps for anything still open. If a round doesn't move one of those numbers, say so honestly instead of writing a new paragraph that sounds like progress.

---

## 9. Every "remaining" item needs a concrete trigger, not a vibe
"Pilot-phase, not blocking" appears repeatedly in this repo's STATE.md without a defined threshold for when it *becomes* blocking. Vague deferrals accumulate into permanent gaps — this is how load testing, WCAG compliance, and DB TLS all stayed "not blocking" across dozens of rounds.

> **Rule:** Every deferred item gets a specific trigger condition written next to it — a customer count, a compliance deadline, a request from a named stakeholder — not just a priority label. "Not blocking (until: second paying customer signs / SOC2 audit scheduled / whichever comes first)" is a real deferral. "Pilot-phase, not blocking" with no trigger is a way of never doing it.

---

## 10. When you find a bug the previous session missed, write down *why* it was missed, not just that it's fixed
The value of a forensic audit isn't the bug — it's the pattern. If C1 (fake semantic search fix) is fixed without asking "how did this get marked VERIFIED in the first place," the next session will produce a differently-shaped version of the same mistake.

> **Rule:** Every bugfix entry in STATE.md includes a one-line root cause about the *process* gap, not just the code gap — e.g. "root cause: zero test coverage in this module let a TypeError-on-call ship as verified" — so the fix for the fix is also visible, not just the fix for the bug.

---

## How to use this
Re-read this file at the start of every session, before writing a single ✓. Re-audit against it every N rounds by picking 2-3 "VERIFIED" items at random and actually re-running them — not the ones you're worried about, the ones you're confident are fine. That's where entropy hides.
