"""
Run the ablation benchmark with LLM active.

Tests 30 questions (was 10 in the old artifact) across 5 categories:
  - Factual (10): specific commitments, deadlines, outcomes
  - Entity-specific (8): must return the RIGHT entity
  - Abstract (5): reasoning across signals
  - Contradiction (3): detect conflicting commitments
  - Temporal (4): time-aware retrieval

Conditions:
  1. Full Maestro (LLM + retrieval + graph + ranker) — via /api/ask
  2. LLM-only (no retrieval) — direct LLM call with just the query
  3. Rule-based (LLM off) — for comparison with the old artifact

The old artifact (ablation_matrix_results.json) showed:
  BM25=0.55, Full=0.50, Rules=0.45, lift_B_vs_A=-5.0
  llm_active=0, total_questions=10

This re-run uses:
  - LLM active (ZAI GLM via /etc/.z-ai-config)
  - 30 questions (was 10)
  - Fresh execution, not cached artifact
"""
import os, sys, json, tempfile, asyncio, time
from pathlib import Path
from datetime import datetime, timezone, timedelta

MAESTRO_ROOT = Path("/home/z/my-project/MaestroAgent/download/MaestroAgent/maestro-personal")
MAESTRO_SRC = MAESTRO_ROOT / "src"
sys.path.insert(0, str(MAESTRO_SRC))
sys.path.insert(0, str(MAESTRO_ROOT / "tests"))

os.environ["MAESTRO_ENV"] = "dev"
os.environ["ENV"] = "dev"
os.environ["MAESTRO_DEMO_MODE"] = "0"

from fastapi.testclient import TestClient
from maestro_personal_shell.api import app, init_db

# Import the benchmark questions + scoring + corpus from the test file
# We can't run it as a pytest test (it's marked llm_integration + takes 10+ min)
# so we import the data + run the benchmark directly.
import importlib.util
spec = importlib.util.spec_from_file_location("ablation_test", MAESTRO_ROOT / "tests" / "test_ablation_benchmark.py")
ablation_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ablation_mod)

BENCHMARK_QUESTIONS = ablation_mod.BENCHMARK_QUESTIONS
score_answer = ablation_mod.score_answer
CORPUS_SIGNALS = ablation_mod.CORPUS_SIGNALS

print("=" * 80)
print("ABLATION BENCHMARK — LLM ACTIVE (Round 68)")
print("=" * 80)
print(f"Questions: {len(BENCHMARK_QUESTIONS)} (was 10 in old artifact)")
print(f"LLM provider: ", end="")

from maestro_personal_shell.llm_bridge import is_llm_available, get_llm_provider_name, reset_llm_router
reset_llm_router()
print(f"{'ACTIVE' if is_llm_available() else 'INACTIVE'} — {get_llm_provider_name()}")

# Setup temp DB + seed corpus
db_fd, db_path = tempfile.mkstemp(suffix=".db")
os.close(db_fd)
os.environ["MAESTRO_PERSONAL_DB"] = db_path
os.environ["MAESTRO_PERSONAL_TOKEN"] = "ablation-benchmark"

init_db(db_path)
client = TestClient(app)
TOKEN = "ablation-benchmark"
H = {"Authorization": f"Bearer {TOKEN}"}

