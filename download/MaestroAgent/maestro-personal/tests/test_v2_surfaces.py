"""
v2 tests: Gmail adapter, Calendar adapter, Whisper surface, new API endpoints.

Per CEO Option B: build all four versions. These tests verify v2 features
(Gmail/Calendar sync, Whisper) and v3 features (account deletion, data export).
"""

import sys
import os
import pathlib
import tempfile
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "backend"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import pytest


# ---------------------------------------------------------------------------
# Gmail adapter tests
# ---------------------------------------------------------------------------


class TestGmailAdapter:
    """Tests for the Gmail signal adapter."""

    def test_detect_commitment_in_email(self):
        """The adapter must detect 'I will send' patterns as commitments."""
        from maestro_personal_shell.signal_adapters.gmail import detect_commitments_in_text

        commitments = detect_commitments_in_text(
            "I will send the proposal by Friday."
        )
        assert len(commitments) >= 1
        assert "send" in commitments[0]["text"].lower()

    def test_detect_casual_commitment(self):
        """The adapter must detect 'I'll' as a commitment."""
        from maestro_personal_shell.signal_adapters.gmail import detect_commitments_in_text

        commitments = detect_commitments_in_text(
            "I'll send revised numbers too."
        )
        assert len(commitments) >= 1
        assert "send" in commitments[0]["text"].lower()

    def test_detect_follow_up(self):
        """The adapter must detect follow-up patterns."""
        from maestro_personal_shell.signal_adapters.gmail import detect_follow_ups_in_text

        assert detect_follow_ups_in_text("Following up on the proposal — did you get a chance to review?")
        assert detect_follow_ups_in_text("Just checking in on this.")
        assert not detect_follow_ups_in_text("The proposal is ready.")

    def test_detect_meeting_change(self):
        """The adapter must detect meeting reschedule patterns."""
        from maestro_personal_shell.signal_adapters.gmail import detect_meeting_changes_in_text

        changes = detect_meeting_changes_in_text(
            "The meeting has been moved to Tuesday at 2pm."
        )
        assert len(changes) >= 1

    def test_extract_signals_from_message(self):
        """Extract signals from a full Gmail message dict."""
        from maestro_personal_shell.signal_adapters.gmail import extract_signals_from_message

        message = {
            "message_id": "msg1",
            "headers": {
                "From": "Alex <alex@example.com>",
                "To": "me <me@example.com>",
                "Subject": "Re: Proposal",
                "Date": "Wed, 9 Jul 2025 10:00:00 +0000",
            },
            "body": "I will send the proposal by Friday. Let me know if you need anything else.",
        }

        signals = extract_signals_from_message(message, user_email="me@example.com")
        assert len(signals) >= 1
        # The entity should be Alex (from the From header)
        assert any(s["entity"] == "Alex" for s in signals)
        # At least one signal should be a commitment
        assert any("commitment" in s["signal_type"] or "promise" in s["signal_type"] for s in signals)

    def test_extract_signals_from_sent_email(self):
        """Sent emails (From = user) create commitment_made signals."""
        from maestro_personal_shell.signal_adapters.gmail import extract_signals_from_message

        message = {
            "message_id": "msg2",
            "headers": {
                "From": "me <me@example.com>",
                "To": "Alex <alex@example.com>",
                "Subject": "Proposal",
                "Date": "Wed, 9 Jul 2025 09:00:00 +0000",
            },
            "body": "I will send the proposal by Friday.",
        }

        signals = extract_signals_from_message(message, user_email="me@example.com")
        assert any(s["signal_type"] == "commitment_made" for s in signals)

    def test_no_false_positives_on_neutral_text(self):
        """Neutral text should not produce commitment signals."""
        from maestro_personal_shell.signal_adapters.gmail import detect_commitments_in_text

        commitments = detect_commitments_in_text(
            "The weather is nice today. I went for a walk."
        )
        assert len(commitments) == 0


# ---------------------------------------------------------------------------
# Calendar adapter tests
# ---------------------------------------------------------------------------


