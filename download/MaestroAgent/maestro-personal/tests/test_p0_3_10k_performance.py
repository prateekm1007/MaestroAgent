"""
P0-3 regression test — Finding 9: "10K performance collapse."

THE BUG (independent product audit):
    At 10,000 signals, Ask takes 12.3 seconds (median). 10 concurrent asks
    take ~124 seconds each. Root cause: async route builds a full shell/
    history with synchronous SQLite in the event loop.

CURRENT STATE (cross-referenced at fe1182c):
    The codebase already has 3 of the 4 auditor-recommended fixes:
    1. ✅ FTS5-indexed bounded retrieval — get_relevant_signals() uses
       BM25-ranked FTS5 MATCH, not linear scan (semantic_retrieval.py:208)
    2. ✅ Sync SQLite off the event loop — build_shell_async() wraps
       build_shell in asyncio.to_thread() (api.py:493)
    3. ✅ Bounded signal loading — ask() passes signal_limit=500 to
       build_shell_async, so only 500 most-recent signals are loaded
       into the shell (not all 10K) (api.py:1050)
    4. ❌ busy_timeout — NOT set on SQLite connections (addressed in P1-3)

    This test proves fixes 1-3 are sufficient to meet the SLO:
    Ask p95 ≤ 500ms at 10K signals.

THE PROOF (this test):
    1. Bulk-insert 10,000 signals directly into SQLite + FTS5 index
    2. Call POST /api/ask 20 times with a natural-language query
    3. Measure latency for each call
    4. Assert p95 ≤ 500ms (the auditor's SLO)
    5. Assert p50 ≤ 200ms (reasonable median)

    If the benchmark fails, the performance fixes are insufficient and
    the SLO is not met. If it passes, the 10K performance collapse is
    resolved.

Governance: P1 (execute, don't read), P22 (integration test through
REAL production entry point: POST /api/ask with 10K signals in the DB).
"""

import sys
import os
import time
import tempfile
import sqlite3
import json
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


