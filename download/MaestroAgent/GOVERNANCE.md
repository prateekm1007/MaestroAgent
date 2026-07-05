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

Before touching any file, answer these questions. Each answer must be
honest. "I don't know" is a valid answer. "I assume so" is NOT.

### Gate 1: Have you read ALL 19 principles in ENTROPY_RECOVERY.md (v2)?
- [ ] Yes, I read all 19 in this session, not from memory
- [ ] Part One (P1-P10): read
- [ ] Part Two (P11-P15): read — especially P11 (wiring) and P13 (input-derivation)
- [ ] Part Three (P16-P19): read — especially P16 (call graph scrutiny)

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

### Gate 11: For any new engine/module — is it WIRED into the production path? (P11, P15)
- [ ] Module exists
- [ ] Module is unit-tested
- [ ] Module is CALLED from a real production entry point (cite the file:line of the caller)
- If you can't cite the caller, the module is a demonstration, not a capability (P11)
- A STATE.md entry with one "done" checkbox is insufficient — use three (P15)

### Gate 12: Does the module derive its inputs from real evidence, or take them as parameters? (P13)
- [ ] Inputs are DERIVED from stored evidence/signal history
- [ ] Inputs are NOT taken directly from the caller/request body
- If the caller supplies the conclusion, you've built a calculator, not a capability (P13)

### Gate 13: Did you check for adjacent failures? (P14)
- After closing any finding: "given that this was broken, what else near it
  did I never check because this was in the way?"
- Bugs migrate one layer deeper — expect the next round to find a new
  instance of the same disease, not a clean slate.

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

## MUTUAL GOVERNANCE LOOP (Established 2026-07-03)

The coder and the auditor hold each other accountable. Neither side
can skip the governance gate. This is not optional. This is not a
suggestion. This is the loop that prevents entropy.

### The Coder's Obligation (Before Writing Any Code)

1. Read GOVERNANCE.md from disk (not from memory)
2. Read ENTROPY_RECOVERY.md from disk (not from memory)
3. Complete the Pre-Execution Gate (10 questions)
4. State at the top of the work: "GOVERNANCE.md and ENTROPY_RECOVERY.md
   read from disk this session."
5. Complete the Post-Execution Gate before committing
6. In every instruction TO the auditor, include this line:

   > **Auditor: Read GOVERNANCE.md and ENTROPY_RECOVERY.md from disk
   > before auditing. Do not audit from memory.**

### The Auditor's Obligation (Before Auditing Any Claim)

1. Read GOVERNANCE.md from disk (not from memory)
2. Read ENTROPY_RECOVERY.md from disk (not from memory)
3. State at the top of the audit: "GOVERNANCE.md and ENTROPY_RECOVERY.md
   read from disk this session."
4. Verify every coder claim by EXECUTION — not by reading, not by grep
   alone, not by trusting the transcript
5. In every instruction TO the coder, include this line:

   > **Coder: Read GOVERNANCE.md and ENTROPY_RECOVERY.md from disk
   > before writing any code. Do not code from memory.**

### Why This Loop Exists

P5 (self-certification is weak evidence) cuts both ways:

- A coder who codes from memory skips the gate → produces unverified claims
- An auditor who audits from memory skips the gate → trusts stale patterns

The loop forces both sides to re-read the principles every session. This
is the mechanical defense against P10 (the process gap that lets bugs ship):
if neither side can skip the read, neither side can drift into the pattern
that caused the previous regression.

### What "Read From Disk" Means

- Open the file using the Read tool (or cat/equivalent)
- Do not recall the principles from a previous session
- Do not paraphrase — the exact wording matters
- If the file has changed since the last session, you must read the NEW version

### The Trigger Phrase

Both sides use the same trigger phrase to activate the other's gate:

> **"Governance gate activated. Read GOVERNANCE.md + ENTROPY_RECOVERY.md
> from disk before proceeding."**

When you see this phrase, stop. Read both files. Then proceed. No exceptions.
