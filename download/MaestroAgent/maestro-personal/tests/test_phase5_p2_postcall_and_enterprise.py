"""
Tests for the 5 Phase 5 P2 + Phase 7 enterprise features (gap 22/30 → 30/30).

Verifies:
  1. FollowUpEmailGenerator — commitment-aware drafts, tone inference,
     org-law citation, send-time suggestion
  2. PreCallIntelPanel — Forgotten/Open-Question/Contradiction +
     talk tracks + staleness check
  3. PostCallSummaryUI — full payload (hero, stats, commitments,
     objections, draft email, learning)
  4. PlaybookEngine — load defaults, match transcript, upsert/delete,
     record outcome + promotion to learned_responses
  5. ShadowMode — start/end session, add notes, leave feedback,
     list sessions, isolation
  6. API integration — all 13 new endpoints return 200 + correct shape

These tests close the auditor-flagged gaps and bring the Cluely Killer
feature tracker from 22/30 → 30/30.
"""

import sys
import os
import tempfile
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_api():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-phase5p2"
    os.environ.pop("MAESTRO_PERSONAL_ENV", None)

    import importlib
    import maestro_personal_shell.api as api_module
    importlib.reload(api_module)
    api_module.init_db(db_path)

    try:
        from maestro_personal_shell.semantic_retrieval import init_fts_index, rebuild_fts_index
        init_fts_index(db_path)
        rebuild_fts_index(db_path)
    except Exception:
        pass

    yield api_module

    os.unlink(db_path)
    os.environ.pop("MAESTRO_PERSONAL_DB", None)
    os.environ.pop("MAESTRO_PERSONAL_TOKEN", None)


@pytest.fixture
def client(isolated_api):
    return TestClient(isolated_api.app)


@pytest.fixture
def auth_headers(client):
    response = client.post(
        "/api/auth/login",
        json={"password": os.environ.get("MAESTRO_PERSONAL_TOKEN", "test")},
    )
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _mock_shell_with_signals(signals: list, laws: list = None):
    """Build a mock shell with signals and laws for testing."""
    shell = MagicMock()
    shell.core = MagicMock()
    shell.core.signals = signals
    shell.core.laws = laws or []
    return shell


def _make_signal(entity, text, signal_type="commitment_made", timestamp="2026-07-01T10:00:00Z"):
    """Build a mock signal."""
    s = MagicMock()
    s.entity = entity
    s.text = text
    s.signal_type = signal_type
    s.timestamp = timestamp
    return s


# ---------------------------------------------------------------------------
# 1. FollowUpEmailGenerator
# ---------------------------------------------------------------------------

class TestFollowUpEmailGenerator:
    """Phase 5 P2: commitment-aware follow-up email drafts."""

    def test_generates_subject_and_body(self):
        from maestro_personal_shell.copilot_postcall_features import FollowUpEmailGenerator
        gen = FollowUpEmailGenerator(shell=None)
        result = gen.generate(
            meeting_title="Q3 Pricing Review",
            participants=["alex@acme.com", "maria@acme.com"],
            commitments=[{"text": "send the proposal by Friday", "actor": "alex@acme.com"}],
            entity="AcmeCorp",
        )
        assert "Follow-up — Q3 Pricing Review" in result["subject"]
        assert "send the proposal by Friday" in result["body"]
        assert "alex" in result["body"].lower()
        assert result["commitment_count"] == 1

    def test_tone_inferred_direct_for_stale_commitments(self):
        from maestro_personal_shell.copilot_postcall_features import FollowUpEmailGenerator
        gen = FollowUpEmailGenerator(shell=None)
        result = gen.generate(
            commitments=[{"text": "old commitment", "days_stale": 10}],
            entity="AcmeCorp",
        )
        assert result["tone"] == "direct"

    def test_tone_professional_default(self):
        from maestro_personal_shell.copilot_postcall_features import FollowUpEmailGenerator
        gen = FollowUpEmailGenerator(shell=None)
        result = gen.generate(commitments=[], entity="AcmeCorp")
        assert result["tone"] == "professional"

    def test_send_time_now_for_stale(self):
        from maestro_personal_shell.copilot_postcall_features import FollowUpEmailGenerator
        gen = FollowUpEmailGenerator(shell=None)
        result = gen.generate(commitments=[{"days_stale": 10}])
        assert result["suggested_send_time"] == "now"

    def test_send_time_within_4h_default(self):
        from maestro_personal_shell.copilot_postcall_features import FollowUpEmailGenerator
        gen = FollowUpEmailGenerator(shell=None)
        result = gen.generate(commitments=[{"days_stale": 1}])
        assert result["suggested_send_time"] == "within_4h"

    def test_objections_produce_action_items(self):
        from maestro_personal_shell.copilot_postcall_features import FollowUpEmailGenerator
        gen = FollowUpEmailGenerator(shell=None)
        result = gen.generate(
            commitments=[],
            objections=[{"type": "price_too_high"}],
        )
        assert "Action items" in result["body"]
        assert "price_too_high" in result["body"]

    def test_cites_organizational_laws(self):
        from maestro_personal_shell.copilot_postcall_features import FollowUpEmailGenerator
        # Mock shell with a law that overlaps with transcript words (need >=2 overlap)
        shell = _mock_shell_with_signals(
            signals=[],
            laws=[{"statement": "Always anchor pricing before discussing discounts",
                   "confidence": 0.9}],
        )
        gen = FollowUpEmailGenerator(shell=shell)
        result = gen.generate(
            transcript_chunks=[{"text": "We need to anchor pricing and discuss discounts"}],
        )
        assert result["evidence_count"] >= 1
        assert "anchor pricing" in result["body"].lower()


