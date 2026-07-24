"""Microsoft Mail (Graph API) OAuth2 connector — one-click OAuth for
Microsoft 365 / Outlook / Hotmail / Live accounts.

Auditor (2026-07-24) strict-order item 2: "Build the work-email OAuth
redesign — Google / Microsoft / Yahoo as one-click OAuth cards".

This connector implements the Microsoft Identity Platform v2.0
authorization-code flow with the Mail.Read + Mail.Send scopes (delegated
permissions). It also supports the enterprise admin-consent path via the
`prompt=admin_consent` parameter for tenant-wide deployment.

Configuration (env vars):
  - MAESTRO_MICROSOFT_CLIENT_ID: Azure app registration client ID
  - MAESTRO_MICROSOFT_CLIENT_SECRET: Azure app client secret
  - MAESTRO_MICROSOFT_TENANT_ID: 'common' for multi-tenant, or specific
    tenant ID for single-tenant enterprise apps
  - MAESTRO_MICROSOFT_REDIRECT_URI: must be whitelisted in Azure

When NOT set, is_microsoft_configured() returns False — no fake
"connected" ever.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Microsoft Identity Platform v2.0 endpoints
MS_AUTH_BASE = "https://login.microsoftonline.com"
MS_TOKEN_BASE = "https://login.microsoftonline.com"

# Microsoft Graph API base
MS_GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# Delegated scopes for mail read/send (NOT application scopes — these run
# as the signed-in user, which is the right model for a personal-agent
# product; the admin-consent path pre-approves these for an entire tenant
# so individual users don't see a consent prompt)
MICROSOFT_MAIL_SCOPES = [
    "https://graph.microsoft.com/Mail.Read",
    "https://graph.microsoft.com/Mail.Send",
    "offline_access",  # required for refresh tokens
    "openid", "email", "profile",
]


def _get_microsoft_config() -> dict[str, str]:
    """Get Microsoft OAuth2 config from env."""
    return {
        "client_id": os.environ.get("MAESTRO_MICROSOFT_CLIENT_ID", ""),
        "client_secret": os.environ.get("MAESTRO_MICROSOFT_CLIENT_SECRET", ""),
        "tenant_id": os.environ.get("MAESTRO_MICROSOFT_TENANT_ID", "common"),
        "redirect_uri": os.environ.get(
            "MAESTRO_MICROSOFT_REDIRECT_URI",
            "https://maestroagent-production.up.railway.app/api/connectors/microsoft_mail/oauth/callback",
        ),
    }


def is_microsoft_configured() -> bool:
    """Check if real Microsoft Mail OAuth credentials are configured."""
    config = _get_microsoft_config()
    return bool(config["client_id"] and config["client_secret"])


# ---------------------------------------------------------------------------
# Microsoft Mail OAuth2 Client
# ---------------------------------------------------------------------------


class MicrosoftMailOAuthClient:
    """Microsoft Graph OAuth2 authorization-code flow + token refresh.

    Supports both:
      - User consent flow (default — each user consents individually)
      - Admin consent flow (prompt=admin_consent — pre-approves the scopes
        for an entire tenant, used for enterprise deployment)
    """

    def __init__(self, admin_consent: bool = False):
        self.config = _get_microsoft_config()
        self.admin_consent = admin_consent

    def get_authorization_url(self, state: str = "") -> str:
        """Generate the Microsoft OAuth2 authorization URL.

        When admin_consent=True, appends prompt=admin_consent to the URL
        so a tenant admin can pre-approve the scopes for all users in
        their organization. This is the enterprise admin-consent path
        the auditor asked for.
        """
        if not self.config["client_id"]:
            raise ValueError(
                "Microsoft OAuth not configured (MAESTRO_MICROSOFT_CLIENT_ID missing)"
            )

        tenant = self.config["tenant_id"]
        auth_url = f"{MS_AUTH_BASE}/{tenant}/oauth2/v2.0/authorize"

        params = {
            "client_id": self.config["client_id"],
            "redirect_uri": self.config["redirect_uri"],
            "response_type": "code",
            "scope": " ".join(MICROSOFT_MAIL_SCOPES),
            "state": state,
        }
        if self.admin_consent:
            params["prompt"] = "admin_consent"
        else:
            # Force consent to ensure we get a refresh_token
            params["prompt"] = "consent"

        return f"{auth_url}?{urlencode(params)}"

    def exchange_code_for_tokens(self, code: str) -> dict[str, Any]:
        """Exchange authorization code for access + refresh tokens."""
        tenant = self.config["tenant_id"]
        token_url = f"{MS_TOKEN_BASE}/{tenant}/oauth2/v2.0/token"

        data = urlencode({
            "code": code,
            "client_id": self.config["client_id"],
            "client_secret": self.config["client_secret"],
            "redirect_uri": self.config["redirect_uri"],
            "grant_type": "authorization_code",
            "scope": " ".join(MICROSOFT_MAIL_SCOPES),
        }).encode()

        req = urllib.request.Request(
            token_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                token_data = json.loads(resp.read().decode())
                token_data["expires_at"] = (
                    datetime.now(timezone.utc)
                    + timedelta(seconds=token_data.get("expires_in", 3600))
                ).isoformat()
                return token_data
        except Exception as e:
            logger.error("Microsoft OAuth token exchange failed: %s", e)
            return {"error": str(e)}

    def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Refresh an expired access token."""
        tenant = self.config["tenant_id"]
        token_url = f"{MS_TOKEN_BASE}/{tenant}/oauth2/v2.0/token"

        data = urlencode({
            "client_id": self.config["client_id"],
            "client_secret": self.config["client_secret"],
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "scope": " ".join(MICROSOFT_MAIL_SCOPES),
        }).encode()

        req = urllib.request.Request(
            token_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                token_data = json.loads(resp.read().decode())
                token_data["expires_at"] = (
                    datetime.now(timezone.utc)
                    + timedelta(seconds=token_data.get("expires_in", 3600))
                ).isoformat()
                return token_data
        except Exception as e:
            logger.error("Microsoft token refresh failed: %s", e)
            return {"error": str(e)}

    def get_valid_access_token(self, stored_token_json: str) -> tuple[str, str]:
        """Get a valid access token, refreshing if necessary."""
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
            except Exception:
                pass

        refresh_token = token_data.get("refresh_token", "")
        if not refresh_token:
            return "", stored_token_json

        refreshed = self.refresh_access_token(refresh_token)
        if "error" in refreshed:
            return "", stored_token_json

        token_data["access_token"] = refreshed["access_token"]
        token_data["expires_at"] = refreshed["expires_at"]
        if "refresh_token" in refreshed:
            token_data["refresh_token"] = refreshed["refresh_token"]
        updated_json = json.dumps(token_data)
        return token_data["access_token"], updated_json


# ---------------------------------------------------------------------------
# Microsoft Graph API Client
# ---------------------------------------------------------------------------


class MicrosoftMailAPIClient:
    """Calls the Microsoft Graph Mail API using an access token."""

    def __init__(self, access_token: str):
        self.access_token = access_token

    def _request(self, path: str, method: str = "GET", body: dict | None = None) -> dict:
        url = f"{MS_GRAPH_BASE}{path}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            err_body = e.read().decode() if e.fp else ""
            logger.error("MS Graph %s %s failed: %s %s", method, path, e.code, err_body[:200])
            return {"error": f"HTTP {e.code}: {err_body[:200]}"}
        except Exception as e:
            logger.error("MS Graph %s %s failed: %s", method, path, e)
            return {"error": str(e)}

    def list_messages(self, max_results: int = 50) -> list[dict[str, Any]]:
        """List recent messages from the user's inbox."""
        result = self._request(f"/me/messages?$top={max_results}&$select=subject,from,receivedDateTime,bodyPreview,id")
        return result.get("value", []) if "error" not in result else []

    def get_message(self, message_id: str) -> dict[str, Any]:
        """Get a single message with full body."""
        return self._request(
            f"/me/messages/{message_id}?$select=subject,from,receivedDateTime,body"
        )


# ---------------------------------------------------------------------------
# Microsoft Mail Ingester
# ---------------------------------------------------------------------------


class MicrosoftMailIngester:
    """Pulls messages from Microsoft Mail and extracts commitments."""

    def __init__(self, access_token: str):
        self.api = MicrosoftMailAPIClient(access_token)

    def ingest_recent(self, max_messages: int = 50) -> dict[str, Any]:
        messages = self.api.list_messages(max_results=max_messages)
        commitments_found = 0
        signals: list[dict[str, Any]] = []
        errors: list[str] = []

        for msg in messages:
            try:
                body_preview = msg.get("bodyPreview", "")
                body_obj = msg.get("body", {})
                body = body_obj.get("content", "") if isinstance(body_obj, dict) else ""
                # Strip HTML tags if HTML content
                if body_obj.get("contentType") == "html":
                    body = re.sub(r"<[^>]+>", "", body)
                body = body or body_preview

                if not body:
                    continue

                from_obj = msg.get("from", {}).get("emailAddress", {})
                entity = from_obj.get("name", "") or from_obj.get("address", "")
                timestamp = msg.get("receivedDateTime", "")

                commitments = self._keyword_commitment_detection(body, entity, timestamp)
                for c in commitments:
                    commitments_found += 1
                    signals.append(c)

            except Exception as e:
                errors.append(f"Message: {e}")

        return {
            "messages_scanned": len(messages),
            "commitments_found": commitments_found,
            "signals": signals,
            "errors": errors,
        }

    def _keyword_commitment_detection(
        self, body: str, entity: str, timestamp: str
    ) -> list[dict[str, Any]]:
        body_lower = body.lower()
        patterns = [
            r"i will (.+?)(?:[.\n]|$)",
            r"i'll (.+?)(?:[.\n]|$)",
            r"i promise to (.+?)(?:[.\n]|$)",
            r"i need to (.+?)(?:[.\n]|$)",
            r"let me (.+?)(?:[.\n]|$)",
            r"i'm going to (.+?)(?:[.\n]|$)",
        ]
        commitments = []
        for pattern in patterns:
            matches = re.findall(pattern, body_lower, re.MULTILINE)
            for match in matches[:2]:
                commitments.append({
                    "entity": entity,
                    "text": match.strip()[:200],
                    "signal_type": "commitment_made",
                    "timestamp": timestamp,
                    "source": "microsoft_mail:inbox",
                })
        return commitments[:5]


# ---------------------------------------------------------------------------
# Factory — used by ConnectorStore._fetch_messages
# ---------------------------------------------------------------------------


def fetch_real_microsoft_messages(
    stored_token_json: str,
    oauth_client: MicrosoftMailOAuthClient,
    max_messages: int = 50,
) -> tuple[list[dict[str, Any]], str]:
    """Fetch real messages from Microsoft Mail using stored OAuth tokens."""
    access_token, updated_token_json = oauth_client.get_valid_access_token(stored_token_json)
    if not access_token:
        return [], stored_token_json

    ingester = MicrosoftMailIngester(access_token)
    result = ingester.ingest_recent(max_messages=max_messages)
    return result.get("signals", []), updated_token_json
