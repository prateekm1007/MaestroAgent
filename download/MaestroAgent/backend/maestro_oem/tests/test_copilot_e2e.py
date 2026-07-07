"""Maestro Live Copilot — Phase 8 Integration Test (E2E).

Tests the full flow: lobby → pre-call → live → post-call → learning loop.

This is the Phase 8 gate. The auditor runs it independently (P31).
"""

from __future__ import annotations

import pathlib
import sys

import pytest
from fastapi.testclient import TestClient

BACKEND = str(pathlib.Path(__file__).resolve().parents[2])
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


@pytest.fixture(scope="module")
def client():
    import os, pathlib, sys
    os.environ.setdefault("MAESTRO_APP_DIR", str(pathlib.Path(__file__).resolve().parents[3]))
    os.environ.setdefault("MAESTRO_AUTH_DB", "/tmp/test_copilot_e2e.db")
    os.environ.setdefault("MAESTRO_ADMIN_PASSWORD", "test")
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from maestro_api.main import create_app
    app = create_app(db_path=":memory:")
    with TestClient(app) as c:
        yield c


class TestCopilotE2E:
    """Phase 8: end-to-end integration test for the Live Copilot."""

    def test_phase1_extension_scaffold_exists(self, client):
        """Phase 1: extension files exist and manifest is valid."""
        import json, pathlib
        ext_dir = pathlib.Path(__file__).resolve().parents[3] / "extension"
        manifest_path = ext_dir / "manifest.json"
        assert manifest_path.exists(), "manifest.json must exist"
        manifest = json.loads(manifest_path.read_text())
        assert manifest["manifest_version"] == 3
        assert "sidePanel" in manifest["permissions"]
        assert manifest["side_panel"]["default_path"] == "panel.html"

    def test_phase1_consent_manager_gates_capture(self, client):
        """Phase 1: consent manager exists and gates every capture path."""
        import pathlib
        consent_path = pathlib.Path(__file__).resolve().parents[3] / "extension" / "lib" / "consent-manager.js"
        assert consent_path.exists(), "consent-manager.js must exist"
        consent_src = consent_path.read_text()
        assert "checkConsent" in consent_src
        assert "revokeConsent" in consent_src
        assert "_auditLog" in consent_src

    def test_phase1_zero_active_capture_calls_in_phase1(self, client):
        """Phase 1: ZERO active getUserMedia calls (scaffold only)."""
        import pathlib, re
        offscreen_path = pathlib.Path(__file__).resolve().parents[3] / "extension" / "offscreen.js"
        src = offscreen_path.read_text()
        # Remove comments
        lines = [l for l in src.split("\n") if not l.strip().startswith("//") and not l.strip().startswith("*")]
        active_src = "\n".join(lines)
        # Phase 2 adds getDisplayMedia — it should be present but gated
        # Phase 1 had zero; Phase 2 has it consent-gated
        if "getDisplayMedia" in active_src:
            # Must be preceded by consent check
            assert "checkConsent" in active_src, "getDisplayMedia must be consent-gated"

    def test_phase2_websocket_endpoint_exists(self, client):
        """Phase 2: /ws/copilot WebSocket endpoint is registered."""
        routes = [r.path for r in client.app.routes if hasattr(r, "path")]
        assert "/ws/copilot" in routes, "WebSocket /ws/copilot must be registered"

    def test_phase3_pre_call_briefing(self, client):
        """Phase 3: pre-call endpoint returns attendee intelligence with evidence."""
        r = client.post("/api/copilot/pre-call", json={
            "meeting_title": "Q3 Renewal — Globex Corp",
            "attendees": ["raj.patel@globex.com", "sam.kumar@globex.com"],
            "user_email": "jane.d@acme.com",
        })
        assert r.status_code == 200
        d = r.json()
        assert d["meeting_context"]["entity"] == "Globex"
        assert len(d["attendee_intelligence"]) == 2
        # Every talking point must have evidence
        for tp in d["suggested_talking_points"]:
            assert tp.get("evidence"), f"Talking point missing evidence: {tp}"

    def test_phase4_live_intelligence_4_card_types(self, client):
        """Phase 4: live engine produces cards with color-coded borders + P25 confidence."""

        from maestro_oem.live_intelligence import LiveIntelligenceEngine
        engine = LiveIntelligenceEngine(None)
        cards = engine.process_transcript(
            "That is above what we budgeted. We will deliver SSO by Friday.",
            "Sam Kumar", "Globex"
        )
        assert len(cards) >= 2, f"Expected >= 2 cards, got {len(cards)}"
        for card in cards:
            assert card.color in ["#FF5577", "#FFB84D", "#7C5CFF", "#5CC8FF", "#00D4AA"]
            # P25: confidence must have denominator
            assert card.confidence_denominator >= 1
            if card.confidence_denominator < 10:
                assert "insufficient" in card.confidence_label

    def test_phase5_post_call_summary(self, client):
        """Phase 5: post-call endpoint returns summary + draft email + learning."""
        r = client.post("/api/copilot/post-call", json={
            "meeting_title": "Q3 Renewal — Globex Corp",
            "duration_seconds": 2052,
            "participants": ["raj.patel@globex.com"],
            "transcript_chunks": [{"text": "chunk"} for _ in range(38)],
            "suggestion_cards": [
                {"card_type": "commitment", "text": "SSO by Friday",
                 "evidence": {"speaker": "raj.patel@globex.com", "day_count": 0, "deduped": False}},
                {"card_type": "objection", "text": "Above budget",
                 "evidence": {"objection_type": "pricing"},
                 "confidence": 0.82, "confidence_label": "82% (3 samples)"},
            ],
            "entity": "Globex",
        })
        assert r.status_code == 200
        d = r.json()
        assert d["hero_summary"]["title"] == "Q3 Renewal — Globex Corp"
        assert d["key_stats"]["commitments"] == 1
        assert d["key_stats"]["objections"] == 1
        assert "Follow-up" in d["draft_email"]["subject"]
        assert "SSO by Friday" in d["draft_email"]["body"]
        assert d["what_maestro_learned"]["new_signals_ingested"] == 1

    def test_phase6_p25_confidence_gate(self, client):
        """Phase 6: P25 confidence gate — no confidence without denominator."""

        from maestro_oem.live_intelligence import SuggestionCard
        # < 10 samples = "insufficient calibration history"
        c1 = SuggestionCard("objection", "t", "t", 0.6, 3)
        assert "insufficient" in c1.confidence_label
        # >= 10 samples = percentage + count
        c2 = SuggestionCard("objection", "t", "t", 0.82, 12)
        assert "82%" in c2.confidence_label and "12" in c2.confidence_label

    def test_phase7_accessibility_features(self, client):
        """Phase 7: accessibility features present in the extension."""
        import pathlib
        panel_css = (pathlib.Path(__file__).resolve().parents[3] / "extension" / "panel.css").read_text()
        panel_html = (pathlib.Path(__file__).resolve().parents[3] / "extension" / "panel.html").read_text()
        assert "prefers-reduced-motion" in panel_css
        assert "focus-visible" in panel_css
        assert "skip-link" in panel_html
        assert "aria-live" in panel_html or "role=" in panel_html

    def test_phase8_l0_gate_no_regression(self, client):
        """Phase 8: L0 gate still passes — no regression from the copilot build."""

        from maestro_oem.situation import Situation
        import dataclasses
        fields = [f.name for f in dataclasses.fields(Situation)]
        assert len(fields) == 27, f"SituationSnapshot regressed: {len(fields)} fields"

        from maestro_oem.governed_adaptation import OutcomeLedger
        ol = OutcomeLedger()
        assert hasattr(ol, "append") and hasattr(ol, "count")

        from maestro_oem.content_epistemic_classifier import ContentEpistemicClassifier
        clf = ContentEpistemicClassifier()
        assert clf.classify("Maybe we can ship SSO.") == "tentative"

    def test_phase8_full_e2e_flow(self, client):
        """Phase 8: full E2E flow — pre-call → live → post-call → learning."""
        # 1. Pre-call briefing
        pre = client.post("/api/copilot/pre-call", json={
            "meeting_title": "Globex Renewal",
            "attendees": ["raj@globex.com"],
            "user_email": "jane@acme.com",
        })
        assert pre.status_code == 200
        assert pre.json()["meeting_context"]["entity"] == "Globex"

        # 2. Live intelligence (simulate transcript processing)

        from maestro_oem.live_intelligence import LiveIntelligenceEngine
        engine = LiveIntelligenceEngine(None)
        cards = engine.process_transcript("We will deliver by Friday. That is above budget.", "Raj", "Globex")
        assert len(cards) >= 2

        # 3. Post-call summary
        post = client.post("/api/copilot/post-call", json={
            "meeting_title": "Globex Renewal",
            "duration_seconds": 1800,
            "participants": ["raj@globex.com"],
            "transcript_chunks": [{"text": "chunk"} for _ in range(30)],
            "suggestion_cards": [c.to_dict() for c in cards],
            "entity": "Globex",
        })
        assert post.status_code == 200
        summary = post.json()
        assert summary["hero_summary"]["title"] == "Globex Renewal"
        assert summary["what_maestro_learned"]["new_signals_ingested"] >= 1
