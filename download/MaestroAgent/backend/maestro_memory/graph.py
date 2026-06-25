"""Graph memory — entity & agent relationship store.

The graph tier captures relationships that vector similarity cannot:
"agent X produced file Y", "artifact A depends on artifact B", "agent
P is the parent of agent C". This is essential for:

- **Provenance.** "Where did this file come from?" → traverse the graph.
- **Impact analysis.** "If I change this artifact, what depends on it?"
- **Audit.** "Which agents touched this run?"

Backends
--------
- `NetworkXGraphMemory` — default. In-memory + JSON persistence. Good
  for single-machine runs.
- `Neo4jGraphMemory` — placeholder for v0.2 multi-machine deployments.

Schema
------
Nodes: {kind: "agent"|"artifact"|"tool_call"|"episode", id, props...}
Edges: {kind: "produced"|"consumed"|"spawned"|"depends_on"|"critiqued", src, dst, props...}
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GraphNode:
    kind: str  # "agent" | "artifact" | "tool_call" | "episode"
    id: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    kind: str  # "produced" | "consumed" | "spawned" | "depends_on" | "critiqued"
    src: str
    dst: str
    properties: dict[str, Any] = field(default_factory=dict)


class GraphMemory(ABC):
    """Abstract graph memory."""

    @abstractmethod
    async def add_node(self, node: GraphNode) -> None: ...

    @abstractmethod
    async def add_edge(self, edge: GraphEdge) -> None: ...

    @abstractmethod
    async def neighbors(self, node_id: str, edge_kind: str | None = None) -> list[GraphNode]: ...

    @abstractmethod
    async def path(self, src: str, dst: str) -> list[str]: ...

    @abstractmethod
    async def ancestors(self, node_id: str) -> list[GraphNode]: ...

    @abstractmethod
    async def descendants(self, node_id: str) -> list[GraphNode]: ...


class NetworkXGraphMemory(GraphMemory):
    """NetworkX-backed graph memory with JSON persistence."""

    def __init__(self, persist_path: str | Path | None = ".maestro/graph.json") -> None:
        try:
            import networkx as nx
        except ImportError as e:
            raise ImportError("NetworkXGraphMemory requires `pip install networkx`") from e
        self._nx = nx
        self._graph = nx.DiGraph()
        self._persist_path = str(persist_path) if persist_path else None
        if self._persist_path and Path(self._persist_path).exists():
            self._load()

    async def add_node(self, node: GraphNode) -> None:
        self._graph.add_node(node.id, kind=node.kind, **node.properties)
        self._maybe_persist()

    async def add_edge(self, edge: GraphEdge) -> None:
        self._graph.add_edge(
            edge.src, edge.dst, kind=edge.kind, **edge.properties
        )
        self._maybe_persist()

    async def neighbors(self, node_id: str, edge_kind: str | None = None) -> list[GraphNode]:
        if node_id not in self._graph:
            return []
        results: list[GraphNode] = []
        for neighbor in self._graph.successors(node_id):
            edge_data = self._graph.edges[node_id, neighbor]
            if edge_kind is not None and edge_data.get("kind") != edge_kind:
                continue
            data = self._graph.nodes[neighbor]
            results.append(
                GraphNode(
                    kind=data.get("kind", "unknown"),
                    id=neighbor,
                    properties={k: v for k, v in data.items() if k != "kind"},
                )
            )
        return results

    async def path(self, src: str, dst: str) -> list[str]:
        try:
            return self._nx.shortest_path(self._graph, src, dst)
        except (self._nx.NetworkXNoPath, self._nx.NodeNotFound):
            return []

    async def ancestors(self, node_id: str) -> list[GraphNode]:
        if node_id not in self._graph:
            return []
        results: list[GraphNode] = []
        for anc in self._nx.ancestors(self._graph, node_id):
            data = self._graph.nodes[anc]
            results.append(
                GraphNode(
                    kind=data.get("kind", "unknown"),
                    id=anc,
                    properties={k: v for k, v in data.items() if k != "kind"},
                )
            )
        return results

    async def descendants(self, node_id: str) -> list[GraphNode]:
        if node_id not in self._graph:
            return []
        results: list[GraphNode] = []
        for desc in self._nx.descendants(self._graph, node_id):
            data = self._graph.nodes[desc]
            results.append(
                GraphNode(
                    kind=data.get("kind", "unknown"),
                    id=desc,
                    properties={k: v for k, v in data.items() if k != "kind"},
                )
            )
        return results

    def _maybe_persist(self) -> None:
        if not self._persist_path:
            return
        Path(self._persist_path).parent.mkdir(parents=True, exist_ok=True)
        data = self._nx.node_link_data(self._graph)
        Path(self._persist_path).write_text(json.dumps(data, default=str))

    def _load(self) -> None:
        data = json.loads(Path(self._persist_path).read_text())
        self._graph = self._nx.node_link_graph(data, directed=True)