@pytest.fixture
def isolated_api_10k():
    """Initialize the API with a temp DB containing 10K signals."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-p0-3"
    os.environ.pop("MAESTRO_PERSONAL_ENV", None)

    import importlib
    import maestro_personal_shell.api as api_module
    importlib.reload(api_module)
    api_module.init_db(db_path)

    # Initialize FTS5
    from maestro_personal_shell.semantic_retrieval import init_fts_index, rebuild_fts_index
    init_fts_index(db_path)

    # Bulk-insert 10K signals directly into SQLite (fast — bypasses API)
    conn = sqlite3.connect(db_path)
    from datetime import datetime, timezone, timedelta
    base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    entities = ["AcmeCorp", "GlobexCorp", "Initrode", "UmbrellaCorp", "Cyberdyne",
                "StarkIndustries", "WayneEnterprises", "LexCorp", "OsCorp", "PowellCorp"]
    topics = ["send proposal", "sign contract", "deliver report", "review spec",
              "schedule demo", "approve budget", "finalize terms", "follow up",
              "provide estimate", "confirm timeline"]
    rows = []
    for i in range(10000):
        entity = entities[i % len(entities)]
        topic = topics[i % len(topics)]
        ts = (base_time + timedelta(hours=i)).isoformat()
        sig_id = f"sig-10k-{i:05d}"
        metadata = json.dumps({"commitment_type": "explicit", "is_commitment": True})
        rows.append((sig_id, entity, f"{entity} will {topic} by Friday", "commitment_made", ts, metadata, "public", ts, "bench-user@test.com"))
    conn.executemany(
        "INSERT OR IGNORE INTO signals (signal_id, entity, text, signal_type, timestamp, metadata, source_acl, created_at, user_email) VALUES (?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()

    # Rebuild FTS5 index from the 10K signals
    count = rebuild_fts_index(db_path)
    assert count >= 9000, f"FTS5 rebuild should index ~10K signals, got {count}"

    yield api_module

    os.unlink(db_path)
    os.environ.pop("MAESTRO_PERSONAL_DB", None)
    os.environ.pop("MAESTRO_PERSONAL_TOKEN", None)


@pytest.fixture
def client_10k(isolated_api_10k):
    return TestClient(isolated_api_10k.app)


def _login_10k(client_10k):
    resp = client_10k.post("/api/auth/login", json={
        "user_email": "bench-user@test.com",
        "password": os.environ["MAESTRO_PERSONAL_TOKEN"],
    })
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _mock_llm():
    return (
        patch(
            "maestro_personal_shell.commitment_classifier.classify_commitment",
            new_callable=AsyncMock,
            return_value={
                "commitment_type": "explicit", "is_commitment": True,
                "confidence": 0.85, "state": "active", "owner": "user",
                "reasoning": "test", "llm_powered": False,
            },
        ),
        patch(
            "maestro_personal_shell.llm_bridge.llm_complete",
            new_callable=AsyncMock, return_value=None,
        ),
        patch(
            "maestro_personal_shell.llm_bridge.is_llm_available",
            return_value=False,
        ),
    )


class TestAskSLO10K:
    """SLO: Ask p95 ≤ 500ms at 10K signals."""

    def test_ask_p95_under_500ms_at_10k_signals(self, client_10k):
        """With 10K signals in the DB, Ask p95 must be ≤ 500ms.

        The auditor measured 12.3s median at 10K signals. After the fixes
        (FTS5 bounded retrieval, asyncio.to_thread, signal_limit=500),
        this must be under 500ms p95.
        """
        headers = _login_10k(client_10k)

        with _mock_llm()[0], _mock_llm()[1], _mock_llm()[2]:
            # Warm up (first call may be slower due to module imports)
            client_10k.post("/api/ask", json={"query": "What did AcmeCorp commit to?"}, headers=headers)

            # Measure 20 Ask calls
            latencies = []
            queries = [
                "What did AcmeCorp commit to?",
                "What did GlobexCorp promise?",
                "What do I know about Initrode?",
                "What did StarkIndustries say about the proposal?",
                "What did WayneEnterprises commit to?",
            ]
            for i in range(20):
                query = queries[i % len(queries)]
                start = time.perf_counter()
                resp = client_10k.post("/api/ask", json={"query": query}, headers=headers)
                elapsed_ms = (time.perf_counter() - start) * 1000
                assert resp.status_code == 200, f"Ask failed: {resp.status_code} {resp.text[:200]}"
                latencies.append(elapsed_ms)

            latencies.sort()
            p50 = latencies[len(latencies) // 2]
            p95 = latencies[int(len(latencies) * 0.95)]
            p99 = latencies[min(int(len(latencies) * 0.99), len(latencies) - 1)]

            print(f"\n10K Ask benchmark ({len(latencies)} calls):")
            print(f"  p50: {p50:.1f}ms")
            print(f"  p95: {p95:.1f}ms")
            print(f"  p99: {p99:.1f}ms")
            print(f"  min: {latencies[0]:.1f}ms")
            print(f"  max: {latencies[-1]:.1f}ms")

            assert p95 <= 500, (
                f"P0-3 SLO FAIL: Ask p95 = {p95:.1f}ms at 10K signals "
                f"(SLO: ≤500ms). The 10K performance collapse is NOT resolved. "
                f"p50={p50:.1f}ms, p99={p99:.1f}ms. "
                f"Check: (1) signal_limit is passed to build_shell_async, "
                f"(2) get_relevant_signals uses FTS5 not linear scan, "
                f"(3) build_shell_async uses asyncio.to_thread."
            )

    def test_ask_returns_relevant_result_at_10k(self, client_10k):
        """At 10K signals, Ask must still return a relevant answer (not
        just be fast — also correct). The FTS5 + ask_ranker pipeline
        must find the right signal among 10K."""
        headers = _login_10k(client_10k)

        with _mock_llm()[0], _mock_llm()[1], _mock_llm()[2]:
            resp = client_10k.post(
                "/api/ask",
                json={"query": "What did AcmeCorp commit to?"},
                headers=headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            # The answer or source must mention AcmeCorp (FTS5 found it among 10K)
            answer = data.get("answer", "") + " " + data.get("source_sentence", "")
            assert "AcmeCorp" in answer or "acmecorp" in answer.lower(), (
                f"At 10K signals, Ask should find AcmeCorp's commitments. "
                f"Answer: {data.get('answer', '')[:200]}"
            )

    def test_ask_p50_under_200ms_at_10k(self, client_10k):
        """Bonus SLO: p50 should be under 200ms (reasonable median).
        This catches latency regressions before they hit the p95 threshold."""
        headers = _login_10k(client_10k)

        with _mock_llm()[0], _mock_llm()[1], _mock_llm()[2]:
            client_10k.post("/api/ask", json={"query": "warmup"}, headers=headers)

            latencies = []
            for i in range(10):
                start = time.perf_counter()
                resp = client_10k.post(
                    "/api/ask",
                    json={"query": "What did AcmeCorp commit to?"},
                    headers=headers,
                )
                elapsed_ms = (time.perf_counter() - start) * 1000
                assert resp.status_code == 200
                latencies.append(elapsed_ms)

            latencies.sort()
            p50 = latencies[len(latencies) // 2]
            print(f"\n10K Ask p50: {p50:.1f}ms")
            assert p50 <= 200, (
                f"Ask p50 = {p50:.1f}ms at 10K signals (target: ≤200ms). "
                f"Median latency is too high — check for O(n) scans."
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
