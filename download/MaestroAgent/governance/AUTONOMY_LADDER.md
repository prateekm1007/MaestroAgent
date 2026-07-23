# Autonomy Ladder — What the Swarm Can and Cannot Do Without Human Approval

The autonomy ladder defines what actions the swarm can take at each level. Higher levels require more human involvement.

## Level 0 — Observe (autonomous, no human)

The swarm can always:
- Read public endpoints (`/api/health`, frontend root)
- Query Railway GraphQL API (with token)
- Query GitHub API (with token)
- Read the repo, read logs, read metrics
- Detect drift, diagnose stalls, create tickets
- Search case memory (FTS5)
- Run the benchmark subset (canary)

**No human approval needed.** These are read-only / observe-only actions.

## Level 1 — Repair (autonomous, with governance gate)

The swarm can:
- Trigger a deploy via GitHub Actions `workflow_dispatch`
- Restart a service (Railway API)
- Run a canary benchmark
- Apply a known runbook fix (from case memory, high-confidence match)
- Create a GitHub issue / PR draft

**Governance gate required:** `GovernanceEnforcer.check(action)` must return ALLOW. The deterministic layer + LLM critic must both pass. Outcome verification runs after.

## Level 2 — Investigate (autonomous, bounded)

The swarm can:
- Run diagnostic scripts (read-only DB queries, log analysis)
- Propose a code fix (as a PR draft, NOT merged)
- Create a test case for a new bug
- Modify non-governance config files (e.g., a workflow's timeout)

**Governance gate required + PR review.** The swarm drafts; a human reviews and merges. The swarm CANNOT merge its own PRs.

## Level 3 — Change governance / thresholds / architecture (HUMAN REQUIRED)

The swarm CANNOT:
- Modify `governance/` files (BLOCKED by Layer 1)
- Lower gate thresholds (BLOCKED by Layer 1)
- Merge a PR (BLOCKED — human must merge)
- Delete a deployment (BLOCKED — human must approve)
- Change the autonomy ladder itself (BLOCKED — human must ratify)
- Modify the benchmark YAML's thresholds (BLOCKED by Layer 1)

**These actions ESCALATE to human.** The swarm drafts the change; Prateek ratifies.

## The Escalation Path

When the swarm hits a Level-3 action or a governance BLOCK:
1. Create a GitHub issue with the proposed action + governance verdict
2. Tag it `needs-human-ratification`
3. Stop — do not attempt the action
4. Wait for human approval (issue comment with `/approve`)

The swarm never grades its own homework. The GovernanceEnforcer is independent; the human is the final authority.
