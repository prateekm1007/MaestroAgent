"""
Enterprise authentication models.

Replaces the stub auth in maestro_auth/ with production-grade:
  - User, Group, Role, Permission
  - Session (with HttpOnly cookie tokens)
  - RefreshToken (rotating, family-based reuse detection)
  - MFADevice (TOTP)
  - AuditEvent (append-only)
  - SCIM external identity mapping

All persisted to SQLite. Passwords use argon2. Tokens use secrets.token_urlsafe.
"""

from __future__ import annotations

import json
import logging
import secrets
from maestro_db import sqlite_compat as sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

import hashlib
import hmac
import base64
import struct
import time as _time
import os

logger = logging.getLogger(__name__)


# ─── Schema ───

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    email           TEXT UNIQUE NOT NULL,
    display_name    TEXT NOT NULL DEFAULT '',
    password_hash   TEXT,              -- argon2 hash (NULL for SSO-only users)
    is_active       INTEGER NOT NULL DEFAULT 1,
    is_admin        INTEGER NOT NULL DEFAULT 0,
    mfa_enabled     INTEGER NOT NULL DEFAULT 0,
    mfa_secret      TEXT,              -- TOTP secret (encrypted at rest in production)
    mfa_backup_codes TEXT,             -- JSON array of hashed backup codes
    external_id     TEXT,              -- OIDC/SAML subject
    external_provider TEXT,            -- oidc:azure | oidc:okta | oidc:google | oidc:auth0 | oidc:supabase | saml
    scim_external_id TEXT,             -- SCIM user ID from IdP
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    last_login_at   TEXT
);

