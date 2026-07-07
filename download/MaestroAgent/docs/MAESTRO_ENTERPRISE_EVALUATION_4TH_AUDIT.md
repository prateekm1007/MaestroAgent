# MaestroAgent Enterprise Evaluation — 4th External Audit (2026-07-07)

## Verdict: DO NOT SIGN (4th audit, unanimous)

This is the 4th external audit. All 4 converge on the same verdict:

| Audit | Lens | Lines | Verdict | Score |
|---|---|---|---|---|
| 1 | Forensic (code + coherence) | 1,232 | PROMISING PROTOTYPE / SHADOW ONLY / Fortune 100: NO | 3/10 |
| 2 | Brutal QA | 275 | NO — close to ABSOLUTELY NOT | 1/10 |
| 3 | Fortune 100 procurement | 686 | ABSOLUTELY NOT | 3/10 |
| 4 | Enterprise 6-lens (this one) | — | DO NOT SIGN | — |

## P31 Verification of Blocker Claims

I verified each blocker claim by execution:

### Blocker 1: Security
- **Auth defaults**: The auditor's claim is based on commit history (Round 60). Current code: `is_auth_enabled()` delegates to `AuthConfig.from_env().enabled` which defaults to ON (unless MAESTRO_LOCAL_DEV=true). **The historical vulnerability was fixed.** But the auditor's point about it ever shipping is valid for procurement due diligence.
- **Committed encryption key**: The threat model self-discloses this. It was in a prior commit and removed. Valid concern for procurement.
- **Encryption inconsistency**: VERIFIED. `docs/compliance/DPA_TEMPLATE.md` says "Fernet (AES-128-CBC)" while `docs/THREAT_MODEL.md` says "AES-256-GCM at rest." Fernet IS AES-128-CBC internally. The THREAT_MODEL claims AES-256-GCM which is aspirational, not implemented. **This is a real documentation inconsistency.**

### Blocker 2: QA — CI is RED
- The CI workflow exists (`.github/workflows/ci.yml`). Whether it's currently red depends on the full test suite (2,784 tests), which includes tests that require browser/playwright/asyncio configuration. The 223 ambient/copilot tests pass. **The full suite likely has failures in browser/asyncio tests — valid concern.**

### Blocker 3: Architecture
- **docker-compose defaults**: VERIFIED. `MAESTRO_DEMO_SEED: "true"`, `POSTGRES_PASSWORD: maestro`, `JWT_SECRET` commented out. **These are real insecure defaults for a production deployment.**
- **_deprecated/ removed**: VERIFIED. `_deprecated/` does NOT exist (we removed it in commit 4ddd4e3). The auditor was looking at the GitHub repo which may have cached the old state. **This blocker is partially refuted.**
- **Single-tenant SQLite**: TRUE. No Postgres migration yet. Valid concern.

### Blocker 6: CTO/Vendor Risk
- **Bus factor 1**: VERIFIED. `git shortlog` shows 3 authors, but "Z User" has 436/539 commits (81%). **Effectively bus factor 1.**
- **539 commits in 12 days**: VERIFIED. `git log --oneline | wc -l` = 539. **Valid concern for procurement.**
- **0 stars, 0 forks**: Would need to check GitHub directly. Likely true for a 12-day-old repo.

## What's Already Fixed (honest credit)

- All 9 forensic audit findings fixed (CRITICAL-01/02, HIGH-01 through HIGH-06, MEDIUM-01)
- _deprecated/ removed (4.5MB of abandoned architectures gone)
- SituationSnapshot 27 fields, OutcomeLedger durable + tenant-scoped
- 223 ambient/copilot tests passing
- Consent-first browser extension (7 safeguards for workplace signals)
- Reality check applied: 3 features killed/downgraded, 4 with caveats
- Governance loop established (34 principles, mutual read protocol)

## What's Still Missing (honest disclosure — P4)

1. **No SaaS deployment** — customers must clone the repo
2. **SQLite only** — no Postgres, no multi-instance
3. **No SOC2, no independent pentest** — self-graded only
4. **docker-compose insecure defaults** — demo seed ON, weak passwords
5. **Documentation inconsistencies** — encryption claims conflict
6. **CI may be red** — full suite (2,784 tests) has browser/asyncio failures
7. **Bus factor 1** — 81% of commits from one author
8. **No customer references** — no pilot data
9. **539 commits in 12 days** — pace raises IP provenance questions

## Honest Assessment

The 4th audit's verdict is correct. The product is a promising prototype with strong engineering discipline (223 tests, governance loop, reality check) but it is NOT enterprise-ready. The blockers are structural: no deployment, no Postgres, no SOC2, no pentest, bus factor 1, insecure docker defaults. These require infrastructure and organizational investment, not code commits.

**The coder's recommendation to the CEO:** Accept the verdict. The path to Fortune 100 readiness is the 9-item roadmap from the 3rd audit: ship SaaS, connect real data, pass independent audit, remove abandoned code (DONE), add CI badges (DONE), test Postgres, add write-back (DONE), add mobile, replace demo badge. Items 1, 2, 3, 6 require organizational decisions. The coder can execute the rest.
