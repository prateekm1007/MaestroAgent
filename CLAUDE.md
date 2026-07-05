# Project Instructions — MaestroAgent

## ⛔ MANDATORY: Read Governance Files Before ANY Work

Before executing ANY task on this project, you MUST:

1. **Read `/download/MaestroAgent/GOVERNANCE.md`** — the enforcement protocol with pre/post-execution gates
2. **Read `/download/MaestroAgent/ENTROPY_RECOVERY.md`** — all 10 anti-entropy principles
3. **Complete the Pre-Execution Gate** in GOVERNANCE.md for the specific task
4. **After work, complete the Post-Execution Gate** before committing

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

## Enforcement

- Every commit message MUST include execution evidence (terminal transcripts)
- Every fix to an untested module MUST include a new test
- Every claim of "✓ VERIFIED" MUST be backed by execution output in this session
- If you can't execute it, write "UNVERIFIED — reasoning only"
- The auditor will verify. Your job is to make their job easy by being honest.

## Key File Locations

- Governance protocol: `download/MaestroAgent/GOVERNANCE.md`
- Anti-entropy principles: `download/MaestroAgent/ENTROPY_RECOVERY.md`
- State log: `download/MaestroAgent/STATE.md`
- Contributing guide: `download/MaestroAgent/CONTRIBUTING.md`
- Backend: `download/MaestroAgent/backend/`
- Frontend: `download/MaestroAgent/static/`
- CI workflows: `.github/workflows/` (repo root, NOT nested)
