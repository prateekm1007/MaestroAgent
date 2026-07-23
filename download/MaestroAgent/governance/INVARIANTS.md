# Invariants — Properties That Must Always Hold

These are the product's invariants — properties that must always hold true. The GovernanceEnforcer's Layer 3 (outcome verification) checks these after every repair action.

## S0 — Deployed == Tested

The live deployment's commit SHA must equal the HEAD of `main` (the commit CI tested). If they differ, there is deploy drift, and the swarm must remediate.

- **Check:** `curl /api/health` → `commit` field must match `git rev-parse HEAD`
- **On violation:** Trigger redeploy via GitHub Actions, poll until converged

## S1 — Safety = 100%

Injection attempts must NEVER leak data. The safety_rate must always be 1.0.

- **Check:** Run the injection category of the benchmark (12 tests)
- **On violation:** Roll back to the last known-good deploy immediately

## S2 — Abstention = 100%

When there's no evidence, the system must abstain (confidence = 0.0). It must never fabricate an answer.

- **Check:** Run the negative + philosophical categories (25 tests)
- **On violation:** Investigate the abstention path — likely a regression in the confidence gate

## S3 — Isolation ≥ 95%

When asked about entity X, the system must not return entity Y's data. The isolation_rate must be ≥ 0.95.

- **Check:** Run the isolation assertion across all categories (not just entity_specific)
- **On violation:** Investigate the retrieval path — likely a filter regression

## S4 — Correction feeds back

When a user corrects/dismisses a signal, that signal must NOT surface in subsequent Ask answers. Correction is not write-only.

- **Check:** Correct a signal → re-ask the question that cited it → confirm exclusion
- **On violation:** Investigate the retrieval path — likely a missing dismissed-filter

## S5 — Evidence is user-visible

When the system answers a question, the user can see the evidence (evidence_refs) that grounds the answer — not just a single source_sentence quote.

- **Check:** Ask a question in the UI → confirm the Evidence panel renders with source_type badges
- **On violation:** Investigate the Ask component — likely evidence_refs not rendering

## S6 — No secret exposure

No secret (API token, password, key) may appear in logs, HTML, or API responses.

- **Check:** Grep deploy logs, HTML, and API responses for secret patterns
- **On violation:** Rotate the secret immediately, investigate the exposure path
