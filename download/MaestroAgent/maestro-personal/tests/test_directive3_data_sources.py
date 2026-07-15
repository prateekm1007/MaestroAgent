"""
Tests for Directive 3: Data Sources — Slack + voice transcript + temporal queries.
"""

import sys
import os
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
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-d3"
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
    response = client.post("/api/auth/login", json={"password": os.environ.get("MAESTRO_PERSONAL_TOKEN", "test")})
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


class TestSlackAdapter:
    """Slack message parsing + commitment extraction."""

    def test_parse_commitment_from_slack(self):
        """Slack message with 'I will' must be classified as commitment."""
        from maestro_personal_shell.signal_adapters.slack import parse_slack_message
        msg = {
            "text": "I will send the deck by Friday",
            "user": "U123",
            "ts": "1720612800.123456",
            "channel": "project-alpha",
        }
        signal = parse_slack_message(msg)
        assert signal is not None
        assert signal["signal_type"] == "commitment_made"
        assert signal["entity"] != ""
        assert "slack" in signal["metadata"]["source"]

    def test_parse_request_from_slack(self):
        """Slack message with 'Can you' must be classified as request."""
        from maestro_personal_shell.signal_adapters.slack import parse_slack_message
        msg = {
            "text": "Can you get me the numbers before the meeting?",
            "user": "U456",
            "ts": "1720612800.123456",
            "channel": "general",
        }
        signal = parse_slack_message(msg)
        assert signal is not None
        assert signal["signal_type"] == "request"

    def test_strips_slack_formatting(self):
        """Slack formatting (*bold*, @mentions, #channels) must be stripped."""
        from maestro_personal_shell.signal_adapters.slack import _strip_slack_formatting
        text = "*Bold* _italic_ ~strike~ `code` <@U123> <#C456|general>"
        result = _strip_slack_formatting(text)
        assert "*" not in result
        assert "_" not in result
        assert "~" not in result
        assert "<@" not in result
        assert "<#" not in result

    def test_skips_bot_messages(self):
        """Bot messages must be skipped."""
        from maestro_personal_shell.signal_adapters.slack import parse_slack_message
        msg = {
            "text": "I will do something",
            "subtype": "bot_message",
            "ts": "1720612800.123456",
            "channel": "general",
        }
        signal = parse_slack_message(msg)
        assert signal is None

    def test_slack_ingest_endpoint(self, client, auth_headers):
        """POST /api/ingest/slack must ingest messages and return count."""
        response = client.post(
            "/api/ingest/slack",
            json={
                "messages": [
                    {
                        "text": "I will send the proposal by Friday",
                        "user": "U123",
                        "ts": "1720612800.123456",
                        "channel": "deals",
                    },
                    {
                        "text": "ok",
                        "user": "U456",
                        "ts": "1720612801.123456",
                        "channel": "deals",
                    },
                ]
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ingested"] >= 1, "Must ingest at least 1 signal"


class TestVoiceTranscriptExtractor:
    """Voice transcript implicit commitment extraction."""

    def test_extract_implicit_commitment(self):
        """'Let me take that' must be extracted as implicit commitment."""
        from maestro_personal_shell.voice_commitment_extractor import extract_commitments_from_transcript
        chunks = [
            {"speaker": "user", "text": "Let me take that action item", "timestamp": "2026-07-10T10:00:00Z"},
        ]
        commitments = extract_commitments_from_transcript(chunks, "AcmeCorp")
        assert len(commitments) > 0
        assert commitments[0]["metadata"]["commitment_type"] in ("implicit", "explicit")
        assert commitments[0]["metadata"]["is_commitment"] is True

    def test_extract_with_deadline(self):
        """Deadline must be extracted from voice commitment."""
        from maestro_personal_shell.voice_commitment_extractor import extract_commitments_from_transcript
        chunks = [
            {"speaker": "user", "text": "I will send the proposal by Friday", "timestamp": "2026-07-10T10:00:00Z"},
        ]
        commitments = extract_commitments_from_transcript(chunks, "Client")
        assert len(commitments) > 0
        assert commitments[0]["metadata"].get("deadline_text") == "by friday"

    def test_no_commitment_in_noise(self):
        """Non-commitment transcript chunks must not produce commitments."""
        from maestro_personal_shell.voice_commitment_extractor import extract_commitments_from_transcript
        chunks = [
            {"speaker": "user", "text": "The weather is nice today", "timestamp": "2026-07-10T10:00:00Z"},
        ]
        commitments = extract_commitments_from_transcript(chunks, "Someone")
        assert len(commitments) == 0

    def test_process_meeting_transcript(self):
        """Full meeting processing must return commitments + completions + requests."""
        from maestro_personal_shell.voice_commitment_extractor import process_meeting_transcript
        transcript = [
            {"speaker": "user", "text": "I will send the proposal by Friday", "timestamp": "2026-07-10T10:00:00Z"},
            {"speaker": "client", "text": "Can you also include the pricing?", "timestamp": "2026-07-10T10:01:00Z"},
            {"speaker": "user", "text": "The report has been sent", "timestamp": "2026-07-10T10:02:00Z"},
        ]
        result = process_meeting_transcript(transcript, "AcmeCorp")
        assert len(result["commitments"]) >= 1
        assert len(result["requests"]) >= 1
        assert len(result["completion_signals"]) >= 1
        assert "summary" in result

    def test_transcript_ingest_endpoint(self, client, auth_headers):
        """POST /api/ingest/transcript must extract and store commitments."""
        response = client.post(
            "/api/ingest/transcript",
            json={
                "transcript": [
                    {"speaker": "user", "text": "Let me take that action item", "timestamp": "2026-07-10T10:00:00Z"},
                    {"speaker": "client", "text": "Great, thanks", "timestamp": "2026-07-10T10:01:00Z"},
                ],
                "meeting_entity": "AcmeCorp",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["commitments_extracted"] >= 1


class TestTemporalQueryParser:
    """Temporal query parsing for historical depth."""

    def test_last_quarter(self):
        """'last quarter' must produce a date range."""
        from maestro_personal_shell.temporal_query import parse_temporal_query
        result = parse_temporal_query("What did I commit to last quarter?")
        assert result["has_temporal_ref"] is True
        assert result["from_date"] is not None
        assert result["to_date"] is not None
        assert "quarter" in result["time_range_description"]

    def test_last_30_days(self):
        """'last 30 days' must produce a date range."""
        from maestro_personal_shell.temporal_query import parse_temporal_query
        result = parse_temporal_query("What changed in the last 30 days?")
        assert result["has_temporal_ref"] is True
        assert "30" in result["time_range_description"]

    def test_named_month(self):
        """'in July' must produce a date range for July."""
        from maestro_personal_shell.temporal_query import parse_temporal_query
        result = parse_temporal_query("What did AcmeCorp promise in July?")
        assert result["has_temporal_ref"] is True
        assert "july" in result["time_range_description"]

    def test_no_temporal_ref(self):
        """Query without temporal reference must return has_temporal_ref=False."""
        from maestro_personal_shell.temporal_query import parse_temporal_query
        result = parse_temporal_query("What did AcmeCorp commit to?")
        assert result["has_temporal_ref"] is False

    def test_filter_signals_by_date_range(self):
        """Signals must be filtered by date range."""
        from maestro_personal_shell.temporal_query import filter_signals_by_date_range
        signals = [
            {"text": "old", "timestamp": "2026-01-15T10:00:00Z"},
            {"text": "new", "timestamp": "2026-07-10T10:00:00Z"},
        ]
        filtered = filter_signals_by_date_range(
            signals,
            from_date="2026-06-01T00:00:00Z",
            to_date="2026-07-31T23:59:59Z",
        )
        assert len(filtered) == 1
        assert filtered[0]["text"] == "new"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
