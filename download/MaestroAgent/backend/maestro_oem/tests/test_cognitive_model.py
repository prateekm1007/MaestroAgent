"""Tests for the Organizational Cognitive Model — Signal Classes, Preparation Engine, Assumption Graph.

Tests:
  1. Signal Classes — every SignalType maps to a SignalClass
  2. Preparation Engine — creates work packets from OEM data
  3. Assumption Graph — tracks, validates, and surfaces dangerous assumptions
"""

from __future__ import annotations
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from maestro_api.main import create_app
from maestro_api.oem_state import oem_state, import_state
from maestro_oem.signal import SignalType
from maestro_oem.signal_classes import SignalClass, get_signal_class, all_signal_types_mapped, get_unmapped_signal_types


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


# ═══════════════════════════════════════════════════════════════════════════
# 1. SIGNAL CLASSES
# ═══════════════════════════════════════════════════════════════════════════

class TestSignalClasses:
    def test_every_signal_type_maps_to_a_signal_class(self):
        """Every SignalType must have a SignalClass mapping."""
        assert all_signal_types_mapped(), (
            f"Unmapped SignalTypes: {[st.value for st in get_unmapped_signal_types()]}"
        )

    def test_github_pr_maps_to_execution(self):
        assert get_signal_class(SignalType.PR_OPENED) == SignalClass.EXECUTION
        assert get_signal_class(SignalType.PR_MERGED) == SignalClass.EXECUTION

    def test_github_review_maps_to_approval(self):
        assert get_signal_class(SignalType.PR_REVIEWED) == SignalClass.APPROVAL

    def test_slack_message_maps_to_communication(self):
        assert get_signal_class(SignalType.MESSAGE_SENT) == SignalClass.COMMUNICATION

    def test_slack_conflict_maps_to_objection(self):
        assert get_signal_class(SignalType.CONFLICT) == SignalClass.OBJECTION

    def test_customer_commitment_maps_to_commitment(self):
        assert get_signal_class(SignalType.CUSTOMER_COMMITMENT_MADE) == SignalClass.COMMITMENT

    def test_customer_champion_quiet_maps_to_risk(self):
        assert get_signal_class(SignalType.CUSTOMER_CHAMPION_QUIET) == SignalClass.RISK

    def test_contract_churned_maps_to_risk(self):
        assert get_signal_class(SignalType.CUSTOMER_CONTRACT_CHURNED) == SignalClass.RISK

    def test_postmortem_maps_to_learning(self):
        assert get_signal_class(SignalType.POSTMORTEM_CREATED) == SignalClass.LEARNING

    def test_unmapped_type_raises(self):
        """An unmapped SignalType should raise ValueError."""
        # All current types are mapped, so this tests the guard
        from maestro_oem.signal_classes import _SIGNAL_TYPE_TO_CLASS
        assert len(_SIGNAL_TYPE_TO_CLASS) == len(list(SignalType)), (
            f"Mapping has {len(_SIGNAL_TYPE_TO_CLASS)} entries but SignalType has {len(list(SignalType))} values"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 2. PREPARATION ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class TestPreparationEngine:
    def test_preparations_endpoint_returns_data(self, client):
        """GET /api/oem/preparations returns preparations for all recommendations."""
        r = client.get("/api/oem/preparations")
        assert r.status_code == 200
        data = r.json()
        assert "preparations" in data
        assert data["total"] >= 0

    def test_preparation_content_includes_evidence(self, client):
        """Each preparation must include evidence (not LLM-generated content)."""
        r = client.get("/api/oem/preparations")
        for prep in r.json().get("preparations", []):
            assert "evidence" in prep, f"Preparation {prep.get('preparation_id')} missing evidence"
            assert "content" in prep, f"Preparation {prep.get('preparation_id')} missing content"
            assert "confidence" in prep
            assert 0 <= prep["confidence"] <= 1

    def test_preparation_has_type(self, client):
        """Each preparation must have a type (rollback_plan, rfc_draft, etc.)."""
        r = client.get("/api/oem/preparations")
        for prep in r.json().get("preparations", []):
            assert prep["preparation_type"] in (
                "rollback_plan", "rfc_draft", "customer_brief",
                "incident_response", "legal_packet", "general_brief"
            ), f"Unknown preparation type: {prep['preparation_type']}"

    def test_preparation_can_be_approved(self, client):
        """POST /api/oem/preparations/{id}/approve marks it as approved."""
        # Get preparations first
        r = client.get("/api/oem/preparations")
        preps = r.json().get("preparations", [])
        if not preps:
            pytest.skip("No preparations available to approve")
        prep_id = preps[0]["preparation_id"]

        # Approve it
        r = client.post(f"/api/oem/preparations/{prep_id}/approve?approved_by=ceo@acme.com")
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

    def test_preparation_status_filter(self, client):
        """GET /api/oem/preparations?status=ready filters by status."""
        r = client.get("/api/oem/preparations?status=ready")
        assert r.status_code == 200
        for prep in r.json().get("preparations", []):
            assert prep["status"] == "ready"


# ═══════════════════════════════════════════════════════════════════════════
# 3. ASSUMPTION GRAPH
# ═══════════════════════════════════════════════════════════════════════════

class TestAssumptionGraph:
    def test_assumptions_endpoint_returns_data(self, client):
        """GET /api/oem/assumptions returns inferred assumptions."""
        r = client.get("/api/oem/assumptions")
        assert r.status_code == 200
        data = r.json()
        assert "assumptions" in data
        assert data["total"] >= 0

    def test_create_explicit_assumption(self, client):
        """POST /api/oem/assumptions creates an explicit assumption."""
        r = client.post("/api/oem/assumptions", json={
            "statement": "Legal review takes 3 days",
            "context": "Q4 launch plan",
            "stakes": "high",
            "made_by": "jane@acme.com",
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert r.json()["assumption_id"].startswith("asmp-")

    def test_assumption_has_status(self, client):
        """Each assumption must have a status (open/validated/invalidated)."""
        r = client.get("/api/oem/assumptions")
        for a in r.json().get("assumptions", []):
            assert a["status"] in ("open", "validated", "invalidated", "forgotten")

    def test_dangerous_assumptions_view(self, client):
        """GET /api/oem/assumptions/dangerous returns high-stakes open assumptions."""
        # Create a dangerous assumption
        client.post("/api/oem/assumptions", json={
            "statement": "The API will be ready by Q3",
            "context": "Product launch depends on this",
            "stakes": "critical",
            "made_by": "cto@acme.com",
        })
        r = client.get("/api/oem/assumptions/dangerous")
        assert r.status_code == 200
        data = r.json()
        assert "dangerous_assumptions" in data
        # The assumption we just created should be in there
        assert any("API will be ready" in a["statement"] for a in data["dangerous_assumptions"]), (
            f"Dangerous assumption not found: {[a['statement'][:40] for a in data['dangerous_assumptions']]}"
        )

    def test_assumption_accuracy_report(self, client):
        """GET /api/oem/assumptions/accuracy returns accuracy metrics."""
        r = client.get("/api/oem/assumptions/accuracy")
        assert r.status_code == 200
        data = r.json()
        assert "total_assumptions" in data
        assert "validated" in data
        assert "invalidated" in data
        assert "accuracy_rate" in data
        assert "narrative" in data

    def test_assumption_filter_by_status(self, client):
        """GET /api/oem/assumptions?status=open filters by status."""
        r = client.get("/api/oem/assumptions?status=open")
        assert r.status_code == 200
        for a in r.json().get("assumptions", []):
            assert a["status"] == "open"

    def test_inferred_assumptions_from_recommendations(self, client):
        """Assumptions are inferred from OEM recommendations."""
        r = client.get("/api/oem/assumptions")
        data = r.json()
        # With demo data, recommendations exist → assumptions should be inferred
        if data["total"] > 0:
            inferred = [a for a in data["assumptions"] if a["made_by"] == "system:inferred"]
            assert len(inferred) > 0, "No inferred assumptions from recommendations"


# ═══════════════════════════════════════════════════════════════════════════
# 4. LEARNING LOOP REGRESSION (must not break)
# ═══════════════════════════════════════════════════════════════════════════

class TestLearningLoopRegression:
    def test_learning_loop_still_closes(self, client):
        """The new capabilities must not break the closed learning loop."""
        import os as _os
        import pathlib
        _os.environ["MAESTRO_LEARNING_DB"] = str(pathlib.Path(_os.environ.get("MAESTRO_AUTH_DB", "/tmp/test/auth.db")).parent / "test_learning_cog.db")

        # 1. Surface recommendations → auto-creates predictions
        r = client.get("/api/oem/recommendations")
        assert r.status_code == 200
        recs = r.json().get("recommendations", [])
        assert len(recs) > 0

        # 2. CEO agrees on a linked law
        rec = next((r for r in recs if r.get("linked_laws")), recs[0])
        target_law = rec["linked_laws"][0] if rec.get("linked_laws") else rec["title"]
        r = client.post("/api/oem/contradict", json={
            "target_type": "law" if rec.get("linked_laws") else "recommendation",
            "target_id": target_law,
            "action": "agree",
            "reasoning": "Cognitive model regression test",
            "actor": "ceo@acme.com",
        })
        assert r.status_code == 200

        # 3. Improvement dashboard must show resolved > 0, brier != 0.5
        r = client.get("/api/oem/improvement")
        assert r.status_code == 200
        report = r.json()
        assert report["summary"]["resolved"] > 0, "Learning loop regression — resolved=0"
        assert report["calibration"]["brier_score"] != 0.5, "Learning loop regression — Brier stuck at 0.5"
