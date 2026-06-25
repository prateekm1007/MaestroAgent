"""Verifier registry — register verifiers by name so loops can reference them.

A `Verifier` is an async callable `(State, RunContext) -> VerifierResult`.
Verifiers are registered with a name; templates reference verifiers by
name (e.g. `condition: {verifier: "pytest"}`). This indirection lets
users swap verifiers without rewriting templates.

Built-in verifiers
------------------
- `pytest` — run pytest in the sandbox.
- `ruff` — run ruff lint in the sandbox.
- `mypy` — run mypy in the sandbox.
- `critic` — LLM-as-judge critic with a configurable rubric.
- `evaluator` — full evaluator-optimizer loop.

Users can register their own via `registry.register("name", verifier)`.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    from maestro_core.context import RunContext
    from maestro_core.state import State


@dataclass
class VerifierResult:
    passed: bool
    score: float = 0.0
    reason: str = ""
    artifacts: dict[str, Any] | None = None


# A verifier is an async callable.
Verifier = Callable[["State", "RunContext"], Awaitable[VerifierResult]]


class VerifierRegistry:
    """Named registry of verifiers."""

    def __init__(self) -> None:
        self._verifiers: dict[str, Verifier] = {}
        self._register_builtins()

    def register(self, name: str, verifier: Verifier) -> None:
        self._verifiers[name] = verifier

    def get(self, name: str) -> Verifier:
        if name not in self._verifiers:
            raise KeyError(f"Unknown verifier: {name}")
        return self._verifiers[name]

    def names(self) -> list[str]:
        return sorted(self._verifiers.keys())

    def _register_builtins(self) -> None:
        async def _pytest(state: "State", ctx: "RunContext") -> VerifierResult:
            from maestro_verify.sandbox import run_in_sandbox
            res = await run_in_sandbox(ctx, "pytest -x --tb=short", timeout=180)
            return VerifierResult(
                passed=res.exit_code == 0,
                score=1.0 if res.exit_code == 0 else 0.0,
                reason=res.stderr[:500] if res.exit_code != 0 else "all tests passed",
                artifacts={"stdout": res.stdout, "stderr": res.stderr},
            )

        async def _ruff(state: "State", ctx: "RunContext") -> VerifierResult:
            from maestro_verify.sandbox import run_in_sandbox
            res = await run_in_sandbox(ctx, "ruff check .", timeout=60)
            return VerifierResult(
                passed=res.exit_code == 0,
                score=1.0 if res.exit_code == 0 else 0.5,
                reason=res.stdout[:500],
            )

        async def _mypy(state: "State", ctx: "RunContext") -> VerifierResult:
            from maestro_verify.sandbox import run_in_sandbox
            res = await run_in_sandbox(ctx, "mypy .", timeout=120)
            return VerifierResult(
                passed=res.exit_code == 0,
                score=1.0 if res.exit_code == 0 else 0.5,
                reason=res.stdout[:500],
            )

        self.register("pytest", _pytest)
        self.register("ruff", _ruff)
        self.register("mypy", _mypy)
