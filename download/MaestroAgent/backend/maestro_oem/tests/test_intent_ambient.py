"""Tests for the Intent Engine, Interrupt Intelligence, and Ambient endpoint."""

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


class TestIntentEngine:
    def test_infer_negotiation_from_calendar(self, client):
        """Calendar event with external participant → preparing_for_negotiation."""
        r = client.get("/api/oem/intent?active_app=calendar&calendar_title=Q4 renewal with Globex&calendar_participants=raj@globex.com")
        assert r.status_code == 200
        d = r.json()
        assert d["intent"] == "preparing_for_negotiation"
        assert d["confidence"] > 0
        assert len(d["why"]) > 0
        assert d["recommended_whisper"] is not None

    def test_infer_code_review_from_github(self, client):
        """GitHub active → reviewing_code intent."""
        r = client.get("/api/oem/intent?active_app=github&url_context=github.com")
        d = r.json()
        assert d["intent"] == "reviewing_code"
        assert d["confidence"] > 0

    def test_infer_board_prep_from_calendar(self, client):
        """Calendar event with 'board' → board_update_preparation."""
        r = client.get("/api/oem/intent?active_app=calendar&calendar_title=Board meeting Q4")
        d = r.json()
        assert d["intent"] == "board_update_preparation"

    def test_intent_returns_alternatives(self, client):
        """Intent should return alternative intents with lower confidence."""
        r = client.get("/api/oem/intent?active_app=github")
        d = r.json()
        assert "alternative_intents" in d
        assert isinstance(d["alternative_intents"], list)

    def test_intent_returns_what_maestro_knows(self, client):
        """Intent should include relevant OEM knowledge."""
        r = client.get("/api/oem/intent?active_app=calendar&calendar_title=Q4 renewal&calendar_participants=raj@globex.com")
        d = r.json()
        assert "what_maestro_knows" in d

    def test_intent_returns_whisper_recommendation(self, client):
        """Intent should recommend a whisper when relevant."""
        r = client.get("/api/oem/intent?active_app=calendar&calendar_title=Q4 renewal&calendar_participants=raj@globex.com")
        d = r.json()
        assert d["recommended_whisper"] is not None
        assert "text" in d["recommended_whisper"]
        assert "action" in d["recommended_whisper"]


class TestInterruptEngine:
    def test_interrupt_evaluates_feed(self, client):
        """Interrupt endpoint evaluates feed events and returns prioritized list."""
        r = client.get("/api/oem/interrupt?user=jane.d@acme.com")
        assert r.status_code == 200
        d = r.json()
        assert "events_needing_attention" in d
        assert "total_evaluated" in d
        assert "total_suppressed" in d
        assert d["total_evaluated"] >= d["total_suppressed"]  # Some may be suppressed

    def test_interrupt_includes_user_context(self, client):
        """Interrupt should include user's cognitive load and inferred intent."""
        r = client.get("/api/oem/interrupt?user=jane.d@acme.com&active_app=calendar")
        d = r.json()
        assert "cognitive_load" in d
        assert "inferred_intent" in d

    def test_interrupt_events_have_priority(self, client):
        """Each interrupt event must have a priority and delivery method."""
        r = client.get("/api/oem/interrupt?user=jane.d@acme.com")
        d = r.json()
        for ev in d["events_needing_attention"]:
            decision = ev.get("interrupt_decision", {})
            assert decision["priority"] in ("ignore", "notify", "recommend", "escalate", "interrupt")
            assert decision["delivery"] in ("silent", "badge", "toast", "banner", "modal")


class TestAmbientEndpoint:
    def test_ambient_returns_should_show(self, client):
        """Ambient endpoint returns should_show flag."""
        r = client.get("/api/oem/ambient?user=jane.d@acme.com&active_app=calendar&calendar_title=Q4 renewal with Globex")
        assert r.status_code == 200
        d = r.json()
        assert "should_show" in d
        assert isinstance(d["should_show"], bool)

    def test_ambient_returns_intent_and_whisper(self, client):
        """Ambient returns inferred intent + whisper when relevant."""
        r = client.get("/api/oem/ambient?user=jane.d@acme.com&active_app=calendar&calendar_title=Q4 renewal with Globex")
        d = r.json()
        assert "intent" in d
        assert d["intent"]["intent"] == "preparing_for_negotiation"
        if d["should_show"]:
            assert d["whisper"] is not None

    def test_ambient_returns_pulse(self, client):
        """Ambient returns organizational pulse state."""
        r = client.get("/api/oem/ambient?user=jane.d@acme.com")
        d = r.json()
        assert "pulse" in d
        assert "state" in d["pulse"]
        assert "narrative" in d["pulse"]

    def test_ambient_returns_interrupts(self, client):
        """Ambient returns prioritized interrupts."""
        r = client.get("/api/oem/ambient?user=jane.d@acme.com")
        d = r.json()
        assert "interrupts" in d
        assert isinstance(d["interrupts"], list)

    def test_ambient_returns_cognitive_load(self, client):
        """Ambient returns user's cognitive load."""
        r = client.get("/api/oem/ambient?user=priya.m@acme.com")
        d = r.json()
        assert "cognitive_load" in d
        if d["cognitive_load"]:
            assert "level" in d["cognitive_load"]


class TestAmbientOverlay:
    def test_ambient_install_page_exists(self, client):
        """The ambient overlay installation page should be accessible."""
        # This is a static HTML file, not an API route
        import os
        app_dir = os.environ.get("MAESTRO_APP_DIR", ".")
        install_path = Path(app_dir) / "ambient-install.html"
        assert install_path.exists(), "ambient-install.html not found"

    def test_ambient_js_exists(self, client):
        """The ambient overlay JS should exist in static/."""
        import os
        app_dir = os.environ.get("MAESTRO_APP_DIR", ".")
        js_path = Path(app_dir) / "static" / "maestro-ambient.js"
        assert js_path.exists(), "static/maestro-ambient.js not found"
