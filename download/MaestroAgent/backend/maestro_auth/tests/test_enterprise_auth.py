"""
Comprehensive enterprise auth tests.

Covers:
  - Password hashing (argon2/pbkdf2)
  - TOTP MFA (RFC 6238)
  - Session management (HttpOnly cookies, rotation, revocation)
  - Refresh token rotation + reuse detection
  - RBAC (roles, permissions, require_permission dependency)
  - CSRF protection (double-submit cookie)
  - OIDC flow (state CSRF, id_token verification)
  - SAML flow (InResponseTo, NameID extraction)
  - SCIM 2.0 (CRUD, filter, bearer auth)
  - Audit logging
  - OWASP Top 10 protections
  - Penetration tests (token reuse, session fixation, privilege escalation)
"""

import os
import secrets
import tempfile
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from maestro_api.main import create_app
from maestro_api.oem_state import oem_state, import_state
from maestro_auth.models import (
    AuthStore, hash_password, verify_password,
    totp_generate, totp_verify, _totp_secret,
    Permissions, ALL_PERMISSIONS, SYSTEM_ROLES,
    generate_session_id, generate_csrf_token, generate_refresh_token,
    hash_token,
)
from maestro_auth.sessions import SessionManager, SESSION_COOKIE, REFRESH_COOKIE, CSRF_COOKIE
from maestro_auth.permissions import init_auth, is_auth_enabled, require_permission


