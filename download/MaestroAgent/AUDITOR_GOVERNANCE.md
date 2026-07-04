# AUDITOR GOVERNANCE — Enforcement Protocol for Auditors

> **Read this before every audit session. Do not audit from memory.**
>
> This file is the auditor's equivalent of GOVERNANCE.md. Just as the coder
> must read GOVERNANCE.md + ENTROPY_RECOVERY.md before coding, the auditor
> must read this file before auditing. The mutual governance loop requires
> both sides' gates to be on disk in the repo.

---

## PRE-REVIEW GATE (Mandatory — Complete Before Auditing Any Claim)

Before reviewing any coder claim, answer these questions honestly.

### Gate 1: Have you read ALL 19 principles in ENTROPY_RECOVERY.md (v2)?
- [ ] Yes, I read all 19 in this session, not from memory
- [ ] Part One (P1-P10): read
- [ ] Part Two (P11-P15): read — especially P11 (wiring) and P15 (three states)
- [ ] Part Three (P16-P19): read — these are the AUDITOR'S OWN principles

### Gate 2: Are you auditing from a fresh clone?
- [ ] Yes — I cloned `--depth 1` from `origin/main` this session
- [ ] No — I am using a stale local copy (FORBIDDEN per P4)

### Gate 3: Are you treating prior "PASSED" verdicts as hypotheses to falsify?
- [ ] Yes — every prior "PASSED" is a claim I will independently verify
- [ ] No — I am trusting prior verdicts (FORBIDDEN per P5)

### Gate 4: Have you identified the product's 1-2 flagship claims?
- [ ] Yes — the capabilities the product's pitch depends on most
- [ ] These claims get call graph scrutiny, not just test scrutiny (P16)

### Gate 5: For each flagship claim, will you trace the call graph from the
### real user-facing entry point to the module?
- [ ] Yes — `grep -rn "function_name" path/to/production/entry/point`
- [ ] Not just "does the test pass" but "does the production code call it" (P19)

### Gate 6: Are you distrusting code that cites you by name?
- [ ] Yes — modules citing "auditor's finding X" get EXTRA scrutiny, not less (P17)
- [ ] A citation is a flag to re-verify at the integration level, not a credential

### Gate 7: Will you state what you did NOT test?
- [ ] Yes — untested phases are marked UNTESTED with a reason, not filled with
      plausible results (P18)
- [ ] An audit that fabricates results has committed the exact sin it exists to catch

### Gate 8: For each capability, will you run BOTH unit tests AND integration tests?
- [ ] Yes — unit tests verify the function; integration tests verify the wiring (P19)
- [ ] I will state explicitly which of the two I ran, every time

### Gate 9: Will you verify by execution, not by reading?
- [ ] Yes — I will run the code, not just read it
- [ ] "The transcript says it passed" is not verification (P1)

### Gate 10: Will you check for adjacent failures?
- [ ] Yes — after closing any finding, I will ask "what else near it did I
      never check because this was in the way?" (P14)
- [ ] Bugs migrate one layer deeper — expect the next instance

### Gate 11: For flagship claims, will you independently trace the call graph?
- [ ] Yes — for the 1-2 capabilities the product's pitch depends on most
- [ ] `grep -rn "function_name" production/entry/point` — not just the test file
- [ ] This check would have caught CRITICAL-01 (decide_delivery unwired) (P16)

### Gate 12: Will you verify three states separately (exists, unit-tested, wired)?
- [ ] Yes — a module can be 100% correct and 0% real if nobody calls it (P15)
- [ ] I will check all three: does it exist? do its tests pass? is it called from production?

### Gate 13: Will you be honest about scope?
- [ ] Yes — I will say what I didn't test, precisely (P18)
- [ ] I will not fill gaps with plausible-sounding results

### Gate 14: Will you check for the "demonstration harness" pattern?
- [ ] Yes — an endpoint that takes the conclusion as input is a demo, not a
      capability (P13)
- [ ] I will check whether inputs are DERIVED from evidence, not caller-supplied

### Gate 15 (NEW): For "wired" claims, will you verify callers pass the parameter?
- [ ] Yes — a function signature with a new parameter proves nothing (P20, C-002)
- [ ] I will run `grep -rn "<func>(" --include="*.py" | grep -v test_ | grep -v "def <func>"` and count callers that pass the new parameter
- [ ] If M < N, the fix is (M/N)% done — I will mark it INCOMPLETE, not FIXED

### Gate 16 (NEW): For "persisted" claims, will you execute the restart cycle?
- [ ] Yes — a save function that exists but doesn't fire from the right trigger is theater (P21, C6)
- [ ] I will: start server → create state via path X → SIGKILL → restart → verify state survived
- [ ] I will paste before/after counts. "The save function exists" is not evidence.

### Gate 17 (NEW): For "dedup" claims, will you send duplicate input?
- [ ] Yes — reading the dedup logic proves nothing; executing it with duplicates does (P22, C-002)
- [ ] I will send 4 identical signals through the REAL production entry point (not a unit test)
- [ ] I will verify: 1 LO (not 4), evidence_count ≤ 2 (not 4), content_hashes set non-empty

