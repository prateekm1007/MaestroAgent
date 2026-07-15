"""Gold scoring v2 — bulk-seed directly into SQLite (bypassing the LLM
classifier that was making seeding take 14 min), then fire Ask queries
through the HTTP API with LLM active.

5 representative questions in parallel. Target: Maestro >= 0.75.
"""
import os, sys, json, time, tempfile, threading, statistics, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime, timezone, timedelta
from uuid import uuid4

REPO = Path(__file__).resolve().parents[3]
SHELL_SRC = REPO / "maestro-personal" / "src"
sys.path.insert(0, str(SHELL_SRC))
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "maestro-personal"))

assert os.environ.get("OLLAMA_HOST"), "OLLAMA_HOST must be set"
assert os.environ.get("OLLAMA_MODEL"), "OLLAMA_MODEL must be set"
print(f"Tunnel: {os.environ['OLLAMA_HOST']}")
print(f"Model:  {os.environ['OLLAMA_MODEL']}")

tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="gold_v2_")
tmp_db.close()
os.environ["MAESTRO_PERSONAL_DB"] = tmp_db.name
os.environ["MAESTRO_PERSONAL_TOKEN"] = "gold-v2-token"
os.environ["MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL"] = "1"
os.environ.pop("MAESTRO_PERSONAL_ENV", None)

# ── Bulk-seed directly into SQLite (fast — no LLM classifier) ──────
print("\n[score] Bulk-seeding 32 signals directly into SQLite...")
from maestro_personal_shell.db_util import get_db_conn
from maestro_personal_shell import api as personal_api
personal_api.init_db()

