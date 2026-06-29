"""
Additional persistence edge case tests.

Tests:
- get_all_signals returns signals with all fields
- Knowledge graph round-trip with sets (serialization)
- Pattern detector patterns restored correctly
- LO restored with all fields (not just count)
- Law restored with all fields
- Receipt chain restored with receipt data
- Multiple contradiction events persist in order
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from maestro_oem import PersistentOEM, OEMStore
from maestro_oem.providers import normalize_github, normalize_jira
from maestro_oem.signal import ExecutionSignal, SignalProvider, SignalType


def _make_signals():
    return [normalize_github(e) for e in [
        {"event_type": "merge", "repository": "acme/payments", "actor": "priya@acme.com",
         "artifact": "github:acme/payments/pull/1", "timestamp": "2024-01-15T09:00:00Z",
         "metadata": {"domain": "payments", "action": "merged", "labels": ["bug"]}},
        {"event_type": "review", "repository": "acme/payments", "actor": "priya@acme.com",
         "artifact": "github:acme/payments/pull/1", "timestamp": "2024-01-15T09:30:00Z",
         "metadata": {"reviewer": "carlos@acme.com", "domain": "payments", "action": "approved"}},
    ]] + [normalize_jira(e) for e in [
        {"event_type": "issue_created", "project": "EMEA", "actor": "sara@acme.com",
         "artifact": "jira:EMEA-1", "timestamp": "2024-02-05T09:00:00Z",
         "metadata": {"priority": "P1", "issue_type": "Bug"}},
    ]]


class TestSignalPersistence:
    def test_get_all_signals_returns_all_fields(self):
        """get_all_signals must return signals with all fields intact."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            persistent = PersistentOEM(db_path=db_path)
            signals = _make_signals()
            persistent.ingest(signs := signals)
            persistent.close()

            store = OEMStore(db_path)
            loaded = store.get_all_signals()
            store.close()

            assert len(loaded) == len(signals)
            # Check first signal has all fields
            s = loaded[0]
            assert s.actor == "priya@acme.com"
            assert s.provider == SignalProvider.GITHUB
            assert s.type in (SignalType.PR_MERGED, SignalType.PR_OPENED)
            assert s.metadata.get("domain") == "payments"
            assert "labels" in s.metadata

    def test_signals_ordered_by_timestamp(self):
        """get_all_signals must return signals ordered by timestamp."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            persistent = PersistentOEM(db_path=db_path)
            persistent.ingest(_make_signals())
            persistent.close()

            store = OEMStore(db_path)
            loaded = store.get_all_signals()
            store.close()

            for i in range(len(loaded) - 1):
                assert loaded[i].timestamp <= loaded[i + 1].timestamp


class TestKnowledgeGraphRoundTrip:
    def test_knowledge_graph_sets_preserved(self):
        """Knowledge graph sets must survive serialization round-trip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            persistent = PersistentOEM(db_path=db_path)
            persistent.ingest(_make_signals())
            model = persistent.get_model()
            # Verify sets were built
            assert "priya@acme.com" in model.knowledge.expertise
            assert isinstance(model.knowledge.expertise["priya@acme.com"], set)
            assert "payments" in model.knowledge.expertise["priya@acme.com"]
            persistent.close()

            # Reload
            persistent2 = PersistentOEM(db_path=db_path)
            model2 = persistent2.get_model()
            assert "priya@acme.com" in model2.knowledge.expertise
            assert isinstance(model2.knowledge.expertise["priya@acme.com"], set)
            assert "payments" in model2.knowledge.expertise["priya@acme.com"]
            persistent2.close()

    def test_influence_scores_preserved(self):
        """Influence scores must survive round-trip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            persistent = PersistentOEM(db_path=db_path)
            persistent.ingest(_make_signals())
            model = persistent.get_model()
            original_influence = model.knowledge.influence.get("carlos@acme.com", 0)
            assert original_influence > 0
            persistent.close()

            persistent2 = PersistentOEM(db_path=db_path)
            model2 = persistent2.get_model()
            restored_influence = model2.knowledge.influence.get("carlos@acme.com", 0)
            assert restored_influence == original_influence
            persistent2.close()


class TestLORoundTrip:
    def test_lo_all_fields_restored(self):
        """Learning objects must restore all fields, not just count."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            persistent = PersistentOEM(db_path=db_path)
            persistent.ingest(_make_signals())
            model = persistent.get_model()
            if model.learning_objects:
                lo_id = list(model.learning_objects.keys())[0]
                original = model.learning_objects[lo_id]
                persistent.close()

                persistent2 = PersistentOEM(db_path=db_path)
                model2 = persistent2.get_model()
                restored = model2.learning_objects.get(lo_id)
                assert restored is not None
                assert restored.title == original.title
                assert restored.type == original.type
                assert restored.evidence_count == original.evidence_count
                assert restored.confidence == original.confidence
                assert restored.providers == original.providers
                persistent2.close()


