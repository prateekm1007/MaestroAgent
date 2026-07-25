"""K3 audit fix verification tests — rate limiting (P67/K3), OAuth fail-closed
(K3-CONN-001), reconcile_signal ownership (K3-BE-002), entity_aliases composite
PK (K3-DATA-001).

These tests verify the fixes are WIRED (P43) and behave correctly on both
the rules-only path and the live path.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# K3-BE-001 + P67: rate limiting fires regardless of MAESTRO_TEST_MODE
# ---------------------------------------------------------------------------

class _FakeClient:
    def __init__(self, host: str):
        self.host = host


class _FakeRequest:
    """Minimal stand-in for starlette.Request used by _check_rl."""
    def __init__(self, peer_host: str = "203.0.113.1", xff: str = ""):
        self.client = _FakeClient(peer_host)
        self.headers = {"X-Forwarded-For": xff} if xff else {}


def test_check_rl_fires_when_test_mode_set_but_local_dev_unset(monkeypatch):
    """P67/K3 fix: rate limiting MUST fire in production even if MAESTRO_TEST_MODE=1."""
    monkeypatch.delenv("MAESTRO_LOCAL_DEV", raising=False)
    monkeypatch.setenv("MAESTRO_TEST_MODE", "1")  # this was the bug — Railway has this set
    monkeypatch.setenv("MAESTRO_PERSONAL_ENV", "")  # not 'production' — was the second condition

    # Import fresh to pick up env
    import importlib
    from maestro_personal_shell.routers import auth as auth_mod
    importlib.reload(auth_mod)
    auth_mod._auth_rl.clear()

    # Fire 10 requests — should succeed
    for i in range(10):
        auth_mod._check_rl(_FakeRequest())
    # 11th request MUST 429
    with pytest.raises(HTTPException) as exc:
        auth_mod._check_rl(_FakeRequest())
    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"] == "60"


def test_check_rl_skipped_only_when_local_dev_true(monkeypatch):
    """P67/K3 fix: rate limiting is skipped ONLY when MAESTRO_LOCAL_DEV=true."""
    monkeypatch.setenv("MAESTRO_LOCAL_DEV", "true")
    monkeypatch.setenv("MAESTRO_TEST_MODE", "1")  # should be ignored

    import importlib
    from maestro_personal_shell.routers import auth as auth_mod
    importlib.reload(auth_mod)
    auth_mod._auth_rl.clear()

    # 100 requests should all succeed (rate limit skipped)
    for i in range(100):
        auth_mod._check_rl(_FakeRequest())


# ---------------------------------------------------------------------------
# K3-BE-001: X-Forwarded-For spoofing protection
# ---------------------------------------------------------------------------

def test_xff_ignored_when_peer_not_trusted(monkeypatch):
    """K3-BE-001 fix: spoofed X-Forwarded-For is ignored when the peer is not a trusted proxy."""
    monkeypatch.delenv("MAESTRO_LOCAL_DEV", raising=False)
    monkeypatch.delenv("MAESTRO_TRUSTED_PROXIES", raising=False)  # default: localhost only

    import importlib
    from maestro_personal_shell.routers import auth as auth_mod
    importlib.reload(auth_mod)
    auth_mod._auth_rl.clear()

    # 10 requests from a non-trusted peer with different spoofed XFF each time
    # should all bucket to the SAME peer IP, so the 11th 429s.
    for i in range(10):
        req = _FakeRequest(peer_host="203.0.113.99", xff=f"10.0.0.{i}")
        auth_mod._check_rl(req)
    with pytest.raises(HTTPException) as exc:
        auth_mod._check_rl(_FakeRequest(peer_host="203.0.113.99", xff="10.0.0.99"))
    assert exc.value.status_code == 429


def test_xff_honored_when_peer_is_trusted(monkeypatch):
    """K3-BE-001 fix: when peer is a trusted proxy, XFF is honored (leftmost IP)."""
    monkeypatch.delenv("MAESTRO_LOCAL_DEV", raising=False)
    monkeypatch.setenv("MAESTRO_TRUSTED_PROXIES", "127.0.0.1")

    import importlib
    from maestro_personal_shell.routers import auth as auth_mod
    importlib.reload(auth_mod)
    auth_mod._auth_rl.clear()

    # Peer is 127.0.0.1 (trusted), XFF varies → each request gets a fresh bucket
    for i in range(20):
        req = _FakeRequest(peer_host="127.0.0.1", xff=f"10.0.0.{i}")
        auth_mod._check_rl(req)  # no 429 — each XFF is a unique bucket


# ---------------------------------------------------------------------------
# K3-BE-002: reconcile_signal ownership predicate (P58 authorization)
# ---------------------------------------------------------------------------

def test_reconcile_signal_respects_user_email_ownership(tmp_path):
    """K3-BE-002 fix: reconcile_signal scopes by user_email when provided."""
    db_path = str(tmp_path / "test.db")
    from maestro_personal_shell.db_util import get_db_conn

    # Seed two users' signals
    conn = get_db_conn(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            signal_id TEXT PRIMARY KEY,
            user_email TEXT NOT NULL,
            entity TEXT,
            text TEXT,
            timestamp TEXT,
            metadata TEXT,
            signal_type TEXT
        )
    """)
    conn.execute("INSERT INTO signals VALUES ('sig-A', 'alice@example.com', 'Maria', 'text', '2026-01-01', '{}', 'commitment_made')")
    conn.execute("INSERT INTO signals VALUES ('sig-B', 'bob@example.com', 'Maria', 'text', '2026-01-01', '{}', 'commitment_made')")
    conn.commit()
    conn.close()

    from maestro_personal_shell.reconcile import reconcile_signal

    # Alice can read her own signal
    rec_a = reconcile_signal("sig-A", db_path=db_path, user_email="alice@example.com")
    assert rec_a is not None, "Alice should be able to read her own signal"
    assert rec_a["signal_id"] == "sig-A"

    # Alice CANNOT read Bob's signal (IDOR fix)
    rec_b = reconcile_signal("sig-B", db_path=db_path, user_email="alice@example.com")
    assert rec_b is None, "K3-BE-002 IDOR fix: Alice must not read Bob's signal"

    # Privileged path (no user_email) still works
    rec_priv = reconcile_signal("sig-B", db_path=db_path, user_email="")
    assert rec_priv is not None, "Privileged path (no user_email) should still work"


