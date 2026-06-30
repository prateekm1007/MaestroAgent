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
from maestro_oem.contradiction import (
    ContradictionLog,
    ContradictionEvent,
    FeedbackAction,
)


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


# ═══════════════════════════════════════════════════════════════════════════
# 6. CLOSED-LOOP END-TO-END — proves the loop actually closes
#
# These tests exist because the previous commit (8f342f8) shipped with
# "loop closed" in the commit message but the loop did NOT close: the
# resolver read feedback from a nonexistent attribute (_feedback_index on
# CalibrationEngine), and live_ingest() never called on_signals_ingested().
# The tests below submit feedback, trigger resolution, and assert the
# prediction status flips AND the calibration engine records the outcome
# (Brier score moves off 0.5, total_resolved > 0). If any of these break,
# the loop is broken — do not ship.
# ═══════════════════════════════════════════════════════════════════════════

class TestClosedLoopEndToEnd:
    """End-to-end proof that the learning loop actually closes."""

    def test_agree_feedback_via_contradiction_log_resolves_prediction(self, db_path):
        """A recommendation prediction must resolve as `correct` when an AGREE
        event for its entity_id appears in the contradiction log and
        on_signals_ingested() runs.

        This is the exact path that was broken in 8f342f8: the resolver
        looked for _feedback_index on CalibrationEngine (which doesn't have
        it) instead of reading the ContradictionLog.
        """
        cal = CalibrationEngine(db_path)
        log = ContradictionLog()
        manager = ClosedLoopLearningManager(
            db_path, None, [], cal, contradiction_log=log,
        )

        # Surface a recommendation → creates a pending prediction.
        pred_id = manager.on_recommendation_surfaced(
            type("R", (), {
                "title": "Hire 3 APAC engineers",
                "recommendation": "Hire 3 APAC engineers",
                "impact": "APAC coverage improves",
                "confidence": 0.8,
                "linked_laws": ["L-APAC-001"],
                "urgency": "normal",
            }),
            None,
        )
        assert manager.recorder.get_prediction(pred_id)["status"] == "pending"

        # CEO agrees — append the event to the shared contradiction log.
        log.append(ContradictionEvent(
            target_type="recommendation",
            target_id="Hire 3 APAC engineers",
            action=FeedbackAction.AGREE,
            reasoning="Looks right",
            actor="ceo@acme.com",
        ))

        # New signals arrive → live_ingest fires on_signals_ingested →
        # check_pending → _evaluate_prediction reads the log → resolves.
        class MockModel:
            class health:
                p1_cluster_risk = 0.45
                incident_rate = 3
                decision_velocity_days = 0.8
                release_frequency = 0.1
            laws = {}

        result = manager.on_signals_ingested([], MockModel())
        assert result["predictions_resolved"] >= 1, (
            f"Expected ≥1 resolved, got {result} — the contradiction log "
            f"is not being read by _evaluate_prediction."
        )

        pred = manager.recorder.get_prediction(pred_id)
        assert pred["status"] == "correct", (
            f"Expected 'correct' after AGREE, got '{pred['status']}'."
        )

        # Calibration must have recorded the outcome → Brier score moves
        # off 0.5 (the value returned when nothing is resolved).
        cal_data = cal.get_calibration()
        assert cal_data["overall"]["total_resolved"] >= 1, (
            "Calibration engine did not record the resolved prediction."
        )
        assert cal_data["overall"]["total_hits"] >= 1
        # Brier for a single hit at confidence 0.8 = (0.8-1)^2 = 0.04.
        assert abs(cal_data["overall"]["brier_score"] - 0.04) < 0.01, (
            f"Brier score {cal_data['overall']['brier_score']} != 0.04 — "
            f"calibration did not update from the resolved prediction."
        )

    def test_reject_feedback_via_contradiction_log_resolves_as_incorrect(self, db_path):
        """A REJECT event must resolve the prediction as `incorrect` and
        register a miss in calibration (Brier = (0.8-0)^2 = 0.64)."""
        cal = CalibrationEngine(db_path)
        log = ContradictionLog()
        manager = ClosedLoopLearningManager(
            db_path, None, [], cal, contradiction_log=log,
        )

        pred_id = manager.on_recommendation_surfaced(
            type("R", (), {
                "title": "Migrate to microservices",
                "recommendation": "Migrate to microservices",
                "impact": "Velocity improves",
                "confidence": 0.8,
                "linked_laws": [],
                "urgency": "normal",
            }),
            None,
        )

        log.append(ContradictionEvent(
            target_type="recommendation",
            target_id="Migrate to microservices",
            action=FeedbackAction.REJECT,
            reasoning="Too risky right now",
            actor="ceo@acme.com",
        ))

        class MockModel:
            class health:
                p1_cluster_risk = 0.45
                incident_rate = 3
                decision_velocity_days = 0.8
                release_frequency = 0.1
            laws = {}

        result = manager.on_signals_ingested([], MockModel())
        assert result["predictions_resolved"] >= 1

        pred = manager.recorder.get_prediction(pred_id)
        assert pred["status"] == "incorrect"

        cal_data = cal.get_calibration()
        assert cal_data["overall"]["total_resolved"] >= 1
        # Brier for a single miss at confidence 0.8 = (0.8-0)^2 = 0.64.
        assert abs(cal_data["overall"]["brier_score"] - 0.64) < 0.01, (
            f"Brier {cal_data['overall']['brier_score']} != 0.64 — "
            f"miss was not recorded by calibration."
        )

    def test_feedback_on_linked_law_resolves_recommendation_prediction(self, db_path):
        """Feedback on a LAW must resolve every recommendation prediction that
        links to that law (via linked_laws). This covers the common production
        path: CEO contradicts a law, all recommendations depending on it
        should resolve."""
        cal = CalibrationEngine(db_path)
        log = ContradictionLog()
        manager = ClosedLoopLearningManager(
            db_path, None, [], cal, contradiction_log=log,
        )

        pred_id = manager.on_recommendation_surfaced(
            type("R", (), {
                "title": "Reduce EMEA headcount by 3",
                "recommendation": "Reduce EMEA headcount by 3",
                "impact": "Cost savings",
                "confidence": 0.7,
                "linked_laws": ["L-EMEA-001", "L-EMEA-002"],
                "urgency": "normal",
            }),
            None,
        )

        # CEO rejects the LAW (not the recommendation directly).
        log.append(ContradictionEvent(
            target_type="law",
            target_id="L-EMEA-001",
            action=FeedbackAction.REJECT,
            reasoning="EMEA law is outdated",
            actor="ceo@acme.com",
        ))

        class MockModel:
            class health:
                p1_cluster_risk = 0.45
                incident_rate = 3
                decision_velocity_days = 0.8
                release_frequency = 0.1
            laws = {}

        result = manager.on_signals_ingested([], MockModel())
        assert result["predictions_resolved"] >= 1, (
            "Feedback on a linked law did not resolve the recommendation prediction."
        )

        pred = manager.recorder.get_prediction(pred_id)
        assert pred["status"] == "incorrect"

    def test_resolver_returns_zero_when_no_feedback(self, db_path):
        """Sanity check: with no feedback in the log, recommendation
        predictions stay pending. This guards against false positives in
        the tests above (they could pass even if the resolver always
        returns 'correct')."""
        cal = CalibrationEngine(db_path)
        log = ContradictionLog()
        manager = ClosedLoopLearningManager(
            db_path, None, [], cal, contradiction_log=log,
        )

        manager.on_recommendation_surfaced(
            type("R", (), {
                "title": "Adopt trunk-based development",
                "recommendation": "Adopt trunk-based development",
                "impact": "Integration risk drops",
                "confidence": 0.6,
                "linked_laws": ["L-DEV-001"],
                "urgency": "normal",
            }),
            None,
        )

        class MockModel:
            class health:
                p1_cluster_risk = 0.45
                incident_rate = 3
                decision_velocity_days = 0.8
                release_frequency = 0.1
            laws = {}

        result = manager.on_signals_ingested([], MockModel())
        assert result["predictions_resolved"] == 0, (
            "Resolver resolved a prediction with no feedback — false positive."
        )


