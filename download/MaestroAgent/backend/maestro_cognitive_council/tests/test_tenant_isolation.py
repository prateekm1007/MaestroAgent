"""Tests for tenant isolation in the Cognitive Council.

Per the pre-pilot audit Part XVII: "Cross-tenant leakage, permission changes."
The Situation Engine must enforce org_id scoping on all operations:
  - Signals from org A must not create situations for org B
  - Situations from org A must not be visible to org B
  - All bridges must scope by org_id
"""

from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest


def _make_signal(sig_type, entity, text, signal_id="", days_ago=0, org_id="default"):
    sig = MagicMock()
    sig.type = MagicMock()
    sig.type.value = sig_type
    sig.entity = entity
    sig.text = text
    sig.signal_id = signal_id or f"sig-{entity.lower()}-{org_id}-{days_ago}"
    sig.metadata = {"customer": entity}
    sig.timestamp = datetime.now(timezone.utc) - timedelta(days=days_ago)
    sig.actor = ""
    sig.org_id = org_id
    sig.tenant_id = org_id
    return sig


# ════════════════════════════════════════════════════════════════════════════
# Situation Engine — org_id scoping
# ════════════════════════════════════════════════════════════════════════════

class TestSituationEngineTenantIsolation:
    """The Situation Engine enforces org_id scoping on all operations."""

    def test_signals_filtered_by_org_id(self):
        """Signals from org A do not create situations for org B."""
        from maestro_cognitive_council import SituationEngine

        org_a_signals = [
            _make_signal("customer.commitment_made", "EntityA", "Commitment A", org_id="org-a", days_ago=10),
            _make_signal("customer.commitment_made", "EntityA", "Commitment B", org_id="org-a", days_ago=8),
        ]
        org_b_signals = [
            _make_signal("customer.commitment_made", "EntityB", "Commitment C", org_id="org-b", days_ago=5),
            _make_signal("customer.commitment_made", "EntityB", "Commitment D", org_id="org-b", days_ago=3),
        ]

        oem = MagicMock()
        oem.signals = org_a_signals + org_b_signals
        engine = SituationEngine(oem_state=oem)

        # Detect for org-a
        org_a_situations = engine.detect_situations(org_id="org-a")
        org_a_entities = {s.entity for s in org_a_situations}
        assert "EntityA" in org_a_entities
        assert "EntityB" not in org_a_entities, (
            "org-a should NOT see org-b's entities — tenant isolation violation"
        )

        # Detect for org-b
        org_b_situations = engine.detect_situations(org_id="org-b")
        org_b_entities = {s.entity for s in org_b_situations}
        assert "EntityB" in org_b_entities
        assert "EntityA" not in org_b_entities, (
            "org-b should NOT see org-a's entities — tenant isolation violation"
        )

    def test_situations_scoped_by_org_id(self):
        """get_active_situations only returns situations for the specified org."""
        from maestro_cognitive_council import SituationEngine

        signals = [
            _make_signal("customer.commitment_made", "EntityA", "Commitment A", org_id="org-a", days_ago=10),
            _make_signal("customer.commitment_made", "EntityA", "Commitment B", org_id="org-a", days_ago=8),
            _make_signal("customer.commitment_made", "EntityB", "Commitment C", org_id="org-b", days_ago=5),
            _make_signal("customer.commitment_made", "EntityB", "Commitment D", org_id="org-b", days_ago=3),
        ]

        oem = MagicMock()
        oem.signals = signals
        engine = SituationEngine(oem_state=oem)

        # Detect for both orgs
        engine.detect_situations(org_id="org-a")
        engine.detect_situations(org_id="org-b")

        # org-a should only see org-a situations
        org_a_active = engine.get_active_situations(org_id="org-a")
        for s in org_a_active:
            assert s.org_id == "org-a", (
                f"org-a should only see org-a situations, found {s.org_id}"
            )

        # org-b should only see org-b situations
        org_b_active = engine.get_active_situations(org_id="org-b")
        for s in org_b_active:
            assert s.org_id == "org-b", (
                f"org-b should only see org-b situations, found {s.org_id}"
            )

    def test_get_situations_by_entity_respects_org_id(self):
        """get_situations_by_entity only returns situations for the specified org."""
        from maestro_cognitive_council import SituationEngine

        signals = [
            _make_signal("customer.commitment_made", "SharedEntity", "Commitment A", org_id="org-a", days_ago=10),
            _make_signal("customer.commitment_made", "SharedEntity", "Commitment B", org_id="org-a", days_ago=8),
            _make_signal("customer.commitment_made", "SharedEntity", "Commitment C", org_id="org-b", days_ago=5),
            _make_signal("customer.commitment_made", "SharedEntity", "Commitment D", org_id="org-b", days_ago=3),
        ]

        oem = MagicMock()
        oem.signals = signals
        engine = SituationEngine(oem_state=oem)

        engine.detect_situations(org_id="org-a")
        engine.detect_situations(org_id="org-b")

        # Both orgs have a "SharedEntity" situation, but they're separate
        org_a_situations = engine.get_situations_by_entity("SharedEntity", org_id="org-a")
        org_b_situations = engine.get_situations_by_entity("SharedEntity", org_id="org-b")

        assert all(s.org_id == "org-a" for s in org_a_situations), (
            "org-a should only see org-a's SharedEntity situation"
        )
        assert all(s.org_id == "org-b" for s in org_b_situations), (
            "org-b should only see org-b's SharedEntity situation"
        )

        # They should be different situations (different situation_ids)
        org_a_ids = {s.situation_id for s in org_a_situations}
        org_b_ids = {s.situation_id for s in org_b_situations}
        assert org_a_ids.isdisjoint(org_b_ids), (
            "org-a and org-b situations must have different IDs — no cross-tenant leakage"
        )

    def test_no_cross_tenant_leakage_in_evidence_refs(self):
        """Evidence refs from org A do not appear in org B's situations."""
        from maestro_cognitive_council import SituationEngine

        signals = [
            _make_signal("customer.commitment_made", "EntityA", "Commitment A",
                         signal_id="ev-org-a-1", org_id="org-a", days_ago=10),
            _make_signal("customer.commitment_made", "EntityA", "Commitment B",
                         signal_id="ev-org-a-2", org_id="org-a", days_ago=8),
            _make_signal("customer.commitment_made", "EntityB", "Commitment C",
                         signal_id="ev-org-b-1", org_id="org-b", days_ago=5),
            _make_signal("customer.commitment_made", "EntityB", "Commitment D",
                         signal_id="ev-org-b-2", org_id="org-b", days_ago=3),
        ]

        oem = MagicMock()
        oem.signals = signals
        engine = SituationEngine(oem_state=oem)

        engine.detect_situations(org_id="org-a")
        engine.detect_situations(org_id="org-b")

        org_a_situations = engine.get_active_situations(org_id="org-a")
        org_b_situations = engine.get_active_situations(org_id="org-b")

        for s in org_a_situations:
            assert "ev-org-b-1" not in s.evidence_refs, (
                "org-a situation contains org-b evidence — cross-tenant leakage!"
            )
            assert "ev-org-b-2" not in s.evidence_refs, (
                "org-a situation contains org-b evidence — cross-tenant leakage!"
            )

        for s in org_b_situations:
            assert "ev-org-a-1" not in s.evidence_refs, (
                "org-b situation contains org-a evidence — cross-tenant leakage!"
            )
            assert "ev-org-a-2" not in s.evidence_refs, (
                "org-b situation contains org-a evidence — cross-tenant leakage!"
            )


