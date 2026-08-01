"""
Comprehensive MaestroAgent Test Suite
Tests all critical benchmarks for 9/10 rating
"""

import requests
import time
import statistics
import sys

BACKEND = "https://maestroagent-production.up.railway.app"

def test_performance():
    """Test Ask performance (target: p95 < 3s)"""
    print("\n=== Testing Performance ===")
    
    # Register fresh account
    email = f"perf-test-{int(time.time())}@test.com"
    resp = requests.post(f"{BACKEND}/api/auth/register", json={
        "user_email": email,
        "password": "testpass123"
    })
    if resp.status_code != 200:
        print("❌ Registration failed")
        return False
    
    token = resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test 10 queries
    latencies = []
    for i in range(10):
        start = time.time()
        resp = requests.post(
            f"{BACKEND}/api/ask",
            headers=headers,
            json={"query": f"What did I promise Person{i}?"},
            timeout=20
        )
        latency = time.time() - start
        latencies.append(latency)
        
        if resp.status_code != 200:
            print(f"❌ Query {i} failed: {resp.status_code}")
            return False
    
    p50 = statistics.median(latencies)
    p95 = sorted(latencies)[int(len(latencies) * 0.95)]
    
    print(f"p50: {p50:.2f}s")
    print(f"p95: {p95:.2f}s")
    
    if p95 < 3.0:
        print("✅ Performance: PASS (p95 < 3s)")
        return True
    else:
        print(f"❌ Performance: FAIL (p95={p95:.2f}s > 3s)")
        return False


def test_abstention():
    """Test negative knowledge abstention (target: 100%)"""
    print("\n=== Testing Abstention ===")
    
    # Register fresh account
    email = f"abstention-test-{int(time.time())}@test.com"
    resp = requests.post(f"{BACKEND}/api/auth/register", json={
        "user_email": email,
        "password": "testpass123"
    })
    if resp.status_code != 200:
        print("❌ Registration failed")
        return False
    
    token = resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test 5 negative queries
    test_entities = ["Elon Musk", "Jeff Bezos", "Project Alpha", "Mars Colony", "Time Travel"]
    abstention_count = 0
    
    for entity in test_entities:
        resp = requests.post(
            f"{BACKEND}/api/ask",
            headers=headers,
            json={"query": f"What did I promise {entity}?"},
            timeout=20
        )
        
        if resp.status_code != 200:
            print(f"❌ Query failed: {resp.status_code}")
            continue
        
        data = resp.json()
        confidence = data.get("confidence", 0)
        answer = data.get("answer", "")
        
        if confidence < 0.1 or "no evidence" in answer.lower() or "no records" in answer.lower():
            abstention_count += 1
    
    rate = abstention_count / len(test_entities)
    print(f"Abstention rate: {abstention_count}/{len(test_entities)} ({rate*100:.0f}%)")
    
    if rate == 1.0:
        print("✅ Abstention: PASS (100%)")
        return True
    else:
        print(f"❌ Abstention: FAIL ({rate*100:.0f}% < 100%)")
        return False


