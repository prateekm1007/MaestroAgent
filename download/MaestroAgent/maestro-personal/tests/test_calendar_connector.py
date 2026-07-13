"""
Tests for the Google Calendar OAuth2 connector (Phase E).

Read-only connector — same OAuth pattern as Gmail, but no send/draft logic.
Verifies:
  1. CalendarOAuthClient: authorization URL, token exchange, refresh
  2. CalendarAPIClient: events.list (mocked HTTP)
  3. CalendarIngester: event → signal extraction (attendees, time, summary)
  4. ConnectorStore integration: _fetch_messages uses real Calendar when configured
  5. OAuth callback endpoint
  6. Fallback: returns mock data when OAuth NOT configured
"""

import sys
import os
import tempfile
import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def calendar_env():
    """Set fake Calendar OAuth credentials in env."""
    old = os.environ.copy()
    os.environ["MAESTRO_CALENDAR_CLIENT_ID"] = "test-cal-client-id"
    os.environ["MAESTRO_CALENDAR_CLIENT_SECRET"] = "test-cal-client-secret"
    os.environ["MAESTRO_CALENDAR_REDIRECT_URI"] = "http://localhost:8766/api/connectors/calendar/oauth/callback"
    yield
    os.environ.clear()
    os.environ.update(old)


@pytest.fixture
def no_calendar_env():
    """Ensure Calendar OAuth is NOT configured (demo mode)."""
    old = os.environ.copy()
    for k in ("MAESTRO_CALENDAR_CLIENT_ID", "MAESTRO_CALENDAR_CLIENT_SECRET", "MAESTRO_CALENDAR_REDIRECT_URI"):
        os.environ.pop(k, None)
    yield
    os.environ.clear()
    os.environ.update(old)


@pytest.fixture
def isolated_api():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-cal"
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


# ---------------------------------------------------------------------------
# 1. CalendarOAuthClient
# ---------------------------------------------------------------------------

class TestCalendarOAuthClient:
    """OAuth2 authorization URL + token exchange + refresh."""

    def test_authorization_url_contains_required_params(self, calendar_env):
        from maestro_personal_shell.calendar_connector import CalendarOAuthClient
        client = CalendarOAuthClient()
        url = client.get_authorization_url(state="user=test@example.com")
        assert "client_id=test-cal-client-id" in url
        assert "redirect_uri=" in url
        assert "response_type=code" in url
        assert "access_type=offline" in url
        assert "calendar.readonly" in url
        assert "state=" in url

    def test_authorization_url_raises_when_not_configured(self, no_calendar_env):
        from maestro_personal_shell.calendar_connector import CalendarOAuthClient
        client = CalendarOAuthClient()
        with pytest.raises(ValueError, match="not configured"):
            client.get_authorization_url()

    @patch("urllib.request.urlopen")
    def test_exchange_code_returns_tokens(self, mock_urlopen, calendar_env):
        from maestro_personal_shell.calendar_connector import CalendarOAuthClient
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "access_token": "ya29.test-access",
            "refresh_token": "1//test-refresh",
            "expires_in": 3600,
            "token_type": "Bearer",
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = CalendarOAuthClient()
        tokens = client.exchange_code_for_tokens("test-code")
        assert tokens["access_token"] == "ya29.test-access"
        assert tokens["refresh_token"] == "1//test-refresh"
        assert "expires_at" in tokens

    def test_get_valid_access_token_returns_existing_if_not_expired(self, calendar_env):
        from maestro_personal_shell.calendar_connector import CalendarOAuthClient
        client = CalendarOAuthClient()
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        stored = json.dumps({
            "access_token": "ya29.valid",
            "refresh_token": "1//refresh",
            "expires_at": future,
        })
        token, updated = client.get_valid_access_token(stored)
        assert token == "ya29.valid"
        assert updated == stored

    def test_get_valid_access_token_refreshes_when_expired(self, calendar_env):
        from maestro_personal_shell.calendar_connector import CalendarOAuthClient
        client = CalendarOAuthClient()
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        stored = json.dumps({
            "access_token": "ya29.expired",
            "refresh_token": "1//refresh",
            "expires_at": past,
        })
        with patch.object(client, "refresh_access_token", return_value={
            "access_token": "ya29.refreshed",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        }):
            token, updated = client.get_valid_access_token(stored)
        assert token == "ya29.refreshed"
        updated_data = json.loads(updated)
        assert updated_data["access_token"] == "ya29.refreshed"


# ---------------------------------------------------------------------------
# 2. CalendarAPIClient
# ---------------------------------------------------------------------------

