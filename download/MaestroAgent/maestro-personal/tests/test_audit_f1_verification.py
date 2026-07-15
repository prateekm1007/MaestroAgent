"""
Verify Finding 1 from the independent audit (CRITICAL cross-user prediction
leak) is FIXED at current HEAD.

The auditor at eb80a91 found that Alice could resolve Bob's prediction and
both users saw identical calibration. This was fixed at 3dfe17a (P20) and
a95e3c5 (IDOR). This test proves the fix by execution.
"""

import sys
import os
import tempfile
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
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-audit-f1"
    os.environ.pop("MAESTRO_PERSONAL_ENV", None)

    import importlib
    import maestro_personal_shell.api as api_module
    importlib.reload(api_module)
    api_module.init_db(db_path)

    yield api_module
    os.unlink(db_path)
    os.environ.pop("MAESTRO_PERSONAL_DB", None)
    os.environ.pop("MAESTRO_PERSONAL_TOKEN", None)


@pytest.fixture
def client(isolated_api):
    return TestClient(isolated_api.app)


def _login(client, email):
    resp = client.post("/api/auth/login", json={
        "user_email": email,
        "password": os.environ["MAESTRO_PERSONAL_TOKEN"],
    })
    return {"Authorization": f"Bearer {resp.json()['token']}"}


class TestCrossUserPredictionIsolation:
    """Finding 1: Alice must NOT be able to resolve Bob's prediction.
    Calibration must be per-user."""

    def test_alice_cannot_resolve_bob_prediction(self, client):
        """Alice POST /api/outcomes with Bob's prediction_id → must fail
        (404 or 403), NOT 200."""
        bob_headers = _login(client, "bob-audit@test.com")
        alice_headers = _login(client, "alice-audit@test.com")

        # Bob registers a prediction
        resp = client.post("/api/predictions", json={
            "predicted_confidence": 0.8,
            "expected_outcome": "hit",
            "prediction_type": "commitment_completion",
            "entity_id": "SecretCorp-Nightfall",
        }, headers=bob_headers)
        assert resp.status_code == 200, resp.text
        bob_pred_id = resp.json()["prediction_id"]

        # Alice tries to resolve Bob's prediction
        resp = client.post("/api/outcomes", json={
            "prediction_id": bob_pred_id,
            "actual_outcome": "miss",
        }, headers=alice_headers)

        assert resp.status_code in (403, 404), (
            f"CRITICAL: Alice was able to resolve Bob's prediction! "
            f"Expected 403/404, got {resp.status_code}: {resp.text}"
        )

    def test_calibration_is_per_user(self, client):
        """Alice and Bob must have DIFFERENT calibration after separate
        prediction/outcome histories."""
        bob_headers = _login(client, "bob-cal@test.com")
        alice_headers = _login(client, "alice-cal@test.com")

        # Bob: 5 predictions, all hits
        for i in range(5):
            resp = client.post("/api/predictions", json={
                "predicted_confidence": 0.9,
                "expected_outcome": "hit",
                "prediction_type": "commitment_completion",
                "entity_id": f"BobEntity{i}",
            }, headers=bob_headers)
            pred_id = resp.json()["prediction_id"]
            client.post("/api/outcomes", json={
                "prediction_id": pred_id,
                "actual_outcome": "hit",
            }, headers=bob_headers)

        # Alice: 5 predictions, all misses
        for i in range(5):
            resp = client.post("/api/predictions", json={
                "predicted_confidence": 0.9,
                "expected_outcome": "hit",
                "prediction_type": "commitment_completion",
                "entity_id": f"AliceEntity{i}",
            }, headers=alice_headers)
            pred_id = resp.json()["prediction_id"]
            client.post("/api/outcomes", json={
                "prediction_id": pred_id,
                "actual_outcome": "miss",
            }, headers=alice_headers)

        bob_cal = client.get("/api/calibration", headers=bob_headers).json()
        alice_cal = client.get("/api/calibration", headers=alice_headers).json()

        bob_resolved = bob_cal.get("counts", {}).get("resolved", 0)
        alice_resolved = alice_cal.get("counts", {}).get("resolved", 0)

        assert bob_resolved == 5, f"Bob should have 5 resolved, got {bob_resolved}"
        assert alice_resolved == 5, f"Alice should have 5 resolved, got {alice_resolved}"

        # Bob's Brier should be low (all hits, predicted 0.9)
        # Alice's Brier should be high (all misses, predicted 0.9)
        bob_brier = bob_cal.get("brier_score", 0)
        alice_brier = alice_cal.get("brier_score", 0)
        assert bob_brier < alice_brier, (
            f"Bob (all hits) should have lower Brier than Alice (all misses). "
            f"Bob={bob_brier}, Alice={alice_brier}"
        )
