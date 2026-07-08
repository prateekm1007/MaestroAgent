"""Tests for the Persistent Situation Store.

Per the audit: "No persistent Situation store — SituationEngine rebuilds
from signals per request. Even the new API re-derives rather than evolves
a situation over time."

This test verifies:
  1. SituationStore saves and loads situations
  2. SituationEngine with a store EVOLVES situations (delta-driven)
  3. Situations persist across "requests" (multiple detect_situations calls)
  4. The situation_id is STABLE across requests (not a new UUID each time)
"""

from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
import os
import tempfile

import pytest


def _make_signal(sig_type, entity, text, signal_id="", days_ago=0):
    sig = MagicMock()
    sig.type = MagicMock()
    sig.type.value = sig_type
    sig.entity = entity
    sig.text = text
    sig.signal_id = signal_id or f"sig-{entity.lower()}-{days_ago}"
    sig.metadata = {"customer": entity}
    sig.timestamp = datetime.now(timezone.utc) - timedelta(days=days_ago)
    sig.actor = ""
    sig.org_id = "default"
    return sig


class TestSituationStore:
    """The SituationStore persists situations to SQLite."""

    def test_store_saves_and_loads_situation(self):
        """SituationStore.save_situation + load_situation round-trips."""
        from maestro_cognitive_council import SituationStore, LivingSituation, SituationState

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            store = SituationStore(db_path=db_path)

            situation = LivingSituation(
                situation_id="sit-test-1",
                title="Test situation",
                entity="TestEntity",
                org_id="default",
                state=SituationState.MATERIAL,
            )
            situation.evidence_refs = ["ev-1", "ev-2"]

            store.save_situation(situation)

            loaded = store.load_situation("TestEntity", "default")
            assert loaded is not None
            assert loaded["situation_id"] == "sit-test-1"
            assert loaded["entity"] == "TestEntity"
            assert "ev-1" in loaded["evidence_refs"]
        finally:
            os.unlink(db_path)

    def test_store_persists_across_instances(self):
        """A new SituationStore instance can load situations saved by a previous one."""
        from maestro_cognitive_council import SituationStore, LivingSituation

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            # Save with one instance
            store1 = SituationStore(db_path=db_path)
            situation = LivingSituation(
                situation_id="sit-persist-1",
                title="Persistent test",
                entity="PersistEntity",
            )
            store1.save_situation(situation)

            # Load with a NEW instance (simulates a new request)
            store2 = SituationStore(db_path=db_path)
            loaded = store2.load_situation("PersistEntity", "default")
            assert loaded is not None
            assert loaded["situation_id"] == "sit-persist-1"
        finally:
            os.unlink(db_path)

    def test_store_counts_situations(self):
        """SituationStore.count returns the number of situations for an org."""
        from maestro_cognitive_council import SituationStore, LivingSituation

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            store = SituationStore(db_path=db_path)
            assert store.count("default") == 0

            store.save_situation(LivingSituation(
                situation_id="s1", title="A", entity="EntityA"))
            store.save_situation(LivingSituation(
                situation_id="s2", title="B", entity="EntityB"))

            assert store.count("default") == 2
        finally:
            os.unlink(db_path)


