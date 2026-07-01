"""
V8 P1 Features — Regression tests.

P1-1: Trust Ledger
P1-2: Progressive Trust (Auto-Execute)
P1-3: Unknown-to-Action Pipeline
P1-4: Auto-Completion Detection
P1-5: The Briefing Learns (Attention Signals)
"""

from __future__ import annotations

import os
import pathlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    app_dir = str(pathlib.Path(__file__).resolve().parents[3])
    os.environ.setdefault("MAESTRO_APP_DIR", app_dir)
    os.environ.setdefault("MAESTRO_AUTH_DB", "/tmp/maestro_test_p1_auth.db")
    os.environ.setdefault("MAESTRO_ADMIN_PASSWORD", "test")
    from maestro_api.main import create_app
    app = create_app(db_path=":memory:")
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clear_stores():
    from maestro_oem.trust_ledger import TrustLedger
    from maestro_oem.attention_signals import AttentionSignalStore
    from maestro_oem.user_settings import UserSettings
    from maestro_oem.writeback import WriteBackStore
    TrustLedger.clear()
    AttentionSignalStore.clear()
    UserSettings.clear()
    WriteBackStore.clear()
    yield
    TrustLedger.clear()
    AttentionSignalStore.clear()
    UserSettings.clear()
    WriteBackStore.clear()


# ============================================================
# P1-1: Trust Ledger
# ============================================================

class TestTrustLedger:
    """The trust ledger records every write-back action."""

    def test_ledger_endpoint_returns_200(self, client) -> None:
        r = client.get("/api/oem/trust/ledger")
        assert r.status_code == 200
        data = r.json()
        assert "entries" in data
        assert "count" in data
        assert "summary" in data

    def test_manual_approval_creates_ledger_entry(self, client) -> None:
        """POST /writeback/{id}/approve must create a ledger entry."""
        from maestro_oem.trust_ledger import TrustLedger
        # Preview + approve
        r1 = client.post("/api/oem/writeback", json={
            "provider": "jira", "action_type": "create_issue",
            "params": {"project": "ENG", "summary": "Test", "description": "d"},
        })
        action_id = r1.json()["action_id"]
        client.post(f"/api/oem/writeback/{action_id}/approve", json={"approved_by": "ceo@acme.com"})
        # Check ledger
        entries = TrustLedger.get_entries()
        assert len(entries) >= 1
        assert entries[-1].approver == "ceo@acme.com"
        assert entries[-1].provider == "jira"
        assert entries[-1].outcome == "success"
        assert entries[-1].auto is False

    def test_trust_score_computation(self, client) -> None:
        """Trust score = successful - rolled_back."""
        from maestro_oem.trust_ledger import TrustLedger
        TrustLedger.clear()
        # Record 5 successes
        for i in range(5):
            TrustLedger.record("aid-1", "slack", "post_message", "ceo", "success")
        # Record 1 rollback
        TrustLedger.record("aid-2", "slack", "post_message", "ceo", "rolled_back")
        score = TrustLedger.compute_trust_score("ceo", "slack", "post_message")
        assert score == 4  # 5 - 1

    def test_auto_execute_eligibility_threshold(self, client) -> None:
        """Auto-execute requires trust_score >= 10 AND 0 rollbacks."""
        from maestro_oem.trust_ledger import TrustLedger
        TrustLedger.clear()
        # 9 successes — not eligible yet
        for i in range(9):
            TrustLedger.record("aid", "slack", "post_message", "ceo", "success")
        assert not TrustLedger.is_auto_execute_eligible("ceo", "slack", "post_message")
        # 10th success — eligible
        TrustLedger.record("aid", "slack", "post_message", "ceo", "success")
        assert TrustLedger.is_auto_execute_eligible("ceo", "slack", "post_message")
        # 1 rollback — not eligible
        TrustLedger.record("aid", "slack", "post_message", "ceo", "rolled_back")
        assert not TrustLedger.is_auto_execute_eligible("ceo", "slack", "post_message")

    def test_trust_score_endpoint(self, client) -> None:
        r = client.get("/api/oem/trust/score", params={"user": "ceo", "provider": "slack", "action_type": "post_message"})
        assert r.status_code == 200
        data = r.json()
        assert "trust_score" in data
        assert "auto_execute_eligible" in data
        assert data["threshold"] == 10


