"""
Task 59-2 (full): Score Maestro Ask against Gold-150 with verified LLM.

Optimized version of score_gold_150_honest.py:
  - Uses TestClient (in-process) instead of uvicorn (no HTTP overhead)
  - Seeds signals with LLM disabled (fast), then enables LLM for Ask
  - Runs in background with progress logging

Usage:
  OLLAMA_HOST=https://<tunnel> OLLAMA_MODEL=llama3:8b \
  python /home/z/my-project/scripts/score_gold_150_full.py
"""
from __future__ import annotations

import os
import sys
import json
import time
import tempfile
import asyncio
import signal
import traceback
from pathlib import Path

# Crash handler — write the traceback to the log so we can see why
def _crash_handler(exc_type, exc_value, exc_tb):
    print(f"\n[score] CRASH: {exc_value}", flush=True)
    traceback.print_exception(exc_type, exc_value, exc_tb)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(1)

sys.excepthook = _crash_handler

def _signal_handler(signum, frame):
    print(f"\n[score] Killed by signal {signum}", flush=True)
    os._exit(130)

for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
    signal.signal(sig, _signal_handler)

REPO = Path("/home/z/my-project/MaestroAgent/download/MaestroAgent")
SHELL_SRC = REPO / "maestro-personal" / "src"
sys.path.insert(0, str(SHELL_SRC))
sys.path.insert(0, str(REPO / "maestro-personal"))

# Fresh DB
tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="maestro_gold_full_")
tmp_db.close()
os.environ["MAESTRO_PERSONAL_DB"] = tmp_db.name
os.environ["MAESTRO_PERSONAL_TOKEN"] = "gold-test-token"
os.environ["MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL"] = "1"
os.environ.setdefault("MAESTRO_ENV", "dev")

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3:8b")
if not OLLAMA_HOST:
    print("FATAL: OLLAMA_HOST must be set")
    sys.exit(1)

print(f"Tunnel: {OLLAMA_HOST}")
print(f"Model:  {OLLAMA_MODEL}")

# Disable LLM during seeding (fast) — we'll re-enable for Ask
os.environ["OLLAMA_HOST"] = ""

from fastapi.testclient import TestClient
from maestro_personal_shell.api import app, init_db
from maestro_personal_shell.llm_bridge import reset_llm_router, get_llm_provider_name, probe_provider

# Initialize DB tables
init_db()
print(f"[score] DB initialized at {os.environ['MAESTRO_PERSONAL_DB']}")

client = TestClient(app)

# Login
r = client.post("/api/auth/login", json={"user_email": "default@personal.local", "password": "gold-test-token"})
assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
TOKEN = r.json()["token"]
H = {"Authorization": f"Bearer {TOKEN}"}
print(f"[score] Logged in")

# Import gold corpus
from evaluation.scoreboard.gold_150 import GOLD_150

# 1. Seed all unique signals (LLM disabled — fast)
all_signals = []
for q in GOLD_150:
    for sig in q.get("seed_signals", []):
        sig["user_email"] = "default@personal.local"
        all_signals.append(sig)
seen = set()
unique_signals = []
for sig in all_signals:
    key = (sig.get("entity", ""), sig.get("text", ""))
    if key not in seen:
        seen.add(key)
        unique_signals.append(sig)

