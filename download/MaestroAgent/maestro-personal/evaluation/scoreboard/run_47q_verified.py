"""
Reproducible 47-question gold scoring with FULL answer text.

This is the GENERATOR SCRIPT for maestro_gold_47q_llm_active.json.
Per governance P1: every claim must be reproducible from a committed script.

Usage:
    OLLAMA_HOST=https://<tunnel> OLLAMA_MODEL=llama3:8b \
    PYTHONPATH=src python3 evaluation/scoreboard/run_47q_verified.py

Output: evaluation/scoreboard/maestro_gold_47q_llm_active.json
  - Full answer text for every question (auditor can verify)
  - Full evidence_refs for every question
  - Per-question Maestro score + BM25 score
  - llm_active flag for every question
  - Per-type breakdown
  - Composite lift vs BM25

Runs in 5 chunks of ~10 questions to stay within sandbox timeouts.
Each chunk saves partial results; the final step combines them.
"""
import os, sys, json, time, tempfile, subprocess, urllib.request
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

REPO = Path(__file__).resolve().parents[3]
SHELL_SRC = REPO / "maestro-personal" / "src"
sys.path.insert(0, str(SHELL_SRC))
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "maestro-personal"))

PORT = int(os.environ.get("GOLD_PORT", "8950"))
TOKEN = "gold47q"
DB_PATH = os.environ.get("GOLD_DB", "/tmp/maestro_47q_verified.db")

# ── Seed DB (shared across chunks) ────────────────────────────────
os.environ["MAESTRO_PERSONAL_DB"] = DB_PATH
os.environ["MAESTRO_PERSONAL_TOKEN"] = TOKEN
os.environ["MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL"] = "1"

if not os.path.exists(DB_PATH):
    from maestro_personal_shell import api as pa
    pa.init_db()
    from evaluation.scoreboard.memory_v1 import get_corpus
    from maestro_personal_shell.db_util import get_db_conn
    conn = get_db_conn(DB_PATH)
    now = datetime.now(timezone.utc)
    for sig in get_corpus():
        conn.execute(
            "INSERT OR REPLACE INTO signals (signal_id, entity, text, signal_type, timestamp, metadata, source_acl, created_at, user_email) VALUES (?,?,?,?,?,?,?,?,?)",
            (str(uuid4()), sig["entity"], sig["text"], sig.get("signal_type", "reported_statement"),
             sig.get("timestamp", now.isoformat()), "{}", "public", sig.get("timestamp", now.isoformat()), "bootstrap"))
    conn.commit()
    conn.close()
    from maestro_personal_shell.semantic_retrieval import rebuild_fts_index
    rebuild_fts_index(DB_PATH)
    print(f"Seeded {len(get_corpus())} signals to {DB_PATH}", flush=True)
else:
    print(f"Using existing DB at {DB_PATH}", flush=True)

# ── Start server in subprocess ────────────────────────────────────
env = os.environ.copy()
env["PYTHONPATH"] = str(SHELL_SRC) + ":" + str(REPO / "backend") + ":" + str(REPO / "maestro-personal")
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
    env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
for i in range(60):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/health", timeout=2)
        print("API ready", flush=True)
        break
    except Exception:
        time.sleep(0.5)

