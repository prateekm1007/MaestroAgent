"""
API Performance SLO Gates.

Round 71 Step 4: These tests measure real API route performance and enforce
hard SLO thresholds. Fail CI on regression.

The CEO's directive requires:
- Measure real app route performance (not just static page)
- API latency SLO gates for /api/oem/ceo-briefing, /api/oem/ask, /api/imports/*
- Track p50/p95/p99 and fail on regression thresholds
"""
from __future__ import annotations

import os
import time
import statistics
import pytest
from fastapi.testclient import TestClient




# SLO thresholds (milliseconds)
SLO_P50 = 200   # p50 must be under 200ms
SLO_P95 = 500   # p95 must be under 500ms
SLO_P99 = 1000  # p99 must be under 1000ms (generous for CI)

# Number of requests per endpoint for stable percentiles
SAMPLE_SIZE = 20


class TestAPIPerformanceSLOs:
    """API latency must stay within SLOs. Fail CI on regression."""

    ENDPOINTS = [
        ("/api/oem/ceo-briefing", "CEO Briefing"),
        ("/api/oem/ask?q=payments", "Ask"),
        ("/api/oem/timeline?limit=10", "Timeline"),
        ("/api/oem/laws", "Laws"),
        ("/api/oauth/status", "OAuth Status"),
        ("/api/oem/tasks", "Tasks"),
        ("/api/oem/commitments", "Commitments"),
        ("/api/oem/contradictions", "Contradictions"),
        ("/api/oem/predictions", "Predictions"),
        ("/api/oem/unknowns", "Unknowns"),
        ("/metrics", "Prometheus Metrics"),
    ]

    @pytest.mark.parametrize("endpoint,label", ENDPOINTS)
    def test_p95_latency_within_slo(self, client, endpoint, label):
        """p95 latency must be under 500ms for all critical endpoints."""
        latencies = []
        for _ in range(SAMPLE_SIZE):
            start = time.perf_counter()
            resp = client.get(endpoint)
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        assert resp.status_code == 200, f"{label} returned {resp.status_code}"

        latencies.sort()
        p50 = statistics.median(latencies)
        p95 = latencies[int(len(latencies) * 0.95)]
        p99 = latencies[int(len(latencies) * 0.99)]

        # Log for artifact
        print(f"\n{label} ({endpoint}):")
        print(f"  p50={p50:.0f}ms  p95={p95:.0f}ms  p99={p99:.0f}ms")
        print(f"  SLO: p50<{SLO_P50}ms  p95<{SLO_P95}ms  p99<{SLO_P99}ms")

        assert p50 < SLO_P50, \
            f"{label} p50={p50:.0f}ms exceeds SLO of {SLO_P50}ms"
        assert p95 < SLO_P95, \
            f"{label} p95={p95:.0f}ms exceeds SLO of {SLO_P95}ms"
        assert p99 < SLO_P99, \
            f"{label} p99={p99:.0f}ms exceeds SLO of {SLO_P99}ms"

    def test_writeback_preview_latency(self, client):
        """WriteBack preview must respond in under 500ms p95."""
        latencies = []
        for i in range(SAMPLE_SIZE):
            start = time.perf_counter()
            resp = client.post("/api/oem/writeback", json={
                "provider": "jira",
                "action_type": "create_issue",
                "params": {"project": "ENG", "summary": f"Perf test {i}", "description": "Test"}
            })
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        assert resp.status_code == 200

        latencies.sort()
        p95 = latencies[int(len(latencies) * 0.95)]
        print(f"\nWriteBack Preview: p95={p95:.0f}ms")
        assert p95 < SLO_P95, f"WriteBack p95={p95:.0f}ms exceeds SLO of {SLO_P95}ms"

    def test_simulator_latency(self, client):
        """Simulator must respond in under 500ms p95."""
        latencies = []
        for _ in range(SAMPLE_SIZE):
            start = time.perf_counter()
            resp = client.post("/api/oem/simulate", json={"inputs": {"hire_count": 5}})
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        assert resp.status_code == 200

        latencies.sort()
        p95 = latencies[int(len(latencies) * 0.95)]
        print(f"\nSimulator: p95={p95:.0f}ms")
        assert p95 < SLO_P95, f"Simulator p95={p95:.0f}ms exceeds SLO of {SLO_P95}ms"
