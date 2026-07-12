"""
30-meeting copilot benchmark — fires 30 synthetic meeting transcripts
through POST /api/copilot/transcript and measures latency + usefulness.

Phase 4 of Roadmap to 9/10:
  - p95 < 1500ms (rule/local mode)
  - p99 < 2500ms
  - provenance availability
  - commitment detection rate

Runs in RULE MODE (no LLM) so it's not blocked by tunnel congestion.
"""
import os, sys, json, time, tempfile, threading, statistics, urllib.request, urllib.error
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SHELL_SRC = REPO / "maestro-personal" / "src"
sys.path.insert(0, str(SHELL_SRC))
sys.path.insert(0, str(REPO / "backend"))

tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="copilot_")
tmp_db.close()
os.environ["MAESTRO_PERSONAL_DB"] = tmp_db.name
os.environ["MAESTRO_PERSONAL_TOKEN"] = "copilot-bench-token"
os.environ["MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL"] = "1"
os.environ.pop("MAESTRO_PERSONAL_ENV", None)
os.environ.pop("OLLAMA_HOST", None)
os.environ.pop("OLLAMA_MODEL", None)

import uvicorn
from maestro_personal_shell import api as personal_api
personal_api.init_db()
config = uvicorn.Config(personal_api.app, host="127.0.0.1", port=8783, log_level="error")
server = uvicorn.Server(config)
t = threading.Thread(target=server.run, daemon=True)
t.start()

for i in range(40):
    try:
        urllib.request.urlopen("http://127.0.0.1:8783/api/health", timeout=2)
        print(f"[bench] API ready after {i}s")
        break
    except Exception:
        time.sleep(0.5)

BASE = "http://127.0.0.1:8783"
TOKEN = "copilot-bench-token"

def http_post(path, body, timeout=60):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE}{path}", data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.status, json.loads(resp.read() or "null")
    except Exception as e:
        return -1, {"error": str(e)}

# Login
r, body = http_post("/api/auth/login", {"password": TOKEN})
assert r == 200

# Seed some context signals so the copilot has history
SEED_SIGNALS = [
    {"entity": "AcmeCorp", "text": "I will send AcmeCorp the pricing proposal by Friday", "signal_type": "commitment_made"},
    {"entity": "AcmeCorp", "text": "AcmeCorp quoted us $120k for the annual contract", "signal_type": "reported_statement"},
    {"entity": "Globex", "text": "Globex is threatening to cancel their contract", "signal_type": "reported_statement"},
    {"entity": "Orion", "text": "I will deliver the Orion integration by March 15", "signal_type": "commitment_made"},
    {"entity": "Orion", "text": "Orion integration is overdue — hasn't been delivered", "signal_type": "reported_statement"},
    {"entity": "Maria", "text": "Maria asked for the security questionnaire by end of week", "signal_type": "reported_statement"},
    {"entity": "Maria", "text": "Never sent the security questionnaire — overdue", "signal_type": "reported_statement"},
]
for sig in SEED_SIGNALS:
    http_post("/api/signals", sig, timeout=30)

# 30 meeting transcripts — 10 scenarios × 3 chunks each
MEETINGS = [
    # Sales negotiation
    {"scenario": "sales_negotiation", "entity": "AcmeCorp", "chunks": [
        {"speaker": "prospect", "text": "We're looking at your premium tier, but the price seems high compared to competitors."},
        {"speaker": "rep", "text": "I can offer a 10% discount if you commit to an annual contract by Friday."},
        {"speaker": "prospect", "text": "Let me think about it. Can you send the revised pricing by tomorrow?"},
    ]},
    # Technical incident
    {"scenario": "tech_incident", "entity": "EngOncall", "chunks": [
        {"speaker": "engineer", "text": "The auth service is down again. Same root cause as last week."},
        {"speaker": "lead", "text": "We need a permanent fix, not another patch. This is the third outage this month."},
        {"speaker": "engineer", "text": "I'll have a root cause analysis by Friday."},
    ]},
    # Customer escalation
    {"scenario": "customer_escalation", "entity": "Globex", "chunks": [
        {"speaker": "customer", "text": "We've been waiting three weeks for the security questionnaire. This is unacceptable."},
        {"speaker": "rep", "text": "I apologize for the delay. I'll personally ensure it's sent by end of day."},
        {"speaker": "customer", "text": "If we don't have it by tomorrow, we're pulling out of the deal."},
    ]},
    # Hiring discussion
    {"scenario": "hiring", "entity": "Hiring", "chunks": [
        {"speaker": "manager", "text": "The candidate's technical skills are strong, but I'm concerned about culture fit."},
        {"speaker": "director", "text": "Let's make an offer and see. We can always reassess in 90 days."},
        {"speaker": "manager", "text": "I'll draft the offer letter by Wednesday."},
    ]},
    # Project planning
    {"scenario": "project_planning", "entity": "Orion", "chunks": [
        {"speaker": "pm", "text": "The Orion integration is already two weeks behind. What's blocking it?"},
        {"speaker": "eng", "text": "We're waiting on the API documentation from their team."},
        {"speaker": "pm", "text": "I'll escalate to their CTO today. We need this by end of quarter."},
    ]},
    # Financial discussion
    {"scenario": "financial", "entity": "Board", "chunks": [
        {"speaker": "cfo", "text": "Q3 revenue is tracking 15% below forecast. We need to cut expenses."},
        {"speaker": "ceo", "text": "Let's review the top 3 cost centers and make a decision by Friday."},
        {"speaker": "cfo", "text": "I'll have the analysis on your desk by Thursday."},
    ]},
    # Strategy disagreement
    {"scenario": "strategy", "entity": "Leadership", "chunks": [
        {"speaker": "vp_sales", "text": "We should prioritize the enterprise segment. Higher ACV."},
        {"speaker": "vp_product", "text": "I disagree. SMB is where our growth is. Enterprise takes too long."},
        {"speaker": "ceo", "text": "Let's test both for 30 days and decide based on data."},
    ]},
    # Casual chat (should stay silent)
    {"scenario": "casual", "entity": "Team", "chunks": [
        {"speaker": "person_a", "text": "How was everyone's weekend?"},
        {"speaker": "person_b", "text": "Great! Went hiking. The weather was perfect."},
        {"speaker": "person_a", "text": "Nice. Anyway, let's get started on the agenda."},
    ]},
    # High-noise transcript
    {"scenario": "noisy", "entity": "ClientX", "chunks": [
        {"speaker": "speaker_1", "text": "um so like yeah we need to uh deliver the thing by you know whenever"},
        {"speaker": "speaker_2", "text": "right right okay so um the deadline is basically Friday I think"},
        {"speaker": "speaker_1", "text": "yeah Friday works I'll send it over"},
    ]},
    # Commitment-heavy
    {"scenario": "commitments", "entity": "Partner", "chunks": [
        {"speaker": "us", "text": "I will send the contract by Monday and the onboarding docs by Wednesday."},
        {"speaker": "partner", "text": "And I'll have our technical team review by Friday."},
        {"speaker": "us", "text": "Perfect. I'll also schedule the kick-off call for next week."},
    ]},
] * 3  # 10 scenarios × 3 = 30 meetings

