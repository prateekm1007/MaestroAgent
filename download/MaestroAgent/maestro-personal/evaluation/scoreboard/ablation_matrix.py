"""
Phase 5: Ablation matrix — prove each subsystem earns its keep.

Roadmap §5.2: Run under equal budgets:
  1. Single strong prompt (LLM only, no retrieval)
  2. Single LLM + retrieval (LLM + FTS, no ranker/aggregation)
  3. Full Maestro (ranker + intent + entity aggregation + ledger + LLM)

For each, run the 10-question representative subset and compare:
  - Factual precision
  - Provenance availability
  - Confidence calibration
  - Latency

Decision rules (§5.3):
  - If Full Maestro doesn't beat LLM+retrieval by >=8 points → simplify
  - If graph doesn't improve longitudinal questions by >=10 points → freeze
  - If agents don't improve quality by >=5% → disable

This ablation uses the HTTP subprocess approach with OpenRouter.
"""
import os, sys, json, time, tempfile, subprocess, urllib.request, statistics
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

REPO = Path(__file__).resolve().parents[3]
SHELL_SRC = REPO / "maestro-personal" / "src"
sys.path.insert(0, str(SHELL_SRC))
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "maestro-personal"))

PORT = 8890
TOKEN = "ablation"

# ── Setup ─────────────────────────────────────────────────────────
tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="ablation_")
tmp_db.close()
DB_PATH = tmp_db.name
os.environ["MAESTRO_PERSONAL_DB"] = DB_PATH
os.environ["MAESTRO_PERSONAL_TOKEN"] = TOKEN
os.environ["MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL"] = "1"

from evaluation.scoreboard.memory_v1 import get_corpus, get_questions
from evaluation.scoreboard.bm25_baseline import score_answer, bm25_retrieve
from maestro_personal_shell.db_util import get_db_conn
from maestro_personal_shell import api as pa
pa.init_db()

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
print(f"Seeded {len(corpus)} signals", flush=True)

# ── Start server ──────────────────────────────────────────────────
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

