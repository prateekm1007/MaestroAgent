"""maestro_loops — native advanced loops with verifiable exit conditions.

Loops are first-class in MaestroAgent. A `LoopHandler` wraps a sub-graph
(or a single agent) and runs it repeatedly until an exit condition is
met, a budget is exhausted, or the run is paused for HITL.

Loop types
----------
- **Recursive (until-verifiable)**: run until tests pass / metrics met /
  critic approves. The default for "agent that fixes its own bugs".
- **Cron**: run on a schedule (cron expression). Used for periodic ops.
- **Webhook**: run when an external webhook fires. Used for CI triggers.
- **File event**: run when a file path changes. Used for "watch and react".
- **Nested**: a loop whose body contains another loop.
- **Parallel**: N loops running concurrently with results merged.
- **Meta**: a supervisor that decides which loop to run next.

Every loop has:
- `exit_condition`: a `Condition` object (test runner, metric, critic, callable)
- `budget`: max iterations / tokens / wall-clock
- `backoff`: policy for retrying on failure
- `on_exceed`: escalate / pause / fail
"""

from maestro_loops.handler import LoopHandler, LoopSpec, LoopOutcome
from maestro_loops.conditions import (
    Condition,
    TestPassCondition,
    MetricThresholdCondition,
    CriticCondition,
    CallableCondition,
    AllOf,
    AnyOf,
)
from maestro_loops.types import LoopKind, BackoffPolicy, OnExceedAction
from maestro_loops.nested import NestedLoop, ParallelLoop, MetaLoop

__all__ = [
    "LoopHandler",
    "LoopSpec",
    "LoopOutcome",
    "Condition",
    "TestPassCondition",
    "MetricThresholdCondition",
    "CriticCondition",
    "CallableCondition",
    "AllOf",
    "AnyOf",
    "LoopKind",
    "BackoffPolicy",
    "OnExceedAction",
    "NestedLoop",
    "ParallelLoop",
    "MetaLoop",
]
