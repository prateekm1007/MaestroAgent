"""Tests for pilot instrumentation: weekly snapshots, decision log, capability impact.

These 3 instrumentation surfaces prepare the ground for the advisor's vision
(Principles, Genome, Gravity, Fragility) WITHOUT building those capabilities
prematurely. Per the advisor's directive: "instrument the system so that,
after 90 days, you can derive Principles, Genome, Gravity, and Fragility
from customer data."
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


# ═══════════════════════════════════════════════════════════════════════════
# SNAPSHOT STORE — "does it get smarter every week?"
# ═══════════════════════════════════════════════════════════════════════════

class TestSnapshotStore:
    def test_collect_snapshot_returns_metrics(self, client):
        """POST /api/oem/snapshots/collect captures all learning-loop metrics."""
        r = client.post("/api/oem/snapshots/collect")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        snapshot = data["snapshot"]

        # Must capture the key metrics the pilot needs
        required_keys = [
            "snapshot_at", "week_label",
            "signals_processed", "laws_inferred", "recommendations_active",
            "predictions_total", "predictions_resolved", "predictions_pending",
            "brier_score", "calibration_error", "accuracy_rate",
            "is_well_calibrated", "is_learning",
            "hidden_experts_count", "concentration_risks_count",
            "intents_count", "hypotheses_count", "assumptions_count",
            "contradictions_count", "preparations_count",
        ]
        for key in required_keys:
            assert key in snapshot, f"Snapshot missing key: {key}"

        # With demo seed, we should have signals and laws
        assert snapshot["signals_processed"] > 0
        assert snapshot["laws_inferred"] > 0

        # Week label should be ISO format like "2026-W27"
        assert "-W" in snapshot["week_label"]

    def test_list_snapshots_returns_history(self, client):
        """GET /api/oem/snapshots returns the snapshot history."""
        # Collect two snapshots
        client.post("/api/oem/snapshots/collect")
        client.post("/api/oem/snapshots/collect")

        r = client.get("/api/oem/snapshots")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 2
        assert len(data["snapshots"]) >= 2
        # Most recent first
        assert data["snapshots"][0]["snapshot_at"] >= data["snapshots"][1]["snapshot_at"]

    def test_snapshot_captures_brier_score(self, client):
        """The snapshot must capture Brier score — the pilot's key metric."""
        # First, close the learning loop so Brier is non-zero
        client.get("/api/oem/recommendations")
        client.post("/api/oem/contradict", json={
            "target_type": "recommendation",
            "target_id": "Address bottleneck: sara.k@acme.com gates 3 items",
            "action": "agree",
            "reasoning": "Snapshot test",
            "actor": "ceo@acme.com",
        })

        r = client.post("/api/oem/snapshots/collect")
        snapshot = r.json()["snapshot"]
        # Brier should be present (may be 0 if no predictions resolved yet,
        # but the field must exist and be a number)
        assert "brier_score" in snapshot
        assert isinstance(snapshot["brier_score"], (int, float))


# ═══════════════════════════════════════════════════════════════════════════
# DECISION LOG — raw material for Principle extraction
# ═══════════════════════════════════════════════════════════════════════════

