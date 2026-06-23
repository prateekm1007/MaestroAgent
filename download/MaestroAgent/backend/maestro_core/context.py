"""Run context and configuration — passed to every node invocation.

The `RunContext` is the "service locator" for a run. It carries:

- the LLM router (for agent calls)
- the memory manager (for read/write across tiers)
- the checkpoint store (for save/resume)
- the event bus (for streaming UI/WS clients)
- the verifier registry (for critic / evaluator-optimizer loops)
- the plugin registry
- run-wide config: budgets, role, template name, environment

Nodes receive `(State, RunContext)` and use the ctx to call out to the
rest of the system. This keeps node functions pure-ish: the same node
function works in tests (with a stub ctx) and in production (with a real
ctx), with no monkey-patching.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from maestro_llm.router import LLMRouter
    from maestro_memory.manager import MemoryManager
    from maestro_core.checkpoint import CheckpointStore
    from maestro_core.streaming import EventBus
    from maestro_verify.registry import VerifierRegistry
    from maestro_plugins.registry import PluginRegistry


@dataclass
class RunConfig:
    """Per-run configuration."""

    run_id: str
    template: str
    goal: str
    # Budgets — any one being hit pauses/escalates the run
    max_cost_usd: float = 10.0
    max_iterations: int = 100
    max_wall_clock_seconds: int = 60 * 60  # 1h default
    # Provider/model hints (router may override per-call)
    default_provider: str | None = None
    default_model: str | None = None
    # Sandbox
    sandbox_enabled: bool = True
    sandbox_image: str = "maestroagent/sandbox:latest"
    # Roles / RBAC
    agent_role: str = "default"
    # HITL
    hitl_mode: str = "async"  # "async" | "sync" | "off"
    # Environment
    env: dict[str, str] = field(default_factory=dict)
    # Arbitrary template-specific knobs
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunContext:
    """Passed to every node. Carries all the cross-cutting services."""

    config: RunConfig
    llm: "LLMRouter"
    memory: "MemoryManager"
    checkpoints: "CheckpointStore"
    events: "EventBus"
    verifiers: "VerifierRegistry"
    plugins: "PluginRegistry"
    # Per-run accumulators
    cost_so_far: float = 0.0
    iterations_so_far: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Set by the engine when entering a node that requires a specific role
    agent_role: str = "default"
    # Free-form per-run scratch (used by loops, supervisors, etc.)
    scratch: dict[str, Any] = field(default_factory=dict)

    @property
    def budget_remaining(self) -> float:
        return max(0.0, self.config.max_cost_usd - self.cost_so_far)

    @property
    def is_budget_exhausted(self) -> bool:
        return self.cost_so_far >= self.config.max_cost_usd

    @property
    def is_iteration_capped(self) -> bool:
        return self.iterations_so_far >= self.config.max_iterations

    def check_budget(self) -> None:
        """Raise if budget is exhausted. Called by nodes before expensive ops."""
        if self.is_budget_exhausted:
            raise BudgetExhausted(
                f"Run {self.config.run_id} hit cost cap "
                f"{self.config.max_cost_usd} (spent {self.cost_so_far:.4f})"
            )


class BudgetExhausted(Exception):
    """Raised when a run exceeds its cost budget."""


class IterationCapHit(Exception):
    """Raised when a run exceeds its iteration cap."""