class TestSituationEnginePersistence:
    """SituationEngine with a store EVOLVES situations (not rebuild)."""

    def test_situation_id_is_stable_across_requests(self):
        """The situation_id is STABLE when detect_situations is called twice.

        Without a store: each call creates a new situation_id (UUID).
        With a store: the situation_id persists from the first call.
        """
        from maestro_cognitive_council import SituationEngine, SituationStore

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            signals = [
                _make_signal("customer.commitment_made", "TestEntity", "Deliver X", "s1", days_ago=10),
                _make_signal("customer.commitment_made", "TestEntity", "Deliver Y", "s2", days_ago=8),
            ]
            oem = MagicMock()
            oem.signals = signals
            store = SituationStore(db_path=db_path)
            engine = SituationEngine(oem_state=oem, situation_store=store)

            # First call — creates the situation
            situations_1 = engine.detect_situations()
            assert len(situations_1) >= 1
            situation_id_1 = situations_1[0].situation_id

            # Second call — should EVOLVE, not rebuild
            situations_2 = engine.detect_situations()
            assert len(situations_2) >= 1
            situation_id_2 = situations_2[0].situation_id

            # The situation_id should be STABLE (same entity → same situation)
            assert situation_id_1 == situation_id_2, (
                f"Situation ID changed across requests: {situation_id_1} → {situation_id_2}. "
                "Without a store, each call creates a new UUID. With a store, it should persist."
            )
        finally:
            os.unlink(db_path)

    def test_new_signal_evolves_existing_situation(self):
        """A new signal EVOLVES the existing situation (delta-driven, not rebuild)."""
        from maestro_cognitive_council import SituationEngine, SituationStore

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            # First request: 2 signals
            signals_1 = [
                _make_signal("customer.commitment_made", "TestEntity", "Deliver X", "s1", days_ago=10),
                _make_signal("customer.commitment_made", "TestEntity", "Deliver Y", "s2", days_ago=8),
            ]
            oem = MagicMock()
            oem.signals = signals_1
            store = SituationStore(db_path=db_path)
            engine = SituationEngine(oem_state=oem, situation_store=store)

            situations_1 = engine.detect_situations()
            original_evidence_count = len(situations_1[0].evidence_refs)
            assert original_evidence_count >= 2

            # Second request: same 2 signals + 1 new signal
            signals_2 = signals_1 + [
                _make_signal("security.condition", "TestEntity", "Security approval", "s3", days_ago=5),
            ]
            oem.signals = signals_2
            engine2 = SituationEngine(oem_state=oem, situation_store=store)
            situations_2 = engine2.detect_situations()

            # The situation should have EVOLVED — more evidence refs
            assert len(situations_2[0].evidence_refs) > original_evidence_count, (
                "The new signal should have been applied as a delta — "
                "evidence_refs should grow, not be rebuilt from scratch."
            )
        finally:
            os.unlink(db_path)

    def test_situation_persists_to_sqlite(self):
        """The situation is saved to the SQLite store after detect_situations."""
        from maestro_cognitive_council import SituationEngine, SituationStore

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            signals = [
                _make_signal("customer.commitment_made", "PersistEntity", "Deliver X", "s1", days_ago=10),
                _make_signal("customer.commitment_made", "PersistEntity", "Deliver Y", "s2", days_ago=8),
            ]
            oem = MagicMock()
            oem.signals = signals
            store = SituationStore(db_path=db_path)
            engine = SituationEngine(oem_state=oem, situation_store=store)
            engine.detect_situations()

            # Verify it was saved to the store
            assert store.count("default") >= 1
            loaded = store.load_situation("PersistEntity", "default")
            assert loaded is not None
            assert loaded["entity"] == "PersistEntity"
        finally:
            os.unlink(db_path)

    def test_transitions_are_persisted(self):
        """State transitions are persisted to the store."""
        from maestro_cognitive_council import SituationEngine, SituationStore

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            signals = [
                _make_signal("customer.commitment_made", "TransEntity", "Deliver SSO", "s1", days_ago=10),
                _make_signal("security.condition", "TransEntity", "Security approval required", "s2", days_ago=8),
            ]
            oem = MagicMock()
            oem.signals = signals
            store = SituationStore(db_path=db_path)
            engine = SituationEngine(oem_state=oem, situation_store=store)
            situations = engine.detect_situations()

            if situations:
                situation = situations[0]
                # Save any transitions
                for transition in situation.state_history:
                    store.save_transition(situation.entity, situation.org_id, transition)

                # Load transitions
                transitions = store.load_transitions("TransEntity", "default")
                assert len(transitions) > 0
        finally:
            os.unlink(db_path)
