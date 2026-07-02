#!/usr/bin/env python3
"""
Round 50 — Load Test Script (H11).

Tests the Maestro API at 100, 500, and 1000 requests per second (RPS)
against a running system. Measures:
  - Response time (p50, p95, p99)
  - Error rate
  - Throughput

Usage:
  # Start the server first:
  cd backend
  MAESTRO_APP_DIR=/path/to/MaestroAgent PYTHONPATH=. \
    uvicorn maestro_api.main:create_app --factory --port 1420 &

  # Run the load test:
  python /home/z/my-project/scripts/load_test.py --base-url http://localhost:1420

  # Or against a specific RPS:
  python /home/z/my-project/scripts/load_test.py --rps 100

Requirements:
  pip install aiohttp asyncio
"""
import argparse
import asyncio
import time
import statistics
import sys
from collections import defaultdict

try:
    import aiohttp
except ImportError:
    print("Install aiohttp first: pip install aiohttp")
    sys.exit(1)


# The endpoints to test (mix of light and heavy)
ENDPOINTS = [
    ("GET", "/api/health", "Health (light)"),
    ("GET", "/api/oem/ceo-briefing", "CEO Briefing (heavy)"),
    ("GET", "/api/oem/timeline?limit=10", "Timeline (medium)"),
    ("GET", "/api/oem/tasks", "Tasks (light)"),
    ("GET", "/api/oem/ask?q=payments", "Ask (heavy)"),
]


async def hit_endpoint(session, method, url, label):
    """Hit one endpoint and return (label, status, latency_ms, error)."""
    start = time.perf_counter()
    try:
        async with session.request(method, url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            await resp.read()
            latency = (time.perf_counter() - start) * 1000
            return (label, resp.status, latency, None)
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return (label, 0, latency, str(e))


async def run_load_test(base_url, target_rps, duration_seconds):
    """Run a load test at the target RPS for the given duration."""
    total_requests = target_rps * duration_seconds
    delay_between = 1.0 / target_rps

    print(f"\n{'='*60}")
    print(f"LOAD TEST: {target_rps} RPS for {duration_seconds}s ({total_requests} requests)")
    print(f"{'='*60}")

    results = defaultdict(list)
    errors = defaultdict(int)
    status_counts = defaultdict(int)

    connector = aiohttp.TCPConnector(limit=100, force_close=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        for i in range(total_requests):
            method, path, label = ENDPOINTS[i % len(ENDPOINTS)]
            url = base_url + path
            tasks.append(hit_endpoint(session, method, url, label))
            # Stagger requests to hit target RPS
            if (i + 1) % target_rps == 0:
                await asyncio.sleep(delay_between * target_rps)

        # Run all requests
        responses = await asyncio.gather(*tasks)

    # Analyze results
    for label, status, latency, error in responses:
        results[label].append(latency)
        status_counts[status] += 1
        if error:
            errors[label] += 1

    # Print results per endpoint
    print(f"\n{'Endpoint':<35} {'p50':>8} {'p95':>8} {'p99':>8} {'errors':>6} {'total':>6}")
    print("-" * 75)
    for label in results:
        latencies = sorted(results[label])
        n = len(latencies)
        p50 = latencies[int(n * 0.5)]
        p95 = latencies[int(n * 0.95)]
        p99 = latencies[int(n * 0.99)] if n > 100 else latencies[-1]
        err = errors.get(label, 0)
        print(f"{label:<35} {p50:>7.1f}ms {p95:>7.1f}ms {p99:>7.1f}ms {err:>6} {n:>6}")

    # Overall stats
    all_latencies = [l for lats in results.values() for l in lats]
    total = len(all_latencies)
    total_errors = sum(errors.values())
    error_rate = (total_errors / total * 100) if total > 0 else 0
    print(f"\n{'OVERALL':<35} {statistics.median(all_latencies):>7.1f}ms "
          f"{sorted(all_latencies)[int(total*0.95)]:>7.1f}ms "
          f"{sorted(all_latencies)[int(total*0.99)]:>7.1f}ms {total_errors:>6} {total:>6}")
    print(f"\nError rate: {error_rate:.1f}%")
    print(f"Status codes: {dict(status_counts)}")

    # Verdict
    if error_rate > 5:
        print(f"\n✗ FAIL — error rate {error_rate:.1f}% exceeds 5% threshold")
        return False
    elif statistics.median(all_latencies) > 500:
        print(f"\n⚠ WARN — median latency {statistics.median(all_latencies):.0f}ms exceeds 500ms")
        return True
    else:
        print(f"\n✓ PASS — error rate {error_rate:.1f}%, median {statistics.median(all_latencies):.0f}ms")
        return True


async def main():
    parser = argparse.ArgumentParser(description="Maestro Load Test")
    parser.add_argument("--base-url", default="http://localhost:1420", help="Base URL")
    parser.add_argument("--rps", type=int, nargs="+", default=[100, 500, 1000], help="RPS levels to test")
    parser.add_argument("--duration", type=int, default=10, help="Duration in seconds per RPS level")
    args = parser.parse_args()

    print(f"Maestro Load Test")
    print(f"Base URL: {args.base_url}")
    print(f"RPS levels: {args.rps}")
    print(f"Duration per level: {args.duration}s")

    all_pass = True
    for rps in args.rps:
        passed = await run_load_test(args.base_url, rps, args.duration)
        if not passed:
            all_pass = False

    print(f"\n{'='*60}")
    if all_pass:
        print("ALL LOAD TESTS PASS")
    else:
        print("SOME LOAD TESTS FAILED — investigate before shipping")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
