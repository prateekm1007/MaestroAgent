"""
Lightweight HTTP-based Gold-150 scorer.
Uses the already-running API at localhost:8779 instead of in-process TestClient.
"""
import os
import sys
import json
import time
import urllib.request
import urllib.error
import asyncio

sys.path.insert(0, "/home/z/my-project/MaestroAgent/download/MaestroAgent/maestro-personal")
from evaluation.scoreboard.gold_150 import GOLD_150

BASE = "http://127.0.0.1:8779"
TOKEN = "gold-test-token"

def http_post(path, body, timeout=120):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE}{path}", data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"},
    )
    resp = urllib.request.urlopen(req, timeout=timeout)
    return resp.status, json.loads(resp.read() or "null")

def http_get(path, timeout=30):
    req = urllib.request.Request(f"{BASE}{path}", headers={"Authorization": f"Bearer {TOKEN}"})
    resp = urllib.request.urlopen(req, timeout=timeout)
    return resp.status, json.loads(resp.read() or "null")

# 1. Verify API is up + LLM is active
s, body = http_get("/api/llm-status")
print(f"LLM status: active={body.get('active')} provider={body.get('provider')}", flush=True)
assert body.get("active") is True, "LLM not active — aborting"

# 2. Seed signals directly into DB (fast — bypass API)
print(f"Seeding {len(GOLD_150)} questions' signals...", flush=True)
sys.path.insert(0, "/home/z/my-project/MaestroAgent/download/MaestroAgent/maestro-personal/src")
from maestro_personal_shell.db_util import get_db_conn
import sqlite3

# Connect to the same DB the API is using
conn = sqlite3.connect("/tmp/gold_api2.db")
seeded = 0
all_signals = []
for q in GOLD_150:
    for sig in q.get("seed_signals", []):
        all_signals.append(sig)