class TestCalendarAPIClient:
    """Calendar REST API calls (mocked HTTP)."""

    @patch("urllib.request.urlopen")
    def test_list_upcoming_events(self, mock_urlopen):
        from maestro_personal_shell.calendar_connector import CalendarAPIClient
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "items": [
                {
                    "id": "evt1",
                    "summary": "Meeting with Maria",
                    "start": {"dateTime": "2026-07-15T14:00:00Z"},
                    "attendees": [{"email": "maria@example.com"}],
                },
                {
                    "id": "evt2",
                    "summary": "Team sync",
                    "start": {"dateTime": "2026-07-16T10:00:00Z"},
                    "attendees": [],
                },
            ],
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = CalendarAPIClient("ya29.token")
        events = client.list_upcoming_events(max_results=10, days_ahead=7)
        assert len(events) == 2
        assert events[0]["summary"] == "Meeting with Maria"

    @patch("urllib.request.urlopen")
    def test_list_upcoming_events_handles_empty(self, mock_urlopen):
        """P28: edge case — no upcoming events."""
        from maestro_personal_shell.calendar_connector import CalendarAPIClient
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = CalendarAPIClient("ya29.token")
        events = client.list_upcoming_events()
        assert events == []


# ---------------------------------------------------------------------------
# 3. CalendarIngester — event → signal extraction
# ---------------------------------------------------------------------------

class TestCalendarIngester:
    """Extract signals from calendar events."""

    def test_extract_signals_from_event_with_attendees(self):
        from maestro_personal_shell.calendar_connector import CalendarIngester
        ingester = CalendarIngester("token")
        event = {
            "summary": "Pricing Review",
            "start": {"dateTime": "2026-07-15T14:00:00Z"},
            "attendees": [
                {"email": "maria.garcia@example.com"},
                {"email": "alex.chen@example.com"},
            ],
        }
        signals = ingester._extract_signals_from_event(event)
        assert len(signals) == 2  # one per attendee
        assert all(s["source"] == "calendar:upcoming" for s in signals)
        assert all(s["signal_type"] == "reported_statement" for s in signals)
        assert any("Maria Garcia" in s["entity"] for s in signals)
        assert any("Alex Chen" in s["entity"] for s in signals)
        assert all("Pricing Review" in s["text"] for s in signals)

    def test_extract_signals_from_event_no_attendees(self):
        """P28: edge case — event with no attendees."""
        from maestro_personal_shell.calendar_connector import CalendarIngester
        ingester = CalendarIngester("token")
        event = {
            "summary": "Focus block",
            "start": {"dateTime": "2026-07-15T09:00:00Z"},
            "attendees": [],
        }
        signals = ingester._extract_signals_from_event(event)
        assert len(signals) == 1
        assert "Focus block" in signals[0]["text"]

    def test_extract_signals_skips_self_and_resources(self):
        """P28: edge case — skip self + resource attendees (rooms)."""
        from maestro_personal_shell.calendar_connector import CalendarIngester
        ingester = CalendarIngester("token")
        event = {
            "summary": "Meeting",
            "start": {"dateTime": "2026-07-15T14:00:00Z"},
            "attendees": [
                {"email": "me@example.com", "self": True},
                {"email": "room-1@example.com", "resource": True},
                {"email": "maria@example.com"},
            ],
        }
        signals = ingester._extract_signals_from_event(event)
        assert len(signals) == 1  # only Maria
        assert "Maria" in signals[0]["entity"]

    def test_extract_entity_from_email(self):
        from maestro_personal_shell.calendar_connector import CalendarIngester
        ingester = CalendarIngester("token")
        assert ingester._extract_entity_from_email("maria.garcia@example.com") == "Maria Garcia"
        assert ingester._extract_entity_from_email("alex@example.com") == "Alex"
        assert ingester._extract_entity_from_email("john_doe@example.com") == "John Doe"
        assert ingester._extract_entity_from_email("") == ""

    def test_parse_calendar_time(self):
        from maestro_personal_shell.calendar_connector import CalendarIngester
        ingester = CalendarIngester("token")
        # With Z suffix
        result = ingester._parse_calendar_time("2026-07-15T14:00:00Z")
        assert "2026-07-15" in result
        # Empty → now
        result2 = ingester._parse_calendar_time("")
        assert "T" in result2

    def test_format_time(self):
        from maestro_personal_shell.calendar_connector import CalendarIngester
        ingester = CalendarIngester("token")
        formatted = ingester._format_time("2026-07-15T14:00:00Z")
        assert "Jul" in formatted or "15" in formatted

    @patch("urllib.request.urlopen")
    def test_ingest_upcoming_returns_signals(self, mock_urlopen, calendar_env):
        """Integration: ingest_upcoming pulls events and creates signals."""
        from maestro_personal_shell.calendar_connector import CalendarIngester
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "items": [
                {
                    "summary": "Meeting with Maria",
                    "start": {"dateTime": "2026-07-15T14:00:00Z"},
                    "attendees": [{"email": "maria@example.com"}],
                },
            ],
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        ingester = CalendarIngester("ya29.token")
        result = ingester.ingest_upcoming(max_events=5, days_ahead=7)
        assert result["events_scanned"] == 1
        assert result["signals_created"] >= 1
        assert len(result["signals"]) >= 1
        assert result["signals"][0]["source"] == "calendar:upcoming"