def test_nora_transcript():
    """Test commitment intelligence (target: 7/7)"""
    print("\n=== Testing Nora Controlled Transcript ===")
    
    # Register fresh account
    email = f"nora-test-{int(time.time())}@test.com"
    resp = requests.post(f"{BACKEND}/api/auth/register", json={
        "user_email": email,
        "password": "testpass123"
    })
    if resp.status_code != 200:
        print("❌ Registration failed")
        return False
    
    token = resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Ingest 7 controlled signals
    signals = [
        ("Nora", "I will send the audit report to Nora by Friday."),
        ("Nora", "Maybe I can review it sometime next week."),
        ("Nora", "Can you send the report by Friday?"),
        ("Nora", "Just kidding, I will conquer Mars tomorrow."),
        ("Nora", "Nora: I will send the pricing deck by Friday."),
        ("Nora", "I will not send the audit report; cancelled."),
        ("Nora", "As Nora said, 'the Q3 numbers look strong.'"),
    ]
    
    for entity, text in signals:
        resp = requests.post(
            f"{BACKEND}/api/signals",
            headers=headers,
            json={"entity": entity, "text": text, "signal_type": "email"}
        )
        if resp.status_code != 200:
            print(f"❌ Signal ingestion failed: {resp.status_code}")
            return False
        time.sleep(0.5)
    
    time.sleep(3)
    
    # Get commitments
    resp = requests.get(f"{BACKEND}/api/commitments", headers=headers)
    if resp.status_code != 200:
        print("❌ Get commitments failed")
        return False
    
    commitments = resp.json()
    
    # Verify expectations
    results = []
    
    # Test 1: Exactly 1 user commitment
    user_commitments = [c for c in commitments if c.get("owner") == "user" and c.get("state") == "active"]
    results.append(("Exactly 1 user commitment", len(user_commitments) == 1))
    
    # Test 2: Tentative not extracted
    tentative_found = any("Maybe I can review" in c.get("text", "") for c in commitments)
    results.append(("Tentative not extracted", not tentative_found))
    
    # Test 3: Request not user commitment
    request_found = any("Can you send" in c.get("text", "") and c.get("owner") == "user" for c in commitments)
    results.append(("Request not user commitment", not request_found))
    
    # Test 4: Joke not extracted
    joke_found = any("conquer Mars" in c.get("text", "") for c in commitments)
    results.append(("Joke not extracted", not joke_found))
    
    # Test 5: Nora's promise attributed to Nora
    nora_pricing = [c for c in commitments if "pricing deck" in c.get("text", "")]
    results.append(("Nora's promise attributed to Nora", 
                   len(nora_pricing) == 1 and nora_pricing[0].get("entity") == "Nora"))
    
    # Test 6: Cancellation detected
    cancellation_detected = any(c.get("state") == "cancelled" for c in commitments if "audit report" in c.get("text", ""))
    results.append(("Cancellation detected", cancellation_detected))
    
    # Test 7: Quotation not user commitment
    quotation_found = any("Q3 numbers" in c.get("text", "") and c.get("owner") == "user" for c in commitments)
    results.append(("Quotation not user commitment", not quotation_found))
    
    # Report
    passed = sum(1 for _, p in results if p)
    total = len(results)
    
    print(f"\nResults: {passed}/{total} passed")
    for name, result in results:
        status = "✅" if result else "❌"
        print(f"{status} {name}")
    
    if passed == total:
        print("✅ Nora Test: PASS (7/7)")
        return True
    else:
        print(f"❌ Nora Test: FAIL ({passed}/7)")
        return False


def test_reliability():
    """Test endpoint reliability (target: no 500s)"""
    print("\n=== Testing Reliability ===")
    
    # Register fresh account
    email = f"reliability-test-{int(time.time())}@test.com"
    resp = requests.post(f"{BACKEND}/api/auth/register", json={
        "user_email": email,
        "password": "testpass123"
    })
    if resp.status_code != 200:
        print("❌ Registration failed")
        return False
    
    token = resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test key endpoints
    endpoints = [
        "/api/commitments",
        "/api/signals",
        "/api/the-moment",
        "/api/briefing",
        "/api/what-changed",
    ]
    
    all_ok = True
    for endpoint in endpoints:
        resp = requests.get(f"{BACKEND}{endpoint}", headers=headers, timeout=10)
        if resp.status_code >= 500:
            print(f"❌ {endpoint}: {resp.status_code}")
            all_ok = False
        elif resp.status_code >= 400:
            print(f"⚠️  {endpoint}: {resp.status_code}")
        else:
            print(f"✅ {endpoint}: {resp.status_code}")
    
    if all_ok:
        print("✅ Reliability: PASS (no 500s)")
        return True
    else:
        print("❌ Reliability: FAIL (500s detected)")
        return False


if __name__ == "__main__":
    print("=" * 70)
    print("MAESTROAGENT COMPREHENSIVE TEST SUITE")
    print("=" * 70)
    
    results = {
        "Performance": test_performance(),
        "Abstention": test_abstention(),
        "Nora Test": test_nora_transcript(),
        "Reliability": test_reliability(),
    }
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} benchmarks passed")
    
    if passed == total:
        print("\n🎉 ALL BENCHMARKS AT 9/10")
        sys.exit(0)
    else:
        print(f"\n⚠️  {total - passed} benchmarks need improvement")
        sys.exit(1)