from evaluation.scoreboard.memory_v1 import get_corpus
conn = get_db_conn(tmp_db.name)
now = datetime.now(timezone.utc)
for sig in get_corpus():
    sig_id = str(uuid4())
    ts = sig.get("timestamp", now.isoformat())
    conn.execute(
        """INSERT OR REPLACE INTO signals
           (signal_id, entity, text, signal_type, timestamp, metadata, source_acl, created_at, user_email)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (sig_id, sig["entity"], sig["text"], sig.get("signal_type", "reported_statement"),
         ts, "{}", "public", ts, "default@personal.local"),
    )
conn.commit()
conn.close()
print(f"[score] Seeded {len(get_corpus())} signals")

# Rebuild FTS
from maestro_personal_shell.semantic_retrieval import rebuild_fts_index
count = rebuild_fts_index(tmp_db.name)
print(f"[score] FTS index: {count} signals")

# ── Start API with LLM ────────────────────────────────────────────
print("\n[score] Starting API with LLM active...")
import uvicorn
config = uvicorn.Config(personal_api.app, host="127.0.0.1", port=8786, log_level="error")
server = uvicorn.Server(config)
t = threading.Thread(target=server.run, daemon=True)
t.start()
for i in range(40):
    try:
        urllib.request.urlopen("http://127.0.0.1:8786/api/health", timeout=2)
        print(f"[score] API ready after {i}s")
        break
    except Exception:
        time.sleep(0.5)

# Verify LLM
from maestro_personal_shell.llm_bridge import reset_llm_router, probe_provider
import asyncio
reset_llm_router()
probe = asyncio.run(probe_provider(force=True))
print(f"[score] LLM verified: {probe.get('verified')}, latency: {probe.get('latency_ms')}ms")
assert probe.get("verified") is True

# ── Fire 5 questions in parallel ──────────────────────────────────
from evaluation.scoreboard.memory_v1 import get_questions
from evaluation.scoreboard.bm25_baseline import score_answer, bm25_retrieve
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = "http://127.0.0.1:8786"
TOKEN = "gold-v2-token"

# Login first
data = json.dumps({"password": TOKEN}).encode()
req = urllib.request.Request(f"{BASE}/api/auth/login", data=data,
                             headers={"Content-Type": "application/json"})
resp = urllib.request.urlopen(req, timeout=10)
# Use AUTH_TOKEN directly (it equals TOKEN in dev mode)

ALL_Q = get_questions()
INDICES = [0, 4, 6, 9, 35]  # direct_lookup, broken, relational, contradiction, abstention
questions = [ALL_Q[i] for i in INDICES]
print(f"\n[score] Firing {len(questions)} questions in parallel...")

def fire_question(q):
    t0 = time.time()
    data = json.dumps({"query": q["q"]}).encode()
    req = urllib.request.Request(f"{BASE}/api/ask", data=data,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {TOKEN}"})
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        body = json.loads(resp.read())
        elapsed = time.time() - t0
        answer = body.get("answer", "")
        evidence = body.get("evidence_refs", [])
        m_score = score_answer(q, answer, evidence if isinstance(evidence, list) else [])
        retrieved = bm25_retrieve(q["q"], get_corpus(), top_k=5)
        bm25_answer = " ".join(r.get("text", "") for r in retrieved)
        b_score = score_answer(q, bm25_answer, retrieved)
        return {
            "q": q["q"], "type": q["expected_type"],
            "maestro_score": m_score, "bm25_score": b_score,
            "answer_preview": answer[:120],
            "llm_active": body.get("llm_active", False),
            "confidence": body.get("confidence", 0),
            "elapsed": elapsed,
        }
    except Exception as e:
        return {"q": q["q"], "type": q["expected_type"], "maestro_score": 0.0,
                "bm25_score": 0.0, "error": str(e)[:100], "elapsed": time.time() - t0}

results = [None] * len(questions)
with ThreadPoolExecutor(max_workers=3) as pool:
    future_to_idx = {pool.submit(fire_question, q): i for i, q in enumerate(questions)}
    for future in as_completed(future_to_idx):
        idx = future_to_idx[future]
        try:
            results[idx] = future.result()
            r = results[idx]
            print(f"  [{idx+1}] {r['type']:15s} m={r['maestro_score']:.2f} b={r['bm25_score']:.2f} ({r['elapsed']:.1f}s)")
        except Exception as e:
            print(f"  [{idx+1}] ERROR: {e}")
            results[idx] = {"q": questions[idx]["q"], "type": questions[idx]["expected_type"],
                           "maestro_score": 0.0, "bm25_score": 0.0, "error": str(e)}

# ── Compute composites ────────────────────────────────────────────
valid = [r for r in results if r is not None]
m_avg = sum(r["maestro_score"] for r in valid) / len(valid)
b_avg = sum(r["bm25_score"] for r in valid) / len(valid)
lift = (m_avg - b_avg) * 100

print("\n" + "=" * 70)
print("  MEMORY GOLD SET — 5-QUESTION PARALLEL (LLM ACTIVE)")
print("=" * 70)
print(f"\n  BM25 baseline:  {b_avg:.3f}")
print(f"  Maestro (LLM):  {m_avg:.3f}")
print(f"  Lift:           {lift:+.1f} points (target: >= +15)")

print(f"\n  Per-question:")
print(f"    {'type':<20s} {'maestro':>8s} {'bm25':>8s} {'win':>4s}")
for r in valid:
    win = "+" if r["maestro_score"] > r["bm25_score"] else ("=" if r["maestro_score"] == r["bm25_score"] else "-")
    print(f"    {r['type']:<20s} {r['maestro_score']:>8.2f} {r['bm25_score']:>8.2f} {win:>4s}")

llm_active_count = sum(1 for r in valid if r.get("llm_active"))
avg_conf = sum(r.get("confidence", 0) for r in valid) / len(valid)
avg_lat = sum(r.get("elapsed", 0) for r in valid) / len(valid)
print(f"\n  LLM active: {llm_active_count}/{len(valid)}")
print(f"  Avg confidence: {avg_conf:.3f}")
print(f"  Avg latency:    {avg_lat:.1f}s")

if lift >= 15:
    print("\n  PASS — Maestro beats BM25 by >= 15 points")
elif lift > 0:
    print(f"\n  PARTIAL — Maestro beats BM25 by {lift:+.1f} points (target: >= +15)")
else:
    print(f"\n  FAIL — Maestro does not beat BM25 ({lift:+.1f} points)")

out_path = "/home/z/my-project/download/maestro_gold_results_final.json"
with open(out_path, "w") as f:
    json.dump({
        "subset_size": len(valid),
        "bm25_baseline": b_avg,
        "maestro_composite": m_avg,
        "lift_points": lift,
        "llm_active_count": llm_active_count,
        "results": valid,
    }, f, indent=2)
print(f"\n  Full results: {out_path}")

server.should_exit = True
time.sleep(1)
