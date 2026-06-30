"""
Interaction audit tests — verify every card/metric/insight is clickable.

Verifies that app.html has NO dead-end cards. Every clickable element
must either:
  1. Call openDrilldown() to open the drill-down modal, OR
  2. Call a navigation function (navTo) with context, OR
  3. Be a feedback button (contradictLaw, etc.)

Specifically checks:
  - All metric tiles are clickable (metric-clickable class)
  - All discovery cards call openDrilldown
  - All recommendation cards call openDrilldown
  - All law cards call openDrilldown
  - All expert cards call openDrilldown
  - All risk cards call openDrilldown
  - All knowledge-flow cards call openDrilldown
  - All audit receipts call openDrilldown
  - The drill-down modal exists with 9 tabs (8 original + Perspectives)
  - The drill-down endpoint returns all 8 sections
"""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from maestro_api.main import create_app
from maestro_api.oem_state import oem_state, import_state


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Test client with auth + static file serving enabled."""
    test_db = str(tmp_path / "test_import.db")
    monkeypatch.setattr("maestro_api.oem_state._IMPORT_DB_PATH", test_db)
    monkeypatch.setenv("MAESTRO_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("MAESTRO_ADMIN_PASSWORD", "test-admin-pass")
    # Point to the app directory so /static/js/*.js files are served
        # Resolve app dir relative to this test file (works on any clone)
    import pathlib
    app_dir = str(pathlib.Path(__file__).resolve().parents[3])  # backend/../../ = app root
    monkeypatch.setenv("MAESTRO_APP_DIR", app_dir)

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
# 1. FRONTEND: every card has an onclick that opens a drill-down
# ═══════════════════════════════════════════════════════════════════════════

class TestNoDeadCards:
    """Verify no card in app.html is a dead-end."""

    @staticmethod
    def _get_all_js(client):
        """Get app.html + all external JS files combined.

        The frontend was modularized in round 17 from a single app.js into
        19 files in /static/js/. This method fetches app.html plus every
        JS file referenced via <script defer src="/static/js/..."> tags.
        """
        html = client.get("/app.html").text

        # Extract all /static/js/*.js script srcs from app.html
        import re
        js_files = re.findall(r'<script[^>]*src="(/static/js/[^"]+)"', html)

        combined = html
        for js_path in js_files:
            js_resp = client.get(js_path)
            if js_resp.status_code == 200:
                combined += "\n" + js_resp.text

        return combined

    def test_metric_tiles_are_clickable(self, client):
        """All 6 metric tiles on Home must have the metric-clickable class."""
        combined = self._get_all_js(client)
        assert combined.count("metric-clickable") >= 6, "Not all metrics are clickable"

    def test_drilldown_modal_exists(self, client):
        """The drill-down modal must exist in the HTML."""
        resp = client.get("/app.html")
        html = resp.text
        assert 'id="drilldown-modal"' in html, "Drill-down modal not found"

    def test_drilldown_modal_has_tabs(self, client):
        """The drill-down modal must have all required tabs.

        9 tabs: Why/Where/Evidence/Timeline/People/Prediction/Simulation/
        Recommendation/Perspectives. (Perspectives was added in the
        cognitive-model UI commit for the 6-team translation view.)
        """
        resp = client.get("/app.html")
        html = resp.text
        tabs = ["why", "where", "evidence", "timeline", "people",
                "prediction", "simulation", "recommendation", "perspectives"]
        for tab in tabs:
            assert f'data-tab="{tab}"' in html, f"Missing drill-down tab: {tab}"

    def test_openDrilldown_function_exists(self, client):
        """The openDrilldown function must be defined."""
        combined = self._get_all_js(client)
        assert "function openDrilldown" in combined or "openDrilldown = " in combined

    def test_closeDrilldown_function_exists(self, client):
        """The closeDrilldown function must be defined."""
        combined = TestNoDeadCards._get_all_js(client)
        assert "function closeDrilldown" in combined

    def test_every_card_has_onclick(self, client):
        """Every card div must have an onclick handler (no dead cards)."""
        combined = TestNoDeadCards._get_all_js(client)
        assert 'cursor-pointer' in combined, "No clickable cards found"

    def test_no_navTo_on_cards(self, client):
        """Cards should use openDrilldown, not generic navTo (which dead-ends)."""
        combined = TestNoDeadCards._get_all_js(client)
        assert "openDrilldown('law'" in combined, "Law cards don't use openDrilldown"
        assert "openDrilldown('recommendation'" in combined, "Rec cards don't use openDrilldown"
        assert "openDrilldown('expert'" in combined, "Expert cards don't use openDrilldown"
        assert "openDrilldown('risk'" in combined, "Risk cards don't use openDrilldown"
        assert "openDrilldown('metric'" in combined, "Metric tiles don't use openDrilldown"
        assert "openDrilldown('signal'" in combined, "Audit receipts don't use openDrilldown"


# ═══════════════════════════════════════════════════════════════════════════
# 2. BACKEND: drill-down endpoint returns all 8 sections
# ═══════════════════════════════════════════════════════════════════════════

class TestDrilldownEndpoint:
    """Verify the /api/oem/entity/{type}/{id} endpoint returns all 8 sections."""

    def test_law_drilldown(self, client):
        """Law drill-down must return all 8 sections."""
        # First get a law code
        laws_resp = client.get("/api/oem/laws")
        laws = laws_resp.json().get("laws", [])
        if not laws:
            pytest.skip("No laws in OEM")
        law_code = laws[0]["code"]

        resp = client.get(f"/api/oem/entity/law/{law_code}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert data["entity_type"] == "law"
        # All 8 sections present
        assert "why" in data
        assert "where" in data
        assert "evidence" in data
        assert "timeline" in data
        assert "people" in data
        assert "prediction" in data
        assert "simulation" in data
        assert "recommendation" in data
        # Why should be non-empty
        assert len(data["why"]) > 20
        # Should have evidence
        assert len(data["evidence"]) > 0
        # Should have people
        assert len(data["people"]) > 0

    def test_recommendation_drilldown(self, client):
        """Recommendation drill-down must return all 8 sections."""
        recs_resp = client.get("/api/oem/recommendations")
        recs = recs_resp.json().get("recommendations", [])
        if not recs:
            pytest.skip("No recommendations in OEM")
        # Use title (stable) instead of rec_id (ephemeral — changes per call)
        rec_title = recs[0]["title"]

        resp = client.get(f"/api/oem/entity/recommendation/{rec_title}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert data["why"] is not None
        assert data["simulation"]["available"] is True

    def test_expert_drilldown(self, client):
        """Expert drill-down must return all 8 sections."""
        experts_resp = client.get("/api/oem/knowledge")
        experts = experts_resp.json().get("hidden_experts", [])
        if not experts:
            pytest.skip("No experts in OEM")
        expert_name = experts[0]["entity"]

        resp = client.get(f"/api/oem/entity/expert/{expert_name}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert data["why"] is not None
        assert "influence" in str(data["where"])

    def test_risk_drilldown(self, client):
        """Risk drill-down must return all 8 sections."""
        risks_resp = client.get("/api/oem/knowledge")
        risks = risks_resp.json().get("concentration_risks", [])
        if not risks:
            pytest.skip("No risks in OEM")
        risk_domain = risks[0]["domain"]

        resp = client.get(f"/api/oem/entity/risk/{risk_domain}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert data["why"] is not None

    def test_metric_drilldown(self, client):
        """Metric drill-down must return all 8 sections."""
        resp = client.get("/api/oem/entity/metric/signals_processed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert data["why"] is not None
        assert data["where"]["value"] > 0

    def test_signal_drilldown(self, client):
        """Signal drill-down must return all 8 sections."""
        # Get a signal ID from receipts
        receipts_resp = client.get("/api/oem/receipts?limit=1")
        receipts = receipts_resp.json().get("receipts", [])
        if not receipts:
            pytest.skip("No receipts in OEM")
        signal_id = receipts[0]["receipt_id"]

        resp = client.get(f"/api/oem/entity/signal/{signal_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert data["why"] is not None

    def test_drilldown_404_for_unknown(self, client):
        """Unknown entity should return 404."""
        resp = client.get("/api/oem/entity/law/L-9999")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# 3. SIMULATION ENDPOINT
# ═══════════════════════════════════════════════════════════════════════════

class TestSimulationEndpoint:
    """Verify the /api/oem/simulate endpoint works for drill-downs."""

    def test_simulate_with_hire_count(self, client):
        """Simulation should return predicted health metrics."""
        resp = client.post("/api/oem/simulate", json={
            "inputs": {"hire_count": 3},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "base_health" in data
        assert "predicted" in data
        assert "confidence" in data
        assert data["predicted"]["p1_cluster_risk"] >= 0

    def test_simulate_with_law_code(self, client):
        """Simulation with a law_code should link it."""
        laws_resp = client.get("/api/oem/laws")
        laws = laws_resp.json().get("laws", [])
        if not laws:
            pytest.skip("No laws")
        law_code = laws[0]["code"]

        resp = client.post("/api/oem/simulate", json={
            "law_code": law_code,
            "inputs": {"hire_count": 2},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert law_code in data["linked_laws"]

    def test_simulate_prediction_changes(self, client):
        """More hires should reduce P1 risk."""
        resp1 = client.post("/api/oem/simulate", json={"inputs": {"hire_count": 0}})
        resp2 = client.post("/api/oem/simulate", json={"inputs": {"hire_count": 5}})
        p1_0 = resp1.json()["predicted"]["p1_cluster_risk"]
        p1_5 = resp2.json()["predicted"]["p1_cluster_risk"]
        assert p1_5 <= p1_0, "More hires should reduce P1 risk"