print(f"\n[bench] Firing {len(MEETINGS)} meeting transcripts (3 chunks each = {len(MEETINGS)*3} API calls)...")

latencies = []
commitments_detected = 0
whispers_generated = 0
errors = 0

for i, meeting in enumerate(MEETINGS):
    for j, chunk in enumerate(meeting["chunks"]):
        body = {
            "text": chunk["text"],
            "speaker": chunk["speaker"],
            "entity": meeting["entity"],
        }
        t0 = time.time()
        status, resp = http_post("/api/copilot/transcript", body, timeout=60)
        elapsed = time.time() - t0
        if status == 200:
            latencies.append(elapsed * 1000)
            # Count useful outputs
            if isinstance(resp, dict):
                cds = resp.get("commitments_detected", [])
                if cds:
                    commitments_detected += len(cds)
                # Check for any whisper/intervention fields
                for key in ("whisper", "intervention", "insight", "talking_points"):
                    if resp.get(key):
                        whispers_generated += 1
                        break
        else:
            errors += 1

# ── Summary ───────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("  30-MEETING COPILOT BENCHMARK — RULE MODE")
print("=" * 70)

total_calls = len(MEETINGS) * 3
print(f"\n  Total API calls:     {total_calls}")
print(f"  Successful:          {len(latencies)}")
print(f"  Errors:              {errors}")

if latencies:
    p50 = statistics.median(latencies)
    p95 = sorted(latencies)[int(len(latencies)*0.95)] if len(latencies) > 1 else latencies[0]
    p99 = sorted(latencies)[int(len(latencies)*0.99)] if len(latencies) > 1 else latencies[0]
    avg = statistics.mean(latencies)
    print(f"\n  Latency p50:         {p50:.1f}ms")
    print(f"  Latency p95:         {p95:.1f}ms")
    print(f"  Latency p99:         {p99:.1f}ms")
    print(f"  Latency avg:         {avg:.1f}ms")
    print(f"  9/10 bar (p95<1500ms): {'PASS' if p95 < 1500 else 'FAIL'}")
    print(f"  9/10 bar (p99<2500ms): {'PASS' if p99 < 2500 else 'FAIL'}")

print(f"\n  Commitments detected: {commitments_detected}")
print(f"  Whispers/insights:    {whispers_generated}")
print(f"  Useful output rate:   {(whispers_generated / max(len(latencies), 1)) * 100:.1f}%")

out = {
    "total_api_calls": total_calls,
    "successful_calls": len(latencies),
    "errors": errors,
    "latencies_ms": latencies,
    "latency_p50_ms": statistics.median(latencies) if latencies else None,
    "latency_p95_ms": sorted(latencies)[int(len(latencies)*0.95)] if len(latencies) > 1 else (latencies[0] if latencies else None),
    "latency_p99_ms": sorted(latencies)[int(len(latencies)*0.99)] if len(latencies) > 1 else (latencies[0] if latencies else None),
    "latency_avg_ms": statistics.mean(latencies) if latencies else None,
    "commitments_detected": commitments_detected,
    "whispers_generated": whispers_generated,
    "useful_output_rate": (whispers_generated / max(len(latencies), 1)) * 100 if latencies else 0,
}
out_path = "/home/z/my-project/download/benchmark_copilot_30meetings.json"
with open(out_path, "w") as f:
    json.dump(out, f, indent=2)
print(f"\n  Results: {out_path}")

server.should_exit = True
time.sleep(1)
