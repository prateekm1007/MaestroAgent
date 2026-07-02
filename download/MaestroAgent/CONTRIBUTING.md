# Contributing to Maestro

## Verification Protocol (MANDATORY — read [ENTROPY_RECOVERY.md](./ENTROPY_RECOVERY.md) first)

> **A fix is not "verified" until it has been executed, not read.**
>
> This rule exists because, across multiple audit rounds, fixes were marked
> ✓ VERIFIED in `STATE.md` and docstrings while being completely non-functional
> on first execution. The canonical instance: a "semantic search fix" that
> instantiated an abstract class (`VectorMemory`, an `ABC`), called a method
> that did not exist (`.search()`), and swallowed both errors with
> `except Exception: pass` — every call fell through to SQL `LIKE` while the
> docstring claimed semantic ranking. It shipped "verified" for 18+ rounds
> because no test exercised the path with a query that would distinguish
> semantic ranking from substring matching.

**No fix may be marked ✓ VERIFIED without ALL THREE of the following:**

### 1. A pasted terminal transcript in the commit message (Principle 1)

The actual code path must be run, with output. Not "tests pass" — the
specific function called, in isolation, with the result printed.

**Required format in the commit message:**

```
fix(memory): LongTermMemory semantic search actually invokes vector layer

VERIFICATION (executed, not read):
$ python -c "
import asyncio
from maestro_memory.long_term import LongTermMemory
from maestro_memory.vector import InMemoryVectorMemory
mem = LongTermMemory(db_path=':memory:', vector=InMemoryVectorMemory())
asyncio.run(mem.write(run_id='r1', agent_id='a', scope='shared',
    content='We chose Postgres for streaming replication.'))
results = asyncio.run(mem.search('database scaling', limit=5))
print(f'Results: {len(results)}')
print(f'First: {results[0][\"summary\"]}')"
Results: 1
First: Postgres chosen for replication + index performance

TEST: backend/maestro_memory/tests/test_long_term_search.py::test_semantic_search_finds_non_substring_match — PASS
```

If the transcript is missing, the PR is blocked. No exceptions.

### 2. For fixes touching a module with zero test coverage, add a test that FAILS when the fix is reverted (Principles 2 + 10)

This is the rule that would have caught the `VectorMemory` bug immediately.
If you're fixing `maestro_memory/long_term.py` and `maestro_memory/tests/`
does not exist, your PR must create it with at least one test that would
fail if your fix were reverted.

**How to verify your test actually guards the fix (proof by negation):**
1. Write the fix + the test. Confirm the test PASSES.
2. Temporarily revert the fix. Confirm the test FAILS.
3. Re-apply the fix. Confirm the test PASSES again.
4. Paste all three outputs in the commit message.

A test that passes both with and without the fix is decoration, not verification.

### 3. The function must be called in isolation, outside test mocks, at least once (Principle 3)

Unit tests with `MagicMock`-ed dependencies prove the code *paths* wire
together — they do not prove the code *works*. The mocked-SAML-signature
test (which `MagicMock`-ed `xmlsec`, `python3-saml`, and `lxml`, then
hardcoded `mock_ctx.verify.return_value = True`) is the canonical example:
it passed for rounds while proving nothing about real XML-DSig verification.

Before marking a fix verified, run the actual function with real
dependencies (or real fixtures) at least once. Paste the output.

**Before mocking a dependency, ask:** "if this dependency were subtly broken,
would this test still pass?" If yes, you're not testing your integration —
you're testing that you can call a mock. For anything security- or
correctness-critical (crypto, auth, data isolation), use a real fixture.

---

### Pre-merge checklist (paste this at the top of every PR description)

```
- [ ] I read ENTROPY_RECOVERY.md before starting this work
- [ ] I imported and called the fixed function in isolation, outside test mocks
- [ ] I pasted the terminal transcript in the commit message
- [ ] If the touched module had zero tests, I added a test that FAILS when my fix is reverted (proof by negation outputs pasted)
- [ ] I did NOT write a bare `except Exception: pass` around new/fixed code (Principle 6 — fail closed, or log loudly)
- [ ] If this changes shared/global state to scoped state, I added a two-instance isolation test (Principle 7)
- [ ] I did NOT mark anything ✓ VERIFIED in STATE.md that I have not personally executed in this session
```

If any box is unchecked, the PR cannot merge. Reviewers must reject on
sight, including the founder's own PRs.

---

## The Merge-Gate Rule

> **No engineer — including the founder — can merge a feature unless it satisfies one of:**
>
> 1. A design partner explicitly requested it.
> 2. It removes friction from onboarding.
> 3. It improves a measured business outcome.
> 4. It fixes a reliability or security issue.
>
> If a feature doesn't satisfy one of those four criteria, it waits.

This discipline is what turns a sophisticated platform into a successful enterprise company.

---

## Why This Exists

The architecture is complete (see [CONSTITUTION.md](./CONSTITUTION.md)). The cognitive stack is frozen. The next risk is not underbuilding — it's overbuilding.

Every feature that doesn't satisfy the merge-gate rule:
- Adds complexity without adding customer value
- Increases the surface area that needs maintenance
- Distracts from the only hypothesis that matters:
  > *Organizations using Maestro execute measurably better than organizations that don't.*

---

## How to Contribute

### 1. Check the Merge-Gate

Before writing any code, ask: **which of the four criteria does this satisfy?**

If you can't answer with a specific, measurable reason — don't build it.

### 2. Link to Customer Evidence

In your PR description, include:
- Which design partner requested this (or which onboarding friction it removes, or which metric it improves)
- The expected business outcome
- How you'll measure whether it worked

### 3. Keep the Architecture Frozen

No new cognitive layers. The hierarchy is:
```
Learning Object → Pattern → Playbook → Policy → Governance Control →
Evidence → Case → Precedent → Receipt → Operational Knowledge
```

Do not add: Rule Layer, Wisdom Layer, Experience Layer, Meta Pattern Layer, Reflection Layer, or any other conceptual abstraction. The constitution is frozen until 10 enterprise organizations are running Maestro AND we have evidence that a new kind of knowledge cannot be represented by existing layers.

### 4. Customer-Driven, Not Imagination-Driven

The roadmap is driven by observed customer bottlenecks, not architectural imagination. If you're excited about a feature that no customer has asked for, channel that energy into finding a customer who needs it.

---

## What Gets Merged

✅ **Merged:**
- A design partner reported that approval latency is too high → optimize the approval flow
- Onboarding takes 45 minutes → reduce to 15 minutes by pre-configuring defaults
- Knowledge reuse is stuck at 20% → improve pattern retrieval relevance
- Security vulnerability in the receipt hashing → fix immediately

❌ **Not Merged:**
- "It would be cool if Maestro had voice mode"
- "Let's add a new agent type called 'Architect'"
- "What if we added a Wisdom Layer above Policies?"
- "Let's build a mobile app" (no customer has asked for it)

---

## The One Sentence

> **We are no longer a platform engineering company. We are a customer learning company.**

The architecture is complete. The next 6 months are about producing evidence that organizations using Maestro execute better than organizations that don't.

If we can do that with 3 design partners, we have a business.
If we can't, no amount of architecture will save us.

---

*See [DESIGN_PARTNER_PLAYBOOK.md](./DESIGN_PARTNER_PLAYBOOK.md) for the full customer validation plan.*
