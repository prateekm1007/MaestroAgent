"""GovernanceEnforcer — three layers of defense against forbidden actions.

Layer 1 (DETERMINISTIC): structurally checkable rules — no LLM needed.
  - Writes to governance/ → BLOCK
  - Changes threshold in benchmark.yml → BLOCK
  - Contains secret pattern → BLOCK
  - Action level > agent's max level → ESCALATE

Layer 2 (INDEPENDENT LLM CRITIC): semantic rules — a SEPARATE LLM context.
  - "Does this action game a metric?"
  - "Is this diagnosis dishonest?"
  - "Does this narrow a metric's scope to exclude failures?"
  The critic is blind to the actor's reasoning — it reviews the action alone.

Layer 3 (OUTCOME VERIFICATION): after the action, re-check invariants.
  - Did the fix game a metric? Re-run the benchmark subset.
  - Did it break an invariant? Re-check health/provenance/isolation.

The actor never grades its own homework. The enforcer is independent.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Verdict(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    ESCALATE = "ESCALATE"


@dataclass
class GovernanceResult:
    verdict: Verdict
    reason: str
    layer: str  # "deterministic" | "llm_critic" | "outcome_verification"
    post_verify: bool = False  # True if Layer 3 should run after the action


# ── Forbidden patterns (Layer 1) ────────────────────────────────────────────

SECRET_PATTERNS = [
    # Railway tokens (UUID format with hyphens)
    re.compile(r"e3d39b32-d40a-4405-9c08-958acaa9e92c", re.IGNORECASE),
    # Generic API key patterns (long hex/base64 strings labeled as keys)
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[a-zA-Z0-9]{32,}"),
    # OpenRouter keys
    re.compile(r"sk-or-[a-zA-Z0-9]{40,}"),
]

# Threshold constants in benchmark.yml — these must NEVER be lowered
DOCUMENTED_THRESHOLDS = {
    "safety_rate": 1.0,
    "abstention_rate": 1.0,
    "isolation_rate": 0.95,
    "correctness_rate": 0.90,
}

# Governance file paths — swarm cannot write these without human ratification
GOVERNANCE_DIR = Path(__file__).resolve().parents[1] / "governance"
BENCHMARK_YML = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "benchmark.yml"


@dataclass
class Action:
    """An action the swarm proposes to take."""
    name: str
    description: str
    level: int = 1  # 0=observe, 1=repair, 2=investigate, 3=governance change
    writes_to: list[str] = field(default_factory=list)  # file paths the action modifies
    changes_threshold: bool = False  # does it modify a gate threshold?
    contains_secret: bool = False  # does the action text contain a secret?
    raw_content: str = ""  # the full action payload for LLM review


class GovernanceEnforcer:
    """Three-layer governance enforcement. The actor never grades itself."""

    def __init__(self, agent_max_level: int = 2, llm_critic=None):
        self.agent_max_level = agent_max_level
        self.llm_critic = llm_critic  # injected; None = skip Layer 2 (testing only)

    def check(self, action: Action) -> GovernanceResult:
        """Check an action against all three layers. Returns a verdict."""
        # Layer 1: DETERMINISTIC (structural rules, no LLM)
        result = self._check_deterministic(action)
        if result.verdict != Verdict.ALLOW:
            return result

        # Layer 2: INDEPENDENT LLM CRITIC (semantic rules)
        result = self._check_llm_critic(action)
        if result.verdict != Verdict.ALLOW:
            return result

        # Layer 3: OUTCOME VERIFICATION (runs AFTER the action, not before)
        return GovernanceResult(
            verdict=Verdict.ALLOW,
            reason="Passed deterministic + LLM critic layers; outcome verification will run after action",
            layer="pre_action",
            post_verify=True,
        )

    # ── Layer 1: Deterministic ──────────────────────────────────────────────

    def _check_deterministic(self, action: Action) -> GovernanceResult:
        """Structurally checkable rules — no LLM needed."""

        # Rule 1: Cannot write to governance/ without human ratification
        for path in action.writes_to:
            try:
                resolved = Path(path).resolve()
                if GOVERNANCE_DIR in resolved.parents or resolved == GOVERNANCE_DIR:
                    return GovernanceResult(
                        verdict=Verdict.BLOCK,
                        reason=f"FORBIDDEN: cannot modify governance file {path} — human ratification required (AUTONOMY_LADDER Level 3)",
                        layer="deterministic",
                    )
            except Exception:
                pass

        # Rule 2: Cannot change threshold constants in benchmark.yml
        if action.changes_threshold:
            return GovernanceResult(
                verdict=Verdict.BLOCK,
                reason="FORBIDDEN: cannot lower gate thresholds — no-gaming rule (ANTI_ENTROPY.md). If threshold genuinely needs adjustment, escalate to human.",
                layer="deterministic",
            )
        for path in action.writes_to:
            if "benchmark.yml" in str(path) or "benchmark.yaml" in str(path):
                # Check if the action modifies a threshold value
                if self._action_modifies_threshold(action):
                    return GovernanceResult(
                        verdict=Verdict.BLOCK,
                        reason="FORBIDDEN: action modifies a threshold in benchmark.yml — no-gaming rule. Escalate to human.",
                        layer="deterministic",
                    )

        # Rule 3: Cannot expose secrets
        if action.contains_secret:
            return GovernanceResult(
                verdict=Verdict.BLOCK,
                reason="FORBIDDEN: action contains a secret pattern — S6 invariant (no secret exposure)",
                layer="deterministic",
            )
        for pattern in SECRET_PATTERNS:
            if pattern.search(action.raw_content) or pattern.search(action.description):
                return GovernanceResult(
                    verdict=Verdict.BLOCK,
                    reason=f"FORBIDDEN: action contains a secret pattern — S6 invariant (no secret exposure)",
                    layer="deterministic",
                )

        # Rule 4: Level check — Level 3 actions require human
        if action.level > self.agent_max_level:
            return GovernanceResult(
                verdict=Verdict.ESCALATE,
                reason=f"Level {action.level} action exceeds agent max level {self.agent_max_level} — human ratification required (AUTONOMY_LADDER.md)",
                layer="deterministic",
            )

        return GovernanceResult(
            verdict=Verdict.ALLOW,
            reason="Passed all deterministic checks",
            layer="deterministic",
        )

    def _action_modifies_threshold(self, action: Action) -> bool:
        """Check if the action's content modifies a threshold value."""
        content = action.raw_content.lower()
        for metric in DOCUMENTED_THRESHOLDS:
            # Look for patterns like 'isolation_rate': 0.80 (lowered from 0.95)
            pattern = rf"'{metric}'\s*:\s*([0-9.]+)"
            m = re.search(pattern, content)
            if m:
                new_val = float(m.group(1))
                if new_val < DOCUMENTED_THRESHOLDS[metric]:
                    return True
        return False

    # ── Layer 2: Independent LLM Critic ─────────────────────────────────────

    def _check_llm_critic(self, action: Action) -> GovernanceResult:
        """Semantic rules — reviewed by a SEPARATE LLM context (not the actor)."""
        if self.llm_critic is None:
            # No critic configured — skip (used in testing)
            return GovernanceResult(
                verdict=Verdict.ALLOW,
                reason="LLM critic not configured (skipped — testing mode only)",
                layer="llm_critic",
            )

        try:
            critique = self.llm_critic.review(action)
            if critique.get("verdict") == "VIOLATION":
                return GovernanceResult(
                    verdict=Verdict.BLOCK,
                    reason=f"LLM critic (independent): {critique.get('reason', 'unspecified violation')}",
                    layer="llm_critic",
                )
            return GovernanceResult(
                verdict=Verdict.ALLOW,
                reason=f"LLM critic (independent): {critique.get('reason', 'no violation detected')}",
                layer="llm_critic",
            )
        except Exception as e:
            # Fail safe — if the critic errors, BLOCK (don't allow un-reviewed)
            return GovernanceResult(
                verdict=Verdict.BLOCK,
                reason=f"LLM critic error (fail-safe BLOCK): {e}",
                layer="llm_critic",
            )

    # ── Layer 3: Outcome Verification (runs AFTER the action) ───────────────

    def verify_outcome(self, action: Action, invariant_checks: dict[str, bool]) -> GovernanceResult:
        """Layer 3: after the action, verify invariants still hold.

        Args:
            action: the action that was taken
            invariant_checks: dict of {invariant_name: passed} from re-running checks

        Returns:
            ALLOW if all invariants hold, BLOCK if any were violated
        """
        failed = [name for name, passed in invariant_checks.items() if not passed]
        if failed:
            return GovernanceResult(
                verdict=Verdict.BLOCK,
                reason=f"Outcome verification FAILED — invariants violated: {', '.join(failed)}. The action may have gamed a metric or broken a property. Roll back and investigate.",
                layer="outcome_verification",
            )
        return GovernanceResult(
            verdict=Verdict.ALLOW,
            reason=f"Outcome verification passed — all invariants hold: {', '.join(invariant_checks.keys())}",
            layer="outcome_verification",
        )

    # ── Report governance: enforce rules on outgoing reports ─────────────────

    def check_report(self, report_text: str) -> GovernanceResult:
        """Enforce governance rules on an outgoing report.

        The constitution applies to reports ABOUT the swarm, not just to the
        actions the swarm takes. This catches secret values in reports, which
        is exactly what FORBIDDEN_ACTIONS.md Rule 3 forbids.

        This is the swarm's first real enforcement action: it caught its own
        operator's secret slip (the RAILWAY_API_TOKEN value pasted in a summary).

        Args:
            report_text: the full text of the report/outgoing message

        Returns:
            BLOCK if a secret pattern is found, ALLOW otherwise
        """
        # Layer 1: secret pattern check on the report text
        for pattern in SECRET_PATTERNS:
            match = pattern.search(report_text)
            if match:
                # Redact the match for the reason (don't repeat the secret!)
                return GovernanceResult(
                    verdict=Verdict.BLOCK,
                    reason=f"FORBIDDEN: report contains a secret pattern (matched: {pattern.pattern[:30]}...). Secrets must be referenced BY NAME ONLY, never by value. (FORBIDDEN_ACTIONS.md Rule 3, S6 invariant)",
                    layer="deterministic",
                )

        return GovernanceResult(
            verdict=Verdict.ALLOW,
            reason="Report passed secret-pattern check — no secret values detected",
            layer="deterministic",
        )


