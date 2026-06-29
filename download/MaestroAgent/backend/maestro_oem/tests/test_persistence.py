"""
Tests for OEM persistence.

Tests:
1. Save and restore model — state survives close/reopen
2. Cold boot reconstructs OEM — no reprocessing needed
3. Incremental updates — new signals after restore don't reprocess old ones
4. Learning objects persist
5. Patterns persist
6. Laws persist
7. Receipts persist
8. Processed signals persist (deduplication survives restart)
9. Contradiction events persist (append-only log survives)
10. Model state persists (health, knowledge, approvals, risks)
11. Connected providers persist
12. Fresh database starts empty
13. Multiple save/load cycles are idempotent
14. Signal deduplication works after restart
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from maestro_oem import (
    ContradictionEngine,
    ContradictionLog,
    FeedbackAction,
    OEMEngine,
    PersistentOEM,
)
from maestro_oem.providers import (
    normalize_github,
    normalize_jira,
    normalize_slack,
)


def _make_signals():
    """Create test signals."""
    return [
        normalize_github(e) for e in [
            {"event_type": "merge", "repository": "acme/payments", "actor": "priya@acme.com",
             "artifact": "github:acme/payments/pull/1", "timestamp": "2024-01-15T09:00:00Z",
             "metadata": {"domain": "payments", "action": "merged"}},
            {"event_type": "review", "repository": "acme/payments", "actor": "priya@acme.com",
             "artifact": "github:acme/payments/pull/1", "timestamp": "2024-01-15T09:30:00Z",
             "metadata": {"reviewer": "carlos@acme.com", "domain": "payments", "action": "approved"}},
            {"event_type": "commit", "repository": "acme/platform", "actor": "aisha@acme.com",
             "artifact": "github:acme/platform/commit/abc", "timestamp": "2024-02-01T11:00:00Z",
             "metadata": {"domain": "platform"}},
        ]
    ] + [
        normalize_jira(e) for e in [
            {"event_type": "issue_created", "project": "EMEA", "actor": "sara@acme.com",
             "artifact": "jira:EMEA-1", "timestamp": "2024-02-05T09:00:00Z",
             "metadata": {"priority": "P1", "issue_type": "Bug"}},
            {"event_type": "issue_transitioned", "project": "EMEA", "actor": "sara@acme.com",
             "artifact": "jira:EMEA-1", "timestamp": "2024-02-06T14:00:00Z",
             "metadata": {"transition": "Approved", "assignee": "sara@acme.com"}},
        ]
    ] + [
        normalize_slack(e) for e in [
            {"event_type": "message", "channel": "#eng", "actor": "anya@acme.com",
             "artifact": "slack:C-1/p-1", "timestamp": "2024-02-10T15:00:00Z",
             "metadata": {"text": "I'm thinking about a new opportunity", "participants": ["anya@acme.com"]}},
        ]
    ]


# ============================================================
# TEST 1: Save and restore — state survives close/reopen
# ============================================================

class TestSaveRestore:
    def test_model_survives_close_reopen(self):
        """All model state must survive close and reopen."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")

            # First run: ingest signals
            persistent = PersistentOEM(db_path=db_path)
            signals = _make_signals()
            persistent.ingest(signals)
            original_summary = persistent.get_summary()
            persistent.close()

            # Second run: cold boot
            persistent2 = PersistentOEM(db_path=db_path)
            restored_summary = persistent2.get_summary()

            assert restored_summary["signals_processed"] == original_summary["signals_processed"]
            assert restored_summary["learning_objects"] == original_summary["learning_objects"]
            assert restored_summary["laws_inferred"] == original_summary["laws_inferred"]
            assert restored_summary["providers_connected"] == original_summary["providers_connected"]
            persistent2.close()


# ============================================================
# TEST 2: Cold boot reconstructs OEM — no reprocessing
# ============================================================