# ---------------------------------------------------------------------------
# 2. PreCallIntelPanel
# ---------------------------------------------------------------------------

class TestPreCallIntelPanel:
    """Phase 5 P2: pre-call intelligence panel."""

    def test_empty_entity_returns_empty_panel(self):
        from maestro_personal_shell.copilot_postcall_features import PreCallIntelPanel
        panel = PreCallIntelPanel(shell=None)
        result = panel.build(entity="")
        assert result["the_forgotten"] is None
        assert result["the_open_question"] is None
        assert result["the_contradiction"] is None

    def test_finds_the_forgotten_oldest_commitment(self):
        from maestro_personal_shell.copilot_postcall_features import PreCallIntelPanel
        signals = [
            _make_signal("AcmeCorp", "I will send the proposal", "commitment_made", "2026-07-10T10:00:00Z"),
            _make_signal("AcmeCorp", "I will send the report", "commitment_made", "2026-06-15T10:00:00Z"),  # older
        ]
        shell = _mock_shell_with_signals(signals)
        panel = PreCallIntelPanel(shell=shell)
        result = panel.build(entity="AcmeCorp")
        assert result["the_forgotten"] is not None
        assert "report" in result["the_forgotten"]["text"]
        assert result["the_forgotten"]["days_stale"] > 0

    def test_finds_open_question(self):
        from maestro_personal_shell.copilot_postcall_features import PreCallIntelPanel
        signals = [
            _make_signal("AcmeCorp", "When can you deliver?", "follow_up_required", "2026-07-10T10:00:00Z"),
        ]
        shell = _mock_shell_with_signals(signals)
        panel = PreCallIntelPanel(shell=shell)
        result = panel.build(entity="AcmeCorp")
        assert result["the_open_question"] is not None
        assert "deliver" in result["the_open_question"]["text"]

    def test_finds_contradiction(self):
        from maestro_personal_shell.copilot_postcall_features import PreCallIntelPanel
        signals = [
            _make_signal("AcmeCorp", "Actually, we never agreed to that", "contradiction", "2026-07-10T10:00:00Z"),
        ]
        shell = _mock_shell_with_signals(signals)
        panel = PreCallIntelPanel(shell=shell)
        result = panel.build(entity="AcmeCorp")
        assert result["the_contradiction"] is not None

    def test_staleness_check(self):
        from maestro_personal_shell.copilot_postcall_features import PreCallIntelPanel
        # Signal from 30 days ago — stale
        signals = [
            _make_signal("AcmeCorp", "old signal", "commitment_made", "2026-06-01T10:00:00Z"),
        ]
        shell = _mock_shell_with_signals(signals)
        panel = PreCallIntelPanel(shell=shell)
        result = panel.build(entity="AcmeCorp")
        assert result["is_stale"] is True

    def test_greeting_adapts_to_signal_count(self):
        from maestro_personal_shell.copilot_postcall_features import PreCallIntelPanel
        # 0 signals
        shell = _mock_shell_with_signals([])
        panel = PreCallIntelPanel(shell=shell)
        result = panel.build(entity="NewEntity")
        assert "First interaction" in result["greeting"]

        # Many signals
        shell = _mock_shell_with_signals([_make_signal("AcmeCorp", f"signal {i}") for i in range(10)])
        panel = PreCallIntelPanel(shell=shell)
        result = panel.build(entity="AcmeCorp")
        assert "well-tracked" in result["greeting"]