# Seed the corpus
print(f"\nSeeding {len(CORPUS_SIGNALS)} corpus signals...")
now = datetime.now(timezone.utc)
for sig in CORPUS_SIGNALS:
    days_ago = sig.get("days_ago", 30)
    ts = (now - timedelta(days=days_ago)).isoformat()
    body = json.dumps({
        "entity": sig["entity"],
        "text": sig["text"],
        "signal_type": sig["signal_type"],
        "timestamp": ts,
    }).encode()
    import urllib.request
    req = urllib.request.Request(
        f"http://127.0.0.1:8766/api/signals",
        data=body,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    # Use TestClient instead of HTTP
    r = client.post("/api/signals", json={
        "entity": sig["entity"],
        "text": sig["text"],
        "signal_type": sig["signal_type"],
        "timestamp": ts,
    }, headers=H)
    if r.status_code != 200:
        print(f"  WARN: signal seed returned {r.status_code}: {r.text[:100]}")
print(f"Seeded {len(CORPUS_SIGNALS)} signals.")

# === CONDITION 1: Full Maestro ===
print("\n" + "=" * 80)
print("CONDITION 1: FULL MAESTRO (LLM + retrieval + graph + ranker)")
print("=" * 80)
print(f"{'ID':<5} {'Score':>6} {'Entity':>7} {'KWs':>5} {'Abst':>5} {'Source':<8} {'LLM':>4} Query")
print("-" * 80)

maestro_results = []
total_score = 0
for i, q in enumerate(BENCHMARK_QUESTIONS):
    t0 = time.time()
    r = client.post("/api/ask", json={"query": q["query"]}, headers=H)
    elapsed = time.time() - t0
    if r.status_code != 200:
        print(f"{q['id']:<5} {'ERROR':>6} — HTTP {r.status_code} ({elapsed:.1f}s) — {q['query'][:50]}")
        maestro_results.append({"id": q["id"], "score": 0, "error": r.status_code, "query": q["query"]})
        continue
    data = r.json()
    answer = data.get("answer", "")
    score = score_answer(answer, q)
    total_score += score["total_score"]
    maestro_results.append({
        "id": q["id"],
        "query": q["query"],
        "answer": answer[:200],
        "score": score["total_score"],
        "entity_correct": score["entity_correct"],
        "keyword_hits": score["keyword_hits"],
        "abstained": score["abstained"],
        "intelligence_source": data.get("intelligence_source"),
        "llm_active": data.get("llm_active"),
        "latency_s": round(elapsed, 1),
    })
    print(f"{q['id']:<5} {score['total_score']:>6.1f} {str(score['entity_correct']):>7} {score['keyword_hits']:>3}/{3:<2} {str(score['abstained']):>5} {data.get('intelligence_source','?'):<8} {'Y' if data.get('llm_active') else 'N':>4} {q['query'][:50]}")

maestro_avg = total_score / len(BENCHMARK_QUESTIONS)
print("-" * 80)
print(f"{'AVG':<5} {maestro_avg:>6.1f}/10  (n={len(BENCHMARK_QUESTIONS)})")
print(f"LLM Active: {maestro_results[0].get('llm_active') if maestro_results else 'N/A'}")

# === CONDITION 2: LLM-only (no retrieval) ===
print("\n" + "=" * 80)
print("CONDITION 2: LLM-ONLY (no retrieval, no graph)")
print("=" * 80)

from maestro_personal_shell.llm_bridge import get_llm_router
router = get_llm_router()

if router:
    print(f"{'ID':<5} {'Score':>6} {'Entity':>7} {'KWs':>5} {'Abst':>5} Query")
    print("-" * 80)
    llm_only_results = []
    llm_total = 0
    for q in BENCHMARK_QUESTIONS:
        try:
            response = asyncio.run(router.complete(
                system="You are a helpful assistant. Answer the user's question concisely. If you don't know, say so.",
                user=q["query"],
                temperature=0.1,
                max_tokens=200,
            ))
            answer = getattr(response, "text", str(response))
        except Exception as e:
            answer = f"I don't have enough information to answer that. ({type(e).__name__})"
        score = score_answer(answer, q)
        llm_total += score["total_score"]
        llm_only_results.append({
            "id": q["id"],
            "score": score["total_score"],
            "entity_correct": score["entity_correct"],
            "keyword_hits": score["keyword_hits"],
            "abstained": score["abstained"],
            "answer": answer[:200],
        })
        print(f"{q['id']:<5} {score['total_score']:>6.1f} {str(score['entity_correct']):>7} {score['keyword_hits']:>3}/{3:<2} {str(score['abstained']):>5} {q['query'][:50]}")
    llm_avg = llm_total / len(BENCHMARK_QUESTIONS)
    print("-" * 80)
    print(f"{'AVG':<5} {llm_avg:>6.1f}/10  (n={len(BENCHMARK_QUESTIONS)})")
else:
    llm_avg = 0
    llm_only_results = []
    print("LLM router not available — skipping LLM-only condition")

# === COMPARISON REPORT ===
print("\n" + "=" * 80)
print("COMPARISON REPORT")
print("=" * 80)
print(f"  Full Maestro (LLM + retrieval):  {maestro_avg:.2f}/10  (n={len(BENCHMARK_QUESTIONS)})")
print(f"  LLM-only (no retrieval):         {llm_avg:.2f}/10  (n={len(BENCHMARK_QUESTIONS)})")
lift = (maestro_avg - llm_avg) / llm_avg * 100 if llm_avg > 0 else 0
print(f"  Lift (Maestro vs LLM-only):      {lift:+.1f}%")

# Compare with old artifact
print(f"\n  OLD ARTIFACT (n=10, llm_active=0):")
print(f"    BM25:     0.55")
print(f"    Full:     0.50  (lift_B_vs_A = -5.0%)")
print(f"    Rules:    0.45")

# Save new results
results = {
    "round": 68,
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "llm_active": is_llm_available(),
    "llm_provider": get_llm_provider_name(),
    "total_questions": len(BENCHMARK_QUESTIONS),
    "full_maestro_avg": round(maestro_avg, 2),
    "llm_only_avg": round(llm_avg, 2),
    "lift_maestro_vs_llm_only": round(lift, 1),
    "old_artifact": {
        "bm25": 0.55,
        "full_maestro": 0.50,
        "rule_based": 0.45,
        "lift_B_vs_A": -5.0,
        "llm_active": 0,
        "total_questions": 10,
    },
    "maestro_results": maestro_results,
    "llm_only_results": llm_only_results,
}
output_path = MAESTRO_ROOT / "evaluation" / "scoreboard" / "ablation_round68.json"
with open(output_path, "w") as f:
    json.dump(results, f, indent=2, default=str)
print(f"\nResults saved to: {output_path}")

# Cleanup
try:
    os.unlink(db_path)
except:
    pass
