"""
V8 Daily Work #1 — Organizational Timeline. Regression tests.

GET /api/oem/timeline returns a paginated, filterable chronological view
of ALL signals across ALL providers.
"""

from __future__ import annotations

import os
import pathlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    app_dir = str(pathlib.Path(__file__).resolve().parents[3])
    os.environ.setdefault("MAESTRO_APP_DIR", app_dir)
    os.environ.setdefault("MAESTRO_AUTH_DB", "/tmp/maestro_test_timeline_auth.db")
    os.environ.setdefault("MAESTRO_ADMIN_PASSWORD", "test")
    from maestro_api.main import create_app
    app = create_app(db_path=":memory:")
    with TestClient(app) as c:
        yield c


class TestTimelineEndpoint:
    """The /api/oem/timeline endpoint must return paginated, filterable signals."""

    def test_timeline_returns_200(self, client) -> None:
        r = client.get("/api/oem/timeline")
        assert r.status_code == 200

    def test_timeline_has_required_structure(self, client) -> None:
        r = client.get("/api/oem/timeline")
        data = r.json()
        assert "signals" in data
        assert "pagination" in data
        assert "filters_applied" in data

    def test_timeline_returns_signals_from_demo_seed(self, client) -> None:
        r = client.get("/api/oem/timeline")
        data = r.json()
        assert data["pagination"]["total"] > 0, "Demo seed should produce signals"
        assert len(data["signals"]) > 0

    def test_timeline_signals_have_required_fields(self, client) -> None:
        r = client.get("/api/oem/timeline")
        data = r.json()
        for sig in data["signals"]:
            assert "signal_id" in sig
            assert "type" in sig
            assert "provider" in sig
            assert "timestamp" in sig
            assert "actor" in sig
            assert "artifact" in sig
            assert "domain" in sig

    def test_timeline_sorted_descending(self, client) -> None:
        """Signals must be sorted by timestamp descending (most recent first)."""
        r = client.get("/api/oem/timeline", params={"limit": 10})
        data = r.json()
        timestamps = [s["timestamp"] for s in data["signals"]]
        assert timestamps == sorted(timestamps, reverse=True), (
            "Timeline signals are not sorted descending by timestamp"
        )

    def test_timeline_pagination(self, client) -> None:
        """Pagination must work correctly."""
        r1 = client.get("/api/oem/timeline", params={"limit": 5, "offset": 0})
        data1 = r1.json()
        assert len(data1["signals"]) <= 5
        assert data1["pagination"]["has_more"] is True

        r2 = client.get("/api/oem/timeline", params={"limit": 5, "offset": 5})
        data2 = r2.json()
        # The second page should have different signals
        ids1 = {s["signal_id"] for s in data1["signals"]}
        ids2 = {s["signal_id"] for s in data2["signals"]}
        assert not ids1 & ids2, "Pagination returned overlapping signals"

    def test_timeline_filter_by_provider(self, client) -> None:
        """Filtering by provider must work."""
        r = client.get("/api/oem/timeline", params={"provider": "github"})
        data = r.json()
        for sig in data["signals"]:
            assert sig["provider"] == "github", (
                f"Provider filter failed: got {sig['provider']}"
            )

    def test_timeline_filter_by_domain(self, client) -> None:
        """Filtering by domain must work."""
        r = client.get("/api/oem/timeline", params={"domain": "payments"})
        data = r.json()
        for sig in data["signals"]:
            assert sig["domain"] == "payments", (
                f"Domain filter failed: got {sig['domain']}"
            )

    def test_timeline_filter_by_actor(self, client) -> None:
        """Filtering by actor must work."""
        # First get an actor from the unfiltered timeline
        r0 = client.get("/api/oem/timeline", params={"limit": 1})
        actor = r0.json()["signals"][0]["actor"]
        r = client.get("/api/oem/timeline", params={"actor": actor})
        data = r.json()
        for sig in data["signals"]:
            assert sig["actor"] == actor

    def test_timeline_filters_applied_echoed(self, client) -> None:
        """The response must echo which filters were applied."""
        r = client.get("/api/oem/timeline", params={"provider": "github", "domain": "payments"})
        data = r.json()
        assert data["filters_applied"]["provider"] == ["github"]
        assert data["filters_applied"]["domain"] == ["payments"]

    def test_timeline_limit_validation(self, client) -> None:
        """Limit must be between 1 and 500."""
        r = client.get("/api/oem/timeline", params={"limit": 0})
        assert r.status_code == 422
        r = client.get("/api/oem/timeline", params={"limit": 501})
        assert r.status_code == 422
