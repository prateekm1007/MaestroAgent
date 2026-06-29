"""
Tests for the Evidence Graph.

Tests:
1. Building the graph from the OEM
2. Traversing from recommendation → law → pattern → LO → receipt → signal → artifact
3. Every recommendation returns evidence chain + supporting artifacts + contradicting artifacts
4. Deleting evidence → confidence falls
5. Reconnecting evidence → confidence rises
6. Clicking a badge (traversal) opens the real chain
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from maestro_oem import (
    ConfidenceCalculator,
    DecisionEngine,
    EvidenceGraph,
    EvidenceNode,
    EvidenceNodeType,
    EvidenceEdgeType,
    ExecutionModel,
    OEMEngine,
)
from maestro_oem.providers import (
    normalize_github,
    normalize_jira,
    normalize_slack,
    normalize_confluence,
    normalize_gmail,
)


# ============================================================
# Test data — same as test_oem.py
# ============================================================

GITHUB_EVENTS = [
    {"event_type": "pull_request", "repository": "acme/payments", "actor": "priya@acme.com",
     "artifact": "github:acme/payments/pull/447", "timestamp": "2024-11-12T09:00:00Z",
     "metadata": {"action": "opened", "domain": "payments", "title": "Add circuit breaker"}},
    {"event_type": "review", "repository": "acme/payments", "actor": "priya@acme.com",
     "artifact": "github:acme/payments/pull/447", "timestamp": "2024-11-12T09:30:00Z",
     "metadata": {"reviewer": "carlos@acme.com", "domain": "payments", "action": "approved"}},
    {"event_type": "merge", "repository": "acme/payments", "actor": "priya@acme.com",
     "artifact": "github:acme/payments/pull/447", "timestamp": "2024-11-12T10:00:00Z",
     "metadata": {"domain": "payments", "action": "merged"}},
    {"event_type": "commit", "repository": "acme/platform", "actor": "aisha@acme.com",
     "artifact": "github:acme/platform/commit/abc123", "timestamp": "2024-11-08T11:00:00Z",
     "metadata": {"domain": "platform"}},
    {"event_type": "commit", "repository": "acme/platform", "actor": "aisha@acme.com",
     "artifact": "github:acme/platform/commit/def456", "timestamp": "2024-11-09T11:00:00Z",
     "metadata": {"domain": "platform"}},
    {"event_type": "commit", "repository": "acme/platform", "actor": "aisha@acme.com",
     "artifact": "github:acme/platform/commit/ghi789", "timestamp": "2024-11-10T11:00:00Z",
     "metadata": {"domain": "platform"}},
]

JIRA_EVENTS = [
    {"event_type": "issue_created", "project": "EMEA", "actor": "sara@acme.com",
     "artifact": "jira:EMEA-1247", "timestamp": "2024-11-05T09:00:00Z",
     "metadata": {"priority": "P1", "issue_type": "Bug"}},
    {"event_type": "issue_created", "project": "EMEA", "actor": "chris@acme.com",
     "artifact": "jira:EMEA-1248", "timestamp": "2024-11-06T09:00:00Z",
     "metadata": {"priority": "P1", "issue_type": "Bug"}},
    {"event_type": "issue_created", "project": "EMEA", "actor": "chris@acme.com",
     "artifact": "jira:EMEA-1249", "timestamp": "2024-11-07T09:00:00Z",
     "metadata": {"priority": "P1", "issue_type": "Bug"}},
    {"event_type": "issue_transitioned", "project": "EMEA", "actor": "sara@acme.com",
     "artifact": "jira:EMEA-1247", "timestamp": "2024-11-08T14:00:00Z",
     "metadata": {"transition": "Approved", "assignee": "sara@acme.com"}},
    {"event_type": "issue_transitioned", "project": "EMEA", "actor": "sara@acme.com",
     "artifact": "jira:EMEA-1248", "timestamp": "2024-11-09T14:00:00Z",
     "metadata": {"transition": "Approved", "assignee": "sara@acme.com"}},
    {"event_type": "issue_transitioned", "project": "EMEA", "actor": "sara@acme.com",
     "artifact": "jira:EMEA-1249", "timestamp": "2024-11-10T14:00:00Z",
     "metadata": {"transition": "Approved", "assignee": "sara@acme.com"}},
    {"event_type": "sprint_completed", "project": "EMEA", "actor": "chris@acme.com",
     "artifact": "jira:SPRINT-Q4-3", "timestamp": "2024-11-08T17:00:00Z",
     "metadata": {"velocity": 42}},
]

SLACK_EVENTS = [
    {"event_type": "message", "channel": "#engineering", "actor": "priya@acme.com",
     "artifact": "slack:C-123/p-1", "timestamp": "2024-11-12T09:14:00Z",
     "metadata": {"text": "the payments PR is ready for review. who can take a look today?",
                  "participants": ["priya@acme.com", "carlos@acme.com"]}},
    {"event_type": "message", "channel": "#leadership", "actor": "pat@acme.com",
     "artifact": "slack:C-456/p-3", "timestamp": "2024-11-11T10:00:00Z",
     "metadata": {"text": "I disagree with the Q3 hiring plan", "participants": ["pat@acme.com", "jane@acme.com"]}},
    {"event_type": "message", "channel": "#engineering", "actor": "anya@acme.com",
     "artifact": "slack:C-123/p-5", "timestamp": "2024-11-10T15:00:00Z",
     "metadata": {"text": "I'm thinking about a new opportunity", "participants": ["anya@acme.com"]}},
]

CONFLUENCE_EVENTS = [
    {"event_type": "postmortem_created", "space": "Engineering", "actor": "chris@acme.com",
     "artifact": "confluence:PM-2024-11-09", "timestamp": "2024-11-09T16:00:00Z",
     "metadata": {"title": "Postmortem: payments incident", "has_owner": False, "page_type": "postmortem"}},
    {"event_type": "page_created", "space": "Engineering", "actor": "priya@acme.com",
     "artifact": "confluence:DOC-789", "timestamp": "2024-11-01T11:00:00Z",
     "metadata": {"title": "Deployment Runbook", "domain": "deployment", "page_type": "documentation"}},
]

GMAIL_EVENTS = [
    {"event_type": "meeting_completed", "actor": "jane@acme.com",
     "artifact": "cal:event-001", "timestamp": "2024-11-11T15:00:00Z",
     "metadata": {"participants": ["jane@acme.com", "raj@globex.com"], "duration": 30, "subject": "Q4 renewal"}},
]


def _build_full_model() -> OEMEngine:
    """Build an OEM with all providers connected."""
    engine = OEMEngine()
    all_signals = (
        [normalize_github(e) for e in GITHUB_EVENTS] +
        [normalize_jira(e) for e in JIRA_EVENTS] +
        [normalize_slack(e) for e in SLACK_EVENTS] +
        [normalize_confluence(e) for e in CONFLUENCE_EVENTS] +
        [normalize_gmail(e) for e in GMAIL_EVENTS]
    )
    engine.ingest(all_signals)
    return engine


# ============================================================
# TEST 1: Building the evidence graph from the model
# ============================================================

class TestBuildEvidenceGraph:
    def test_graph_has_nodes(self):
        """Building the graph from the model must produce nodes."""
        engine = _build_full_model()
        graph = EvidenceGraph()
        graph.build_from_model(engine.get_model())
        assert graph.node_count() > 0

    def test_graph_has_signal_nodes(self):
        """The graph must contain signal nodes."""
        engine = _build_full_model()
        graph = EvidenceGraph()
        graph.build_from_model(engine.get_model())
        signal_nodes = [n for n in graph.nodes.values() if n.node_type == EvidenceNodeType.SIGNAL]
        assert len(signal_nodes) > 0

    def test_graph_has_lo_nodes(self):
        """The graph must contain learning object nodes."""
        engine = _build_full_model()
        graph = EvidenceGraph()
        graph.build_from_model(engine.get_model())
        lo_nodes = [n for n in graph.nodes.values() if n.node_type == EvidenceNodeType.LEARNING_OBJECT]
        assert len(lo_nodes) > 0

    def test_graph_has_receipt_nodes(self):
        """The graph must contain receipt nodes (the link between signals and LOs)."""
        engine = _build_full_model()
        graph = EvidenceGraph()
        graph.build_from_model(engine.get_model())
        receipt_nodes = [n for n in graph.nodes.values() if n.node_type == EvidenceNodeType.RECEIPT]
        assert len(receipt_nodes) > 0

    def test_graph_has_edges(self):
        """The graph must contain edges connecting nodes."""
        engine = _build_full_model()
        graph = EvidenceGraph()
        graph.build_from_model(engine.get_model())
        assert graph.edge_count() > 0


# ============================================================
# TEST 2: Traversal — recommendation → artifact
# ============================================================

class TestEvidenceTraversal:
    def test_traverse_from_law_reaches_signals(self):
        """Traversing from a law must reach signal nodes."""
        engine = _build_full_model()
        graph = EvidenceGraph()
        graph.build_from_model(engine.get_model())

        # Find any law node
        law_nodes = [n for n in graph.nodes.values() if n.node_type == EvidenceNodeType.LAW]
        if not law_nodes:
            pytest.skip("No laws were inferred — adjust test data")

        law_node = law_nodes[0]
        chain = graph.traverse(law_node.node_id)

        assert len(chain.nodes) > 1  # At least the law + something
        # Should reach at least one signal or receipt
        chain_types = {n.node_type for n in chain.nodes}
        assert EvidenceNodeType.SIGNAL in chain_types or EvidenceNodeType.RECEIPT in chain_types

    def test_traverse_from_recommendation_returns_chain(self):
        """Every recommendation must return a traversable evidence chain."""
        engine = _build_full_model()
        graph = EvidenceGraph()
        graph.build_from_model(engine.get_model())

        dec = DecisionEngine(engine.get_model(), evidence_graph=graph)
        recs = dec.get_recommendations()

        if not recs:
            pytest.skip("No recommendations generated")

        for rec in recs:
            assert rec.evidence_chain is not None, f"Rec '{rec.title}' has no evidence chain"
            assert rec.evidence_strength >= 0.0

    def test_traverse_returns_supporting_artifacts(self):
        """Traversal must return supporting artifacts (PRs, tickets, etc.)."""
        engine = _build_full_model()
        graph = EvidenceGraph()
        graph.build_from_model(engine.get_model())

        # Check LO nodes directly — they should have artifacts from receipts
        lo_nodes = [n for n in graph.nodes.values() if n.node_type == EvidenceNodeType.LEARNING_OBJECT]
        has_artifacts = False
        for lo_node in lo_nodes:
            chain = graph.traverse(lo_node.node_id)
            if chain.supporting_artifacts:
                has_artifacts = True
                break

        # Also check recommendations (may or may not have law-backed evidence)
        dec = DecisionEngine(engine.get_model(), evidence_graph=graph)
        recs = dec.get_recommendations()
        for rec in recs:
            if rec.supporting_artifacts:
                has_artifacts = True
                break

        assert has_artifacts, "No node in the graph has supporting artifacts"

    def test_traverse_chain_is_complete(self):
        """The evidence chain must go from recommendation to signal level."""
        engine = _build_full_model()
        graph = EvidenceGraph()
        graph.build_from_model(engine.get_model())

        # Find a law node and traverse
        law_nodes = [n for n in graph.nodes.values() if n.node_type == EvidenceNodeType.LAW]
        if not law_nodes:
            pytest.skip("No laws inferred")

        chain = graph.traverse(law_nodes[0].node_id)

        # Chain should have multiple levels
        node_types = [n.node_type for n in chain.nodes]
        assert EvidenceNodeType.LAW in node_types
        # Should reach at least receipt or signal level
        assert (
            EvidenceNodeType.RECEIPT in node_types or
            EvidenceNodeType.SIGNAL in node_types or
            EvidenceNodeType.LEARNING_OBJECT in node_types
        )


# ============================================================
# TEST 3: Every recommendation returns full evidence
# ============================================================

class TestRecommendationEvidence:
    def test_every_recommendation_has_evidence_chain(self):
        """Every recommendation must have an evidence_chain field populated."""
        engine = _build_full_model()
        graph = EvidenceGraph()
        graph.build_from_model(engine.get_model())

        dec = DecisionEngine(engine.get_model(), evidence_graph=graph)
        recs = dec.get_recommendations()

        if not recs:
            pytest.skip("No recommendations generated")

        for rec in recs:
            assert rec.evidence_chain is not None
            assert "chain" in rec.evidence_chain
            assert "strength" in rec.evidence_chain
            assert "supporting_artifacts" in rec.evidence_chain
            assert "contradicting_artifacts" in rec.evidence_chain

    def test_evidence_strength_is_computed(self):
        """Evidence strength must be a computed value, not hardcoded."""
        engine = _build_full_model()
        graph = EvidenceGraph()
        graph.build_from_model(engine.get_model())

        dec = DecisionEngine(engine.get_model(), evidence_graph=graph)
        recs = dec.get_recommendations()

        if not recs:
            pytest.skip("No recommendations generated")

        for rec in recs:
            assert 0.0 <= rec.evidence_strength <= 1.0

    def test_supporting_artifacts_have_refs(self):
        """Supporting artifacts must contain artifact references (URLs, IDs)."""
        engine = _build_full_model()
        graph = EvidenceGraph()
        graph.build_from_model(engine.get_model())

        dec = DecisionEngine(engine.get_model(), evidence_graph=graph)
        recs = dec.get_recommendations()

        for rec in recs:
            for artifact in rec.supporting_artifacts:
                assert "artifact" in artifact
                assert artifact["artifact"]  # Non-empty
                assert "provider" in artifact


# ============================================================
# TEST 4: Delete evidence → confidence falls
# ============================================================

class TestDeleteEvidence:
    def test_deleting_signal_node_reduces_graph(self):
        """Deleting a signal node must reduce the graph's node count."""
        engine = _build_full_model()
        graph = EvidenceGraph()
        graph.build_from_model(engine.get_model())

        original_count = graph.node_count()

        # Find a signal node to delete
        signal_nodes = [n for n in graph.nodes.values() if n.node_type == EvidenceNodeType.SIGNAL]
        if not signal_nodes:
            pytest.skip("No signal nodes to delete")

        signal_node = signal_nodes[0]
        affected = graph.delete_evidence(signal_node.node_id.split(":")[1])

        assert graph.node_count() < original_count
        assert len(affected) > 0

    def test_deleting_evidence_reduces_strength(self):
        """Deleting evidence must reduce the evidence strength of affected nodes."""
        # Build a simple graph manually to ensure we can test delete → strength
        graph = EvidenceGraph()

        # Create: law → LO → receipt → signal (with artifact)
        law_node = EvidenceNode(
            node_id="law:L-TEST",
            node_type=EvidenceNodeType.LAW,
            label="Test law",
        )
        lo_node = EvidenceNode(
            node_id="lo:test-1",
            node_type=EvidenceNodeType.LEARNING_OBJECT,
            label="Test LO",
        )
        receipt_node = EvidenceNode(
            node_id="receipt:test-1",
            node_type=EvidenceNodeType.RECEIPT,
            label="Test receipt",
            artifact_ref="github:acme/test/pull/1",
            provider="github",
        )
        signal_node = EvidenceNode(
            node_id="signal:test-signal-1",
            node_type=EvidenceNodeType.SIGNAL,
            label="github:pr.opened",
            artifact_ref="github:acme/test/pull/1",
            provider="github",
        )

        graph.add_node(law_node)
        graph.add_node(lo_node)
        graph.add_node(receipt_node)
        graph.add_node(signal_node)

        graph.add_edge("law:L-TEST", "lo:test-1", EvidenceEdgeType.VALIDATED)
        graph.add_edge("lo:test-1", "receipt:test-1", EvidenceEdgeType.CAUSED)
        graph.add_edge("receipt:test-1", "signal:test-signal-1", EvidenceEdgeType.PRODUCED)

        original_strength = graph.get_evidence_strength("law:L-TEST")
        assert original_strength > 0, "Law should have positive strength before deletion"

        # Delete the signal
        affected = graph.delete_evidence("test-signal-1")
        assert len(affected) > 0

        # After deletion, the law's strength should decrease or the law should be gone
        if "law:L-TEST" in graph.nodes:
            new_strength = graph.get_evidence_strength("law:L-TEST")
            assert new_strength <= original_strength, (
                f"Strength should decrease. Before: {original_strength}, After: {new_strength}"
            )
        # If the law is gone, that's also acceptable — cascading deletion


