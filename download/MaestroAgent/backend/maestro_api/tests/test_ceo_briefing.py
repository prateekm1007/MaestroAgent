"""
Tests for the CEO Briefing — verifies the homepage answers the 5 questions
a Fortune 100 CEO needs.

1. What changed overnight?
2. If I only do one thing today?
3. Where is money being lost?
4. Where is knowledge trapped?
5. What decision only I can make?
"""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from maestro_api.main import create_app
from maestro_api.oem_state import oem_state, import_state


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_import.db")
    monkeypatch.setattr("maestro_api.oem_state._IMPORT_DB_PATH", test_db)
    monkeypatch.setenv("MAESTRO_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("MAESTRO_ADMIN_PASSWORD", "test-admin-pass")
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
# 1. CEO BRIEFING ENDPOINT — all 5 questions answered
# ═══════════════════════════════════════════════════════════════════════════

class TestCEOBriefing:
    """The /api/oem/ceo-briefing endpoint must answer all 5 CEO questions."""

    def test_briefing_returns_5_sections(self, client):
        """The briefing must contain all 5 sections."""
        resp = client.get("/api/oem/ceo-briefing")
        assert resp.status_code == 200
        data = resp.json()
        assert "overnight" in data
        assert "one_thing" in data
        assert "money" in data
        assert "knowledge" in data
        assert "decisions" in data

    def test_q1_what_changed_overnight(self, client):
        """Q1: What changed overnight? — must have headline + summary + changes list."""
        resp = client.get("/api/oem/ceo-briefing")
        ov = resp.json()["overnight"]
        assert "summary" in ov
        assert "headline" in ov
        assert "headline_detail" in ov
        assert "changes" in ov
        assert isinstance(ov["changes"], list)
        # Summary should be a human-readable sentence
        assert len(ov["summary"]) > 10
        # Headline should be a specific thing, not a generic metric
        assert "signal" not in ov["headline"].lower() or "expert" in ov["headline"].lower()

    def test_q2_one_thing_today(self, client):
        """Q2: If I only do one thing today? — must have a specific actionable recommendation."""
        resp = client.get("/api/oem/ceo-briefing")
        ot = resp.json()["one_thing"]
        assert "title" in ot
        assert "recommendation" in ot
        assert "why" in ot
        assert "impact" in ot
        assert "urgency" in ot
        assert "confidence" in ot
        # The recommendation must be actionable (not just a metric)
        assert len(ot["recommendation"]) > 10
        # Urgency should be a valid value
        assert ot["urgency"] in ("urgent", "normal", "low")

    def test_q3_where_is_money_lost(self, client):
        """Q3: Where is money being lost? — must have losses with estimated costs."""
        resp = client.get("/api/oem/ceo-briefing")
        money = resp.json()["money"]
        assert "summary" in money
        assert "headline" in money
        assert "losses" in money
        # Each loss should have an estimated cost (the "so what")
        for loss in money["losses"]:
            assert "estimated_cost" in loss, "Money loss without estimated cost"
            assert "title" in loss
            assert "severity" in loss

    def test_q4_where_is_knowledge_trapped(self, client):
        """Q4: Where is knowledge trapped? — must have traps with risk descriptions."""
        resp = client.get("/api/oem/ceo-briefing")
        knowledge = resp.json()["knowledge"]
        assert "summary" in knowledge
        assert "headline" in knowledge
        assert "traps" in knowledge
        # Each trap should have a risk description (the "so what")
        for trap in knowledge["traps"]:
            assert "risk" in trap, "Knowledge trap without risk description"

    def test_q5_what_decision_only_i_can_make(self, client):
        """Q5: What decision only I can make? — must have decisions with questions."""
        resp = client.get("/api/oem/ceo-briefing")
        decisions = resp.json()["decisions"]
        assert "summary" in decisions
        assert "headline" in decisions
        assert "headline_question" in decisions
        assert "decisions" in decisions
        # Each decision should have a question the CEO must answer
        for d in decisions["decisions"]:
            assert "question" in d, "CEO decision without a question"
            assert "recommendation" in d

    def test_no_generic_metrics_in_briefing(self, client):
        """The briefing must NOT answer with raw metric numbers.

        A CEO doesn't care that there are '39 signals' — they care what changed,
        what to do, where money is lost, where knowledge is trapped, and what
        decision only they can make.
        """
        resp = client.get("/api/oem/ceo-briefing")
        data = resp.json()
        # The briefing should NOT have a "metrics" section
        assert "metrics" not in data
        # The one_thing should not just be a number
        assert not data["one_thing"]["title"].isdigit()
        # The overnight headline should be a sentence, not a number
        assert not data["overnight"]["headline"].isdigit()


# ═══════════════════════════════════════════════════════════════════════════
# 2. HOMEPAGE ANSWERS THE 5 QUESTIONS
# ═══════════════════════════════════════════════════════════════════════════

class TestHomepageCEOUX:
    """The homepage HTML must have sections for all 5 CEO questions."""

    def test_homepage_has_5_ceo_question_panels(self, client):
        """The homepage must have panels for all CEO questions (now ECC sections)."""
        resp = client.get("/app.html")
        html = resp.text
        # The ECC sections replace the old CEO question panels
        assert "Today's Attention" in html
        assert "What Changed Overnight" in html
        assert "Hayek Lens" in html
        assert "Knowledge Flow" in html
        assert "Hidden Experts" in html
        assert "Decision Simulator" in html
        assert "Ask the Organization" in html
        assert "Execution Replay" in html
        assert "Executive Autocomplete" in html

    def test_homepage_says_good_morning(self, client):
        """The homepage should say 'Executive Cognition Center', not 'Organizational execution state.'"""
        resp = client.get("/app.html")
        html = resp.text
        assert "Executive Cognition Center" in html or "briefing" in html.lower()
        # Should NOT have the old generic title
        assert "Organizational execution state." not in html

    def test_homepage_loads_ceo_briefing(self, client):
        """The homepage JS must call /api/oem/ceo-briefing."""
        resp = client.get("/app.html")
        html = resp.text
        assert "ceo-briefing" in html

    def test_homepage_does_not_lead_with_metrics(self, client):
        """The homepage should NOT lead with the 6 raw metric tiles.

        The OEM State panel should be collapsed (in a <details> element)
        so the CEO sees the 5 questions first.
        """
        resp = client.get("/app.html")
        html = resp.text
        # The OEM State should be in a <details> (collapsed)
        assert "<details" in html
        # The 5 question panels should come BEFORE the OEM State details
        q5_pos = html.find("What decision only you can make?")
        details_pos = html.find("<details")
        assert q5_pos < details_pos, "CEO questions should come before OEM State"

    def test_homepage_one_thing_has_investigate_button(self, client):
        """The 'one thing' section should have an 'Investigate this' button."""
        # Check the external JS files (frontend was modularized into /static/js/*.js)
        html = client.get("/app.html").text
        import re
        js_files = re.findall(r'<script[^>]*src="(/static/js/[^"]+)"', html)
        combined = html
        for js_path in js_files:
            js_resp = client.get(js_path)
            if js_resp.status_code == 200:
                combined += "\n" + js_resp.text
        assert "openDrilldown" in combined, "openDrilldown not found in JS"

    def test_homepage_every_section_has_loading_state(self, client):
        """Every CEO question panel should have a loading state (no blank waits)."""
        resp = client.get("/app.html")
        html = resp.text
        # Count loading-state occurrences in the home section
        home_start = html.find('id="surface-home"')
        home_end = html.find('</section>', home_start)
        home_html = html[home_start:home_end]
        # Should have at least 5 loading states (one per question)
        assert home_html.count("loading-state") >= 5

    def test_homepage_every_card_is_clickable(self, client):
        """Every card in the CEO briefing must be clickable (no dead-ends)."""
        # Check both app.html and all external JS files (modularized into /static/js/*.js)
        html = client.get("/app.html").text
        import re
        js_files = re.findall(r'<script[^>]*src="(/static/js/[^"]+)"', html)
        combined = html
        for js_path in js_files:
            js_resp = client.get(js_path)
            if js_resp.status_code == 200:
                combined += "\n" + js_resp.text
        assert "openDrilldown" in combined
        assert "cursor-pointer" in combined


# ═══════════════════════════════════════════════════════════════════════════
# 3. CEO BRIEFING CONTENT QUALITY
# ═══════════════════════════════════════════════════════════════════════════

class TestCEOBriefingQuality:
    """The briefing content must be specific and actionable — no 'so what?' moments."""

    def test_one_thing_has_linked_laws(self, client):
        """The 'one thing' recommendation should reference the laws it's based on."""
        resp = client.get("/api/oem/ceo-briefing")
        ot = resp.json()["one_thing"]
        # If there are recommendations, they should have linked_laws
        if ot["rec_id"]:
            assert "linked_laws" in ot

    def test_money_losses_have_specific_costs(self, client):
        """Each money loss should have a specific estimated cost, not just 'money lost'."""
        resp = client.get("/api/oem/ceo-briefing")
        money = resp.json()["money"]
        for loss in money["losses"]:
            # The estimated_cost should contain a specific unit (h/week, revenue, etc.)
            cost = loss["estimated_cost"].lower()
            assert any(unit in cost for unit in ["h/week", "revenue", "cost", "delay", "lost", "wasted"]), \
                f"Money loss has no specific cost unit: {loss['estimated_cost']}"

    def test_knowledge_traps_have_specific_risks(self, client):
        """Each knowledge trap should have a specific risk, not just 'risk'."""
        resp = client.get("/api/oem/ceo-briefing")
        knowledge = resp.json()["knowledge"]
        for trap in knowledge["traps"]:
            # The risk should be a sentence, not just a word
            assert len(trap["risk"]) > 15, f"Knowledge trap risk too short: {trap['risk']}"

    def test_ceo_decisions_have_specific_questions(self, client):
        """Each CEO decision should have a specific question, not just 'decide something'."""
        resp = client.get("/api/oem/ceo-briefing")
        decisions = resp.json()["decisions"]
        for d in decisions["decisions"]:
            # The question should end with a ? or be a clear imperative
            assert "?" in d["question"] or len(d["question"]) > 15, \
                f"CEO decision question too vague: {d['question']}"

    def test_briefing_generated_at_present(self, client):
        """The briefing should have a timestamp so the CEO knows when it was generated."""
        resp = client.get("/api/oem/ceo-briefing")
        data = resp.json()
        assert "generated_at" in data
        assert data["generated_at"] is not None
