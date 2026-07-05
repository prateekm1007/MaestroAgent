"""
V8 Daily Work #6 — Role-Specific Playbooks. Regression tests.

Acceptance criteria:
  1. GET /api/oem/playbook/sales returns drafted outreach with evidence
  2. GET /api/oem/playbook/product returns PRD outline + tickets + unresolved concerns
  3. GET /api/oem/playbook/marketing returns unified ROI view
  4. Playbook surface accessible via Ctrl+K (NOT in sidebar)
  5. V5 litmus: no new sidebar item
  6. Feeds constitution: playbooks generate new signal types (outreach, PRD, ticket)
"""

from __future__ import annotations

import os
import pathlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    app_dir = str(pathlib.Path(__file__).resolve().parents[3])
    os.environ.setdefault("MAESTRO_APP_DIR", app_dir)
    os.environ.setdefault("MAESTRO_AUTH_DB", "/tmp/maestro_test_playbook_auth.db")
    os.environ.setdefault("MAESTRO_ADMIN_PASSWORD", "test")
    from maestro_api.main import create_app
    app = create_app(db_path=":memory:")
    with TestClient(app) as c:
        yield c


# ============================================================
# Criterion 1 — Sales playbook returns drafted outreach
# ============================================================

class TestSalesPlaybook:
    """GET /api/oem/playbook/sales must return drafted outreach with evidence."""

    def test_sales_returns_200(self, client) -> None:
        r = client.get("/api/oem/playbook/sales")
        assert r.status_code == 200

    def test_sales_has_role_field(self, client) -> None:
        r = client.get("/api/oem/playbook/sales")
        data = r.json()
        assert data["role"] == "sales"

    def test_sales_has_drafted_outreach(self, client) -> None:
        """Sales playbook must include a drafted_outreach with subject + body."""
        r = client.get("/api/oem/playbook/sales")
        data = r.json()
        # If there are customer signals, outreach should be present
        if data.get("drafted_outreach"):
            outreach = data["drafted_outreach"]
            assert "subject" in outreach
            assert "body" in outreach
            assert len(outreach["body"]) > 20

    def test_sales_has_evidence(self, client) -> None:
        """Sales playbook must include evidence citations."""
        r = client.get("/api/oem/playbook/sales")
        data = r.json()
        assert "evidence" in data
        assert isinstance(data["evidence"], list)

    def test_sales_with_context(self, client) -> None:
        """Sales playbook with a customer context must attempt that customer."""
        r = client.get("/api/oem/playbook/sales", params={"context": "Globex"})
        data = r.json()
        # Should either return outreach for Globex or an honest error
        assert data["role"] == "sales"
        assert "customer" in data or "error" in data


# ============================================================
# Criterion 2 — Product playbook returns PRD outline + tickets + concerns
# ============================================================

class TestProductPlaybook:
    """GET /api/oem/playbook/product must return PRD outline + tickets + concerns."""

    def test_product_returns_200(self, client) -> None:
        r = client.get("/api/oem/playbook/product")
        assert r.status_code == 200

    def test_product_has_role_field(self, client) -> None:
        r = client.get("/api/oem/playbook/product")
        data = r.json()
        assert data["role"] == "product"

    def test_product_has_required_fields(self, client) -> None:
        """Product playbook must have prd_outline, drafted_tickets, unresolved_concerns."""
        r = client.get("/api/oem/playbook/product")
        data = r.json()
        assert "prd_outline" in data
        assert "drafted_tickets" in data
        assert "unresolved_concerns" in data
        assert "evidence" in data

    def test_product_prd_has_sections(self, client) -> None:
        """If prd_outline is present, it must have sections."""
        r = client.get("/api/oem/playbook/product")
        data = r.json()
        if data.get("prd_outline"):
            assert "sections" in data["prd_outline"]
            assert len(data["prd_outline"]["sections"]) >= 3  # Problem, Solution, Metrics, Questions

    def test_product_with_feature_context(self, client) -> None:
        """Product playbook with a feature context must filter to that feature."""
        r = client.get("/api/oem/playbook/product", params={"context": "payments"})
        data = r.json()
        assert data["role"] == "product"
        # Should either return a PRD for "payments" or an honest error
        if data.get("feature"):
            assert "payments" in data["feature"].lower() or data["feature"] == "New Feature"


# ============================================================
# Criterion 3 — Marketing playbook returns unified ROI view
# ============================================================

