# ENTROPY RECOVERY FILE

## SESSION COMPLETE — ALL FIXES SHIPPED

### Commits pushed
1. a960419 — Remove last error suppression filter in test_cognitive_surfaces.py
2. 0008841 — STATE.md updated with Round 65 fixes (pushed as 2a33f7b after rebase)

### What was verified
The coder's commit 2d5567c already contained all 4 Round 65 fixes:
- C3: Import pipeline org-scoping (_org_aware_ingest → OEMStateRegistry.get(org_id))
- C2: Unified provider whitelist (SUPPORTED_IMPORT_PROVIDERS used at all check sites)
- C1: Docstring fixed ("Defaults to True only when MAESTRO_LOCAL_DEV=true")
- H1: Onboarding localStorage (save/load/clear functions present)

I additionally fixed:
- Error suppression in test_cognitive_surfaces.py:86 (the last remaining filter)

### The 5 CTO checks — ALL PASS
1. Auth gate: ON with zero env vars ✓
2. Demo seed: OFF in non-local ✓
3. Error suppression: 0 patterns ✓
4. Import pipeline: org-aware, not singleton ✓
5. Provider whitelist: unified, no drift ✓

### PAT status
PAT removed from git remote. No PAT in any file. PAT should be revoked by user.

### What remains (pilot-phase, not blocking)
- DB TLS, container security context, CSP nonce-based (infra hardening)
- SOC2/DPA/CAIQ (procurement)
- Load test against Postgres (pilot exit criterion)
- WCAG 2.1 Level A compliance (pilot-phase)
- 188 onclick handlers → addEventListener migration (CSP compliance)


# PART FIFTEEN: GOVERNANCE COHERENCE RESOLUTIONS (Addendum)

The following resolutions clarify and amend previous principles to ensure strict logical coherence and mechanical enforceability across the governance framework. In cases of conflict between these resolutions and earlier text, these resolutions take precedence.

## Resolution 1: Promotion Threshold (Amends P82 and FA#33)
**Add P88 — The Promotion Threshold Principle**
The attribution classifier accuracy target (P82, 95%) is distinct from the promotion threshold. To satisfy FA#33 (never promote non-user events without review), promotions to the active commitment ledger require `confidence ≥ 0.9 AND actor_attribution_confidence ≥ 0.95`. Extractions falling between 0.70 and 0.95 attribution confidence must be routed to a human review queue, not the active ledger.

## Resolution 2: Auto-Deploy Rollback (Amends P71 and P85)
**Revise P71 — The Infrastructure Automation Principle**
If it runs in production, it auto-deploys from main. No manual deploys. **Addendum:** Auto-deploy must include automatic rollback on SLO breach. If the HTTP 500 rate on read endpoints exceeds 0.1% within 15 minutes of a deploy, the system must automatically rollback to the previous commit, trigger an alert, and block further deploys until the root cause is fixed. This ensures P71 and P85 are simultaneously satisfiable.

## Resolution 3: Enforcement Timing (Amends P70)
**Revise P70 — The Enforcement Principle**
A principle written down after finding a bug does not retroactively **blame** code written before the principle existed. However, it **does** apply to all future code, including modifications to the same file. Principles are forward-looking enforcement mechanisms, not backward-looking blame assignments.

## Resolution 4: Independent Reproduction (Amends FA#27)
**Revise FA#27 — Closing Tickets Without Live Reproduction**
Closing a ticket on a verdict without a posted live reproduction is forbidden. **Addendum:** To satisfy Principle 5 (Independence), the live reproduction must be executed and posted by an **independent session or auditor**, not the same session that authored the fix. The fix-author may run tests locally, but the ticket cannot be closed until an independent verifier confirms the live reproduction.