class TestLawRoundTrip:
    def test_law_all_fields_restored(self):
        """Laws must restore all fields."""
        from maestro_oem.law import OrganizationalLaw, LawStatus

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            persistent = PersistentOEM(db_path=db_path)
            persistent.ingest(_make_signals())
            model = persistent.get_model()

            # Inject a law
            law = OrganizationalLaw(
                code="L-FULL-TEST",
                statement="Full field test law",
                condition="When X",
                outcome="Y happens",
                status=LawStatus.VALIDATED,
                validated_runtimes=7,
                failed_runtimes=2,
                evidence_count=9,
                providers={"github", "jira"},
                confidence=0.78,
                known_to_leadership=True,
            )
            model.laws["L-FULL-TEST"] = law
            persistent._save()
            persistent.close()

            persistent2 = PersistentOEM(db_path=db_path)
            model2 = persistent2.get_model()
            restored = model2.laws.get("L-FULL-TEST")
            assert restored is not None
            assert restored.statement == "Full field test law"
            assert restored.status == LawStatus.VALIDATED
            assert restored.validated_runtimes == 7
            assert restored.failed_runtimes == 2
            assert restored.confidence == 0.78
            assert restored.known_to_leadership is True
            assert "github" in restored.providers
            assert "jira" in restored.providers
            persistent2.close()


class TestReceiptChainRoundTrip:
    def test_receipt_chain_has_receipts(self):
        """Receipt chains must restore with actual receipt data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            persistent = PersistentOEM(db_path=db_path)
            persistent.ingest(_make_signals())
            model = persistent.get_model()
            original_chain_count = len(model.receipt_chains)
            assert original_chain_count > 0
            # Check a chain has receipts
            for target, chain in model.receipt_chains.items():
                assert len(chain.receipts) > 0
                assert chain.receipts[0].signal_artifact != ""
            persistent.close()

            persistent2 = PersistentOEM(db_path=db_path)
            model2 = persistent2.get_model()
            assert len(model2.receipt_chains) == original_chain_count
            for target, chain in model2.receipt_chains.items():
                assert len(chain.receipts) > 0
                assert chain.receipts[0].signal_artifact != ""
                assert chain.receipts[0].signal_type != ""
            persistent2.close()


class TestMultipleContradictionsPersist:
    def test_multiple_events_in_order(self):
        """Multiple contradiction events must persist in chronological order."""
        from maestro_oem import ContradictionEngine, FeedbackAction
        from maestro_oem.law import OrganizationalLaw, LawStatus

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            persistent = PersistentOEM(db_path=db_path)
            persistent.ingest(_make_signals())
            model = persistent.get_model()

            law = OrganizationalLaw(
                code="L-MULTI-CONTRA",
                statement="Multi contradiction test",
                condition="X", outcome="Y",
                status=LawStatus.VALIDATED,
                validated_runtimes=3,
            )
            model.laws["L-MULTI-CONTRA"] = law

            contra = ContradictionEngine(model)
            for action in [FeedbackAction.AGREE, FeedbackAction.REJECT, FeedbackAction.MODIFY]:
                event = contra.apply_feedback(
                    target_type="law",
                    target_id="L-MULTI-CONTRA",
                    action=action,
                    actor="ceo@acme.com",
                )
                persistent.save_contradiction(event)

            persistent._save()
            persistent.close()

            persistent2 = PersistentOEM(db_path=db_path)
            log = persistent2.load_contradiction_log()
            assert log.total_events() == 3
            actions = [e.action for e in log.events]
            assert actions == [FeedbackAction.AGREE, FeedbackAction.REJECT, FeedbackAction.MODIFY]
            persistent2.close()