# ---------------------------------------------------------------------------
# 3. PostCallSummaryUI
# ---------------------------------------------------------------------------

class TestPostCallSummaryUI:
    """Phase 5 P2: post-call summary UI payload."""

    def test_full_payload_shape(self):
        from maestro_personal_shell.copilot_postcall_features import PostCallSummaryUI
        builder = PostCallSummaryUI(shell=None)
        result = builder.build(
            meeting_title="Test Meeting",
            duration_seconds=1800,
            participants=["alex@acme.com"],
            transcript_chunks=[{"speaker": "alex", "text": "hi"}],
            suggestion_cards=[
                {"card_type": "commitment", "text": "send proposal", "evidence": {"speaker": "alex"}},
                {"card_type": "objection", "text": "price too high", "confidence": 0.8, "confidence_label": "high"},
            ],
            entity="AcmeCorp",
            talk_ratio_pct=65.0,
        )
        assert "hero_summary" in result
        assert "key_stats" in result
        assert "commitments_tracked" in result
        assert "objections_raised" in result
        assert "draft_email" in result
        assert "what_maestro_learned" in result

    def test_hero_card_duration_minutes(self):
        from maestro_personal_shell.copilot_postcall_features import PostCallSummaryUI
        builder = PostCallSummaryUI(shell=None)
        result = builder.build(duration_seconds=1800)
        assert result["hero_summary"]["duration_minutes"] == 30.0

    def test_talk_ratio_status_coaching(self):
        from maestro_personal_shell.copilot_postcall_features import PostCallSummaryUI
        builder = PostCallSummaryUI(shell=None)
        result = builder.build(talk_ratio_pct=85.0)
        assert result["key_stats"]["talk_ratio_status"] == "talking_too_much"
        result = builder.build(talk_ratio_pct=25.0)
        assert result["key_stats"]["talk_ratio_status"] == "listening_well"

    def test_commitments_tracked_with_actor(self):
        from maestro_personal_shell.copilot_postcall_features import PostCallSummaryUI
        builder = PostCallSummaryUI(shell=None)
        result = builder.build(
            suggestion_cards=[
                {"card_type": "commitment", "text": "send proposal", "evidence": {"speaker": "alex@acme.com"}},
            ],
        )
        assert len(result["commitments_tracked"]) == 1
        assert result["commitments_tracked"][0]["actor"] == "alex@acme.com"
        assert result["commitments_tracked"][0]["status"] == "Tracked"

    def test_learning_section_reports_new_signals(self):
        from maestro_personal_shell.copilot_postcall_features import PostCallSummaryUI
        builder = PostCallSummaryUI(shell=None)
        result = builder.build(
            suggestion_cards=[
                {"card_type": "commitment", "text": "commitment 1"},
                {"card_type": "commitment", "text": "commitment 2"},
                {"card_type": "objection", "text": "objection 1"},
            ],
        )
        learned = result["what_maestro_learned"]
        assert learned["new_signals_ingested"] == 2
        assert learned["objection_pattern_data_points"] == 1
        assert learned["data_points_to_validated_law"] == 4  # 5 - 1
        assert learned["learning_active"] is True

    def test_draft_email_included_in_summary(self):
        from maestro_personal_shell.copilot_postcall_features import PostCallSummaryUI
        builder = PostCallSummaryUI(shell=None)
        result = builder.build(
            meeting_title="Sync",
            suggestion_cards=[{"card_type": "commitment", "text": "follow up"}],
        )
        assert "subject" in result["draft_email"]
        assert "body" in result["draft_email"]
        assert "Sync" in result["draft_email"]["subject"]


