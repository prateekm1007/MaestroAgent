#!/usr/bin/env python3
"""Independent latency measurement for the MaestroAgent latency audit.

Measures:
1. Frontend HTML load time (with preconnect)
2. the-moment cold cache (first call after token mint)
3. the-moment warm cache (second call, should hit backend shell cache)
4. shifts endpoint
5. commitments endpoint
6. whisper endpoint
7. Page revisit simulation (second call to all endpoints, should hit SWR
   if we were a browser — but since we're using curl, this measures the
   backend cache, not the browser sessionStorage cache)

NOTE: The SWR sessionStorage cache is a BROWSER-side optimization. We
cannot measure it with curl because curl doesn't have sessionStorage.
The coder's claim of "<0.1s page revisit" is only measurable in a real
browser. We can, however, measure the backend-side latency (shell cache)
and verify the preconnect tags are in the HTML.

P46 enforcement: we measure the SERVED latency, not the claimed latency.
"""
import json
import subprocess
import time
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BACKEND = "https://maestroagent-production.up.railway.app"
FRONTEND = "https://web-production-d5c26.up.railway.app"

def timed_get(url, headers=None, timeout=30):
    """GET with timing. Returns (status, latency_s, body_or_error)."""
    t0 = time.monotonic()
    req = Request(url, headers=headers or {})
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            latency = time.monotonic() - t0
            return resp.status, latency, body
    except HTTPError as e:
        latency = time.monotonic() - t0
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return e.code, latency, body
    except (URLError, TimeoutError, Exception) as e:
        latency = time.monotonic() - t0
        return 0, latency, str(e)

def timed_post(url, payload, headers=None, timeout=30):
    """POST with timing. Returns (status, latency_s, body_or_error)."""
    t0 = time.monotonic()
    data = json.dumps(payload).encode("utf-8")
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = Request(url, data=data, headers=h, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            latency = time.monotonic() - t0
            return resp.status, latency, body
    except HTTPError as e:
        latency = time.monotonic() - t0
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return e.code, latency, body
    except (URLError, TimeoutError, Exception) as e:
        latency = time.monotonic() - t0
        return 0, latency, str(e)

def login():
    """Login as bootstrap demo user, return bearer token."""
    status, lat, body = timed_post(
        f"{BACKEND}/api/auth/login",
        {"user_email": "bootstrap", "password": "maestro-demo"},
        timeout=20,
    )
    if status != 200:
        print(f"LOGIN FAILED: {status} in {lat:.2f}s — {body[:200]}")
        sys.exit(1)
    token = json.loads(body).get("token")
    print(f"Login: {status} in {lat:.2f}s (token prefix: {token[:12]}...)")
    return token

def measure_endpoint(name, url, token, iterations=2):
    """Measure an endpoint N times, report each latency."""
    headers = {"Authorization": f"Bearer {token}"}
    results = []
    for i in range(iterations):
        status, lat, body = timed_get(url, headers, timeout=30)
        # Truncate body for display
        body_preview = body[:100].replace("\n", " ") if body else "(empty)"
        results.append((status, lat, body_preview))
        print(f"  {name} call {i+1}: {status} in {lat:.2f}s — {body_preview[:80]}")
        if i < iterations - 1:
            time.sleep(0.5)
    return results

def main():
    print("=" * 72)
    print("INDEPENDENT LATENCY AUDIT — MaestroAgent")
    print(f"Backend: {BACKEND}")
    print(f"Frontend: {FRONTEND}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print("=" * 72)

    # 1. Frontend HTML load (preconnect check)
    print("\n--- 1. Frontend HTML load (preconnect) ---")
    status, lat, body = timed_get(FRONTEND + "/", timeout=15)
    has_preconnect = 'rel="preconnect"' in body and "maestroagent-production" in body
    has_dns_prefetch = 'rel="dns-prefetch"' in body and "maestroagent-production" in body
    print(f"  Frontend HTML: {status} in {lat:.2f}s")
    print(f"  preconnect tag present: {has_preconnect}")
    print(f"  dns-prefetch tag present: {has_dns_prefetch}")

    # 2. Backend health (deployed commit)
    print("\n--- 2. Backend health (deployed commit) ---")
    status, lat, body = timed_get(f"{BACKEND}/api/health", timeout=10)
    health = json.loads(body) if status == 200 else {}
    print(f"  /api/health: {status} in {lat:.2f}s — commit={health.get('commit','?')[:7]}")

    # 3. Login
    print("\n--- 3. Login ---")
    token = login()

    # 4. the-moment cold cache (first call)
    print("\n--- 4. the-moment (cold cache, first call) ---")
    measure_endpoint("the-moment", f"{BACKEND}/api/the-moment", token, iterations=2)

    # 5. shifts
    print("\n--- 5. shifts ---")
    measure_endpoint("shifts", f"{BACKEND}/api/shifts", token, iterations=2)

    # 6. commitments
    print("\n--- 6. commitments ---")
    measure_endpoint("commitments", f"{BACKEND}/api/commitments", token, iterations=2)

    # 7. whisper
    print("\n--- 7. whisper ---")
    measure_endpoint("whisper", f"{BACKEND}/api/whisper", token, iterations=2)

    # 8. Wait 5s, then re-measure the-moment to check backend shell cache
    print("\n--- 8. the-moment (after 5s wait — backend shell cache check) ---")
    time.sleep(5)
    measure_endpoint("the-moment", f"{BACKEND}/api/the-moment", token, iterations=1)

    print("\n" + "=" * 72)
    print("NOTE: The SWR sessionStorage cache (browser-side) cannot be measured")
    print("with curl. The coder's '<0.1s page revisit' claim is only verifiable")
    print("in a real browser with DevTools open. This audit measures BACKEND")
    print("latency (shell cache) and HTML preconnect tags — not browser cache.")
    print("=" * 72)

if __name__ == "__main__":
    main()
