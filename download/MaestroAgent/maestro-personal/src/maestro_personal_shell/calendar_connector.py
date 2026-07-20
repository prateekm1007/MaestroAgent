"""
Google Calendar OAuth2 connector — real Calendar API integration (Phase E).

Read-only connector: pulls upcoming meetings, ingests as signals, feeds
into the Pre-call Intelligence Panel (built in Phase A).

NO send capability (Calendar is read-only by design). No draft generation.
This connector exists solely to complete the meeting intelligence loop:
  Calendar (BEFORE) → Copilot (DURING) → Gmail/Slack (AFTER)

Architecture (same pattern as gmail_connector.py):
  - CalendarOAuthClient: OAuth2 authorization code flow + token refresh
  - CalendarAPIClient: Calendar REST API calls (events.list)
  - CalendarIngester: pulls upcoming events, extracts participants + context

OAuth2 flow:
  1. User clicks "Connect Calendar" in the UI
  2. Backend generates authorization URL with scope:
     - https://www.googleapis.com/auth/calendar.readonly
  3. User grants access on Google's consent screen
  4. Google redirects to /api/connectors/calendar/oauth/callback
  5. Backend exchanges code for access + refresh tokens
  6. Tokens stored encrypted in ConnectorStore
  7. Ingestion uses the access token to call calendar.events().list()
  8. Each upcoming event becomes a signal with:
      entity = each attendee name
      text = "Meeting with {attendees} at {time} — {summary}"
      signal_type = reported_statement
      timestamp = event start time
      source = calendar:upcoming

The pre-call intel panel then uses these signals to surface what matters
for the upcoming meeting (forgotten commitments, open questions, etc.).

Configuration (env vars):
  - MAESTRO_CALENDAR_CLIENT_ID: Google OAuth2 client ID
  - MAESTRO_CALENDAR_CLIENT_SECRET: Google OAuth2 client secret
  - MAESTRO_CALENDAR_REDIRECT_URI: OAuth2 redirect URI

When NOT set, falls back to MOCK_INGESTION_DATA — demo mode.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any
from urllib.parse import urlencode, quote

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
]

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


def _get_calendar_config() -> dict[str, str]:
    """Get Calendar OAuth2 config from env."""
    return {
        "client_id": os.environ.get("MAESTRO_CALENDAR_CLIENT_ID", ""),
        "client_secret": os.environ.get("MAESTRO_CALENDAR_CLIENT_SECRET", ""),
        "redirect_uri": os.environ.get(
            "MAESTRO_CALENDAR_REDIRECT_URI",
            "http://localhost:8766/api/connectors/calendar/oauth/callback",
        ),
    }


def is_calendar_configured() -> bool:
    """Check if real Calendar OAuth credentials are configured."""
    config = _get_calendar_config()
    return bool(config["client_id"] and config["client_secret"])


# ---------------------------------------------------------------------------
# Calendar OAuth2 Client
# ---------------------------------------------------------------------------

class CalendarOAuthClient:
    """Handles Google Calendar OAuth2 authorization code flow + token refresh.

    Same structure as GmailOAuthClient (both use Google's OAuth2 endpoint).
    """

    def __init__(self):
        self.config = _get_calendar_config()

    def get_authorization_url(self, state: str = "") -> str:
        """Generate the Google OAuth2 authorization URL for Calendar scope."""
        if not self.config["client_id"]:
            raise ValueError("Calendar OAuth not configured (MAESTRO_CALENDAR_CLIENT_ID missing)")

        params = {
            "client_id": self.config["client_id"],
            "redirect_uri": self.config["redirect_uri"],
            "response_type": "code",
            "scope": " ".join(CALENDAR_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    def exchange_code_for_tokens(self, code: str) -> dict[str, Any]:
        """Exchange authorization code for access + refresh tokens."""
        import urllib.request
        import urllib.parse

        data = urllib.parse.urlencode({
            "code": code,
            "client_id": self.config["client_id"],
            "client_secret": self.config["client_secret"],
            "redirect_uri": self.config["redirect_uri"],
            "grant_type": "authorization_code",
        }).encode()

        req = urllib.request.Request(
            GOOGLE_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                token_data = json.loads(resp.read().decode())
                token_data["expires_at"] = (
                    datetime.now(timezone.utc) + timedelta(seconds=token_data.get("expires_in", 3600))
                ).isoformat()
                return token_data
        except Exception as e:
            logger.error(f"Calendar OAuth token exchange failed: {e}")
            return {"error": str(e)}

    def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Refresh an expired access token."""
        import urllib.request
        import urllib.parse

        data = urllib.parse.urlencode({
            "client_id": self.config["client_id"],
            "client_secret": self.config["client_secret"],
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }).encode()

        req = urllib.request.Request(
            GOOGLE_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                token_data = json.loads(resp.read().decode())
                token_data["expires_at"] = (
                    datetime.now(timezone.utc) + timedelta(seconds=token_data.get("expires_in", 3600))
                ).isoformat()
                return token_data
        except Exception as e:
            logger.error(f"Calendar token refresh failed: {e}")
            return {"error": str(e)}

    def get_valid_access_token(self, stored_token_json: str) -> tuple[str, str]:
        """Get a valid access token, refreshing if necessary.

        Returns: (access_token, updated_token_json)
        """
        try:
            token_data = json.loads(stored_token_json)
        except Exception:
            return "", stored_token_json

        expires_at_str = token_data.get("expires_at", "")
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) < (expires_at - timedelta(minutes=5)):
                    return token_data.get("access_token", ""), stored_token_json
            except Exception as e:
                logger.debug("get failed: %s", e)
        refresh_token = token_data.get("refresh_token", "")
        if not refresh_token:
            return "", stored_token_json

        refreshed = self.refresh_access_token(refresh_token)
        if "error" in refreshed:
            return "", stored_token_json

        token_data["access_token"] = refreshed["access_token"]
        token_data["expires_at"] = refreshed["expires_at"]
        updated_json = json.dumps(token_data)
        return token_data["access_token"], updated_json


# ---------------------------------------------------------------------------
# Calendar API Client (read-only)
# ---------------------------------------------------------------------------

class CalendarAPIClient:
    """Calls the Google Calendar REST API using an access token.

    Read-only: only events.list(). No create/update/delete.
    """

    def __init__(self, access_token: str):
        self.access_token = access_token

    def _request(self, url: str) -> dict:
        import urllib.request
        headers = {"Authorization": f"Bearer {self.access_token}"}
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            logger.error(f"Calendar API GET failed: {e}")
            return {"error": str(e)}

    def list_upcoming_events(self, max_results: int = 25, days_ahead: int = 14) -> list[dict[str, Any]]:
        """List upcoming events from the user's primary calendar.

        Args:
            max_results: max events to return
            days_ahead: how many days ahead to look

        Returns: list of event dicts with {id, summary, start, end, attendees, htmlLink}
        """
        time_min = datetime.now(timezone.utc).isoformat()
        time_max = (datetime.now(timezone.utc) + timedelta(days=days_ahead)).isoformat()

        params = urlencode({
            "timeMin": time_min,
            "timeMax": time_max,
            "maxResults": str(max_results),
            "singleEvents": "true",
            "orderBy": "startTime",
        })
        url = f"{CALENDAR_API_BASE}?{params}"
        result = self._request(url)

        if "error" in result:
            return []
        return result.get("items", [])


# ---------------------------------------------------------------------------
# Calendar Ingester — pulls events, creates signals
# ---------------------------------------------------------------------------

class CalendarIngester:
    """Pulls upcoming events from Google Calendar and creates signals.

    Each event becomes one or more signals (one per attendee entity):
      entity = attendee name (or email username)
      text = "Meeting with {organizer} at {time} — {summary}"
      signal_type = reported_statement
      timestamp = event start time
      source = calendar:upcoming

    These signals feed the Pre-call Intelligence Panel, which surfaces
    forgotten commitments, open questions, and contradictions for the
    upcoming meeting.
    """

    def __init__(self, access_token: str):
        self.api = CalendarAPIClient(access_token)

    def ingest_upcoming(
        self,
        max_events: int = 25,
        days_ahead: int = 14,
    ) -> dict[str, Any]:
        """Ingest upcoming calendar events.

        Returns: {
            events_scanned: int,
            signals_created: int,
            signals: list[dict],
            errors: list[str],
        }
        """
        events = self.api.list_upcoming_events(max_results=max_events, days_ahead=days_ahead)

        signals: list[dict[str, Any]] = []
        for event in events:
            try:
                event_signals = self._extract_signals_from_event(event)
                signals.extend(event_signals)
            except Exception as e:
                logger.warning(f"Event extraction failed: {e}")

        return {
            "events_scanned": len(events),
            "signals_created": len(signals),
            "signals": signals,
            "errors": [],
        }

    def _extract_signals_from_event(self, event: dict) -> list[dict[str, Any]]:
        """Extract signals from a calendar event.

        Creates one signal per attendee (so the pre-call panel can surface
        commitments for each person the user is about to meet with).
        """
        summary = event.get("summary", "(no title)")
        start = event.get("start", {}).get("dateTime", event.get("start", {}).get("date", ""))
        timestamp = self._parse_calendar_time(start)

        attendees = event.get("attendees", [])
        # Filter to human attendees (skip resources, skip self)
        human_attendees = [
            a for a in attendees
            if not a.get("self") and not a.get("resource")
        ]

        if not human_attendees:
            # No attendees — create one signal with the event summary as entity
            return [{
                "entity": self._extract_entity_from_email(event.get("creator", {}).get("email", "")) or "Meeting",
                "text": f"Meeting: {summary} at {self._format_time(timestamp)}",
                "signal_type": "reported_statement",
                "timestamp": timestamp,
                "source": "calendar:upcoming",
            }]

        signals = []
        attendee_names = [self._extract_entity_from_email(a.get("email", "")) for a in human_attendees]
        attendee_list = ", ".join(attendee_names[:3])
        if len(attendee_names) > 3:
            attendee_list += f" +{len(attendee_names) - 3} others"

        for attendee in human_attendees:
            entity = self._extract_entity_from_email(attendee.get("email", ""))
            if not entity:
                continue
            signals.append({
                "entity": entity,
                "text": f"Meeting with {attendee_list} at {self._format_time(timestamp)} — {summary}",
                "signal_type": "reported_statement",
                "timestamp": timestamp,
                "source": "calendar:upcoming",
            })

        return signals

    def _extract_entity_from_email(self, email: str) -> str:
        """Extract a name from an email address.

        For 'maria.garcia@example.com' → 'Maria Garcia'
        For 'maria@example.com' → 'Maria'
        """
        if not email:
            return ""
        username = email.split("@")[0]
        # Replace dots/underscores with spaces, title-case
        name = username.replace(".", " ").replace("_", " ").strip()
        return name.title() if name else ""

    def _parse_calendar_time(self, time_str: str) -> str:
        """Parse a Calendar API time string into ISO format."""
        if not time_str:
            return datetime.now(timezone.utc).isoformat()
        try:
            # Calendar API returns ISO 8601 with 'Z' or offset
            return time_str.replace("Z", "+00:00") if time_str.endswith("Z") else time_str
        except Exception:
            return datetime.now(timezone.utc).isoformat()

    def _format_time(self, iso_time: str) -> str:
        """Format an ISO time for human-readable display."""
        try:
            dt = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
            return dt.strftime("%a %b %d at %I:%M %p")
        except Exception:
            return iso_time


# ---------------------------------------------------------------------------
# Factory — used by ConnectorStore._fetch_messages
# ---------------------------------------------------------------------------

def fetch_real_calendar_events(
    stored_token_json: str,
    oauth_client: CalendarOAuthClient,
    max_events: int = 25,
    days_ahead: int = 14,
) -> tuple[list[dict[str, Any]], str]:
    """Fetch real upcoming events from Google Calendar.

    Args:
        stored_token_json: JSON of {access_token, refresh_token, expires_at}
        oauth_client: CalendarOAuthClient instance
        max_events: max events to pull
        days_ahead: how many days ahead to look

    Returns:
        (signals, updated_token_json) — signals ready for ingestion,
        updated_token_json includes refreshed access token if applicable.
    """
    access_token, updated_token_json = oauth_client.get_valid_access_token(stored_token_json)
    if not access_token:
        return [], stored_token_json

    ingester = CalendarIngester(access_token)
    result = ingester.ingest_upcoming(max_events=max_events, days_ahead=days_ahead)

    return result.get("signals", []), updated_token_json