# Verify LLM
H = {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"}
BASE = f"http://127.0.0.1:{PORT}"
req = urllib.request.Request(f"{BASE}/api/llm-status", headers=H)
resp = urllib.request.urlopen(req, timeout=30)
status = json.loads(resp.read())
print(f"LLM: active={status.get('active')} provider={status.get('provider')} verified={status.get('verified')}", flush=True)
assert status.get("active"), f"LLM not active — check OLLAMA_HOST={os.environ.get('OLLAMA_HOST','NOT SET')}"

# ── Fire all 47 questions WITH FULL ANSWER TEXT ───────────────────
from evaluation.scoreboard.memory_v1 import get_questions, get_corpus
from evaluation.scoreboard.bm25_baseline import score_answer, bm25_retrieve

ALL_Q = get_questions()
corpus = get_corpus()
print(f"Firing {len(ALL_Q)} questions with full answer text...", flush=True)

results = []
for idx, q in enumerate(ALL_Q):
    t0 = time.time()
    data = json.dumps({"query": q["q"]}).encode()
    req = urllib.request.Request(f"{BASE}/api/ask", data=data, headers=H)
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        body = json.loads(resp.read())
        elapsed = time.time() - t0
        answer = body.get("answer", "")
        evidence = body.get("evidence_refs", [])
        ev_list = []
        if isinstance(evidence, list):
            for e in evidence:
                if isinstance(e, dict):
                    ev_list.append(e)
                elif isinstance(e, str):
                    ev_list.append({"text": e, "entity": ""})

        m = score_answer(q, answer, ev_list)
        retrieved = bm25_retrieve(q["q"], corpus, top_k=5)
        bm25_answer = " ".join(r.get("text", "") for r in retrieved)
        b = score_answer(q, bm25_answer, retrieved)

        results.append({
            "idx": idx,
            "question": q["q"],
            "type": q["expected_type"],
            "maestro_score": m,
            "bm25_score": b,
            "llm_active": body.get("llm_active", False),
            "llm_provider": body.get("llm_provider", ""),
            "confidence": body.get("confidence", 0),
            "intelligence_source": body.get("intelligence_source", ""),
            "answer": answer,
            "answer_preview": answer[:200],
            "source_sentence": body.get("source_sentence", ""),
            "source_entity": body.get("source_entity", ""),
            "evidence_refs": ev_list[:5],
            "bm25_top_text": bm25_answer[:200],
            "elapsed": round(elapsed, 1),
        })
        marker = "OK" if m >= 0.5 else "--"
        win = "+" if m > b else ("=" if m == b else "-")
        print(f"  [{idx+1:>2}] {marker} {q['expected_type']:15s} m={m:.2f} b={b:.2f} {win} llm={body.get('llm_active')} ({elapsed:.1f}s) {q['q'][:35]}", flush=True)
    except Exception as e:
        results.append({
            "idx": idx,
            "question": q["q"],
            "type": q["expected_type"],
            "maestro_score": 0,
            "bm25_score": 0,
            "llm_active": False,
            "error": str(e)[:100],
            "elapsed": round(time.time() - t0, 1),
        })
        print(f"  [{idx+1:>2}] ERR {q['expected_type']:15s} {str(e)[:50]}", flush=True)

    # Save partial every 10 questions
    if (idx + 1) % 10 == 0 or idx == len(ALL_Q) - 1:
        m_avg = sum(r["maestro_score"] for r in results) / len(results)
        b_avg = sum(r["bm25_score"] for r in results) / len(results)
        lift = (m_avg - b_avg) * 100
        partial = {
            "questions_done": len(results),
            "total_questions": len(ALL_Q),
            "bm25_baseline": round(b_avg, 4),
            "maestro_composite": round(m_avg, 4),
            "lift_points": round(lift, 1),
            "results": results,
        }
        partial_path = REPO / "maestro-personal" / "evaluation" / "scoreboard" / "maestro_gold_47q_llm_active.json"
        with open(partial_path, "w") as f:
            json.dump(partial, f, indent=2)

# ── Final summary ─────────────────────────────────────────────────
m_avg = sum(r["maestro_score"] for r in results) / len(results)
b_avg = sum(r["bm25_score"] for r in results) / len(results)
lift = (m_avg - b_avg) * 100
llm_count = sum(1 for r in results if r.get("llm_active"))

by_type = {}
for r in results:
    t = r["type"]
    by_type.setdefault(t, {"m": [], "b": []})
    by_type[t]["m"].append(r["maestro_score"])
    by_type[t]["b"].append(r["bm25_score"])

print(f"\n{'='*70}", flush=True)
print(f"  47-QUESTION GOLD SCORING — VERIFIED WITH FULL ANSWER TEXT", flush=True)
print(f"{'='*70}", flush=True)
print(f"  BM25 baseline:  {b_avg:.3f}", flush=True)
print(f"  Maestro (LLM):  {m_avg:.3f}", flush=True)
print(f"  Lift:           {lift:+.1f} points (target: >= +15)", flush=True)
print(f"  LLM active:     {llm_count}/{len(results)}", flush=True)
print(f"\n  Per-type:", flush=True)
print(f"    {'type':<20s} {'maestro':>8s} {'bm25':>8s} {'lift':>8s} {'n':>3s}", flush=True)
for t_name in sorted(by_type.keys()):
    ms = by_type[t_name]["m"]
    bs = by_type[t_name]["b"]
    mt = sum(ms) / len(ms)
    bt = sum(bs) / len(bs)
    lt = (mt - bt) * 100
    print(f"    {t_name:<20s} {mt:>8.3f} {bt:>8.3f} {lt:>+8.1f} {len(ms):>3d}", flush=True)

if lift >= 15:
    print(f"\n  PASS — Maestro beats BM25 by >= 15 points!", flush=True)
elif lift > 0:
    print(f"\n  PARTIAL — Maestro beats BM25 by {lift:+.1f} points", flush=True)
else:
    print(f"\n  FAIL — Maestro does not beat BM25 ({lift:+.1f} points)", flush=True)

# Save final JSON with full answer text
out = {
    "generator_script": "evaluation/scoreboard/run_47q_verified.py",
    "commit": subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO).decode().strip(),
    "provider": f"ollama ({os.environ.get('OLLAMA_MODEL', 'llama3:8b')})",
    "tunnel": os.environ.get("OLLAMA_HOST", "NOT SET"),
    "bm25_baseline": round(b_avg, 4),
    "maestro_composite": round(m_avg, 4),
    "lift_points": round(lift, 1),
    "llm_active_count": llm_count,
    "total_questions": len(results),
    "per_type": {t: {"maestro": round(sum(by_type[t]["m"]) / len(by_type[t]["m"]), 4),
                      "bm25": round(sum(by_type[t]["b"]) / len(by_type[t]["b"]), 4),
                      "n": len(by_type[t]["m"])} for t in sorted(by_type.keys())},
    "results": results,
}
out_path = REPO / "maestro-personal" / "evaluation" / "scoreboard" / "maestro_gold_47q_llm_active.json"
with open(out_path, "w") as f:
    json.dump(out, f, indent=2)
print(f"\nResults saved to: {out_path}", flush=True)
print(f"Full answer text included for all {len(results)} questions.", flush=True)

server_proc.terminate()
server_proc.wait(timeout=5)