# ---------------------------------------------------------------------------
# 4. PlaybookEngine
# ---------------------------------------------------------------------------

class TestPlaybookEngine:
    """Phase 7: playbook engine with learning loop."""

    def test_load_seeds_defaults(self, tmp_path):
        from maestro_personal_shell.copilot_enterprise import PlaybookEngine
        engine = PlaybookEngine(db_path=str(tmp_path / "test.db"))
        playbooks = engine.load()
        assert len(playbooks) >= 3  # discovery, negotiation, renewal
        ids = [p["id"] for p in playbooks]
        assert "discovery-call" in ids
        assert "negotiation" in ids
        assert "renewal" in ids

    def test_match_transcript_returns_playbook(self, tmp_path):
        from maestro_personal_shell.copilot_enterprise import PlaybookEngine
        engine = PlaybookEngine(db_path=str(tmp_path / "test.db"))
        engine.load()
        match = engine.match_transcript("prospect wants a discount on pricing")
        assert match is not None
        assert match["playbook_id"] == "negotiation"
        assert len(match["talk_tracks"]) >= 2
        assert "price_too_high" in match["objection_responses"]

    def test_match_transcript_returns_none_when_no_match(self, tmp_path):
        from maestro_personal_shell.copilot_enterprise import PlaybookEngine
        engine = PlaybookEngine(db_path=str(tmp_path / "test.db"))
        engine.load()
        match = engine.match_transcript("totally unrelated weather chat")
        assert match is None

    def test_upsert_custom_playbook(self, tmp_path):
        from maestro_personal_shell.copilot_enterprise import PlaybookEngine
        engine = PlaybookEngine(db_path=str(tmp_path / "test.db"))
        engine.load()
        new_pb = engine.upsert({
            "id": "custom-demo",
            "name": "Demo Call",
            "triggers": ["demo", "walkthrough"],
            "talk_tracks": [{"text": "Open with their use case", "rationale": "Personalize"}],
            "objection_responses": {"need_to_think": "Schedule follow-up"},
        })
        assert new_pb["id"] == "custom-demo"

        # Verify it persists
        engine2 = PlaybookEngine(db_path=str(tmp_path / "test.db"))
        engine2.load()
        match = engine2.match_transcript("let's do a demo")
        assert match is not None
        assert match["playbook_id"] == "custom-demo"

    def test_delete_playbook(self, tmp_path):
        from maestro_personal_shell.copilot_enterprise import PlaybookEngine
        engine = PlaybookEngine(db_path=str(tmp_path / "test.db"))
        engine.load()
        assert engine.delete("discovery-call") is True
        assert engine.get_playbook("discovery-call") is None

    def test_record_outcome_and_promotion(self, tmp_path):
        from maestro_personal_shell.copilot_enterprise import PlaybookEngine
        engine = PlaybookEngine(db_path=str(tmp_path / "test.db"))
        engine.load()

        # Record 3 positive outcomes for talk track 0 of negotiation
        for _ in range(3):
            result = engine.record_outcome("negotiation", 0, "positive")
            assert result["recorded"] is True

        # 4th call should trigger promotion
        result = engine.record_outcome("negotiation", 0, "positive")
        # After 3+ positives, promotion triggers
        pb = engine.get_playbook("negotiation")
        learned = pb["learned_responses"]
        assert any(lr.get("positive_outcomes", 0) >= 3 for lr in learned), \
            "Talk track should be promoted to learned_responses after 3+ positive outcomes"

    def test_invalid_outcome_rejected(self, tmp_path):
        from maestro_personal_shell.copilot_enterprise import PlaybookEngine
        engine = PlaybookEngine(db_path=str(tmp_path / "test.db"))
        engine.load()
        result = engine.record_outcome("negotiation", 0, "invalid")
        assert "error" in result

    def test_list_playbooks_returns_summary(self, tmp_path):
        from maestro_personal_shell.copilot_enterprise import PlaybookEngine
        engine = PlaybookEngine(db_path=str(tmp_path / "test.db"))
        engine.load()
        summary = engine.list_playbooks()
        assert len(summary) >= 3
        assert "trigger_count" in summary[0]
        assert "talk_track_count" in summary[0]


