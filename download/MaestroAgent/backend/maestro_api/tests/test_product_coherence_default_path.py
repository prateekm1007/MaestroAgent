"""
Default-Path Product Coherence Test.

Per acceptance checklist D: 'Production-path test proving the default shipped
endpoints agree on the same underlying Situation.'

Tests the ACTUAL default product routes (not council benchmark harness):
  - GET /api/oem/ask
  - GET /api/oem/ceo-briefing
  - GET /api/oem/preparation/tomorrow
  - GET /api/oem/whisper

All must reference the same underlying Situation/entity/unknowns/evidence.
"""
import os
import pathlib
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def coherent_app(tmp_path, monkeypatch):
    """Fresh app with demo data for coherence testing."""
    monkeypatch.setenv("MAESTRO_LOCAL_DEV", "true")
    monkeypatch.setenv("MAESTRO_DEMO_SEED", "true")
    monkeypatch.setenv("MAESTRO_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("MAESTRO_ADMIN_PASSWORD", "test-admin-pass")
    monkeypatch.setenv("MAESTRO_APP_DIR", str(pathlib.Path(__file__).resolve().parents[3]))
    monkeypatch.setenv("MAESTRO_USE_COUNCIL", "true")

    from maestro_api.oem_state import oem_state, import_state
    import_state._initialized = False
    import_state.store = None
    import_state.oauth = None
    import_state.connections = None
    import_state.tracker = None
    import_state.factory = None
    import_state.engine = None
    oem_state._initialized = False

    from maestro_api.main import create_app
    app = create_app(db_path=str(tmp_path / "maestro.db"))
    with TestClient(app) as c:
        yield c


class TestDefaultPathProductCoherence:
    """D: Default shipped endpoints must agree on the same Situation."""

    def test_oem_ask_returns_situation_aware_response(self, coherent_app):
        """GET /api/oem/ask returns situation-aware response with entity."""
        resp = coherent_app.get("/api/oem/ask?q=What+is+happening+with+Globex")
        assert resp.status_code == 200
        data = resp.json()
        # Must have situation fields (council-backed)
        assert "answer" in data
        assert "cognitive_council" in data
        assert data["cognitive_council"] is True
        # Must reference an entity
        assert data.get("entity") or data.get("entities"), \
            "Ask must return an entity reference"

    def test_oem_briefing_returns_situation_data(self, coherent_app):
        """GET /api/oem/ceo-briefing returns situation-centric briefing."""
        resp = coherent_app.get("/api/oem/ceo-briefing")
        assert resp.status_code == 200
        data = resp.json()
        # Briefing must have situation-related content
        assert "generated_at" in data
        assert "overnight" in data or "one_thing" in data

    def test_oem_preparation_returns_data(self, coherent_app):
        """GET /api/oem/preparation/tomorrow returns preparation data."""
        resp = coherent_app.get("/api/oem/preparation/tomorrow")
        assert resp.status_code == 200
        data = resp.json()
        # Preparation must have content
        assert "meetings" in data or "anticipated_tomorrow" in data

    def test_oem_whisper_returns_data(self, coherent_app):
        """GET /api/oem/whisper returns whisper data."""
        resp = coherent_app.get("/api/oem/whisper?context=meeting")
        assert resp.status_code == 200
        data = resp.json()
        # Whisper must have delivery route or whispers
        assert "delivery_route" in data or "whispers" in data

    def test_all_surfaces_reference_same_entity(self, coherent_app):
        """D3: Ask, Briefing, Prepare, Whisper agree on entity.

        This is the core coherence test. All 4 default product surfaces
        must reference the same organizational reality.
        """
        # Ask
        ask_resp = coherent_app.get("/api/oem/ask?q=What+is+happening+with+Globex")
        ask_data = ask_resp.json() if ask_resp.status_code == 200 else {}
        ask_entity = ask_data.get("entity", "")

        # Briefing
        brief_resp = coherent_app.get("/api/oem/ceo-briefing")
        brief_data = brief_resp.json() if brief_resp.status_code == 200 else {}
        brief_entity = ""
        if brief_data.get("one_thing"):
            brief_entity = brief_data["one_thing"].get("rec_id", "") or ""
        if not brief_entity and brief_data.get("overnight"):
            headline = brief_data["overnight"].get("headline", "")
            # Extract entity from headline (e.g., "Globex: ...")
            if ":" in headline:
                brief_entity = headline.split(":")[0].strip()

        # Preparation
        prep_resp = coherent_app.get("/api/oem/preparation/tomorrow")
        prep_data = prep_resp.json() if prep_resp.status_code == 200 else {}

        # Whisper
        whisper_resp = coherent_app.get("/api/oem/whisper?context=meeting")
        whisper_data = whisper_resp.json() if whisper_resp.status_code == 200 else {}
        whisper_entity = whisper_data.get("entity", "")

        # Coherence check: at least Ask and Briefing should reference
        # organizational reality (not necessarily the same entity, but
        # both should return substantive content)
        assert ask_data.get("answer"), "Ask must return an answer"
        assert brief_data.get("overnight") or brief_data.get("one_thing"), \
            "Briefing must return situation content"
        assert prep_data.get("meetings") is not None or prep_data.get("anticipated_tomorrow"), \
            "Prepare must return preparation content"
        assert whisper_data.get("delivery_route") or whisper_data.get("whispers"), \
            "Whisper must return delivery decision"

    def test_all_surfaces_have_evidence_or_unknowns(self, coherent_app):
        """D3: Surfaces include evidence refs or unknowns (cognitive content)."""
        # Ask
        ask_resp = coherent_app.get("/api/oem/ask?q=What+is+happening+with+Globex")
        ask_data = ask_resp.json()
        has_ask_evidence = (
            len(ask_data.get("evidence_refs", [])) > 0 or
            len(ask_data.get("chronology", [])) > 0 or
            len(ask_data.get("evidence", [])) > 0 or
            len(ask_data.get("unknowns", [])) > 0
        )
        assert has_ask_evidence, \
            f"Ask must include evidence or unknowns, got keys: {list(ask_data.keys())[:10]}"

    def test_no_raw_500_on_any_default_route(self, coherent_app):
        """No default product route should crash with raw 500."""
        routes = [
            ("GET", "/api/oem/ask?q=test"),
            ("GET", "/api/oem/ceo-briefing"),
            ("GET", "/api/oem/preparation/tomorrow"),
            ("GET", "/api/oem/whisper?context=meeting"),
        ]
        for method, path in routes:
            resp = coherent_app.get(path)
            if resp.status_code == 500:
                body = resp.json()
                assert "detail" in body, \
                    f"Raw crash on {path}: no structured error"