# ---------------------------------------------------------------------------
# K3-CONN-001: OAuth state fails closed when no signing key
# ---------------------------------------------------------------------------

def test_oauth_state_fails_closed_without_signing_key(monkeypatch):
    """K3-CONN-001 fix: missing signing key → 503, not silent acceptance."""
    monkeypatch.delenv("MAESTRO_PERSONAL_TOKEN", raising=False)
    monkeypatch.delenv("MAESTRO_ENCRYPTION_KEY", raising=False)

    import importlib
    from maestro_personal_shell.routers import connectors as conn_mod
    importlib.reload(conn_mod)

    # Any state (signed or unsigned) should 503 when no key is configured
    with pytest.raises(HTTPException) as exc:
        conn_mod._validate_oauth_state("user=victim@x.com;connector=gmail")
    assert exc.value.status_code == 503, f"Expected 503, got {exc.value.status_code}"

    with pytest.raises(HTTPException) as exc:
        conn_mod._validate_oauth_state("user=victim@x.com;connector=gmail;sig=fakesig")
    assert exc.value.status_code == 503


def test_oauth_state_rejects_unsigned_when_key_set(monkeypatch):
    """K3-CONN-001 fix: signed key configured → unsigned state is 403."""
    monkeypatch.setenv("MAESTRO_PERSONAL_TOKEN", "test-secret-key")

    import importlib
    from maestro_personal_shell.routers import connectors as conn_mod
    importlib.reload(conn_mod)

    with pytest.raises(HTTPException) as exc:
        conn_mod._validate_oauth_state("user=victim@x.com;connector=gmail")
    assert exc.value.status_code == 403


def test_oauth_state_accepts_valid_signature(monkeypatch):
    """K3-CONN-001 fix: validly-signed state still works."""
    monkeypatch.setenv("MAESTRO_PERSONAL_TOKEN", "test-secret-key")

    import importlib
    from maestro_personal_shell.routers import connectors as conn_mod
    importlib.reload(conn_mod)

    state = conn_mod._sign_oauth_state("alice@example.com", "gmail")
    user, conn = conn_mod._validate_oauth_state(state)
    assert user == "alice@example.com"
    assert conn == "gmail"


# ---------------------------------------------------------------------------
# K3-DATA-001: entity_aliases composite primary key (no cross-user corruption)
# ---------------------------------------------------------------------------

def test_entity_aliases_composite_pk_allows_same_alias_per_user(tmp_path):
    """K3-DATA-001 fix: two users can independently own the same alias string."""
    db_path = str(tmp_path / "test_entities.db")
    from maestro_personal_shell.entity_resolver import init_entity_aliases, add_alias, resolve_entity

    init_entity_aliases(db_path)
    # Alice and Bob both have a "Maria" alias pointing to different canonicals
    add_alias("Maria", "Maria Garcia", user_email="alice@example.com", db_path=db_path)
    add_alias("Maria", "Maria Santos", user_email="bob@example.com", db_path=db_path)

    # Alice's "Maria" resolves to "Maria Garcia"
    a = resolve_entity("Maria", user_email="alice@example.com", db_path=db_path)
    assert a == "Maria Garcia", f"Alice's Maria should resolve to Maria Garcia, got {a}"

    # Bob's "Maria" resolves to "Maria Santos" — NOT silently overwritten by Alice
    b = resolve_entity("Maria", user_email="bob@example.com", db_path=db_path)
    assert b == "Maria Santos", f"Bob's Maria should resolve to Maria Santos, got {b}"
