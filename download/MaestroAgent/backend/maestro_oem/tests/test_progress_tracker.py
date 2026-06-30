"""Unit tests for ProgressTracker."""

import time

import pytest

from maestro_oem.progress_tracker import ProgressTracker


@pytest.fixture
def tracker():
    return ProgressTracker()


def test_start_job(tracker):
    job = tracker.start_job("job-1", ["github", "jira"], since="5y")
    assert job.job_id == "job-1"
    assert job.providers == ["github", "jira"]
    assert job.status == "pending"
    assert job.phase == "connecting"
    assert "github" in job.provider_progress
    assert "jira" in job.provider_progress


def test_record_page_updates_progress(tracker):
    tracker.start_job("job-1", ["github"], since="5y")
    tracker.mark_provider_running("job-1", "github", total_estimated=1000)
    tracker.record_page("job-1", "github", events=100, pages_fetched=1)
    tracker.record_page("job-1", "github", events=100, pages_fetched=1)

    job = tracker.get_job("job-1")
    pp = job.provider_progress["github"]
    assert pp.events_processed == 200
    assert pp.pages_fetched == 2
    assert pp.eta_seconds > 0  # Should have ETA based on throughput


def test_mark_provider_completed(tracker):
    tracker.start_job("job-1", ["github"], since="5y")
    tracker.mark_provider_running("job-1", "github")
    tracker.mark_provider_completed("job-1", "github")

    job = tracker.get_job("job-1")
    assert job.provider_progress["github"].status == "completed"
    assert job.status == "completed"  # All providers done → job done


def test_mark_provider_failed(tracker):
    tracker.start_job("job-1", ["github"], since="5y")
    tracker.mark_provider_failed("job-1", "github", "Token expired")

    job = tracker.get_job("job-1")
    assert job.provider_progress["github"].status == "failed"
    assert job.provider_progress["github"].last_error == "Token expired"


def test_oem_snapshot_update(tracker):
    tracker.start_job("job-1", ["github"], since="5y")
    tracker.update_oem_snapshot(
        "job-1",
        signals_processed=100,
        learning_objects=80,
        patterns_detected=12,
        laws_inferred=3,
        recommendations=5,
        validated_laws=2,
    )
    job = tracker.get_job("job-1")
    assert job.oem_snapshot.signals_processed == 100
    assert job.oem_snapshot.patterns_detected == 12
    assert job.oem_snapshot.laws_inferred == 3
    assert job.oem_snapshot.last_updated is not None


def test_subscribers_receive_updates(tracker):
    updates = []
    tracker.start_job("job-1", ["github"], since="5y")
    tracker.subscribe("job-1", lambda snap: updates.append(snap))

    # record_page triggers a broadcast (throttled to 4Hz, so we may need to wait)
    tracker.record_page("job-1", "github", events=100)
    # Force broadcast
    tracker.force_broadcast("job-1")

    assert len(updates) >= 1
    assert "providers_progress" in updates[-1]


def test_force_broadcast_bypasses_throttle(tracker):
    updates = []
    tracker.start_job("job-1", ["github"], since="5y")
    tracker.subscribe("job-1", lambda snap: updates.append(snap))

    # Multiple rapid updates
    for i in range(10):
        tracker.record_page("job-1", "github", events=10)
        tracker.force_broadcast("job-1")  # Bypass throttle

    assert len(updates) >= 10


def test_total_events_aggregation(tracker):
    tracker.start_job("job-1", ["github", "jira"], since="5y")
    tracker.record_page("job-1", "github", events=100)
    tracker.record_page("job-1", "jira", events=50)

    job = tracker.get_job("job-1")
    assert job.to_dict()["total_events"] == 150


def test_cancel_sets_status(tracker):
    tracker.start_job("job-1", ["github"], since="5y")
    tracker.set_job_status("job-1", "cancelled")
    job = tracker.get_job("job-1")
    assert job.status == "cancelled"
    assert job.completed_at is not None
    assert job.phase == "cancelled"


def test_unsubscribe(tracker):
    updates = []
    tracker.start_job("job-1", ["github"], since="5y")
    cb = lambda snap: updates.append(snap)
    tracker.subscribe("job-1", cb)
    tracker.unsubscribe("job-1", cb)
    tracker.force_broadcast("job-1")
    # Only the initial snapshot from subscribe should be in updates
    assert len(updates) <= 1
