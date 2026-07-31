#!/usr/bin/env python3
"""
MaestroAgent Production Monitor
Runs continuously to verify production health
"""

import requests
import time
import json
from datetime import datetime

BACKEND = "https://maestroagent-production.up.railway.app"
CHECK_INTERVAL = 300  # 5 minutes

def check_health():
    """Check if production is healthy"""
    try:
        resp = requests.get(f"{BACKEND}/api/health", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            print(f"[{datetime.now().isoformat()}] ✅ Health: {data.get('status', 'unknown')}")
            return True
        else:
            print(f"[{datetime.now().isoformat()}] ❌ Health: {resp.status_code}")
            return False
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] ❌ Health check failed: {e}")
        return False

def check_performance():
    """Quick performance check"""
    try:
        email = f"monitor-{int(time.time())}@test.com"
        resp = requests.post(f"{BACKEND}/api/auth/register", json={
            "user_email": email,
            "password": "testpass123"
        }, timeout=10)
        
        if resp.status_code != 200:
            return False
        
        token = resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        start = time.time()
        resp = requests.post(
            f"{BACKEND}/api/ask",
            headers=headers,
            json={"query": "What did I promise?"},
            timeout=20
        )
        latency = time.time() - start
        
        if resp.status_code == 200 and latency < 3.0:
            print(f"[{datetime.now().isoformat()}] ✅ Performance: {latency:.2f}s")
            return True
        else:
            print(f"[{datetime.now().isoformat()}] ❌ Performance: {latency:.2f}s or {resp.status_code}")
            return False
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] ❌ Performance check failed: {e}")
        return False

if __name__ == "__main__":
    print("Starting MaestroAgent Production Monitor")
    print(f"Checking every {CHECK_INTERVAL} seconds")
    print("Press Ctrl+C to stop\n")
    
    try:
        while True:
            health_ok = check_health()
            perf_ok = check_performance()
            
            if not (health_ok and perf_ok):
                print(f"[{datetime.now().isoformat()}] ⚠️  Issues detected!")
            
            time.sleep(CHECK_INTERVAL)
    except KeyboardInterrupt:
        print("\nMonitor stopped")