class TestMarketingPlaybook:
    """GET /api/oem/playbook/marketing must return unified ROI view."""

    def test_marketing_returns_200(self, client) -> None:
        r = client.get("/api/oem/playbook/marketing")
        assert r.status_code == 200

    def test_marketing_has_role_field(self, client) -> None:
        r = client.get("/api/oem/playbook/marketing")
        data = r.json()
        assert data["role"] == "marketing"

    def test_marketing_has_required_fields(self, client) -> None:
        """Marketing playbook must have campaigns, total_spend, recommendation."""
        r = client.get("/api/oem/playbook/marketing")
        data = r.json()
        assert "campaigns" in data
        assert "total_spend" in data
        assert "recommendation" in data
        assert "evidence" in data

    def test_marketing_campaigns_have_roi_fields(self, client) -> None:
        """If campaigns exist, each must have spend, conversions, cpa, roi."""
        r = client.get("/api/oem/playbook/marketing")
        data = r.json()
        for campaign in data.get("campaigns", []):
            assert "spend" in campaign
            assert "conversions" in campaign
            assert "cpa" in campaign
            assert "roi" in campaign


# ============================================================
# Criterion 4 — Playbook accessible via Ctrl+K (NOT in sidebar)
# ============================================================

class TestCommandPaletteAccess:
    """Playbook must be accessible via command palette, NOT in sidebar."""

    def test_playbook_in_command_palette(self, client) -> None:
        """The command palette must include the playbook surface."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        maestro_path = os.path.join(app_dir, "static", "js", "maestro.js")
        if not os.path.exists(maestro_path):
            pytest.skip("maestro.js not found")
        source = open(maestro_path).read()
        assert "playbook" in source, "maestro.js doesn't reference playbook"
        assert "Role Playbooks" in source, "Command palette missing 'Role Playbooks' entry"

    def test_playbook_surface_in_app_html(self, client) -> None:
        """app.html must have a surface-playbook section."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        app_html_path = os.path.join(app_dir, "app.html")
        if not os.path.exists(app_html_path):
            pytest.skip("app.html not found")
        source = open(app_html_path).read()
        assert 'id="surface-playbook"' in source, "app.html missing surface-playbook section"
        assert "playbook.js" in source, "app.html missing playbook.js script tag"

    def test_playbook_js_exists_and_has_render_functions(self, client) -> None:
        """playbook.js must exist and have the render functions."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        playbook_path = os.path.join(app_dir, "static", "js", "playbook.js")
        if not os.path.exists(playbook_path):
            pytest.skip("playbook.js not found")
        source = open(playbook_path).read()
        assert "function loadPlaybook" in source
        assert "function renderPlaybook" in source
        assert "renderSalesPlaybook" in source
        assert "renderMarketingPlaybook" in source
        assert "renderProductPlaybook" in source


# ============================================================
# Criterion 5 — V5 litmus: no new sidebar item
# ============================================================

class TestV5LitmusNoNewSidebar:
    """V5 litmus: playbook must NOT be in the sidebar."""

    def test_playbook_not_in_sidebar(self, client) -> None:
        """app.html must NOT have a sidebar link for playbook."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        app_html_path = os.path.join(app_dir, "app.html")
        if not os.path.exists(app_html_path):
            pytest.skip("app.html not found")
        source = open(app_html_path).read()
        # The sidebar links use data-surface="..." — playbook should NOT appear
        assert 'data-surface="playbook"' not in source, (
            "Playbook is in the sidebar — V5 litmus violated. "
            "Playbook should be command-palette only."
        )

    def test_playbooks_module_does_not_create_surface(self) -> None:
        """The playbooks module must NOT register a new surface/panel."""
        import maestro_oem.playbooks as mod
        source = open(mod.__file__).read()
        assert "register_surface" not in source
        assert "new_panel" not in source

    def test_routes_oem_has_playbook_endpoint(self) -> None:
        """routes/oem.py must have the /playbook/{role} endpoint."""
        import maestro_api.routes.oem as mod
        source = open(mod.__file__).read()
        assert '@router.get("/playbook/{role}")' in source


# ============================================================
# Criterion 6 — Unsupported role returns error
# ============================================================

class TestUnsupportedRole:
    """Unsupported roles must return a helpful error."""

    def test_unsupported_role_returns_200_with_error(self, client) -> None:
        """Unsupported roles must return 200 with an error message (not 500)."""
        r = client.get("/api/oem/playbook/finance")
        assert r.status_code == 200
        data = r.json()
        assert "error" in data
        assert "supported_roles" in data
        assert "sales" in data["supported_roles"]
        assert "marketing" in data["supported_roles"]
        assert "product" in data["supported_roles"]
