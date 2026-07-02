"""Unit tests for CheckpointStore — SQLite-backed persistence."""

import os
import tempfile
from datetime import datetime, timezone

import pytest

from maestro_oem.checkpoint_store import CheckpointStore


@pytest.fixture
def store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        s = CheckpointStore(path)
        yield s
        s.close()
    finally:
        os.unlink(path)


def test_create_job(store):
    job_id = store.create_job(providers=["github", "jira"], since="5y")
    job = store.get_job(job_id)
    assert job is not None
    assert job["status"] == "pending"
    assert job["providers"] == ["github", "jira"]
    assert job["since"] == "5y"


def test_update_job_status(store):
    job_id = store.create_job(providers=["github"])
    store.update_job_status(job_id, "running")
    assert store.get_job(job_id)["status"] == "running"
    store.update_job_status(job_id, "completed", total_signals=100)
    job = store.get_job(job_id)
    assert job["status"] == "completed"
    assert job["total_signals"] == 100
    assert job["completed_at"] is not None


def test_save_and_load_checkpoint(store):
    job_id = store.create_job(providers=["github"])
    cp = {
        "job_id": job_id,
        "provider": "github",
        "resource_type": "all",
        "sync_mode": "full",
        "last_page": 5,
        "last_cursor": "5:pulls:5:2024-01-01",
        "total_pages_estimated": 100,
        "pages_completed": 5,
        "signals_produced": 500,
        "errors": 0,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "completed": False,
    }
    store.save_checkpoint(cp)
    loaded = store.load_checkpoint(job_id, "github")
    assert loaded is not None
    assert loaded["last_page"] == 5
    assert loaded["last_cursor"] == "5:pulls:5:2024-01-01"
    assert loaded["pages_completed"] == 5
    assert loaded["signals_produced"] == 500
    assert loaded["completed"] is False


def test_checkpoint_upsert(store):
    """Re-saving the same checkpoint should update, not duplicate."""
    job_id = store.create_job(providers=["github"])
    base_cp = {
        "job_id": job_id,
        "provider": "github",
        "resource_type": "all",
        "sync_mode": "full",
        "last_page": 1,
        "total_pages_estimated": 100,
        "pages_completed": 1,
        "signals_produced": 100,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
    store.save_checkpoint(base_cp)
    base_cp["last_page"] = 50
    base_cp["pages_completed"] = 50
    base_cp["signals_produced"] = 5000
    store.save_checkpoint(base_cp)

    cps = store.list_checkpoints(job_id)
    assert len(cps) == 1
    assert cps[0]["last_page"] == 50
    assert cps[0]["signals_produced"] == 5000


def test_list_incomplete_checkpoints(store):
    job_id = store.create_job(providers=["github", "jira"])
    for p in ["github", "jira"]:
        store.save_checkpoint({
            "job_id": job_id, "provider": p, "resource_type": "all",
            "sync_mode": "full", "started_at": datetime.now(timezone.utc).isoformat(),
            "last_updated": datetime.now(timezone.utc).isoformat(),
        })
    # Mark github as complete
    store.save_checkpoint({
        "job_id": job_id, "provider": "github", "resource_type": "all",
        "sync_mode": "full", "completed": True,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "last_updated": datetime.now(timezone.utc).isoformat(),
    })
    incomplete = store.list_incomplete_checkpoints(job_id)
    assert len(incomplete) == 1
    assert incomplete[0]["provider"] == "jira"


def test_oauth_credentials_crud(store):
    store.save_credentials(
        provider="github",
        access_token="gho_test123",
        refresh_token="ghr_refresh456",
        token_type="Bearer",
        expires_at="1900000000",
        scopes=["repo", "read:org"],
        metadata={"installation_id": 12345},
    )
    creds = store.load_credentials("github")
    assert creds is not None
    assert creds["access_token"] == "gho_test123"
    assert creds["refresh_token"] == "ghr_refresh456"
    assert "repo" in creds["scopes"]
    assert creds["metadata"]["installation_id"] == 12345

    store.delete_credentials("github")
    assert store.load_credentials("github") is None


def test_connection_state(store):
    store.set_connection("github", connected=True, org_id="acme")
    conn = store.get_connection("github")
    assert conn["connected"] is True
    assert conn["org_id"] == "acme"

    store.set_connection("github", connected=False)
    assert store.get_connection("github")["connected"] is False


def test_list_jobs_ordering(store):
    """Most recent job should be first."""
    j1 = store.create_job(providers=["github"])
    j2 = store.create_job(providers=["jira"])
    jobs = store.list_jobs()
    assert jobs[0]["job_id"] == j2
    assert jobs[1]["job_id"] == j1


def test_auto_migrate_org_id_on_legacy_db():
    """Regression test: _auto_migrate_org_id must add org_id to legacy DBs.

    Root cause (found by execution 2026-07-03): the old code used
    `row[1]` to read PRAGMA table_info results, but sqlite_compat
    returns dicts (not tuples), so `row[1]` raised KeyError(1). The
    broad `except Exception` caught it and logged at DEBUG level
    (invisible at default log level), so the ALTER TABLE never ran.
    This caused /api/imports and /api/oauth/status to 500 with
    "no such column: org_id".

    This test creates a legacy DB (no org_id) and verifies the
    CheckpointStore constructor auto-migrates all 3 tables.
    """
    import sqlite3
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        # Create legacy schema (no org_id) — simulates a DB from before Round 52
        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE import_jobs (
                job_id TEXT PRIMARY KEY, status TEXT NOT NULL,
                providers TEXT NOT NULL, since TEXT,
                started_at TEXT NOT NULL, completed_at TEXT,
                total_signals INTEGER NOT NULL DEFAULT 0, error TEXT
            );
            CREATE TABLE oauth_credentials (
                provider TEXT NOT NULL, access_token TEXT NOT NULL,
                refresh_token TEXT, token_type TEXT DEFAULT 'Bearer',
                expires_at TEXT, scopes TEXT, metadata TEXT
            );
            CREATE TABLE provider_connections (
                provider TEXT NOT NULL, connected INTEGER NOT NULL DEFAULT 0,
                connected_at TEXT, metadata TEXT
            );
        """)
        conn.commit()
        conn.close()

        # Verify legacy DB has NO org_id
        check = sqlite3.connect(path)
        cols_before = [r[1] for r in check.execute("PRAGMA table_info(import_jobs)").fetchall()]
        assert "org_id" not in cols_before, "Test setup wrong: org_id already exists"
        check.close()

        # Construct CheckpointStore — should auto-migrate
        s = CheckpointStore(path)
        s.close()

        # Verify org_id was added to all 3 tables
        verify = sqlite3.connect(path)
        for table in ["import_jobs", "oauth_credentials", "provider_connections"]:
            cols = [r[1] for r in verify.execute(f"PRAGMA table_info({table})").fetchall()]
            assert "org_id" in cols, f"FAIL: org_id not added to {table}. Cols: {cols}"
        verify.close()

        # Verify list_jobs works (the original failure surface)
        s2 = CheckpointStore(path)
        jobs = s2.list_jobs()
        assert jobs == [], "list_jobs should return empty list on fresh DB"
        s2.close()
    finally:
        os.unlink(path)
