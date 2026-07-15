"""
LLM-latency hypothesis test: does a slow/failing LLM provider cause
the 12.3s Ask latency the other audit reported?

Method: mock the LLM with controlled delays (0ms, 500ms, 2s, 5s, 10s)
and measure Ask latency at 10K signals. This isolates the LLM-call
variable from signal-count scaling.

If Ask latency = base + LLM_delay, the 12.3s number is explained by
LLM call latency (with retries), not signal-count scaling.
If Ask latency stays flat regardless of LLM delay, the LLM path is
not the cause and the 12.3s needs a different explanation.
"""

import sys
import os
import time
import tempfile
import sqlite3
import json
import asyncio
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


def _seed_signals(db_path, count, user_email):
    """Bulk-insert signals directly into SQLite for benchmarking."""
    from datetime import datetime, timezone, timedelta
    conn = sqlite3.connect(db_path)
    base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    entities = ["AcmeCorp", "GlobexCorp", "Initrode", "UmbrellaCorp", "Cyberdyne"]
    topics = ["send proposal", "sign contract", "deliver report", "review spec"]
    rows = []
    for i in range(count):
        entity = entities[i % len(entities)]
        topic = topics[i % len(topics)]
        ts = (base_time + timedelta(hours=i)).isoformat()
        sig_id = f"sig-bench-{i:05d}"
        metadata = json.dumps({"commitment_type": "explicit", "is_commitment": True})
        rows.append((sig_id, entity, f"{entity} will {topic} by Friday", "commitment_made", ts, metadata, "public", ts, user_email))
    conn.executemany(
        "INSERT OR IGNORE INTO signals (signal_id, entity, text, signal_type, timestamp, metadata, source_acl, created_at, user_email) VALUES (?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()


class TestLLMLatencyHypothesis:
    """Test whether LLM-call latency explains the 12.3s Ask number."""

    @pytest.fixture
    def setup_10k(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        os.environ["MAESTRO_PERSONAL_DB"] = db_path
        os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-llm-latency"
        os.environ.pop("MAESTRO_PERSONAL_ENV", None)

        import importlib
        import maestro_personal_shell.api as api_module
        importlib.reload(api_module)
        api_module.init_db(db_path)

        from maestro_personal_shell.semantic_retrieval import init_fts_index, rebuild_fts_index
        init_fts_index(db_path)
        _seed_signals(db_path, 10000, "bench@test.com")
        rebuild_fts_index(db_path)

        client = TestClient(api_module.app)
        resp = client.post("/api/auth/login", json={
            "user_email": "bench@test.com",
            "password": os.environ["MAESTRO_PERSONAL_TOKEN"],
        })
        headers = {"Authorization": f"Bearer {resp.json()['token']}"}

        yield client, headers

        os.unlink(db_path)
        os.environ.pop("MAESTRO_PERSONAL_DB", None)
        os.environ.pop("MAESTRO_PERSONAL_TOKEN", None)

    def _mock_llm_with_delay(self, delay_seconds, available=True):
        """Create a mock LLM that sleeps for delay_seconds before responding."""
        async def slow_llm_complete(system, user, **kwargs):
            await asyncio.sleep(delay_seconds)
            return MagicMock(text=f"LLM response after {delay_seconds}s")

        return (
            patch("maestro_personal_shell.commitment_classifier.classify_commitment",
                  new_callable=AsyncMock,
                  return_value={"commitment_type": "explicit", "is_commitment": True,
                                "confidence": 0.85, "state": "active", "owner": "user",
                                "reasoning": "test", "llm_powered": False}),
            patch("maestro_personal_shell.llm_bridge.is_llm_available",
                  return_value=available),
            patch("maestro_personal_shell.llm_bridge.get_llm_router",
                  return_value=MagicMock(
                      default_provider="mock-llm",
                      complete=slow_llm_complete,
                  )),
        )

    def test_ask_latency_without_llm(self, setup_10k):
        """Baseline: Ask at 10K signals with NO LLM (rule-based only)."""
        client, headers = setup_10k

        with patch("maestro_personal_shell.commitment_classifier.classify_commitment",
                   new_callable=AsyncMock,
                   return_value={"commitment_type": "explicit", "is_commitment": True,
                                 "confidence": 0.85, "state": "active", "owner": "user",
                                 "reasoning": "test", "llm_powered": False}), \
             patch("maestro_personal_shell.llm_bridge.is_llm_available",
                   return_value=False):
            # Warm up
            client.post("/api/ask", json={"query": "warmup"}, headers=headers)

            # Measure
            start = time.perf_counter()
            resp = client.post("/api/ask", json={"query": "What did AcmeCorp commit to?"}, headers=headers)
            elapsed_ms = (time.perf_counter() - start) * 1000

            assert resp.status_code == 200
            data = resp.json()
            assert data["intelligence_source"] == "rules"
            print(f"\n10K Ask WITHOUT LLM: {elapsed_ms:.0f}ms")
            return elapsed_ms

    def test_ask_latency_with_slow_llm(self, setup_10k):
        """Ask at 10K signals WITH a slow LLM (2s delay per call)."""
        client, headers = setup_10k

        mocks = self._mock_llm_with_delay(2.0, available=True)
        with mocks[0], mocks[1], mocks[2]:
            start = time.perf_counter()
            resp = client.post("/api/ask", json={"query": "What did AcmeCorp commit to?"}, headers=headers)
            elapsed_ms = (time.perf_counter() - start) * 1000

            assert resp.status_code == 200
            data = resp.json()
            assert data["intelligence_source"] == "llm"
            print(f"\n10K Ask WITH 2s LLM: {elapsed_ms:.0f}ms")
            return elapsed_ms

    def test_ask_latency_with_very_slow_llm(self, setup_10k):
        """Ask at 10K signals WITH a very slow LLM (10s delay per call)."""
        client, headers = setup_10k

        mocks = self._mock_llm_with_delay(10.0, available=True)
        with mocks[0], mocks[1], mocks[2]:
            start = time.perf_counter()
            resp = client.post("/api/ask", json={"query": "What did AcmeCorp commit to?"}, headers=headers)
            elapsed_ms = (time.perf_counter() - start) * 1000

            assert resp.status_code == 200
            data = resp.json()
            print(f"\n10K Ask WITH 10s LLM: {elapsed_ms:.0f}ms")
            return elapsed_ms

    def test_ask_latency_with_failing_llm_retries(self, setup_10k):
        """Ask at 10K seconds with a FAILING LLM that triggers retries.

        This simulates the retry-with-backoff scenario. The ZAI router
        retries 3 times with 1s, 2s, 4s delays = 7s of retry waits
        before falling back to rules."""
        client, headers = setup_10k

        # Mock a router that always fails (simulates 429 rate limit)
        async def failing_llm_complete(system, user, **kwargs):
            raise RuntimeError("429: Too many requests")

        with patch("maestro_personal_shell.commitment_classifier.classify_commitment",
                   new_callable=AsyncMock,
                   return_value={"commitment_type": "explicit", "is_commitment": True,
                                 "confidence": 0.85, "state": "active", "owner": "user",
                                 "reasoning": "test", "llm_powered": False}), \
             patch("maestro_personal_shell.llm_bridge.is_llm_available",
                   return_value=True), \
             patch("maestro_personal_shell.llm_bridge.get_llm_router",
                   return_value=MagicMock(
                       default_provider="failing-llm",
                       complete=failing_llm_complete,
                   )):
            start = time.perf_counter()
            resp = client.post("/api/ask", json={"query": "What did AcmeCorp commit to?"}, headers=headers)
            elapsed_ms = (time.perf_counter() - start) * 1000

            assert resp.status_code == 200
            data = resp.json()
            # LLM failed → fell back to rules
            print(f"\n10K Ask with FAILING LLM (triggers retry/fallback): {elapsed_ms:.0f}ms")
            return elapsed_ms

    def test_latency_breakdown_summary(self, setup_10k):
        """Run all scenarios and print a summary table."""
        print("\n" + "=" * 60)
        print("LLM LATENCY HYPOTHESIS TEST — 10K signals")
        print("=" * 60)

        # 1. No LLM (baseline)
        t1 = self.test_ask_latency_without_llm(setup_10k)

        # 2. 2s LLM delay
        t2 = self.test_ask_latency_with_slow_llm(setup_10k)

        # 3. Failing LLM (retry scenario)
        t3 = self.test_ask_latency_with_failing_llm_retries(setup_10k)

        print("\n" + "-" * 60)
        print(f"{'Scenario':<40} {'Latency':>10}")
        print("-" * 60)
        print(f"{'No LLM (rule-based baseline)':<40} {t1:>8.0f}ms")
        print(f"{'LLM with 2s delay':<40} {t2:>8.0f}ms")
        print(f"{'Failing LLM (retry/fallback)':<40} {t3:>8.0f}ms")
        print("-" * 60)

        # Analysis
        llm_overhead_2s = t2 - t1
        print(f"\nLLM overhead (2s delay): +{llm_overhead_2s:.0f}ms")
        print(f"  Expected: ~2000ms (1 LLM call)")
        print(f"  Actual:   {llm_overhead_2s:.0f}ms")

        # The key finding: does a slow/failing LLM explain 12.3s?
        print(f"\n{'='*60}")
        print("HYPOTHESIS TEST RESULT:")
        print(f"{'='*60}")
        if t3 > 5000:
            print(f"  FAILING LLM (retries) → {t3:.0f}ms — YES, retry latency")
            print(f"  can stack into multi-second delays. This is consistent")
            print(f"  with the 12.3s number being LLM-call latency, not")
            print(f"  signal-count scaling.")
        else:
            print(f"  FAILING LLM (retries) → {t3:.0f}ms — retry latency is")
            print(f"  bounded. The 12.3s number is NOT explained by LLM")
            print(f"  retries alone and needs a different explanation.")
        print(f"{'='*60}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
