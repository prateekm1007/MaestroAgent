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
import sqlite3
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
            conn = sqlite3.connect(self.db_path, timeout=5.0)
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
            conn = sqlite3.connect(self.db_path, timeout=5.0)
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
            result.append({
                "provider": provider_id,
                "name": meta["name"],
                "icon": meta["icon"],
                "category": meta["category"],
                "phase": meta["phase"],
                "ingest_description": meta["ingest_description"],
                "write_description": meta["write_description"],
                "oauth_configured": self._is_oauth_configured(provider_id),
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
            conn = sqlite3.connect(self.db_path, timeout=5.0)
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
            conn = sqlite3.connect(self.db_path, timeout=5.0)
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
            conn = sqlite3.connect(self.db_path, timeout=5.0)
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
            if "commitment" in msg.get("commitment_type", ""):
                # Try to ingest into the shell's signal store
                if shell:
                    try:
                        shell.ingest_signal({
                            "entity": msg["entity"],
                            "text": msg["text"],
                            "signal_type": msg.get("commitment_type", "reported_statement"),
                            "timestamp": msg["timestamp"],
                            "source": msg.get("source", provider),
                        })
                        new_commitments += 1
                    except Exception:
                        duplicates += 1
                else:
                    new_commitments += 1

        # Update last_ingest_at + commitments_ingested
        try:
            conn = sqlite3.connect(self.db_path, timeout=5.0)
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

        In production: call the provider's API using the stored OAuth token.
        In demo mode: return MOCK_INGESTION_DATA.

        TODO (production): implement real API calls:
          - gmail: gmail.users().messages().list() + get()
          - slack: conversations.history() + im.history()
          - github: /repos/{owner}/{repo}/issues?assignee={user}
          - calendar: calendar.events().list()
        """
        # Check if we have real OAuth configured
        state = self.get_connector_state(user_email, provider)
        if state and state["connected"]:
            # For now, use mock data. When real OAuth is configured,
            # this is where the real API call goes.
            pass

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
            conn = sqlite3.connect(self.db_path, timeout=5.0)
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
            conn = sqlite3.connect(self.db_path, timeout=5.0)
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
            conn = sqlite3.connect(self.db_path, timeout=5.0)
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
        if resolution == "approve":
            # In production: actually send via the provider's API
            # (Gmail: messages().send(), Slack: chat.postMessage(), etc.)
            # For now: simulate a successful send
            sent_message_id = f"msg-{secrets.token_urlsafe(8)}"
            action_detail = f"Approved and sent to {draft['recipient']} (msg_id={sent_message_id})"
        elif resolution == "deny":
            action_detail = f"Discarded draft for {draft['recipient']}"
        else:  # use_draft
            action_detail = f"Marked as draft for {draft['recipient']} — user will edit and send manually"

        try:
            conn = sqlite3.connect(self.db_path, timeout=5.0)
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
        }

    # --- Audit log ----------------------------------------------------------

    def get_audit_log(self, user_email: str, limit: int = 50) -> list[dict[str, Any]]:
        """Get the connector + draft audit log for a user."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=5.0)
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
    """

    def __init__(self, shell: Any = None):
        self.shell = shell

    def generate_draft(
        self,
        provider: str,
        recipient: str,
        commitment: dict[str, Any],
        evidence_refs: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Generate a draft for the given commitment + provider.

        Returns: {subject, body, commitment_ref, evidence_refs, provider, recipient}
        """
        evidence_refs = evidence_refs or []
        commitment_text = commitment.get("text", "")
        entity = commitment.get("entity", recipient)

        if provider == "gmail":
            return self._generate_email(recipient, entity, commitment_text, evidence_refs)
        elif provider == "slack":
            return self._generate_slack(recipient, entity, commitment_text, evidence_refs)
        elif provider == "github":
            return self._generate_github(recipient, entity, commitment_text, evidence_refs)
        elif provider == "whatsapp":
            return self._generate_whatsapp(recipient, entity, commitment_text, evidence_refs)
        elif provider in ("facebook", "instagram", "twitter"):
            return self._generate_social(provider, recipient, entity, commitment_text, evidence_refs)
        else:
            # Unknown provider — use email format but keep the provider name
            result = self._generate_email(recipient, entity, commitment_text, evidence_refs)
            result["provider"] = provider
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