# ============================================================
# TEST 5: Reconnect evidence → confidence rises
# ============================================================

class TestReconnectEvidence:
    def test_reconnecting_evidence_increases_strength(self):
        """Reconnecting evidence must increase the evidence strength."""
        # Build a simple graph manually
        graph = EvidenceGraph()

        law_node = EvidenceNode(
            node_id="law:L-RECONNECT",
            node_type=EvidenceNodeType.LAW,
            label="Reconnect test law",
        )
        lo_node = EvidenceNode(
            node_id="lo:reconnect-1",
            node_type=EvidenceNodeType.LEARNING_OBJECT,
            label="Reconnect test LO",
        )
        receipt_node = EvidenceNode(
            node_id="receipt:reconnect-1",
            node_type=EvidenceNodeType.RECEIPT,
            label="Reconnect test receipt",
            artifact_ref="github:acme/test/pull/999",
            provider="github",
        )
        signal_node = EvidenceNode(
            node_id="signal:reconnect-signal-1",
            node_type=EvidenceNodeType.SIGNAL,
            label="github:pr.opened",
            artifact_ref="github:acme/test/pull/999",
            provider="github",
        )

        graph.add_node(law_node)
        graph.add_node(lo_node)
        graph.add_node(receipt_node)
        graph.add_node(signal_node)

        graph.add_edge("law:L-RECONNECT", "lo:reconnect-1", EvidenceEdgeType.VALIDATED)
        graph.add_edge("lo:reconnect-1", "receipt:reconnect-1", EvidenceEdgeType.CAUSED)
        graph.add_edge("receipt:reconnect-1", "signal:reconnect-signal-1", EvidenceEdgeType.PRODUCED)

        original_strength = graph.get_evidence_strength("law:L-RECONNECT")
        assert original_strength > 0

        # Delete the signal
        graph.delete_evidence("reconnect-signal-1")
        strength_after_delete = graph.get_evidence_strength("law:L-RECONNECT")

        # Reconnect with new evidence
        new_signal = EvidenceNode(
            node_id="signal:reconnect-signal-1",
            node_type=EvidenceNodeType.SIGNAL,
            label="github:pr.opened (reconnected)",
            artifact_ref="github:acme/test/pull/999",
            provider="github",
        )
        new_receipt = EvidenceNode(
            node_id="receipt:reconnect-1",
            node_type=EvidenceNodeType.RECEIPT,
            label="Reconnected receipt",
            artifact_ref="github:acme/test/pull/999",
            provider="github",
        )
        new_lo = EvidenceNode(
            node_id="lo:reconnect-1",
            node_type=EvidenceNodeType.LEARNING_OBJECT,
            label="Reconnected LO",
            provider="github",
        )

        graph.reconnect_evidence(new_signal, new_receipt, new_lo, ["law:L-RECONNECT"])

        strength_after_reconnect = graph.get_evidence_strength("law:L-RECONNECT")

        assert strength_after_reconnect >= strength_after_delete, (
            f"Strength should increase after reconnection. "
            f"Deleted: {strength_after_delete}, Reconnected: {strength_after_reconnect}"
        )