class TestCalendarAdapter:
    """Tests for the Calendar signal adapter."""

    def test_extract_meeting_scheduled(self):
        """A confirmed calendar event creates a meeting.scheduled signal."""
        from maestro_personal_shell.signal_adapters.calendar import extract_signals_from_event

        event = {
            "id": "evt1",
            "summary": "1:1 with Alex",
            "start": {"dateTime": "2025-07-15T14:00:00+00:00"},
            "end": {"dateTime": "2025-07-15T14:30:00+00:00"},
            "attendees": [
                {"email": "me@example.com", "displayName": "Me"},
                {"email": "alex@example.com", "displayName": "Alex"},
            ],
            "status": "confirmed",
        }

        signals = extract_signals_from_event(event, user_email="me@example.com")
        assert len(signals) >= 1
        assert any(s["signal_type"] == "meeting.scheduled" for s in signals)
        assert any(s["entity"] == "Alex" for s in signals)

    def test_extract_meeting_cancelled(self):
        """A cancelled event creates a meeting.cancelled signal."""
        from maestro_personal_shell.signal_adapters.calendar import extract_signals_from_event

        event = {
            "id": "evt2",
            "summary": "Team sync",
            "start": {"dateTime": "2025-07-15T14:00:00+00:00"},
            "end": {"dateTime": "2025-07-15T15:00:00+00:00"},
            "attendees": [{"email": "alex@example.com"}],
            "status": "cancelled",
        }

        signals = extract_signals_from_event(event, user_email="me@example.com")
        assert any(s["signal_type"] == "meeting.cancelled" for s in signals)

    def test_detect_upcoming_meetings(self):
        """Meetings within N hours are flagged as upcoming."""
        from maestro_personal_shell.signal_adapters.calendar import detect_upcoming_meetings

        now = datetime.now(timezone.utc)
        events = [
            {
                "id": "past",
                "summary": "Past meeting",
                "start": {"dateTime": (now - timedelta(hours=2)).isoformat()},
                "status": "confirmed",
            },
            {
                "id": "soon",
                "summary": "Soon meeting",
                "start": {"dateTime": (now + timedelta(hours=1)).isoformat()},
                "status": "confirmed",
            },
            {
                "id": "later",
                "summary": "Later meeting",
                "start": {"dateTime": (now + timedelta(hours=48)).isoformat()},
                "status": "confirmed",
            },
        ]

        upcoming = detect_upcoming_meetings(events, hours_ahead=24)
        assert len(upcoming) == 1
        assert upcoming[0]["id"] == "soon"


# ---------------------------------------------------------------------------
# Whisper surface tests
# ---------------------------------------------------------------------------


class TestWhisperSurface:
    """Tests for the Whisper surface — proactive intervention."""

    def _make_shell_with_stale_commitment(self, days_stale: int = 5):
        """Build a shell with a stale commitment (no follow-up for N days)."""
        from maestro_personal_shell.shell import PersonalShell
        from maestro_personal_shell.personal_oem_state import PersonalOemState, PersonalSignal

        old_time = datetime.now(timezone.utc) - timedelta(days=days_stale)
        state = PersonalOemState(signals=[
            PersonalSignal(
                entity="Alex",
                text="I will send the proposal by Friday",
                signal_type="commitment_made",
                timestamp=old_time,
            ),
        ])
        return PersonalShell(oem_state=state)

    def test_whisper_detects_stale_commitment(self):
        """A commitment stale 5+ days should produce a whisper."""
        from maestro_personal_shell.surfaces.whisper import WhisperSurface

        shell = self._make_shell_with_stale_commitment(days_stale=5)
        surface = WhisperSurface(shell=shell)
        whispers = surface.get_active_whispers()

        stale_whispers = [w for w in whispers if w["type"] == "stale_commitment"]
        assert len(stale_whispers) >= 1
        assert "Alex" in stale_whispers[0]["title"]
        assert stale_whispers[0]["priority"] in ("high", "medium")

    def test_whisper_silence_on_fresh_commitment(self):
        """A commitment with follow-up within 3 days should NOT whisper (restraint)."""
        from maestro_personal_shell.surfaces.whisper import WhisperSurface
        from maestro_personal_shell.shell import PersonalShell
        from maestro_personal_shell.personal_oem_state import PersonalOemState, PersonalSignal

        now = datetime.now(timezone.utc)
        state = PersonalOemState(signals=[
            PersonalSignal(
                entity="Alex",
                text="I will send the proposal",
                signal_type="commitment_made",
                timestamp=now - timedelta(days=1),
            ),
            # Follow-up yesterday — commitment is not stale
            PersonalSignal(
                entity="Alex",
                text="Did you get the proposal?",
                signal_type="follow_up.required",
                timestamp=now - timedelta(hours=12),
            ),
        ])
        shell = PersonalShell(oem_state=state)
        surface = WhisperSurface(shell=shell)
        whispers = surface.get_active_whispers()

        stale_whispers = [w for w in whispers if w["type"] == "stale_commitment"]
        assert len(stale_whispers) == 0, (
            "Fresh commitment with follow-up should NOT whisper — restraint"
        )

    def test_whisper_silence_on_empty_state(self):
        """Empty state should produce zero whispers (trusted silence)."""
        from maestro_personal_shell.surfaces.whisper import WhisperSurface
        from maestro_personal_shell.shell import PersonalShell
        from maestro_personal_shell.personal_oem_state import PersonalOemState

        shell = PersonalShell(oem_state=PersonalOemState(signals=[]))
        surface = WhisperSurface(shell=shell)
        whispers = surface.get_active_whispers()
        assert whispers == []

    def test_should_whisper_now_returns_true_for_high_priority(self):
        """should_whisper_now returns True only if there's a high-priority whisper."""
        from maestro_personal_shell.surfaces.whisper import WhisperSurface

        # 7+ days stale = high priority
        shell = self._make_shell_with_stale_commitment(days_stale=8)
        surface = WhisperSurface(shell=shell)
        assert surface.should_whisper_now() == True

    def test_should_whisper_now_returns_false_for_empty(self):
        """should_whisper_now returns False for empty state (trusted silence)."""
        from maestro_personal_shell.surfaces.whisper import WhisperSurface
        from maestro_personal_shell.shell import PersonalShell
        from maestro_personal_shell.personal_oem_state import PersonalOemState

        shell = PersonalShell(oem_state=PersonalOemState(signals=[]))
        surface = WhisperSurface(shell=shell)
        assert surface.should_whisper_now() == False


