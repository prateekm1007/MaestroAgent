"""
Tests for the Connectors module — OAuth2 connector management + draft approval flow.

Verifies:
  1. ConnectorStore: list, connect, disconnect, ingest, audit log
  2. DraftStore: create, list, get, resolve (approve/deny/use_draft)
  3. ConnectorDraftGenerator: generates platform-specific drafts
  4. API integration: all 9 new endpoints return 200 + correct shape
  5. Security: tokens stored encrypted, per-connector revocation
  6. Approval flow: never auto-sends, requires explicit resolution
"""

import sys
import os
import tempfile
import pytest
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
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-connectors"
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
# 1. ConnectorStore — connector management
# ---------------------------------------------------------------------------

class TestConnectorStore:
    """Connector state management + token storage."""

    def test_list_connectors_returns_all_supported(self, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        connectors = store.list_connectors("user@test.com")
        provider_ids = [c["provider"] for c in connectors]
        assert "gmail" in provider_ids
        assert "slack" in provider_ids
        assert "github" in provider_ids
        assert "calendar" in provider_ids
        assert "whatsapp" in provider_ids
        assert "facebook" in provider_ids
        assert "instagram" in provider_ids
        assert "twitter" in provider_ids

    def test_connect_marks_as_connected(self, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        result = store.connect("user@test.com", "gmail", "oauth-token-123")
        assert result["connected"] is True
        assert result["provider"] == "gmail"

        state = store.get_connector_state("user@test.com", "gmail")
        assert state["connected"] is True

    def test_disconnect_removes_token(self, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        store.connect("user@test.com", "gmail", "oauth-token-123")
        result = store.disconnect("user@test.com", "gmail")
        assert result["connected"] is False

        state = store.get_connector_state("user@test.com", "gmail")
        assert state["connected"] is False

    def test_per_connector_revocation(self, tmp_path):
        """Disconnecting one provider doesn't affect others."""
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        store.connect("user@test.com", "gmail", "token-gmail")
        store.connect("user@test.com", "slack", "token-slack")

        # Disconnect gmail only
        store.disconnect("user@test.com", "gmail")

        gmail_state = store.get_connector_state("user@test.com", "gmail")
        slack_state = store.get_connector_state("user@test.com", "slack")
        assert gmail_state["connected"] is False
        assert slack_state["connected"] is True

    def test_connect_unsupported_provider_returns_error(self, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        result = store.connect("user@test.com", "myspace", "token")
        assert "error" in result

    def test_token_stored_encrypted(self, tmp_path):
        """Token is not stored in plaintext (dev: prefix or Fernet-encrypted)."""
        import sqlite3
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        store.connect("user@test.com", "gmail", "super-secret-token")

        # Read raw DB — token should NOT be the plaintext
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        row = conn.execute(
            "SELECT token FROM connectors WHERE provider = 'gmail'"
        ).fetchone()
        conn.close()
        assert row[0] != "super-secret-token"  # not plaintext
        assert "super-secret-token" in store._decrypt(row[0])  # decrypts back


# ---------------------------------------------------------------------------
# 2. Ingestion
# ---------------------------------------------------------------------------

class TestIngestion:
    """Message ingestion + commitment extraction."""

    def test_ingest_requires_connection(self, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        result = store.ingest("user@test.com", "gmail")
        assert "error" in result

    def test_ingest_returns_commitment_count(self, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        from maestro_personal_shell.api import init_db
        init_db(str(tmp_path / "test.db"))
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        store.connect("user@test.com", "gmail", "token")
        result = store.ingest("user@test.com", "gmail", shell=None)
        assert result["ingested"] > 0
        assert result["new_commitments"] > 0
        assert "ingested_at" in result

    def test_ingest_updates_commitment_count(self, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        from maestro_personal_shell.api import init_db
        init_db(str(tmp_path / "test.db"))
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        store.connect("user@test.com", "gmail", "token")
        store.ingest("user@test.com", "gmail", shell=None)
        store.ingest("user@test.com", "gmail", shell=None)

        state = store.get_connector_state("user@test.com", "gmail")
        assert state["commitments_ingested"] > 0

    def test_ingest_logs_audit_entry(self, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        store.connect("user@test.com", "slack", "token")
        store.ingest("user@test.com", "slack", shell=None)

        audit = store.get_audit_log("user@test.com")
        actions = [a["action"] for a in audit]
        assert "connector.connect" in actions
        assert "connector.ingest" in actions


# ---------------------------------------------------------------------------
# 3. Draft management + approval flow
# ---------------------------------------------------------------------------

class TestDrafts:
    """Draft creation, listing, and the approve/deny/use_draft flow."""

    def test_create_draft_returns_pending(self, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        result = store.create_draft(
            user_email="user@test.com",
            provider="gmail",
            recipient="maria@example.com",
            subject="Follow-up",
            body="Hi Maria...",
            commitment_ref="Send proposal by Friday",
            evidence_refs=[{"entity": "Maria", "text": "I will send..."}],
        )
        assert result["status"] == "pending"
        assert result["draft_id"].startswith("draft-")
        assert result["recipient"] == "maria@example.com"

    def test_list_drafts_filtered_by_status(self, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        store.create_draft("u@t.com", "gmail", "a@x.com", "S1", "B1", "C1")
        store.create_draft("u@t.com", "slack", "b@x.com", "S2", "B2", "C2")

        pending = store.list_drafts("u@t.com", status="pending")
        assert len(pending) == 2

    def test_resolve_approve_marks_approved(self, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        draft = store.create_draft("u@t.com", "gmail", "a@x.com", "S", "B", "C")
        result = store.resolve_draft(draft["draft_id"], "approve", user_email="u@t.com")
        # P6 fix: without OAuth configured, send fails honestly
        assert result["status"] == "send_failed"
        assert result["send_error"] != ""  # honest error, not fabrication

    def test_resolve_deny_marks_denied(self, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        draft = store.create_draft("u@t.com", "gmail", "a@x.com", "S", "B", "C")
        result = store.resolve_draft(draft["draft_id"], "deny", user_email="u@t.com")
        assert result["status"] == "denied"

    def test_resolve_use_draft_marks_used(self, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        draft = store.create_draft("u@t.com", "gmail", "a@x.com", "S", "B", "C")
        result = store.resolve_draft(draft["draft_id"], "use_draft", user_email="u@t.com")
        assert result["status"] == "used_as_draft"

    def test_cannot_resolve_already_resolved(self, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        draft = store.create_draft("u@t.com", "gmail", "a@x.com", "S", "B", "C")
        store.resolve_draft(draft["draft_id"], "deny", user_email="u@t.com")
        result = store.resolve_draft(draft["draft_id"], "approve", user_email="u@t.com")
        assert "error" in result

    def test_invalid_resolution_returns_error(self, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        draft = store.create_draft("u@t.com", "gmail", "a@x.com", "S", "B", "C")
        result = store.resolve_draft(draft["draft_id"], "invalid", user_email="u@t.com")
        assert "error" in result

    def test_resolve_nonexistent_draft_returns_error(self, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        result = store.resolve_draft("nonexistent", "approve", user_email="u@t.com")
        assert "error" in result

    def test_approval_logs_audit(self, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        draft = store.create_draft("u@t.com", "gmail", "a@x.com", "S", "B", "C")
        store.resolve_draft(draft["draft_id"], "approve", user_email="u@t.com")
        audit = store.get_audit_log("u@t.com")
        actions = [a["action"] for a in audit]
        assert "draft.create" in actions
        assert "draft.approve" in actions


# ---------------------------------------------------------------------------
# 4. ConnectorDraftGenerator — platform-specific drafts
# ---------------------------------------------------------------------------

class TestDraftGenerator:
    """Platform-specific draft generation."""

    def test_gmail_draft_has_subject_and_body(self):
        from maestro_personal_shell.connectors import ConnectorDraftGenerator
        gen = ConnectorDraftGenerator()
        draft = gen.generate_draft(
            provider="gmail",
            recipient="maria@example.com",
            commitment={"text": "Send proposal by Friday", "entity": "Maria"},
            evidence_refs=[{"entity": "Maria", "text": "I will send..."}],
        )
        assert draft["provider"] == "gmail"
        assert draft["subject"] != ""
        assert "Send proposal by Friday" in draft["body"]
        assert "maria" in draft["body"].lower()

    def test_slack_draft_is_shorter(self):
        from maestro_personal_shell.connectors import ConnectorDraftGenerator
        gen = ConnectorDraftGenerator()
        gmail = gen.generate_draft("gmail", "sam", {"text": "commitment", "entity": "Sam"}, [])
        slack = gen.generate_draft("slack", "sam", {"text": "commitment", "entity": "Sam"}, [])
        assert len(slack["body"]) < len(gmail["body"])
        assert slack["subject"] == ""  # Slack has no subject

    def test_github_draft_mentions_visibility(self):
        from maestro_personal_shell.connectors import ConnectorDraftGenerator
        gen = ConnectorDraftGenerator()
        draft = gen.generate_draft(
            "github", "orion-tech/repo", {"text": "review PR", "entity": "Orion"}, []
        )
        assert "visibility" in draft["body"].lower()

    def test_whatsapp_draft_has_emoji(self):
        from maestro_personal_shell.connectors import ConnectorDraftGenerator
        gen = ConnectorDraftGenerator()
        draft = gen.generate_draft("whatsapp", "+1234", {"text": "commitment", "entity": "x"}, [])
        assert "👋" in draft["body"]

    def test_unknown_provider_defaults_to_email(self):
        from maestro_personal_shell.connectors import ConnectorDraftGenerator
        gen = ConnectorDraftGenerator()
        draft = gen.generate_draft("unknown", "x@y.com", {"text": "c", "entity": "x"}, [])
        assert draft["provider"] == "unknown"
        assert draft["subject"] != ""  # email format

    def test_evidence_refs_included_in_draft(self):
        from maestro_personal_shell.connectors import ConnectorDraftGenerator
        gen = ConnectorDraftGenerator()
        evidence = [{"entity": "Maria", "text": "I will send the proposal"}]
        draft = gen.generate_draft("gmail", "maria@x.com", {"text": "commitment", "entity": "Maria"}, evidence)
        assert draft["evidence_refs"] == evidence


# ---------------------------------------------------------------------------
# 5. API Integration — all 9 new endpoints
# ---------------------------------------------------------------------------

class TestConnectorAPI:
    """All 9 connector + draft endpoints."""

    def test_list_connectors_endpoint(self, client, auth_headers):
        response = client.get("/api/connectors", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "connectors" in data
        assert len(data["connectors"]) >= 8

    def test_connect_endpoint(self, client, auth_headers):
        response = client.post(
            "/api/connectors/gmail/connect",
            headers=auth_headers,
            json={"provider": "gmail", "oauth_token": "test-token"},
        )
        assert response.status_code == 200
        assert response.json()["connected"] is True

    def test_connect_unsupported_returns_400(self, client, auth_headers):
        response = client.post(
            "/api/connectors/myspace/connect",
            headers=auth_headers,
            json={"provider": "myspace", "oauth_token": ""},
        )
        assert response.status_code == 400

    def test_disconnect_endpoint(self, client, auth_headers):
        # Connect first
        client.post("/api/connectors/slack/connect", headers=auth_headers,
                    json={"provider": "slack", "oauth_token": "token"})
        # Then disconnect
        response = client.delete("/api/connectors/slack", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["connected"] is False

    def test_ingest_endpoint(self, client, auth_headers):
        # Connect first
        client.post("/api/connectors/gmail/connect", headers=auth_headers,
                    json={"provider": "gmail", "oauth_token": "token"})
        # Then ingest
        response = client.post("/api/connectors/gmail/ingest", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["ingested"] > 0

    def test_ingest_without_connection_returns_400(self, client, auth_headers):
        response = client.post("/api/connectors/github/ingest", headers=auth_headers)
        assert response.status_code == 400

    def test_audit_log_endpoint(self, client, auth_headers):
        client.post("/api/connectors/gmail/connect", headers=auth_headers,
                    json={"provider": "gmail", "oauth_token": "token"})
        response = client.get("/api/connectors/audit", headers=auth_headers)
        assert response.status_code == 200
        assert "audit" in response.json()

    def test_create_draft_endpoint(self, client, auth_headers):
        response = client.post(
            "/api/drafts",
            headers=auth_headers,
            json={
                "provider": "gmail",
                "recipient": "maria@example.com",
                "commitment_text": "Send proposal by Friday",
                "entity": "Maria",
                "evidence_refs": [{"entity": "Maria", "text": "I will send..."}],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        assert "draft_id" in data

    def test_list_drafts_endpoint(self, client, auth_headers):
        # Create a draft
        client.post("/api/drafts", headers=auth_headers, json={
            "provider": "gmail", "recipient": "a@b.com", "commitment_text": "test"
        })
        response = client.get("/api/drafts", headers=auth_headers)
        assert response.status_code == 200
        assert len(response.json()["drafts"]) >= 1

    def test_get_draft_endpoint(self, client, auth_headers):
        create = client.post("/api/drafts", headers=auth_headers, json={
            "provider": "gmail", "recipient": "a@b.com", "commitment_text": "test"
        })
        draft_id = create.json()["draft_id"]
        response = client.get(f"/api/drafts/{draft_id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["draft_id"] == draft_id

    def test_get_draft_404(self, client, auth_headers):
        response = client.get("/api/drafts/nonexistent", headers=auth_headers)
        assert response.status_code == 404

    def test_resolve_approve_endpoint(self, client, auth_headers):
        create = client.post("/api/drafts", headers=auth_headers, json={
            "provider": "gmail", "recipient": "a@b.com", "commitment_text": "test"
        })
        draft_id = create.json()["draft_id"]
        response = client.post(
            f"/api/drafts/{draft_id}/resolve",
            headers=auth_headers,
            json={"resolution": "approve"},
        )
        assert response.status_code == 200
        # P6 fix: without OAuth configured, send fails honestly
        assert response.json()["status"] == "send_failed"
        assert response.json()["send_error"] != ""

    def test_resolve_deny_endpoint(self, client, auth_headers):
        create = client.post("/api/drafts", headers=auth_headers, json={
            "provider": "gmail", "recipient": "a@b.com", "commitment_text": "test"
        })
        draft_id = create.json()["draft_id"]
        response = client.post(
            f"/api/drafts/{draft_id}/resolve",
            headers=auth_headers,
            json={"resolution": "deny"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "denied"

    def test_resolve_use_draft_endpoint(self, client, auth_headers):
        create = client.post("/api/drafts", headers=auth_headers, json={
            "provider": "gmail", "recipient": "a@b.com", "commitment_text": "test"
        })
        draft_id = create.json()["draft_id"]
        response = client.post(
            f"/api/drafts/{draft_id}/resolve",
            headers=auth_headers,
            json={"resolution": "use_draft"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "used_as_draft"

    def test_resolve_invalid_returns_400(self, client, auth_headers):
        create = client.post("/api/drafts", headers=auth_headers, json={
            "provider": "gmail", "recipient": "a@b.com", "commitment_text": "test"
        })
        draft_id = create.json()["draft_id"]
        response = client.post(
            f"/api/drafts/{draft_id}/resolve",
            headers=auth_headers,
            json={"resolution": "invalid"},
        )
        assert response.status_code == 400

    def test_unauthenticated_rejected(self, client):
        response = client.get("/api/connectors")
        assert response.status_code in (401, 403)

        response = client.post("/api/drafts", json={})
        assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# 6. Security tests
# ---------------------------------------------------------------------------

class TestSecurity:
    """Token storage security + per-connector isolation."""

    def test_token_not_in_plaintext(self, tmp_path):
        import sqlite3
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        store.connect("user@test.com", "gmail", "SECRET-OAUTH-TOKEN")

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        row = conn.execute("SELECT token FROM connectors WHERE provider='gmail'").fetchone()
        conn.close()

        # Token in DB should NOT be the plaintext
        assert row[0] != "SECRET-OAUTH-TOKEN"
        # But should decrypt back to the plaintext
        assert store._decrypt(row[0]) == "SECRET-OAUTH-TOKEN"

    def test_disconnect_deletes_token(self, tmp_path):
        import sqlite3
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        store.connect("user@test.com", "gmail", "SECRET-TOKEN")
        store.disconnect("user@test.com", "gmail")

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        row = conn.execute("SELECT token FROM connectors WHERE provider='gmail'").fetchone()
        conn.close()
        assert row[0] == ""  # token deleted

    def test_per_user_isolation(self, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        store.connect("userA@test.com", "gmail", "token-a")
        store.connect("userB@test.com", "gmail", "token-b")

        connectors_a = store.list_connectors("userA@test.com")
        connectors_b = store.list_connectors("userB@test.com")

        gmail_a = [c for c in connectors_a if c["provider"] == "gmail"][0]
        gmail_b = [c for c in connectors_b if c["provider"] == "gmail"][0]

        assert gmail_a["connected"] is True
        assert gmail_b["connected"] is True
        # User A disconnecting shouldn't affect user B
        store.disconnect("userA@test.com", "gmail")
        gmail_b_after = [c for c in store.list_connectors("userB@test.com") if c["provider"] == "gmail"][0]
        assert gmail_b_after["connected"] is True


# ---------------------------------------------------------------------------
# 7. P13 FIX — Auto-derivation tests (the real capability)
# ---------------------------------------------------------------------------

class TestAutoDraftDerivation:
    """P13 fix: /api/drafts/auto DERIVES the commitment from signal history.

    Unlike /api/drafts (which takes caller-supplied commitment_text), the
    auto endpoint takes only provider + recipient and DERIVES:
      1. The commitment (from the user's signals)
      2. The evidence_refs (from related signals + FTS5)
    """

    def test_auto_draft_derives_commitment_from_signals(self):
        """The auto endpoint finds a commitment for the recipient in signal history."""
        from unittest.mock import MagicMock
        from maestro_personal_shell.connectors import ConnectorDraftGenerator

        # Mock shell with signals including a commitment to Maria
        shell = MagicMock()
        sig1 = MagicMock()
        sig1.text = "I will send Maria the pricing proposal by Friday"
        sig1.entity = "Maria"
        sig1.signal_type = "commitment_made"
        sig1.timestamp = "2026-07-10T10:00:00Z"
        sig1.signal_id = "sig-001"

        sig2 = MagicMock()
        sig2.text = "Maria followed up asking for the proposal"
        sig2.entity = "Maria"
        sig2.signal_type = "follow_up_required"
        sig2.timestamp = "2026-07-12T09:00:00Z"
        sig2.signal_id = "sig-002"

        shell.oem_state = None; shell.signals = [sig1, sig2]
        shell.core = None  # skip FTS

        gen = ConnectorDraftGenerator(shell=shell)
        result = gen.generate_auto_draft(
            provider="gmail",
            recipient="maria@example.com",
            shell=shell,
        )

        assert "error" not in result, f"Should derive, got: {result}"
        assert result["derived"] is True, "Must be marked as derived"
        assert "pricing proposal" in result["body"], "Draft must cite the derived commitment"
        assert result["commitment_source"] == "sig-001"
        assert result["evidence_count"] >= 1, "Must have at least 1 evidence ref"
        assert len(result["evidence_refs"]) >= 1

    def test_auto_draft_returns_error_when_no_commitments_found(self):
        """If no commitments exist for the recipient, return a clear error."""
        from unittest.mock import MagicMock
        from maestro_personal_shell.connectors import ConnectorDraftGenerator

        shell = MagicMock()
        shell.oem_state = None; shell.signals = []  # no signals at all
        shell.core = None

        gen = ConnectorDraftGenerator(shell=shell)
        result = gen.generate_auto_draft(
            provider="gmail",
            recipient="nobody@example.com",
            shell=shell,
        )

        assert "error" in result
        assert "No active commitments" in result["error"]

    def test_auto_draft_requires_shell(self):
        """Without a shell, auto-derivation can't work — must error clearly."""
        from maestro_personal_shell.connectors import ConnectorDraftGenerator
        gen = ConnectorDraftGenerator(shell=None)
        result = gen.generate_auto_draft("gmail", "maria@example.com")
        assert "error" in result
        assert "Shell required" in result["error"]

    def test_auto_draft_finds_commitment_by_name_not_email(self):
        """Should match 'maria' in signal entity even when recipient is 'maria@example.com'."""
        from unittest.mock import MagicMock
        from maestro_personal_shell.connectors import ConnectorDraftGenerator

        shell = MagicMock()
        sig = MagicMock()
        sig.text = "I will send Maria the security questionnaire"
        sig.entity = "Maria Garcia"
        sig.signal_type = "commitment_made"
        sig.timestamp = "2026-07-09T10:00:00Z"
        sig.signal_id = "sig-maria"
        shell.oem_state = None; shell.signals = [sig]
        shell.core = None

        gen = ConnectorDraftGenerator(shell=shell)
        result = gen.generate_auto_draft("gmail", "maria.garcia@example.com", shell=shell)
        assert "error" not in result
        assert "security questionnaire" in result["body"]

    def test_manual_draft_marked_not_derived(self):
        """The manual generate_draft() must be marked derived=False (P13 disclosure)."""
        from maestro_personal_shell.connectors import ConnectorDraftGenerator
        gen = ConnectorDraftGenerator(shell=None)
        result = gen.generate_draft(
            provider="gmail",
            recipient="maria@example.com",
            commitment={"text": "test commitment", "entity": "Maria"},
            evidence_refs=[],
        )
        assert result["derived"] is False, "Manual drafts must be marked derived=False"

    def test_auto_draft_api_endpoint(self, client, auth_headers):
        """The /api/drafts/auto endpoint must return 200 or 404 (not 500)."""
        response = client.post(
            "/api/drafts/auto",
            headers=auth_headers,
            json={"provider": "gmail", "recipient": "maria@example.com"},
        )
        # 200 if signals exist for maria, 404 if not — both are correct behavior
        assert response.status_code in (200, 404), f"Got {response.status_code}: {response.text}"

    def test_auto_draft_only_takes_provider_and_recipient(self):
        """P13: the ConnectorAutoDraftRequest must NOT accept commitment_text."""
        # Phase 6: model moved to routers/connectors.py during api.py split
        from maestro_personal_shell.routers.connectors import ConnectorAutoDraftRequest
        fields = ConnectorAutoDraftRequest.model_fields
        assert "provider" in fields
        assert "recipient" in fields
        assert "commitment_text" not in fields, "P13 violation: auto endpoint must not take commitment_text"
        assert "evidence_refs" not in fields, "P13 violation: auto endpoint must not take evidence_refs"
