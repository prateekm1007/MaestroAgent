# GOVERNANCE LOOP — Mutual Read Protocol

> **THE LOOP CANNOT BE BROKEN.**
> **Both sides read this file from disk at the start of every session.**
> **Both sides read the files the OTHER side is told to read.**
> **Both sides paste a read receipt (timestamp + key line) in their first message.**
> **The Coder's first message MUST remind the Auditor to read their governance modules.**
> **The Auditor's first message MUST remind the Coder to read their governance modules.**
> **The CEO rejects any message without a read receipt. No exceptions. No excuses.**

This is the loop that worked. It worked because both sides read from disk (not memory), cited what they applied, and checked the other side's work. This file makes that loop a fixture — not a suggestion.

---

## The Problem This Solves

Principles (P1-P26) were prose. Gates (1-20) were checklists. Both were violated repeatedly because neither side re-read them before each session. P26 says: "Principles don't enforce themselves. Re-application does." This fixture IS the re-application — it forces both sides to read the load-bearing files before publishing anything.

---

## What the Coder Must Read (at the start of every session)

### 0. `STATE.md` (handoff section, top of file)
**Why:** STATE.md is the canonical handoff log. The 2026-07-20 entry records the
coder transition, the current HEAD, the open-issue list (mirrored from
FORENSIC_AUDIT_AND_HANDOFF.md), and the new coder's read receipt. Skipping this
read means re-deriving who's holding which tokens and what the current P0 is.

**Read receipt:** Paste the timestamp + the HEAD SHA from STATE.md + the P0
issue currently at the top of the open-issues table.

### 0b. `FORENSIC_AUDIT_AND_HANDOFF.md`
**Why:** The 354-line forensic audit + handoff document (committed at `8ff6b92`)
is the load-bearing artifact for the new coder. It contains the verified-works
list, the verified-broken list (with severity + fix), the architectural
decisions, and the shell-verification tips earned from 1,053 commits of history.
The audit doc itself instructs: "Read GOVERNANCE.md, ENTROPY_RECOVERY.md,
GOVERNANCE_LOOP.md, and AUDITOR_GOVERNANCE.md from disk before writing any code."

**Read receipt:** Paste the timestamp + confirm you read the "What Works" and
"What's Broken" tables + the 8 architectural decisions + the shell-verification
tips.

### 1. `ENTROPY_RECOVERY.md` Part Four (P20-P26) + Part Five (P27-P34)
**Why:** Part Four contains the principles the Coder has violated most. P20 (call-site parameter rule), P21 (all-paths trigger), P22 (regression = production path), P23 (commit cites output), P24 (cross-surface coherence), P25 (confidence display gate), P26 (re-application meta-principle). Part Five contains the Auditor's own failures — P27 (read assertions), P28 (test 3+ inputs), P29 (re-run canonical scenario), P30 (verify comprehensiveness by counting), P31 (run verify scripts yourself), P32 (check all derived state), P33 (search for refutation), P34 (re-derive method from failures).

**Read receipt:** Paste the timestamp + one key sentence from P20 and one from P26 (Part Four) + one from P27 and one from P34 (Part Five).

### 2. `AUDITOR_GOVERNANCE.md` Gates 15-20
**Why:** These are the gates the auditor will verify against. If the Coder reads them before committing, the Coder knows exactly what the auditor will check — and can self-check first.

**Read receipt:** Paste the timestamp + one key sentence from Gate 15 and one from Gate 17.

### 3. `audit_scripts/audit_gates.sh`
**Why:** This is the script the auditor MUST run before publishing. Reading it reminds the Coder what the auditor will execute — and that the Coder should run it too before claiming done.

**Read receipt:** Paste the timestamp + confirm you understand it enforces Gate 11 (fetch first) + full suite + all verify scripts.

---

## What the Auditor Must Read (at the start of every session)

### 1. `audit_scripts/audit_gates.sh`
**Why:** This is YOUR enforcement mechanism. You proposed it. You must run it before publishing any audit. If you don't run it, your audit is unverifiable.

**Read receipt:** Paste the timestamp + confirm you will run it and paste output inline.

### 2. `ENTROPY_RECOVERY.md` Part Four (P20-P26) + Part Five (P27-P34)
**Why:** Part Four contains the principles the Coder should be following. If you don't know them, you can't verify the Coder applied them. P22 (unit ≠ integration) and P24 (cross-surface coherence) are the ones that catch theater. Part Five contains YOUR OWN failures — P27 (read assertions, not test names), P28 (test 3+ inputs), P29 (re-run full SSO scenario after shared component changes), P30 (count and check each), P31 (run verify scripts yourself), P32 (check all derived state), P33 (search for refutation of negative claims), P34 (re-derive your method from failures, not memory). These are the principles YOU violated. Read them or repeat the failures.

**Read receipt:** Paste the timestamp + one key sentence from P22 and P24 (Part Four) + one from P27 and P34 (Part Five).

### 3. `AUDITOR_GOVERNANCE.md` Gates 15-20
**Why:** These are YOUR gates. You proposed them. If you don't re-read them, you'll skip them — as you did 3 times.

**Read receipt:** Paste the timestamp + one key sentence from Gate 18 and one from Gate 20.

