"""
Gold-150 scorer — TestClient + batch mode.
Uses TestClient (in-process) which correctly initializes the LLM router.
Processes questions in batches of 25, saving progress to survive crashes.
"""
import os
import sys
import json
import time
import gc
import asyncio
import tempfile

REPO = "/home/z/my-project/MaestroAgent/download/MaestroAgent/maestro-personal"
sys.path.insert(0, f"{REPO}/src")
sys.path.insert(0, REPO)

TUNNEL = os.environ.get("OLLAMA_HOST", "https://theatre-having-receptor-stuart.trycloudflare.com")
MODEL = os.environ.get("OLLAMA_MODEL", "llama3:8b")
TOKEN = "gold-test-token"
DB_PATH = "/tmp/gold_tc_batch.db"
PROGRESS_PATH = "/tmp/gold_150_tc_progress.json"
OUT_PATH = "/home/z/my-project/download/gold_150_llm_active_full_results.json"

# Set env BEFORE any imports
os.environ["MAESTRO_PERSONAL_DB"] = DB_PATH
os.environ["MAESTRO_PERSONAL_TOKEN"] = TOKEN
os.environ["MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL"] = "1"
os.environ["MAESTRO_ENV"] = "dev"
os.environ["OLLAMA_HOST"] = TUNNEL
os.environ["OLLAMA_MODEL"] = MODEL

# Clean slate
if os.path.exists(DB_PATH):
    os.unlink(DB_PATH)

from maestro_personal_shell.api import init_db, app
init_db()

# Reset LLM router AFTER all imports (critical — imports may cache None)
from maestro_personal_shell.llm_bridge import reset_llm_router, get_llm_provider_name, probe_provider
reset_llm_router()
probe = asyncio.run(probe_provider(force=True))
print(f"[score] LLM provider: {get_llm_provider_name()}, verified: {probe.get('verified')}", flush=True)
assert probe.get("verified") is True, "LLM probe failed — aborting"

# Seed directly into DB
from maestro_personal_shell.db_util import get_db_conn
from evaluation.scoreboard.gold_150 import GOLD_150

conn = get_db_conn()
all_signals = []
for q in GOLD_150:
    for sig in q.get("seed_signals", []):
        all_signals.append(sig)
seen = set()
seeded = 0
for i, sig in enumerate(all_signals):
    key = (sig.get("entity", ""), sig.get("text", ""))
    if key in seen:
        continue
    seen.add(key)
    conn.execute(
        "INSERT OR IGNORE INTO signals (signal_id, user_email, entity, text, signal_type, timestamp, metadata, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (f"sig-seed-{i+1:04d}", "default@personal.local", sig.get("entity", ""), sig.get("text", ""),
         sig.get("signal_type", "reported_statement"),
         sig.get("timestamp", "2026-07-14T00:00:00Z"),
         json.dumps({"signal_type": sig.get("signal_type", "reported_statement")}),
         "2026-07-14T00:00:00Z"),
    )
    seeded += 1
conn.commit()
conn.close()
print(f"[score] Seeded {seeded} signals", flush=True)

# Build FTS index
try:
    from maestro_personal_shell.semantic_retrieval import rebuild_fts_index
    count = rebuild_fts_index()
    print(f"[score] FTS index rebuilt: {count} signals", flush=True)
except Exception as e:
    print(f"[score] FTS rebuild failed: {e}", flush=True)

# Login
from fastapi.testclient import TestClient
client = TestClient(app)
r = client.post("/api/auth/login", json={"user_email": "default@personal.local", "password": TOKEN})
TOKEN_ACTUAL = r.json()["token"]
H = {"Authorization": f"Bearer {TOKEN_ACTUAL}"}
print(f"[score] Logged in", flush=True)

# Load progress
if os.path.exists(PROGRESS_PATH):
    with open(PROGRESS_PATH) as f:
        progress = json.load(f)
    results = progress["results"]
    llm_active_count = progress["llm_active_count"]
    print(f"[score] Resuming from {len(results)} completed questions", flush=True)
else:
    results = []
    llm_active_count = 0

start_idx = len(results)
print(f"\n[score] Starting from question {start_idx+1}, {len(GOLD_150)-start_idx} remaining", flush=True)

t_start = time.time()
for i in range(start_idx, len(GOLD_150)):
    q = GOLD_150[i]
    t0 = time.time()
    try:
        r = client.post("/api/ask", json={"query": q["query"]}, headers=H, timeout=120)
        elapsed = time.time() - t0
        if r.status_code != 200:
            print(f"  [{i+1:>3}/150] FAIL {q['type']:15s} -> {r.status_code}", flush=True)
            results.append({"id": q["id"], "type": q["type"], "query": q["query"], "score": 0.0, "error": f"HTTP {r.status_code}", "llm_active": False, "elapsed": elapsed})
        else:
            body = r.json()
            answer = body.get("answer", "")
            llm_active = body.get("llm_active", False)
            confidence = body.get("confidence", 0)
            evidence = body.get("evidence_refs", [])
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
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  [{i+1:>3}/150] ERR  {q['type']:15s} -> {e}", flush=True)
        results.append({"id": q["id"], "type": q["type"], "query": q["query"], "score": 0.0, "error": str(e)[:200], "llm_active": False, "elapsed": elapsed})

    # Save progress EVERY question (survive OOM kills)
    with open(PROGRESS_PATH, "w") as f:
        json.dump({"results": results, "llm_active_count": llm_active_count}, f)
    gc.collect()

# Compute composite
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

with open(OUT_PATH, "w") as f:
    json.dump({
        "mode": "LLM-ACTIVE",
        "provider": get_llm_provider_name(),
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
        "tunnel_url": TUNNEL,
        "model": MODEL,
        "results": results,
    }, f, indent=2)
print(f"\nResults saved to {OUT_PATH}", flush=True)
if os.path.exists(PROGRESS_PATH):
    os.unlink(PROGRESS_PATH)
os._exit(0)
