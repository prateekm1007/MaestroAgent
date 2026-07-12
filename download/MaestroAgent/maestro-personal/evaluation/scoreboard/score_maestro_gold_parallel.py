"""5-question ultra-quick gold scoring — fires requests in parallel to
stay under the bash timeout."""
import os, sys, json, time, tempfile, threading, urllib.request, urllib.error
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Resolve repo root from script location (works from any clone)
# Script is at: <repo>/maestro-personal/evaluation/scoreboard/<this>.py
# Repo root is: parents[3]
REPO = Path(__file__).resolve().parents[3]
SHELL_SRC = REPO / "maestro-personal" / "src"
sys.path.insert(0, str(SHELL_SRC))
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "maestro-personal"))

assert os.environ.get("OLLAMA_HOST"), "OLLAMA_HOST must be set"
assert os.environ.get("OLLAMA_MODEL"), "OLLAMA_MODEL must be set"
print(f"Tunnel: {os.environ['OLLAMA_HOST']}")
print(f"Model:  {os.environ['OLLAMA_MODEL']}")

tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="maestro_gold_")
tmp_db.close()
os.environ["MAESTRO_PERSONAL_DB"] = tmp_db.name
os.environ["MAESTRO_PERSONAL_TOKEN"] = "gold-test-token"
os.environ["MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL"] = "1"
os.environ.pop("MAESTRO_PERSONAL_ENV", None)

import uvicorn
from maestro_personal_shell import api as personal_api
personal_api.init_db()
config = uvicorn.Config(personal_api.app, host="127.0.0.1", port=8785, log_level="error")
server = uvicorn.Server(config)
t = threading.Thread(target=server.run, daemon=True)
t.start()

for i in range(40):
    try:
        urllib.request.urlopen("http://127.0.0.1:8785/api/health", timeout=2)
        print(f"[score] API ready after {i}s")
        break
    except Exception:
        time.sleep(0.5)

from maestro_personal_shell.llm_bridge import reset_llm_router, get_llm_provider_name, probe_provider
import asyncio
reset_llm_router()
probe = asyncio.run(probe_provider(force=True))
print(f"[score] LLM verified: {probe.get('verified')}, latency: {probe.get('latency_ms')}ms")
assert probe.get("verified") is True

from evaluation.scoreboard.memory_v1 import get_corpus, get_questions
from evaluation.scoreboard.bm25_baseline import score_answer, bm25_retrieve

BASE = "http://127.0.0.1:8785"
TOKEN = "gold-test-token"

def http_post(path, body, timeout=90):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE}{path}", data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.status, json.loads(resp.read() or "null")
    except urllib.error.HTTPError as e:
        body = e.read()
        try: return e.code, json.loads(body)
        except Exception: return e.code, {"error": body.decode("utf-8", "replace")[:200]}
    except Exception as e:
        return -1, {"error": str(e)}

# Seed
print(f"\n[score] Seeding {len(get_corpus())} signals...")
seeded = 0
for sig in get_corpus():
    s, _ = http_post("/api/signals", sig, timeout=30)
    if s == 200: seeded += 1
print(f"[score] Seeded {seeded}/{len(get_corpus())} signals")

# 5 questions covering the audit failure modes
ALL_Q = get_questions()
INDICES = [0, 4, 6, 9, 35]  # direct_lookup, broken, relational, contradiction, abstention
questions = [ALL_Q[i] for i in INDICES]
print(f"\n[score] Firing {len(questions)} questions in parallel...")

def fire_question(q):
    t0 = time.time()
    s, body = http_post("/api/ask", {"query": q["q"]}, timeout=90)
    elapsed = time.time() - t0
    if s != 200:
        return {"q": q["q"], "type": q["expected_type"], "maestro_score": 0.0, "bm25_score": 0.0, "error": f"HTTP {s}", "elapsed": elapsed}
    answer = body.get("answer", "")
    evidence = body.get("evidence_refs", [])
    m_score = score_answer(q, answer, evidence if isinstance(evidence, list) else [])
    retrieved = bm25_retrieve(q["q"], get_corpus(), top_k=5)
    bm25_answer = " ".join(r.get("text", "") for r in retrieved)
    b_score = score_answer(q, bm25_answer, retrieved)
    llm_active = body.get("llm_active", False)
    confidence = body.get("confidence", 0)
    return {
        "q": q["q"], "type": q["expected_type"],
        "maestro_score": m_score, "bm25_score": b_score,
        "answer_preview": answer[:120],
        "llm_active": llm_active, "confidence": confidence,
        "elapsed": elapsed,
    }

# Fire in parallel (3 workers — Ollama can handle 3 concurrent on P100)
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
            results[idx] = {"q": questions[idx]["q"], "type": questions[idx]["expected_type"], "maestro_score": 0.0, "bm25_score": 0.0, "error": str(e)}

# Compute composites
valid = [r for r in results if r is not None]
m_avg = sum(r["maestro_score"] for r in valid) / len(valid)
b_avg = sum(r["bm25_score"] for r in valid) / len(valid)
lift = (m_avg - b_avg) * 100

print("\n" + "=" * 70)
print("  MEMORY GOLD SET — 5-QUESTION PARALLEL SUBSET")
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

out_path = "/home/z/my-project/download/maestro_gold_results.json"
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