# ---------------------------------------------------------------------------
# 5. ShadowMode
# ---------------------------------------------------------------------------

class TestShadowMode:
    """Phase 7: shadow mode for manager coaching."""

    def test_start_session(self, tmp_path):
        from maestro_personal_shell.copilot_enterprise import ShadowMode
        shadow = ShadowMode(db_path=str(tmp_path / "test.db"))
        session = shadow.start_session(
            manager_email="mgr@acme.com",
            rep_email="rep@acme.com",
            meeting_title="Q3 Review",
            entity="AcmeCorp",
        )
        assert session["session_id"].startswith("shadow-")
        assert session["status"] == "active"
        assert session["rep_email"] == "rep@acme.com"

    def test_end_session(self, tmp_path):
        from maestro_personal_shell.copilot_enterprise import ShadowMode
        shadow = ShadowMode(db_path=str(tmp_path / "test.db"))
        session = shadow.start_session("mgr@acme.com", "rep@acme.com")
        result = shadow.end_session(session["session_id"])
        assert result["status"] == "ended"

    def test_add_and_list_notes(self, tmp_path):
        from maestro_personal_shell.copilot_enterprise import ShadowMode
        shadow = ShadowMode(db_path=str(tmp_path / "test.db"))
        session = shadow.start_session("mgr@acme.com", "rep@acme.com")

        shadow.add_note(session["session_id"], "Slow down on pricing", "let's talk price", "coaching")
        shadow.add_note(session["session_id"], "Good objection handling", "objection", "praise")

        notes = shadow.list_notes(session["session_id"])
        assert len(notes) == 2
        assert notes[0]["note_text"] == "Slow down on pricing"
        assert notes[1]["note_type"] == "praise"

    def test_leave_and_get_feedback(self, tmp_path):
        from maestro_personal_shell.copilot_enterprise import ShadowMode
        shadow = ShadowMode(db_path=str(tmp_path / "test.db"))
        session = shadow.start_session("mgr@acme.com", "rep@acme.com")

        feedback = shadow.leave_feedback(
            session["session_id"],
            overall_rating=4,
            strengths="Strong discovery questions",
            improvements="Could anchor pricing earlier",
            next_steps="Shadow again next week",
        )
        assert feedback["overall_rating"] == 4

        retrieved = shadow.get_feedback(session["session_id"])
        assert retrieved["strengths"] == "Strong discovery questions"

    def test_feedback_clamps_rating(self, tmp_path):
        from maestro_personal_shell.copilot_enterprise import ShadowMode
        shadow = ShadowMode(db_path=str(tmp_path / "test.db"))
        session = shadow.start_session("mgr@acme.com", "rep@acme.com")
        feedback = shadow.leave_feedback(session["session_id"], overall_rating=10)
        assert feedback["overall_rating"] == 5  # clamped

        session2 = shadow.start_session("mgr@acme.com", "rep2@acme.com")
        feedback2 = shadow.leave_feedback(session2["session_id"], overall_rating=0)
        assert feedback2["overall_rating"] == 1  # clamped

    def test_list_sessions_filtered_by_manager(self, tmp_path):
        from maestro_personal_shell.copilot_enterprise import ShadowMode
        shadow = ShadowMode(db_path=str(tmp_path / "test.db"))
        shadow.start_session("mgr1@acme.com", "rep1@acme.com")
        shadow.start_session("mgr1@acme.com", "rep2@acme.com")
        shadow.start_session("mgr2@acme.com", "rep3@acme.com")

        sessions = shadow.list_sessions(manager_email="mgr1@acme.com")
        assert len(sessions) == 2
        assert all(s["manager_email"] == "mgr1@acme.com" for s in sessions)

    def test_get_session_returns_none_for_missing(self, tmp_path):
        from maestro_personal_shell.copilot_enterprise import ShadowMode
        shadow = ShadowMode(db_path=str(tmp_path / "test.db"))
        assert shadow.get_session("nonexistent") is None

    def test_invalid_note_type_defaults_to_coaching(self, tmp_path):
        from maestro_personal_shell.copilot_enterprise import ShadowMode
        shadow = ShadowMode(db_path=str(tmp_path / "test.db"))
        session = shadow.start_session("mgr@acme.com", "rep@acme.com")
        result = shadow.add_note(session["session_id"], "test", note_type="invalid")
        assert result["note_type"] == "coaching"


