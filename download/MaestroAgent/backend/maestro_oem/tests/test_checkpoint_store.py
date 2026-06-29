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