class TestColdBoot:
    def test_cold_boot_no_reprocessing(self):
        """Cold boot must not reprocess signals — processed count must stay the same."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")

            # First run
            persistent = PersistentOEM(db_path=db_path)
            signals = _make_signals()
            persistent.ingest(signals)
            first_count = persistent.get_summary()["signals_processed"]
            persistent.close()

            # Cold boot
            persistent2 = PersistentOEM(db_path=db_path)
            cold_count = persistent2.get_summary()["signals_processed"]
            assert cold_count == first_count, (
                f"Cold boot should not reprocess. Before: {first_count}, After: {cold_count}"
            )
            persistent2.close()

    def test_cold_boot_restores_learning_objects(self):
        """Learning objects must be restored on cold boot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")

            persistent = PersistentOEM(db_path=db_path)
            persistent.ingest(_make_signals())
            lo_count = len(persistent.get_model().learning_objects)
            persistent.close()

            persistent2 = PersistentOEM(db_path=db_path)
            restored_lo_count = len(persistent2.get_model().learning_objects)
            assert restored_lo_count == lo_count
            persistent2.close()

    def test_cold_boot_restores_laws(self):
        """Laws must be restored on cold boot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")

            persistent = PersistentOEM(db_path=db_path)
            persistent.ingest(_make_signals())
            law_count = len(persistent.get_model().laws)
            persistent.close()

            persistent2 = PersistentOEM(db_path=db_path)
            restored_law_count = len(persistent2.get_model().laws)
            assert restored_law_count == law_count
            persistent2.close()

    def test_cold_boot_restores_knowledge_graph(self):
        """Knowledge graph (expertise, influence) must be restored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")

            persistent = PersistentOEM(db_path=db_path)
            persistent.ingest(_make_signals())
            model = persistent.get_model()
            assert "priya@acme.com" in model.knowledge.expertise
            persistent.close()

            persistent2 = PersistentOEM(db_path=db_path)
            restored_model = persistent2.get_model()
            assert "priya@acme.com" in restored_model.knowledge.expertise
            assert "payments" in restored_model.knowledge.expertise["priya@acme.com"]
            persistent2.close()


# ============================================================
# TEST 3: Incremental updates — new signals after restore
# ============================================================

class TestIncrementalUpdates:
    def test_new_signals_after_restore_are_processed(self):
        """After cold boot, new signals must be processed incrementally."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")

            # First run: 6 signals
            persistent = PersistentOEM(db_path=db_path)
            signals1 = _make_signals()
            persistent.ingest(signals1)
            count1 = persistent.get_summary()["signals_processed"]
            persistent.close()

            # Cold boot + new signal
            persistent2 = PersistentOEM(db_path=db_path)
            count_after_boot = persistent2.get_summary()["signals_processed"]
            assert count_after_boot == count1

            new_signal = normalize_github({
                "event_type": "merge",
                "repository": "acme/new",
                "actor": "new@acme.com",
                "artifact": "github:acme/new/pull/1",
                "timestamp": "2024-03-01T09:00:00Z",
                "metadata": {"domain": "new", "action": "merged"},
            })
            persistent2.ingest_one(new_signal)
            count2 = persistent2.get_summary()["signals_processed"]
            assert count2 == count1 + 1
            persistent2.close()

    def test_deduplication_survives_restart(self):
        """A signal processed before restart must not be reprocessed after."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")

            persistent = PersistentOEM(db_path=db_path)
            signals = _make_signals()
            persistent.ingest(signals)
            count = persistent.get_summary()["signals_processed"]
            persistent.close()

            # Cold boot and try to reingest the same signals
            persistent2 = PersistentOEM(db_path=db_path)
            persistent2.ingest(signals)  # Same signals
            count2 = persistent2.get_summary()["signals_processed"]
            assert count2 == count, "Same signals reprocessed after restart — deduplication failed"
            persistent2.close()


# ============================================================
# TEST 4-7: Individual component persistence
# ============================================================

class TestComponentPersistence:
    def test_learning_objects_persist(self):
        """Learning objects must persist with all fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")

            persistent = PersistentOEM(db_path=db_path)
            persistent.ingest(_make_signals())
            original_los = persistent.get_model().learning_objects
            persistent.close()

            persistent2 = PersistentOEM(db_path=db_path)
            restored_los = persistent2.get_model().learning_objects

            assert len(restored_los) == len(original_los)
            # Check a specific LO has its fields
            for lo_id, lo in restored_los.items():
                assert lo.title != ""
                assert lo.type is not None
                assert lo.evidence_count >= 1
            persistent2.close()

    def test_patterns_persist(self):
        """Patterns must persist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")

            persistent = PersistentOEM(db_path=db_path)
            persistent.ingest(_make_signals())
            original_patterns = len(persistent.get_model().pattern_detector.patterns)
            persistent.close()

            persistent2 = PersistentOEM(db_path=db_path)
            restored_patterns = len(persistent2.get_model().pattern_detector.patterns)
            assert restored_patterns == original_patterns
            persistent2.close()

    def test_receipts_persist(self):
        """Receipt chains must persist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")

            persistent = PersistentOEM(db_path=db_path)
            persistent.ingest(_make_signals())
            original_chains = len(persistent.get_model().receipt_chains)
            persistent.close()

            persistent2 = PersistentOEM(db_path=db_path)
            restored_chains = len(persistent2.get_model().receipt_chains)
            assert restored_chains == original_chains
            persistent2.close()

    def test_model_state_persists(self):
        """Health metrics, knowledge graph, approvals, risks must persist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")

            persistent = PersistentOEM(db_path=db_path)
            persistent.ingest(_make_signals())
            model = persistent.get_model()
            original_incident_rate = model.health.incident_rate
            original_release_freq = model.health.release_frequency
            persistent.close()

            persistent2 = PersistentOEM(db_path=db_path)
            restored_model = persistent2.get_model()
            assert restored_model.health.incident_rate == original_incident_rate
            assert restored_model.health.release_frequency == original_release_freq
            persistent2.close()