### 4. `test_cross_surface_coherence.py`
**Why:** This is the authority test. Not the 11 verify scripts. This test queries all surfaces horizontally and asserts agreement. If you don't read it, you can't verify the Coder's coherence claims.

**Read receipt:** Paste the timestamp + confirm the test covers Briefing/Ask/Whisper/Preparation/Situation/Timeline.

---

## The Mutual Read-Back Protocol

**Step 1 — Coder's first message of the session:**

The Coder MUST:
1. Read all governance modules from disk (not memory)
2. Paste the read receipt below
3. Remind the Auditor to read THEIR governance modules

```
GOVERNANCE LOOP READ RECEIPT (Coder):
- ENTROPY_RECOVERY.md Part Four (P20-P26) + Part Five (P27-P34) read at <timestamp>
  P20 key line: "<paste one sentence>"
  P26 key line: "<paste one sentence>"
  P27 key line: "<paste one sentence>"
  P34 key line: "<paste one sentence>"
- AUDITOR_GOVERNANCE.md Gates 15-20 read at <timestamp>
  Gate 15 key line: "<paste one sentence>"
  Gate 17 key line: "<paste one sentence>"
- audit_scripts/audit_gates.sh read at <timestamp>
  Confirmed: enforces Gate 11 + full suite + all verify scripts

> Auditor: Read GOVERNANCE_LOOP.md, AUDITOR_GOVERNANCE.md, and
> ENTROPY_RECOVERY.md Part Four + Part Five from disk before auditing.
> Do not audit from memory. The loop cannot be broken.
```

**Step 2 — Auditor's first message of the session:**

The Auditor MUST:
1. Read all governance modules from disk (not memory)
2. Paste the read receipt below
3. Remind the Coder to read THEIR governance modules

```
GOVERNANCE LOOP READ RECEIPT (Auditor):
- audit_scripts/audit_gates.sh read at <timestamp>
  Confirmed: I will run it and paste output inline before publishing.
- ENTROPY_RECOVERY.md Part Four (P20-P26) + Part Five (P27-P34) read at <timestamp>
  P22 key line: "<paste one sentence>"
  P24 key line: "<paste one sentence>"
  P27 key line: "<paste one sentence>"
  P34 key line: "<paste one sentence>"
- AUDITOR_GOVERNANCE.md Gates 15-20 read at <timestamp>
  Gate 18 key line: "<paste one sentence>"
  Gate 20 key line: "<paste one sentence>"
- test_cross_surface_coherence.py read at <timestamp>
  Confirmed: covers Briefing/Ask/Whisper/Preparation/Situation/Timeline

> Coder: Read GOVERNANCE_LOOP.md, ENTROPY_RECOVERY.md Part Four + Part Five,
> and AUDITOR_GOVERNANCE.md Gates 15-20 from disk before writing any code.
> Do not code from memory. The loop cannot be broken.
```

**Step 3 — Both sides read the OTHER side's receipt:**
- The Coder reads the Auditor's receipt (did the auditor actually read the files?)
- The Auditor reads the Coder's receipt (did the coder actually read the files?)
- If either receipt is missing or incomplete, the other side calls it out BEFORE any work begins

---

## The CEO's Enforcement (the load-bearing piece)

1. **Reject any Coder claim that doesn't include a read receipt.** If the receipt is missing, the Coder skipped the governance loop. No exceptions.
2. **Reject any Auditor report that doesn't include `audit_gates.sh` output pasted inline.** If the output is missing, the auditor skipped their own gate. No exceptions.
3. **Every 3rd audit, pick 2 random `verify_*.sh` scripts and re-run them.** Don't tell either side which ones until after the audit is published.

---

## Why This Works (and prior attempts didn't)

| Prior attempt | Why it failed |
|---------------|---------------|
| Principles (P1-P26) | Prose. Not enforced. Violated repeatedly. |
| Gates (1-20) | Checklist. Not enforced. Skipped repeatedly. |
| Pre-commit hook | Mechanical, but only enforces P20 + P6 + P23. |
| Verify scripts | Mechanical, but only as good as the auditor running them. |

**This fixture works because:**
1. It requires a **read receipt** — a timestamp + key line that proves the file was read THIS session, not recalled from memory.
2. It's **mutual** — both sides read the OTHER side's files. The Coder reads the auditor's gates. The auditor reads the Coder's principles.
3. The **CEO enforces** — rejects any message without a receipt. This is the one part that requires a human, and the human is the CEO.
4. The **read-back** catches stale-clone auditing (Gate 11), code-path-tracing (Gate 17), and unit-vs-integration confusion (P22) — the 3 blindspots that recurred across this engagement.

---

## The Files (canonical paths)

```
ENTROPY_RECOVERY.md                          — Coder's principles (P1-P26, Part Four is P20-P26)
AUDITOR_GOVERNANCE.md                        — Auditor's gates (Gates 1-20, 15-20 are new)
audit_scripts/audit_gates.sh                 — Auditor's enforcement script
audit_scripts/verify_*.sh                    — 11 canonical verification scripts
backend/maestro_oem/tests/test_cross_surface_coherence.py — The authority test (P24)
.githooks/pre-commit                         — Coder's enforcement (P20 + P6 + P23)
```
