"""
EvidenceGraph — the traversable provenance graph.

Every recommendation traces back through:
  Recommendation → Law → Pattern → LearningObject → Receipt → Signal → Original Artifact

The EvidenceGraph is a directed graph where:
- Nodes are evidence elements (signals, receipts, LOs, patterns, laws, recommendations)
- Edges are "supported by" relationships
- Traversal from any node reaches the original artifacts

The graph supports:
- Building from the ExecutionModel's state
- Traversing from any node to its supporting evidence
- Deleting evidence (removes nodes + edges, recomputes confidence)
- Reconnecting evidence (adds nodes + edges, recomputes confidence)
- Returning supporting and contradicting artifacts for any recommendation
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EvidenceNodeType(str, Enum):
    SIGNAL = "signal"
    RECEIPT = "receipt"
    LEARNING_OBJECT = "learning_object"
    PATTERN = "pattern"
    LAW = "law"
    RECOMMENDATION = "recommendation"


class EvidenceEdgeType(str, Enum):
    PRODUCED = "produced"          # Signal produced a Receipt
    CAUSED = "caused"              # Receipt caused a LearningObject
    CONTRIBUTED_TO = "contributed"  # LO contributed to a Pattern
    PROMOTED_TO = "promoted"       # Pattern promoted to Law
    VALIDATED = "validated"        # Signal validated a Law
    CONTRADICTED = "contradicted"  # Signal contradicted a Law
    DERIVED_FROM = "derived"       # Recommendation derived from Law
    SUPPORTS = "supports"          # General support edge


class EvidenceNode(BaseModel):
    """A node in the evidence graph."""
    node_id: str  # Unique ID (e.g., "signal:uuid", "law:L-0007", "rec:abc123")
    node_type: EvidenceNodeType
    label: str  # Human-readable label
    artifact_ref: str = ""  # Reference to the original artifact (URL, ticket ID, etc.)
    provider: str = ""  # Which signal provider
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}


class EvidenceEdge(BaseModel):
    """A directed edge in the evidence graph."""
    edge_id: UUID = Field(default_factory=uuid4)
    source: str  # Source node_id (higher in the chain, e.g., "law:L-0007")
    target: str  # Target node_id (lower in the chain, e.g., "lo:uuid")
    edge_type: EvidenceEdgeType
    weight: float = 1.0  # How strongly this edge supports the source
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceChain(BaseModel):
    """A complete chain from a recommendation back to original artifacts."""
    root_id: str  # The recommendation or law this chain explains
    nodes: list[EvidenceNode] = Field(default_factory=list)
    edges: list[EvidenceEdge] = Field(default_factory=list)
    supporting_artifacts: list[dict[str, Any]] = Field(default_factory=list)
    contradicting_artifacts: list[dict[str, Any]] = Field(default_factory=list)
    strength: float = 0.0  # Overall evidence strength (0..1)

    def to_display(self) -> dict[str, Any]:
        """Convert to a UI-friendly structure."""
        return {
            "root": self.root_id,
            "strength": round(self.strength, 4),
            "chain": [
                {
                    "node_id": n.node_id,
                    "type": n.node_type.value,
                    "label": n.label,
                    "artifact": n.artifact_ref,
                    "provider": n.provider,
                    "timestamp": n.timestamp.isoformat(),
                }
                for n in self.nodes
            ],
            "supporting_artifacts": self.supporting_artifacts,
            "contradicting_artifacts": self.contradicting_artifacts,
            "edge_count": len(self.edges),
            "node_count": len(self.nodes),
        }


class EvidenceGraph:
    """
    The traversable evidence graph.

    Built from the ExecutionModel's state. Supports:
    - Traversal from any node to its supporting evidence
    - Deletion of evidence (with confidence recomputation)
    - Reconnection of evidence (with confidence recomputation)
    - Querying supporting and contradicting artifacts
    """

    def __init__(self) -> None:
        self.nodes: dict[str, EvidenceNode] = {}
        self.edges: list[EvidenceEdge] = []
        # Adjacency: source_id → list of (edge, target_id)
        self._outgoing: dict[str, list[tuple[EvidenceEdge, str]]] = defaultdict(list)
        # Reverse adjacency: target_id → list of (edge, source_id)
        self._incoming: dict[str, list[tuple[EvidenceEdge, str]]] = defaultdict(list)

    def add_node(self, node: EvidenceNode) -> None:
        """Add a node to the graph."""
        self.nodes[node.node_id] = node

    def add_edge(
        self,
        source: str,
        target: str,
        edge_type: EvidenceEdgeType,
        weight: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> EvidenceEdge:
        """Add a directed edge: source is supported by target."""
        edge = EvidenceEdge(
            source=source,
            target=target,
            edge_type=edge_type,
            weight=weight,
            metadata=metadata or {},
        )
        self.edges.append(edge)
        self._outgoing[source].append((edge, target))
        self._incoming[target].append((edge, source))
        return edge

    def remove_node(self, node_id: str) -> None:
        """Remove a node and all its edges."""
        if node_id not in self.nodes:
            return
        del self.nodes[node_id]
        # Remove outgoing edges
        self._outgoing.pop(node_id, None)
        # Remove incoming edges
        self._incoming.pop(node_id, None)
        # Remove from edge list
        self.edges = [
            e for e in self.edges
            if e.source != node_id and e.target != node_id
        ]
        # Rebuild adjacency for nodes that pointed to or from this node
        self._rebuild_adjacency()

    def _rebuild_adjacency(self) -> None:
        """Rebuild adjacency lists from edge list."""
        self._outgoing = defaultdict(list)
        self._incoming = defaultdict(list)
        for edge in self.edges:
            if edge.source in self.nodes and edge.target in self.nodes:
                self._outgoing[edge.source].append((edge, edge.target))
                self._incoming[edge.target].append((edge, edge.source))

    def traverse(self, root_id: str) -> EvidenceChain:
        """
        Traverse the graph from a root node (recommendation or law)
        down to the original artifacts.

        Returns an EvidenceChain with all supporting nodes and artifacts.
        """
        chain = EvidenceChain(root_id=root_id)

        if root_id not in self.nodes:
            return chain

        # BFS traversal following outgoing edges
        visited: set[str] = set()
        queue: list[str] = [root_id]
        chain.nodes.append(self.nodes[root_id])

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            for edge, target_id in self._outgoing.get(current, []):
                if target_id in self.nodes and target_id not in visited:
                    chain.edges.append(edge)
                    chain.nodes.append(self.nodes[target_id])

                    # Collect artifacts
                    node = self.nodes[target_id]
                    if node.artifact_ref:
                        artifact_entry = {
                            "artifact": node.artifact_ref,
                            "provider": node.provider,
                            "type": node.node_type.value,
                            "label": node.label,
                            "node_id": node.node_id,
                        }
                        if edge.edge_type == EvidenceEdgeType.CONTRADICTED:
                            chain.contradicting_artifacts.append(artifact_entry)
                        else:
                            chain.supporting_artifacts.append(artifact_entry)

                    queue.append(target_id)

        # Compute strength from edge weights and node count
        if chain.edges:
            total_weight = sum(e.weight for e in chain.edges)
            chain.strength = min(1.0, total_weight / (total_weight + 2))
        elif root_id in self.nodes:
            chain.strength = 0.1  # Lone node, minimal strength
        else:
            chain.strength = 0.0

        return chain

    def get_supporting_artifacts(self, root_id: str) -> list[dict[str, Any]]:
        """Get all artifacts that support the given node."""
        chain = self.traverse(root_id)
        return chain.supporting_artifacts

    def get_contradicting_artifacts(self, root_id: str) -> list[dict[str, Any]]:
        """Get all artifacts that contradict the given node."""
        chain = self.traverse(root_id)
        return chain.contradicting_artifacts

    def get_evidence_strength(self, root_id: str) -> float:
        """Get the overall evidence strength for a node (0..1)."""
        chain = self.traverse(root_id)
        return chain.strength

    def delete_evidence(self, signal_id: str) -> list[str]:
        """
        Delete all evidence derived from a signal.

        Removes the signal node and cascades: removes receipts that reference it,
        removes LOs that only had that signal as evidence, etc.

        Returns the list of affected node IDs (for confidence recomputation).
        """
        affected: list[str] = []

        # Find the signal node
        signal_node_id = f"signal:{signal_id}"
        if signal_node_id not in self.nodes:
            return affected

        # Find all nodes that depend on this signal (transitive closure)
        to_remove: set[str] = {signal_node_id}
        changed = True
        while changed:
            changed = False
            for node_id in list(self.nodes.keys()):
                if node_id in to_remove:
                    continue
                # If all outgoing edges point to removed nodes, this node loses all support
                outgoing = self._outgoing.get(node_id, [])
                if outgoing and all(t in to_remove for _, t in outgoing):
                    to_remove.add(node_id)
                    changed = True

        # Also find nodes that have SOME support removed (not all)
        for node_id in self.nodes:
            if node_id in to_remove:
                continue
            outgoing = self._outgoing.get(node_id, [])
            for _, target_id in outgoing:
                if target_id in to_remove:
                    affected.append(node_id)
                    break

        # Remove the nodes
        for node_id in to_remove:
            affected.append(node_id)
            self.remove_node(node_id)

        return list(set(affected))

    def reconnect_evidence(
        self,
        signal_node: EvidenceNode,
        receipt_node: EvidenceNode,
        lo_node: EvidenceNode,
        law_node_ids: list[str],
    ) -> None:
        """
        Reconnect evidence after a signal is re-added.

        Rebuilds the edges: signal → receipt → LO → law
        """
        self.add_node(signal_node)
        self.add_node(receipt_node)
        self.add_node(lo_node)

        self.add_edge(receipt_node.node_id, signal_node.node_id, EvidenceEdgeType.PRODUCED)
        self.add_edge(lo_node.node_id, receipt_node.node_id, EvidenceEdgeType.CAUSED)

        for law_id in law_node_ids:
            if law_id in self.nodes:
                self.add_edge(law_id, lo_node.node_id, EvidenceEdgeType.VALIDATED)

    def build_from_model(self, model: Any) -> None:
        """
        Build the evidence graph from an ExecutionModel.

        Creates nodes for:
        - Every processed signal
        - Every receipt
        - Every learning object
        - Every pattern
        - Every law
        - Every recommendation (from DecisionEngine)
        """
        from maestro_oem.decision import DecisionEngine

        # 1. Add signal nodes
        for signal_id in model.processed_signals:
            node_id = f"signal:{signal_id}"
            self.add_node(EvidenceNode(
                node_id=node_id,
                node_type=EvidenceNodeType.SIGNAL,
                label=f"Signal {str(signal_id)[:8]}",
                artifact_ref="",
                provider="",
            ))

        # 2. Add learning object nodes and connect to receipts/signals
        for lo_id, lo in model.learning_objects.items():
            lo_node_id = f"lo:{lo_id}"
            self.add_node(EvidenceNode(
                node_id=lo_node_id,
                node_type=EvidenceNodeType.LEARNING_OBJECT,
                label=lo.title,
                provider=",".join(lo.providers),
                metadata={"type": lo.type.value, "confidence": lo.confidence},
            ))

            # Connect LO to its signals via receipts
            for chain in model.receipt_chains.values():
                for receipt in chain.receipts:
                    if receipt.oem_target == str(lo_id):
                        receipt_node_id = f"receipt:{receipt.receipt_id}"
                        signal_node_id = f"signal:{receipt.signal_id}"

                        # Add receipt node if not exists
                        if receipt_node_id not in self.nodes:
                            self.add_node(EvidenceNode(
                                node_id=receipt_node_id,
                                node_type=EvidenceNodeType.RECEIPT,
                                label=f"Receipt: {receipt.oem_change}",
                                artifact_ref=receipt.signal_artifact,
                                provider=receipt.signal_provider,
                                timestamp=receipt.signal_timestamp,
                                metadata={
                                    "signal_type": receipt.signal_type,
                                    "actor": receipt.signal_actor,
                                    "oem_change": receipt.oem_change,
                                },
                            ))

                        # Connect LO → Receipt → Signal
                        self.add_edge(lo_node_id, receipt_node_id, EvidenceEdgeType.CAUSED)
                        self.add_edge(receipt_node_id, signal_node_id, EvidenceEdgeType.PRODUCED)

                        # Update signal node with artifact info
                        if signal_node_id in self.nodes:
                            sig_node = self.nodes[signal_node_id]
                            sig_node.artifact_ref = receipt.signal_artifact
                            sig_node.provider = receipt.signal_provider
                            sig_node.label = f"{receipt.signal_provider}:{receipt.signal_type}"

        # 3. Add pattern nodes and connect to LOs
        for pattern in model.pattern_detector.patterns:
            pattern_node_id = f"pattern:{pattern.pattern_id}"
            self.add_node(EvidenceNode(
                node_id=pattern_node_id,
                node_type=EvidenceNodeType.PATTERN,
                label=pattern.description,
                metadata={
                    "type": pattern.type.value,
                    "strength": pattern.strength,
                    "coverage": pattern.coverage,
                },
            ))

            for lo_id in pattern.learning_object_ids:
                lo_node_id = f"lo:{lo_id}"
                if lo_node_id in self.nodes:
                    self.add_edge(
                        pattern_node_id, lo_node_id,
                        EvidenceEdgeType.CONTRIBUTED_TO,
                        weight=pattern.strength,
                    )

        # 4. Add law nodes and connect to patterns and signals
        for code, law in model.laws.items():
            law_node_id = f"law:{code}"
            self.add_node(EvidenceNode(
                node_id=law_node_id,
                node_type=EvidenceNodeType.LAW,
                label=f"{code}: {law.statement}",
                metadata={
                    "confidence": law.confidence,
                    "status": law.status.value,
                    "validated_runtimes": law.validated_runtimes,
                    "failed_runtimes": law.failed_runtimes,
                },
            ))

            # Connect law to its patterns
            for pattern_id in law.pattern_ids:
                pattern_node_id = f"pattern:{pattern_id}"
                if pattern_node_id in self.nodes:
                    self.add_edge(law_node_id, pattern_node_id, EvidenceEdgeType.PROMOTED_TO)

            # Connect law to its validating/contradicting signals
            for signal_id in law.signal_ids:
                signal_node_id = f"signal:{signal_id}"
                if signal_node_id in self.nodes:
                    # Check if this signal validated or contradicted
                    # (simplified: assume validation unless we have contradict metadata)
                    self.add_edge(
                        law_node_id, signal_node_id,
                        EvidenceEdgeType.VALIDATED,
                        weight=law.confidence,
                    )

        # 5. Add recommendation nodes and connect to laws
        dec_engine = DecisionEngine(model)
        for rec in dec_engine.get_recommendations():
            rec_node_id = f"rec:{rec.rec_id}"
            self.add_node(EvidenceNode(
                node_id=rec_node_id,
                node_type=EvidenceNodeType.RECOMMENDATION,
                label=rec.title,
                metadata={
                    "confidence": rec.confidence,
                    "recommendation": rec.recommendation,
                    "decision_question": rec.decision_question,
                    "urgency": rec.urgency,
                },
            ))

            # Connect recommendation to its linked laws
            for law_code in rec.linked_laws:
                law_node_id = f"law:{law_code}"
                if law_node_id in self.nodes:
                    self.add_edge(
                        rec_node_id, law_node_id,
                        EvidenceEdgeType.DERIVED_FROM,
                        weight=rec.confidence,
                    )

    def get_node(self, node_id: str) -> EvidenceNode | None:
        return self.nodes.get(node_id)

    def get_outgoing(self, node_id: str) -> list[tuple[EvidenceEdge, str]]:
        return self._outgoing.get(node_id, [])

    def get_incoming(self, node_id: str) -> list[tuple[EvidenceEdge, str]]:
        return self._incoming.get(node_id, [])

    def node_count(self) -> int:
        return len(self.nodes)

    def edge_count(self) -> int:
        return len(self.edges)

    def summary(self) -> dict[str, Any]:
        """Get a summary of the graph."""
        type_counts: dict[str, int] = defaultdict(int)
        for node in self.nodes.values():
            type_counts[node.node_type.value] += 1
        return {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "nodes_by_type": dict(type_counts),
        }