seen = set()
for i, sig in enumerate(all_signals):
    key = (sig.get("entity", ""), sig.get("text", ""))
    if key in seen:
        continue
    seen.add(key)
    try:
        sig_id = f"sig-seed-{i+1:04d}"
        conn.execute(
            "INSERT OR IGNORE INTO signals (signal_id, user_email, entity, text, signal_type, timestamp, metadata, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (sig_id, "default@personal.local", sig.get("entity", ""), sig.get("text", ""),
             sig.get("signal_type", "reported_statement"),
             sig.get("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
             json.dumps({"signal_type": sig.get("signal_type", "reported_statement")}),
             time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
        )
        seeded += 1
    except Exception as e:
        print(f"  seed {i+1} failed: {e}", flush=True)
conn.commit()
conn.close()
print(f"Seeded {seeded} signals", flush=True)

# 3. Fire all 150 questions
print(f"\nFiring {len(GOLD_150)} questions...", flush=True)
results = []
llm_active_count = 0
t_start = time.time()
for i, q in enumerate(GOLD_150):
    t0 = time.time()
    try:
        s, body = http_post("/api/ask", {"query": q["query"]}, timeout=120)
        elapsed = time.time() - t0
        if s != 200:
            print(f"  [{i+1:>3}/150] FAIL {q['type']:15s} -> {s}", flush=True)
            results.append({"id": q["id"], "type": q["type"], "query": q["query"], "score": 0.0, "error": f"HTTP {s}", "llm_active": False, "elapsed": elapsed})
            continue
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  [{i+1:>3}/150] ERR  {q['type']:15s} -> {e}", flush=True)
        results.append({"id": q["id"], "type": q["type"], "query": q["query"], "score": 0.0, "error": str(e)[:200], "llm_active": False, "elapsed": elapsed})
        continue

    answer = body.get("answer", "")
    evidence = body.get("evidence_refs", [])
    llm_active = body.get("llm_active", False)
    confidence = body.get("confidence", 0)
    if llm_active:
        llm_active_count += 1

    expected = q.get("expected_keywords", [])
    forbidden = q.get("forbidden_keywords", [])
    should_abstain = q.get("should_abstain", False)
    answer_lower = answer.lower()
    if should_abstain:
        abstain_phrases = ["don't have", "insufficient", "no evidence", "not enough"]
        score = 1.0 if any(p in answer_lower for p in abstain_phrases) else 0.0
    else:
        has_all_expected = all(kw.lower() in answer_lower for kw in expected)
        has_forbidden = any(kw.lower() in answer_lower for kw in forbidden)
        score = 1.0 if (has_all_expected and not has_forbidden) else 0.0

    results.append({
        "id": q["id"], "type": q["type"], "query": q["query"], "score": score,
        "answer_preview": answer[:150],
        "evidence_count": len(evidence) if isinstance(evidence, list) else 0,
        "llm_active": llm_active, "confidence": confidence, "elapsed": elapsed,
    })
    marker = "✓" if score >= 0.5 else "✗"
    llm_marker = "LLM" if llm_active else "RBD"
    elapsed_total = time.time() - t_start
    print(f"  [{i+1:>3}/150] {marker} {llm_marker} {q['type']:15s} s={score:.2f} {q['query'][:40]} ({elapsed:.1f}s, total={elapsed_total:.0f}s)", flush=True)

# 4. Compute composite
maestro_avg = sum(r["score"] for r in results) / len(results) if results else 0
bm25_baseline = 0.514
lift = (maestro_avg - bm25_baseline) * 100
by_type = {}
for r in results:
    by_type.setdefault(r["type"], []).append(r["score"])

print("\n" + "=" * 70, flush=True)
print(f"  GOLD-150 — MAESTRO (LLM-ACTIVE) vs BM25", flush=True)
print("=" * 70, flush=True)
print(f"\n  BM25 baseline:     {bm25_baseline:.3f}", flush=True)
print(f"  Maestro composite: {maestro_avg:.3f}", flush=True)
print(f"  Lift:              {lift:+.1f} points (target: >= +15)", flush=True)
print(f"\n  Per-type breakdown:", flush=True)
print(f"    {'type':<20s} {'maestro':>8s}", flush=True)
for t_name, scores in sorted(by_type.items()):
    m_avg = sum(scores) / len(scores) if scores else 0
    print(f"    {t_name:<20s} {m_avg:>8.3f}", flush=True)
print(f"\n  LLM active on {llm_active_count}/{len(results)} answers", flush=True)
avg_confidence = sum(r.get("confidence", 0) for r in results) / len(results) if results else 0
avg_latency = sum(r.get("elapsed", 0) for r in results) / len(results) if results else 0
print(f"  Avg confidence: {avg_confidence:.3f}", flush=True)
print(f"  Avg latency:    {avg_latency:.1f}s", flush=True)

if llm_active_count == 0:
    print(f"\n  FATAL: 0/{len(results)} had llm_active=True. Aborting — no file.", flush=True)
    os._exit(1)

gate_pass = lift >= 15
print(f"\n  {'PASS' if gate_pass else 'FAIL'} — lift={lift:+.1f} (target >= +15)", flush=True)

# 5. Save results
out_path = "/home/z/my-project/download/gold_150_llm_active_full_results.json"
with open(out_path, "w") as f:
    json.dump({
        "mode": "LLM-ACTIVE",
        "provider": body.get("llm_provider", "ollama") if "body" in dir() else "ollama",
        "llm_active_count": llm_active_count,
        "total_questions": len(results),
        "maestro_composite": maestro_avg,
        "bm25_baseline": bm25_baseline,
        "lift": lift / 100,
        "gate_pass": gate_pass,
        "per_type": {t: sum(s) / len(s) for t, s in by_type.items()},
        "avg_confidence": avg_confidence,
        "avg_latency_s": avg_latency,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tunnel_url": os.environ.get("OLLAMA_HOST", ""),
        "model": os.environ.get("OLLAMA_MODEL", "llama3:8b"),
        "results": results,
    }, f, indent=2)
print(f"\nResults saved to {out_path}", flush=True)
os._exit(0)
