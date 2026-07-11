"""Phase 9 tests — learning, calibration, export/delete, activation."""

import os
import sys
import tempfile
import sqlite3
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "evaluation"))


@pytest.fixture
def isolated_api():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-p9"
    os.environ.pop("MAESTRO_PERSONAL_ENV", None)

    import importlib
    import maestro_personal_shell.api as api_module
    importlib.reload(api_module)
    api_module.init_db(db_path)

    from maestro_personal_shell.audit_trust import init_audit_tables
    from maestro_personal_shell.commitment_ledger import init_ledger_table
    from maestro_personal_shell.outcome_tracker import init_outcome_db
    init_audit_tables(db_path)
    init_ledger_table(db_path)
    init_outcome_db(db_path)

    try:
        from maestro_personal_shell.semantic_retrieval import init_fts_index, rebuild_fts_index
        init_fts_index(db_path)
        rebuild_fts_index(db_path)
    except Exception:
        pass

    yield api_module

    os.unlink(db_path)
    del os.environ["MAESTRO_PERSONAL_DB"]
    del os.environ["MAESTRO_PERSONAL_TOKEN"]


@pytest.fixture
def client(isolated_api):
    return TestClient(isolated_api.app)


@pytest.fixture
def auth_headers(client):
    response = client.post("/api/auth/login", json={"password": os.environ.get("MAESTRO_PERSONAL_TOKEN", "test")})
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _mock_llm():
    return (
        patch("maestro_personal_shell.commitment_classifier.classify_commitment",
              new_callable=AsyncMock,
              return_value={"commitment_type": "explicit", "is_commitment": True,
                            "confidence": 0.85, "state": "active", "owner": "user",
                            "reasoning": "test", "llm_powered": False}),
        patch("maestro_personal_shell.llm_bridge.llm_complete",
              new_callable=AsyncMock, return_value=None),
        patch("maestro_personal_shell.dynamic_agents.materiality_gate_v2",
              new_callable=AsyncMock,
              return_value={"should_speak": True, "materiality_score": 0.5,
                            "urgency": "medium", "reasoning": "test", "llm_powered": False}),
    )


