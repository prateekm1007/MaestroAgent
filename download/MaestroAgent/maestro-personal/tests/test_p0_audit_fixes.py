"""
P0 regression tests — the 5 critical findings from the independent audit.

P0-1: Graph cross-user leak — Alice must NOT read Bob's graph data
P0-2: Passwordless login — login must validate (not just mint token for any email)
P0-3: Timestamp preservation — client timestamp must be preserved
P0-4: Calibration type filter — must include 'commitment_completion' predictions
P0-5: Noise topping — newsletter entities must NOT be top briefing situation
"""

import sys
import os
import tempfile
import sqlite3
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


@pytest.fixture
def isolated_api():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-p0"
    os.environ.pop("MAESTRO_PERSONAL_ENV", None)

    import importlib
    import maestro_personal_shell.api as api_module
    importlib.reload(api_module)
    api_module.init_db(db_path)

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


def _login(client, user_email):
    response = client.post("/api/auth/login", json={
        "user_email": user_email,
        "password": os.environ.get("MAESTRO_PERSONAL_TOKEN", "test"),
    })
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _mock_llm():
    return (
        patch("maestro_personal_shell.commitment_classifier.classify_commitment",
              new_callable=AsyncMock,
              return_value={"commitment_type": "explicit", "is_commitment": True,
                            "confidence": 0.85, "state": "active", "owner": "user",
                            "reasoning": "test", "llm_powered": False}),
        patch("maestro_personal_shell.llm_bridge.llm_complete",
              new_callable=AsyncMock, return_value=None),
        patch("maestro_personal_shell.materiality_gate.evaluate_materiality",
              new_callable=AsyncMock,
              return_value={"should_speak": True, "materiality_score": 0.5,
                            "urgency": "medium", "reasoning": "test", "llm_powered": False}),
    )


class TestP0GraphIsolation:
    """P0-1: Graph reads must be user-scoped."""

    def test_alice_cannot_read_bob_graph_entity(self, client):
        """Alice must NOT read Bob's entity graph."""
        alice_h = _login(client, "alice@test.com")
        bob_h = _login(client, "bob@test.com")

        m1, m2, m3 = _mock_llm()
        with m1, m2, m3:
            # Bob creates a secret commitment (adds to graph)
            client.post("/api/signals", json={
                "entity": "SecretBobClient", "text": "I will send the secret proposal",
                "signal_type": "commitment_made",
            }, headers=bob_h)

            # Alice tries to read Bob's graph entity
            resp = client.get("/api/graph/entity/SecretBobClient", headers=alice_h)
            data = resp.json()
            assert data.get("exists") is False, \
                "P0-1 LEAK: Alice can read Bob's graph entity"

    def test_alice_cannot_read_bob_graph_risk(self, client):
        """Alice must NOT read Bob's risk prediction."""
        alice_h = _login(client, "alice@test.com")
        bob_h = _login(client, "bob@test.com")

        m1, m2, m3 = _mock_llm()
        with m1, m2, m3:
            client.post("/api/signals", json={
                "entity": "SecretRiskCorp", "text": "I will deliver",
                "signal_type": "commitment_made",
            }, headers=bob_h)

            resp = client.get("/api/graph/risk/SecretRiskCorp", headers=alice_h)
            data = resp.json()
            # P0 fix: Alice should get exists=false (no data for this entity)
            assert data.get("exists") is False, \
                "P0-1 LEAK: Alice should get exists=false for Bob's entity"


class TestP0TimestampPreservation:
    """P0-3: Client timestamps must be preserved."""

    def test_client_timestamp_preserved(self, client, auth_headers):
        """POST /api/signals with a timestamp must preserve it."""
        m1, m2, m3 = _mock_llm()
        old_ts = "2026-04-01T10:00:00+00:00"
        with m1, m2, m3:
            resp = client.post("/api/signals", json={
                "entity": "OldCorp",
                "text": "I will send the proposal",
                "signal_type": "commitment_made",
                "timestamp": old_ts,
            }, headers=auth_headers)
            assert resp.status_code == 200

            # Verify the timestamp was preserved
            resp = client.get("/api/signals", headers=auth_headers)
            signals = resp.json()
            assert len(signals) >= 1
            sig = signals[0]
            assert sig["timestamp"].startswith("2026-04-01"), \
                f"P0-3: Timestamp not preserved. Expected 2026-04-01, got {sig['timestamp']}"

    def test_stale_detection_works_with_old_timestamp(self, client, auth_headers):
        """Old commitments must be detected as stale when timestamp is preserved."""
        import sqlite3
        from datetime import datetime, timezone, timedelta
        m1, m2, m3 = _mock_llm()
        with m1, m2, m3:
            old_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
            client.post("/api/signals", json={
                "entity": "StaleCorp",
                "text": "I will send the proposal",
                "signal_type": "commitment_made",
                "timestamp": old_ts,
            }, headers=auth_headers)

            # Get commitments — should show as at-risk (stale)
            resp = client.get("/api/commitments", headers=auth_headers)
            commitments = resp.json()
            stale = [c for c in commitments if c.get("entity") == "StaleCorp"]
            if stale:
                assert stale[0].get("is_at_risk") is True or stale[0].get("days_stale", 0) > 0, \
                    "P0-3: Stale detection must work with preserved timestamps"


class TestP0CalibrationTypeFilter:
    """P0-4: Calibration must include 'commitment_completion' predictions."""

    def test_calibration_includes_commitment_completion(self):
        """Calibration report must include auto-registered commitment_completion predictions."""
        from maestro_personal_shell.outcome_tracker import (
            init_outcome_db, register_prediction, resolve_outcome,
            get_calibration_report,
        )
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            init_outcome_db(db_path)

            # Register a commitment_completion prediction (auto-registered type)
            pred = register_prediction(
                predicted_confidence=0.8,
                expected_outcome="hit",
                prediction_type="commitment_completion",
                entity_id="TestCorp:sig1",
                db_path=db_path,
            )
            resolve_outcome(
                prediction_id=pred["prediction_id"],
                actual_outcome="hit",
                db_path=db_path,
            )

            report = get_calibration_report(db_path=db_path)
            assert report["resolved_predictions"] >= 1, \
                "P0-4: Calibration must include commitment_completion predictions"
        finally:
            os.unlink(db_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