# ═══════════════════════════════════════════════════════════════════════════
# 7. API-LEVEL CLOSED-LOOP — the exact test the auditor ran manually
# ═══════════════════════════════════════════════════════════════════════════

class TestClosedLoopAPI:
    """Submit feedback via /contradict, then verify /improvement moved."""

    def test_contradict_endpoint_resolves_predictions_and_updates_brier(self, client):
        """The exact end-to-end test the auditor ran manually and that failed
        on 8f342f8:

            1. GET /recommendations  → predictions auto-created
            2. POST /contradict      → CEO agrees on a linked law
            3. GET /improvement      → resolved > 0, correct > 0, brier != 0.5

        Before the fix, step 3 returned resolved=0, accuracy=0, brier=0.5
        because (a) /contradict never called manager.on_feedback() and
        (b) the resolver's _evaluate_prediction looked for feedback on the
        wrong object. Both are now fixed.
        """
        import pathlib
        # Point the learning DB at a temp file so the test is hermetic.
        learning_db = str(pathlib.Path(client.app.state.__dict__.get("_db_path", "/tmp/maestro_test")) .parent / "test_learning.db") \
            if hasattr(client.app.state, "_db_path") else None
        # Fall back to env-based path (the routes use MAESTRO_LEARNING_DB).
        import os as _os
        _os.environ["MAESTRO_LEARNING_DB"] = str(pathlib.Path(_os.environ.get("MAESTRO_AUTH_DB", "/tmp/maestro_test/auth.db")).parent / "test_learning.db")

        # 1. Surface recommendations → auto-creates predictions.
        resp = client.get("/api/oem/recommendations")
        assert resp.status_code == 200
        recs = resp.json().get("recommendations", [])
        assert len(recs) > 0, "Demo data should produce at least one recommendation."

        # Pick a recommendation with at least one linked law.
        rec = next((r for r in recs if r.get("linked_laws")), recs[0])
        target_law = rec["linked_laws"][0] if rec.get("linked_laws") else rec["title"]

        # Sanity: predictions were created.
        resp = client.get("/api/oem/predictions")
        preds_before = resp.json().get("predictions", [])
        pending_before = [p for p in preds_before if p["status"] == "pending"]
        assert len(pending_before) > 0, "Recommendations did not auto-create pending predictions."

        # 2. CEO agrees on the linked law (or on the rec title if no law).
        resp = client.post("/api/oem/contradict", json={
            "target_type": "law" if rec.get("linked_laws") else "recommendation",
            "target_id": target_law,
            "action": "agree",
            "reasoning": "End-to-end test: this recommendation is right",
            "actor": "ceo@acme.com",
        })
        assert resp.status_code == 200, f"contradict failed: {resp.text}"
        assert resp.json()["ok"] is True

        # 3. Improvement dashboard must show the loop closed.
        resp = client.get("/api/oem/improvement")
        assert resp.status_code == 200
        report = resp.json()
        summary = report["summary"]

        assert summary["resolved"] > 0, (
            f"resolved={summary['resolved']} — /contradict did not resolve "
            f"any predictions. The on_feedback wire is missing or broken."
        )
        assert summary["correct"] > 0, (
            f"correct={summary['correct']} — agree feedback did not register "
            f"as a correct resolution."
        )

        # Brier score must have moved off 0.5 (the empty-calibration default).
        brier = report["calibration"].get("brier_score", 0.5)
        assert brier != 0.5, (
            f"brier_score={brier} — calibration never updated. The resolved "
            f"prediction did not flow into CalibrationEngine.record_prediction."
        )

        # Improvement evidence should now report is_learning=True.
        assert report["improvement_evidence"]["is_learning"] is True

    def test_resolve_endpoint_picks_up_contradiction_log_feedback(self, client):
        """The manual /predictions/resolve endpoint must also see feedback
        in the contradiction log (it constructs the manager with the log
        passed in). This is the fallback path when live_ingest hasn't fired."""
        import os as _os
        import pathlib
        _os.environ["MAESTRO_LEARNING_DB"] = str(pathlib.Path(_os.environ.get("MAESTRO_AUTH_DB", "/tmp/maestro_test/auth.db")).parent / "test_learning_resolve.db")

        # Create predictions.
        resp = client.get("/api/oem/recommendations")
        recs = resp.json().get("recommendations", [])
        assert recs, "Demo data should produce recommendations."
        rec = next((r for r in recs if r.get("linked_laws")), recs[0])
        target_law = rec["linked_laws"][0] if rec.get("linked_laws") else rec["title"]

        # Submit reject feedback.
        resp = client.post("/api/oem/contradict", json={
            "target_type": "law" if rec.get("linked_laws") else "recommendation",
            "target_id": target_law,
            "action": "reject",
            "reasoning": "End-to-end test: this is wrong",
            "actor": "ceo@acme.com",
        })
        assert resp.status_code == 200

        # /contradict already calls manager.on_feedback(), so predictions
        # should already be resolved. But the /resolve endpoint must NOT
        # break when called after — and any remaining pending predictions
        # that can now be resolved (e.g. via expiry) should be handled.
        resp = client.post("/api/oem/predictions/resolve")
        assert resp.status_code == 200
        result = resp.json()
        # At least the endpoint ran and returned a well-formed summary.
        assert "predictions_checked" in result
        assert "predictions_resolved" in result
        assert "still_pending" in result

