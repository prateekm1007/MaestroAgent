"""Test: ensure_default_key() — the function that auto-generates the API key.

Principle 2: this function had ZERO test coverage across 76 rounds. The
Round 76 security fix (move key file outside repo tree) added a logger.info()
call but the module had no logger defined — a NameError that fired every
time the function ran to completion. No test caught it because no test
called the function.

This test calls ensure_default_key() exactly as a fresh headless deployment
would: no MAESTRO_API_KEY env var, no keyring entry, generating for the
first time. It asserts the function completes and writes the key file.

Proof by negation: revert the 'import logging' + 'logger = ...' fix →
this test FAILS with NameError. Restore → PASSES.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from maestro_auth.api_keys import ensure_default_key, SQLiteApiKeyStore


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Simulate a fresh headless deployment: no pre-set key, XDG_CONFIG_HOME in tmp."""
    monkeypatch.delenv("MAESTRO_API_KEY", raising=False)
    monkeypatch.delenv("MAESTRO_API_KEY_FILE", raising=False)
    monkeypatch.delenv("MAESTRO_API_KEY_FILE_IN_REPO", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))
    return tmp_path


async def test_ensure_default_key_generates_and_writes_file(clean_env: Path) -> None:
    """ensure_default_key() must complete without error and write the key file
    outside the repo tree.

    This is the test that would have caught the Round 76 NameError. The
    function had zero coverage; the security fix added a logger.info() call
    referencing an undefined name. This test calls the function end-to-end.
    """
    db_path = str(clean_env / "auth.db")
    store = SQLiteApiKeyStore(db_path=db_path)

    key = await ensure_default_key(store=store, config_db_path=db_path)

    assert key is not None, "ensure_default_key() must return a key, not None"
    assert key.startswith("ma_"), f"Key must start with 'ma_', got {key[:5]}..."
    assert len(key) > 10, f"Key too short: {len(key)} chars"

    # The key file must exist OUTSIDE the repo tree (in XDG_CONFIG_HOME).
    expected_path = Path(os.environ["XDG_CONFIG_HOME"]) / "maestroagent" / "api_key.txt"
    assert expected_path.exists(), (
        f"Key file not written to expected path: {expected_path}"
    )
    assert expected_path.read_text() == key, "Key file content must match returned key"


async def test_ensure_default_key_does_not_write_inside_repo(clean_env: Path) -> None:
    """The key file must NOT be written inside the repo tree by default.

    This is the security property the Round 76 fix intended — but the fix
    shipped a NameError that prevented the function from completing at all.
    Now that the NameError is fixed, this test verifies the security property
    actually holds: the function writes to XDG_CONFIG_HOME, not to the
    config_db_path's parent (which is inside the repo tree in dev).

    Note: we check the function's OUTPUT path, not whether api_key.txt exists
    anywhere in the repo — a pre-existing file from before the fix may still
    be on disk (removed from git tracking but not deleted). The security
    property is about where the function WRITES, not about leftover files.
    """
    db_path = str(clean_env / "auth.db")
    store = SQLiteApiKeyStore(db_path=db_path)

    key = await ensure_default_key(store=store, config_db_path=db_path)

    # The function must write to XDG_CONFIG_HOME/maestroagent/api_key.txt.
    expected_path = Path(os.environ["XDG_CONFIG_HOME"]) / "maestroagent" / "api_key.txt"
    assert expected_path.exists(), f"Key must be written to {expected_path}"

    # The function must NOT write to config_db_path's parent (the old buggy path).
    old_buggy_path = Path(db_path).parent / "api_key.txt"
    # Only fail if the function JUST wrote it there (mtime is recent).
    if old_buggy_path.exists():
        import time
        mtime = old_buggy_path.stat().st_mtime
        now = time.time()
        assert now - mtime > 5.0, (
            f"Key file was JUST written inside the repo tree at {old_buggy_path} "
            f"(mtime {now - mtime:.1f}s ago) — security fix not working. "
            f"The function must write to XDG_CONFIG_HOME, not config_db_path's parent."
        )


async def test_ensure_default_key_returns_existing_key_if_already_set(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If MAESTRO_API_KEY is set, the function must return it without generating."""
    monkeypatch.setenv("MAESTRO_API_KEY", "ma_existing_test_key_12345")
    db_path = str(clean_env / "auth.db")
    store = SQLiteApiKeyStore(db_path=db_path)

    key = await ensure_default_key(store=store, config_db_path=db_path)
    assert key == "ma_existing_test_key_12345"