# ============================================================
# P1-2: Progressive Trust (Auto-Execute)
# ============================================================

class TestProgressiveTrust:
    """Auto-execute after earned trust. 60-second undo window."""

    def test_auto_execute_not_eligible_by_default(self, client) -> None:
        """Auto-execute must require trust_score >= 10."""
        r = client.post("/api/oem/writeback/auto-execute", json={
            "provider": "slack", "action_type": "post_message",
            "params": {"channel": "general", "text": "test"},
            "user": "newuser@acme.com",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "requires_manual_approval"
        assert data["auto"] is False

    def test_auto_execute_after_10_approvals(self, client) -> None:
        """After 10 successful approvals + opt-in, auto-execute fires."""
        from maestro_oem.trust_ledger import TrustLedger
        from maestro_oem.user_settings import UserSettings
        TrustLedger.clear()
        UserSettings.clear()
        for i in range(10):
            TrustLedger.record("aid", "slack", "post_message", "ceo@acme.com", "success")
        # Must also opt-in (Round-35 fix)
        UserSettings.set_auto_execute("ceo@acme.com", "slack", "post_message", True)
        r = client.post("/api/oem/writeback/auto-execute", json={
            "provider": "slack", "action_type": "post_message",
            "params": {"channel": "general", "text": "auto test"},
            "user": "ceo@acme.com",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "executed"
        assert data.get("auto") is True
        assert "undo_until" in data

    def test_undo_endpoint(self, client) -> None:
        """POST /writeback/{id}/undo must roll back and record in ledger."""
        from maestro_oem.trust_ledger import TrustLedger
        from maestro_oem.user_settings import UserSettings
        TrustLedger.clear()
        UserSettings.clear()
        for i in range(10):
            TrustLedger.record("aid", "slack", "post_message", "ceo@acme.com", "success")
        # Must also opt-in (Round-35 fix)
        UserSettings.set_auto_execute("ceo@acme.com", "slack", "post_message", True)
        # Auto-execute
        r1 = client.post("/api/oem/writeback/auto-execute", json={
            "provider": "slack", "action_type": "post_message",
            "params": {"channel": "general", "text": "undo test"},
            "user": "ceo@acme.com",
        })
        action_id = r1.json()["action_id"]
        # Undo
        r2 = client.post(f"/api/oem/writeback/{action_id}/undo", json={"user": "ceo@acme.com"})
        assert r2.status_code == 200
        assert r2.json()["status"] == "rolled_back"
        # Check ledger has a rolled_back entry
        entries = TrustLedger.get_entries(user_id="ceo@acme.com")
        rollbacks = [e for e in entries if e.outcome == "rolled_back"]
        assert len(rollbacks) >= 1


# ============================================================
# P1-3: Unknown-to-Action Pipeline
# ============================================================

class TestUnknownToAction:
    """Each unknown level has a suggested action."""

    def test_unknowns_actions_endpoint(self, client) -> None:
        r = client.get("/api/oem/unknowns/actions")
        assert r.status_code == 200
        data = r.json()
        assert "actions" in data
        assert "count" in data
        assert "summary" in data

    def test_actions_have_required_fields(self, client) -> None:
        r = client.get("/api/oem/unknowns/actions")
        data = r.json()
        for action in data["actions"]:
            assert "area" in action
            assert "level" in action
            assert "action" in action
            assert "label" in action
            assert "reason" in action

    def test_unknown_unknowns_have_connect_action(self, client) -> None:
        """Unknown Unknowns should suggest 'connect'."""
        r = client.get("/api/oem/unknowns/actions")
        data = r.json()
        connect_actions = [a for a in data["actions"] if a["action"] == "connect"]
        # If there are unknown_unknowns, they should have connect actions
        # (may be 0 if no unknown_unknowns exist in demo seed)
        for a in connect_actions:
            assert "suggested_provider" in a

    def test_emerging_unknowns_have_investigate_action(self, client) -> None:
        """Emerging Unknowns should suggest 'investigate'."""
        r = client.get("/api/oem/unknowns/actions")
        data = r.json()
        investigate_actions = [a for a in data["actions"] if a["action"] == "investigate"]
        for a in investigate_actions:
            assert "detected_at" in a


# ============================================================
# P1-4: Auto-Completion Detection
# ============================================================

class TestAutoCompletion:
    """Tasks auto-complete when matching completion signals arrive."""

    def test_auto_completed_endpoint(self, client) -> None:
        r = client.get("/api/oem/tasks/auto-completed")
        assert r.status_code == 200
        data = r.json()
        assert "tasks" in data
        assert "count" in data
        assert "summary" in data

    def test_auto_complete_tasks_function(self) -> None:
        """auto_complete_tasks must mark matching tasks as kept."""
        from maestro_oem import OEMEngine
        from maestro_oem.signal import ExecutionSignal, SignalType, SignalProvider
        from maestro_oem.task_extraction import TaskExtractor, auto_complete_tasks
        from maestro_oem.learning_object import LearningObjectType
        from uuid import uuid4
        from datetime import datetime, timezone

        engine = OEMEngine()
        model = engine.get_model()

        # Create an open task linked to artifact "PR-999"
        from maestro_oem.learning_object import LearningObject
        task = LearningObject(
            lo_id=uuid4(),
            type=LearningObjectType.TASK,
            title="Review PR-999",
            description="Review PR-999",
            entities=["raj@acme.com"],
            artifacts=["PR-999"],
            metadata={"status": "open", "assignee": "raj@acme.com"},
        )
        model.learning_objects[task.lo_id] = task

        # Create a completion signal (PR merged on the same artifact)
        sig = ExecutionSignal(
            type=SignalType.PR_MERGED,
            timestamp=datetime.now(timezone.utc),
            actor="raj@acme.com",
            artifact="PR-999",
            metadata={"domain": "engineering"},
            provider=SignalProvider.GITHUB,
        )

        completed = auto_complete_tasks(model, [sig])
        assert completed == 1
        assert task.metadata["status"] == "kept"
        assert task.metadata["auto_completed"] is True
        assert task.metadata["completed_by_signal"] is not None

    def test_live_ingest_calls_auto_complete(self) -> None:
        """oem_state.py live_ingest must call auto_complete_tasks."""
        import maestro_api.oem_state as mod
        source = open(mod.__file__).read()
        assert "auto_complete_tasks" in source, "oem_state.py doesn't call auto_complete_tasks"


# ============================================================
# P1-5: The Briefing Learns (Attention Signals)
# ============================================================

class TestAttentionSignals:
    """Attention signals record which briefing items the CEO clicks."""

    def test_record_attention(self, client) -> None:
        r = client.post("/api/oem/attention/record", json={
            "item_type": "commitments",
            "item_id": "commit-1",
        })
        assert r.status_code == 200
        assert r.json()["recorded"] is True

    def test_attention_summary(self, client) -> None:
        # Record a few signals
        client.post("/api/oem/attention/record", json={"item_type": "commitments"})
        client.post("/api/oem/attention/record", json={"item_type": "commitments"})
        client.post("/api/oem/attention/record", json={"item_type": "one_thing"})
        r = client.get("/api/oem/attention/summary")
        assert r.status_code == 200
        data = r.json()
        assert data["total_clicks"] >= 3
        assert "commitments" in data["click_counts"]
        assert data["click_counts"]["commitments"] >= 2

    def test_ranking_weight(self, client) -> None:
        """Ranking weight should be proportional to click share."""
        from maestro_oem.attention_signals import AttentionSignalStore
        AttentionSignalStore.clear()
        # 5 clicks on commitments, 0 on risks
        for _ in range(5):
            AttentionSignalStore.record("commitments")
        weight_commitments = AttentionSignalStore.get_ranking_weight("commitments")
        weight_risks = AttentionSignalStore.get_ranking_weight("risks")
        assert weight_commitments > weight_risks
        assert weight_risks == 0.0  # never hide — 0 weight is neutral

    def test_attention_never_hides(self, client) -> None:
        """Items with 0 clicks must still have weight 0.0 (not negative)."""
        from maestro_oem.attention_signals import AttentionSignalStore
        AttentionSignalStore.clear()
        AttentionSignalStore.record("commitments")
        weight = AttentionSignalStore.get_ranking_weight("risks")
        assert weight >= 0.0, "Attention signals must never produce negative weight (would hide items)"

    def test_attention_module_exists(self) -> None:
        """attention_signals.py must exist."""
        import maestro_oem.attention_signals as mod
        source = open(mod.__file__).read()
        assert "class AttentionSignalStore" in source
        assert "class AttentionSignal" in source
        assert "get_ranking_weight" in source
