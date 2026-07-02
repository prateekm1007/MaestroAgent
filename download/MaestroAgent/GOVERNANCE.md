# GOVERNANCE ENFORCEMENT PROTOCOL — MaestroAgent
# ═══════════════════════════════════════════════════════════════════════════
#
# This file is the GOVERNANCE GATE. It is read and acknowledged BEFORE
# any code is written, any fix is applied, or any claim is made.
#
# It is not a suggestion. It is not a "best practice." It is the
# mechanical enforcement of the anti-entropy principles, encoded as
# a pre-execution checklist that MUST be completed before work begins.
#
# ═══════════════════════════════════════════════════════════════════════════

## PRE-EXECUTION GATE (Mandatory — Complete Before Writing Any Code)

Before touching any file, answer these 10 questions. Each answer must be
honest. "I don't know" is a valid answer. "I assume so" is NOT.

### Gate 1: Have you read ALL 10 principles in ENTROPY_RECOVERY.md?
- [ ] Yes, I read all 10 in this session, not from memory

### Gate 2: What module are you about to touch?
- Module: ___________
- Does it have tests? [ ] Yes [ ] No
- If no: you MUST add a test before marking anything fixed (P2)

### Gate 3: Will you need to mock anything to test this?
- [ ] No mocks needed
- [ ] Yes, mocking: ___________
- If mocking a security/correctness dependency: use a real fixture instead (P3)

### Gate 4: Is there a risk of silent fallback (except: pass)?
- [ ] No exception handling in the new code
- [ ] Yes — I will log loudly, not silently swallow (P6)

### Gate 5: Are you changing shared/global state to scoped state?
- [ ] No state scoping change
- [ ] Yes — I will write a two-instance isolation test (P7)

### Gate 6: What will you claim in the commit message?
- Before writing the claim, state: "I will only claim what I have executed."
- Any ✓ VERIFIED must have a pasted terminal transcript (P1)

### Gate 7: What is the root cause of the bug you're fixing?
- Not just "the code was wrong" — WHY was it wrong?
- What process gap let it ship? (P10)

### Gate 8: Are you deferring anything?
- If yes: what is the concrete trigger? (P9)
- "Pilot-phase, not blocking" without a trigger is FORBIDDEN.

### Gate 9: Will you re-verify prior claims that affect your work?
- Before claiming "tests pass," re-run them.
- Before claiming "0 inline styles," re-grep.
- Stale claims are P4 violations. (P4)

### Gate 10: Who will verify your work?
- Self-certification is weak evidence (P5)
- The auditor will verify. Your job is to make their job easy by
  being honest about what you did and didn't execute.

## POST-EXECUTION GATE (Mandatory — Complete Before Committing)

Before committing, verify:

### Exit 1: Did you execute every code path you changed?
- [ ] Yes — pasted output below
- [ ] No — wrote "UNVERIFIED — reasoning only" instead of ✓

### Exit 2: Did you write a test for new code in an untested module?
- [ ] Yes — test file: ___________
- [ ] No — documented in commit message why (P2 honesty)

### Exit 3: Did you verify no silent exception swallowing?
- [ ] grep "except.*pass" in changed files = 0 (P6)

### Exit 4: Did you re-verify all claims in your commit message?
- [ ] Every claim has execution evidence in this session (P1, P4)

### Exit 5: Did you document the root cause (process gap)?
- [ ] Yes — root cause: ___________ (P10)

## ENFORCEMENT MECHANISM

This protocol is enforced by the agent itself at the start of every
session. The agent MUST:

1. Read this file
2. Read ENTROPY_RECOVERY.md
3. Complete the Pre-Execution Gate for each task
4. Complete the Post-Execution Gate before each commit
5. If any gate item is skipped, document WHY in the commit message

The auditor's role is to verify the agent followed this protocol. If
the auditor finds a claim that wasn't executed (P1 violation), the
protocol was not followed — and the root cause is in the process, not
just the code.
