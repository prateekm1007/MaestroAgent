"""
HistoricalImportEngine — orchestrates parallel multi-provider historical imports.

Responsibilities:
  - Start a job (one job_id per /api/imports/start call)
  - Run all providers in parallel (asyncio.gather)
  - For each provider:
      1. Create PageFetcher via ProviderFactory
      2. Resume from CheckpointStore if there's an incomplete checkpoint
      3. Stream pages through IngestionPipeline
      4. After each page, call engine.ingest() on the live OEM (continuous update)
      5. Update ProgressTracker
      6. Save checkpoints after each page
  - Cancel running jobs on user request
  - Support restart (resume from persisted checkpoints)

The engine is process-local but the CheckpointStore is shared (SQLite on disk),
so a job started in one process can be resumed in another after a restart.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import httpx

from maestro_oem.checkpoint_store import CheckpointStore
from maestro_oem.connection_manager import ConnectionManager
from maestro_oem.importers.factory import ProviderFactory
from maestro_oem.ingestion import (
    IngestionPipeline,
    PageFetcher,
    PageStatus,
    RateLimiter,
    RetryPolicy,
)
from maestro_oem.oauth_manager import OAuthError, OAuthManager
from maestro_oem.progress_tracker import ProgressTracker

logger = logging.getLogger(__name__)


# ─── Since-string parsing ───

def parse_since(since: str | None) -> datetime | None:
    """Parse a 'since' value into a datetime.

    Accepts:
      - None → all history
      - "5y", "2y", "6mo", "30d", "1w" → relative
      - ISO 8601 datetime → absolute
    """
    if not since:
        return None
    since = since.strip()

    # Relative (case-insensitive)
    since_lower = since.lower()
    if since_lower.endswith("y") and since_lower[:-1].isdigit():
        years = int(since_lower[:-1])
        return datetime.now(timezone.utc) - timedelta(days=years * 365)
    if since_lower.endswith("mo") and since_lower[:-2].isdigit():
        months = int(since_lower[:-2])
        return datetime.now(timezone.utc) - timedelta(days=months * 30)
    if since_lower.endswith("d") and since_lower[:-1].isdigit():
        days = int(since_lower[:-1])
        return datetime.now(timezone.utc) - timedelta(days=days)
    if since_lower.endswith("w") and since_lower[:-1].isdigit():
        weeks = int(since_lower[:-1])
        return datetime.now(timezone.utc) - timedelta(weeks=weeks)

    # ISO 8601
    try:
        dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


# ─── The engine ───

class HistoricalImportEngine:
    """
    Runs historical imports across multiple providers in parallel.

    Continuous OEM updates: after each page is fetched, the new signals are
    ingested into the live OEM via the on_signals callback. The dashboard
    improves in real time.

    Lifecycle:
      engine = HistoricalImportEngine(store, oauth, factory, tracker, on_signals)
      job_id = await engine.start_import(["github", "jira"], since="5y")
      progress = tracker.get_job(job_id)
      await engine.wait_for_completion(job_id)
    """

    def __init__(
        self,
        store: CheckpointStore,
        oauth: OAuthManager,
        factory: ProviderFactory,
        tracker: ProgressTracker,
        on_signals: Callable[[list[Any]], None] | None = None,
        on_oem_update: Callable[[], dict[str, int]] | None = None,
    ) -> None:
        self.store = store
        self.oauth = oauth
        self.factory = factory
        self.tracker = tracker
        self.on_signals = on_signals        # Called with new signals to ingest into live OEM
        self.on_oem_update = on_oem_update  # Called to fetch fresh OEM snapshot
        self._running_jobs: dict[str, asyncio.Task] = {}
        self._cancelled: set[str] = set()

    # ─── Job control ───

    async def start_import(
        self,
        providers: list[str],
        since: str | None = "5y",
        job_id: str | None = None,
        resume: bool = True,
    ) -> str:
        """Start a new import job (or resume an existing one).

        Returns job_id immediately; the actual import runs as a background task.
        """
        job_id = job_id or self.store.create_job(providers=providers, since=since)
        self.store.update_job_status(job_id, "running")

        # Start the background task
        task = asyncio.create_task(self._run_job(job_id, providers, since, resume))
        self._running_jobs[job_id] = task
        return job_id

    async def wait_for_completion(self, job_id: str) -> None:
        task = self._running_jobs.get(job_id)
        if task:
            await task

    def cancel_job(self, job_id: str) -> None:
        self._cancelled.add(job_id)
        task = self._running_jobs.get(job_id)
        if task:
            task.cancel()

    def cancel_for_provider(self, provider: str) -> None:
        """Cancel all jobs that include this provider (used on disconnect)."""
        for job in self.store.list_jobs():
            if job["status"] == "running" and provider in job["providers"]:
                self.cancel_job(job["job_id"])

    def list_jobs(self) -> list[dict[str, Any]]:
        return self.tracker.list_jobs()

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        job = self.tracker.get_job(job_id)
        return job.to_dict() if job else None

    # ─── Job execution ───

    async def _run_job(
        self,
        job_id: str,
        providers: list[str],
        since: str | None,
        resume: bool,
    ) -> None:
        """Main job loop. Runs all providers in parallel."""
        self.tracker.start_job(job_id, providers, since)
        self.tracker.set_phase(job_id, "importing")

        since_dt = parse_since(since)

        # Run all providers concurrently
        tasks = [
            self._run_provider(job_id, provider, since_dt, resume)
            for provider in providers
        ]
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        except asyncio.CancelledError:
            # Job was cancelled externally; mark and exit
            self.store.update_job_status(job_id, "cancelled")
            self.tracker.set_job_status(job_id, "cancelled")
            self._running_jobs.pop(job_id, None)
            self._cancelled.discard(job_id)
            return

        # Update job status
        any_failed = any(isinstance(r, Exception) for r in results)
        all_completed = all(
            not isinstance(r, Exception) and r for r in results
        )
        if any_failed and not all_completed:
            self.store.update_job_status(job_id, "failed", error="Some providers failed")
            self.tracker.set_job_status(job_id, "failed", "Some providers failed")
        elif self._is_cancelled(job_id):
            self.store.update_job_status(job_id, "cancelled")
            self.tracker.set_job_status(job_id, "cancelled")
        else:
            self.store.update_job_status(job_id, "completed")
            self.tracker.set_job_status(job_id, "completed")

        # Final OEM snapshot
        if self.on_oem_update:
            try:
                snapshot = self.on_oem_update()
                self.tracker.update_oem_snapshot(job_id, **snapshot)
            except Exception as e:
                logger.warning("Final OEM snapshot failed: %s", e)

        # Cleanup
        self._running_jobs.pop(job_id, None)
        self._cancelled.discard(job_id)

    def _is_cancelled(self, job_id: str) -> bool:
        return job_id in self._cancelled

    async def _run_provider(
        self,
        job_id: str,
        provider: str,
        since: datetime | None,
        resume: bool,
    ) -> bool:
        """Run ingestion for one provider. Returns True on success."""
        # Check if provider is connected
        if not self.oauth.store.load_credentials(provider):
            self.tracker.mark_provider_failed(
                job_id, provider, f"Provider {provider} not connected"
            )
            return False

        # Create fetcher
        try:
            fetcher = self.factory.create(provider)
        except Exception as e:
            self.tracker.mark_provider_failed(job_id, provider, str(e))
            return False

        # Estimate total pages for progress UI
        try:
            total_pages = await fetcher.estimate_total_pages(since)
            total_events = total_pages * 100  # Rough estimate
            self.tracker.mark_provider_running(job_id, provider, total_estimated=total_events)
        except Exception as e:
            logger.warning("Estimate failed for %s: %s", provider, e)
            self.tracker.mark_provider_running(job_id, provider, total_estimated=0)

        # Load checkpoint if resuming
        checkpoint = None
        if resume:
            checkpoint = self.store.load_checkpoint(job_id, provider, "all")
            if checkpoint and checkpoint["completed"]:
                logger.info("Provider %s already completed in job %s", provider, job_id)
                self.tracker.mark_provider_completed(job_id, provider)
                return True

        # Run the ingestion loop
        try:
            await self._ingest_loop(job_id, provider, fetcher, since, checkpoint)
            self.tracker.mark_provider_completed(job_id, provider)
            return True
        except asyncio.CancelledError:
            logger.info("Provider %s import cancelled", provider)
            # Mark the provider as paused (not failed); resume on restart
            if job_id in self.tracker._jobs:
                pp = self.tracker._jobs[job_id].provider_progress.get(provider)
                if pp:
                    pp.status = "paused"
            return False
        except Exception as e:
            logger.exception("Provider %s import failed", provider)
            self.tracker.mark_provider_failed(job_id, provider, str(e))
            return False
        finally:
            try:
                await fetcher.http.aclose()
            except Exception:
                pass

    async def _ingest_loop(
        self,
        job_id: str,
        provider: str,
        fetcher: PageFetcher,
        since: datetime | None,
        existing_checkpoint: dict[str, Any] | None,
    ) -> None:
        """The actual page-fetch loop for one provider."""
        rate_limiter = RateLimiter(provider)
        retry_policy = RetryPolicy(max_retries=5)

        # Resume state
        page = 1
        cursor = ""
        if existing_checkpoint:
            page = existing_checkpoint.get("last_page", 0) + 1
            cursor = existing_checkpoint.get("last_cursor", "")

        # Initialize checkpoint record
        checkpoint_data = {
            "job_id": job_id,
            "provider": provider,
            "resource_type": "all",
            "sync_mode": "incremental" if since else "full",
            "last_page": page - 1,
            "last_cursor": cursor,
            "total_pages_estimated": existing_checkpoint.get("total_pages_estimated", 0) if existing_checkpoint else 0,
            "pages_completed": existing_checkpoint.get("pages_completed", 0) if existing_checkpoint else 0,
            "signals_produced": existing_checkpoint.get("signals_produced", 0) if existing_checkpoint else 0,
            "errors": existing_checkpoint.get("errors", 0) if existing_checkpoint else 0,
            "started_at": existing_checkpoint.get("started_at", datetime.now(timezone.utc).isoformat()) if existing_checkpoint else datetime.now(timezone.utc).isoformat(),
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "completed": False,
        }
        self.store.save_checkpoint(checkpoint_data)

        # Create the pipeline (for the normalizer)
        pipeline = IngestionPipeline()

        consecutive_errors = 0
        signals_since_last_oem_update = 0
        OEM_UPDATE_BATCH_SIZE = 100  # Update OEM every 100 signals for responsiveness

        while True:
            if self._is_cancelled(job_id):
                checkpoint_data["completed"] = True
                self.store.save_checkpoint(checkpoint_data)
                return

            # Rate limit check
            if not rate_limiter.can_request():
                wait = min(rate_limiter.wait_time(), 60.0)
                logger.info("Rate limited on %s, waiting %.1fs", provider, wait)
                await asyncio.sleep(wait)
                continue

            # Fetch with retry
            page_result = await self._fetch_with_retry(
                fetcher, page, cursor, since, rate_limiter, retry_policy, job_id, provider
            )

            if page_result.status == PageStatus.SUCCESS:
                consecutive_errors = 0
                rate_limiter.record_request()

                # Normalize and ingest signals
                new_signals = []
                for item in page_result.items:
                    try:
                        normalized = fetcher.normalize_item(item)
                        signal = pipeline._create_signal(provider, normalized)
                        if signal:
                            new_signals.append(signal)
                    except Exception as e:
                        logger.debug("Signal creation failed: %s", e)
                        checkpoint_data["errors"] += 1

                # Stream into live OEM
                if new_signals and self.on_signals:
                    try:
                        self.on_signals(new_signals)
                        signals_since_last_oem_update += len(new_signals)
                    except Exception as e:
                        logger.warning("Live OEM ingest failed: %s", e)

                # Update OEM snapshot periodically
                if signals_since_last_oem_update >= OEM_UPDATE_BATCH_SIZE and self.on_oem_update:
                    try:
                        snapshot = self.on_oem_update()
                        self.tracker.update_oem_snapshot(job_id, **snapshot)
                        signals_since_last_oem_update = 0
                    except Exception as e:
                        logger.debug("OEM snapshot failed: %s", e)

                # Update progress + checkpoint
                self.tracker.record_page(
                    job_id, provider,
                    events=len(new_signals),
                    pages_fetched=1,
                    errors=1 if not new_signals and page_result.items else 0,
                )
                checkpoint_data["pages_completed"] += 1
                checkpoint_data["signals_produced"] += len(new_signals)
                checkpoint_data["last_page"] = page
                checkpoint_data["last_updated"] = datetime.now(timezone.utc).isoformat()
                self.store.save_checkpoint(checkpoint_data)

                # Advance cursor
                if page_result.next_cursor:
                    cursor = page_result.next_cursor
                    page += 1
                elif page_result.next_page:
                    page = page_result.next_page
                else:
                    # No more pages
                    break

            elif page_result.status == PageStatus.RATE_LIMITED:
                rate_limiter.record_request()
                reset_at = page_result.rate_limit_reset_at
                wait_seconds = 60.0
                if reset_at:
                    wait_seconds = max(1.0, (reset_at - datetime.now(timezone.utc)).total_seconds())
                    wait_seconds = min(wait_seconds, 300.0)  # Cap at 5 min
                logger.info("Rate limited by %s, waiting %.1fs", provider, wait_seconds)
                self.tracker.record_page(job_id, provider, rate_limit_hits=1)
                await asyncio.sleep(wait_seconds)
                continue

            elif page_result.status == PageStatus.AUTH_EXPIRED:
                logger.info("Auth expired for %s, refreshing", provider)
                try:
                    await asyncio.to_thread(self.oauth.refresh_token, provider)
                except OAuthError as e:
                    checkpoint_data["errors"] += 1
                    self.tracker.record_page(job_id, provider, errors=1)
                    self.tracker.mark_provider_failed(job_id, provider, f"Auth refresh failed: {e}")
                    return
                continue

            elif page_result.status == PageStatus.ERROR:
                consecutive_errors += 1
                checkpoint_data["errors"] += 1
                self.tracker.record_page(job_id, provider, errors=1)

                if consecutive_errors >= 10:
                    logger.error("Too many consecutive errors for %s, giving up", provider)
                    return

                # Advance cursor if possible
                if page_result.next_cursor:
                    cursor = page_result.next_cursor
                    page += 1
                elif page_result.next_page:
                    page = page_result.next_page
                else:
                    page += 1
                continue

            else:
                # SKIPPED or unknown
                if page_result.next_cursor:
                    cursor = page_result.next_cursor
                page += 1
                continue

        # Mark complete
        checkpoint_data["completed"] = True
        checkpoint_data["last_updated"] = datetime.now(timezone.utc).isoformat()
        self.store.save_checkpoint(checkpoint_data)

    async def _fetch_with_retry(
        self,
        fetcher: PageFetcher,
        page: int,
        cursor: str,
        since: datetime | None,
        rate_limiter: RateLimiter,
        retry_policy: RetryPolicy,
        job_id: str,
        provider: str,
    ):
        """Fetch one page with retry/backoff."""
        attempt = 0
        while True:
            try:
                return await fetcher.fetch_page(page, cursor, since)
            except Exception as e:
                attempt += 1
                logger.warning(
                    "Fetch failed for %s page %d (attempt %d): %s",
                    provider, page, attempt, e,
                )
                if attempt >= retry_policy.max_retries:
                    from maestro_oem.ingestion import PageResult, PageStatus
                    return PageResult(
                        page_number=page,
                        status=PageStatus.ERROR,
                        error=str(e),
                    )
                delay = retry_policy.get_delay(attempt)
                await asyncio.sleep(delay)

    # ─── Resume after restart ───

    async def resume_incomplete_jobs(self) -> list[str]:
        """Resume all jobs that were running when the process died.

        Called at server startup.
        """
        resumed = []
        for job in self.store.list_jobs():
            if job["status"] != "running":
                continue
            incomplete = self.store.list_incomplete_checkpoints(job["job_id"])
            if not incomplete:
                # Job was actually complete; mark it
                self.store.update_job_status(job["job_id"], "completed")
                continue
            logger.info("Resuming job %s with %d incomplete providers",
                        job["job_id"], len(incomplete))
            new_job_id = await self.start_import(
                providers=job["providers"],
                since=job["since"],
                job_id=job["job_id"],
                resume=True,
            )
            resumed.append(new_job_id)
        return resumed