H = {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"}
BASE = f"http://127.0.0.1:{PORT}"

# ── 10 representative questions ────────────────────────────────────
INDICES = [0, 4, 6, 9, 12, 25, 28, 35, 40, 44]
ALL_Q = get_questions()
questions = [ALL_Q[i] for i in INDICES]

# ── Ablation A: BM25 baseline (no LLM, no ranker) ────────────────
print("\n[A] BM25 baseline (no LLM)...", flush=True)
results_A = []
for q in questions:
    retrieved = bm25_retrieve(q["q"], corpus, top_k=5)
    answer = " ".join(r.get("text", "") for r in retrieved)
    score = score_answer(q, answer, retrieved)
    results_A.append({"type": q["expected_type"], "score": score, "answer": answer[:100]})
    print(f"  {q['expected_type']:15s} score={score:.2f}", flush=True)
avg_A = sum(r["score"] for r in results_A) / len(results_A)
print(f"  Average: {avg_A:.3f}", flush=True)

# ── Ablation B: Full Maestro (HTTP API with LLM) ─────────────────
print("\n[B] Full Maestro (HTTP API + LLM)...", flush=True)
results_B = []
for idx, q in enumerate(questions):
    t0 = time.time()
    data = json.dumps({"query": q["q"]}).encode()
    req = urllib.request.Request(f"{BASE}/api/ask", data=data, headers=H)
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        body = json.loads(resp.read())
        elapsed = time.time() - t0
        answer = body.get("answer", "")
        evidence = body.get("evidence_refs", [])
        ev_list = [{"text": e, "entity": ""} if isinstance(e, str) else e for e in (evidence if isinstance(evidence, list) else [])]
        score = score_answer(q, answer, ev_list)
        llm_active = body.get("llm_active", False)
        confidence = body.get("confidence", 0)
        results_B.append({"type": q["expected_type"], "score": score, "answer": answer[:100], "llm": llm_active, "conf": confidence, "elapsed": round(elapsed, 1)})
        print(f"  [{idx+1}] {q['expected_type']:15s} score={score:.2f} llm={llm_active} conf={confidence:.2f} ({elapsed:.1f}s)", flush=True)
    except Exception as e:
        results_B.append({"type": q["expected_type"], "score": 0, "error": str(e)[:60]})
        print(f"  [{idx+1}] ERROR: {str(e)[:50]}", flush=True)
avg_B = sum(r["score"] for r in results_B) / len(results_B)
llm_count_B = sum(1 for r in results_B if r.get("llm"))
print(f"  Average: {avg_B:.3f} (LLM active: {llm_count_B}/{len(results_B)})", flush=True)

# ── Ablation C: Rule-based Maestro (HTTP API, no LLM) ────────────
# The Ask endpoint falls back to rules when LLM is unavailable.
# We can't easily disable the LLM per-request, so we use the direct
# AskSurface approach (which doesn't call the LLM) as the rule-only baseline.
print("\n[C] Rule-based Maestro (no LLM)...", flush=True)
sys.path.insert(0, str(SHELL_SRC))
from maestro_personal_shell.shell import PersonalShell
from maestro_personal_shell.personal_oem_state import PersonalOemState, PersonalSignal
from maestro_personal_shell.surfaces.ask import AskSurface
from maestro_personal_shell.api import load_signals_from_db

db_signals = load_signals_from_db(user_email="bootstrap")
personal_signals = []
for row in db_signals:
    try: ts = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
    except: ts = datetime.now(timezone.utc)
    sig = PersonalSignal(entity=row["entity"], text=row["text"], signal_type=row["signal_type"],
                         signal_id=row["signal_id"], timestamp=ts, metadata={}, source_acl="public")
    personal_signals.append(sig)
state = PersonalOemState(signals=personal_signals)
shell = PersonalShell(oem_state=state)

results_C = []
for q in questions:
    surface = AskSurface(shell=shell)
    try:
        result = surface.ask(q["q"])
        answer = getattr(result, "answer", "") or str(result)
        evidence = getattr(result, "evidence_refs", []) or []
        ev_list = [{"text": e, "entity": ""} if isinstance(e, str) else e for e in (evidence if isinstance(evidence, list) else [])]
        score = score_answer(q, answer, ev_list)
    except Exception as e:
        answer = f"ERROR: {e}"
        score = 0.0
    results_C.append({"type": q["expected_type"], "score": score, "answer": answer[:100]})
    print(f"  {q['expected_type']:15s} score={score:.2f}", flush=True)
avg_C = sum(r["score"] for r in results_C) / len(results_C)
print(f"  Average: {avg_C:.3f}", flush=True)

# ── Summary ───────────────────────────────────────────────────────
lift_B_vs_A = (avg_B - avg_A) * 100
lift_B_vs_C = (avg_B - avg_C) * 100
lift_C_vs_A = (avg_C - avg_A) * 100

print(f"\n{'='*70}", flush=True)
print(f"  ABLATION MATRIX — 10 QUESTIONS", flush=True)
print(f"{'='*70}", flush=True)
print(f"", flush=True)
print(f"  A. BM25 baseline:         {avg_A:.3f}", flush=True)
print(f"  B. Full Maestro (LLM):    {avg_B:.3f}  (LLM: {llm_count_B}/{len(results_B)})", flush=True)
print(f"  C. Rule-based Maestro:    {avg_C:.3f}", flush=True)
print(f"", flush=True)
print(f"  B vs A (Maestro vs BM25):     {lift_B_vs_A:+.1f} pts (bar: >=+15)", flush=True)
print(f"  B vs C (LLM vs rules):        {lift_B_vs_C:+.1f} pts (bar: >=+8)", flush=True)
print(f"  C vs A (rules vs BM25):       {lift_C_vs_A:+.1f} pts", flush=True)
print(f"", flush=True)

if lift_B_vs_A >= 15:
    print(f"  Maestro vs BM25: PASS", flush=True)
elif lift_B_vs_A > 0:
    print(f"  Maestro vs BM25: PARTIAL ({lift_B_vs_A:+.1f})", flush=True)
else:
    print(f"  Maestro vs BM25: FAIL", flush=True)

if lift_B_vs_C >= 8:
    print(f"  LLM vs rules: PASS", flush=True)
elif lift_B_vs_C > 0:
    print(f"  LLM vs rules: PARTIAL ({lift_B_vs_C:+.1f})", flush=True)
else:
    print(f"  LLM vs rules: FAIL (LLM doesn't improve over rules)", flush=True)

# Per-type comparison
print(f"\n  Per-type:", flush=True)
print(f"    {'type':<20s} {'BM25':>6s} {'Rules':>6s} {'Full':>6s} {'B-A':>6s} {'B-C':>6s}", flush=True)
by_type = {}
for i, q in enumerate(questions):
    t = q["expected_type"]
    by_type.setdefault(t, []).append({
        "A": results_A[i]["score"],
        "B": results_B[i]["score"],
        "C": results_C[i]["score"],
    })
for t_name in sorted(by_type.keys()):
    rows = by_type[t_name]
    a_avg = sum(r["A"] for r in rows) / len(rows)
    b_avg = sum(r["B"] for r in rows) / len(rows)
    c_avg = sum(r["C"] for r in rows) / len(rows)
    print(f"    {t_name:<20s} {a_avg:>6.2f} {c_avg:>6.2f} {b_avg:>6.2f} {(b_avg-a_avg)*100:>+6.1f} {(b_avg-c_avg)*100:>+6.1f}", flush=True)

# Save
out = {
    "A_bm25": round(avg_A, 4),
    "B_full_maestro": round(avg_B, 4),
    "C_rule_based": round(avg_C, 4),
    "lift_B_vs_A": round(lift_B_vs_A, 1),
    "lift_B_vs_C": round(lift_B_vs_C, 1),
    "lift_C_vs_A": round(lift_C_vs_A, 1),
    "llm_active": llm_count_B,
    "total_questions": len(questions),
    "results_A": results_A,
    "results_B": results_B,
    "results_C": results_C,
}
out_path = "/home/z/my-project/download/ablation_matrix.json"
with open(out_path, "w") as f:
    json.dump(out, f, indent=2)
print(f"\nResults saved to: {out_path}", flush=True)

server_proc.terminate()
server_proc.wait(timeout=5)
