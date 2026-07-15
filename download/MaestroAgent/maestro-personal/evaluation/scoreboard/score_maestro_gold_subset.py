"""Quick 10-question subset of the gold corpus — gets the lift signal
in ~5 minutes instead of ~25. Uses port 8778 to avoid conflicts."""
import os, sys, json, time, tempfile, threading, urllib.request, urllib.error
from pathlib import Path

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
config = uvicorn.Config(personal_api.app, host="127.0.0.1", port=8778, log_level="error")
server = uvicorn.Server(config)
t = threading.Thread(target=server.run, daemon=True)
t.start()

for i in range(40):
    try:
        urllib.request.urlopen("http://127.0.0.1:8778/api/health", timeout=2)
        print(f"[score] API ready after {i}s")
        break
    except Exception:
        time.sleep(0.5)

from maestro_personal_shell.llm_bridge import get_llm_router, reset_llm_router, get_llm_provider_name, probe_provider
import asyncio
reset_llm_router()
provider = get_llm_provider_name()
probe = asyncio.run(probe_provider(force=True))
print(f"[score] LLM provider: {provider}, verified: {probe.get('verified')}")
assert probe.get("verified") is True

from evaluation.scoreboard.memory_v1 import get_corpus, get_questions
from evaluation.scoreboard.bm25_baseline import score_answer, bm25_retrieve

BASE = "http://127.0.0.1:8778"
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

# Pick 10 representative questions
ALL_Q = get_questions()
REPRESENTATIVE_INDICES = [
    0,   # direct_lookup — "What did I promise Alex?"
    3,   # overdue — "Which promises are now overdue?"
    4,   # broken — "What did I fail to deliver?"
    6,   # relational — "Who am I repeatedly disappointing?"
    9,   # contradiction — "What is Orion Tech's pricing?"
    12,  # recurring — "Which issue keeps recurring across meetings?"
    25,  # multilingual — "What did Carlos say?"
    28,  # critical — "Are there any legal issues?"
    35,  # abstention — "What did I commit to in 2024?"
    43,  # temporal — "What's the oldest unfulfilled commitment?"
]
questions = [ALL_Q[i] for i in REPRESENTATIVE_INDICES]
print(f"\n[score] Firing {len(questions)} representative questions...")

results = []
for i, q in enumerate(questions):
    t0 = time.time()
    s, body = http_post("/api/ask", {"query": q["q"]}, timeout=90)
    elapsed = time.time() - t0
    if s != 200:
        print(f"  [{i+1:>2}] FAIL {q['expected_type']:15s} {q['q'][:50]} -> {s}")
        results.append({"q": q["q"], "type": q["expected_type"], "maestro_score": 0.0, "bm25_score": 0.0, "error": f"HTTP {s}"})
        continue
    answer = body.get("answer", "")
    evidence = body.get("evidence_refs", [])
    m_score = score_answer(q, answer, evidence if isinstance(evidence, list) else [])
    retrieved = bm25_retrieve(q["q"], get_corpus(), top_k=5)
    bm25_answer = " ".join(r.get("text", "") for r in retrieved)
    b_score = score_answer(q, bm25_answer, retrieved)
    llm_active = body.get("llm_active", False)
    confidence = body.get("confidence", 0)
    marker = "OK" if m_score >= 0.5 else "X "
    win = "+" if m_score > b_score else ("=" if m_score == b_score else "-")
    print(f"  [{i+1:>2}] {marker} {q['expected_type']:15s} m={m_score:.2f} b={b_score:.2f} {win} {q['q'][:50]} ({elapsed:.1f}s)")
    results.append({
        "q": q["q"], "type": q["expected_type"],
        "maestro_score": m_score, "bm25_score": b_score,
        "answer_preview": answer[:150],
        "llm_active": llm_active, "confidence": confidence,
        "elapsed": elapsed,
    })

# Compute composites
m_avg = sum(r["maestro_score"] for r in results) / len(results)
b_avg = sum(r["bm25_score"] for r in results) / len(results)
lift = (m_avg - b_avg) * 100

print("\n" + "=" * 70)
print("  MEMORY GOLD SET — 10-QUESTION REPRESENTATIVE SUBSET")
print("=" * 70)
print(f"\n  BM25 baseline:  {b_avg:.3f}")
print(f"  Maestro (LLM):  {m_avg:.3f}")
print(f"  Lift:           {lift:+.1f} points (target: >= +15)")

print(f"\n  Per-question:")
print(f"    {'type':<20s} {'maestro':>8s} {'bm25':>8s} {'win':>4s}")
for r in results:
    win = "+" if r["maestro_score"] > r["bm25_score"] else ("=" if r["maestro_score"] == r["bm25_score"] else "-")
    print(f"    {r['type']:<20s} {r['maestro_score']:>8.2f} {r['bm25_score']:>8.2f} {win:>4s}")

llm_active_count = sum(1 for r in results if r.get("llm_active"))
avg_conf = sum(r.get("confidence", 0) for r in results) / len(results)
avg_lat = sum(r.get("elapsed", 0) for r in results) / len(results)
print(f"\n  LLM active: {llm_active_count}/{len(results)}")
print(f"  Avg confidence: {avg_conf:.3f}")
print(f"  Avg latency:    {avg_lat:.1f}s")

if lift >= 15:
    print("\n  PASS — Maestro beats BM25 by >= 15 points")
elif lift > 0:
    print(f"\n  PARTIAL — Maestro beats BM25 by {lift:+.1f} points (target: >= +15)")
else:
    print(f"\n  FAIL — Maestro does not beat BM25 ({lift:+.1f} points)")

out_path = "/home/z/my-project/download/maestro_gold_subset_results.json"
with open(out_path, "w") as f:
    json.dump({
        "subset_size": len(results),
        "bm25_baseline": b_avg,
        "maestro_composite": m_avg,
        "lift_points": lift,
        "llm_active_count": llm_active_count,
        "results": results,
    }, f, indent=2)
print(f"\n  Full results: {out_path}")

server.should_exit = True
time.sleep(1)
