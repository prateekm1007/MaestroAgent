# Forbidden Actions — Drawn From Real Incidents

Each forbidden action below is grounded in a specific incident from this audit arc. The swarm must NEVER take these actions, and the GovernanceEnforcer must BLOCK them.

## 1. Lowering a gate threshold to silence a red

**Incident:** The scorer isolation_rate was computed incorrectly (used overall pass instead of isolation-specific pass). The fix corrected the metric, but a tempting alternative would have been to lower the isolation threshold from 0.95 to 0.80 to make the old metric read green.

**Rule:** Never lower a threshold in `benchmark.yml` or any gate config to make a failing metric pass. If a threshold genuinely needs adjustment, escalate to human.

**Enforcement:** `GovernanceEnforcer` Layer 1 (deterministic) — any action that modifies a threshold constant in `benchmark.yml` is BLOCKED.

## 2. Claiming "live" without a fresh fetch

**Incident:** The SSR first-paint was claimed "live" based on a local build artifact, but the external auditor's fresh fetch showed `Loading…` (later resolved as a non-JS tool blind spot, but the claim was made without the right instrument).

**Rule:** Never state something is "live" without a fresh, independent fetch of the public endpoint at the moment of the claim. For client-rendered content, use a JS-executing instrument.

**Enforcement:** `GovernanceEnforcer` Layer 2 (LLM critic) — reviews reports for live-claims without evidence.

## 3. Seeding synthetic data and presenting it as real

**Incident:** Temptation to seed the calibration report with synthetic benchmark predictions to show a Brier score before real usage accumulated.

**Rule:** Never present synthetic/demo data as real calibration, real evidence, or real usage. If demo data is needed for dogfood, label it explicitly ("demo/synthetic, not real usage").

**Enforcement:** `GovernanceEnforcer` Layer 2 (LLM critic) — reviews calibration/evidence outputs for synthetic data presented as real.

## 4. Modifying governance files without human ratification

**Incident:** (Preventive) — an autonomous agent could weaken the constitution to escape constraints.

**Rule:** The swarm's file-write tool CANNOT touch `governance/` without a human ratification token. Governance amendments require human approval.

**Enforcement:** `GovernanceEnforcer` Layer 1 (deterministic) — any action that writes to `governance/` is BLOCKED.

## 5. Gaming a metric by narrowing scope

**Incident:** The old isolation_rate only inspected the entity_specific category. Widening to all categories revealed 98.86% (more honest) instead of 100% (narrow). The temptation would have been to keep the narrow scope to preserve the headline 100%.

**Rule:** Never narrow a metric's scope to exclude failures and make it read greener. Metrics must measure what they claim to measure, across the full applicable domain.

**Enforcement:** `GovernanceEnforcer` Layer 2 (LLM critic) — reviews metric changes for scope-narrowing.

## 6. Accepting "exists" for "works"

**Incident:** The correction endpoint existed and recorded `metadata["correction"]`, but specialist retrievers didn't read it — so correction was write-only. The temptation was to say "correction works" because the endpoint existed.

**Rule:** Never claim a capability works based on the endpoint existing. Trace the full path: does the data flow downstream? Does it actually change behavior? "Exists" ≠ "works."

**Enforcement:** `GovernanceEnforcer` Layer 3 (outcome verification) — after a fix, verify the full loop, not just the entry point.

## 7. Spraying a fix before all return paths

**Incident:** `_fix_source_types` was inserted before all 12 `return AskResponse` statements, including early-return abstention paths where `evidence_refs` was undefined → `UnboundLocalError` → safety dropped to 0%.

**Rule:** When adding a fix that touches multiple return paths, verify the variable is defined on ALL paths — including early returns, error paths, and abstention paths. Never spray a fix blindly.

**Enforcement:** `GovernanceEnforcer` Layer 3 (outcome verification) — after the fix, re-run the benchmark subset to confirm no regression on abstention/safety paths.

## 8. Headless-browser OAuth to install a third-party GitHub App

**Incident:** The Railway GitHub App required browser OAuth. The temptation was to automate it with a headless browser + stored credentials.

**Rule:** Never automate browser-based OAuth for third-party app installation. GitHub gates this behind a consent screen deliberately. Route around it (e.g., deploy from GitHub Actions) instead of fighting it.

**Enforcement:** `GovernanceEnforcer` Layer 2 (LLM critic) — reviews actions for headless-browser OAuth attempts.