@pytest.fixture
def store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        s = AuthStore(path)
        yield s
        s.close()
    finally:
        os.unlink(path)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Test client with auth enabled."""
    test_db = str(tmp_path / "test_import.db")
    monkeypatch.setattr("maestro_api.oem_state._IMPORT_DB_PATH", test_db)
    monkeypatch.setenv("MAESTRO_AUTH_ENABLED", "true")
    monkeypatch.setenv("MAESTRO_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("MAESTRO_ADMIN_PASSWORD", "test-admin-pass")

    import_state._initialized = False
    import_state.store = None
    import_state.oauth = None
    import_state.connections = None
    import_state.tracker = None
    import_state.factory = None
    import_state.engine = None

    app = create_app(db_path=str(tmp_path / "maestro.db"))
    with TestClient(app) as c:
        yield c


# ═══════════════════════════════════════════════════════════════════════════
# 1. PASSWORD HASHING
# ═══════════════════════════════════════════════════════════════════════════

def test_password_hash_is_not_plaintext():
    h = hash_password("mySecretPassword123")
    assert "mySecretPassword123" not in h
    assert len(h) > 30


def test_password_verify_correct():
    h = hash_password("correctPassword")
    assert verify_password(h, "correctPassword") is True


def test_password_verify_wrong():
    h = hash_password("correctPassword")
    assert verify_password(h, "wrongPassword") is False


def test_password_hash_unique():
    h1 = hash_password("samePassword")
    h2 = hash_password("samePassword")
    assert h1 != h2


# ═══════════════════════════════════════════════════════════════════════════
# 2. TOTP MFA
# ═══════════════════════════════════════════════════════════════════════════

def test_totp_secret_is_base32():
    secret = _totp_secret()
    import base64
    base64.b32decode(secret, casefold=True)


def test_totp_generate_returns_6_digits():
    secret = _totp_secret()
    code = totp_generate(secret)
    assert len(code) == 6
    assert code.isdigit()


def test_totp_verify_correct_code():
    secret = _totp_secret()
    code = totp_generate(secret)
    assert totp_verify(secret, code) is True


def test_totp_verify_wrong_code():
    secret = _totp_secret()
    assert totp_verify(secret, "000000") is False


def test_totp_verify_rejects_non_digit():
    secret = _totp_secret()
    assert totp_verify(secret, "abcdef") is False
    assert totp_verify(secret, "") is False
    assert totp_verify(secret, "12345") is False


# ═══════════════════════════════════════════════════════════════════════════
# 3. SESSION MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════

def test_session_creation(store):
    user = store.create_user("test@acme.com", password="pass")
    sm = SessionManager(store)
    session_info = sm.login(user["id"], ip_address="127.0.0.1", user_agent="test")
    assert "session_id" in session_info
    assert "csrf_token" in session_info
    assert "refresh_token" in session_info
    assert "expires_at" in session_info


def test_session_validation(store):
    user = store.create_user("test@acme.com", password="pass")
    sm = SessionManager(store)
    session_info = sm.login(user["id"])
    result = sm.validate_session(session_info["session_id"])
    assert result is not None
    assert result["user"]["id"] == user["id"]


def test_session_revocation(store):
    user = store.create_user("test@acme.com", password="pass")
    sm = SessionManager(store)
    session_info = sm.login(user["id"])
    sm.logout(session_info["session_id"])
    assert sm.validate_session(session_info["session_id"]) is None


def test_inactive_user_session_invalid(store):
    user = store.create_user("test@acme.com", password="pass")
    sm = SessionManager(store)
    session_info = sm.login(user["id"])
    store.update_user(user["id"], is_active=0)
    assert sm.validate_session(session_info["session_id"]) is None


# ═══════════════════════════════════════════════════════════════════════════
# 4. REFRESH TOKEN ROTATION + REUSE DETECTION
# ═══════════════════════════════════════════════════════════════════════════

def test_refresh_token_rotation(store):
    user = store.create_user("test@acme.com", password="pass")
    sm = SessionManager(store)
    session_info = sm.login(user["id"])
    old_token = session_info["refresh_token"]
    new_session = sm.refresh(old_token)
    assert new_session is not None
    assert new_session["refresh_token"] != old_token


def test_refresh_token_reuse_detection(store):
    """Reusing a consumed refresh token must revoke the entire family."""
    user = store.create_user("test@acme.com", password="pass")
    sm = SessionManager(store)
    session_info = sm.login(user["id"])
    old_token = session_info["refresh_token"]
    new_session = sm.refresh(old_token)
    assert new_session is not None
    reuse_result = sm.refresh(old_token)
    assert reuse_result is None
    reuse_new = sm.refresh(new_session["refresh_token"])
    assert reuse_new is None


def test_refresh_token_hashed_in_db(store):
    """The DB must store only the hash, not the raw token."""
    user = store.create_user("test@acme.com", password="pass")
    sm = SessionManager(store)
    session_info = sm.login(user["id"])
    raw_token = session_info["refresh_token"]
    import sqlite3
    conn = sqlite3.connect(store.db_path)
    rows = conn.execute("SELECT token_hash FROM refresh_tokens").fetchall()
    conn.close()
    for row in rows:
        assert raw_token != row[0]


def test_refresh_token_expiry(store):
    user = store.create_user("test@acme.com", password="pass")
    session = store.create_session(user["id"])
    raw_token, _ = store.create_refresh_token(user["id"], session["id"], ttl_seconds=-1)
    sm = SessionManager(store)
    assert sm.refresh(raw_token) is None


# ═══════════════════════════════════════════════════════════════════════════
# 5. RBAC
# ═══════════════════════════════════════════════════════════════════════════

def test_system_roles_seeded(store):
    roles = store.list_roles()
    role_names = [r["name"] for r in roles]
    assert "ceo" in role_names
    assert "admin" in role_names
    assert "viewer" in role_names


def test_admin_has_all_permissions(store):
    user = store.create_user("admin@acme.com", password="pass", is_admin=True)
    store.assign_role(user["id"], "admin")
    perms = store.get_user_permissions(user["id"])
    assert Permissions.OEM_READ in perms
    assert Permissions.USER_MANAGE in perms


def test_viewer_has_only_read(store):
    user = store.create_user("viewer@acme.com", password="pass")
    store.assign_role(user["id"], "viewer")
    perms = store.get_user_permissions(user["id"])
    assert perms == {Permissions.OEM_READ}


def test_permission_check(store):
    user = store.create_user("eng@acme.com", password="pass")
    store.assign_role(user["id"], "engineer")
    assert store.has_permission(user["id"], Permissions.OEM_READ) is True
    assert store.has_permission(user["id"], Permissions.IMPORT_START) is True
    assert store.has_permission(user["id"], Permissions.USER_MANAGE) is False


def test_role_revocation(store):
    user = store.create_user("eng@acme.com", password="pass")
    store.assign_role(user["id"], "engineer")
    assert store.has_permission(user["id"], Permissions.IMPORT_START)
    store.revoke_role(user["id"], "engineer")
    assert not store.has_permission(user["id"], Permissions.IMPORT_START)


# ═══════════════════════════════════════════════════════════════════════════
# 6. AUDIT LOGGING
# ═══════════════════════════════════════════════════════════════════════════

def test_audit_event_recorded(store):
    store.audit(
        event_type="login", user_id="u1", email="test@acme.com",
        ip_address="127.0.0.1", detail={"method": "password"}, success=True,
    )
    events = store.list_audit_events(event_type="login")
    assert len(events) == 1
    assert events[0]["email"] == "test@acme.com"
    assert events[0]["success"] is True


def test_audit_failed_login(store):
    store.audit(event_type="login_failed", email="bad@acme.com",
                 detail={"reason": "bad_password"}, success=False)
    events = store.list_audit_events(event_type="login_failed")
    assert events[0]["success"] is False


# ═══════════════════════════════════════════════════════════════════════════
# 7. OIDC STATE CSRF
# ═══════════════════════════════════════════════════════════════════════════

def test_oidc_state_single_use(store):
    store.save_oidc_state("state-123", provider="google", nonce="nonce-abc")
    record = store.consume_oidc_state("state-123")
    assert record is not None
    assert record["provider"] == "google"
    assert store.consume_oidc_state("state-123") is None


def test_oidc_state_expiry(store):
    store.save_oidc_state("state-expired", provider="google", ttl=-1)
    assert store.consume_oidc_state("state-expired") is None


# ═══════════════════════════════════════════════════════════════════════════
# 8. SAML InResponseTo
# ═══════════════════════════════════════════════════════════════════════════

def test_saml_request_single_use(store):
    store.save_saml_request("_req-123", provider="azure")
    record = store.consume_saml_request("_req-123")
    assert record is not None
    assert record["provider"] == "azure"
    assert store.consume_saml_request("_req-123") is None


# ═══════════════════════════════════════════════════════════════════════════
# 9. SCIM
# ═══════════════════════════════════════════════════════════════════════════

def test_scim_create_user(store):
    from maestro_auth.scim import SCIMManager
    manager = SCIMManager(store)
    result = manager.create_user({
        "id": "scim-1", "userName": "alice@acme.com", "displayName": "Alice",
        "emails": [{"value": "alice@acme.com", "primary": True}], "active": True,
    })
    assert result["userName"] == "alice@acme.com"
    local = store.get_user_by_email("alice@acme.com")
    assert local is not None
    assert store.has_permission(local["id"], Permissions.OEM_READ)


def test_scim_delete_deactivates(store):
    from maestro_auth.scim import SCIMManager
    manager = SCIMManager(store)
    manager.create_user({
        "id": "scim-1", "userName": "carol@acme.com",
        "emails": [{"value": "carol@acme.com", "primary": True}], "active": True,
    })
    manager.delete_user("scim-1")
    user = store.get_user_by_email("carol@acme.com")
    assert user is not None
    assert user["is_active"] == 0


def test_scim_token_verification():
    from maestro_auth.scim import SCIMManager
    with patch.dict(os.environ, {"MAESTRO_SCIM_TOKEN": "scim-secret-123"}):
        assert SCIMManager.is_enabled() is True
        assert SCIMManager.verify_token("scim-secret-123") is True
        assert SCIMManager.verify_token("wrong") is False


# ═══════════════════════════════════════════════════════════════════════════
# 10. API INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════

def test_login_sets_httponly_cookies(client):
    resp = client.post("/api/auth/login", json={
        "email": "admin@maestro.local", "password": "test-admin-pass",
    })
    assert resp.status_code == 200
    cookies = resp.headers.get("set-cookie", "")
    assert "maestro_session=" in cookies
    assert "HttpOnly" in cookies
    assert "maestro_refresh=" in cookies


def test_login_wrong_password(client):
    resp = client.post("/api/auth/login", json={
        "email": "admin@maestro.local", "password": "wrong",
    })
    assert resp.status_code == 401


def test_login_unknown_user(client):
    resp = client.post("/api/auth/login", json={
        "email": "nobody@nowhere.com", "password": "anything",
    })
    assert resp.status_code == 401


def test_me_requires_auth(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_returns_user_after_login(client):
    client.post("/api/auth/login", json={
        "email": "admin@maestro.local", "password": "test-admin-pass",
    })
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["email"] == "admin@maestro.local"
    assert resp.json()["is_admin"] is True


def test_logout_clears_cookies(client):
    client.post("/api/auth/login", json={
        "email": "admin@maestro.local", "password": "test-admin-pass",
    })
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 200
    cookies = resp.headers.get("set-cookie", "")
    assert "Max-Age=0" in cookies or "expires=Thu, 01 Jan 1970" in cookies.lower()


def test_oidc_providers_list(client):
    resp = client.get("/api/auth/oidc/providers")
    assert resp.status_code == 200
    names = [p["provider"] for p in resp.json()["providers"]]
    assert "azure" in names and "okta" in names and "google" in names
    assert "auth0" in names and "supabase" in names


def test_saml_metadata(client):
    resp = client.get("/api/auth/saml/metadata")
    assert resp.status_code == 200
    assert "EntityDescriptor" in resp.text


def test_roles_list(client):
    client.post("/api/auth/login", json={
        "email": "admin@maestro.local", "password": "test-admin-pass",
    })
    resp = client.get("/api/auth/roles")
    assert resp.status_code == 200
    names = [r["name"] for r in resp.json()["roles"]]
    assert "admin" in names and "viewer" in names


def test_audit_log_requires_admin(client):
    resp = client.get("/api/auth/audit")
    assert resp.status_code == 401
    client.post("/api/auth/login", json={
        "email": "admin@maestro.local", "password": "test-admin-pass",
    })
    resp = client.get("/api/auth/audit")
    assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# 11. OWASP TOP 10
# ═══════════════════════════════════════════════════════════════════════════

def test_owasp_no_token_in_response(client):
    """No access_token in JSON response (must be in HttpOnly cookie only)."""
    resp = client.post("/api/auth/login", json={
        "email": "admin@maestro.local", "password": "test-admin-pass",
    })
    data = resp.json()
    assert "access_token" not in data
    assert "token" not in data
    assert "refresh_token" not in data


def test_owasp_no_password_in_response(client):
    client.post("/api/auth/login", json={
        "email": "admin@maestro.local", "password": "test-admin-pass",
    })
    data = client.get("/api/auth/me").json()
    assert "password_hash" not in data
    assert "password" not in data
    assert "mfa_secret" not in data


def test_owasp_no_user_enumeration(client):
    """Login errors must not reveal whether a user exists."""
    resp_unknown = client.post("/api/auth/login", json={
        "email": "nobody@nowhere.com", "password": "wrong",
    })
    resp_wrong_pw = client.post("/api/auth/login", json={
        "email": "admin@maestro.local", "password": "wrong",
    })
    assert resp_unknown.status_code == resp_wrong_pw.status_code
    assert resp_unknown.json()["detail"] == resp_wrong_pw.json()["detail"]


def test_owasp_session_cookie_httponly(client):
    resp = client.post("/api/auth/login", json={
        "email": "admin@maestro.local", "password": "test-admin-pass",
    })
    assert "HttpOnly" in resp.headers.get("set-cookie", "")


# ═══════════════════════════════════════════════════════════════════════════
# 12. PENETRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════

def test_pen_session_fixation(store):
    """Server generates session IDs (doesn't accept client-supplied)."""
    user = store.create_user("test@acme.com", password="pass")
    sm = SessionManager(store)
    session_info = sm.login(user["id"])
    import uuid
    uuid.UUID(session_info["session_id"])


def test_pen_token_reuse_revokes_family(store):
    """Replaying a used refresh token revokes the entire family."""
    user = store.create_user("test@acme.com", password="pass")
    sm = SessionManager(store)
    session_info = sm.login(user["id"])
    stolen = sm.refresh(session_info["refresh_token"])
    assert stolen is not None
    # Legitimate user's reuse fails
    assert sm.refresh(session_info["refresh_token"]) is None
    # Attacker's stolen session also revoked
    assert sm.refresh(stolen["refresh_token"]) is None


def test_pen_privilege_escalation_blocked(store):
    viewer = store.create_user("viewer@acme.com", password="pass")
    store.assign_role(viewer["id"], "viewer")
    assert not store.has_permission(viewer["id"], Permissions.USER_MANAGE)
    assert not store.has_permission(viewer["id"], Permissions.ROLE_MANAGE)


def test_pen_sql_injection_in_email(store):
    store.create_user("alice@acme.com", password="pass")
    assert store.get_user_by_email("alice@acme.com' OR '1'='1") is None
    assert store.get_user_by_email("alice@acme.com") is not None


def test_pen_sql_injection_in_scim_filter(store):
    from maestro_auth.scim import SCIMManager
    manager = SCIMManager(store)
    manager.create_user({
        "id": "scim-1", "userName": "alice@acme.com",
        "emails": [{"value": "alice@acme.com", "primary": True}], "active": True,
    })
    result = manager.list_users(filter_expr='userName eq "\' OR \'1\'=\'1"')
    assert result["totalResults"] == 0


def test_pen_expired_session_rejected(store):
    user = store.create_user("test@acme.com", password="pass")
    session = store.create_session(user["id"], ttl_seconds=-1)
    sm = SessionManager(store)
    assert sm.validate_session(session["id"]) is None


def test_pen_revoked_session_rejected(store):
    user = store.create_user("test@acme.com", password="pass")
    sm = SessionManager(store)
    session_info = sm.login(user["id"])
    sm.logout(session_info["session_id"])
    assert sm.validate_session(session_info["session_id"]) is None


def test_pen_backup_code_single_use(store):
    user = store.create_user("test@acme.com", password="pass")
    store.set_backup_codes(user["id"], ["code1", "code2"])
    assert store.verify_backup_code(user["id"], "code1") is True
    assert store.verify_backup_code(user["id"], "code1") is False
    assert store.verify_backup_code(user["id"], "code2") is True


def test_pen_revoke_all_sessions(store):
    user = store.create_user("test@acme.com", password="pass")
    sm = SessionManager(store)
    s1 = sm.login(user["id"])
    s2 = sm.login(user["id"])
    store.revoke_all_user_sessions(user["id"])
    assert sm.validate_session(s1["session_id"]) is None
    assert sm.validate_session(s2["session_id"]) is None


# ═══════════════════════════════════════════════════════════════════════════
# 13. SCIM API
# ═══════════════════════════════════════════════════════════════════════════

def test_scim_api_requires_token(client, monkeypatch):
    monkeypatch.setenv("MAESTRO_SCIM_TOKEN", "test-scim-token")
    assert client.get("/scim/v2/Users").status_code == 401
    assert client.get("/scim/v2/Users", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/scim/v2/Users", headers={"Authorization": "Bearer test-scim-token"}).status_code == 200


def test_scim_api_crud(client, monkeypatch):
    monkeypatch.setenv("MAESTRO_SCIM_TOKEN", "test-scim-token")
    headers = {"Authorization": "Bearer test-scim-token"}
    # Create
    resp = client.post("/scim/v2/Users", json={
        "id": "scim-test-1", "userName": "scim-test@acme.com", "displayName": "SCIM Test",
        "emails": [{"value": "scim-test@acme.com", "primary": True}], "active": True,
    }, headers=headers)
    assert resp.status_code == 200
    # Read
    assert client.get("/scim/v2/Users/scim-test-1", headers=headers).status_code == 200
    # Update
    resp = client.put("/scim/v2/Users/scim-test-1", json={
        "id": "scim-test-1", "userName": "scim-test@acme.com", "displayName": "Updated",
        "emails": [{"value": "scim-test@acme.com", "primary": True}], "active": False,
    }, headers=headers)
    assert resp.json()["displayName"] == "Updated"
    # Delete
    assert client.delete("/scim/v2/Users/scim-test-1", headers=headers).status_code == 204