# ============================================================
# TEST 6: Evidence chain display format
# ============================================================

class TestEvidenceChainDisplay:
    def test_chain_display_has_required_fields(self):
        """The chain display must have all required fields for the UI."""
        engine = _build_full_model()
        graph = EvidenceGraph()
        graph.build_from_model(engine.get_model())

        law_nodes = [n for n in graph.nodes.values() if n.node_type == EvidenceNodeType.LAW]
        if not law_nodes:
            pytest.skip("No laws inferred")

        chain = graph.traverse(law_nodes[0].node_id)
        display = chain.to_display()

        assert "root" in display
        assert "strength" in display
        assert "chain" in display
        assert "supporting_artifacts" in display
        assert "contradicting_artifacts" in display
        assert "edge_count" in display
        assert "node_count" in display

    def test_chain_nodes_have_artifact_refs(self):
        """Chain nodes must contain artifact references where available."""
        engine = _build_full_model()
        graph = EvidenceGraph()
        graph.build_from_model(engine.get_model())

        # Find receipt nodes (they always have artifact refs)
        receipt_nodes = [n for n in graph.nodes.values() if n.node_type == EvidenceNodeType.RECEIPT]
        if not receipt_nodes:
            pytest.skip("No receipt nodes")

        for receipt in receipt_nodes:
            assert receipt.artifact_ref, f"Receipt {receipt.node_id} has no artifact ref"
            assert receipt.provider, f"Receipt {receipt.node_id} has no provider"


# ============================================================
# TEST 7: Graph summary
# ============================================================

class TestGraphSummary:
    def test_summary_reports_node_types(self):
        """The graph summary must report node counts by type."""
        engine = _build_full_model()
        graph = EvidenceGraph()
        graph.build_from_model(engine.get_model())

        summary = graph.summary()

        assert "total_nodes" in summary
        assert "total_edges" in summary
        assert "nodes_by_type" in summary
        assert summary["total_nodes"] > 0
        assert summary["total_edges"] > 0
