"""Gold scoring v4 — sequential (1 question at a time) to avoid P100
overload. P11 fix + 60s latency budget active."""
import os, sys, json, time, tempfile, threading, urllib.request
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "maestro-personal" / "src"))
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "maestro-personal"))

assert os.environ.get("OLLAMA_HOST"), "OLLAMA_HOST must be set"
assert os.environ.get("OLLAMA_MODEL"), "OLLAMA_MODEL must be set"
print(f"Tunnel: {os.environ['OLLAMA_HOST']}")
print(f"Model:  {os.environ['OLLAMA_MODEL']}")

tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="gold_v4_")
tmp_db.close()
os.environ["MAESTRO_PERSONAL_DB"] = tmp_db.name
os.environ["MAESTRO_PERSONAL_TOKEN"] = "gold-v4-token"
os.environ["MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL"] = "1"
os.environ.pop("MAESTRO_PERSONAL_ENV", None)

# Bulk-seed for user=bootstrap
print("\n[score] Bulk-seeding for user=bootstrap...")
from maestro_personal_shell.db_util import get_db_conn
from maestro_personal_shell import api as personal_api
personal_api.init_db()

from evaluation.scoreboard.memory_v1 import get_corpus, get_questions
from evaluation.scoreboard.bm25_baseline import score_answer, bm25_retrieve

conn = get_db_conn(tmp_db.name)
now = datetime.now(timezone.utc)
for sig in get_corpus():
    conn.execute(
        "INSERT OR REPLACE INTO signals (signal_id, entity, text, signal_type, timestamp, metadata, source_acl, created_at, user_email) VALUES (?,?,?,?,?,?,?,?,?)",
        (str(uuid4()), sig["entity"], sig["text"], sig.get("signal_type", "reported_statement"),
         sig.get("timestamp", now.isoformat()), "{}", "public", sig.get("timestamp", now.isoformat()), "bootstrap"))
conn.commit()
conn.close()

from maestro_personal_shell.semantic_retrieval import rebuild_fts_index
rebuild_fts_index(tmp_db.name)
print(f"[score] Seeded {len(get_corpus())} signals")

# Start API
print("\n[score] Starting API with LLM active...")
import uvicorn
config = uvicorn.Config(personal_api.app, host="127.0.0.1", port=8800, log_level="error")
server = uvicorn.Server(config)
t = threading.Thread(target=server.run, daemon=True)
t.start()
for i in range(40):
    try:
        urllib.request.urlopen("http://127.0.0.1:8800/api/health", timeout=2)
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

# Fire 5 questions SEQUENTIALLY (P100 can't handle parallel)
TOKEN = "gold-v4-token"
BASE = "http://127.0.0.1:8800"
H = {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"}

ALL_Q = get_questions()
INDICES = [0, 4, 6, 9, 35]
questions = [ALL_Q[i] for i in INDICES]
print(f"\n[score] Firing {len(questions)} questions SEQUENTIALLY (P11 fix + 60s budget)...")

results = []
for i, q in enumerate(questions):
    t0 = time.time()
    data = json.dumps({"query": q["q"]}).encode()
    req = urllib.request.Request(f"{BASE}/api/ask", data=data, headers=H)
    try:
        resp = urllib.request.urlopen(req, timeout=90)
        body = json.loads(resp.read())
        elapsed = time.time() - t0
        answer = body.get("answer", "")
        evidence = body.get("evidence_refs", [])
        m = score_answer(q, answer, evidence if isinstance(evidence, list) else [])
        retrieved = bm25_retrieve(q["q"], get_corpus(), top_k=5)
        bm25_ans = " ".join(r.get("text", "") for r in retrieved)
        b = score_answer(q, bm25_ans, retrieved)
        llm = body.get("llm_active", False)
        conf = body.get("confidence", 0)
        results.append({"q": q["q"], "type": q["expected_type"], "m": m, "b": b,
                        "llm": llm, "conf": conf, "ans": answer[:150], "elapsed": elapsed})
        print(f"  [{i+1}] {q['expected_type']:15s} m={m:.2f} b={b:.2f} llm={llm} ({elapsed:.1f}s)")
    except Exception as e:
        results.append({"q": q["q"], "type": q["expected_type"], "m": 0, "b": 0, "error": str(e)[:100]})
        print(f"  [{i+1}] {q['expected_type']:15s} ERROR: {str(e)[:60]}")

# Compute composites
valid = [r for r in results if r]
m_avg = sum(r["m"] for r in valid) / len(valid)
b_avg = sum(r["b"] for r in valid) / len(valid)
lift = (m_avg - b_avg) * 100
llm_count = sum(1 for r in valid if r.get("llm"))

print("\n" + "=" * 70)
print("  MEMORY GOLD SET — 5-QUESTION SEQUENTIAL (P11 FIX + LLM ACTIVE)")
print("=" * 70)
print(f"\n  BM25 baseline:  {b_avg:.3f}")
print(f"  Maestro (LLM):  {m_avg:.3f}")
print(f"  Lift:           {lift:+.1f} points (target: >= +15)")
print(f"  LLM active:     {llm_count}/{len(valid)}")

print(f"\n  Per-question:")
for r in valid:
    win = "+" if r["m"] > r["b"] else ("=" if r["m"] == r["b"] else "-")
    print(f"    {r['type']:<20s} m={r['m']:.2f} b={r['b']:.2f} {win}  llm={r.get('llm')}  {r.get('ans','')[:80]}")

if lift >= 15:
    print("\n  PASS — Maestro beats BM25 by >= 15 points")
elif lift > 0:
    print(f"\n  PARTIAL — Maestro beats BM25 by {lift:+.1f} points (target: >= +15)")
else:
    print(f"\n  MAESTRO DOES NOT BEAT BM25 ({lift:+.1f} points)")

out_path = "/home/z/my-project/download/maestro_gold_results_p11fix.json"
with open(out_path, "w") as f:
    json.dump({"bm25": b_avg, "maestro": m_avg, "lift": lift, "llm_active": llm_count, "results": valid}, f, indent=2)
print(f"\n  Results: {out_path}")

server.should_exit = True
time.sleep(1)