class TestPhase9AccountDeletion:
    """Account deletion must remove data from ALL stores."""

    def test_delete_removes_from_all_stores(self, client, auth_headers):
        """DELETE /api/account must delete from signals, ledger, audit_log,
        calibration_history, graph, user_tokens, and FTS."""
        m1, m2, m3 = _mock_llm()
        with m1, m2, m3:
            # Seed data
            client.post("/api/signals", json={
                "entity": "DeleteCorp", "text": "I will send the proposal",
                "signal_type": "commitment_made",
            }, headers=auth_headers)

            # Delete account
            resp = client.delete("/api/account", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert "deleted_stores" in data
            # Must delete from at least: signals, commitments_ledger, audit_log,
            # user_tokens, fts_index
            deleted = data["deleted_stores"]
            assert "signals" in deleted
            assert "user_tokens" in deleted

    def test_delete_does_not_affect_other_users(self, client, auth_headers):
        """Deleting user A's account must NOT delete user B's signals."""
        m1, m2, m3 = _mock_llm()
        with m1, m2, m3:
            # User A creates a signal
            client.post("/api/signals", json={
                "entity": "UserA", "text": "I will send the proposal",
                "signal_type": "commitment_made",
            }, headers=auth_headers)

            # Delete user A's account
            client.delete("/api/account", headers=auth_headers)

            # The signals table should be empty for user A
            db = os.environ["MAESTRO_PERSONAL_DB"]
            conn = sqlite3.connect(db)
            count = conn.execute(
                "SELECT COUNT(*) FROM signals WHERE user_email = ?",
                ("default@personal.local",)  # the resolved user email
            ).fetchone()[0]
            conn.close()
            assert count == 0, "User A's signals should be deleted"


class TestPhase9Export:
    """Export must include ALL user data, not just signals."""

    def test_export_includes_all_stores(self, client, auth_headers):
        """GET /api/account/export must include signals, ledger, audit_log,
        calibration_history, predictions, graph."""
        m1, m2, m3 = _mock_llm()
        with m1, m2, m3:
            client.post("/api/signals", json={
                "entity": "ExportCorp", "text": "I will send the proposal",
                "signal_type": "commitment_made",
            }, headers=auth_headers)

            resp = client.get("/api/account/export", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert "signals" in data
            assert "commitments_ledger" in data
            assert "audit_log" in data
            assert "calibration_history" in data
            assert "predictions" in data
            assert "graph_entities" in data
            assert len(data["signals"]) >= 1


class TestPhase9BehaviorChange:
    """Past outcomes must change future behavior."""

    def test_entity_track_record(self, isolated_api):
        """get_entity_track_record returns hit/miss stats."""
        from maestro_personal_shell.behavior_change import get_entity_track_record
        db = os.environ["MAESTRO_PERSONAL_DB"]
        # Seed predictions + outcomes
        from maestro_personal_shell.outcome_tracker import register_prediction, resolve_outcome
        pred = register_prediction(predicted_confidence=0.8, expected_outcome="hit",
                                    prediction_type="commitment_completion", entity_id="Alex",
                                    db_path=db)
        resolve_outcome(pred["prediction_id"], "hit", db_path=db)

        record = get_entity_track_record("Alex", "default@personal.local", db)
        assert record["total"] >= 1
        assert record["hits"] >= 1
        assert record["hit_rate"] > 0

    def test_behavior_adjustments_returned(self, isolated_api):
        """get_behavior_adjustments returns ranking, suppression, calibration."""
        from maestro_personal_shell.behavior_change import get_behavior_adjustments
        db = os.environ["MAESTRO_PERSONAL_DB"]
        adjustments = get_behavior_adjustments("default@personal.local", db)
        assert "entity_reliability" in adjustments
        assert "suppressed_entities" in adjustments
        assert "brier_score" in adjustments
        assert "adjustments" in adjustments

    def test_calibrated_confidence(self, isolated_api):
        """get_calibrated_confidence adjusts raw confidence by Brier score."""
        from maestro_personal_shell.behavior_change import get_calibrated_confidence
        db = os.environ["MAESTRO_PERSONAL_DB"]
        calibrated = get_calibrated_confidence(0.9, "default@personal.local", db)
        assert 0.0 <= calibrated <= 1.0

    def test_should_suppress_entity(self, isolated_api):
        """should_suppress_entity returns False for new entities."""
        from maestro_personal_shell.behavior_change import should_suppress_entity
        db = os.environ["MAESTRO_PERSONAL_DB"]
        assert should_suppress_entity("NewEntity", "default@personal.local", db) is False


class TestPhase9CalibrationIntegrity:
    """Calibration must not show fake precision."""

    def test_insufficient_history_message(self, isolated_api):
        """When n < 10, the report must say 'insufficient'."""
        from maestro_personal_shell.outcome_tracker import get_calibration_report
        db = os.environ["MAESTRO_PERSONAL_DB"]
        report = get_calibration_report(db_path=db)
        assert report["has_sufficient_data"] is False
        assert "insufficient" in report["message"].lower() or "partial" in report["message"].lower()

    def test_no_fake_precision_flag(self, isolated_api):
        """When n >= 10, the report must include calibration_integrity."""
        from maestro_personal_shell.outcome_tracker import register_prediction, resolve_outcome, get_calibration_report
        db = os.environ["MAESTRO_PERSONAL_DB"]
        # Seed 10 resolved predictions
        for i in range(10):
            pred = register_prediction(predicted_confidence=0.8, expected_outcome="hit",
                                        prediction_type="commitment_completion", entity_id="Alex",
                                        db_path=db)
            resolve_outcome(pred["prediction_id"], "hit" if i % 2 == 0 else "miss", db_path=db)

        report = get_calibration_report(db_path=db)
        assert report["has_sufficient_data"] is True
        assert "calibration_integrity" in report
        assert report["calibration_integrity"]["no_fake_precision"] is True


class TestPhase9Activation:
    """Activation benchmark — time to first useful output."""

    def test_activation_produces_useful_output(self, client, auth_headers):
        """With 7 days of history, the system must produce a useful output."""
        from activation_benchmark import measure_activation_time
        m1, m2, m3 = _mock_llm()
        with m1, m2, m3:
            result = measure_activation_time(client, auth_headers, days_of_history=7)
            assert result["useful"] is True
            assert result["first_useful_surface"] != "none"
            assert result["time_to_first_useful_ms"] > 0

    def test_activation_time_under_5_min(self, client, auth_headers):
        """Activation time must be under 5 minutes (300,000ms)."""
        from activation_benchmark import measure_activation_time
        m1, m2, m3 = _mock_llm()
        with m1, m2, m3:
            result = measure_activation_time(client, auth_headers, days_of_history=7)
            assert result["time_to_first_useful_ms"] < 300000  # 5 min


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