CREATE TABLE IF NOT EXISTS groups (
    id              TEXT PRIMARY KEY,
    name            TEXT UNIQUE NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS group_members (
    group_id        TEXT NOT NULL,
    user_id         TEXT NOT NULL,
    PRIMARY KEY (group_id, user_id),
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS roles (
    id              TEXT PRIMARY KEY,
    name            TEXT UNIQUE NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    is_system       INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id         TEXT NOT NULL,
    permission      TEXT NOT NULL,
    PRIMARY KEY (role_id, permission),
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_roles (
    user_id         TEXT NOT NULL,
    role_id         TEXT NOT NULL,
    scope_org_id    TEXT,              -- optional org scope
    PRIMARY KEY (user_id, role_id, scope_org_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY,          -- session ID (not the cookie value)
    user_id         TEXT NOT NULL,
    csrf_token      TEXT NOT NULL,             -- double-submit CSRF
    ip_address      TEXT,
    user_agent      TEXT,
    created_at      TEXT NOT NULL,
    expires_at      TEXT NOT NULL,
    last_used_at    TEXT NOT NULL,
    revoked_at      TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    session_id      TEXT NOT NULL,
    token_hash      TEXT UNIQUE NOT NULL,      -- SHA-256 of the refresh token
    family_id       TEXT NOT NULL,             -- for reuse detection
    expires_at      TEXT NOT NULL,
    used_at         TEXT,
    revoked_at      TEXT,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_refresh_family ON refresh_tokens(family_id);
CREATE INDEX IF NOT EXISTS idx_refresh_hash ON refresh_tokens(token_hash);

CREATE TABLE IF NOT EXISTS audit_events (
    id              TEXT PRIMARY KEY,
    timestamp       TEXT NOT NULL,
    user_id         TEXT,
    email           TEXT,
    event_type      TEXT NOT NULL,             -- login|logout|login_failed|mfa_challenge|mfa_success|mfa_failed|token_refresh|token_revoke|permission_denied|scim_provision|role_change|password_change
    ip_address      TEXT,
    user_agent      TEXT,
    resource        TEXT,
    detail          TEXT,                       -- JSON
    success         INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_events(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_type ON audit_events(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_events(timestamp);

CREATE TABLE IF NOT EXISTS oidc_state_cache (
    state           TEXT PRIMARY KEY,
    provider        TEXT NOT NULL,
    nonce           TEXT,
    redirect_to     TEXT,
    created_at      TEXT NOT NULL,
    expires_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS saml_request_cache (
    request_id      TEXT PRIMARY KEY,
    provider        TEXT NOT NULL,
    relay_state     TEXT,
    created_at      TEXT NOT NULL,
    expires_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scim_resource_mappings (
    scim_id         TEXT PRIMARY KEY,
    maestro_id      TEXT NOT NULL,
    resource_type   TEXT NOT NULL,             -- User | Group
    created_at      TEXT NOT NULL
);
"""


# ─── Argon2 password hashing (with fallback to pbkdf2 for environments without argon2) ───

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError
    _argon2 = PasswordHasher()

    def hash_password(password: str) -> str:
        return _argon2.hash(password)

    def verify_password(hash_str: str, password: str) -> bool:
        try:
            _argon2.verify(hash_str, password)
            return True
        except VerifyMismatchError:
            return False
except ImportError:
    # Fallback: PBKDF2-HMAC-SHA256 (still secure, just slower)
    import hashlib

    def hash_password(password: str) -> str:
        salt = secrets.token_bytes(16)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
        return f"pbkdf2$200000${salt.hex()}${dk.hex()}"

    def verify_password(hash_str: str, password: str) -> bool:
        if not hash_str.startswith("pbkdf2$"):
            return False
        _, iters_str, salt_hex, hash_hex = hash_str.split("$", 3)
        iters = int(iters_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iters)
        return hmac.compare_digest(dk, expected)


# ─── TOTP (RFC 6238) — no external deps ───

def _totp_secret() -> str:
    """Generate a base32-encoded TOTP secret."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")


def _totp_now() -> int:
    return int(_time.time() // 30)


def _hotp(secret: str, counter: int) -> str:
    """HOTP per RFC 4226."""
    key = base64.b32decode(secret, casefold=True)
    msg = struct.pack(">Q", counter)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code = struct.unpack(">I", h[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{code % 1_000_000:06d}"


def totp_generate(secret: str, at_counter: int | None = None) -> str:
    """Generate the current TOTP code."""
    counter = at_counter if at_counter is not None else _totp_now()
    return _hotp(secret, counter)


def totp_verify(secret: str, code: str, window: int = 1) -> bool:
    """Verify a TOTP code, allowing ±window steps for clock drift."""
    if not code or not code.isdigit() or len(code) != 6:
        return False
    now = _totp_now()
    for offset in range(-window, window + 1):
        if hmac.compare_digest(_hotp(secret, now + offset), code):
            return True
    return False


def _hash_backup_code(code: str) -> str:
    """Hash a backup code for storage (SHA-256 with pepper from env)."""
    pepper = (os.environ.get("MAESTRO_AUTH_PEPPER") or "default-pepper-change-me").encode()
    return hashlib.sha256(code.encode() + pepper).hexdigest()


# ─── Token generation ───

def generate_session_id() -> str:
    return str(uuid4())


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def generate_refresh_token() -> str:
    """Generate a refresh token. The raw value is returned to the client;
    the DB stores only the SHA-256 hash."""
    return secrets.token_urlsafe(48)


def generate_family_id() -> str:
    return str(uuid4())


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ─── Date helpers ───

def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def utcnow_plus(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


# ─── Permission constants ───

class Permissions:
    """All permissions in the system. Used by RBAC."""
    # OEM
    OEM_READ = "oem:read"
    OEM_WRITE = "oem:write"
    OEM_CONTRADICT = "oem:contradict"
    OEM_SIMULATE = "oem:simulate"
    # Imports
    IMPORT_START = "import:start"
    IMPORT_CANCEL = "import:cancel"
    IMPORT_READ = "import:read"
    # OAuth connections
    CONNECT_PROVIDER = "connect:provider"
    DISCONNECT_PROVIDER = "connect:disconnect"
    # Admin
    USER_MANAGE = "user:manage"
    ROLE_MANAGE = "role:manage"
    AUDIT_READ = "audit:read"
    SCIM_PROVISION = "scim:provision"
    # Settings
    SETTINGS_READ = "settings:read"
    SETTINGS_WRITE = "settings:write"


ALL_PERMISSIONS = [v for k, v in vars(Permissions).items() if not k.startswith("_") and isinstance(v, str)]


# ─── System roles (seeded on init) ───

SYSTEM_ROLES = {
    "ceo": {
        "description": "Chief Executive — full read access to OEM, can simulate and contradict",
        "permissions": [
            Permissions.OEM_READ, Permissions.OEM_SIMULATE, Permissions.OEM_CONTRADICT,
            Permissions.IMPORT_READ, Permissions.AUDIT_READ, Permissions.SETTINGS_READ,
        ],
    },
    "admin": {
        "description": "Administrator — full access including user/role management",
        "permissions": ALL_PERMISSIONS,
    },
    "analyst": {
        "description": "Analyst — read-only OEM access",
        "permissions": [Permissions.OEM_READ, Permissions.IMPORT_READ, Permissions.SETTINGS_READ],
    },
    "engineer": {
        "description": "Engineer — OEM read + import management",
        "permissions": [
            Permissions.OEM_READ, Permissions.IMPORT_START, Permissions.IMPORT_CANCEL,
            Permissions.IMPORT_READ, Permissions.CONNECT_PROVIDER, Permissions.DISCONNECT_PROVIDER,
        ],
    },
    "viewer": {
        "description": "Viewer — read-only dashboard access",
        "permissions": [Permissions.OEM_READ],
    },
}


# ─── AuthStore — the persistence layer ───

class AuthStore:
    """SQLite-backed store for all auth state. Thread-safe."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._connect()
        self._seed_system_roles()

    def _connect(self) -> None:
        is_memory = self.db_path == ":memory:"
        self._conn = sqlite3.connect(
            self.db_path if not is_memory else "file::memory:?cache=shared",
            uri=is_memory,
            check_same_thread=False,
            isolation_level=None,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        assert self._conn is not None
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute("BEGIN")
                yield cur
                cur.execute("COMMIT")
            except Exception:
                cur.execute("ROLLBACK")
                raise

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _seed_system_roles(self) -> None:
        """Seed the system roles and their permissions."""
        with self._cursor() as cur:
            for name, spec in SYSTEM_ROLES.items():
                role_id = f"role:{name}"
                cur.execute(
                    "INSERT OR IGNORE INTO roles (id, name, description, is_system, created_at) VALUES (?, ?, ?, 1, ?)",
                    (role_id, name, spec["description"], utcnow()),
                )
                for perm in spec["permissions"]:
                    cur.execute(
                        "INSERT OR IGNORE INTO role_permissions (role_id, permission) VALUES (?, ?)",
                        (role_id, perm),
                    )

    # ─── User CRUD ───

    def create_user(
        self,
        email: str,
        display_name: str = "",
        password: str | None = None,
        is_admin: bool = False,
        external_id: str | None = None,
        external_provider: str | None = None,
        scim_external_id: str | None = None,
    ) -> dict[str, Any]:
        user_id = str(uuid4())
        password_hash = hash_password(password) if password else None
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO users
                   (id, email, display_name, password_hash, is_active, is_admin,
                    mfa_enabled, created_at, updated_at, external_id, external_provider, scim_external_id)
                   VALUES (?, ?, ?, ?, 1, ?, 0, ?, ?, ?, ?, ?)""",
                (user_id, email.lower(), display_name, password_hash, 1 if is_admin else 0,
                 utcnow(), utcnow(), external_id, external_provider, scim_external_id),
            )
        return self.get_user(user_id)

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM users WHERE email = ?", (email.lower(),))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_user_by_external_id(self, external_id: str, provider: str) -> dict[str, Any] | None:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM users WHERE external_id = ? AND external_provider = ?",
                (external_id, provider),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def update_user(self, user_id: str, **fields) -> None:
        if not fields:
            return
        fields["updated_at"] = utcnow()
        sets = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [user_id]
        with self._cursor() as cur:
            cur.execute(f"UPDATE users SET {sets} WHERE id = ?", values)

    def list_users(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM users ORDER BY created_at DESC LIMIT ?", (limit,))
            return [dict(r) for r in cur.fetchall()]

    def delete_user(self, user_id: str) -> None:
        with self._cursor() as cur:
            cur.execute("DELETE FROM users WHERE id = ?", (user_id,))

    # ─── Password / MFA ───

    def verify_password(self, user_id: str, password: str) -> bool:
        user = self.get_user(user_id)
        if not user or not user["password_hash"]:
            return False
        return verify_password(user["password_hash"], password)

    def set_password(self, user_id: str, password: str) -> None:
        self.update_user(user_id, password_hash=hash_password(password))

    def enable_mfa(self, user_id: str, secret: str) -> None:
        self.update_user(user_id, mfa_enabled=1, mfa_secret=secret)

    def disable_mfa(self, user_id: str) -> None:
        self.update_user(user_id, mfa_enabled=0, mfa_secret=None, mfa_backup_codes=None)

    def set_backup_codes(self, user_id: str, codes: list[str]) -> None:
        hashed = json.dumps([_hash_backup_code(c) for c in codes])
        self.update_user(user_id, mfa_backup_codes=hashed)

    def verify_backup_code(self, user_id: str, code: str) -> bool:
        user = self.get_user(user_id)
        if not user or not user["mfa_backup_codes"]:
            return False
        stored = json.loads(user["mfa_backup_codes"])
        target = _hash_backup_code(code)
        for i, h in enumerate(stored):
            if hmac.compare_digest(h, target):
                # Remove the used code (one-time use)
                stored.pop(i)
                self.update_user(user_id, mfa_backup_codes=json.dumps(stored))
                return True
        return False

    # ─── Roles & permissions ───

    def assign_role(self, user_id: str, role_name: str, scope_org_id: str | None = None) -> None:
        role_id = f"role:{role_name}"
        with self._cursor() as cur:
            cur.execute(
                "INSERT OR IGNORE INTO user_roles (user_id, role_id, scope_org_id) VALUES (?, ?, ?)",
                (user_id, role_id, scope_org_id),
            )

    def revoke_role(self, user_id: str, role_name: str, scope_org_id: str | None = None) -> None:
        role_id = f"role:{role_name}"
        with self._cursor() as cur:
            cur.execute(
                "DELETE FROM user_roles WHERE user_id = ? AND role_id = ? AND COALESCE(scope_org_id, '') = COALESCE(?, '')",
                (user_id, role_id, scope_org_id),
            )

    def get_user_permissions(self, user_id: str) -> set[str]:
        """Get all permissions for a user (from all assigned roles)."""
        with self._cursor() as cur:
            cur.execute(
                """SELECT DISTINCT rp.permission
                   FROM user_roles ur
                   JOIN role_permissions rp ON ur.role_id = rp.role_id
                   WHERE ur.user_id = ?""",
                (user_id,),
            )
            return {r["permission"] for r in cur.fetchall()}

    def get_user_roles(self, user_id: str) -> list[dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute(
                """SELECT r.*, ur.scope_org_id
                   FROM user_roles ur
                   JOIN roles r ON ur.role_id = r.id
                   WHERE ur.user_id = ?""",
                (user_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    def has_permission(self, user_id: str, permission: str) -> bool:
        perms = self.get_user_permissions(user_id)
        return permission in perms

    def list_roles(self) -> list[dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM roles ORDER BY name")
            return [dict(r) for r in cur.fetchall()]

    # ─── Sessions ───

    def create_session(
        self,
        user_id: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        ttl_seconds: int = 86400 * 7,  # 7 days
    ) -> dict[str, Any]:
        session_id = generate_session_id()
        csrf_token = generate_csrf_token()
        now = utcnow()
        expires = utcnow_plus(ttl_seconds)
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO sessions
                   (id, user_id, csrf_token, ip_address, user_agent, created_at, expires_at, last_used_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, user_id, csrf_token, ip_address, user_agent, now, expires, now),
            )
        return {
            "id": session_id,
            "user_id": user_id,
            "csrf_token": csrf_token,
            "expires_at": expires,
            "created_at": now,
        }

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def touch_session(self, session_id: str) -> None:
        with self._cursor() as cur:
            cur.execute(
                "UPDATE sessions SET last_used_at = ? WHERE id = ?",
                (utcnow(), session_id),
            )

    def revoke_session(self, session_id: str) -> None:
        with self._cursor() as cur:
            cur.execute(
                "UPDATE sessions SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                (utcnow(), session_id),
            )
            # Revoke all refresh tokens for this session
            cur.execute(
                "UPDATE refresh_tokens SET revoked_at = ? WHERE session_id = ? AND revoked_at IS NULL",
                (utcnow(), session_id),
            )

    def revoke_all_user_sessions(self, user_id: str) -> None:
        with self._cursor() as cur:
            cur.execute(
                "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                (utcnow(), user_id),
            )
            cur.execute(
                "UPDATE refresh_tokens SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                (utcnow(), user_id),
            )

    def list_user_sessions(self, user_id: str) -> list[dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM sessions WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    # ─── Refresh tokens (rotating, family-based reuse detection) ───

    def create_refresh_token(
        self,
        user_id: str,
        session_id: str,
        ttl_seconds: int = 86400 * 30,  # 30 days
        family_id: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Create a refresh token. Returns (raw_token, record).

        The raw_token is returned to the client; only the hash is stored.
        family_id is set on the first token in a family; subsequent rotations
        inherit it. If a used token is reused, the entire family is revoked
        (reuse detection).
        """
        raw_token = generate_refresh_token()
        token_hash = hash_token(raw_token)
        family_id = family_id or generate_family_id()
        now = utcnow()
        expires = utcnow_plus(ttl_seconds)
        token_id = str(uuid4())
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO refresh_tokens
                   (id, user_id, session_id, token_hash, family_id, expires_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (token_id, user_id, session_id, token_hash, family_id, expires, now),
            )
        return raw_token, {
            "id": token_id,
            "user_id": user_id,
            "session_id": session_id,
            "family_id": family_id,
            "expires_at": expires,
            "created_at": now,
        }

    def verify_refresh_token(self, raw_token: str) -> dict[str, Any] | None:
        """Verify a refresh token. Returns the record if valid.

        If the token was already used, this is a reuse attack — revoke the
        entire family and return None.
        """
        token_hash = hash_token(raw_token)
        with self._cursor() as cur:
            cur.execute(
                """SELECT * FROM refresh_tokens WHERE token_hash = ?""",
                (token_hash,),
            )
            row = cur.fetchone()
            if not row:
                return None
            record = dict(row)

            # Check expiry
            if record["expires_at"] < utcnow():
                return None

            # Check if revoked
            if record["revoked_at"]:
                # Reuse detected — revoke entire family
                logger.warning(
                    "Refresh token reuse detected for family %s — revoking all tokens in family",
                    record["family_id"],
                )
                cur.execute(
                    "UPDATE refresh_tokens SET revoked_at = ? WHERE family_id = ? AND revoked_at IS NULL",
                    (utcnow(), record["family_id"]),
                )
                # Also revoke the session
                cur.execute(
                    "UPDATE sessions SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                    (utcnow(), record["session_id"]),
                )
                return None

            # Check if already used (rotation)
            if record["used_at"]:
                # Reuse detected — revoke entire family
                logger.warning(
                    "Refresh token reuse detected for family %s (already used) — revoking all tokens in family",
                    record["family_id"],
                )
                cur.execute(
                    "UPDATE refresh_tokens SET revoked_at = ? WHERE family_id = ? AND revoked_at IS NULL",
                    (utcnow(), record["family_id"]),
                )
                cur.execute(
                    "UPDATE sessions SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                    (utcnow(), record["session_id"]),
                )
                return None

            return record

    def mark_token_used(self, token_id: str) -> None:
        with self._cursor() as cur:
            cur.execute(
                "UPDATE refresh_tokens SET used_at = ? WHERE id = ?",
                (utcnow(), token_id),
            )

    # ─── Audit events ───

    def audit(
        self,
        event_type: str,
        user_id: str | None = None,
        email: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        resource: str | None = None,
        detail: dict[str, Any] | None = None,
        success: bool = True,
    ) -> None:
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO audit_events
                   (id, timestamp, user_id, email, event_type, ip_address, user_agent, resource, detail, success)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(uuid4()), utcnow(), user_id, email, event_type,
                 ip_address, user_agent, resource, json.dumps(detail or {}), 1 if success else 0),
            )

    def list_audit_events(
        self, limit: int = 100, event_type: str | None = None, user_id: str | None = None
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM audit_events WHERE 1=1"
        params: list[Any] = []
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        with self._cursor() as cur:
            cur.execute(query, params)
            rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            r["detail"] = json.loads(r["detail"] or "{}")
            r["success"] = bool(r["success"])
        return rows

    # ─── OIDC state cache (CSRF protection for OAuth flows) ───

    def save_oidc_state(self, state: str, provider: str, nonce: str | None = None,
                        redirect_to: str | None = None, ttl: int = 600) -> None:
        with self._cursor() as cur:
            cur.execute(
                """INSERT OR REPLACE INTO oidc_state_cache
                   (state, provider, nonce, redirect_to, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (state, provider, nonce, redirect_to, utcnow(), utcnow_plus(ttl)),
            )

    def consume_oidc_state(self, state: str) -> dict[str, Any] | None:
        """Atomically consume a state token (single-use)."""
        with self._cursor() as cur:
            cur.execute("SELECT * FROM oidc_state_cache WHERE state = ?", (state,))
            row = cur.fetchone()
            if not row:
                return None
            record = dict(row)
            # Delete (single-use)
            cur.execute("DELETE FROM oidc_state_cache WHERE state = ?", (state,))
            # Check expiry
            if record["expires_at"] < utcnow():
                return None
            return record

    # ─── SAML request cache ───

    def save_saml_request(self, request_id: str, provider: str, relay_state: str | None = None, ttl: int = 600) -> None:
        with self._cursor() as cur:
            cur.execute(
                """INSERT OR REPLACE INTO saml_request_cache
                   (request_id, provider, relay_state, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (request_id, provider, relay_state, utcnow(), utcnow_plus(ttl)),
            )

    def consume_saml_request(self, request_id: str) -> dict[str, Any] | None:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM saml_request_cache WHERE request_id = ?", (request_id,))
            row = cur.fetchone()
            if not row:
                return None
            record = dict(row)
            cur.execute("DELETE FROM saml_request_cache WHERE request_id = ?", (request_id,))
            if record["expires_at"] < utcnow():
                return None
            return record

    # ─── SCIM resource mappings ───

    def save_scim_mapping(self, scim_id: str, maestro_id: str, resource_type: str) -> None:
        with self._cursor() as cur:
            cur.execute(
                """INSERT OR REPLACE INTO scim_resource_mappings
                   (scim_id, maestro_id, resource_type, created_at)
                   VALUES (?, ?, ?, ?)""",
                (scim_id, maestro_id, resource_type, utcnow()),
            )

    def get_scim_mapping(self, scim_id: str) -> dict[str, Any] | None:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM scim_resource_mappings WHERE scim_id = ?", (scim_id,))
            row = cur.fetchone()
            return dict(row) if row else None

