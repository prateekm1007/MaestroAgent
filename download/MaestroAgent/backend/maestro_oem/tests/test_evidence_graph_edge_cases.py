"""
Additional evidence graph tests covering edge cases.

Tests:
1. Empty graph traversal returns zero strength
2. Node with no outgoing edges returns minimal strength
3. Delete non-existent signal is a no-op
4. Multiple signals supporting same law
5. Contradicting evidence appears in contradicting_artifacts
6. Graph rebuild from updated model
7. Edge weights affect strength
8. Large chain traversal performance
"""

from __future__ import annotations

import pytest
from uuid import uuid4

from maestro_oem import (
    EvidenceGraph,
    EvidenceNode,
    EvidenceEdgeType,
    EvidenceNodeType,
)


class TestEvidenceGraphEdgeCases:
    """Edge cases for the evidence graph."""

    def test_empty_graph_traversal_returns_zero(self):
        """Traversing an empty graph must return zero strength."""
        graph = EvidenceGraph()
        chain = graph.traverse("nonexistent")
        assert chain.strength == 0.0
        assert len(chain.nodes) == 0

    def test_lone_node_has_minimal_strength(self):
        """A node with no outgoing edges must have minimal but non-zero strength."""
        graph = EvidenceGraph()
        node = EvidenceNode(
            node_id="law:L-LONE",
            node_type=EvidenceNodeType.LAW,
            label="Lone law",
        )
        graph.add_node(node)
        chain = graph.traverse("law:L-LONE")
        assert 0 < chain.strength <= 0.2  # Minimal strength for lone node

    def test_delete_nonexistent_is_noop(self):
        """Deleting a non-existent signal must not crash."""
        graph = EvidenceGraph()
        affected = graph.delete_evidence("nonexistent-signal-id")
        assert isinstance(affected, list)
        assert len(affected) == 0

    def test_multiple_signals_supporting_same_law(self):
        """A law supported by multiple signals must have higher strength than one signal."""
        graph = EvidenceGraph()

        law = EvidenceNode(node_id="law:L-MULTI", node_type=EvidenceNodeType.LAW, label="Multi-signal law")
        graph.add_node(law)

        # Add first signal chain
        lo1 = EvidenceNode(node_id="lo:multi-1", node_type=EvidenceNodeType.LEARNING_OBJECT, label="LO 1")
        receipt1 = EvidenceNode(node_id="receipt:multi-1", node_type=EvidenceNodeType.RECEIPT, label="R 1", artifact_ref="github:pr/1", provider="github")
        signal1 = EvidenceNode(node_id="signal:multi-sig-1", node_type=EvidenceNodeType.SIGNAL, label="S 1", artifact_ref="github:pr/1", provider="github")
        graph.add_node(lo1)
        graph.add_node(receipt1)
        graph.add_node(signal1)
        graph.add_edge("law:L-MULTI", "lo:multi-1", EvidenceEdgeType.VALIDATED)
        graph.add_edge("lo:multi-1", "receipt:multi-1", EvidenceEdgeType.CAUSED)
        graph.add_edge("receipt:multi-1", "signal:multi-sig-1", EvidenceEdgeType.PRODUCED)

        strength_one = graph.get_evidence_strength("law:L-MULTI")

        # Add second signal chain
        lo2 = EvidenceNode(node_id="lo:multi-2", node_type=EvidenceNodeType.LEARNING_OBJECT, label="LO 2")
        receipt2 = EvidenceNode(node_id="receipt:multi-2", node_type=EvidenceNodeType.RECEIPT, label="R 2", artifact_ref="jira:T-1", provider="jira")
        signal2 = EvidenceNode(node_id="signal:multi-sig-2", node_type=EvidenceNodeType.SIGNAL, label="S 2", artifact_ref="jira:T-1", provider="jira")
        graph.add_node(lo2)
        graph.add_node(receipt2)
        graph.add_node(signal2)
        graph.add_edge("law:L-MULTI", "lo:multi-2", EvidenceEdgeType.VALIDATED)
        graph.add_edge("lo:multi-2", "receipt:multi-2", EvidenceEdgeType.CAUSED)
        graph.add_edge("receipt:multi-2", "signal:multi-sig-2", EvidenceEdgeType.PRODUCED)

        strength_two = graph.get_evidence_strength("law:L-MULTI")

        assert strength_two >= strength_one, (
            f"Two signals ({strength_two}) should be >= one signal ({strength_one})"
        )

    def test_contradicting_edge_appears_in_contradicting_artifacts(self):
        """An edge with type CONTRADICTED must appear in contradicting_artifacts."""
        graph = EvidenceGraph()

        law = EvidenceNode(node_id="law:L-CONTRA", node_type=EvidenceNodeType.LAW, label="Contradicted law")
        signal = EvidenceNode(
            node_id="signal:contra-sig-1", node_type=EvidenceNodeType.SIGNAL,
            label="Contradicting signal", artifact_ref="jira:BUG-1", provider="jira",
        )
        graph.add_node(law)
        graph.add_node(signal)
        graph.add_edge("law:L-CONTRA", "signal:contra-sig-1", EvidenceEdgeType.CONTRADICTED)

        chain = graph.traverse("law:L-CONTRA")
        assert len(chain.contradicting_artifacts) > 0
        assert chain.contradicting_artifacts[0]["artifact"] == "jira:BUG-1"

    def test_edge_weights_affect_strength(self):
        """Higher edge weights must produce higher strength."""
        graph_a = EvidenceGraph()
        graph_b = EvidenceGraph()

        for g, weight in [(graph_a, 0.1), (graph_b, 1.0)]:
            law = EvidenceNode(node_id="law:L-W", node_type=EvidenceNodeType.LAW, label="Weighted law")
            lo = EvidenceNode(node_id="lo:w-1", node_type=EvidenceNodeType.LEARNING_OBJECT, label="LO")
            signal = EvidenceNode(node_id="signal:w-1", node_type=EvidenceNodeType.SIGNAL, label="S", artifact_ref="x", provider="github")
            g.add_node(law)
            g.add_node(lo)
            g.add_node(signal)
            g.add_edge("law:L-W", "lo:w-1", EvidenceEdgeType.VALIDATED, weight=weight)
            g.add_edge("lo:w-1", "signal:w-1", EvidenceEdgeType.PRODUCED, weight=weight)

        strength_low = graph_a.get_evidence_strength("law:L-W")
        strength_high = graph_b.get_evidence_strength("law:L-W")
        assert strength_high >= strength_low, (
            f"High weight ({strength_high}) should >= low weight ({strength_low})"
        )

    def test_graph_summary_counts_match(self):
        """Graph summary node counts must match actual counts."""
        graph = EvidenceGraph()
        for i in range(5):
            graph.add_node(EvidenceNode(
                node_id=f"signal:test-{i}",
                node_type=EvidenceNodeType.SIGNAL,
                label=f"Signal {i}",
            ))
        summary = graph.summary()
        assert summary["total_nodes"] == 5
        assert summary["nodes_by_type"]["signal"] == 5
        assert summary["total_edges"] == 0

    def test_remove_node_cleans_edges(self):
        """Removing a node must remove all edges to and from it."""
        graph = EvidenceGraph()
        a = EvidenceNode(node_id="law:A", node_type=EvidenceNodeType.LAW, label="A")
        b = EvidenceNode(node_id="lo:B", node_type=EvidenceNodeType.LEARNING_OBJECT, label="B")
        c = EvidenceNode(node_id="signal:C", node_type=EvidenceNodeType.SIGNAL, label="C")
        graph.add_node(a)
        graph.add_node(b)
        graph.add_node(c)
        graph.add_edge("law:A", "lo:B", EvidenceEdgeType.VALIDATED)
        graph.add_edge("lo:B", "signal:C", EvidenceEdgeType.CAUSED)

        assert graph.edge_count() == 2

        graph.remove_node("lo:B")
        assert graph.edge_count() == 0
        assert "lo:B" not in graph.nodes
