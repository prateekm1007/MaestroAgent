"""
HTTP server runner — starts uvicorn in a subprocess so the event loop
doesn't conflict with OpenRouter's async client. The parent process
fires HTTP requests to the subprocess.

Usage:
    OPENROUTER_API_KEY=... OPENROUTER_MODEL=... python3 evaluation/scoreboard/run_50q_http.py
"""
import os
import sys
import json
import time
import tempfile
import subprocess
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

REPO = Path(__file__).resolve().parents[3]
SHELL_SRC = REPO / "maestro-personal" / "src"
sys.path.insert(0, str(SHELL_SRC))
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "maestro-personal"))

PORT = 8860

# ── Fresh DB ──────────────────────────────────────────────────────
tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="gold50http_")
tmp_db.close()
DB_PATH = tmp_db.name
TOKEN = "gold50http"

# ── Bulk-seed directly into SQLite ────────────────────────────────
print("[runner] Bulk-seeding signals...", flush=True)
from evaluation.scoreboard.memory_v1 import get_corpus, get_questions
from evaluation.scoreboard.bm25_baseline import score_answer, bm25_retrieve

# Set env vars BEFORE importing maestro_personal_shell (it reads DB_PATH at import)
os.environ["MAESTRO_PERSONAL_DB"] = DB_PATH
os.environ["MAESTRO_PERSONAL_TOKEN"] = TOKEN
os.environ["MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL"] = "1"

# Seed via Python (runs in THIS process, no server needed)
sys.path.insert(0, str(SHELL_SRC))
sys.path.insert(0, str(REPO / "backend"))
from maestro_personal_shell.db_util import get_db_conn
from maestro_personal_shell import api as pa
pa.init_db()  # Create tables BEFORE seeding

# Also set env for the subprocess
env = os.environ.copy()
env["PYTHONPATH"] = str(SHELL_SRC) + ":" + str(REPO / "backend") + ":" + str(REPO / "maestro-personal")

conn = get_db_conn(DB_PATH)
now = datetime.now(timezone.utc)
corpus = get_corpus()
for sig in corpus:
    conn.execute(
        "INSERT OR REPLACE INTO signals (signal_id, entity, text, signal_type, timestamp, metadata, source_acl, created_at, user_email) VALUES (?,?,?,?,?,?,?,?,?)",
        (str(uuid4()), sig["entity"], sig["text"], sig.get("signal_type", "reported_statement"),
         sig.get("timestamp", now.isoformat()), "{}", "public", sig.get("timestamp", now.isoformat()), "bootstrap"))
conn.commit()
conn.close()

from maestro_personal_shell.semantic_retrieval import rebuild_fts_index
rebuild_fts_index(DB_PATH)
print(f"[runner] Seeded {len(corpus)} signals", flush=True)

# ── Start uvicorn in a SUBPROCESS ─────────────────────────────────
print(f"[runner] Starting uvicorn on port {PORT} (subprocess)...", flush=True)
server_proc = subprocess.Popen(
    [sys.executable, "-c", f"""
import sys
sys.path.insert(0, "{SHELL_SRC}")
sys.path.insert(0, "{REPO / 'backend'}")
from maestro_personal_shell import api as pa
pa.init_db()
import uvicorn
cfg = uvicorn.Config(pa.app, host="127.0.0.1", port={PORT}, log_level="error")
srv = uvicorn.Server(cfg)
srv.run()
"""],
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)

# Wait for API to be ready
import urllib.request as ur
for i in range(60):
    try:
        ur.urlopen(f"http://127.0.0.1:{PORT}/api/health", timeout=2)
        print(f"[runner] API ready after {i}s", flush=True)
        break
    except Exception:
        time.sleep(0.5)
else:
    print("[runner] FATAL: API did not start", flush=True)
    server_proc.kill()
    sys.exit(1)

# Verify LLM
try:
    req = ur.Request(f"http://127.0.0.1:{PORT}/api/llm-status",
                     headers={"Authorization": f"Bearer {TOKEN}"})
    resp = ur.urlopen(req, timeout=30)
    status = json.loads(resp.read())
    print(f"[runner] LLM: provider={status.get('provider')}, active={status.get('active')}", flush=True)
    if not status.get("active"):
        print("[runner] WARNING: LLM not active — check OPENROUTER_API_KEY", flush=True)
except Exception as e:
    print(f"[runner] LLM status check failed: {e}", flush=True)

