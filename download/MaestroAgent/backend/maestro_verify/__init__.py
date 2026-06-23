"""maestro_verify — verification, reliability, and governance.

This package contains the verifiers that make MaestroAgent's autonomy
*trustworthy*:

- `critic` — LLM-as-judge that scores outputs against a rubric.
- `evaluator` — the evaluator-optimizer loop (generate → evaluate →
  optimize → regenerate).
- `sandbox` — Docker-sandboxed command execution for tests/lint/security.
- `recovery` — failure recovery, model fallback, checkpoint resume.
- `registry` — registry of verifiers, so loops can reference them by name.

A `Verifier` is an async callable `(State, RunContext) -> VerifierResult`.
The `LoopHandler`'s `Condition` objects wrap verifiers (e.g.
`TestPassCondition` wraps `run_in_sandbox`).
"""

from maestro_verify.critic import score_with_critic, CriticResult
from maestro_verify.evaluator import EvaluatorOptimizer, EvalResult
from maestro_verify.sandbox import run_in_sandbox, SandboxResult
from maestro_verify.recovery import FailureRecovery, FallbackPolicy
from maestro_verify.registry import VerifierRegistry, Verifier, VerifierResult

__all__ = [
    "score_with_critic",
    "CriticResult",
    "EvaluatorOptimizer",
    "EvalResult",
    "run_in_sandbox",
    "SandboxResult",
    "FailureRecovery",
    "FallbackPolicy",
    "VerifierRegistry",
    "Verifier",
    "VerifierResult",
]
