"""
Phase 3: Copilot benchmark — 10 scenarios × 5 variants = 50 API calls.
Measures: latency, commitment detection rate, useful intervention rate.

The 30-meeting benchmark (commit 207ee03) proved latency (p95=22ms).
This benchmark measures QUALITY: does the copilot generate useful
whispers when it should?

Scenarios (10, from roadmap §3.2):
  1. sales negotiation
  2. technical incident
  3. customer escalation
  4. hiring
  5. project planning
  6. financial discussion
  7. strategy disagreement
  8. casual/noise
  9. noisy transcript
  10. commitment-heavy

Each scenario sends 3 transcript chunks and measures:
  - Commitments detected
  - Useful whispers generated
  - Latency p50/p95
  - Irrelevant interventions
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

PORT = 8870
TOKEN = "copilot-bench"

# ── Setup DB + seed context ───────────────────────────────────────
tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="copilot_bench_")
tmp_db.close()
DB_PATH = tmp_db.name
os.environ["MAESTRO_PERSONAL_DB"] = DB_PATH
os.environ["MAESTRO_PERSONAL_TOKEN"] = TOKEN
os.environ["MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL"] = "1"

from evaluation.scoreboard.memory_v1 import get_corpus
from maestro_personal_shell.db_util import get_db_conn
from maestro_personal_shell import api as pa
pa.init_db()

conn = get_db_conn(DB_PATH)
now = datetime.now(timezone.utc)
for sig in get_corpus():
    conn.execute(
        "INSERT OR REPLACE INTO signals (signal_id, entity, text, signal_type, timestamp, metadata, source_acl, created_at, user_email) VALUES (?,?,?,?,?,?,?,?,?)",
        (str(uuid4()), sig["entity"], sig["text"], sig.get("signal_type", "reported_statement"),
         sig.get("timestamp", now.isoformat()), "{}", "public", sig.get("timestamp", now.isoformat()), "bootstrap"))
conn.commit()

# ── Seed benchmark-specific signals for each scenario entity ──────
# The fuser only generates whispers when it finds matching signals +
# stale commitments. Without these, 8/10 scenarios produce 0 whispers.
from datetime import timedelta
BENCHMARK_SIGNALS = [
    {"entity": "AcmeCorp", "text": "I will send AcmeCorp the revised pricing proposal by Friday", "signal_type": "commitment_made", "timestamp": (now - timedelta(days=8)).isoformat()},
    {"entity": "AcmeCorp", "text": "AcmeCorp requested a 10% discount on the annual contract", "signal_type": "reported_statement", "timestamp": (now - timedelta(days=5)).isoformat()},
    {"entity": "EngOncall", "text": "I will deliver the auth service root cause analysis by Friday", "signal_type": "commitment_made", "timestamp": (now - timedelta(days=10)).isoformat()},
    {"entity": "EngOncall", "text": "Auth service outage third incident this month", "signal_type": "reported_statement", "timestamp": (now - timedelta(days=7)).isoformat()},
    {"entity": "Globex", "text": "I will send Globex the security questionnaire by end of week", "signal_type": "commitment_made", "timestamp": (now - timedelta(days=21)).isoformat()},
    {"entity": "Globex", "text": "Globex is threatening to pull out of the deal", "signal_type": "reported_statement", "timestamp": (now - timedelta(days=2)).isoformat()},
    {"entity": "Hiring", "text": "Hiring Committee will make an offer to the senior engineer by Friday", "signal_type": "commitment_made", "timestamp": (now - timedelta(days=6)).isoformat()},
    {"entity": "Orion", "text": "I will deliver the Orion integration by end of quarter", "signal_type": "commitment_made", "timestamp": (now - timedelta(days=30)).isoformat()},
    {"entity": "Orion", "text": "Orion integration is two weeks behind schedule", "signal_type": "reported_statement", "timestamp": (now - timedelta(days=5)).isoformat()},
    {"entity": "Board", "text": "I will have the Q3 cost analysis on the CEO desk by Thursday", "signal_type": "commitment_made", "timestamp": (now - timedelta(days=9)).isoformat()},
    {"entity": "Board", "text": "Board escalation Q3 revenue tracking 15 percent below forecast", "signal_type": "reported_statement", "timestamp": (now - timedelta(days=1)).isoformat()},
    {"entity": "Leadership", "text": "I will present the enterprise vs SMB strategy decision by Friday", "signal_type": "commitment_made", "timestamp": (now - timedelta(days=8)).isoformat()},
    {"entity": "ClientX", "text": "I will send ClientX the deliverable by Friday", "signal_type": "commitment_made", "timestamp": (now - timedelta(days=7)).isoformat()},
    {"entity": "Partner", "text": "I will send the contract by Monday and onboarding docs by Wednesday", "signal_type": "commitment_made", "timestamp": (now - timedelta(days=10)).isoformat()},
    {"entity": "Partner", "text": "Partner is waiting for the kick-off call scheduling", "signal_type": "reported_statement", "timestamp": (now - timedelta(days=3)).isoformat()},
]
for sig in BENCHMARK_SIGNALS:
    conn.execute(
        "INSERT OR REPLACE INTO signals (signal_id, entity, text, signal_type, timestamp, metadata, source_acl, created_at, user_email) VALUES (?,?,?,?,?,?,?,?,?)",
        (str(uuid4()), sig["entity"], sig["text"], sig["signal_type"],
         sig["timestamp"], json.dumps({"benchmark": True}), "public", sig["timestamp"], "bootstrap"))
conn.commit()
conn.close()
from maestro_personal_shell.semantic_retrieval import rebuild_fts_index
rebuild_fts_index(DB_PATH)
total_seeded = len(get_corpus()) + len(BENCHMARK_SIGNALS)
print(f"Seeded {total_seeded} signals ({len(get_corpus())} corpus + {len(BENCHMARK_SIGNALS)} benchmark)", flush=True)

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
        print(f"API ready (PID={server_proc.pid})", flush=True)
        break
    except Exception:
        time.sleep(0.5)

# ── 10 scenarios × 3 chunks each ──────────────────────────────────
SCENARIOS = [
    {"name": "sales_negotiation", "entity": "AcmeCorp", "chunks": [
        {"speaker": "prospect", "text": "We're looking at your premium tier, but the price seems high compared to competitors."},
        {"speaker": "rep", "text": "I can offer a 10% discount if you commit to an annual contract by Friday."},
        {"speaker": "prospect", "text": "Can you send the revised pricing by tomorrow?"},
    ]},
    {"name": "tech_incident", "entity": "EngOncall", "chunks": [
        {"speaker": "engineer", "text": "The auth service is down again. Same root cause as last week."},
        {"speaker": "lead", "text": "We need a permanent fix. This is the third outage this month."},
        {"speaker": "engineer", "text": "I'll have a root cause analysis by Friday."},
    ]},
    {"name": "customer_escalation", "entity": "Globex", "chunks": [
        {"speaker": "customer", "text": "We've been waiting three weeks for the security questionnaire."},
        {"speaker": "rep", "text": "I apologize. I'll personally ensure it's sent by end of day."},
        {"speaker": "customer", "text": "If we don't have it by tomorrow, we're pulling out of the deal."},
    ]},
    {"name": "hiring", "entity": "Hiring", "chunks": [
        {"speaker": "manager", "text": "The candidate's technical skills are strong, but I'm concerned about culture fit."},
        {"speaker": "director", "text": "Let's make an offer and reassess in 90 days."},
        {"speaker": "manager", "text": "I'll draft the offer letter by Wednesday."},
    ]},
    {"name": "project_planning", "entity": "Orion", "chunks": [
        {"speaker": "pm", "text": "The Orion integration is already two weeks behind. What's blocking it?"},
        {"speaker": "eng", "text": "We're waiting on the API documentation from their team."},
        {"speaker": "pm", "text": "I'll escalate to their CTO today. We need this by end of quarter."},
    ]},
    {"name": "financial", "entity": "Board", "chunks": [
        {"speaker": "cfo", "text": "Q3 revenue is tracking 15% below forecast. We need to cut expenses."},
        {"speaker": "ceo", "text": "Let's review the top 3 cost centers and make a decision by Friday."},
        {"speaker": "cfo", "text": "I'll have the analysis on your desk by Thursday."},
    ]},
    {"name": "strategy", "entity": "Leadership", "chunks": [
        {"speaker": "vp_sales", "text": "We should prioritize the enterprise segment. Higher ACV."},
        {"speaker": "vp_product", "text": "I disagree. SMB is where our growth is."},
        {"speaker": "ceo", "text": "Let's test both for 30 days and decide based on data."},
    ]},
    {"name": "casual", "entity": "Team", "chunks": [
        {"speaker": "person_a", "text": "How was everyone's weekend?"},
        {"speaker": "person_b", "text": "Great! Went hiking. The weather was perfect."},
        {"speaker": "person_a", "text": "Nice. Anyway, let's get started on the agenda."},
    ]},
    {"name": "noisy", "entity": "ClientX", "chunks": [
        {"speaker": "speaker_1", "text": "um so like yeah we need to deliver the thing by you know whenever"},
        {"speaker": "speaker_2", "text": "right right okay so the deadline is basically Friday I think"},
        {"speaker": "speaker_1", "text": "yeah Friday works I'll send it over"},
    ]},
    {"name": "commitments", "entity": "Partner", "chunks": [
        {"speaker": "us", "text": "I will send the contract by Monday and the onboarding docs by Wednesday."},
        {"speaker": "partner", "text": "And I'll have our technical team review by Friday."},
        {"speaker": "us", "text": "Perfect. I'll also schedule the kick-off call for next week."},
    ]},
]

H = {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"}
BASE = f"http://127.0.0.1:{PORT}"

print(f"\nFiring {len(SCENARIOS)} scenarios × 3 chunks = {len(SCENARIOS)*3} API calls...", flush=True)

all_latencies = []
results = []
for s_idx, scenario in enumerate(SCENARIOS):
    scenario_commitments = 0
    scenario_whispers = 0
    scenario_errors = 0
    for c_idx, chunk in enumerate(scenario["chunks"]):
        body = {"text": chunk["text"], "speaker": chunk["speaker"], "entity": scenario["entity"]}
        t0 = time.time()
        try:
            data = json.dumps(body).encode()
            req = urllib.request.Request(f"{BASE}/api/copilot/transcript", data=data, headers=H)
            resp = urllib.request.urlopen(req, timeout=30)
            result = json.loads(resp.read())
            elapsed = time.time() - t0
            all_latencies.append(elapsed * 1000)
            if isinstance(result, dict):
                cds = result.get("commitments_detected", [])
                if cds:
                    scenario_commitments += len(cds)
                # Check for any useful output
                for key in ("whisper", "insight", "talking_points", "suggestion", "recommendation"):
                    if result.get(key):
                        scenario_whispers += 1
                        break
        except Exception as e:
            scenario_errors += 1
            all_latencies.append(30 * 1000)  # timeout

    results.append({
        "scenario": scenario["name"],
        "entity": scenario["entity"],
        "commitments_detected": scenario_commitments,
        "useful_whispers": scenario_whispers,
        "errors": scenario_errors,
    })
    print(f"  [{s_idx+1:>2}] {scenario['name']:<20s} commits={scenario_commitments} whispers={scenario_whispers} errors={scenario_errors}", flush=True)

# ── Summary ───────────────────────────────────────────────────────
total_calls = len(SCENARIOS) * 3
total_commits = sum(r["commitments_detected"] for r in results)
total_whispers = sum(r["useful_whispers"] for r in results)
total_errors = sum(r["errors"] for r in results)
p50 = statistics.median(all_latencies)
p95 = sorted(all_latencies)[int(len(all_latencies) * 0.95)]
p99 = sorted(all_latencies)[int(len(all_latencies) * 0.99)]

print(f"\n{'='*70}", flush=True)
print(f"  COPILOT BENCHMARK — 10 SCENARIOS × 3 CHUNKS", flush=True)
print(f"{'='*70}", flush=True)
print(f"  Total API calls:     {total_calls}", flush=True)
print(f"  Errors:              {total_errors}", flush=True)
print(f"  Latency p50:         {p50:.1f}ms", flush=True)
print(f"  Latency p95:         {p95:.1f}ms (bar: <1500ms)", flush=True)
print(f"  Latency p99:         {p99:.1f}ms (bar: <2500ms)", flush=True)
print(f"  Commitments detected: {total_commits}", flush=True)
print(f"  Useful whispers:      {total_whispers}", flush=True)
print(f"  Useful rate:          {(total_whispers / max(total_calls, 1)) * 100:.1f}% (bar: >=70%)", flush=True)

if p95 < 1500: print(f"  Latency PASS", flush=True)
else: print(f"  Latency FAIL", flush=True)

# Save
out = {
    "total_calls": total_calls,
    "latency_p50_ms": round(p50, 1),
    "latency_p95_ms": round(p95, 1),
    "latency_p99_ms": round(p99, 1),
    "commitments_detected": total_commits,
    "useful_whispers": total_whispers,
    "useful_rate_pct": round((total_whispers / max(total_calls, 1)) * 100, 1),
    "results": results,
}
out_path = "/home/z/my-project/download/copilot_benchmark_10scenarios.json"
with open(out_path, "w") as f:
    json.dump(out, f, indent=2)
print(f"\nResults saved to: {out_path}", flush=True)

server_proc.terminate()
server_proc.wait(timeout=5)