print(f"[score] Seeding {len(unique_signals)} signals directly into DB (fast)...")
t0 = time.time()
from maestro_personal_shell.db_util import get_db_conn
import json as _json
conn = get_db_conn()
seeded = 0
for i, sig in enumerate(unique_signals):
    try:
        sig_id = f"sig-seed-{i+1:04d}"
        entity = sig.get("entity", "")
        text = sig.get("text", "")
        sig_type = sig.get("signal_type", "reported_statement")
        timestamp = sig.get("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        meta = _json.dumps({"signal_type": sig_type, "entity": entity})
        conn.execute(
            "INSERT OR IGNORE INTO signals (signal_id, user_email, entity, text, signal_type, timestamp, metadata, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (sig_id, "default@personal.local", entity, text, sig_type, timestamp, meta, timestamp),
        )
        seeded += 1
    except Exception as e:
        print(f"  seed {i+1} failed: {e}")
conn.commit()
conn.close()
print(f"[score] Seeded {seeded}/{len(unique_signals)} signals in {time.time()-t0:.1f}s")

# 2. Re-enable LLM for Ask scoring
os.environ["OLLAMA_HOST"] = OLLAMA_HOST
reset_llm_router()
provider = get_llm_provider_name()
probe = asyncio.run(probe_provider(force=True))
print(f"[score] LLM provider: {provider}, probe verified: {probe.get('verified')}")
if probe.get("verified") is not True:
    print("[score] FATAL: LLM probe failed — tunnel may be down. Aborting.")
    sys.exit(1)

# 3. Fire all 150 questions
print(f"\n[score] Firing {len(GOLD_150)} questions through /api/ask (LLM active)...", flush=True)
results = []
llm_active_count = 0
t_start = time.time()
for i, q in enumerate(GOLD_150):
    t0 = time.time()
    try:
        r = client.post("/api/ask", json={"query": q["query"]}, headers=H, timeout=120)
        elapsed = time.time() - t0
        if r.status_code != 200:
            print(f"  [{i+1:>3}/150] FAIL {q['type']:15s} {q['query'][:45]} -> {r.status_code}", flush=True)
            results.append({
                "id": q["id"], "type": q["type"], "query": q["query"],
                "score": 0.0, "error": f"HTTP {r.status_code}",
                "llm_active": False, "elapsed": elapsed,
            })
            continue
        body = r.json()
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  [{i+1:>3}/150] ERR  {q['type']:15s} {q['query'][:45]} -> {e}", flush=True)
        results.append({
            "id": q["id"], "type": q["type"], "query": q["query"],
            "score": 0.0, "error": str(e)[:200],
            "llm_active": False, "elapsed": elapsed,
        })
        continue

    answer = body.get("answer", "")
    evidence = body.get("evidence_refs", [])
    llm_active = body.get("llm_active", False)
    confidence = body.get("confidence", 0)
    if llm_active:
        llm_active_count += 1

    # Score against gold
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
        "id": q["id"], "type": q["type"], "query": q["query"],
        "score": score,
        "answer_preview": answer[:150],
        "evidence_count": len(evidence) if isinstance(evidence, list) else 0,
        "llm_active": llm_active,
        "confidence": confidence,
        "elapsed": elapsed,
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

print("\n" + "=" * 70)
print(f"  GOLD-150 — MAESTRO (LLM-ACTIVE) vs BM25")
print("=" * 70)
print(f"\n  BM25 baseline:     {bm25_baseline:.3f}")
print(f"  Maestro composite: {maestro_avg:.3f}")
print(f"  Lift:              {lift:+.1f} points (target: >= +15)")
print(f"\n  Per-type breakdown:")
print(f"    {'type':<20s} {'maestro':>8s}")
for t_name, scores in sorted(by_type.items()):
    m_avg = sum(scores) / len(scores) if scores else 0
    print(f"    {t_name:<20s} {m_avg:>8.3f}")

print(f"\n  LLM active on {llm_active_count}/{len(results)} answers")
avg_confidence = sum(r.get("confidence", 0) for r in results) / len(results) if results else 0
avg_latency = sum(r.get("elapsed", 0) for r in results) / len(results) if results else 0
print(f"  Avg confidence: {avg_confidence:.3f}")
print(f"  Avg latency:    {avg_latency:.1f}s")

# HONESTY GATE
if llm_active_count == 0:
    print(f"\n  FATAL: 0/{len(results)} answers had llm_active=True. Aborting — no file written.")
    sys.exit(1)

gate_pass = lift >= 15
if gate_pass:
    print(f"\n  PASS — Maestro beats BM25 by >= 15 points (got {lift:+.1f})")
else:
    print(f"\n  FAIL — Maestro does not meet the +15-point bar (got {lift:+.1f})")

# 5. Save results
out_path = "/home/z/my-project/download/gold_150_llm_active_full_results.json"
with open(out_path, "w") as f:
    json.dump({
        "mode": "LLM-ACTIVE",
        "provider": provider,
        "probe_verified": probe.get("verified", False),
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
        "tunnel_url": OLLAMA_HOST,
        "model": OLLAMA_MODEL,
        "results": results,
    }, f, indent=2)
print(f"\n[score] Results saved to {out_path}", flush=True)
sys.stdout.flush()
sys.stderr.flush()
os._exit(0)