# ============================================================
# TEST 8: Processed signals persist
# ============================================================

class TestProcessedSignalsPersist:
    def test_processed_signal_ids_persist(self):
        """Processed signal IDs must persist for deduplication."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")

            persistent = PersistentOEM(db_path=db_path)
            signals = _make_signals()
            persistent.ingest(signals)
            original_processed = set(str(sid) for sid in persistent.get_model().processed_signals)
            persistent.close()

            persistent2 = PersistentOEM(db_path=db_path)
            restored_processed = set(str(sid) for sid in persistent2.get_model().processed_signals)
            assert restored_processed == original_processed
            persistent2.close()


# ============================================================
# TEST 9: Contradiction events persist
# ============================================================

class TestContradictionPersistence:
    def test_contradiction_events_persist(self):
        """Contradiction events must persist (append-only log)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")

            # First run: create a contradiction event
            persistent = PersistentOEM(db_path=db_path)
            persistent.ingest(_make_signals())
            model = persistent.get_model()

            # Inject a law for the contradiction
            from maestro_oem.law import OrganizationalLaw, LawStatus
            law = OrganizationalLaw(
                code="L-PERSIST-TEST",
                statement="Test law for persistence",
                condition="X", outcome="Y",
                status=LawStatus.VALIDATED,
                validated_runtimes=3,
                providers={"github"},
            )
            model.laws["L-PERSIST-TEST"] = law

            contra = ContradictionEngine(model)
            event = contra.apply_feedback(
                target_type="law",
                target_id="L-PERSIST-TEST",
                action=FeedbackAction.REJECT,
                reasoning="Test rejection for persistence",
                actor="ceo@acme.com",
            )
            persistent.save_contradiction(event)
            persistent._save()
            persistent.close()

            # Second run: load contradiction log
            persistent2 = PersistentOEM(db_path=db_path)
            log = persistent2.load_contradiction_log()
            assert log.total_events() == 1
            assert log.get_rejections()[0].reasoning == "Test rejection for persistence"
            persistent2.close()


# ============================================================
# TEST 10: Connected providers persist
# ============================================================

class TestProvidersPersist:
    def test_connected_providers_persist(self):
        """Connected providers must persist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")

            persistent = PersistentOEM(db_path=db_path)
            persistent.ingest(_make_signals())
            original_providers = persistent.get_summary()["providers_connected"]
            persistent.close()

            persistent2 = PersistentOEM(db_path=db_path)
            restored_providers = persistent2.get_summary()["providers_connected"]
            assert set(restored_providers) == set(original_providers)
            persistent2.close()


# ============================================================
# TEST 11: Fresh database starts empty
# ============================================================

class TestFreshDatabase:
    def test_fresh_db_starts_empty(self):
        """A fresh database must start with no state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "fresh.db")

            persistent = PersistentOEM(db_path=db_path)
            summary = persistent.get_summary()
            assert summary["signals_processed"] == 0
            assert summary["learning_objects"] == 0
            assert summary["laws_inferred"] == 0
            persistent.close()


# ============================================================
# TEST 12: Multiple save/load cycles are idempotent
# ============================================================

class TestIdempotentSaveLoad:
    def test_multiple_save_load_cycles(self):
        """Saving and loading multiple times must not change state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")

            persistent = PersistentOEM(db_path=db_path)
            persistent.ingest(_make_signals())
            persistent.close()

            # Load and save multiple times
            for i in range(3):
                persistent = PersistentOEM(db_path=db_path)
                summary = persistent.get_summary()
                assert summary["signals_processed"] == len(_make_signals())
                persistent.close()


# ============================================================
# TEST 13: Departure risk persists
# ============================================================

class TestRiskPersistence:
    def test_departure_risk_persists(self):
        """Departure risks must persist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")

            persistent = PersistentOEM(db_path=db_path)
            persistent.ingest(_make_signals())
            model = persistent.get_model()
            assert "anya@acme.com" in model.risks.departure_risks
            original_risk = model.risks.departure_risks["anya@acme.com"]
            persistent.close()

            persistent2 = PersistentOEM(db_path=db_path)
            restored_model = persistent2.get_model()
            assert "anya@acme.com" in restored_model.risks.departure_risks
            assert restored_model.risks.departure_risks["anya@acme.com"] == original_risk
            persistent2.close()