# ---------------------------------------------------------------------------
# 4. ConnectorStore integration — _fetch_messages uses real Calendar
# ---------------------------------------------------------------------------

class TestCalendarIngestionIntegration:
    """Verify _fetch_messages calls real Calendar API when configured."""

    def test_falls_back_to_mock_when_oauth_not_configured(self, no_calendar_env, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        store.connect("user@test.com", "calendar", json.dumps({"access_token": "x"}))
        messages = store._fetch_messages("user@test.com", "calendar")
        assert len(messages) > 0
        assert any("calendar" in m.get("source", "") for m in messages)

    def test_calls_real_calendar_when_configured(self, calendar_env, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        token_json = json.dumps({
            "access_token": "ya29.valid",
            "refresh_token": "1//refresh",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        })
        store.connect("user@test.com", "calendar", token_json)

        mock_signals = [
            {"entity": "Maria", "text": "Meeting with Maria at 2pm", "signal_type": "reported_statement", "timestamp": "2026-07-15T14:00:00Z", "source": "calendar:upcoming"},
        ]
        with patch(
            "maestro_personal_shell.calendar_connector.fetch_real_calendar_events",
            return_value=(mock_signals, token_json),
        ):
            messages = store._fetch_messages("user@test.com", "calendar")
        assert messages == mock_signals
        assert messages[0]["entity"] == "Maria"

    def test_persists_refreshed_token(self, calendar_env, tmp_path):
        """P21: when Calendar API refreshes the token, persist it."""
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        old_token = json.dumps({
            "access_token": "ya29.old",
            "refresh_token": "1//refresh",
            "expires_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        })
        store.connect("user@test.com", "calendar", old_token)

        new_token = json.dumps({
            "access_token": "ya29.new",
            "refresh_token": "1//refresh",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        })
        with patch(
            "maestro_personal_shell.calendar_connector.fetch_real_calendar_events",
            return_value=([], new_token),
        ):
            store._fetch_messages("user@test.com", "calendar")

        stored = store.get_stored_token("user@test.com", "calendar")
        assert json.loads(stored)["access_token"] == "ya29.new"


# ---------------------------------------------------------------------------
# 5. OAuth callback endpoint
# ---------------------------------------------------------------------------

class TestCalendarOAuthCallback:
    """OAuth callback endpoint + connect endpoint with OAuth flow."""

    def test_connect_returns_auth_url_when_oauth_configured(self, client, auth_headers, calendar_env):
        response = client.post(
            "/api/connectors/calendar/connect",
            headers=auth_headers,
            json={"provider": "calendar", "oauth_token": ""},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["oauth_required"] is True
        assert "accounts.google.com" in data["authorization_url"]

    def test_connect_stores_token_directly_when_oauth_token_provided(self, client, auth_headers, no_calendar_env):
        response = client.post(
            "/api/connectors/calendar/connect",
            headers=auth_headers,
            json={"provider": "calendar", "oauth_token": "fake-demo-token"},
        )
        assert response.status_code == 200
        assert response.json()["connected"] is True

    def test_oauth_callback_exchanges_code(self, client, calendar_env):
        with patch(
            "maestro_personal_shell.calendar_connector.CalendarOAuthClient.exchange_code_for_tokens",
            return_value={
                "access_token": "ya29.access",
                "refresh_token": "1//refresh",
                "expires_in": 3600,
                "expires_at": "2026-12-31T23:59:59+00:00",
            },
        ):
            response = client.get(
                "/api/connectors/calendar/oauth/callback?code=test-code&state=user=test@example.com",
            )
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        assert data["provider"] == "calendar"
        assert data["user_email"] == "test@example.com"
        assert "pre-call" in data["message"].lower()

    def test_oauth_callback_returns_error_on_oauth_error(self, client, calendar_env):
        response = client.get(
            "/api/connectors/calendar/oauth/callback?error=access_denied",
        )
        assert response.status_code == 400
        assert "access_denied" in response.json()["detail"]

    def test_oauth_callback_returns_400_when_not_configured(self, client, no_calendar_env):
        response = client.get(
            "/api/connectors/calendar/oauth/callback?code=test-code&state=user=test@example.com",
        )
        assert response.status_code == 400
        assert "not configured" in response.json()["detail"]


# ---------------------------------------------------------------------------
# 6. is_calendar_configured helper
# ---------------------------------------------------------------------------

class TestCalendarConfiguration:
    """Configuration detection."""

    def test_is_calendar_configured_true_when_env_set(self, calendar_env):
        from maestro_personal_shell.calendar_connector import is_calendar_configured
        assert is_calendar_configured() is True

    def test_is_calendar_configured_false_when_env_missing(self, no_calendar_env):
        from maestro_personal_shell.calendar_connector import is_calendar_configured
        assert is_calendar_configured() is False