### Gate 18 (NEW): For "coherence" claims, will you query all surfaces horizontally?
- [ ] Yes — vertical verification (each surface in isolation) misses cross-surface failures (P24, C3)
- [ ] I will query each demo entity through ALL surfaces (Situation/Ask/Whisper/Preparation/Briefing/Timeline)
- [ ] I will assert they agree on commitments/state/people/evidence — paste the comparison table

### Gate 19 (NEW): For confidence values, will you ask "what is the denominator?"
- [ ] Yes — a confidence value without a denominator is decorative precision (P25, C4)
- [ ] For every confidence value displayed to the user: what is the sample size? calibrated?
- [ ] If denominator < 10, the display must say "insufficient calibration history" — never bare 4-decimal precision

### Gate 20 (NEW): For commit messages claiming a fix, will you execute the reproduction?
- [ ] Yes — commit message claims are not evidence (P23, C-002)
- [ ] I will read the claim → find/write the reproduction script → execute → compare to claimed output
- [ ] I will not trust "✓ VERIFIED" without pasted output from THIS session

---

## POST-REVIEW CHECKS (Mandatory — Complete Before Delivering Verdict)

Before delivering your audit verdict, verify:

### Check 1: Did you execute every test you claim passes?
- [ ] Yes — pasted output below
- [ ] No — wrote "NOT TESTED" instead of claiming it passes

### Check 2: Did you run the FULL regression suite, not a subset?
- [ ] Yes — all critical test files, not just the ones I expect to pass
- [ ] No — documented which files I skipped and why

### Check 3: Did you trace call graphs for flagship claims?
- [ ] Yes — grep verified the module is called from the production path
- [ ] No — documented why (e.g., module is not a flagship claim)

### Check 4: Did you state what you did NOT test?
- [ ] Yes — untested phases marked UNTESTED with reasons
- [ ] No — every phase has a result (FORBIDDEN if any result was not executed)

### Check 5: Did you check for the "teaching to the test" pattern?
- [ ] Yes — modules citing audit findings by name got extra scrutiny
- [ ] No — documented why

### Check 6: Did you verify claims by execution, not by reading the coder's transcript?
- [ ] Yes — I ran the code myself
- [ ] No — I trusted the transcript (FORBIDDEN per P1)

### Check 7: Did you document root causes for any regressions found?
- [ ] Yes — process gap documented, not just code gap (P10)
- [ ] No regression found

---

## THE MUTUAL GOVERNANCE LOOP

The coder and the auditor hold each other accountable. Neither side
can skip the governance gate. This is not optional. This is not a
suggestion. This is the loop that prevents entropy.

### The Auditor's Obligation (Before Auditing Any Claim)
1. Read GOVERNANCE.md from disk (not from memory)
2. Read ENTROPY_RECOVERY.md from disk (not from memory) — now includes Part Four (P20-P26)
3. Read AUDITOR_GOVERNANCE.md from disk (not from memory) — now includes Gates 15-20
4. Complete the Pre-Review Gate (20 questions)
5. Verify every coder claim by EXECUTION — not by reading, not by grep
   alone, not by trusting the transcript
6. For every fix commit, cite which P-number principle the fix satisfies
   and which Gate the auditor used to verify it (the mutual enforcement)
7. In every instruction TO the coder, include this line:
   > **Coder: Read GOVERNANCE.md and ENTROPY_RECOVERY.md from disk
   > before writing any code. Do not code from memory.**

### The Coder's Obligation (Before Writing Any Code)
1. Read GOVERNANCE.md from disk (not from memory)
2. Read ENTROPY_RECOVERY.md from disk (not from memory) — Part Four (P20-P26) is NEW
3. Complete the Pre-Execution Gate (13 questions)
4. Complete the Post-Execution Gate before each commit
5. For every fix commit, cite which P-number principle the fix satisfies
   (e.g., "P20: 27/27 callers pass content_hash") — the citation IS the enforcement
6. In every instruction TO the auditor, include this line:
   > **Auditor: Read GOVERNANCE.md and ENTROPY_RECOVERY.md from disk
   > before auditing. Do not audit from memory.**

### The Alignment Table (NEW — the mutual enforcement map)

The auditor's gates and the coder's principles **mirror** each other. The auditor checks what the coder should have done. The coder's principles make the auditor's checks pass. Every fix commit should cite BOTH the P-number (what the coder did) AND the Gate (what the auditor will verify).

| Coder Principle | Auditor Gate | Failure it prevents |
|-----------------|--------------|---------------------|
| P20 Call-site parameter rule | Gate 15 Verify callers pass | C-002 theater (0/27 callers) |
| P21 All-paths trigger rule | Gate 16 Execute restart cycle | C6 persistence theater |
| P22 Regression = production path | Gate 17 Send duplicate input | C-002 unit green, bug present |
| P23 Commit cites executed output | Gate 20 Execute reproduction | C-002 false commit message |
| P24 Cross-surface coherence | Gate 18 Query all surfaces | C3 coherence failure |
| P25 Confidence display gate | Gate 19 Ask "denominator?" | C4 decorative precision |
| P26 Re-application (meta) | All Gates (re-read from disk) | Stale-clone auditing |

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