# ── Fire all 47 questions ─────────────────────────────────────────
ALL_Q = get_questions()
H = {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"}
BASE = f"http://127.0.0.1:{PORT}"

print(f"[runner] Firing {len(ALL_Q)} questions via HTTP...", flush=True)

results = []
RESULT_FILE = "/home/z/my-project/download/maestro_gold_50q_http.json"

for idx, q in enumerate(ALL_Q):
    t0 = time.time()
    data = json.dumps({"query": q["q"]}).encode()
    req = ur.Request(f"{BASE}/api/ask", data=data, headers=H)
    try:
        resp = ur.urlopen(req, timeout=120)
        body = json.loads(resp.read())
        elapsed = time.time() - t0
        answer = body.get("answer", "")
        evidence = body.get("evidence_refs", [])
        # Handle evidence as list of strings or dicts
        ev_list = []
        if isinstance(evidence, list):
            for e in evidence:
                if isinstance(e, dict):
                    ev_list.append(e)
                elif isinstance(e, str):
                    ev_list.append({"text": e, "entity": ""})
        m = score_answer(q, answer, ev_list)
        retrieved = bm25_retrieve(q["q"], corpus, top_k=5)
        bm25_ans = " ".join(r.get("text", "") for r in retrieved)
        b = score_answer(q, bm25_ans, retrieved)
        results.append({
            "question": q["q"], "type": q["expected_type"],
            "maestro_score": m, "bm25_score": b,
            "llm_active": body.get("llm_active", False),
            "llm_provider": body.get("llm_provider", ""),
            "confidence": body.get("confidence", 0),
            "answer_preview": answer[:150],
            "elapsed": round(elapsed, 1),
        })
        marker = "OK" if m >= 0.5 else "--"
        win = "+" if m > b else ("=" if m == b else "-")
        print(f"  [{idx+1:>2}] {marker} {q['expected_type']:15s} m={m:.2f} b={b:.2f} {win} llm={body.get('llm_active')} ({elapsed:.1f}s) {q['q'][:35]}", flush=True)
    except Exception as e:
        results.append({"question": q["q"], "type": q["expected_type"], "maestro_score": 0, "bm25_score": 0, "error": str(e)[:80]})
        print(f"  [{idx+1:>2}] ERR {q['expected_type']:15s} {str(e)[:50]}", flush=True)

    # Save partial every 5 questions
    if (idx + 1) % 5 == 0 or idx == len(ALL_Q) - 1:
        m_avg = sum(r["maestro_score"] for r in results) / len(results)
        b_avg = sum(r["bm25_score"] for r in results) / len(results)
        lift = (m_avg - b_avg) * 100
        partial = {
            "commit": "acd357f",
            "provider": "openrouter (google/gemma-4-26b-a4b-it:free)",
            "questions_done": len(results),
            "total_questions": len(ALL_Q),
            "bm25_baseline": round(b_avg, 4),
            "maestro_composite": round(m_avg, 4),
            "lift_points": round(lift, 1),
            "results": results,
        }
        with open(RESULT_FILE, "w") as f:
            json.dump(partial, f, indent=2)

# ── Final summary ─────────────────────────────────────────────────
m_avg = sum(r["maestro_score"] for r in results) / len(results)
b_avg = sum(r["bm25_score"] for r in results) / len(results)
lift = (m_avg - b_avg) * 100
llm_count = sum(1 for r in results if r.get("llm_active"))

by_type = {}
for r in results:
    by_type.setdefault(r["type"], []).append(r)

print(f"\n{'='*70}", flush=True)
print(f"  FULL {len(ALL_Q)}-QUESTION GOLD SCORING — HTTP API + LLM", flush=True)
print(f"{'='*70}", flush=True)
print(f"  BM25 baseline:  {b_avg:.3f}", flush=True)
print(f"  Maestro (LLM):  {m_avg:.3f}", flush=True)
print(f"  Lift:           {lift:+.1f} points (target: >= +15)", flush=True)
print(f"  LLM active:     {llm_count}/{len(results)}", flush=True)
print(f"\n  Per-type:", flush=True)
print(f"    {'type':<20s} {'maestro':>8s} {'bm25':>8s} {'lift':>8s} {'n':>3s}", flush=True)
for t_name in sorted(by_type.keys()):
    rs = by_type[t_name]
    mt = sum(r["maestro_score"] for r in rs) / len(rs)
    bt = sum(r["bm25_score"] for r in rs) / len(rs)
    lt = (mt - bt) * 100
    print(f"    {t_name:<20s} {mt:>8.3f} {bt:>8.3f} {lt:>+8.1f} {len(rs):>3d}", flush=True)

if lift >= 15:
    print(f"\n  PASS — Maestro beats BM25 by >= 15 points!", flush=True)
elif lift > 0:
    print(f"\n  PARTIAL — Maestro beats BM25 by {lift:+.1f} points", flush=True)
else:
    print(f"\n  FAIL — Maestro does not beat BM25 ({lift:+.1f} points)", flush=True)

# Save final
out = {
    "commit": "acd357f",
    "provider": "openrouter (google/gemma-4-26b-a4b-it:free)",
    "bm25_baseline": round(b_avg, 4),
    "maestro_composite": round(m_avg, 4),
    "lift_points": round(lift, 1),
    "llm_active_count": llm_count,
    "total_questions": len(results),
    "per_type": {t: {"maestro": round(sum(r["maestro_score"] for r in by_type[t]) / len(by_type[t]), 4),
                      "bm25": round(sum(r["bm25_score"] for r in by_type[t]) / len(by_type[t]), 4),
                      "n": len(by_type[t])} for t in sorted(by_type.keys())},
    "results": results,
}
with open(RESULT_FILE, "w") as f:
    json.dump(out, f, indent=2)
print(f"\nResults saved to: {RESULT_FILE}", flush=True)

# Shutdown server
server_proc.terminate()
server_proc.wait(timeout=5)
print("[runner] Server shut down.", flush=True)