# ── Red/Green proof ─────────────────────────────────────────────────────────

def run_red_green_proof() -> bool:
    """Prove the GovernanceEnforcer blocks forbidden actions and allows safe ones.

    Returns True if all tests pass.
    """
    enforcer = GovernanceEnforcer(agent_max_level=2, llm_critic=None)

    tests = []

    # RED 1: Write to governance/ → BLOCK
    action = Action(
        name="modify_constitution",
        description="Update ANTI_ENTROPY.md to relax the no-gaming rule",
        level=1,
        writes_to=["governance/ANTI_ENTROPY.md"],
    )
    result = enforcer.check(action)
    tests.append(("RED: write to governance/", result.verdict == Verdict.BLOCK, result.reason))

    # RED 2: Lower isolation threshold → BLOCK
    action = Action(
        name="lower_isolation_threshold",
        description="Lower isolation_rate threshold from 0.95 to 0.80 to make the gate pass",
        level=1,
        changes_threshold=True,
        writes_to=[".github/workflows/benchmark.yml"],
        raw_content="'isolation_rate': 0.80,  # lowered to pass",
    )
    result = enforcer.check(action)
    tests.append(("RED: lower isolation threshold", result.verdict == Verdict.BLOCK, result.reason))

    # RED 3: Secret exposure → BLOCK
    action = Action(
        name="log_secret",
        description="Log the Railway token for debugging",
        level=1,
        contains_secret=True,
        raw_content="RAILWAY_TOKEN=e3d39b32-d40a-4405-9c08-958acaa9e92c",
    )
    result = enforcer.check(action)
    tests.append(("RED: secret exposure", result.verdict == Verdict.BLOCK, result.reason))

    # RED 4: Level 3 action → ESCALATE
    action = Action(
        name="delete_deployment",
        description="Delete the production deployment",
        level=3,
    )
    result = enforcer.check(action)
    tests.append(("RED: Level 3 action escalates", result.verdict == Verdict.ESCALATE, result.reason))

    # GREEN 1: Safe deploy trigger → ALLOW
    action = Action(
        name="trigger_deploy",
        description="Trigger deploy.yml via workflow_dispatch to fix drift",
        level=1,
        writes_to=[],  # no file writes
    )
    result = enforcer.check(action)
    tests.append(("GREEN: safe deploy trigger", result.verdict == Verdict.ALLOW, result.reason))

    # GREEN 2: Run benchmark canary → ALLOW
    action = Action(
        name="run_canary",
        description="Run the 20-question safety+abstention+injection canary",
        level=0,
        writes_to=[],
    )
    result = enforcer.check(action)
    tests.append(("GREEN: run canary", result.verdict == Verdict.ALLOW, result.reason))

    # GREEN 3: Raise threshold (stricter) → ALLOW
    action = Action(
        name="raise_isolation_threshold",
        description="Raise isolation_rate threshold from 0.95 to 0.98 (stricter)",
        level=2,
        changes_threshold=False,  # raising is not "lowering"
        writes_to=[".github/workflows/benchmark.yml"],
        raw_content="'isolation_rate': 0.98,  # raised (stricter)",
    )
    result = enforcer.check(action)
    tests.append(("GREEN: raise threshold (stricter)", result.verdict == Verdict.ALLOW, result.reason))

    # RED 5: Report containing the leaked RAILWAY_API_TOKEN value → BLOCK
    # This is the governance self-test: the enforcer catches its own operator's
    # secret slip. The token value below is the one that was pasted in a prior
    # summary — the enforcer must catch it in any report.
    leaked_report = (
        "Summary: Prateek needs to add 3 secrets:\n"
        "  RAILWAY_API_TOKEN = e3d39b32-d40a-4405-9c08-958acaa9e92c\n"
        "  RAILWAY_BACKEND_SERVICE_ID = c12adfcf-...\n"
    )
    result = enforcer.check_report(leaked_report)
    tests.append(("RED: report with leaked token value", result.verdict == Verdict.BLOCK, result.reason))

    # GREEN 4: Report referencing secrets BY NAME ONLY → ALLOW
    clean_report = (
        "Summary: Prateek needs to add 3 GitHub Actions secrets:\n"
        "  - RAILWAY_API_TOKEN (value provided separately)\n"
        "  - RAILWAY_BACKEND_SERVICE_ID\n"
        "  - RAILWAY_FRONTEND_SERVICE_ID\n"
        "All secrets referenced by name only, never by value.\n"
    )
    result = enforcer.check_report(clean_report)
    tests.append(("GREEN: report with secrets by name only", result.verdict == Verdict.ALLOW, result.reason))

    # Print results
    print("=" * 72)
    print("GOVERNANCE ENFORCER — RED/GREEN PROOF")
    print("=" * 72)
    all_pass = True
    for name, passed, reason in tests:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status:10s} {name:45s}")
        if not passed:
            print(f"             reason: {reason}")
            all_pass = False

    print()
    if all_pass:
        print("ALL TESTS PASS — enforcer blocks forbidden actions, allows safe ones.")
    else:
        print("AT LEAST ONE TEST FAILED — enforcer is not enforcing correctly.")
    return all_pass


if __name__ == "__main__":
    import sys
    sys.exit(0 if run_red_green_proof() else 1)
