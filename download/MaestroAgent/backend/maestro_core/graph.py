"""Graph runtime — a small, LangGraph-flavored state machine.

Why not just use LangGraph directly?
------------------------------------
We do use LangGraph's checkpoint store and its `Command` primitive for
interop. But we wrap the graph in our own `Graph` class so we can:

1. Add first-class support for `LoopSpec` edges (MaestroAgent's native
   loops are not LangGraph cycles — they are data-driven sub-graphs with
   verifiable exit conditions).
2. Emit typed events on every transition for our local event bus.
3. Carry our own `State` model (with `revision`, `iteration`, etc.)
   instead of a plain dict.
4. Keep the engine usable as a library without LangGraph installed
   (LangGraph becomes optional in v0.2; for v0.1 we depend on it).

The model
---------
A `Graph` is a directed graph of `Node`s connected by `Edge`s. Nodes are
async callables `(State, RunContext) -> State`. Edges are either:

- `Edge` — unconditional, fire after the source node returns
- `ConditionalEdge` — fires only if `condition(state)` returns True
- `LoopEdge` — a special edge that wraps a sub-graph and a `LoopSpec`

The engine walks the graph starting at `entry`, calling each node and
following edges, until no more edges fire or the run budget is exhausted.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from maestro_core.state import State
from maestro_core.context import RunContext

# A node is an async function: (state, ctx) -> state.
NodeFn = Callable[[State, RunContext], Awaitable[State]]
# An edge condition: (state) -> bool
ConditionFn = Callable[[State], bool]


@dataclass
class Node:
    """A node in the graph."""

    id: str
    fn: NodeFn
    description: str = ""
    # Optional retry policy — None means use the engine default.
    retries: int | None = None
    # Roles allowed to execute this node — None means unrestricted.
    allowed_roles: list[str] | None = None

    async def __call__(self, state: State, ctx: RunContext) -> State:
        if self.allowed_roles is not None:
            # The caller (engine) sets ctx.agent_role; we check it here.
            if ctx.agent_role not in self.allowed_roles:
                raise PermissionError(
                    f"Node {self.id} requires role in {self.allowed_roles}, "
                    f"got {ctx.agent_role}"
                )
        result = self.fn(state, ctx)
        if inspect.isawaitable(result):
            result = await result
        return result


@dataclass
class Edge:
    """Unconditional edge: source -> target."""

    source: str
    target: str


@dataclass
class ConditionalEdge(Edge):
    """Edge that fires only when `condition(state)` is True."""

    condition: ConditionFn = field(default=lambda _s: True)

    def matches(self, state: State) -> bool:
        try:
            return bool(self.condition(state))
        except Exception:
            return False


@dataclass
class ParallelEdges:
    """Fan-out: source -> [targets], all run concurrently."""

    source: str
    targets: list[str]
    # Optional: only fan out to targets whose predicate matches.
    predicates: dict[str, ConditionFn] = field(default_factory=dict)


@dataclass
class Graph:
    """A directed graph of nodes connected by edges."""

    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge | ConditionalEdge | ParallelEdges] = field(default_factory=list)
    entry: str | None = None

    def add_node(self, node: Node) -> "Graph":
        if node.id in self.nodes:
            raise ValueError(f"Duplicate node id: {node.id}")
        self.nodes[node.id] = node
        if self.entry is None:
            self.entry = node.id
        return self

    def add_edge(self, source: str, target: str) -> "Graph":
        self._check_node(source)
        self._check_node(target)
        self.edges.append(Edge(source=source, target=target))
        return self

    def add_conditional_edge(
        self, source: str, target: str, condition: ConditionFn
    ) -> "Graph":
        self._check_node(source)
        self._check_node(target)
        self.edges.append(
            ConditionalEdge(source=source, target=target, condition=condition)
        )
        return self

    def add_parallel_edges(
        self, source: str, targets: list[str], predicates: dict[str, ConditionFn] | None = None
    ) -> "Graph":
        self._check_node(source)
        for t in targets:
            self._check_node(t)
        self.edges.append(
            ParallelEdges(source=source, targets=targets, predicates=predicates or {})
        )
        return self

    def set_entry(self, node_id: str) -> "Graph":
        self._check_node(node_id)
        self.entry = node_id
        return self

    def outgoing(self, node_id: str) -> list[Edge | ConditionalEdge | ParallelEdges]:
        return [e for e in self.edges if e.source == node_id]

    def _check_node(self, node_id: str) -> None:
        if node_id not in self.nodes:
            raise ValueError(f"Unknown node: {node_id}")

    def validate(self) -> list[str]:
        """Return a list of structural problems (empty list = OK)."""
        problems: list[str] = []
        if self.entry is None:
            problems.append("Graph has no entry node")
        for e in self.edges:
            if e.source not in self.nodes:
                problems.append(f"Edge source {e.source} not in nodes")
            if isinstance(e, ParallelEdges):
                for t in e.targets:
                    if t not in self.nodes:
                        problems.append(f"Parallel target {t} not in nodes")
            else:
                if e.target not in self.nodes:
                    problems.append(f"Edge target {e.target} not in nodes")
        return problems


async def run_parallel_targets(
    node: Node, state: State, ctx: RunContext, targets: list[str], graph: Graph
) -> list[State]:
    """Run a list of target nodes concurrently, returning their states.

    Used by ParallelEdges fan-out. Errors in one branch do not abort the
    others; the engine collects successes and failures.
    """
    async def _run_one(target_id: str) -> State:
        target = graph.nodes[target_id]
        # Each branch gets a fork of the state so they don't clobber each other.
        forked = state.bump()
        forked = forked.with_updates(current_node=target_id)
        return await target(forked, ctx)

    results = await asyncio.gather(
        *[_run_one(t) for t in targets], return_exceptions=True
    )
    return [r if not isinstance(r, Exception) else state.with_updates(error=str(r)) for r in results]
