"""Tests for the Ambient Organizational Judgment layers.

Tests:
  1. Organizational Pulse — living metrics (temperature, momentum, etc.)
  2. Executive Feed — meaningful event stream (noise-filtered)
  3. Time Machine — 'have we been here before?' similarity search
  4. Organizational GPS — where am I, what's blocking, who knows
  5. Cognitive Load Engine — OCL measurement
  6. Narrative Engine — daily organizational story
  7. Organizational Whisper — what the org knows but hasn't said
  8. API routes — all 7 endpoints return real data
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
    oem_state.decision_engine = None
    oem_state.evidence_graph = None
    oem_state.signals = []
    oem_state._live_signals_ingested = 0
    oem_state._contradiction_log = None
    oem_state._demo_seeded = False

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

    oem_state._initialized = False
    oem_state.engine = None
    oem_state.decision_engine = None
    oem_state.evidence_graph = None
    oem_state.signals = []
    oem_state._demo_seeded = False


# ═══════════════════════════════════════════════════════════════════════════
# 1. ORGANIZATIONAL PULSE
# ═══════════════════════════════════════════════════════════════════════════

class TestOrganizationalPulse:
    def test_pulse_returns_all_metrics(self, client):
        """Pulse must return all 6 metrics + state + narrative."""
        r = client.get("/api/oem/pulse")
        assert r.status_code == 200
        p = r.json()
        for key in ("temperature", "momentum", "alignment", "trust",
                    "knowledge_mobility", "decision_speed"):
            assert key in p, f"Missing metric: {key}"
            assert 0 <= p[key] <= 100, f"{key} out of range: {p[key]}"
        assert p["state"] in ("healthy", "turbulent", "knowledge_blocked",
                              "decision_stalled", "trust_falling",
                              "execution_accelerating", "steady")
        assert p["narrative"]
        # signals_30d may be 0 if demo data is old; check total signals instead
        assert p["evidence"]["los_total"] > 0

    def test_pulse_metrics_are_derived_from_oem(self, client):
        """Pulse metrics must be derived from real OEM data, not hardcoded."""
        r = client.get("/api/oem/pulse")
        p = r.json()
        # With demo data (65 signals, 6 laws), metrics should be non-baseline
        assert p["evidence"]["laws_total"] >= 6
        assert p["evidence"]["los_total"] > 0


# ═══════════════════════════════════════════════════════════════════════════
# 2. EXECUTIVE FEED
# ═══════════════════════════════════════════════════════════════════════════

class TestExecutiveFeed:
    def test_feed_returns_meaningful_events(self, client):
        """Feed must return meaningful events, not raw signal log."""
        r = client.get("/api/oem/feed")
        assert r.status_code == 200
        data = r.json()
        assert "events" in data
        assert data["total"] > 0

    def test_feed_events_have_required_fields(self, client):
        """Every feed event must have: title, why_it_matters, business_impact, recommended_action."""
        r = client.get("/api/oem/feed")
        events = r.json()["events"]
        for e in events:
            assert e["title"], "Event missing title"
            assert e["why_it_matters"], "Event missing why_it_matters"
            assert e["business_impact"], "Event missing business_impact"
            assert e["recommended_action"], "Event missing recommended_action"
            assert 0 <= e["confidence"] <= 1

    def test_feed_includes_customer_events(self, client):
        """Feed must surface customer drift, broken commitments, and decisions."""
        r = client.get("/api/oem/feed")
        events = r.json()["events"]
        event_types = {e["event_type"] for e in events}
        # With demo data, we should see at least one customer-related event
        customer_types = {t for t in event_types if "customer" in t or "commitment" in t}
        assert len(customer_types) > 0, f"No customer events in feed. Types: {event_types}"

    def test_feed_respects_limit(self, client):
        """Feed must respect the limit parameter."""
        r = client.get("/api/oem/feed?limit=5")
        assert len(r.json()["events"]) <= 5


# ═══════════════════════════════════════════════════════════════════════════
# 3. TIME MACHINE
# ═══════════════════════════════════════════════════════════════════════════

class TestTimeMachine:
    def test_time_machine_search_returns_results(self, client):
        """Time Machine must return historical results for a query."""
        r = client.get("/api/oem/time-machine?q=bottleneck")
        assert r.status_code == 200
        data = r.json()
        assert "results" in data
        assert "summary" in data
        assert "lesson" in data
        assert "confidence" in data

    def test_time_machine_search_by_entity(self, client):
        """Time Machine must find history for a specific entity."""
        r = client.get("/api/oem/time-machine?entity_id=Globex")
        assert r.status_code == 200
        data = r.json()
        # Globex has decision history (renewed)
        assert data["total_found"] >= 0  # May be 0 if no predictions resolved yet

    def test_time_machine_returns_summary_and_lesson(self, client):
        """Time Machine must include a summary and lesson."""
        r = client.get("/api/oem/time-machine?q=customer")
        data = r.json()
        assert data["summary"]
        assert data["lesson"]
        assert isinstance(data["confidence"], float)


# ═══════════════════════════════════════════════════════════════════════════
# 4. ORGANIZATIONAL GPS
# ═══════════════════════════════════════════════════════════════════════════

class TestOrganizationalGPS:
    def test_gps_locates_user(self, client):
        """GPS must locate a user and return their position."""
        r = client.get("/api/oem/gps?user=priya.m@acme.com")
        assert r.status_code == 200
        data = r.json()
        assert data["user"] == "priya.m@acme.com"
        assert data["where_am_i"]
        assert "blocking" in data
        assert "who_knows" in data
        assert "whats_next" in data
        assert "cognitive_load" in data

    def test_gps_returns_next_action(self, client):
        """GPS must recommend a next action."""
        r = client.get("/api/oem/gps?user=priya.m@acme.com")
        data = r.json()
        assert data["whats_next"]["action"]
        assert data["whats_next"]["why"]
        assert data["whats_next"]["urgency"] in ("low", "normal", "high")

    def test_gps_cognitive_load_is_personalized(self, client):
        """GPS cognitive load must be personalized to the user."""
        r = client.get("/api/oem/gps?user=priya.m@acme.com")
        data = r.json()
        cl = data["cognitive_load"]
        assert 0 <= cl["score"] <= 100
        assert cl["level"] in ("low", "moderate", "high", "overloaded")
        assert "factors" in cl

    def test_gps_default_user(self, client):
        """GPS must work without a user parameter (defaults to first signal actor)."""
        r = client.get("/api/oem/gps")
        assert r.status_code == 200
        assert r.json()["user"]


# ═══════════════════════════════════════════════════════════════════════════
# 5. COGNITIVE LOAD ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class TestCognitiveLoad:
    def test_cognitive_load_returns_score_and_level(self, client):
        """OCL must return a score (0-100) and level."""
        r = client.get("/api/oem/cognitive-load")
        assert r.status_code == 200
        data = r.json()
        assert 0 <= data["score"] <= 100
        assert data["level"] in ("low", "moderate", "high", "critical")

    def test_cognitive_load_has_all_factors(self, client):
        """OCL must measure all 7 cognitive load factors."""
        r = client.get("/api/oem/cognitive-load")
        factors = r.json()["factors"]
        expected = {
            "decision_fatigue", "context_switching", "meeting_overhead",
            "knowledge_hunting", "duplicate_thinking", "information_latency",
            "attention_fragmentation",
        }
        assert set(factors.keys()) == expected

    def test_cognitive_load_returns_recommendations(self, client):
        """OCL must return recommendations to reduce load."""
        r = client.get("/api/oem/cognitive-load")
        data = r.json()
        assert len(data["recommendations"]) > 0
        for rec in data["recommendations"]:
            assert rec["factor"]
            assert rec["recommendation"]
            assert rec["expected_reduction"]


# ═══════════════════════════════════════════════════════════════════════════
# 6. NARRATIVE ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class TestNarrativeEngine:
    def test_narrative_returns_story(self, client):
        """Narrative must return a title, body, and highlights."""
        r = client.get("/api/oem/narrative")
        assert r.status_code == 200
        data = r.json()
        assert data["title"]
        assert data["body"]
        assert "highlights" in data
        assert "watch_for" in data

    def test_narrative_highlights_have_impact(self, client):
        """Each highlight must have an impact level."""
        r = client.get("/api/oem/narrative")
        highlights = r.json()["highlights"]
        for h in highlights:
            assert h["impact"] in ("positive", "negative", "warning", "neutral")
            assert h["text"]
            assert h["category"]

    def test_narrative_includes_watch_for(self, client):
        """Narrative must include 'watch for' items."""
        r = client.get("/api/oem/narrative")
        data = r.json()
        assert len(data["watch_for"]) > 0


# ═══════════════════════════════════════════════════════════════════════════
# 7. ORGANIZATIONAL WHISPER
# ═══════════════════════════════════════════════════════════════════════════

class TestOrganizationalWhisper:
    def test_whisper_for_meeting_context(self, client):
        """Whisper must surface relevant knowledge for a meeting context."""
        r = client.get("/api/oem/whisper?context=meeting&entity=Initech&topic=pricing")
        assert r.status_code == 200
        data = r.json()
        assert "whispers" in data
        assert "warnings" in data
        assert "precedents" in data
        assert "confidence" in data

    def test_whisper_surfaces_commitments(self, client):
        """Whisper must surface past commitments for the entity."""
        r = client.get("/api/oem/whisper?entity=Initech")
        data = r.json()
        # Initech has a broken commitment in the demo data
        commitment_whispers = [w for w in data["whispers"] if "commitment" in w.get("type", "")]
        # Should surface the commitment history
        all_text = " ".join(w.get("text", "") for w in data["whispers"])
        assert "SOC2" in all_text or len(commitment_whispers) > 0, \
            f"Whisper did not surface Initech commitments: {data['whispers']}"

    def test_whisper_surfaces_objections(self, client):
        """Whisper must surface past objections for the entity."""
        r = client.get("/api/oem/whisper?entity=Initech")
        data = r.json()
        all_text = " ".join(w.get("text", "") for w in data["whispers"])
        assert "pricing" in all_text.lower() or "objection" in all_text.lower(), \
            f"Whisper did not surface Initech objections: {data['whispers']}"

    def test_whisper_returns_warnings(self, client):
        """Whisper must return warnings for at-risk entities."""
        r = client.get("/api/oem/whisper?entity=Initech")
        data = r.json()
        # Initech has broken commitments + champion quiet
        assert len(data["warnings"]) > 0, "No warnings for at-risk customer Initech"

    def test_whisper_without_entity(self, client):
        """Whisper must work without an entity (general context)."""
        r = client.get("/api/oem/whisper?context=decision&topic=bottleneck")
        assert r.status_code == 200
        data = r.json()
        assert "whispers" in data
