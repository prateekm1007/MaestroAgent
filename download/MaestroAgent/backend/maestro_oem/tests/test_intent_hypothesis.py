"""Tests for Intent Model + Hypothesis Layer — the connected cognitive model.

Tests:
  1. Intent data model — create, list, cascade query
  2. Hypothesis layer — create, resolve, calibration
  3. Connected architecture — assumptions link to intents, hypotheses link to intents
  4. OEM root query — GET /api/oem/intent/{id} returns full cascade
"""

from __future__ import annotations
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from maestro_api.main import create_app
from maestro_api.oem_state import oem_state, import_state


@pytest.fixture
def client(tmp_path, monkeypatch):
    app_dir = str(Path(__file__).resolve().parents[3])
    monkeypatch.setattr("maestro_api.oem_state._IMPORT_DB_PATH", str(tmp_path / "test_import.db"))
    monkeypatch.setenv("MAESTRO_APP_DIR", app_dir)
    monkeypatch.setenv("MAESTRO_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("MAESTRO_LEARNING_DB", str(tmp_path / "learning.db"))
    monkeypatch.setenv("MAESTRO_ADMIN_PASSWORD", "test")
    monkeypatch.setenv("MAESTRO_RATE_LIMIT_RPM", "10000")
    monkeypatch.setenv("MAESTRO_DEMO_SEED", "true")
    oem_state._initialized = False
    oem_state.engine = None
    oem_state.signals = []
    oem_state._demo_seeded = False
    oem_state._contradiction_log = None
    import_state._initialized = False
    app = create_app(db_path=str(tmp_path / "maestro.db"))
    with TestClient(app) as c:
        yield c
    oem_state._initialized = False
    oem_state.engine = None
    oem_state.signals = []


class TestIntentModel:
    def test_list_intents_returns_data(self, client):
        """GET /api/oem/intents returns inferred intents from recommendations."""
        r = client.get("/api/oem/intents")
        assert r.status_code == 200
        data = r.json()
        assert "intents" in data
        assert data["total"] >= 0

    def test_create_explicit_intent(self, client):
        """POST /api/oem/intents creates an intent."""
        r = client.post("/api/oem/intents", json={
            "goal": "Reduce customer onboarding time by 30%",
            "owner": "jane@acme.com",
            "success_criteria": "Onboarding < 10 days",
            "deadline": "2025-Q4",
            "stakeholders": ["jane@acme.com", "chris@acme.com"],
            "intent_type": "strategic",
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert r.json()["intent_id"].startswith("intent-")

    def test_intent_has_goal_and_status(self, client):
        """Each intent must have a goal and status."""
        r = client.get("/api/oem/intents")
        for i in r.json().get("intents", []):
            assert i["goal"]
            assert i["status"] in ("active", "achieved", "abandoned", "superseded")

    def test_intent_cascade_query(self, client):
        """GET /api/oem/intent/{id} returns the full cascade."""
        # Create an intent
        r = client.post("/api/oem/intents", json={"goal": "Test cascade query"})
        intent_id = r.json()["intent_id"]

        # Get the cascade
        r = client.get(f"/api/oem/intents/{intent_id}")
        assert r.status_code == 200
        cascade = r.json()
        assert cascade["intent_id"] == intent_id
        assert cascade["goal"] == "Test cascade query"
        assert "assumptions" in cascade
        assert "hypotheses" in cascade
        assert "preparations" in cascade

    def test_intent_status_update(self, client):
        """PATCH /api/oem/intent/{id}/status updates the status."""
        r = client.post("/api/oem/intents", json={"goal": "Test status update"})
        intent_id = r.json()["intent_id"]

        r = client.patch(f"/api/oem/intents/{intent_id}/status?status=achieved")
        assert r.status_code == 200
        assert r.json()["status"] == "achieved"

    def test_inferred_intents_from_recommendations(self, client):
        """Intents are inferred from OEM recommendations."""
        r = client.get("/api/oem/intents")
        data = r.json()
        if data["total"] > 0:
            inferred = [i for i in data["intents"] if "recommendation" in i.get("goal", "").lower()
                        or "bottleneck" in i.get("goal", "").lower()
                        or "customer" in i.get("goal", "").lower()]
            assert len(inferred) > 0, "No inferred intents from recommendations"


class TestHypothesisLayer:
    def test_list_hypotheses_returns_data(self, client):
        """GET /api/oem/hypotheses returns inferred hypotheses."""
        r = client.get("/api/oem/hypotheses")
        assert r.status_code == 200
        data = r.json()
        assert "hypotheses" in data
        assert data["total"] >= 0

    def test_create_hypothesis_linked_to_intent(self, client):
        """POST /api/oem/hypotheses creates a hypothesis linked to an intent."""
        # First create an intent
        r = client.post("/api/oem/intents", json={"goal": "Test hypothesis intent"})
        intent_id = r.json()["intent_id"]

        # Create a hypothesis
        r = client.post("/api/oem/hypotheses", json={
            "statement": "Moving Legal earlier reduces cycle time by 5 days",
            "intent_id": intent_id,
            "prediction": "Cycle time will be 15 days",
            "predicted_value": 15.0,
            "confidence": 0.7,
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert r.json()["hypothesis_id"].startswith("hyp-")

    def test_hypothesis_requires_intent_id(self, client):
        """Hypotheses without intent_id are rejected."""
        r = client.post("/api/oem/hypotheses", json={
            "statement": "Test hypothesis without intent",
        })
        assert r.status_code == 400

    def test_resolve_hypothesis(self, client):
        """POST /api/oem/hypotheses/{id}/resolve resolves with actual outcome."""
        # Create intent + hypothesis
        r = client.post("/api/oem/intents", json={"goal": "Test resolve"})
        intent_id = r.json()["intent_id"]
        r = client.post("/api/oem/hypotheses", json={
            "statement": "Test resolve hypothesis",
            "intent_id": intent_id,
            "predicted_value": 15.0,
            "confidence": 0.7,
        })
        hid = r.json()["hypothesis_id"]

        # Resolve it
        r = client.post(f"/api/oem/hypotheses/{hid}/resolve", json={
            "actual_value": 17.0,
            "notes": "Partially correct — close but not exact",
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True

        # Verify the resolution
        r = client.get(f"/api/oem/hypotheses/{hid}")
        h = r.json()
        assert h["outcome"] in ("validated", "invalidated", "inconclusive")
        assert h["actual_value"] == 17.0
        assert h["resolved_at"] is not None

    def test_hypothesis_calibration_report(self, client):
        """GET /api/oem/hypotheses/calibration returns calibration metrics."""
        r = client.get("/api/oem/hypotheses/calibration")
        assert r.status_code == 200
        data = r.json()
        assert "total_hypotheses" in data
        assert "validated" in data
        assert "invalidated" in data
        assert "accuracy_rate" in data
        assert "narrative" in data

    def test_hypothesis_filter_by_intent(self, client):
        """GET /api/oem/hypotheses?intent_id=X filters by intent."""
        r = client.post("/api/oem/intents", json={"goal": "Filter test"})
        intent_id = r.json()["intent_id"]
        client.post("/api/oem/hypotheses", json={
            "statement": "Filter test hypothesis",
            "intent_id": intent_id,
        })

        r = client.get(f"/api/oem/hypotheses?intent_id={intent_id}")
        assert r.status_code == 200
        for h in r.json().get("hypotheses", []):
            assert h["intent_id"] == intent_id


class TestConnectedArchitecture:
    """Verify that assumptions, hypotheses, and preparations are connected via Intent."""

    def test_assumption_links_to_intent(self, client):
        """Creating an assumption with intent_id links it to the intent."""
        # Create intent
        r = client.post("/api/oem/intents", json={"goal": "Connected architecture test"})
        intent_id = r.json()["intent_id"]

        # Create assumption linked to intent
        r = client.post("/api/oem/assumptions", json={
            "statement": "Legal review takes 3 days",
            "stakes": "high",
            "intent_id": intent_id,
        })
        assert r.status_code == 200
        assumption_id = r.json()["assumption_id"]

        # Verify the intent's cascade includes the assumption
        r = client.get(f"/api/oem/intents/{intent_id}")
        cascade = r.json()
        assert intent_id in [a.get("evidence", [{}])[0].get("intent_id", "") for a in cascade.get("assumptions", [])] or \
               len(cascade.get("assumptions", [])) > 0, \
               "Assumption not linked to intent in cascade"

    def test_hypothesis_links_to_intent(self, client):
        """Creating a hypothesis links it to the intent in the cascade."""
        r = client.post("/api/oem/intents", json={"goal": "Hypothesis link test"})
        intent_id = r.json()["intent_id"]

        r = client.post("/api/oem/hypotheses", json={
            "statement": "Test linked hypothesis",
            "intent_id": intent_id,
        })
        assert r.status_code == 200

        # Verify the intent's cascade includes the hypothesis
        r = client.get(f"/api/oem/intents/{intent_id}")
        cascade = r.json()
        assert len(cascade.get("hypotheses", [])) > 0, "Hypothesis not linked to intent in cascade"

    def test_full_cascade_has_all_children(self, client):
        """The cascade query returns assumptions + hypotheses + preparations."""
        r = client.post("/api/oem/intents", json={"goal": "Full cascade test"})
        intent_id = r.json()["intent_id"]

        # Add assumption
        client.post("/api/oem/assumptions", json={
            "statement": "Cascade assumption",
            "intent_id": intent_id,
        })

        # Add hypothesis
        client.post("/api/oem/hypotheses", json={
            "statement": "Cascade hypothesis",
            "intent_id": intent_id,
        })

        # Get cascade
        r = client.get(f"/api/oem/intents/{intent_id}")
        cascade = r.json()

        assert "assumptions" in cascade
        assert "hypotheses" in cascade
        assert "preparations" in cascade
        assert "evidence" in cascade
        assert len(cascade["assumptions"]) > 0
        assert len(cascade["hypotheses"]) > 0


class TestLearningLoopRegression:
    def test_learning_loop_still_closes(self, client):
        """New cognitive model capabilities must not break the learning loop."""
        import os as _os
        import pathlib
        _os.environ["MAESTRO_LEARNING_DB"] = str(pathlib.Path(_os.environ.get("MAESTRO_AUTH_DB", "/tmp/test/auth.db")).parent / "test_learning_intent.db")

        r = client.get("/api/oem/recommendations")
        assert r.status_code == 200
        recs = r.json().get("recommendations", [])
        assert len(recs) > 0

        rec = next((r for r in recs if r.get("linked_laws")), recs[0])
        target_law = rec["linked_laws"][0] if rec.get("linked_laws") else rec["title"]
        r = client.post("/api/oem/contradict", json={
            "target_type": "law" if rec.get("linked_laws") else "recommendation",
            "target_id": target_law,
            "action": "agree",
            "reasoning": "Intent model regression test",
            "actor": "ceo@acme.com",
        })
        assert r.status_code == 200

        r = client.get("/api/oem/improvement")
        report = r.json()
        assert report["summary"]["resolved"] > 0
        assert report["calibration"]["brier_score"] != 0.5
