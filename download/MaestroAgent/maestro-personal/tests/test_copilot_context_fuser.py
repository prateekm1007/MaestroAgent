"""
Tests for the Copilot Context Fuser — Directive 1.

Verifies multi-signal fusion: transcript + situations + FTS5 + agents +
contradiction detection + negotiation anchors + materiality gate.
"""

import sys
import os
import asyncio
import tempfile
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


@pytest.fixture
def isolated_api():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-fuser"
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
    del os.environ["MAESTRO_PERSONAL_DB"]
    del os.environ["MAESTRO_PERSONAL_TOKEN"]


@pytest.fixture
def client(isolated_api):
    return TestClient(isolated_api.app)


@pytest.fixture
def auth_headers(client):
    response = client.post("/api/auth/login", json={"password": "any"})
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


class TestCopilotContextFuser:
    """Directive 1: Multi-signal fusion for real-time copilot."""

    def test_talk_ratio_computed(self):
        """Talk ratio must be computed from transcript chunks."""
        from maestro_personal_shell.copilot_context_fuser import CopilotContextFuser
        from maestro_personal_shell.shell import PersonalShell

        fuser = CopilotContextFuser(shell=PersonalShell())
        chunks = [
            {"speaker": "user", "text": "I will send the proposal by Friday"},
            {"speaker": "user", "text": "Let me also check on the timeline"},
            {"speaker": "client", "text": "OK"},
        ]
        ratio = fuser._compute_talk_ratio(chunks)
        assert ratio["user"] > 0.5, "User should have higher talk ratio"
        assert ratio["other"] < 0.5

    def test_contradiction_detection(self):
        """Contradictions between transcript and commitments must be detected."""
        from maestro_personal_shell.copilot_context_fuser import CopilotContextFuser
        from maestro_personal_shell.shell import PersonalShell

        fuser = CopilotContextFuser(shell=PersonalShell())
        transcript = "I haven't started the proposal yet"
        commitments = [
            {"entity": "AcmeCorp", "text": "I will send the proposal by Friday"},
        ]
        contradictions = fuser._detect_contradictions(transcript, commitments)
        assert len(contradictions) > 0, "Should detect contradiction"
        assert contradictions[0]["type"] == "commitment_at_risk"

    def test_negotiation_anchor_detection(self):
        """Negotiation anchors (prices, deadlines) must be detected."""
        from maestro_personal_shell.copilot_context_fuser import CopilotContextFuser
        from maestro_personal_shell.shell import PersonalShell

        fuser = CopilotContextFuser(shell=PersonalShell())
        transcript = "Our best offer is $50,000 and we need it by Friday"
        anchors = fuser._detect_anchors(transcript)
        assert len(anchors) >= 2, "Should detect price and deadline anchors"

    def test_materiality_gate_speaks_for_high_severity(self):
        """Materiality gate must speak for high-severity contradictions."""
        from maestro_personal_shell.copilot_context_fuser import CopilotContextFuser
        from maestro_personal_shell.shell import PersonalShell

        fuser = CopilotContextFuser(shell=PersonalShell())
        contradictions = [{"severity": "high", "evidence": "Haven't started proposal"}]
        should_speak, reason = fuser._evaluate_materiality(contradictions, [], [])
        assert should_speak is True
        assert "contradiction" in reason.lower()

    def test_materiality_gate_silent_when_nothing_material(self):
        """Materiality gate must stay silent when nothing material."""
        from maestro_personal_shell.copilot_context_fuser import CopilotContextFuser
        from maestro_personal_shell.shell import PersonalShell

        fuser = CopilotContextFuser(shell=PersonalShell())
        should_speak, reason = fuser._evaluate_materiality([], [], [])
        assert should_speak is False
        assert "silent" in reason.lower()

    def test_full_fusion_with_empty_transcript(self):
        """Fusion with empty transcript must return valid structure."""
        from maestro_personal_shell.copilot_context_fuser import CopilotContextFuser
        from maestro_personal_shell.shell import PersonalShell

        fuser = CopilotContextFuser(shell=PersonalShell())
        result = asyncio.run(fuser.fuse([], ""))
        assert "transcript_summary" in result
        assert "talk_ratio" in result
        assert "should_whisper" in result
        assert result["should_whisper"] is False  # nothing to say with empty transcript

    def test_suggestions_generated_for_stale_commitments(self):
        """Stale commitments must generate suggestions."""
        from maestro_personal_shell.copilot_context_fuser import CopilotContextFuser
        from maestro_personal_shell.shell import PersonalShell

        fuser = CopilotContextFuser(shell=PersonalShell())
        stale = [{"entity": "AcmeCorp", "days_stale": 7, "text": "Send proposal"}]
        suggestions = fuser._generate_suggestions([], stale, {"user": 0.5, "other": 0.5}, [])
        assert any(s["type"] == "stale_commitment" for s in suggestions)

    def test_talk_ratio_coaching_when_user_dominates(self):
        """Talk ratio coaching must suggest listening when user dominates."""
        from maestro_personal_shell.copilot_context_fuser import CopilotContextFuser
        from maestro_personal_shell.shell import PersonalShell

        fuser = CopilotContextFuser(shell=PersonalShell())
        suggestions = fuser._generate_suggestions([], [], {"user": 0.75, "other": 0.25}, [])
        assert any(s["type"] == "talk_ratio" for s in suggestions)

    def test_agent_whispers_generated_for_contradictions(self):
        """Agent whispers must be generated for contradictions."""
        from maestro_personal_shell.copilot_context_fuser import CopilotContextFuser
        from maestro_personal_shell.shell import PersonalShell

        fuser = CopilotContextFuser(shell=PersonalShell())
        contradictions = [{"evidence": "Haven't started", "type": "commitment_at_risk"}]
        whispers = asyncio.run(fuser._generate_agent_whispers("test", [], [], contradictions))
        assert len(whispers) > 0
        assert any(w["agent"] == "customer_success" for w in whispers)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
