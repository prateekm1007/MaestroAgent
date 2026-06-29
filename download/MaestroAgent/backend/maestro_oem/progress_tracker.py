"""
ProgressTracker — real-time import progress tracking with WebSocket broadcast.

Tracks:
  - Per-job progress (events processed, ETA, current phase)
  - Per-provider sub-progress (pages, signals, rate limits)
  - Live OEM state changes (patterns discovered, laws emerging, recs improving)

Broadcasts updates to all subscribed WebSocket clients. Subscribers receive
a JSON snapshot every time progress changes (throttled to 4 Hz to avoid
flooding slow clients).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class ProviderProgress:
    provider: str
    status: str = "pending"           # pending|running|completed|failed|paused
    events_processed: int = 0
    pages_fetched: int = 0
    pages_skipped: int = 0
    errors: int = 0
    rate_limit_hits: int = 0
    started_at: float | None = None
    last_event_at: float | None = None
    eta_seconds: float = 0.0
    total_estimated: int = 0
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        elapsed = (time.time() - self.started_at) if self.started_at else 0.0
        throughput = self.events_processed / elapsed if elapsed > 0 else 0.0
        return {
            "provider": self.provider,
            "status": self.status,
            "events_processed": self.events_processed,
            "pages_fetched": self.pages_fetched,
            "pages_skipped": self.pages_skipped,
            "errors": self.errors,
            "rate_limit_hits": self.rate_limit_hits,
            "eta_seconds": round(self.eta_seconds, 1),
            "total_estimated": self.total_estimated,
            "throughput_per_sec": round(throughput, 1),
            "elapsed_seconds": round(elapsed, 1),
            "last_error": self.last_error,
        }


@dataclass
class OEMSnapshot:
    """Live snapshot of the OEM's state — used to show 'patterns discovered',
    'laws emerging', 'recommendations improving' in the UI."""
    signals_processed: int = 0
    learning_objects: int = 0
    patterns_detected: int = 0
    laws_inferred: int = 0
    recommendations: int = 0
    validated_laws: int = 0
    last_updated: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "signals_processed": self.signals_processed,
            "learning_objects": self.learning_objects,
            "patterns_detected": self.patterns_detected,
            "laws_inferred": self.laws_inferred,
            "recommendations": self.recommendations,
            "validated_laws": self.validated_laws,
            "last_updated": self.last_updated,
        }


@dataclass
class JobProgress:
    job_id: str
    providers: list[str]
    since: str | None
    status: str = "pending"           # pending|running|completed|failed|cancelled
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    phase: str = "initializing"        # initializing|connecting|importing|building|completed
    provider_progress: dict[str, ProviderProgress] = field(default_factory=dict)
    oem_snapshot: OEMSnapshot = field(default_factory=OEMSnapshot)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "providers": self.providers,
            "since": self.since,
            "status": self.status,
            "phase": self.phase,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_seconds": round(time.time() - self.started_at, 1),
            "total_events": sum(p.events_processed for p in self.provider_progress.values()),
            "providers_progress": {
                p: pp.to_dict() for p, pp in self.provider_progress.items()
            },
            "oem": self.oem_snapshot.to_dict(),
            "error": self.error,
        }


class ProgressTracker:
    """
    Tracks all in-flight import jobs and broadcasts progress to subscribers.

    Singleton instance lives in oem_state alongside the OEM.
    """

    BROADCAST_THROTTLE_SECONDS = 0.25  # Max 4 broadcasts/sec

    def __init__(self) -> None:
        self._jobs: dict[str, JobProgress] = {}
        self._subscribers: dict[str, list[Callable[[dict[str, Any]], None]]] = {}
        self._last_broadcast: dict[str, float] = {}
        self._lock = asyncio.Lock() if asyncio.get_event_loop_policy() else None

    # ─── Job lifecycle ───

    def start_job(
        self, job_id: str, providers: list[str], since: str | None = None
    ) -> JobProgress:
        job = JobProgress(job_id=job_id, providers=list(providers), since=since)
        job.phase = "connecting"
        for p in providers:
            pp = ProviderProgress(provider=p)
            pp.started_at = time.time()
            job.provider_progress[p] = pp
        self._jobs[job_id] = job
        self._broadcast(job_id)
        return job

    def get_job(self, job_id: str) -> JobProgress | None:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[dict[str, Any]]:
        return [j.to_dict() for j in self._jobs.values()]

    def set_phase(self, job_id: str, phase: str) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        job.phase = phase
        self._broadcast(job_id)

    def set_job_status(self, job_id: str, status: str, error: str | None = None) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        job.status = status
        if error:
            job.error = error
        if status in ("completed", "failed", "cancelled"):
            job.completed_at = time.time()
            job.phase = status
        self._broadcast(job_id)

    # ─── Provider progress ───

    def mark_provider_running(self, job_id: str, provider: str, total_estimated: int = 0) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        pp = job.provider_progress.get(provider)
        if not pp:
            pp = ProviderProgress(provider=provider, started_at=time.time())
            job.provider_progress[provider] = pp
        pp.status = "running"
        pp.total_estimated = total_estimated
        self._broadcast(job_id)

    def record_page(
        self,
        job_id: str,
        provider: str,
        events: int = 0,
        pages_fetched: int = 1,
        pages_skipped: int = 0,
        errors: int = 0,
        rate_limit_hits: int = 0,
    ) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        pp = job.provider_progress.get(provider)
        if not pp:
            pp = ProviderProgress(provider=provider, started_at=time.time())
            job.provider_progress[provider] = pp
        pp.events_processed += events
        pp.pages_fetched += pages_fetched
        pp.pages_skipped += pages_skipped
        pp.errors += errors
        pp.rate_limit_hits += rate_limit_hits
        pp.last_event_at = time.time()
        # ETA based on throughput so far
        if pp.started_at and pp.events_processed > 0:
            elapsed = pp.last_event_at - pp.started_at
            if elapsed > 0 and pp.total_estimated > pp.events_processed:
                rate = pp.events_processed / elapsed
                remaining = pp.total_estimated - pp.events_processed
                pp.eta_seconds = remaining / max(0.01, rate)
        self._broadcast(job_id)

    def mark_provider_completed(self, job_id: str, provider: str) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        pp = job.provider_progress.get(provider)
        if pp:
            pp.status = "completed"
            pp.eta_seconds = 0.0
        # Check if all providers done
        if all(p.status == "completed" for p in job.provider_progress.values()):
            job.status = "completed"
            job.completed_at = time.time()
            job.phase = "completed"
        self._broadcast(job_id)

    def mark_provider_failed(self, job_id: str, provider: str, error: str) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        pp = job.provider_progress.get(provider)
        if pp:
            pp.status = "failed"
            pp.last_error = error
        self._broadcast(job_id)

    # ─── OEM snapshot updates ───

    def update_oem_snapshot(
        self,
        job_id: str,
        signals_processed: int,
        learning_objects: int,
        patterns_detected: int,
        laws_inferred: int,
        recommendations: int,
        validated_laws: int = 0,
    ) -> None:
        """Update the OEM snapshot shown in the UI. Called after each batch
        of signals is ingested into the OEM."""
        job = self._jobs.get(job_id)
        if not job:
            return
        snap = job.oem_snapshot
        snap.signals_processed = signals_processed
        snap.learning_objects = learning_objects
        snap.patterns_detected = patterns_detected
        snap.laws_inferred = laws_inferred
        snap.recommendations = recommendations
        snap.validated_laws = validated_laws
        snap.last_updated = time.time()
        self._broadcast(job_id)

    # ─── Subscribers ───

    def subscribe(self, job_id: str, callback: Callable[[dict[str, Any]], None]) -> None:
        self._subscribers.setdefault(job_id, []).append(callback)
        # Send immediate snapshot
        job = self._jobs.get(job_id)
        if job:
            try:
                callback(job.to_dict())
            except Exception as e:
                logger.warning("Subscriber callback failed: %s", e)

    def unsubscribe(self, job_id: str, callback: Callable[[dict[str, Any]], None]) -> None:
        if job_id in self._subscribers:
            try:
                self._subscribers[job_id].remove(callback)
            except ValueError:
                pass

    # ─── Broadcast ───

    def _broadcast(self, job_id: str) -> None:
        """Throttled broadcast to all subscribers of a job."""
        now = time.time()
        last = self._last_broadcast.get(job_id, 0.0)
        if now - last < self.BROADCAST_THROTTLE_SECONDS:
            return
        self._last_broadcast[job_id] = now

        job = self._jobs.get(job_id)
        if not job:
            return
        snapshot = job.to_dict()
        for cb in list(self._subscribers.get(job_id, [])):
            try:
                cb(snapshot)
            except Exception as e:
                logger.warning("Subscriber callback failed: %s", e)
                # Don't remove — might be transient

    def force_broadcast(self, job_id: str) -> None:
        """Bypass throttle (used on completion / error)."""
        self._last_broadcast[job_id] = 0.0
        self._broadcast(job_id)
