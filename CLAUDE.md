# Project Instructions — MaestroAgent

## ⛔ MANDATORY: Read Governance Files Before ANY Work

Before executing ANY task on this project, you MUST read these files FROM DISK
(not from memory) at the start of every session:

1. **`/download/MaestroAgent/ENTROPY_RECOVERY.md`** — all 57 anti-entropy principles (P1-P57)
   - Part One (P1-P10): The original coder principles
   - Part Two (P11-P15): Deeper coder principles
   - Part Three (P16-P19): Call-graph scrutiny + scope honesty
   - Part Four (P20-P26): Wiring-vs-existence failures
   - Part Five (P27-P34): Auditor's own failures
   - Part Six (P35-P40): Journey-correctness principles
   - Part Seven (P41-P49): Integrity principles (model attribution, built-but-not-wired, CI)
   - Part Eight (P50-P53): Ingest-journey + resilience principles
   - Part Nine (P54-P57): Master principle + prose principles

2. **`/download/MaestroAgent/governance/FORBIDDEN_ACTIONS.md`** — all 20 forbidden actions (FA1-FA20)

3. **`/download/MaestroAgent/GOVERNANCE_LOOP.md`** — the mutual read protocol

4. **`/download/MaestroAgent/STATE.md`** — the current state log (top of file)

## The Master Principle (P54)

**Fix the data the user sees, not just the path.** A fix applied to the code
path but not to the corpus the user actually reads is NOT A FIX. Every fix
must reach the data the user sees — the existing corpus, the live API
response, the deployed frontend.

## The Short Version (fit on a wall)

*Fix the data the user sees. Report the served truth, not the requested wish.
One source of truth, derived at read time. Classify by structure with the
rules holding a veto, and re-classify the corpus when the classifier changes.
Never fail silently, never fake readiness, never relabel. A fix isn't done
until it's wired live, green in CI on the push, and proven on the journey —
not the component, not the probe, not the local run.*

## Why This Exists

Every regression in this repo's history happened because someone:
- Claimed "verified" without executing the code (P1)
- Wrote code without tests (P2)
- Mocked the thing they were verifying (P3)
- Let STATE.md drift from reality (P4)
- Self-certified without independent verification (P5)
- Silently swallowed exceptions (P6)
- Changed state shape without isolation tests (P7)
- Cited round numbers instead of real metrics (P8)
- Deferred without concrete triggers (P9)
- Fixed bugs without documenting why they were missed (P10)
- Fixed the path but not the corpus (P54, the master principle)
- Relabeled a fallback as the requested instrument (P46)
- Claimed "done" on a function the live path doesn't call (P43)
- Reported a degradation strategy as a latency win (P44)
- Reported "done" on local-green without CI-green (P45)
- Let a red CI with known failures persist (P48)

## Enforcement

- Every commit message MUST include execution evidence (terminal transcripts)
- Every fix to an untested module MUST include a new test
- Every claim of "✓ VERIFIED" MUST be backed by execution output in this session
- If you can't execute it, write "UNVERIFIED — reasoning only"
- Every "Kimi K3 did X" claim MUST carry a generation ID cross-checkable on OpenRouter (P46)
- Every "done" claim MUST include a CI run URL (P45)
- Every new function MUST ship with a journey assertion proving the live path calls it (P43)
- The auditor will verify. Your job is to make their job easy by being honest.

## Key File Locations

- Anti-entropy principles (P1-P57): `download/MaestroAgent/ENTROPY_RECOVERY.md`
- Forbidden actions (FA1-FA20): `download/MaestroAgent/governance/FORBIDDEN_ACTIONS.md`
- Governance loop protocol: `download/MaestroAgent/GOVERNANCE_LOOP.md`
- State log: `download/MaestroAgent/STATE.md`
- CTO↔Kimi K3 loop script (P46-unfakeable): `download/MaestroAgent/ops/cto_loop.py`
- Backend: `download/MaestroAgent/backend/`
- Personal shell: `download/MaestroAgent/maestro-personal/`
- Frontend: `download/MaestroAgent/maestro-personal/web/`
- CI workflows: `.github/workflows/` (repo root, NOT nested)
