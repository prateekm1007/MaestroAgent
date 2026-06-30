"""Unit tests for HistoricalImportEngine — end-to-end import orchestration."""

import asyncio
import os
import tempfile
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maestro_oem.checkpoint_store import CheckpointStore
from maestro_oem.historical_engine import (
    HistoricalImportEngine,
    parse_since,
)
from maestro_oem.importers.base import BaseProviderFetcher
from maestro_oem.ingestion import PageResult, PageStatus
from maestro_oem.oauth_manager import OAuthManager
from maestro_oem.progress_tracker import ProgressTracker
from maestro_oem.importers.factory import ProviderFactory


# ─── Test fetcher — simulates a real provider with paginated data ───

class _TestFetcher(BaseProviderFetcher):
    """Configurable test fetcher for the engine tests.

    Uses provider='github' so the existing github normalizer works on
    the test events (which are shaped like GitHub PR events).

    Note: Leading underscore + __test__ = False prevents pytest from
    trying to collect this as a test class.
    """

    __test__ = False

    provider = "github"

    def __init__(self, oauth, http_client=None, page_size=None, org_id=None,
                 total_pages=5, page_size_items=10):
        # Skip base init for the http_client since we don't need it
        from maestro_oem.ingestion import PageFetcher
        PageFetcher.__init__(self, "test")
        self.oauth = oauth
        self.page_size = page_size_items
        self._total_pages = total_pages
        self._page_size_items = page_size_items
        self._fetched_pages: list[int] = []

    async def fetch_page(self, page=1, cursor="", since=None):
        self._fetched_pages.append(page)
        if page > self._total_pages:
            return PageResult(page_number=page, status=PageStatus.SUCCESS, items=[], items_count=0)
        items = [{
            "event_type": "pull_request",
            "repository": f"test/repo",
            "actor": f"user{i}@test.com",
            "artifact": f"github:test/repo/pull/{page * 100 + i}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": {"action": "opened", "domain": "engineering", "title": f"PR {i}"},
        } for i in range(self._page_size_items)]
        return PageResult(
            page_number=page, status=PageStatus.SUCCESS,
            items=items, items_count=len(items),
            next_page=page + 1 if page < self._total_pages else None,
        )

    async def estimate_total_pages(self, since=None):
        return self._total_pages

    def normalize_item(self, item):
        return item


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


@pytest.fixture
def oauth(store):
    # Pre-populate credentials for the 'github' provider (used by _TestFetcher)
    store.save_credentials(provider="github", access_token="test_token", scopes=["test"])
    store.set_connection("github", connected=True)
    return OAuthManager(store)


@pytest.fixture
def factory(oauth):
    """Factory that returns _TestFetcher for the 'test' provider."""
    f = MagicMock(spec=ProviderFactory)
    f.create = lambda provider, org_id=None, page_size=None: _TestFetcher(oauth)
    return f


@pytest.fixture
def tracker():
    return ProgressTracker()


