"""S2-6 LATENCY journey gate — LLM circuit breaker trips and falls back.

Auditor found: p95 Ask latency of 28-37s — the latency cliff. Root cause:
the LLM call (Gemma 12B via OpenRouter) takes 15-25s and the user sees
nothing until the full response returns.

FIX (Kimi K3 design, P40):
- Circuit breaker tracks last N LLM call latencies (60s rolling window).
- If 3 consecutive calls took >25s, the breaker trips for 60s.
- While tripped, ask requests skip the LLM and use rules-only with
  calibration_note='S2-6: LLM circuit-breaker tripped — answer is
  rules-only (latency protection).'
- The gate threshold (p95 < 10s under 5 concurrent) is NEVER lowered
  (forbidden action 1). If the gate fails, the product falls back to
  rules-only — it does NOT weaken the gate.

This test verifies the breaker mechanics by directly invoking
_record_llm_latency and _is_llm_breaker_tripped. The end-to-end
latency gate (5 concurrent asks < p95 10s) lives in ops/test_user_journey.py
and runs against the deployed backend.

Run:
  cd /home/z/my-project/MaestroAgent/download/MaestroAgent/maestro-personal
  python -m pytest tests/test_S2_06_latency_breaker.py -v
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
os.environ.setdefault("MAESTRO_ENV", "dev")
_env_local = Path("/home/z/my-project/.env.local")
if _env_local.exists():
    for line in _env_local.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


from maestro_personal_shell.routers.ask import (
    _record_llm_latency,
    _is_llm_breaker_tripped,
    _llm_breaker_status,
    _LLM_LATENCY_RECORDS,
    _LLM_BREAKER_TRIPPED_UNTIL,
    _LLM_SLOW_THRESHOLD_S,
    _LLM_BREAKER_TRIP_COUNT,
)


@pytest.fixture(autouse=True)
def _reset_breaker():
    """Reset the breaker state before each test (P35 — isolated state)."""
    import maestro_personal_shell.routers.ask as _ask_mod
    # Clear the latency records and breaker trip
    _ask_mod._LLM_LATENCY_RECORDS.clear()
    _ask_mod._LLM_BREAKER_TRIPPED_UNTIL = 0.0
    yield
    _ask_mod._LLM_LATENCY_RECORDS.clear()
    _ask_mod._LLM_BREAKER_TRIPPED_UNTIL = 0.0


def test_breaker_does_not_trip_on_fast_calls():
    """S2-6: 3 fast LLM calls (<25s each) MUST NOT trip the breaker."""
    assert not _is_llm_breaker_tripped(), "breaker should not be tripped initially"
    _record_llm_latency(5.0)
    _record_llm_latency(10.0)
    _record_llm_latency(15.0)
    assert not _is_llm_breaker_tripped(), (
        "S2-6 violation: breaker tripped after 3 fast calls (<25s each). "
        "The breaker should only trip after 3 SLOW calls (>25s each)."
    )
    status = _llm_breaker_status()
    assert status["tripped"] is False
    assert status["slow_call_count"] == 0


def test_breaker_trips_after_3_slow_calls():
    """S2-6: 3 consecutive slow LLM calls (>25s each) MUST trip the breaker."""
    _record_llm_latency(26.0)
    assert not _is_llm_breaker_tripped(), "1 slow call should not trip"
    _record_llm_latency(28.0)
    assert not _is_llm_breaker_tripped(), "2 slow calls should not trip"
    _record_llm_latency(30.0)
    assert _is_llm_breaker_tripped(), (
        "S2-6 violation: breaker did NOT trip after 3 consecutive slow "
        "calls (>25s each). The 4th request would still hit the LLM, "
        "perpetuating the latency cliff."
    )
    status = _llm_breaker_status()
    assert status["tripped"] is True
    assert status["slow_call_count"] >= 3


def test_breaker_resets_after_window():
    """S2-6: the breaker auto-resets after the 60s window expires."""
    _record_llm_latency(30.0)
    _record_llm_latency(30.0)
    _record_llm_latency(30.0)
    assert _is_llm_breaker_tripped()

    # Manually expire the breaker by setting the trip-until time to the past
    import maestro_personal_shell.routers.ask as _ask_mod
    _ask_mod._LLM_BREAKER_TRIPPED_UNTIL = time.time() - 1.0
    assert not _is_llm_breaker_tripped(), (
        "S2-6 violation: breaker did not auto-reset after the 60s window."
    )


def test_breaker_status_endpoint_reachable():
    """S2-6 P40: the /api/ask/breaker-status endpoint must be reachable
    for ops + journey-gate observability."""
    from fastapi.testclient import TestClient
    from maestro_personal_shell.api import app
    with TestClient(app) as c:
        # The endpoint is include_in_schema=False but still registered
        r = c.get("/api/ask/breaker-status")
        # May require auth — that's fine, the test just verifies the route exists
        # (401 is acceptable; 404 means the route is missing)
        assert r.status_code != 404, (
            f"S2-6: /api/ask/breaker-status returned 404 — the observability "
            f"endpoint is missing. Got: {r.status_code}"
        )


def test_breaker_threshold_not_lowered():
    """S2-6 forbidden action 1: the slow threshold MUST be 25s, not lower.
    The breaker threshold is a trust property — never weaken it to silence
    a red. If the gate fails, the product falls back, NOT the gate weakens."""
    assert _LLM_SLOW_THRESHOLD_S == 25.0, (
        f"S2-6 forbidden-action-1 violation: LLM_SLOW_THRESHOLD_S is "
        f"{_LLM_SLOW_THRESHOLD_S}, expected 25.0. The threshold MUST NOT "
        f"be lowered to silence a red — the product falls back instead."
    )
    assert _LLM_BREAKER_TRIP_COUNT == 3, (
        f"S2-6: LLM_BREAKER_TRIP_COUNT is {_LLM_BREAKER_TRIP_COUNT}, "
        f"expected 3. The trip count MUST NOT be raised to make the breaker "
        f"harder to trip."
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