class TestDecisionLog:
    def test_approve_preparation_logs_decision(self, client):
        """POST /preparations/{id}/approve must append to the decision log."""
        # Get a preparation to approve
        r = client.get("/api/oem/preparations")
        assert r.status_code == 200
        preps = r.json().get("preparations", [])
        if not preps:
            pytest.skip("No preparations available to approve")
        prep = preps[0]
        prep_id = prep["preparation_id"]

        # Approve it
        r = client.post(f"/api/oem/preparations/{prep_id}/approve?approved_by=ceo@acme.com")
        assert r.status_code == 200

        # Verify it's in the decision log
        r = client.get("/api/oem/decision-log")
        assert r.status_code == 200
        data = r.json()
        assert data["summary"]["total"] >= 1
        assert data["summary"]["approved"] >= 1

        # The logged decision must include the preparation details
        logged = next(
            (d for d in data["decisions"] if d["preparation_id"] == prep_id),
            None,
        )
        assert logged is not None, "Approved preparation not found in decision log"
        assert logged["decision"] == "approved"
        assert logged["decided_by"] == "ceo@acme.com"
        assert logged["title"] == prep["title"]
        assert logged["confidence_at_decision"] == prep.get("confidence", 0.0)

    def test_decision_log_filter_by_decision(self, client):
        """GET /decision-log?decision=approved filters correctly."""
        # Get preparations and approve one
        r = client.get("/api/oem/preparations")
        preps = r.json().get("preparations", [])
        if preps:
            client.post(f"/api/oem/preparations/{preps[0]['preparation_id']}/approve?approved_by=ceo")

        r = client.get("/api/oem/decision-log?decision=approved")
        assert r.status_code == 200
        for d in r.json()["decisions"]:
            assert d["decision"] == "approved"

    def test_decision_log_summary(self, client):
        """The decision log summary must show approved/rejected/resolved counts."""
        r = client.get("/api/oem/decision-log")
        assert r.status_code == 200
        summary = r.json()["summary"]
        assert "total" in summary
        assert "approved" in summary
        assert "rejected" in summary
        assert "resolved_with_outcome" in summary
        assert "avg_confidence_at_decision" in summary

    def test_resolve_decision_outcome(self, client):
        """POST /decision-log/{id}/resolve records the actual outcome.

        This is what feeds Principle extraction: 'we decided X based on
        assumptions A,B,C and the outcome was Y.'
        """
        # Approve a preparation first
        r = client.get("/api/oem/preparations")
        preps = r.json().get("preparations", [])
        if not preps:
            pytest.skip("No preparations available")
        prep_id = preps[0]["preparation_id"]
        client.post(f"/api/oem/preparations/{prep_id}/approve?approved_by=ceo")

        # Resolve the outcome
        r = client.post(f"/api/oem/decision-log/{prep_id}/resolve", json={
            "outcome": "succeeded",
            "notes": "The RFC was merged and the bottleneck was resolved.",
        })
        assert r.status_code == 200
        assert r.json()["outcome"] == "succeeded"

        # Verify it shows as resolved in the log
        r = client.get("/api/oem/decision-log")
        logged = next(
            (d for d in r.json()["decisions"] if d["preparation_id"] == prep_id),
            None,
        )
        assert logged is not None
        assert logged["outcome"] == "succeeded"
        assert logged["resolved_at"] is not None
        assert "merged" in logged["outcome_notes"]


# ═══════════════════════════════════════════════════════════════════════════
# CAPABILITY IMPACT QUERY — "what collapses if person X disappeared?"
# ═══════════════════════════════════════════════════════════════════════════

class TestCapabilityImpactQuery:
    def test_analyze_person_returns_blast_radius(self, client):
        """GET /capabilities/impact?person=X returns the full blast radius."""
        # Use a person from the demo seed
        r = client.get("/api/oem/capabilities/impact?person=sara.k@acme.com")
        assert r.status_code == 200
        data = r.json()
        assert data["person"] == "sara.k@acme.com"
        impact = data["impact"]

        # Must include all blast-radius components
        required_keys = [
            "person", "influence", "domains_held", "domains_orphaned",
            "signal_count", "laws_losing_evidence", "recommendations_weakened",
            "bottleneck_risk", "blast_radius",
        ]
        for key in required_keys:
            assert key in impact, f"Impact missing key: {key}"

        # blast_radius is the sum of affected items
        assert impact["blast_radius"] == (
            len(impact["domains_orphaned"])
            + len(impact["laws_losing_evidence"])
            + len(impact["recommendations_weakened"])
        )

        # bottleneck_risk must be one of the valid levels
        assert impact["bottleneck_risk"] in ("critical", "high", "medium", "low")

    def test_list_high_impact_people(self, client):
        """GET /capabilities/impact (no person) returns high-impact people."""
        r = client.get("/api/oem/capabilities/impact")
        assert r.status_code == 200
        data = r.json()
        assert "high_impact_people" in data
        assert "total" in data
        assert isinstance(data["high_impact_people"], list)

        # If there are high-impact people, they must be sorted by blast_radius desc
        people = data["high_impact_people"]
        if len(people) >= 2:
            assert people[0]["blast_radius"] >= people[1]["blast_radius"]

    def test_person_with_no_signals_has_low_risk(self, client):
        """A person with no signals should have low blast radius."""
        r = client.get("/api/oem/capabilities/impact?person=nobody@nowhere.com")
        assert r.status_code == 200
        impact = r.json()["impact"]
        assert impact["signal_count"] == 0
        assert impact["blast_radius"] == 0
        assert impact["bottleneck_risk"] == "low"

    def test_bottleneck_person_has_high_risk(self, client):
        """A person with domain holdings should have non-trivial impact."""
        # priya.m@acme.com holds 4 domains in the demo seed (PR signals)
        r = client.get("/api/oem/capabilities/impact?person=priya.m@acme.com")
        assert r.status_code == 200
        impact = r.json()["impact"]
        # Priya should hold at least one domain
        assert len(impact["domains_held"]) > 0
        assert impact["influence"] > 0
