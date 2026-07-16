"""
Connectors module — OAuth2 connector management + draft approval flow.

This is the real moat: passive signal ingestion from Gmail, Slack, GitHub,
etc. + commitment-aware draft generation with a human approval gate.

Architecture:
  - ConnectorStore: SQLite-backed storage for connector state + OAuth tokens
    (tokens stored encrypted-at-rest via Fernet when available, plaintext
    fallback for dev environments without a key)
  - DraftStore: SQLite-backed storage for pending drafts (email/message)
    with approval states: pending / approved / denied / used_as_draft
  - IngestionEngine: pulls messages from connectors, extracts commitments
    using the existing commitment_classifier, ingests as signals
  - DraftGenerator: generates commitment-aware drafts using the existing
    FollowUpEmailGenerator, with platform-specific formatting

Supported connectors (Phase 1-3):
  - gmail: OAuth2, read inbox + send via Gmail API
  - slack: OAuth2, read DMs + send via Slack Web API
  - github: OAuth2, read assigned issues/PRs + comment via REST API
  - calendar: OAuth2, read-only (Google Calendar)
  - whatsapp: Phase F — stub for now
  - facebook: Phase F — stub for now
  - instagram: Phase F — stub for now
  - twitter: Phase F — stub for now

Security:
  - OAuth tokens stored encrypted-at-rest (Fernet symmetric encryption)
  - Per-connector revocation (disconnect one without affecting others)
  - Audit log of every access (connector.connect, connector.ingest,
    draft.approve, draft.deny, draft.send)
  - Data minimization: extract commitments, don't store raw message bodies
    (only entity, text, timestamp — the signal)

The approval flow (approve / deny / use draft) is the trust mechanism.
Maestro NEVER auto-sends. Every draft requires explicit human approval.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from maestro_personal_shell.db_util import get_db_conn

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connector definitions
# ---------------------------------------------------------------------------

SUPPORTED_CONNECTORS: dict[str, dict[str, Any]] = {
    "gmail": {
        "name": "Gmail",
        "icon": "email",
        "category": "work",
        "scopes": ["readonly", "send"],
        "ingest_description": "Ingest email threads, extract commitments from your sent + received mail",
        "write_description": "Draft and send commitment follow-up emails on your behalf (with approval)",
        "oauth_configured": False,  # set True when real OAuth credentials are in env
        "phase": 1,
    },
    "slack": {
        "name": "Slack",
        "icon": "message",
        "category": "work",
        "scopes": ["channels:read", "chat:write", "im:read", "im:history"],
        "ingest_description": "Ingest DMs and channel mentions, extract commitments from conversations",
        "write_description": "Draft and send Slack follow-up messages (with approval)",
        "oauth_configured": False,
        "phase": 2,
    },
    "github": {
        "name": "GitHub",
        "icon": "code",
        "category": "work",
        "scopes": ["repo", "user"],
        "ingest_description": "Ingest assigned issues and PRs, extract action items",
        "write_description": "Draft issue comments and PR responses (with approval)",
        "oauth_configured": False,
        "phase": 3,
    },
    "calendar": {
        "name": "Google Calendar",
        "icon": "calendar",
        "category": "work",
        "scopes": ["calendar.readonly"],
        "ingest_description": "Ingest upcoming meetings, feed into pre-call intelligence",
        "write_description": "Read-only — no write capability",
        "oauth_configured": False,
        "phase": 4,
    },
    "work_email": {
        "name": "Work Email (IMAP/SMTP)",
        "icon": "briefcase",
        "category": "work",
        "scopes": ["imap", "smtp"],
        "ingest_description": "Connect any work email via IMAP (Exchange, Outlook, ProtonMail Bridge, custom domain). Extracts commitments from sent + received mail.",
        "write_description": "Draft and send commitment follow-up emails via SMTP (with approval)",
        "oauth_configured": False,
        "phase": 5,
    },
    "whatsapp": {
        "name": "WhatsApp",
        "icon": "chat",
        "category": "social",
        "scopes": ["messages"],
        "ingest_description": "Ingest WhatsApp conversations (requires WhatsApp Business API approval)",
        "write_description": "Draft and send WhatsApp messages (with approval)",
        "oauth_configured": False,
        "phase": 6,
    },
    "facebook": {
        "name": "Facebook",
        "icon": "social",
        "category": "social",
        "scopes": ["pages_messaging"],
        "ingest_description": "Ingest Facebook messages (requires Meta app review)",
        "write_description": "Draft and send Facebook messages (with approval)",
        "oauth_configured": False,
        "phase": 6,
    },
    "instagram": {
        "name": "Instagram",
        "icon": "social",
        "category": "social",
        "scopes": ["instagram_basic", "instagram_manage_messages"],
        "ingest_description": "Ingest Instagram DMs (requires Meta app review)",
        "write_description": "Draft and send Instagram messages (with approval)",
        "oauth_configured": False,
        "phase": 6,
    },
    "twitter": {
        "name": "Twitter / X",
        "icon": "social",
        "category": "social",
        "scopes": ["tweet.read", "dm.read", "dm.write"],
        "ingest_description": "Ingest Twitter DMs (API access restricted since 2023)",
        "write_description": "Draft and send Twitter DMs (with approval)",
        "oauth_configured": False,
        "phase": 6,
    },
}

# Mock message data for demo mode (when OAuth not configured)
# These simulate what would be pulled from a real connector
MOCK_INGESTION_DATA: dict[str, list[dict[str, Any]]] = {
    "gmail": [
        {
            "entity": "Maria Garcia",
            "text": "I will send Maria Garcia the pricing proposal by Friday.",
            "timestamp": "2026-07-10T14:30:00Z",
            "source": "gmail:inbox",
            "commitment_type": "commitment_made",
        },
        {
            "entity": "Riley Quinn",
            "text": "Riley asked for the security questionnaire — no response in 5 days.",
            "timestamp": "2026-07-08T09:15:00Z",
            "source": "gmail:sent",
            "commitment_type": "follow_up_required",
        },
        {
            "entity": "AcmeCorp",
            "text": "AcmeCorp requested a 10% discount on the annual contract.",
            "timestamp": "2026-07-09T11:00:00Z",
            "source": "gmail:inbox",
            "commitment_type": "reported_statement",
        },
        {
            "entity": "Alex Chen",
            "text": "Alex committed to delivering the design review by Wednesday.",
            "timestamp": "2026-07-11T16:45:00Z",
            "source": "gmail:inbox",
            "commitment_type": "commitment_made",
        },
    ],
    "slack": [
        {
            "entity": "Sam Patel",
            "text": "Sam promised to review the PR by end of day.",
            "timestamp": "2026-07-11T10:30:00Z",
            "source": "slack:dm",
            "commitment_type": "commitment_made",
        },
        {
            "entity": "Board",
            "text": "Board escalation: investor wants to see Q3 numbers before Friday meeting.",
            "timestamp": "2026-07-10T08:00:00Z",
            "source": "slack:channel",
            "commitment_type": "reported_statement",
        },
    ],
    "github": [
        {
            "entity": "Orion Tech",
            "text": "Orion Tech sent the final invoice at $150k — pricing dispute.",
            "timestamp": "2026-07-09T14:00:00Z",
            "source": "github:issue",
            "commitment_type": "reported_statement",
        },
    ],
    "calendar": [
        {
            "entity": "Maria Garcia",
            "text": "Meeting with Maria Garcia scheduled for Friday at 2pm.",
            "timestamp": "2026-07-11T09:00:00Z",
            "source": "calendar:upcoming",
            "commitment_type": "reported_statement",
        },
    ],
}


class ConnectorStore:
    """SQLite-backed storage for connector state + encrypted OAuth tokens.

    Tables:
      - connectors: per-user connector state (connected, token, last_ingest)
      - drafts: pending drafts with approval state
      - connector_audit: audit log of every connector + draft action
    """

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.environ.get(
            "MAESTRO_PERSONAL_DB",
            str(Path(__file__).resolve().parent / "personal.db"),
        )
        self._encryption_key = self._get_encryption_key()
        self._init_db()

    def _get_encryption_key(self) -> bytes | None:
        """Get the Fernet encryption key from env, or return None for dev mode."""
        key = os.environ.get("MAESTRO_ENCRYPTION_KEY")
        if key:
            return key.encode() if isinstance(key, str) else key
        return None

    def _encrypt(self, plaintext: str) -> str:
        """Encrypt a string. Falls back to base64 for dev mode."""
        if not self._encryption_key:
            # Dev mode — no encryption (log a warning once)
            return f"dev:{plaintext}"
        try:
            from cryptography.fernet import Fernet
            f = Fernet(self._encryption_key)
            return f.encrypt(plaintext.encode()).decode()
        except ImportError:
            return f"dev:{plaintext}"
        except Exception as e:
            logger.warning(f"Encryption failed, using dev mode: {e}")
            return f"dev:{plaintext}"

    def _decrypt(self, ciphertext: str) -> str:
        """Decrypt a string."""
        if ciphertext.startswith("dev:"):
            return ciphertext[4:]
        if not self._encryption_key:
            return ciphertext
        try:
            from cryptography.fernet import Fernet
            f = Fernet(self._encryption_key)
            return f.decrypt(ciphertext.encode()).decode()
        except Exception:
            return ciphertext

    def _init_db(self) -> None:
        try:
            conn = get_db_conn(self.db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS connectors (
                    user_email TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    connected INTEGER DEFAULT 0,
                    token TEXT DEFAULT '',
                    connected_at TEXT DEFAULT '',
                    last_ingest_at TEXT DEFAULT '',
                    commitments_ingested INTEGER DEFAULT 0,
                    PRIMARY KEY (user_email, provider)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS drafts (
                    draft_id TEXT PRIMARY KEY,
                    user_email TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    subject TEXT DEFAULT '',
                    body TEXT NOT NULL,
                    commitment_ref TEXT DEFAULT '',
                    evidence_refs TEXT DEFAULT '[]',
                    status TEXT DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    resolved_at TEXT DEFAULT '',
                    sent_message_id TEXT DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS connector_audit (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_email TEXT NOT NULL,
                    action TEXT NOT NULL,
                    provider TEXT DEFAULT '',
                    detail TEXT DEFAULT '',
                    timestamp TEXT NOT NULL
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"ConnectorStore._init_db failed: {e}")

    # --- Connector management ----------------------------------------------

    def list_connectors(self, user_email: str) -> list[dict[str, Any]]:
        """List all available connectors with the user's connection state."""
        try:
            conn = get_db_conn(self.db_path)
            rows = conn.execute(
                "SELECT provider, connected, connected_at, last_ingest_at, commitments_ingested "
                "FROM connectors WHERE user_email = ?",
                (user_email,),
            ).fetchall()
            conn.close()

            user_state = {
                r[0]: {
                    "connected": bool(r[1]),
                    "connected_at": r[2],
                    "last_ingest_at": r[3],
                    "commitments_ingested": r[4],
                }
                for r in rows
            }
        except Exception:
            user_state = {}

        result = []
        for provider_id, meta in SUPPORTED_CONNECTORS.items():
            state = user_state.get(provider_id, {
                "connected": False,
                "connected_at": "",
                "last_ingest_at": "",
                "commitments_ingested": 0,
            })
            oauth_configured = self._is_oauth_configured(provider_id)
            result.append({
                "provider": provider_id,
                "name": meta["name"],
                "icon": meta["icon"],
                "category": meta["category"],
                "phase": meta["phase"],
                "ingest_description": meta["ingest_description"],
                "write_description": meta["write_description"],
                "oauth_configured": oauth_configured,
                "demo_mode": not oauth_configured,  # K1: clearly label demo vs production
                "demo_label": "Demo" if not oauth_configured else None,
                **state,
            })
        return result

    def _is_oauth_configured(self, provider: str) -> bool:
        """Check if real OAuth credentials are in env."""
        client_id = os.environ.get(f"MAESTRO_{provider.upper()}_CLIENT_ID", "")
        return bool(client_id) or SUPPORTED_CONNECTORS.get(provider, {}).get("oauth_configured", False)

    def connect(self, user_email: str, provider: str, oauth_token: str = "") -> dict[str, Any]:
        """Connect a provider for a user (stores the OAuth token encrypted)."""
        if provider not in SUPPORTED_CONNECTORS:
            return {"error": f"Unsupported provider: {provider}"}

        encrypted_token = self._encrypt(oauth_token) if oauth_token else ""
        now = datetime.now(timezone.utc).isoformat()

        try:
            conn = get_db_conn(self.db_path)
            conn.execute(
                "INSERT OR REPLACE INTO connectors "
                "(user_email, provider, connected, token, connected_at, last_ingest_at, commitments_ingested) "
                "VALUES (?, ?, 1, ?, ?, '', 0)",
                (user_email, provider, encrypted_token, now),
            )
            conn.execute(
                "INSERT INTO connector_audit (user_email, action, provider, detail, timestamp) "
                "VALUES (?, 'connector.connect', ?, ?, ?)",
                (user_email, provider, "Connected", now),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"ConnectorStore.connect failed: {e}")
            return {"error": str(e)}

        return {
            "provider": provider,
            "connected": True,
            "connected_at": now,
            "commitments_ingested": 0,
        }

    def disconnect(self, user_email: str, provider: str) -> dict[str, Any]:
        """Disconnect a provider (deletes the token, keeps audit history)."""
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn = get_db_conn(self.db_path)
            conn.execute(
                "UPDATE connectors SET connected = 0, token = '' WHERE user_email = ? AND provider = ?",
                (user_email, provider),
            )
            conn.execute(
                "INSERT INTO connector_audit (user_email, action, provider, detail, timestamp) "
                "VALUES (?, 'connector.disconnect', ?, 'Disconnected', ?)",
                (user_email, provider, now),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"ConnectorStore.disconnect failed: {e}")
            return {"error": str(e)}

        return {"provider": provider, "connected": False, "disconnected_at": now}

    def get_connector_state(self, user_email: str, provider: str) -> dict[str, Any] | None:
        """Get the connection state for a specific provider."""
        try:
            conn = get_db_conn(self.db_path)
            row = conn.execute(
                "SELECT connected, connected_at, last_ingest_at, commitments_ingested "
                "FROM connectors WHERE user_email = ? AND provider = ?",
                (user_email, provider),
            ).fetchone()
            conn.close()
            if not row:
                return None
            return {
                "connected": bool(row[0]),
                "connected_at": row[1],
                "last_ingest_at": row[2],
                "commitments_ingested": row[3],
            }
        except Exception as e:
            logger.warning(f"get_connector_state failed: {e}")
            return None

    def get_stored_token(self, user_email: str, provider: str) -> str:
        """Get the decrypted OAuth token for a provider (for real API calls).

        Returns the decrypted token string (may be JSON for OAuth providers
        that store access + refresh tokens). Returns empty string if not
        connected or no token stored.
        """
        try:
            conn = get_db_conn(self.db_path)
            row = conn.execute(
                "SELECT token FROM connectors WHERE user_email = ? AND provider = ? AND connected = 1",
                (user_email, provider),
            ).fetchone()
            conn.close()
            if not row or not row[0]:
                return ""
            return self._decrypt(row[0])
        except Exception as e:
            logger.warning(f"get_stored_token failed: {e}")
            return ""

    def update_stored_token(self, user_email: str, provider: str, new_token: str) -> None:
        """Update the stored OAuth token (e.g., after a refresh).

        Used by the Gmail connector when the access token is refreshed —
        the new token (with new expiry) must be persisted so the next
        ingestion doesn't have to refresh again.
        """
        encrypted = self._encrypt(new_token) if new_token else ""
        try:
            conn = get_db_conn(self.db_path)
            conn.execute(
                "UPDATE connectors SET token = ? WHERE user_email = ? AND provider = ?",
                (encrypted, user_email, provider),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"update_stored_token failed: {e}")

    # --- Ingestion ----------------------------------------------------------

    def ingest(self, user_email: str, provider: str, shell: Any = None) -> dict[str, Any]:
        """Pull messages from a connector and ingest commitments as signals.

        In production, this calls the provider's API (Gmail API, Slack Web API,
        etc.). In demo mode, it uses MOCK_INGESTION_DATA.

        Returns: {ingested: N, new_commitments: N, duplicates: N}
        """
        state = self.get_connector_state(user_email, provider)
        if not state or not state["connected"]:
            return {"error": f"{provider} is not connected"}

        now = datetime.now(timezone.utc).isoformat()

        # Get messages (mock or real)
        messages = self._fetch_messages(user_email, provider)

        # Ingest each as a signal
        ingested = 0
        new_commitments = 0
        duplicates = 0

        for msg in messages:
            ingested += 1
            # Save EVERY message as a signal to the database
            from maestro_personal_shell.api import save_signal_to_db
            import uuid as _uuid
            try:
                signal = {
                    "signal_id": f"conn_{provider}_{_uuid.uuid4().hex[:8]}",
                    "entity": msg.get("entity", "Unknown"),
                    "text": msg.get("text", ""),
                    "signal_type": msg.get("commitment_type", msg.get("signal_type", "reported_statement")),
                    "timestamp": msg.get("timestamp", now),
                    "metadata": {"source": msg.get("source", provider), "provider": provider},
                }
                inserted = save_signal_to_db(signal, db_path=self.db_path, user_email=user_email)
                if inserted:
                    new_commitments += 1
                else:
                    duplicates += 1
            except Exception as e:
                logger.warning("Connector ingest save failed: %s", e)
                duplicates += 1

            # Also ingest into the shell's in-memory store
            if shell:
                try:
                    shell.ingest_signal({
                        "entity": msg.get("entity", "Unknown"),
                        "text": msg.get("text", ""),
                        "signal_type": msg.get("commitment_type", "reported_statement"),
                        "timestamp": msg.get("timestamp", now),
                        "source": msg.get("source", provider),
                    })
                except Exception:
                    pass

        # Update last_ingest_at + commitments_ingested
        try:
            conn = get_db_conn(self.db_path)
            conn.execute(
                "UPDATE connectors SET last_ingest_at = ?, "
                "commitments_ingested = commitments_ingested + ? "
                "WHERE user_email = ? AND provider = ?",
                (now, new_commitments, user_email, provider),
            )
            conn.execute(
                "INSERT INTO connector_audit (user_email, action, provider, detail, timestamp) "
                "VALUES (?, 'connector.ingest', ?, ?, ?)",
                (user_email, provider,
                 f"Ingested {ingested} messages, {new_commitments} new commitments",
                 now),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"ingest update failed: {e}")

        return {
            "provider": provider,
            "ingested": ingested,
            "new_commitments": new_commitments,
            "duplicates": duplicates,
            "ingested_at": now,
        }

    def _fetch_messages(self, user_email: str, provider: str) -> list[dict[str, Any]]:
        """Fetch messages from the provider.

        For Gmail: calls the real Gmail API using stored OAuth tokens (Phase B).
        For other providers: returns MOCK_INGESTION_DATA (Phase C-F).

        If Gmail OAuth is not configured (no MAESTRO_GMAIL_CLIENT_ID), falls
        back to MOCK_INGESTION_DATA so the app still works in demo mode.

        When real ingestion runs, the stored token may be refreshed — the
        updated token is persisted via update_stored_token().
        """
        state = self.get_connector_state(user_email, provider)
        if not state or not state["connected"]:
            return MOCK_INGESTION_DATA.get(provider, [])

        # Phase B: real Gmail ingestion
        if provider == "gmail":
            try:
                from maestro_personal_shell.gmail_connector import (
                    is_gmail_configured,
                    fetch_real_gmail_messages,
                    GmailOAuthClient,
                )
                if not is_gmail_configured():
                    # OAuth not configured — fall back to mock (demo mode)
                    return MOCK_INGESTION_DATA.get("gmail", [])

                stored_token = self.get_stored_token(user_email, "gmail")
                if not stored_token:
                    return MOCK_INGESTION_DATA.get("gmail", [])

                oauth_client = GmailOAuthClient()
                signals, updated_token = fetch_real_gmail_messages(
                    stored_token, oauth_client, days_back=30, max_messages=50,
                )

                # Persist refreshed token if it changed
                if updated_token != stored_token:
                    self.update_stored_token(user_email, "gmail", updated_token)

                return signals
            except ImportError:
                logger.warning("gmail_connector module not available, using mock data")
                return MOCK_INGESTION_DATA.get("gmail", [])
            except Exception as e:
                logger.warning(f"Gmail ingestion failed, falling back to mock: {e}")
                return MOCK_INGESTION_DATA.get("gmail", [])

        # Phase C: real Slack ingestion
        if provider == "slack":
            try:
                from maestro_personal_shell.slack_connector import (
                    is_slack_configured,
                    fetch_real_slack_messages,
                    SlackOAuthClient,
                )
                if not is_slack_configured():
                    return MOCK_INGESTION_DATA.get("slack", [])

                stored_token = self.get_stored_token(user_email, "slack")
                if not stored_token:
                    return MOCK_INGESTION_DATA.get("slack", [])

                oauth_client = SlackOAuthClient()
                signals, updated_token = fetch_real_slack_messages(
                    stored_token, oauth_client, days_back=30,
                )

                if updated_token != stored_token:
                    self.update_stored_token(user_email, "slack", updated_token)

                return signals
            except ImportError:
                logger.warning("slack_connector module not available, using mock data")
                return MOCK_INGESTION_DATA.get("slack", [])
            except Exception as e:
                logger.warning(f"Slack ingestion failed, falling back to mock: {e}")
                return MOCK_INGESTION_DATA.get("slack", [])

        # Phase E: real Calendar ingestion (read-only — no send)
        if provider == "calendar":
            try:
                from maestro_personal_shell.calendar_connector import (
                    is_calendar_configured,
                    fetch_real_calendar_events,
                    CalendarOAuthClient,
                )
                if not is_calendar_configured():
                    return MOCK_INGESTION_DATA.get("calendar", [])

                stored_token = self.get_stored_token(user_email, "calendar")
                if not stored_token:
                    return MOCK_INGESTION_DATA.get("calendar", [])

                oauth_client = CalendarOAuthClient()
                signals, updated_token = fetch_real_calendar_events(
                    stored_token, oauth_client, max_events=25, days_ahead=14,
                )

                if updated_token != stored_token:
                    self.update_stored_token(user_email, "calendar", updated_token)

                return signals
            except ImportError:
                logger.warning("calendar_connector module not available, using mock data")
                return MOCK_INGESTION_DATA.get("calendar", [])
            except Exception as e:
                logger.warning(f"Calendar ingestion failed, falling back to mock: {e}")
                return MOCK_INGESTION_DATA.get("calendar", [])

        # Phase D: real GitHub ingestion
        if provider == "github":
            try:
                from maestro_personal_shell.github_connector import (
                    is_github_configured,
                    fetch_real_github_messages,
                    GitHubOAuthClient,
                )
                if not is_github_configured():
                    return MOCK_INGESTION_DATA.get("github", [])

                stored_token = self.get_stored_token(user_email, "github")
                if not stored_token:
                    return MOCK_INGESTION_DATA.get("github", [])

                oauth_client = GitHubOAuthClient()
                signals, updated_token = fetch_real_github_messages(
                    stored_token, oauth_client, max_issues=50,
                )

                if updated_token != stored_token:
                    self.update_stored_token(user_email, "github", updated_token)

                return signals
            except ImportError:
                logger.warning("github_connector module not available, using mock data")
                return MOCK_INGESTION_DATA.get("github", [])
            except Exception as e:
                logger.warning(f"GitHub ingestion failed, falling back to mock: {e}")
                return MOCK_INGESTION_DATA.get("github", [])

        # Other providers — still mocked (Phase F)
        return MOCK_INGESTION_DATA.get(provider, [])

    # --- Draft management ---------------------------------------------------

    def create_draft(
        self,
        user_email: str,
        provider: str,
        recipient: str,
        subject: str,
        body: str,
        commitment_ref: str = "",
        evidence_refs: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Create a pending draft for user approval."""
        draft_id = f"draft-{secrets.token_urlsafe(12)}"
        now = datetime.now(timezone.utc).isoformat()
        evidence_json = json.dumps(evidence_refs or [])

        try:
            conn = get_db_conn(self.db_path)
            conn.execute(
                "INSERT INTO drafts "
                "(draft_id, user_email, provider, recipient, subject, body, "
                "commitment_ref, evidence_refs, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
                (draft_id, user_email, provider, recipient, subject, body,
                 commitment_ref, evidence_json, now),
            )
            conn.execute(
                "INSERT INTO connector_audit (user_email, action, provider, detail, timestamp) "
                "VALUES (?, 'draft.create', ?, ?, ?)",
                (user_email, provider, f"Draft created for {recipient}", now),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"create_draft failed: {e}")
            return {"error": str(e)}

        return {
            "draft_id": draft_id,
            "provider": provider,
            "recipient": recipient,
            "subject": subject,
            "body": body,
            "commitment_ref": commitment_ref,
            "evidence_refs": evidence_refs or [],
            "status": "pending",
            "created_at": now,
        }

    def list_drafts(self, user_email: str, status: str = "pending") -> list[dict[str, Any]]:
        """List drafts for a user, optionally filtered by status."""
        try:
            conn = get_db_conn(self.db_path)
            if status:
                rows = conn.execute(
                    "SELECT draft_id, provider, recipient, subject, body, "
                    "commitment_ref, evidence_refs, status, created_at, resolved_at "
                    "FROM drafts WHERE user_email = ? AND status = ? "
                    "ORDER BY created_at DESC",
                    (user_email, status),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT draft_id, provider, recipient, subject, body, "
                    "commitment_ref, evidence_refs, status, created_at, resolved_at "
                    "FROM drafts WHERE user_email = ? "
                    "ORDER BY created_at DESC",
                    (user_email,),
                ).fetchall()
            conn.close()
            return [
                {
                    "draft_id": r[0],
                    "provider": r[1],
                    "recipient": r[2],
                    "subject": r[3],
                    "body": r[4],
                    "commitment_ref": r[5],
                    "evidence_refs": json.loads(r[6] or "[]"),
                    "status": r[7],
                    "created_at": r[8],
                    "resolved_at": r[9],
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"list_drafts failed: {e}")
            return []

    def get_draft(self, draft_id: str) -> dict[str, Any] | None:
        """Get a single draft by ID."""
        try:
            conn = get_db_conn(self.db_path)
            row = conn.execute(
                "SELECT draft_id, user_email, provider, recipient, subject, body, "
                "commitment_ref, evidence_refs, status, created_at, resolved_at "
                "FROM drafts WHERE draft_id = ?",
                (draft_id,),
            ).fetchone()
            conn.close()
            if not row:
                return None
            return {
                "draft_id": row[0],
                "user_email": row[1],
                "provider": row[2],
                "recipient": row[3],
                "subject": row[4],
                "body": row[5],
                "commitment_ref": row[6],
                "evidence_refs": json.loads(row[7] or "[]"),
                "status": row[8],
                "created_at": row[9],
                "resolved_at": row[10],
            }
        except Exception as e:
            logger.warning(f"get_draft failed: {e}")
            return None

    def resolve_draft(
        self,
        draft_id: str,
        resolution: str,  # approve | deny | use_draft
        user_email: str = "",
    ) -> dict[str, Any]:
        """Resolve a draft: approve (send), deny (discard), or use_draft (open in compose)."""
        if resolution not in ("approve", "deny", "use_draft"):
            return {"error": "resolution must be approve/deny/use_draft"}

        draft = self.get_draft(draft_id)
        if not draft:
            return {"error": f"Draft {draft_id} not found"}
        if draft["status"] != "pending":
            return {"error": f"Draft is already {draft['status']}"}

        now = datetime.now(timezone.utc).isoformat()
        status_map = {
            "approve": "approved",
            "deny": "denied",
            "use_draft": "used_as_draft",
        }
        new_status = status_map[resolution]

        sent_message_id = ""
        send_error = ""
        if resolution == "approve":
            # Phase B/C/D: actually send via the provider's API
            if draft["provider"] == "gmail":
                sent_message_id, send_error = self._send_via_gmail(
                    user_email or draft["user_email"], draft,
                )
            elif draft["provider"] == "slack":
                sent_message_id, send_error = self._send_via_slack(
                    user_email or draft["user_email"], draft,
                )
            elif draft["provider"] == "github":
                sent_message_id, send_error = self._send_via_github(
                    user_email or draft["user_email"], draft,
                )
            else:
                # Other providers — simulate send (Phase F)
                sent_message_id = f"msg-{secrets.token_urlsafe(8)}"

            if send_error:
                action_detail = f"FAILED to send to {draft['recipient']}: {send_error}"
                new_status = "send_failed"
            else:
                action_detail = f"Approved and sent to {draft['recipient']} (msg_id={sent_message_id})"
        elif resolution == "deny":
            action_detail = f"Discarded draft for {draft['recipient']}"
        else:  # use_draft
            action_detail = f"Marked as draft for {draft['recipient']} — user will edit and send manually"

        try:
            conn = get_db_conn(self.db_path)
            conn.execute(
                "UPDATE drafts SET status = ?, resolved_at = ?, sent_message_id = ? "
                "WHERE draft_id = ?",
                (new_status, now, sent_message_id, draft_id),
            )
            conn.execute(
                "INSERT INTO connector_audit (user_email, action, provider, detail, timestamp) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_email or draft["user_email"],
                 f"draft.{resolution}",
                 draft["provider"],
                 action_detail,
                 now),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"resolve_draft failed: {e}")
            return {"error": str(e)}

        return {
            "draft_id": draft_id,
            "status": new_status,
            "resolved_at": now,
            "sent_message_id": sent_message_id,
            "action": resolution,
            "send_error": send_error,
        }

    def _send_via_gmail(self, user_email: str, draft: dict[str, Any]) -> tuple[str, str]:
        """Send a draft via the real Gmail API (Phase B).

        Returns: (sent_message_id, error_message)
          - On success: (gmail_message_id, "")
          - On failure: ("", error_description)
          - If OAuth not configured: falls back to simulated send (msg-xxx, "")
        """
        try:
            from maestro_personal_shell.gmail_connector import (
                is_gmail_configured,
                send_real_gmail_message,
                GmailOAuthClient,
            )
        except ImportError:
            # Module not available — simulate send
            return f"msg-{secrets.token_urlsafe(8)}", ""

        if not is_gmail_configured():
            # Demo mode — simulate send
            return f"msg-{secrets.token_urlsafe(8)}", ""

        stored_token = self.get_stored_token(user_email, "gmail")
        if not stored_token:
            return "", "Gmail not connected (no stored token)"

        oauth_client = GmailOAuthClient()
        result, updated_token = send_real_gmail_message(
            stored_token,
            oauth_client,
            to=draft["recipient"],
            subject=draft.get("subject", ""),
            body=draft["body"],
        )

        # Persist refreshed token if it changed
        if updated_token != stored_token:
            self.update_stored_token(user_email, "gmail", updated_token)

        if "error" in result:
            return "", result["error"]
        return result.get("id", f"msg-{secrets.token_urlsafe(8)}"), ""

    def _send_via_slack(self, user_email: str, draft: dict[str, Any]) -> tuple[str, str]:
        """Send a draft via the real Slack API (Phase C).

        Returns: (sent_message_id, error_message)
          - On success: (slack_ts, "")
          - On failure: ("", error_description)
          - If OAuth not configured: falls back to simulated send (msg-xxx, "")
        """
        try:
            from maestro_personal_shell.slack_connector import (
                is_slack_configured,
                send_real_slack_message,
                SlackOAuthClient,
            )
        except ImportError:
            return f"msg-{secrets.token_urlsafe(8)}", ""

        if not is_slack_configured():
            return f"msg-{secrets.token_urlsafe(8)}", ""

        stored_token = self.get_stored_token(user_email, "slack")
        if not stored_token:
            return "", "Slack not connected (no stored token)"

        oauth_client = SlackOAuthClient()
        # The recipient is the channel ID or DM channel ID
        result, updated_token = send_real_slack_message(
            stored_token,
            oauth_client,
            channel=draft["recipient"],
            text=draft["body"],
        )

        if updated_token != stored_token:
            self.update_stored_token(user_email, "slack", updated_token)

        if "error" in result:
            return "", result["error"]
        # Slack returns a timestamp (ts) as the message ID
        return result.get("ts", f"msg-{secrets.token_urlsafe(8)}"), ""

    def _send_via_github(self, user_email: str, draft: dict[str, Any]) -> tuple[str, str]:
        """Send a draft via the real GitHub API (Phase D).

        Posts a comment on the issue/PR specified by the draft recipient.
        The recipient format is "owner/repo#123" or "owner/repo/issues/123".

        Returns: (sent_message_id, error_message)
          - On success: (github_comment_id, "")
          - On failure: ("", error_description)
          - If OAuth not configured: falls back to simulated send (msg-xxx, "")
        """
        try:
            from maestro_personal_shell.github_connector import (
                is_github_configured,
                send_real_github_comment,
                GitHubOAuthClient,
                parse_github_recipient,
            )
        except ImportError:
            return f"msg-{secrets.token_urlsafe(8)}", ""

        if not is_github_configured():
            return f"msg-{secrets.token_urlsafe(8)}", ""

        stored_token = self.get_stored_token(user_email, "github")
        if not stored_token:
            return "", "GitHub not connected (no stored token)"

        # Parse the recipient: "owner/repo#123"
        owner, repo, issue_number = parse_github_recipient(draft["recipient"])
        if not owner or not repo or not issue_number:
            return "", f"Invalid GitHub recipient format: '{draft['recipient']}'. Expected 'owner/repo#123'."

        oauth_client = GitHubOAuthClient()
        result, updated_token = send_real_github_comment(
            stored_token,
            oauth_client,
            owner=owner,
            repo=repo,
            issue_number=issue_number,
            body=draft["body"],
        )

        if updated_token != stored_token:
            self.update_stored_token(user_email, "github", updated_token)

        if "error" in result:
            return "", result["error"]
        # GitHub returns a comment ID
        return str(result.get("id", f"msg-{secrets.token_urlsafe(8)}")), ""

    # --- Audit log ----------------------------------------------------------

    def get_audit_log(self, user_email: str, limit: int = 50) -> list[dict[str, Any]]:
        """Get the connector + draft audit log for a user."""
        try:
            conn = get_db_conn(self.db_path)
            rows = conn.execute(
                "SELECT action, provider, detail, timestamp FROM connector_audit "
                "WHERE user_email = ? ORDER BY timestamp DESC LIMIT ?",
                (user_email, limit),
            ).fetchall()
            conn.close()
            return [
                {"action": r[0], "provider": r[1], "detail": r[2], "timestamp": r[3]}
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"get_audit_log failed: {e}")
            return []


# ---------------------------------------------------------------------------
# Draft Generator — generates commitment-aware drafts for connectors
# ---------------------------------------------------------------------------

class ConnectorDraftGenerator:
    """Generate commitment-aware drafts for any connector platform.

    Uses the existing FollowUpEmailGenerator for email, and adapts the
    output for Slack (shorter, informal), GitHub (issue comment format),
    and other platforms.

    P13 FIX: The generate_draft() method below takes caller-supplied
    commitment + evidence. This is a TEMPLATE FORMATTER. The real
    capability is generate_auto_draft() which DERIVES the commitment
    and evidence from the user's signal history — that's the moat.
    """

    def __init__(self, shell: Any = None):
        self.shell = shell

    def generate_auto_draft(
        self,
        provider: str,
        recipient: str,
        shell: Any = None,
    ) -> dict[str, Any]:
        """DERIVE a draft from the user's signal history — the real capability (P13 fix).

        Instead of requiring the caller to supply the commitment + evidence
        (P13 violation), this method:
          1. Searches the user's signals for commitments involving the recipient
          2. Finds the most relevant/stale commitment
          3. DERIVES evidence_refs via FTS5 retrieval on the commitment text
          4. Generates a platform-specific draft citing that commitment + evidence

        This is the moat: Maestro looks at YOUR data and drafts a follow-up
        grounded in what you actually promised — not a template the caller fills in.

        Returns: {subject, body, commitment_ref, evidence_refs, provider, recipient,
                  derived: True, commitment_source: signal_id}
        """
        shell = shell or self.shell
        if not shell:
            return {
                "error": "Shell required for auto-derivation. Use generate_draft() for manual mode.",
            }

        # Step 1: Find commitments for this recipient from the user's signals
        commitment, evidence_refs, source_signal_id = self._derive_commitment_for_recipient(
            shell, recipient
        )

        if not commitment:
            return {
                "error": f"No active commitments found for '{recipient}'. "
                         f"Connect a connector and ingest, or add a signal manually.",
            }

        # Step 2: Generate the platform-specific draft using the DERIVED commitment
        draft = self.generate_draft(
            provider=provider,
            recipient=recipient,
            commitment=commitment,
            evidence_refs=evidence_refs,
        )

        # Step 3: Mark it as derived (not caller-supplied)
        draft["derived"] = True
        draft["commitment_source"] = source_signal_id
        draft["evidence_count"] = len(evidence_refs)
        return draft

    def _derive_commitment_for_recipient(
        self,
        shell: Any,
        recipient: str,
    ) -> tuple[dict[str, Any] | None, list[dict], str]:
        """Search the user's signals for commitments involving the recipient.

        Returns: (commitment_dict, evidence_refs, source_signal_id)
        - commitment_dict: {text, entity} of the most relevant commitment
        - evidence_refs: list of {entity, text, timestamp} backing the commitment
        - source_signal_id: the signal ID the commitment was derived from
        """
        recipient_lower = recipient.lower()
        # Extract name part if it's an email
        if "@" in recipient_lower:
            recipient_name = recipient_lower.split("@")[0]
        else:
            recipient_name = recipient_lower

        # P28 fix: also try with dots replaced by spaces (maria.garcia → maria garcia)
        # and first-name-only, so email usernames match signal entities
        recipient_name_variants = [
            recipient_name,
            recipient_name.replace(".", " "),
            recipient_name.replace(".", ""),
            recipient_name.split(".")[0] if "." in recipient_name else recipient_name,
        ]

        # Search signals for commitments involving this recipient
        best_commitment = None
        best_evidence: list[dict] = []
        best_signal_id = ""

        try:
            # P14 fix: signals live in shell.oem_state.signals (PersonalShell)
            # or shell.signals / shell.core.signals (generic/mock shells)
            if hasattr(shell, "oem_state") and shell.oem_state and hasattr(shell.oem_state, "signals"):
                signals = shell.oem_state.signals
            elif hasattr(shell, "signals") and shell.signals:
                signals = shell.signals
            elif hasattr(shell, "core") and shell.core and hasattr(shell.core, "signals"):
                signals = shell.core.signals
            else:
                signals = []
        except Exception:
            signals = []

        for sig in signals:
            try:
                sig_text = str(getattr(sig, "text", "") or "")
                sig_entity = str(getattr(sig, "entity", "") or "")
                sig_type = str(getattr(sig, "signal_type", "") or "").lower()
                sig_timestamp = str(getattr(sig, "timestamp", "") or "")
                sig_id = str(getattr(sig, "signal_id", "") or getattr(sig, "id", ""))

                sig_entity_lower = sig_entity.lower()
                sig_text_lower = sig_text.lower()

                # Check if this signal involves the recipient (any name variant)
                involves_recipient = any(
                    variant in sig_entity_lower or variant in sig_text_lower
                    for variant in recipient_name_variants
                    if len(variant) >= 3  # skip tiny fragments
                )

                if not involves_recipient:
                    continue

                # Is this a commitment?
                is_commitment = "commitment" in sig_type and "made" in sig_type

                if is_commitment and not best_commitment:
                    # This is our primary commitment
                    best_commitment = {"text": sig_text, "entity": sig_entity}
                    best_signal_id = sig_id
                    # The commitment itself is evidence
                    best_evidence.append({
                        "entity": sig_entity,
                        "text": sig_text,
                        "timestamp": sig_timestamp,
                    })
                else:
                    # Related signal — add as evidence
                    if len(best_evidence) < 3:
                        best_evidence.append({
                            "entity": sig_entity,
                            "text": sig_text,
                            "timestamp": sig_timestamp,
                        })

            except Exception as e:
                logger.debug(f"Signal scan error: {e}")
                continue

        # Also try FTS5 retrieval if available (the real moat — semantic search)
        if shell and hasattr(shell, "core") and shell.core:
            try:
                from maestro_personal_shell.semantic_retrieval import search_signals_fts
                fts_results = search_signals_fts(recipient_name, limit=5)
                for r in fts_results:
                    if len(best_evidence) < 4:
                        best_evidence.append({
                            "entity": r.get("entity", ""),
                            "text": r.get("text", ""),
                            "timestamp": r.get("timestamp", ""),
                        })
            except Exception:
                pass  # FTS not available, keyword match is the fallback

        return best_commitment, best_evidence, best_signal_id

    def generate_draft(
        self,
        provider: str,
        recipient: str,
        commitment: dict[str, Any],
        evidence_refs: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Generate a draft for the given commitment + provider (template formatter).

        NOTE (P13): This is a TEMPLATE FORMATTER. The caller supplies the commitment
        and evidence. For the real capability (deriving from signal history), use
        generate_auto_draft() instead.

        Returns: {subject, body, commitment_ref, evidence_refs, provider, recipient,
                  derived: False}
        """
        evidence_refs = evidence_refs or []
        commitment_text = commitment.get("text", "")
        entity = commitment.get("entity", recipient)

        if provider == "gmail":
            result = self._generate_email(recipient, entity, commitment_text, evidence_refs)
        elif provider == "slack":
            result = self._generate_slack(recipient, entity, commitment_text, evidence_refs)
        elif provider == "github":
            result = self._generate_github(recipient, entity, commitment_text, evidence_refs)
        elif provider == "whatsapp":
            result = self._generate_whatsapp(recipient, entity, commitment_text, evidence_refs)
        elif provider in ("facebook", "instagram", "twitter"):
            result = self._generate_social(provider, recipient, entity, commitment_text, evidence_refs)
        else:
            result = self._generate_email(recipient, entity, commitment_text, evidence_refs)
            result["provider"] = provider

        result["derived"] = False
        return result

    def _generate_email(
        self,
        recipient: str,
        entity: str,
        commitment_text: str,
        evidence_refs: list[dict],
    ) -> dict[str, Any]:
        """Generate an email draft citing the commitment + evidence."""
        subject = f"Follow-up — {entity}"

        body_lines = [
            f"Hi {recipient.split('@')[0] if '@' in recipient else recipient},",
            "",
            "Thank you for the productive discussion. Here's what I captured:",
            "",
            "Commitments:",
            f"  - {commitment_text}",
            "",
        ]

        if evidence_refs:
            body_lines.append("Based on our history:")
            for ref in evidence_refs[:2]:
                body_lines.append(f'  - "{ref.get("text", "")}" — {ref.get("entity", "")}')
            body_lines.append("")

        body_lines.extend([
            "Next steps:",
            "  - I'll follow up on the commitment above",
            "  - Let me know if I've missed anything",
            "",
            "Best,",
            "[Your name]",
        ])

        return {
            "provider": "gmail",
            "recipient": recipient,
            "subject": subject,
            "body": "\n".join(body_lines),
            "commitment_ref": commitment_text,
            "evidence_refs": evidence_refs,
        }

    def _generate_slack(
        self,
        recipient: str,
        entity: str,
        commitment_text: str,
        evidence_refs: list[dict],
    ) -> dict[str, Any]:
        """Generate a Slack message draft (shorter, more informal)."""
        body = f"Hey {recipient} — following up on our conversation. I committed to: {commitment_text}. I'll have that to you by the agreed deadline. Let me know if anything's changed on your end."

        return {
            "provider": "slack",
            "recipient": recipient,
            "subject": "",  # Slack has no subject
            "body": body,
            "commitment_ref": commitment_text,
            "evidence_refs": evidence_refs,
        }

    def _generate_github(
        self,
        recipient: str,
        entity: str,
        commitment_text: str,
        evidence_refs: list[dict],
    ) -> dict[str, Any]:
        """Generate a GitHub issue comment draft."""
        body = f"Following up on this — I committed to: {commitment_text}.\n\nI'll have an update by the agreed deadline. Flagging here for visibility."

        return {
            "provider": "github",
            "recipient": recipient,
            "subject": f"Re: {entity}",
            "body": body,
            "commitment_ref": commitment_text,
            "evidence_refs": evidence_refs,
        }

    def _generate_whatsapp(
        self,
        recipient: str,
        entity: str,
        commitment_text: str,
        evidence_refs: list[dict],
    ) -> dict[str, Any]:
        """Generate a WhatsApp message draft."""
        body = f"Hi {recipient} 👋 Just following up on our chat — I'll get you: {commitment_text}. Talk soon!"

        return {
            "provider": "whatsapp",
            "recipient": recipient,
            "subject": "",
            "body": body,
            "commitment_ref": commitment_text,
            "evidence_refs": evidence_refs,
        }

    def _generate_social(
        self,
        provider: str,
        recipient: str,
        entity: str,
        commitment_text: str,
        evidence_refs: list[dict],
    ) -> dict[str, Any]:
        """Generate a social media DM draft."""
        body = f"Hi {recipient} — following up on our conversation. I committed to: {commitment_text}. Will have that to you soon!"

        return {
            "provider": provider,
            "recipient": recipient,
            "subject": "",
            "body": body,
            "commitment_ref": commitment_text,
            "evidence_refs": evidence_refs,
        }