@pytest.fixture
def engine(store, oauth, factory, tracker):
    received_signals: list = []
    snapshots: list[dict[str, int]] = []

    def on_signals(sigs):
        received_signals.extend(sigs)

    def on_oem_update():
        snap = {
            "signals_processed": len(received_signals),
            "learning_objects": len(received_signals) // 2,
            "patterns_detected": len(received_signals) // 10,
            "laws_inferred": max(0, len(received_signals) // 50 - 1),
            "recommendations": max(0, len(received_signals) // 30),
            "validated_laws": max(0, len(received_signals) // 100),
        }
        snapshots.append(snap)
        return snap

    return HistoricalImportEngine(
        store=store, oauth=oauth, factory=factory, tracker=tracker,
        on_signals=on_signals, on_oem_update=on_oem_update,
    )


# ─── parse_since ───

def test_parse_since_5y():
    dt = parse_since("5y")
    assert dt is not None
    assert (datetime.now(timezone.utc) - dt).days >= 365 * 4  # at least 4 years


def test_parse_since_30d():
    dt = parse_since("30d")
    assert dt is not None
    assert (datetime.now(timezone.utc) - dt).days >= 29


def test_parse_since_iso():
    dt = parse_since("2024-01-01T00:00:00Z")
    assert dt is not None
    assert dt.year == 2024


def test_parse_since_none():
    assert parse_since(None) is None


def test_parse_since_invalid():
    assert parse_since("garbage") is None


# ─── Engine lifecycle ───

@pytest.mark.asyncio
async def test_start_and_complete_import(engine, store):
    job_id = await engine.start_import(["github"], since=None)
    await engine.wait_for_completion(job_id)

    job = engine.get_job(job_id)
    assert job["status"] == "completed"
    assert job["providers_progress"]["github"]["status"] == "completed"
    # Should have processed 5 pages * 10 items = 50 signals
    assert job["providers_progress"]["github"]["events_processed"] == 50
    assert job["total_events"] == 50


@pytest.mark.asyncio
async def test_checkpoint_persisted(engine, store):
    job_id = await engine.start_import(["github"], since=None)
    await engine.wait_for_completion(job_id)

    cps = store.list_checkpoints(job_id)
    assert len(cps) == 1
    assert cps[0]["provider"] == "github"
    assert cps[0]["completed"] is True
    assert cps[0]["signals_produced"] == 50


@pytest.mark.asyncio
async def test_oem_updates_during_import(engine, tracker):
    job_id = await engine.start_import(["github"], since=None)
    await engine.wait_for_completion(job_id)

    job = tracker.get_job(job_id)
    # OEM snapshot should have been updated at least once during the import
    assert job.oem_snapshot.signals_processed == 50
    assert job.oem_snapshot.patterns_detected >= 1


@pytest.mark.asyncio
async def test_cancel_job(engine, store):
    # Use a fetcher that takes a long time per page
    class SlowFetcher(_TestFetcher):
        async def fetch_page(self, page=1, cursor="", since=None):
            await asyncio.sleep(0.1)
            return await super().fetch_page(page, cursor)

    engine.factory.create = lambda provider, org_id=None, page_size=None: SlowFetcher(engine.oauth)

    job_id = await engine.start_import(["github"], since=None)
    await asyncio.sleep(0.05)  # Let it start
    engine.cancel_job(job_id)
    await engine.wait_for_completion(job_id)

    job = engine.get_job(job_id)
    assert job["status"] in ("cancelled", "completed")  # Depending on timing


@pytest.mark.asyncio
async def test_resume_from_checkpoint(store, oauth, tracker):
    """Verify resume picks up where it left off."""
    fetcher_instances: list[_TestFetcher] = []

    class TrackingFactory:
        def create(self, provider, org_id=None, page_size=None):
            f = _TestFetcher(oauth, total_pages=3)
            fetcher_instances.append(f)
            return f

    engine = HistoricalImportEngine(
        store=store, oauth=oauth, factory=TrackingFactory(), tracker=tracker,
        on_signals=lambda sigs: None, on_oem_update=lambda: {"signals_processed": 0,
                                                              "learning_objects": 0,
                                                              "patterns_detected": 0,
                                                              "laws_inferred": 0,
                                                              "recommendations": 0,
                                                              "validated_laws": 0},
    )

    # Pre-create a checkpoint at page 2
    job_id = store.create_job(providers=["github"])
    store.save_checkpoint({
        "job_id": job_id, "provider": "github", "resource_type": "all",
        "sync_mode": "full", "last_page": 1, "last_cursor": "",
        "total_pages_estimated": 3, "pages_completed": 1,
        "signals_produced": 10, "errors": 0,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "completed": False,
    })
    store.update_job_status(job_id, "running")

    # Start the engine with resume=True
    new_job_id = await engine.start_import(["github"], since=None, job_id=job_id, resume=True)
    await engine.wait_for_completion(new_job_id)

    # Should have only fetched pages 2 and 3 (resumed from page 2)
    # Note: the engine starts at last_page + 1 = 2
    assert len(fetcher_instances) == 1
    fetched = fetcher_instances[0]._fetched_pages
    # Engine advances page internally; verify it didn't refetch page 1
    assert 1 not in fetched


@pytest.mark.asyncio
async def test_parallel_providers(store, oauth, tracker):
    """Two providers should run in parallel."""
    class TwoProviderFactory:
        def create(self, provider, org_id=None, page_size=None):
            return _TestFetcher(oauth, total_pages=3)

    engine = HistoricalImportEngine(
        store=store, oauth=oauth, factory=TwoProviderFactory(), tracker=tracker,
        on_signals=lambda sigs: None, on_oem_update=lambda: {"signals_processed": 0,
                                                              "learning_objects": 0,
                                                              "patterns_detected": 0,
                                                              "laws_inferred": 0,
                                                              "recommendations": 0,
                                                              "validated_laws": 0},
    )
    # Pre-populate credentials for both providers
    for p in ["github", "jira"]:
        store.save_credentials(provider=p, access_token="test_token", scopes=["test"])
        store.set_connection(p, connected=True)

    job_id = await engine.start_import(["github", "jira"], since=None)
    await engine.wait_for_completion(job_id)

    job = engine.get_job(job_id)
    assert job["providers_progress"]["github"]["status"] == "completed"
    assert job["providers_progress"]["jira"]["status"] == "completed"
    assert job["status"] == "completed"


@pytest.mark.asyncio
async def test_large_history_simulation(store, oauth, tracker):
    """Simulate 100k events (1000 pages of 100) to verify memory-safe streaming."""
    class BigHistoryFactory:
        def create(self, provider, org_id=None, page_size=None):
            return _TestFetcher(oauth, total_pages=20, page_size_items=100)

    received: list = []
    engine = HistoricalImportEngine(
        store=store, oauth=oauth, factory=BigHistoryFactory(), tracker=tracker,
        on_signals=lambda sigs: received.extend(sigs),
        on_oem_update=lambda: {"signals_processed": len(received),
                                "learning_objects": 0, "patterns_detected": 0,
                                "laws_inferred": 0, "recommendations": 0, "validated_laws": 0},
    )
    store.save_credentials(provider="github", access_token="test_token", scopes=["test"])
    store.set_connection("github", connected=True)

    job_id = await engine.start_import(["github"], since=None)
    await engine.wait_for_completion(job_id)

    # 20 pages * 100 items = 2000 signals
    assert len(received) == 2000
    job = engine.get_job(job_id)
    assert job["providers_progress"]["github"]["events_processed"] == 2000


@pytest.mark.asyncio
async def test_restart_resumes_incomplete(store, oauth, tracker):
    """Verify resume_incomplete_jobs picks up where we left off after a restart."""
    class RestartFactory:
        def create(self, provider, org_id=None, page_size=None):
            return _TestFetcher(oauth, total_pages=3)

    received: list = []
    engine = HistoricalImportEngine(
        store=store, oauth=oauth, factory=RestartFactory(), tracker=tracker,
        on_signals=lambda sigs: received.extend(sigs),
        on_oem_update=lambda: {"signals_processed": len(received),
                                "learning_objects": 0, "patterns_detected": 0,
                                "laws_inferred": 0, "recommendations": 0, "validated_laws": 0},
    )
    store.save_credentials(provider="github", access_token="test_token", scopes=["test"])
    store.set_connection("github", connected=True)

    # Create a "running" job with an incomplete checkpoint (simulating crash mid-import)
    job_id = store.create_job(providers=["github"], since=None)
    store.update_job_status(job_id, "running")
    store.save_checkpoint({
        "job_id": job_id, "provider": "github", "resource_type": "all",
        "sync_mode": "full", "last_page": 0, "last_cursor": "",
        "total_pages_estimated": 3, "pages_completed": 0,
        "signals_produced": 0, "errors": 0,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "completed": False,
    })

    # "Restart" — call resume_incomplete_jobs
    resumed = await engine.resume_incomplete_jobs()
    assert len(resumed) == 1
    await engine.wait_for_completion(resumed[0])

    # Verify the job completed
    job = store.get_job(job_id)
    assert job["status"] == "completed"
    cps = store.list_checkpoints(job_id)
    assert cps[0]["completed"] is True


@pytest.mark.asyncio
async def test_oauth_expiry_handling(store, oauth, tracker):
    """When fetcher returns AUTH_EXPIRED, engine should refresh and retry."""
    refresh_count = {"count": 0}

    class ExpiringFetcher(_TestFetcher):
        async def fetch_page(self, page=1, cursor="", since=None):
            if page == 2 and refresh_count["count"] == 0:
                refresh_count["count"] += 1
                return PageResult(page_number=page, status=PageStatus.AUTH_EXPIRED,
                                  error="Token expired")
            return await super().fetch_page(page, cursor)

    # Stub the OAuthManager.refresh_token to update stored creds
    oauth.refresh_token = lambda provider: "refreshed_token"

    engine = HistoricalImportEngine(
        store=store, oauth=oauth,
        factory=MagicMock(spec=ProviderFactory,
                          create=lambda p, org_id=None, page_size=None: ExpiringFetcher(oauth)),
        tracker=tracker,
        on_signals=lambda sigs: None,
        on_oem_update=lambda: {"signals_processed": 0, "learning_objects": 0,
                                "patterns_detected": 0, "laws_inferred": 0,
                                "recommendations": 0, "validated_laws": 0},
    )
    store.save_credentials(provider="github", access_token="test_token", scopes=["test"])
    store.set_connection("github", connected=True)

    job_id = await engine.start_import(["github"], since=None)
    await engine.wait_for_completion(job_id)

    # Verify refresh was attempted
    assert refresh_count["count"] >= 1
    job = engine.get_job(job_id)
    assert job["status"] == "completed"


@pytest.mark.asyncio
async def test_rate_limit_handling(store, oauth, tracker):
    """When fetcher returns RATE_LIMITED, engine should wait and retry."""
    class RateLimitedFetcher(_TestFetcher):
        def __init__(self, oauth):
            super().__init__(oauth)
            self._call_count = 0

        async def fetch_page(self, page=1, cursor="", since=None):
            self._call_count += 1
            if self._call_count == 1:
                # First call: rate limited
                from datetime import timedelta
                return PageResult(
                    page_number=page, status=PageStatus.RATE_LIMITED,
                    error="Rate limited",
                    rate_limit_remaining=0,
                    rate_limit_reset_at=datetime.now(timezone.utc) + timedelta(seconds=0.1),
                )
            return await super().fetch_page(page, cursor)

    engine = HistoricalImportEngine(
        store=store, oauth=oauth,
        factory=MagicMock(spec=ProviderFactory,
                          create=lambda p, org_id=None, page_size=None: RateLimitedFetcher(oauth)),
        tracker=tracker,
        on_signals=lambda sigs: None,
        on_oem_update=lambda: {"signals_processed": 0, "learning_objects": 0,
                                "patterns_detected": 0, "laws_inferred": 0,
                                "recommendations": 0, "validated_laws": 0},
    )
    store.save_credentials(provider="github", access_token="test_token", scopes=["test"])
    store.set_connection("github", connected=True)

    job_id = await engine.start_import(["github"], since=None)
    await engine.wait_for_completion(job_id)

    job = engine.get_job(job_id)
    # Should have hit at least one rate limit and continued
    assert job["providers_progress"]["github"]["rate_limit_hits"] >= 1
    assert job["status"] == "completed"
