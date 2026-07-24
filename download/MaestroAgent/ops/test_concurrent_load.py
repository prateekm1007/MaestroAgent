#!/usr/bin/env python3
"""test_concurrent_load.py — Concurrent load gate (Principle 8)."""
from __future__ import annotations
import json, os, sys, time, httpx, asyncio

BACKEND_URL = os.environ.get("MAESTRO_BACKEND_URL", "https://maestroagent-production.up.railway.app")
CONCURRENT_COUNT = 5
P95_THRESHOLD = 10.0

async def register_user():
    resp = httpx.post(f"{BACKEND_URL}/api/auth/register", json={"user_email": f"load-{int(time.time())}@example.com", "password": "load-pass", "name": "Load"}, timeout=30)
    token = resp.json().get("token", "")
    if not token:
        print(f"✗ Register failed: {resp.json()}"); sys.exit(1)
    signal = {"signal_id": f"load-{int(time.time())}", "entity": "Test Entity", "text": "I will send the report by Friday.", "signal_type": "commitment_made", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "metadata": {"source": "load_test", "is_commitment": True, "commitment_type": "commitment_made", "commitment_state": "active", "commitment_owner": "user", "commitment_confidence": 0.9}}
    httpx.post(f"{BACKEND_URL}/api/signals", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, json=signal, timeout=30)
    time.sleep(2)
    return token

async def concurrent_ask(token, query, client):
    start = time.time()
    resp = await client.post(f"{BACKEND_URL}/api/ask", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, json={"query": query}, timeout=60)
    return time.time() - start, resp.status_code

async def run_concurrent_load():
    token = await register_user()
    queries = ["What did I promise Test?", "What did I promise Test Entity?", "What commitments do I have?", "What did I promise Test?", "What did I promise Test Entity?"]
    async with httpx.AsyncClient() as client:
        await concurrent_ask(token, "What did I promise Test?", client)
        print(f"Firing {CONCURRENT_COUNT} concurrent Ask queries...")
        tasks = [concurrent_ask(token, q, client) for q in queries]
        results = await asyncio.gather(*tasks)
    latencies = [r[0] for r in results]
    statuses = [r[1] for r in results]
    latencies.sort()
    p50 = latencies[len(latencies) // 2]
    p95 = latencies[-1]
    print(f"\nConcurrent results ({CONCURRENT_COUNT} queries):")
    for i, (lat, status) in enumerate(zip(latencies, statuses)):
        print(f"  Query {i+1}: {lat:.2f}s (HTTP {status})")
    print(f"\np50: {p50:.2f}s | p95: {p95:.2f}s | Threshold: p95 < {P95_THRESHOLD}s")
    return p95, all(s == 200 for s in statuses)

def main():
    print("=" * 60)
    print("CONCURRENT LOAD GATE (Principle 8)")
    print(f"Firing {CONCURRENT_COUNT} concurrent Ask queries")
    print(f"Target: p95 < {P95_THRESHOLD}s")
    print(f"Backend: {BACKEND_URL}")
    print("=" * 60)
    p95, all_200 = asyncio.run(run_concurrent_load())
    print(f"\n{'='*60}")
    if p95 < P95_THRESHOLD and all_200:
        print(f"✅ CONCURRENT LOAD PASSED — p95={p95:.2f}s < {P95_THRESHOLD}s, all HTTP 200")
        sys.exit(0)
    else:
        print(f"❌ CONCURRENT LOAD FAILED — p95={p95:.2f}s")
        if not all_200: print("  Some queries returned non-200 status")
        sys.exit(1)

if __name__ == "__main__":
    main()
