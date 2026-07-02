"""API key generation, hashing, and storage.

API keys are generated as `ma_<random32>` (URL-safe base64). They are
stored as SHA-256 hashes (never plaintext) in SQLite. Verification
compares the hash of the presented key to the stored hash.

For local single-user deployments, the key is also stored in the OS
keyring (via `keyring`) so the user doesn't have to manage it manually.
"""

from __future__ import annotations

import hashlib
import secrets
from maestro_db import sqlite_compat as sqlite3
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


def generate_api_key() -> str:
    """Generate a new random API key: `ma_<32 chars>`."""
    return f"ma_{secrets.token_urlsafe(32)}"


def hash_api_key(key: str) -> str:
    """SHA-256 hash of an API key. Stored; never store plaintext."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def verify_api_key(presented: str, stored_hash: str) -> bool:
    """Constant-time comparison of a presented key to a stored hash."""
    if not presented or not stored_hash:
        return False
    presented_hash = hash_api_key(presented)
    return secrets.compare_digest(presented_hash, stored_hash)


class ApiKeyStore(ABC):
    """Abstract API key store."""

    @abstractmethod
    async def create(self, key: str, name: str, scopes: list[str] | None = None) -> None: ...

    @abstractmethod
    async def verify(self, key: str) -> tuple[bool, dict[str, Any]]: ...

    @abstractmethod
    async def list_keys(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def revoke(self, key: str) -> bool: ...


SCHEMA = """
CREATE TABLE IF NOT EXISTS api_keys(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_hash TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    scopes_json TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL,
    last_used_at REAL,
    revoked INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
"""


class SQLiteApiKeyStore(ApiKeyStore):
    """SQLite-backed API key store."""

    def __init__(self, db_path: str | Path = "maestro.db") -> None:
        self.db_path = str(db_path)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(SCHEMA)
            conn.commit()
        finally:
            conn.close()
        self._conn: sqlite3.Connection | None = None

    def _conn_get(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    async def create(self, key: str, name: str, scopes: list[str] | None = None) -> None:
        import json
        conn = self._conn_get()
        conn.execute(
            "INSERT INTO api_keys (key_hash, name, scopes_json, created_at) VALUES (?, ?, ?, ?)",
            (hash_api_key(key), name, json.dumps(scopes or []), time.time()),
        )
        conn.commit()

    async def verify(self, key: str) -> tuple[bool, dict[str, Any]]:
        if not key:
            return False, {}
        conn = self._conn_get()
        row = conn.execute(
            "SELECT id, name, scopes_json, created_at, last_used_at, revoked FROM api_keys WHERE key_hash = ?",
            (hash_api_key(key),),
        ).fetchone()
        if row is None or row["revoked"]:
            return False, {}
        # Update last_used_at (fire and forget).
        conn.execute(
            "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
            (time.time(), row["id"]),
        )
        conn.commit()
        import json
        return True, {
            "id": row["id"],
            "name": row["name"],
            "scopes": json.loads(row["scopes_json"]),
            "created_at": row["created_at"],
        }

    async def list_keys(self) -> list[dict[str, Any]]:
        import json
        conn = self._conn_get()
        rows = conn.execute(
            "SELECT id, name, scopes_json, created_at, last_used_at, revoked FROM api_keys ORDER BY created_at DESC"
        ).fetchall()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "scopes": json.loads(r["scopes_json"]),
                "created_at": r["created_at"],
                "last_used_at": r["last_used_at"],
                "revoked": bool(r["revoked"]),
            }
            for r in rows
        ]

    async def revoke(self, key: str) -> bool:
        conn = self._conn_get()
        cur = conn.execute(
            "UPDATE api_keys SET revoked = 1 WHERE key_hash = ? AND revoked = 0",
            (hash_api_key(key),),
        )
        conn.commit()
        return cur.rowcount > 0


async def ensure_default_key(store: SQLiteApiKeyStore, config_db_path: str) -> str | None:
    """Ensure a default API key exists if auth is enabled.

    If no key is configured (env or keyring), generate one, store its
    hash in SQLite, write the plaintext to the keyring, and return it.
    The plaintext is only ever shown once — at generation time.
    """
    import os
    key = os.environ.get("MAESTRO_API_KEY")
    if key:
        # Ensure it's in the store.
        ok, _ = await store.verify(key)
        if not ok:
            await store.create(key, "env-default", ["*"])
        return key

    # Try keyring.
    try:
        import keyring
        key = keyring.get_password("maestroagent", "default-api-key")
        if key:
            ok, _ = await store.verify(key)
            if not ok:
                await store.create(key, "keyring-default", ["*"])
            return key
    except Exception:
        pass

    # Generate a new one.
    key = generate_api_key()
    await store.create(key, "auto-generated", ["*"])
    try:
        import keyring
        keyring.set_password("maestroagent", "default-api-key", key)
    except Exception:
        pass
    # Also write to a file the user can read (for headless servers).
    #
    # SECURITY (Round 76): the prior version wrote this to
    # `Path(config_db_path).parent / "api_key.txt"` — which is inside the
    # repo working directory. This caused a live API key to be committed
    # to version control (backend/api_key.txt), giving anyone who cloned
    # the repo the bearer token for all /api/* endpoints.
    #
    # Fix: write to a path OUTSIDE the repo tree by default. Use XDG config
    # dir (~/.config/maestroagent/) or MAESTRO_API_KEY_FILE if set. Only
    # fall back to the config_db_path parent if explicitly requested via
    # MAESTRO_API_KEY_FILE_IN_REPO=true (for dev only, never production).
    import os
    key_file_env = os.environ.get("MAESTRO_API_KEY_FILE")
    if key_file_env:
        key_file = Path(key_file_env)
    elif os.environ.get("MAESTRO_API_KEY_FILE_IN_REPO", "false").lower() == "true":
        # Dev-only escape hatch — must be explicitly opted into.
        key_file = Path(config_db_path).parent / "api_key.txt"
    else:
        # Default: write outside the repo tree.
        xdg_config = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
        key_file = Path(xdg_config) / "maestroagent" / "api_key.txt"
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(key)
    key_file.chmod(0o600)
    logger.info("API key written to %s (outside repo tree)", key_file)
    return key
