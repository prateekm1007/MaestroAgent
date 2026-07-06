"""
Tests for the OEM API routes.

Verifies that every endpoint:
- Returns 200
- Returns real data derived from the OEM (not hardcoded)
- Includes the required fields for the UI
- Handles errors gracefully
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from maestro_api.main import create_app


@pytest.fixture(scope="module")
def client():
    """Build the FastAPI app with the OEM initialized."""
    import os
    import pathlib
    # Set MAESTRO_APP_DIR so the frontend can find app.html
    app_dir = str(pathlib.Path(__file__).resolve().parents[3])  # backend/../../ = app root
    os.environ.setdefault("MAESTRO_APP_DIR", app_dir)
    os.environ.setdefault("MAESTRO_AUTH_DB", "/tmp/maestro_test_oem_auth.db")
    os.environ.setdefault("MAESTRO_ADMIN_PASSWORD", "test")
    app = create_app(db_path=":memory:")
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reinit_oem_state():
    """RC3 fix: re-initialize oem_state before each test.

    The root conftest's autouse fixture clears oem_state.signals between
    tests to prevent cross-test contamination. But this file uses a
    module-scoped client fixture — the app is built once, and the lifespan
    startup calls oem_state.initialize() once. After the autouse fixture
    clears state, the next test's request reads an empty oem_state.signals.

    This fixture re-initializes oem_state before each test so the module-
    scoped client always sees seeded state. MAESTRO_DEMO_SEED=true (set in
    root conftest) ensures demo data is loaded.
    """
    from maestro_api.oem_state import oem_state
    oem_state._initialized = False
    oem_state.signals = []
    oem_state._demo_seeded = False
    oem_state.initialize()
    yield


# ============================================================
# 1. GET /api/oem/state
# ============================================================

class TestOemState:
    def test_returns_200(self, client):
        r = client.get("/api/oem/state")
        assert r.status_code == 200

    def test_returns_summary_with_real_counts(self, client):
        r = client.get("/api/oem/state")
        data = r.json()
        summary = data["summary"]
        assert summary["signals_processed"] > 0, "No signals processed"
        assert summary["learning_objects"] > 0, "No learning objects"
        assert summary["laws_inferred"] > 0, "No laws inferred"
        assert summary["providers_connected"], "No providers connected"

    def test_returns_provider_detail(self, client):
        r = client.get("/api/oem/state")
        providers = r.json()["providers"]
        provider_names = {p["provider"] for p in providers}
        # 5 original providers + customer (Customer Judgment Engine)
        assert provider_names == {"github", "jira", "slack", "confluence", "gmail", "customer"}
        for p in providers:
            assert p["signal_count"] > 0, f"{p['provider']} has 0 signals"
            assert p["label"], f"{p['provider']} has no label"

    def test_returns_health_metrics(self, client):
        r = client.get("/api/oem/state")
        health = r.json()["health"]
        assert "p1_cluster_risk" in health
        assert "incident_rate" in health
        assert "decision_velocity_days" in health
        assert 0.0 <= health["p1_cluster_risk"] <= 1.0


# ============================================================
# 2. GET /api/oem/dashboard
# ============================================================

class TestOemDashboard:
    def test_returns_200(self, client):
        r = client.get("/api/oem/dashboard")
        assert r.status_code == 200

    def test_returns_metrics(self, client):
        data = client.get("/api/oem/dashboard").json()
        metrics = data["metrics"]
        assert metrics["signals_processed"] > 0
        assert "laws_inferred" in metrics
        assert "recommendations_active" in metrics

    def test_returns_overnight_changes(self, client):
        data = client.get("/api/oem/dashboard").json()
        changes = data["overnight_changes"]
        assert len(changes) > 0, "No overnight changes — OEM produced nothing"
        for change in changes:
            assert change["title"], "Change has no title"
            assert change["type"], "Change has no type"
            assert change["severity"] in ("info", "warning", "urgent")

    def test_returns_today_decisions(self, client):
        data = client.get("/api/oem/dashboard").json()
        decisions = data["today_decisions"]
        for d in decisions:
            assert d["title"], "Decision has no title"
            assert "confidence" in d, "Decision has no confidence"
            # Phase 1 fix: confidence may be a string ("insufficient_history")
            # or a float. Accept either — the display gate (C4 fix) returns
            # strings when sample_size < 10.
            conf = d["confidence"]
            if isinstance(conf, (int, float)):
                assert 0.0 <= conf <= 1.0
            else:
                assert isinstance(conf, str), f"confidence must be float or str, got {type(conf)}"
            assert "evidence_chain" in d, "Decision has no evidence chain"

    def test_returns_providers_connected(self, client):
        data = client.get("/api/oem/dashboard").json()
        # 5 original + customer
        assert len(data["providers_connected"]) == 6


# ============================================================
# 3. GET /api/oem/recommendations
# ============================================================

class TestOemRecommendations:
    def test_returns_200(self, client):
        assert client.get("/api/oem/recommendations").status_code == 200

    def test_returns_recommendations_with_evidence(self, client):
        data = client.get("/api/oem/recommendations").json()
        assert data["total"] > 0, "No recommendations — OEM produced nothing"
        for rec in data["recommendations"]:
            assert rec["title"]
            assert rec["recommendation"], "Rec has no recommendation text"
            conf = rec["confidence"]
            if isinstance(conf, (int, float)):
                assert 0.0 <= conf <= 1.0
            else:
                assert isinstance(conf, str)
            assert rec["decision_question"], "Rec has no decision question"
            assert "provenance" in rec, "Rec has no provenance"
            assert "evidence_chain" in rec, "Rec has no evidence chain"
            assert "supporting_artifacts" in rec, "Rec has no supporting artifacts"
            assert "contradicting_artifacts" in rec, "Rec has no contradicting artifacts"
            assert "evidence_strength" in rec, "Rec has no evidence strength"
            assert rec["urgency"] in ("urgent", "normal", "low")

    def test_filter_by_urgency(self, client):
        data = client.get("/api/oem/recommendations?urgency=urgent").json()
        for rec in data["recommendations"]:
            assert rec["urgency"] == "urgent"


# ============================================================
# 4. GET /api/oem/inbox
# ============================================================

class TestOemInbox:
    def test_returns_200(self, client):
        assert client.get("/api/oem/inbox").status_code == 200

    def test_returns_counts(self, client):
        data = client.get("/api/oem/inbox").json()
        counts = data["counts"]
        assert "owed" in counts
        assert "attention" in counts
        assert "drift" in counts
        assert "dissent" in counts

    def test_decisions_owed_are_urgent(self, client):
        data = client.get("/api/oem/inbox").json()
        for d in data["decisions_owed"]:
            assert d["urgency"] == "urgent"


# ============================================================
# 5. GET /api/oem/laws
# ============================================================

class TestOemLaws:
    def test_returns_200(self, client):
        assert client.get("/api/oem/laws").status_code == 200

    def test_returns_laws_with_provenance(self, client):
        data = client.get("/api/oem/laws").json()
        assert data["total"] > 0, "No laws — OEM produced nothing"
        for law in data["laws"]:
            assert law["code"], "Law has no code"
            assert law["statement"], "Law has no statement"
            assert law["condition"], "Law has no condition"
            assert law["outcome"], "Law has no outcome"
            # C4 fix: confidence is now a display string (may be "insufficient
            # calibration history" when sample_size < 10). The raw numeric
            # value is in confidence_raw. Test both.
            assert "confidence" in law, "Law has no confidence field"
            assert "confidence_raw" in law, "Law has no confidence_raw field (C4 fix)"
            conf_raw = law["confidence_raw"]
            if isinstance(conf_raw, (int, float)):
                assert 0.0 <= conf_raw <= 1.0, \
                    f"confidence_raw out of range: {conf_raw}"
            else:
                assert isinstance(conf_raw, str), \
                    f"confidence_raw must be float or str, got {type(conf_raw)}"
            assert "calibration_sample_size" in law, "Law has no calibration_sample_size (C4 fix)"
            # RC1 fix: 'confidence' is now a raw float (0.0-1.0) for programmatic
            # use; 'confidence_display' is the P25-gated string. Both must be present.
            assert isinstance(law["confidence"], (int, float)), \
                f"confidence must be a float (RC1 fix). Got: {type(law['confidence'])}"
            assert 0.0 <= law["confidence"] <= 1.0, \
                f"confidence out of range: {law['confidence']}"
            assert "confidence_display" in law, \
                "Law has no confidence_display field (RC1 fix)"
            assert isinstance(law["confidence_display"], str), \
                f"confidence_display must be a string (C4 fix). Got: {type(law['confidence_display'])}"
            assert "evidence_count" in law
            assert "validated_runtimes" in law
            assert "failed_runtimes" in law
            assert "providers" in law
            assert "provenance" in law, "Law has no provenance"
            assert "evidence_chain" in law, "Law has no evidence chain"
            assert "last_validated" in law, "Law has no last_validated"

    def test_by_status_breakdown(self, client):
        data = client.get("/api/oem/laws").json()
        by_status = data["by_status"]
        assert sum(by_status.values()) == data["total"]

    def test_filter_by_status(self, client):
        data = client.get("/api/oem/laws?status=validated").json()
        for law in data["laws"]:
            assert law["status"] == "validated"

    def test_single_law_404(self, client):
        r = client.get("/api/oem/laws/DOES-NOT-EXIST")
        assert r.status_code == 404

    def test_single_law_returns_full_chain(self, client):
        laws = client.get("/api/oem/laws").json()["laws"]
        if not laws:
            pytest.skip("No laws to test")
        code = laws[0]["code"]
        r = client.get(f"/api/oem/laws/{code}")
        assert r.status_code == 200
        law = r.json()
        assert law["code"] == code
        assert "evidence_chain" in law
        assert "provenance" in law


# ============================================================
# 6. GET /api/oem/ask
# ============================================================

class TestOemAsk:
    def test_returns_200(self, client):
        r = client.get("/api/oem/ask?q=who+is+the+bottleneck")
        assert r.status_code == 200

    def test_returns_answer_with_confidence(self, client):
        data = client.get("/api/oem/ask?q=bottleneck").json()
        assert "answer" in data
        # CEO directive: confidence was intentionally removed from /ask
        # ("Maestro never invents precision"). Don't assert on it.
        assert "sources" in data
        assert "evidence_path" in data

    def test_returns_evidence_for_matching_query(self, client):
        data = client.get("/api/oem/ask?q=bottleneck").json()
        assert "evidence_path" in data
        assert isinstance(data["evidence_path"], list)

    def test_returns_fallback_for_nonsense(self, client):
        data = client.get("/api/oem/ask?q=zzz nonsense xyzzy").json()
        assert "answer" in data
        # CEO directive: confidence was intentionally removed from /ask


# ============================================================
# 7. GET /api/oem/simulator
# ============================================================

class TestOemSimulator:
    def test_returns_200(self, client):
        assert client.get("/api/oem/simulator").status_code == 200

    def test_returns_scenario(self, client):
        data = client.get("/api/oem/simulator").json()
        assert "scenario" in data
        assert "current_health" in data
        assert "linked_laws" in data
        assert "evidence_chain" in data
        assert "supporting_artifacts" in data
        assert "contradicting_artifacts" in data

    def test_post_simulator(self, client):
        r = client.post("/api/oem/simulator", json={"inputs": {"hire_count": 3}})
        assert r.status_code == 200
        data = r.json()
        assert data["inputs"]["hire_count"] == 3
        assert "predicted" in data
        assert "confidence" in data
        assert "base_health" in data


# ============================================================
# 8. GET /api/oem/provenance/{id}
# ============================================================

class TestOemProvenance:
    def test_returns_200(self, client):
        r = client.get("/api/oem/provenance/L-0001")
        assert r.status_code == 200

    def test_returns_chain(self, client):
        data = client.get("/api/oem/provenance/L-0001").json()
        assert "entity_id" in data
        assert "receipt_chain" in data
        assert "evidence_chain" in data
        assert "found" in data

    def test_not_found_returns_200_with_found_false(self, client):
        data = client.get("/api/oem/provenance/DOES-NOT-EXIST").json()
        assert data["found"] is False


# ============================================================
# 9. GET /api/oem/knowledge
# ============================================================

class TestOemKnowledge:
    def test_returns_200(self, client):
        assert client.get("/api/oem/knowledge").status_code == 200

    def test_returns_knowledge_data(self, client):
        data = client.get("/api/oem/knowledge").json()
        assert "hidden_experts" in data
        assert "concentration_risks" in data
        assert "knowledge_death" in data
        assert "duplicate_work" in data
        assert "totals" in data

    def test_concentration_risks_have_score(self, client):
        data = client.get("/api/oem/knowledge").json()
        for risk in data["concentration_risks"]:
            assert "domain" in risk
            assert "score" in risk
            assert risk["score"] >= 0


# ============================================================
# Cross-cutting: no hardcoded insights
# ============================================================

class TestNoHardcodedInsights:
    """The OEM API must return real data, not hardcoded strings."""

    def test_state_matches_seed_data(self, client):
        """The state must reflect the real seed signal data."""
        data = client.get("/api/oem/state").json()
        summary = data["summary"]
        # 39 base signals + 26 customer signals (3 enterprise customers)
        # Phase 2.2: 66 signals (39 base + 27 customer — added 1 mutated Globex commitment
        # so the Trajectory panel has real mutation history to project from out of the box)
        assert summary["signals_processed"] == 66, \
            f"Expected 66 signals (39 base + 27 customer), got {summary['signals_processed']} — OEM not wired"
        # Note: laws_inferred was previously >= 3, but the L-0001/L-0003
        # near-duplicate (same person, same bottleneck, different evidence
        # counts) is now deduplicated to a single law. With the customer
        # provider adding 4 customer-specific laws, total is >= 6.
        assert summary["laws_inferred"] >= 6, \
            f"Expected at least 6 laws, got {summary['laws_inferred']}"
        assert "github" in summary["providers_connected"]
        assert "jira" in summary["providers_connected"]
        assert "slack" in summary["providers_connected"]
        assert "confluence" in summary["providers_connected"]
        assert "gmail" in summary["providers_connected"]
        assert "customer" in summary["providers_connected"]

    def test_recommendations_have_real_provenance(self, client):
        """Provenance must include OEM-derived fields, not hardcoded strings."""
        data = client.get("/api/oem/recommendations").json()
        for rec in data["recommendations"]:
            if rec["provenance"]:
                provenance_str = str(rec["provenance"])
                assert "confidence_formula" in provenance_str or "oem_change" in provenance_str, \
                    "Provenance missing confidence formula — likely not from OEM"