# ---------------------------------------------------------------------------
# v2/v3 API endpoint tests
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_db():
    """Use a temp DB for each API test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-token-v2"

    import importlib
    import maestro_personal_shell.api as api_module
    importlib.reload(api_module)
    api_module.init_db(db_path)

    yield api_module

    os.unlink(db_path)
    del os.environ["MAESTRO_PERSONAL_DB"]
    del os.environ["MAESTRO_PERSONAL_TOKEN"]


@pytest.fixture
def client(temp_db):
    from fastapi.testclient import TestClient
    return TestClient(temp_db.app)


@pytest.fixture
def auth_headers(client):
    response = client.post("/api/auth/login", json={"password": "any"})
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


class TestV2APIEndpoints:
    """Tests for v2 API endpoints: Whisper, Gmail sync, Calendar sync."""

    def test_get_whispers_empty(self, client, auth_headers):
        """GET /api/whisper returns empty list when no whispers (trusted silence)."""
        response = client.get("/api/whisper", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []

    def test_gmail_sync_creates_signals(self, client, auth_headers):
        """POST /api/sync/gmail extracts signals from Gmail messages."""
        messages = [
            {
                "message_id": "m1",
                "headers": {
                    "From": "me <me@example.com>",
                    "To": "Alex <alex@example.com>",
                    "Subject": "Proposal",
                    "Date": "Wed, 9 Jul 2025 09:00:00 +0000",
                },
                "body": "I will send the proposal by Friday.",
            }
        ]

        response = client.post("/api/sync/gmail", json={
            "messages": messages,
            "user_email": "me@example.com",
        }, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["signals_created"] >= 1

    def test_calendar_sync_creates_signals(self, client, auth_headers):
        """POST /api/sync/calendar extracts signals from calendar events."""
        events = [
            {
                "id": "e1",
                "summary": "1:1 with Alex",
                "start": {"dateTime": "2025-07-15T14:00:00+00:00"},
                "end": {"dateTime": "2025-07-15T14:30:00+00:00"},
                "attendees": [
                    {"email": "me@example.com"},
                    {"email": "alex@example.com", "displayName": "Alex"},
                ],
                "status": "confirmed",
            }
        ]

        response = client.post("/api/sync/calendar", json={
            "events": events,
            "user_email": "me@example.com",
        }, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["signals_created"] >= 1


class TestV3APIEndpoints:
    """Tests for v3 API endpoints: account deletion, data export."""

    def test_delete_account_removes_all_signals(self, client, auth_headers):
        """DELETE /api/account removes all signals."""
        # Add a signal first
        client.post("/api/signals", json={
            "entity": "Alex",
            "text": "Test commitment",
            "signal_type": "commitment_made",
        }, headers=auth_headers)

        # Verify it exists
        response = client.get("/api/signals", headers=auth_headers)
        assert len(response.json()) >= 1

        # Delete account
        response = client.delete("/api/account", headers=auth_headers)
        assert response.status_code == 200

        # Verify signals are gone
        response = client.get("/api/signals", headers=auth_headers)
        assert response.json() == []

    def test_export_data(self, client, auth_headers):
        """GET /api/account/export returns all user data."""
        # Add a signal
        client.post("/api/signals", json={
            "entity": "Sam",
            "text": "Review the PR",
            "signal_type": "commitment_made",
        }, headers=auth_headers)

        # Export
        response = client.get("/api/account/export", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["signal_count"] >= 1
        assert len(data["signals"]) >= 1
        assert any(s["entity"] == "Sam" for s in data["signals"])