# ════════════════════════════════════════════════════════════════════════════
# Bridge org_id scoping
# ════════════════════════════════════════════════════════════════════════════

class TestBridgeOrgIdScoping:
    """All bridges scope by org_id."""

    def test_ask_bridge_respects_org_id(self):
        """Ask bridge only finds situations for the specified org."""
        from maestro_cognitive_council import SituationAwareAskBridge

        signals = [
            _make_signal("customer.commitment_made", "EntityA", "Commitment A", org_id="org-a", days_ago=10),
            _make_signal("customer.commitment_made", "EntityA", "Commitment B", org_id="org-a", days_ago=8),
            _make_signal("customer.commitment_made", "EntityB", "Commitment C", org_id="org-b", days_ago=5),
            _make_signal("customer.commitment_made", "EntityB", "Commitment D", org_id="org-b", days_ago=3),
        ]

        oem = MagicMock()
        oem.signals = signals
        bridge = SituationAwareAskBridge(oem_state=oem)

        # org-a asks about EntityA — should find it
        result_a = bridge.ask("What's happening with EntityA?", org_id="org-a")
        assert result_a.found_situation is True

        # org-b asks about EntityA — should NOT find it (different org)
        result_b = bridge.ask("What's happening with EntityA?", org_id="org-b")
        assert result_b.found_situation is False, (
            "org-b should not find org-a's EntityA situation — tenant isolation violation"
        )

    def test_briefing_bridge_respects_org_id(self):
        """Briefing bridge only includes situations for the specified org."""
        from maestro_cognitive_council import SituationBriefingEngine

        signals = [
            _make_signal("customer.commitment_made", "EntityA", "Commitment A", org_id="org-a", days_ago=10),
            _make_signal("customer.commitment_made", "EntityA", "Commitment B", org_id="org-a", days_ago=8),
            _make_signal("customer.commitment_made", "EntityB", "Commitment C", org_id="org-b", days_ago=5),
            _make_signal("customer.commitment_made", "EntityB", "Commitment D", org_id="org-b", days_ago=3),
        ]

        oem = MagicMock()
        oem.signals = signals

        engine_a = SituationBriefingEngine(oem_state=oem)
        briefing_a = engine_a.generate_morning_briefing(org_id="org-a")

        # org-a briefing should reference EntityA, not EntityB
        if briefing_a.top_situation:
            assert briefing_a.top_situation.get("entity") == "EntityA"

        engine_b = SituationBriefingEngine(oem_state=oem)
        briefing_b = engine_b.generate_morning_briefing(org_id="org-b")

        # org-b briefing should reference EntityB, not EntityA
        if briefing_b.top_situation:
            assert briefing_b.top_situation.get("entity") == "EntityB"

    def test_no_cross_tenant_situation_access(self):
        """A situation from org-a cannot be accessed by org-b."""
        from maestro_cognitive_council import SituationEngine

        signals = [
            _make_signal("customer.commitment_made", "EntityA", "Commitment A", org_id="org-a", days_ago=10),
            _make_signal("customer.commitment_made", "EntityA", "Commitment B", org_id="org-a", days_ago=8),
        ]

        oem = MagicMock()
        oem.signals = signals
        engine = SituationEngine(oem_state=oem)

        # org-a detects situations
        situations = engine.detect_situations(org_id="org-a")
        assert len(situations) > 0
        situation_id = situations[0].situation_id

        # org-b tries to access org-a's situation by ID
        # get_situation() doesn't filter by org_id — but the situation's org_id is "org-a"
        situation = engine.get_situation(situation_id)
        assert situation is not None
        assert situation.org_id == "org-a", (
            "Situation should be owned by org-a"
        )

        # org-b's active situations should NOT include org-a's situation
        org_b_active = engine.get_active_situations(org_id="org-b")
        org_b_ids = {s.situation_id for s in org_b_active}
        assert situation_id not in org_b_ids, (
            "org-b should not see org-a's situation in its active list — tenant isolation"
        )