# ---------------------------------------------------------------------------
# 6. API Integration — all 13 new endpoints
# ---------------------------------------------------------------------------

class TestAPIIntegration:
    """All 13 new endpoints return 200 and correct shape."""

    def test_follow_up_email_endpoint(self, client, auth_headers):
        response = client.post(
            "/api/copilot/follow-up-email",
            headers=auth_headers,
            json={
                "meeting_title": "Test Meeting",
                "participants": ["alex@acme.com"],
                "commitments": [{"text": "send proposal", "actor": "alex@acme.com"}],
                "entity": "AcmeCorp",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "subject" in data
        assert "body" in data
        assert "tone" in data
        assert data["commitment_count"] == 1

    def test_pre_call_intel_endpoint(self, client, auth_headers):
        response = client.post(
            "/api/copilot/pre-call-intel",
            headers=auth_headers,
            json={"entity": "AcmeCorp", "meeting_title": "Q3 Review"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "the_forgotten" in data
        assert "the_open_question" in data
        assert "the_contradiction" in data
        assert "talk_tracks" in data

    def test_pre_call_intel_empty_entity(self, client, auth_headers):
        response = client.post(
            "/api/copilot/pre-call-intel",
            headers=auth_headers,
            json={"entity": ""},
        )
        assert response.status_code == 200
        assert response.json()["the_forgotten"] is None

    def test_post_call_ui_endpoint(self, client, auth_headers):
        response = client.post(
            "/api/copilot/post-call-ui",
            headers=auth_headers,
            json={
                "meeting_title": "Test Meeting",
                "duration_seconds": 1800,
                "participants": ["alex@acme.com"],
                "transcript_chunks": [{"speaker": "alex", "text": "hi"}],
                "suggestion_cards": [
                    {"card_type": "commitment", "text": "send proposal", "evidence": {"speaker": "alex"}},
                ],
                "entity": "AcmeCorp",
                "talk_ratio_pct": 60.0,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "hero_summary" in data
        assert "key_stats" in data
        assert "draft_email" in data
        assert "what_maestro_learned" in data

    def test_list_playbooks_endpoint(self, client, auth_headers):
        response = client.get("/api/copilot/playbooks", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "playbooks" in data
        assert len(data["playbooks"]) >= 3  # defaults seeded

    def test_get_playbook_endpoint(self, client, auth_headers):
        response = client.get("/api/copilot/playbooks/negotiation", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["playbook_id"] == "negotiation"
        assert "talk_tracks" in data

    def test_get_playbook_404(self, client, auth_headers):
        response = client.get("/api/copilot/playbooks/nonexistent", headers=auth_headers)
        assert response.status_code == 404

    def test_upsert_playbook_endpoint(self, client, auth_headers):
        response = client.post(
            "/api/copilot/playbooks",
            headers=auth_headers,
            json={
                "id": "custom-test",
                "name": "Test Playbook",
                "triggers": ["test"],
                "talk_tracks": [{"text": "test track", "rationale": "test"}],
                "objection_responses": {"concern": "response"},
            },
        )
        assert response.status_code == 200
        assert response.json()["id"] == "custom-test"

    def test_match_playbook_endpoint(self, client, auth_headers):
        response = client.post(
            "/api/copilot/playbooks/match",
            headers=auth_headers,
            json={"transcript_text": "prospect wants a discount on pricing"},
        )
        assert response.status_code == 200
        match = response.json()["match"]
        assert match is not None
        assert match["playbook_id"] == "negotiation"

    def test_playbook_outcome_endpoint(self, client, auth_headers):
        response = client.post(
            "/api/copilot/playbooks/outcome",
            headers=auth_headers,
            json={
                "playbook_id": "negotiation",
                "talk_track_idx": 0,
                "outcome": "positive",
            },
        )
        assert response.status_code == 200
        assert response.json()["recorded"] is True

    def test_delete_playbook_endpoint(self, client, auth_headers):
        # First create
        client.post(
            "/api/copilot/playbooks",
            headers=auth_headers,
            json={"id": "to-delete", "name": "ToDelete", "triggers": ["x"], "talk_tracks": [], "objection_responses": {}},
        )
        # Then delete
        response = client.delete("/api/copilot/playbooks/to-delete", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["deleted"] is True

    def test_shadow_start_endpoint(self, client, auth_headers):
        response = client.post(
            "/api/copilot/shadow/start",
            headers=auth_headers,
            json={"rep_email": "rep@acme.com", "meeting_title": "Q3 Review", "entity": "AcmeCorp"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "active"
        session_id = data["session_id"]

        # End it
        end_resp = client.post(f"/api/copilot/shadow/{session_id}/end", headers=auth_headers)
        assert end_resp.status_code == 200
        assert end_resp.json()["status"] == "ended"

    def test_shadow_notes_endpoint(self, client, auth_headers):
        # Start a session
        start = client.post(
            "/api/copilot/shadow/start",
            headers=auth_headers,
            json={"rep_email": "rep@acme.com"},
        )
        session_id = start.json()["session_id"]

        # Add a note
        note_resp = client.post(
            f"/api/copilot/shadow/{session_id}/notes",
            headers=auth_headers,
            json={"note_text": "slow down", "note_type": "coaching"},
        )
        assert note_resp.status_code == 200
        assert note_resp.json()["note_text"] == "slow down"

        # List notes
        list_resp = client.get(f"/api/copilot/shadow/{session_id}/notes", headers=auth_headers)
        assert list_resp.status_code == 200
        assert len(list_resp.json()["notes"]) == 1

    def test_shadow_feedback_endpoint(self, client, auth_headers):
        start = client.post(
            "/api/copilot/shadow/start",
            headers=auth_headers,
            json={"rep_email": "rep@acme.com"},
        )
        session_id = start.json()["session_id"]

        feedback_resp = client.post(
            f"/api/copilot/shadow/{session_id}/feedback",
            headers=auth_headers,
            json={"overall_rating": 4, "strengths": "good", "improvements": "x", "next_steps": "y"},
        )
        assert feedback_resp.status_code == 200
        assert feedback_resp.json()["overall_rating"] == 4

    def test_shadow_get_session_endpoint(self, client, auth_headers):
        start = client.post(
            "/api/copilot/shadow/start",
            headers=auth_headers,
            json={"rep_email": "rep@acme.com"},
        )
        session_id = start.json()["session_id"]

        get_resp = client.get(f"/api/copilot/shadow/{session_id}", headers=auth_headers)
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert "notes" in data
        assert "feedback" in data

    def test_shadow_get_session_404(self, client, auth_headers):
        response = client.get("/api/copilot/shadow/nonexistent", headers=auth_headers)
        assert response.status_code == 404

    def test_shadow_list_sessions_endpoint(self, client, auth_headers):
        # Start a couple sessions
        client.post("/api/copilot/shadow/start", headers=auth_headers, json={"rep_email": "rep1@acme.com"})
        client.post("/api/copilot/shadow/start", headers=auth_headers, json={"rep_email": "rep2@acme.com"})

        response = client.get("/api/copilot/shadow", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["count"] >= 2

    def test_unauthenticated_rejected(self, client):
        """All new endpoints require auth."""
        response = client.get("/api/copilot/playbooks")
        assert response.status_code in (401, 403)

        response = client.post("/api/copilot/follow-up-email", json={})
        assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Regression — existing post-call endpoint still works
# ---------------------------------------------------------------------------

class TestRegression:
    """Verify the existing /api/copilot/post-call endpoint still works."""

    def test_existing_post_call_still_works(self, client, auth_headers):
        response = client.post(
            "/api/copilot/post-call",
            headers=auth_headers,
            json={
                "situation_id": "",
                "transcript_chunks": [],
                "commitments": [],
                "entity": "AcmeCorp",
            },
        )
        # Should return 200 (may return an error dict if shell isn't fully wired,
        # but the endpoint itself must respond)
        assert response.status_code == 200
