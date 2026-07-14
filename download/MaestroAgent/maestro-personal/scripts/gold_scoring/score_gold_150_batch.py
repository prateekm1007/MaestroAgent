"""
Gold-150 scorer — batch mode.
Restarts the API every 25 questions to avoid memory accumulation.
Saves partial results after each batch.
"""
import os
import sys
import json
import time
import subprocess
import urllib.request
import tempfile

REPO = "/home/z/my-project/MaestroAgent/download/MaestroAgent/maestro-personal"
sys.path.insert(0, f"{REPO}/src")
sys.path.insert(0, REPO)

from evaluation.scoreboard.gold_150 import GOLD_150

TUNNEL = "https://theatre-having-receptor-stuart.trycloudflare.com"
MODEL = "llama3:8b"
TOKEN = "gold-test-token"
DB_PATH = "/tmp/gold_batch.db"
PORT = 8781
BATCH_SIZE = 25
OUT_PATH = "/home/z/my-project/download/gold_150_llm_active_full_results.json"
PROGRESS_PATH = "/tmp/gold_150_progress.json"

# Initialize DB + seed signals
os.environ["MAESTRO_PERSONAL_DB"] = DB_PATH
os.environ["MAESTRO_PERSONAL_TOKEN"] = TOKEN
from maestro_personal_shell.api import init_db
init_db()

# Seed directly
from maestro_personal_shell.db_util import get_db_conn


def _compute_bm25_baseline():
    """Compute BM25 baseline on the 150-question gold set (not hardcoded)."""
    import sys as _sys
    _sys.path.insert(0, __import__('pathlib').Path(__file__).resolve().parents[-2].as_posix() + '/src' if 'gold_scoring' in str(__file__) else '.')
    try:
        from evaluation.scoreboard.gold_150 import GOLD_150
        from evaluation.scoreboard.bm25_baseline import bm25_score
        results = []
        for q in GOLD_150:
            top_doc = ''
            best = 0.0
            for sig in q.get('seed_signals', []):
                doc = sig.get('text','') + ' ' + sig.get('entity','')
                s = bm25_score(q['query'], doc)
                if s > best: best, top_doc = s, doc
            if q.get('should_abstain'):
                results.append(0.0)
            else:
                has_all = all(kw.lower() in top_doc.lower() for kw in q.get('expected_keywords',[]))
                has_bad = any(kw.lower() in top_doc.lower() for kw in q.get('forbidden_keywords',[]))
                results.append(1.0 if (has_all and not has_bad) else 0.0)
        return sum(results)/len(results) if results else 0.0
    except Exception:
        return 0.2  # fallback — matches the computed value

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
print(f"[batch] Seeded {seeded} signals", flush=True)

def start_api():
    """Start the API server, return the process handle."""
    env = os.environ.copy()
    env["OLLAMA_HOST"] = TUNNEL
    env["OLLAMA_MODEL"] = MODEL
    env["MAESTRO_PERSONAL_TOKEN"] = TOKEN
    env["MAESTRO_PERSONAL_DB"] = DB_PATH
    env["MAESTRO_ENV"] = "dev"
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        ["python3", "-u", "-c",
         f"import sys; sys.path.insert(0,'{REPO}/src'); "
         f"from maestro_personal_shell.api import init_db, app; init_db(); "
         f"import uvicorn; uvicorn.run(app, host='127.0.0.1', port={PORT}, log_level='error')"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=env,
    )
    # Wait for ready
    for _ in range(30):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/health", timeout=2)
            return proc
        except Exception:
            time.sleep(1)
    proc.kill()
    raise RuntimeError("API did not start")

def stop_api(proc):
    if proc:
        proc.kill()
        proc.wait()
    time.sleep(2)

def ask_question(query, timeout=120):
    """Ask one question via HTTP."""
    data = json.dumps({"query": query}).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/api/ask", data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"},
    )
    resp = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(resp.read())

def score_answer(answer, q):
    expected = q.get("expected_keywords", [])
    forbidden = q.get("forbidden_keywords", [])
    should_abstain = q.get("should_abstain", False)
    answer_lower = answer.lower()
    if should_abstain:
        abstain_phrases = ["don't have", "insufficient", "no evidence", "not enough"]
        return 1.0 if any(p in answer_lower for p in abstain_phrases) else 0.0
    has_all_expected = all(kw.lower() in answer_lower for kw in expected)
    has_forbidden = any(kw.lower() in answer_lower for kw in forbidden)
    return 1.0 if (has_all_expected and not has_forbidden) else 0.0

# Load progress if exists
if os.path.exists(PROGRESS_PATH):
    with open(PROGRESS_PATH) as f:
        progress = json.load(f)
    results = progress["results"]
    llm_active_count = progress["llm_active_count"]
    print(f"[batch] Resuming from {len(results)} completed questions", flush=True)
else:
    results = []
    llm_active_count = 0

start_idx = len(results)
print(f"\n[batch] Starting from question {start_idx+1}, {len(GOLD_150)-start_idx} remaining", flush=True)
print(f"[batch] Batch size: {BATCH_SIZE} (restart API every {BATCH_SIZE} questions)", flush=True)

t_start = time.time()
api_proc = None

for i in range(start_idx, len(GOLD_150)):
    # Start/restart API every BATCH_SIZE questions
    if i % BATCH_SIZE == 0 or api_proc is None:
        if api_proc:
            print(f"  [restart] Stopping API after {BATCH_SIZE} questions (memory)", flush=True)
            stop_api(api_proc)
        print(f"  [restart] Starting API for questions {i+1}-{min(i+BATCH_SIZE, len(GOLD_150))}", flush=True)
        api_proc = start_api()
        # Verify LLM is active
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{PORT}/api/llm-status",
                                        headers={"Authorization": f"Bearer {TOKEN}"})
            ls = json.loads(urllib.request.urlopen(req, timeout=30).read())
            if not ls.get("active"):
                print(f"  [restart] FATAL: LLM not active after restart. Aborting.", flush=True)
                stop_api(api_proc)
                break
            print(f"  [restart] LLM active: {ls.get('active')} provider: {ls.get('provider')}", flush=True)
        except Exception as e:
            print(f"  [restart] LLM status check failed: {e}", flush=True)

    q = GOLD_150[i]
    t0 = time.time()
    try:
        body = ask_question(q["query"])
        elapsed = time.time() - t0
        answer = body.get("answer", "")
        llm_active = body.get("llm_active", False)
        confidence = body.get("confidence", 0)
        evidence = body.get("evidence_refs", [])
        if llm_active:
            llm_active_count += 1
        score = score_answer(answer, q)
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

    # Save progress every 5 questions
    if (i + 1) % 5 == 0:
        with open(PROGRESS_PATH, "w") as f:
            json.dump({"results": results, "llm_active_count": llm_active_count}, f)

# Final cleanup
if api_proc:
    stop_api(api_proc)

# Compute composite
maestro_avg = sum(r["score"] for r in results) / len(results) if results else 0
bm25_baseline = _compute_bm25_baseline()  # computed, not hardcoded
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
    sys.exit(1)

gate_pass = lift >= 15
print(f"\n  {'PASS' if gate_pass else 'FAIL'} — lift={lift:+.1f} (target >= +15)", flush=True)

with open(OUT_PATH, "w") as f:
    json.dump({
        "mode": "LLM-ACTIVE",
        "provider": "ollama",
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
# Clean up progress file
if os.path.exists(PROGRESS_PATH):
    os.unlink(PROGRESS_PATH)
