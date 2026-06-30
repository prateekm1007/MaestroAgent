"""Tests for the Prediction Lifecycle — closed learning loop."""

import os
import tempfile
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from maestro_api.main import create_app
from maestro_api.oem_state import oem_state, import_state
from maestro_oem.prediction_lifecycle import (
    PredictionRecorder,
    PredictionResolver,
    ExplainableConfidence,
    ClosedLoopLearningManager,
)
from maestro_oem.learning import CalibrationEngine


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        yield path
    finally:
        if os.path.exists(path):
            os.unlink(path)


@pytest.fixture
def client(tmp_path, monkeypatch):
    import pathlib
    app_dir = str(pathlib.Path(__file__).resolve().parents[3])
    monkeypatch.setattr("maestro_api.oem_state._IMPORT_DB_PATH", str(tmp_path / "test_import.db"))
    monkeypatch.setenv("MAESTRO_APP_DIR", app_dir)
    monkeypatch.setenv("MAESTRO_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("MAESTRO_ADMIN_PASSWORD", "test")
    monkeypatch.setenv("MAESTRO_RATE_LIMIT_RPM", "10000")

    import_state._initialized = False
    import_state.store = None
    import_state.oauth = None
    import_state.connections = None
    import_state.tracker = None
    import_state.factory = None
    import_state.engine = None

    app = create_app(db_path=str(tmp_path / "maestro.db"))
    with TestClient(app) as c:
        yield c


# ═══════════════════════════════════════════════════════════════════════════
# 1. PREDICTION RECORDER
# ═══════════════════════════════════════════════════════════════════════════

class TestPredictionRecorder:
    def test_create_prediction(self, db_path):
        recorder = PredictionRecorder(db_path)
        pred_id = recorder.create_prediction(
            prediction_type="recommendation",
            entity_id="test-rec",
            recommendation="Hire 3 engineers",
            expected_outcome="P1 risk decreases",
            confidence=0.8,
            linked_laws=["L-0001"],
        )
        assert pred_id.startswith("pred-")
        
        pred = recorder.get_prediction(pred_id)
        assert pred is not None
        assert pred["status"] == "pending"
        assert pred["confidence"] == 0.8
        assert pred["linked_laws"] == ["L-0001"]

    def test_get_pending(self, db_path):
        recorder = PredictionRecorder(db_path)
        recorder.create_prediction("recommendation", "e1", "rec1", "outcome1", 0.7)
        recorder.create_prediction("risk", "e2", "rec2", "outcome2", 0.6)
        pending = recorder.get_pending_predictions()
        assert len(pending) == 2

    def test_list_by_status(self, db_path):
        recorder = PredictionRecorder(db_path)
        pid = recorder.create_prediction("recommendation", "e1", "rec1", "outcome1", 0.7)
        # Manually resolve
        with recorder._lock, recorder._connect() as cur:
            cur.execute("UPDATE predictions SET status = 'correct' WHERE prediction_id = ?", (pid,))
        correct = recorder.list_predictions(status="correct")
        assert len(correct) == 1
        pending = recorder.list_predictions(status="pending")
        assert len(pending) == 0

    def test_prediction_has_provenance(self, db_path):
        """No prediction should exist without provenance."""
        recorder = PredictionRecorder(db_path)
        pred_id = recorder.create_prediction(
            prediction_type="recommendation",
            entity_id="test",
            recommendation="Do X",
            expected_outcome="X happens",
            confidence=0.5,
            linked_laws=["L-0001", "L-0002"],
            linked_patterns=["p1"],
            linked_receipts=["r1"],
        )
        pred = recorder.get_prediction(pred_id)
        assert pred["linked_laws"] == ["L-0001", "L-0002"]
        assert pred["linked_patterns"] == ["p1"]
        assert pred["linked_receipts"] == ["r1"]


# ═══════════════════════════════════════════════════════════════════════════
# 2. PREDICTION RESOLVER
# ═══════════════════════════════════════════════════════════════════════════

class TestPredictionResolver:
    def test_resolve_simulation_prediction(self, db_path):
        """Simulation predictions should resolve when metric is close to predicted."""
        recorder = PredictionRecorder(db_path)
        cal = CalibrationEngine(db_path)
        resolver = PredictionResolver(recorder, cal)

        # Create a simulation prediction
        pred_id = recorder.create_prediction(
            prediction_type="simulation",
            entity_id="sim-test",
            recommendation="Predicted P1 risk = 0.35",
            expected_outcome="P1 risk should be close to 0.35",
            confidence=0.8,
            expected_metric="p1_cluster_risk",
            baseline_value=0.45,
            predicted_value=0.35,
            expected_timeframe="1d",  # Short for testing
        )

        # Mock model with matching metric
        class MockModel:
            class health:
                p1_cluster_risk = 0.36  # Close to predicted 0.35
                incident_rate = 3
                decision_velocity_days = 0.8
                release_frequency = 0.1

        result = resolver.check_pending(MockModel(), [])
        assert result["resolved"] >= 1
        
        pred = recorder.get_prediction(pred_id)
        assert pred["status"] == "correct"

    def test_resolve_incorrect_simulation(self, db_path):
        """Simulations that are far off should resolve as incorrect."""
        recorder = PredictionRecorder(db_path)
        cal = CalibrationEngine(db_path)
        resolver = PredictionResolver(recorder, cal)

        pred_id = recorder.create_prediction(
            prediction_type="simulation",
            entity_id="sim-wrong",
            recommendation="Predicted P1 risk = 0.1",
            expected_outcome="P1 risk should be 0.1",
            confidence=0.9,
            expected_metric="p1_cluster_risk",
            baseline_value=0.45,
            predicted_value=0.1,
            expected_timeframe="1d",
        )

        class MockModel:
            class health:
                p1_cluster_risk = 0.8  # Far from predicted 0.1
                incident_rate = 3
                decision_velocity_days = 0.8
                release_frequency = 0.1

        resolver.check_pending(MockModel(), [])
        pred = recorder.get_prediction(pred_id)
        assert pred["status"] == "incorrect"

    def test_expire_old_predictions(self, db_path):
        """Predictions past their expiry should be expired."""
        recorder = PredictionRecorder(db_path)
        cal = CalibrationEngine(db_path)
        resolver = PredictionResolver(recorder, cal)

        # Create with very short expiry
        pred_id = recorder.create_prediction(
            prediction_type="recommendation",
            entity_id="old-pred",
            recommendation="Test",
            expected_outcome="Test",
            confidence=0.5,
            expected_timeframe="1m",  # 1 minute
        )

        # Manually set expiry to past
        with recorder._lock, recorder._connect() as cur:
            cur.execute(
                "UPDATE predictions SET expires_at = ? WHERE prediction_id = ?",
                ("2020-01-01T00:00:00+00:00", pred_id),
            )

        expired = resolver.expire_old_predictions()
        assert expired >= 1
        pred = recorder.get_prediction(pred_id)
        assert pred["status"] == "expired"


# ═══════════════════════════════════════════════════════════════════════════
# 3. EXPLAINABLE CONFIDENCE
# ═══════════════════════════════════════════════════════════════════════════

class TestExplainableConfidence:
    def test_explain_high_confidence(self, db_path):
        recorder = PredictionRecorder(db_path)
        cal = CalibrationEngine(db_path)
        explainer = ExplainableConfidence(recorder, cal)

        result = explainer.explain("L-0001", 0.95, "law")
        assert result["level"] == "HIGH"
        assert "explanation" in result
        assert "evidence" in result
        assert "what_changes_confidence" in result

    def test_explain_low_confidence(self, db_path):
        recorder = PredictionRecorder(db_path)
        cal = CalibrationEngine(db_path)
        explainer = ExplainableConfidence(recorder, cal)

        result = explainer.explain("L-0001", 0.3, "law")
        assert result["level"] == "LOW"

    def test_explain_with_history(self, db_path):
        """After predictions are resolved, explanation should include history."""
        recorder = PredictionRecorder(db_path)
        cal = CalibrationEngine(db_path)
        resolver = PredictionResolver(recorder, cal)

        # Create and resolve predictions
        for i in range(5):
            pid = recorder.create_prediction(
                prediction_type="law", entity_id="L-test",
                recommendation="Test", expected_outcome="Test",
                confidence=0.8, expected_timeframe="1d",
            )

        class MockModel:
            class health:
                p1_cluster_risk = 0.45
                incident_rate = 3
                decision_velocity_days = 0.8
                release_frequency = 0.1
            laws = {}

        resolver.check_pending(MockModel(), [])

        explainer = ExplainableConfidence(recorder, cal)
        result = explainer.explain("L-test", 0.8, "law")
        assert result["evidence"]["total_predictions"] > 0


# ═══════════════════════════════════════════════════════════════════════════
# 4. CLOSED-LOOP LEARNING MANAGER
# ═══════════════════════════════════════════════════════════════════════════

class TestClosedLoopLearning:
    def test_recommendation_creates_prediction(self, db_path):
        """When a recommendation is surfaced, a prediction is auto-created."""
        cal = CalibrationEngine(db_path)
        manager = ClosedLoopLearningManager(db_path, None, [], cal)

        class MockRec:
            title = "Test recommendation"
            recommendation = "Do X"
            impact = "X improves"
            confidence = 0.8
            linked_laws = ["L-0001"]
            urgency = "normal"

        pred_id = manager.on_recommendation_surfaced(MockRec(), None)
        assert pred_id.startswith("pred-")

        pred = manager.recorder.get_prediction(pred_id)
        assert pred["prediction_type"] == "recommendation"
        assert pred["status"] == "pending"

    def test_improvement_report(self, db_path):
        """The improvement dashboard should show learning metrics."""
        cal = CalibrationEngine(db_path)
        manager = ClosedLoopLearningManager(db_path, None, [], cal)

        # Create some predictions
        for i in range(3):
            manager.on_recommendation_surfaced(
                type("R", (), {
                    "title": f"Rec {i}", "recommendation": "Do X",
                    "impact": "X improves", "confidence": 0.7,
                    "linked_laws": [], "urgency": "normal",
                }),
                None,
            )

        report = manager.get_improvement_report()
        assert report["summary"]["total_predictions"] >= 3
        assert report["summary"]["pending"] >= 3
        assert "improvement_evidence" in report
        assert "is_learning" in report["improvement_evidence"]

    def test_feedback_resolves_predictions(self, db_path):
        """CEO feedback should resolve related predictions."""
        cal = CalibrationEngine(db_path)
        manager = ClosedLoopLearningManager(db_path, None, [], cal)

        # Create a prediction
        pred_id = manager.on_recommendation_surfaced(
            type("R", (), {
                "title": "Test Rec", "recommendation": "Do X",
                "impact": "X improves", "confidence": 0.7,
                "linked_laws": [], "urgency": "normal",
            }),
            None,
        )

        # CEO rejects
        manager.on_feedback("recommendation", "Test Rec", "reject", 0.7, 0.3, "Wrong")

        pred = manager.recorder.get_prediction(pred_id)
        assert pred["status"] == "incorrect"


# ═══════════════════════════════════════════════════════════════════════════
# 5. API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

class TestPredictionAPI:
    def test_get_predictions(self, client):
        resp = client.get("/api/oem/predictions")
        assert resp.status_code == 200
        assert "predictions" in resp.json()

    def test_get_improvement_report(self, client):
        resp = client.get("/api/oem/improvement")
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        assert "improvement_evidence" in data

    def test_resolve_predictions(self, client):
        resp = client.post("/api/oem/predictions/resolve")
        assert resp.status_code == 200
        assert "predictions_checked" in resp.json()

    def test_explain_confidence(self, client):
        resp = client.get("/api/oem/confidence/explain?entity_id=L-0001&confidence=0.9&entity_type=law")
        assert resp.status_code == 200
        data = resp.json()
        assert "level" in data
        assert "explanation" in data

    def test_recommendations_auto_create_predictions(self, client):
        """Getting recommendations should auto-create predictions."""
        # First get recommendations (creates predictions)
        resp = client.get("/api/oem/recommendations")
        recs = resp.json().get("recommendations", [])
        
        # Then check predictions exist
        resp = client.get("/api/oem/predictions")
        preds = resp.json().get("predictions", [])
        
        if recs:
            assert len(preds) >= len(recs)
            # Each prediction should have provenance
            for p in preds:
                assert p["entity_id"]
                assert p["recommendation"]
                assert p["confidence"] is not None

    def test_simulator_endpoints_match(self, client):
        """Both /simulator and /simulate must return identical confidence."""
        r1 = client.post("/api/oem/simulator", json={"inputs": {"hire_count": 5}})
        r2 = client.post("/api/oem/simulate", json={"inputs": {"hire_count": 5}})
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["confidence"] == r2.json()["confidence"]
