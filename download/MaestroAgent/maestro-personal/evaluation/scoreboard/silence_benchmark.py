"""
Phase 4: Trusted Silence benchmark — 100 labeled moments.
Measures: critical recall, false silence rate, low-value suppression.

Roadmap §4.2: 100 candidate moments (20 critical, 30 moderate, 50 irrelevant).
Runs through the PRODUCTION whisper endpoint (GET /api/whisper), not the unit
classifier. This is the roadmap's explicit requirement.
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

PORT = 8880
TOKEN = "silence-bench"

# ── 100 labeled moments ───────────────────────────────────────────
# 20 critical, 30 moderate, 50 irrelevant
MOMENTS = [
    # ── 20 CRITICAL (should whisper) ──
    {"label": "critical", "entity": "AcmeCorp", "text": "Customer threatening to cancel their contract — pulling out", "signal_type": "reported_statement"},
    {"label": "critical", "entity": "Legal", "text": "EU regulatory fine of 5M euros imposed for GDPR violation", "signal_type": "reported_statement"},
    {"label": "critical", "entity": "Board", "text": "Board escalation: investor wants to see Q3 numbers before Friday", "signal_type": "reported_statement"},
    {"label": "critical", "entity": "EngOncall", "text": "Production down — sev1 incident on auth service", "signal_type": "reported_statement"},
    {"label": "critical", "entity": "Globex", "text": "Globex is threatening to cancel their contract — pulling out", "signal_type": "reported_statement"},
    {"label": "critical", "entity": "Security", "text": "Data breach detected — unauthorized access to customer database", "signal_type": "reported_statement"},
    {"label": "critical", "entity": "Legal", "text": "Lawsuit filed against the company — legal action pending", "signal_type": "reported_statement"},
    {"label": "critical", "entity": "EngOncall", "text": "Security incident: compromised credentials on production", "signal_type": "reported_statement"},
    {"label": "critical", "entity": "Finance", "text": "SEC investigation launched — regulatory complaint filed", "signal_type": "reported_statement"},
    {"label": "critical", "entity": "Board", "text": "Emergency board meeting called — investor wants CEO change", "signal_type": "reported_statement"},
    {"label": "critical", "entity": "AcmeCorp", "text": "Compliance violation detected — GDPR complaint filed", "signal_type": "reported_statement"},
    {"label": "critical", "entity": "EngOncall", "text": "Service down — complete outage affecting all customers", "signal_type": "reported_statement"},
    {"label": "critical", "entity": "Legal", "text": "Subpoena received — must respond within 30 days", "signal_type": "reported_statement"},
    {"label": "critical", "entity": "Finance", "text": "Penalty of $2M imposed by regulatory body", "signal_type": "reported_statement"},
    {"label": "critical", "entity": "Security", "text": "Ransomware attack — production systems encrypted", "signal_type": "reported_statement"},
    {"label": "critical", "entity": "Board", "text": "Board members are upset about the missed Q3 targets", "signal_type": "reported_statement"},
    {"label": "critical", "entity": "Globex", "text": "Globex moving to competitor — lost the deal", "signal_type": "reported_statement"},
    {"label": "critical", "entity": "EngOncall", "text": "SLA breach — latency spike affecting enterprise customers", "signal_type": "reported_statement"},
    {"label": "critical", "entity": "Legal", "text": "Breach of contract claim from AcmeCorp — attorneys involved", "signal_type": "reported_statement"},
    {"label": "critical", "entity": "Finance", "text": "Sanction imposed by regulatory authority", "signal_type": "reported_statement"},
    # ── 30 MODERATE (should whisper if material) ──
    {"label": "moderate", "entity": "Alex", "text": "I will send Alex the pricing deck by Friday", "signal_type": "commitment_made"},
    {"label": "moderate", "entity": "Riley", "text": "Never sent the security questionnaire — overdue", "signal_type": "reported_statement"},
    {"label": "moderate", "entity": "Priya", "text": "Compliance report is overdue — hasn't been sent", "signal_type": "reported_statement"},
    {"label": "moderate", "entity": "Avery", "text": "I will send Avery the quarterly report", "signal_type": "commitment_made"},
    {"label": "moderate", "entity": "Maria", "text": "Maria asked for the pricing proposal by Friday", "signal_type": "reported_statement"},
    {"label": "moderate", "entity": "Sam", "text": "I will deliver the API integration by March 15", "signal_type": "commitment_made"},
    {"label": "moderate", "entity": "Jamie", "text": "SSO work is complete — pending legal review", "signal_type": "reported_statement"},
    {"label": "moderate", "entity": "Morgan", "text": "Nova results presentation was incomplete — missing Q2 data", "signal_type": "reported_statement"},
    {"label": "moderate", "entity": "Orion", "text": "Orion revised the quote down to $95k after negotiation", "signal_type": "reported_statement"},
    {"label": "moderate", "entity": "Hiring", "text": "Hiring Committee will make an offer by Friday", "signal_type": "commitment_made"},
    {"label": "moderate", "entity": "Orion", "text": "Orion Tech quoted us $120k for the annual contract", "signal_type": "reported_statement"},
    {"label": "moderate", "entity": "Orion", "text": "Orion sent the final invoice at $150k — pricing dispute", "signal_type": "reported_statement"},
    {"label": "moderate", "entity": "EngOncall", "text": "Auth service outage again — same root cause as last week", "signal_type": "reported_statement"},
    {"label": "moderate", "entity": "EngOncall", "text": "Third auth outage this month — systemic issue", "signal_type": "reported_statement"},
    {"label": "moderate", "entity": "EngOncall", "text": "Auth service outage — same root cause", "signal_type": "reported_statement"},
    {"label": "moderate", "entity": "Partner", "text": "I will send the contract by Monday", "signal_type": "commitment_made"},
    {"label": "moderate", "entity": "Partner", "text": "I will send the onboarding docs by Wednesday", "signal_type": "commitment_made"},
    {"label": "moderate", "entity": "Board", "text": "Q3 revenue tracking 15% below forecast", "signal_type": "reported_statement"},
    {"label": "moderate", "entity": "CFO", "text": "I'll have the cost analysis by Thursday", "signal_type": "commitment_made"},
    {"label": "moderate", "entity": "Hiring", "text": "I'll draft the offer letter by Wednesday", "signal_type": "commitment_made"},
    {"label": "moderate", "entity": "ClientX", "text": "The deadline is basically Friday", "signal_type": "commitment_made"},
    {"label": "moderate", "entity": "PM", "text": "I'll escalate to their CTO today", "signal_type": "commitment_made"},
    {"label": "moderate", "entity": "Alex", "text": "Sent the pricing deck to Alex yesterday", "signal_type": "reported_statement"},
    {"label": "moderate", "entity": "Sam", "text": "Delivered the API integration on time", "signal_type": "reported_statement"},
    {"label": "moderate", "entity": "Maria", "text": "Procurement team needs 3 days to review before board meeting", "signal_type": "reported_statement"},
    {"label": "moderate", "entity": "Carlos", "text": "Carlos dijo que enviara el contrato el lunes", "signal_type": "reported_statement"},
    {"label": "moderate", "entity": "Eng", "text": "We're waiting on API documentation from their team", "signal_type": "reported_statement"},
    {"label": "moderate", "entity": "Director", "text": "Let's reassess in 90 days", "signal_type": "reported_statement"},
    {"label": "moderate", "entity": "VP Sales", "text": "We should prioritize the enterprise segment", "signal_type": "reported_statement"},
    {"label": "moderate", "entity": "VP Product", "text": "SMB is where our growth is", "signal_type": "reported_statement"},
    {"label": "moderate", "entity": "Morgan", "text": "Presented Nova results at the all-hands", "signal_type": "reported_statement"},
    # ── 50 IRRELEVANT (should suppress) ──
    {"label": "irrelevant", "entity": "TechNewsletter", "text": "Weekly tech digest: 10 articles about AI you should read", "signal_type": "newsletter"},
    {"label": "irrelevant", "entity": "TechNewsletter", "text": "Monthly newsletter roundup — industry trends", "signal_type": "newsletter"},
    {"label": "irrelevant", "entity": "IndustryNews", "text": "FYI: competitor raised Series B — for your awareness", "signal_type": "fyi"},
    {"label": "irrelevant", "entity": "Eng Team", "text": "Team standup notes: velocity is fine, sprint on track", "signal_type": "reported_statement"},
    {"label": "irrelevant", "entity": "Eng Team", "text": "Team standup notes: velocity is fine, no blockers", "signal_type": "reported_statement"},
    {"label": "irrelevant", "entity": "Newsletter", "text": "Industry newsletter: 5 trends to watch in 2026", "signal_type": "newsletter"},
    {"label": "irrelevant", "entity": "Blog", "text": "Company blog post: 10 tips for better productivity", "signal_type": "blog"},
    {"label": "irrelevant", "entity": "Social", "text": "LinkedIn post: excited to announce our new office", "signal_type": "social"},
    {"label": "irrelevant", "entity": "Newsletter", "text": "Weekly roundup: best articles from the community", "signal_type": "newsletter"},
    {"label": "irrelevant", "entity": "FYI", "text": "FYI: office will be closed on Monday for holiday", "signal_type": "fyi"},
    {"label": "irrelevant", "entity": "Newsletter", "text": "Tech newsletter: 7 tools every developer should know", "signal_type": "newsletter"},
    {"label": "irrelevant", "entity": "Blog", "text": "Blog: how we improved our CI/CD pipeline", "signal_type": "blog"},
    {"label": "irrelevant", "entity": "Social", "text": "Twitter thread: thoughts on the future of AI", "signal_type": "social"},
    {"label": "irrelevant", "entity": "Newsletter", "text": "Monthly digest: product updates and announcements", "signal_type": "newsletter"},
    {"label": "irrelevant", "entity": "Marketing", "text": "Marketing email: 20% off all annual plans", "signal_type": "marketing"},
    {"label": "irrelevant", "entity": "Eng Team", "text": "Standup: all good, no updates today", "signal_type": "reported_statement"},
    {"label": "irrelevant", "entity": "Newsletter", "text": "Weekly newsletter: top stories from the week", "signal_type": "newsletter"},
    {"label": "irrelevant", "entity": "Blog", "text": "Dev blog: migrating from REST to GraphQL", "signal_type": "blog"},
    {"label": "irrelevant", "entity": "Social", "text": "Instagram: team photo from the offsite", "signal_type": "social"},
    {"label": "irrelevant", "entity": "FYI", "text": "FYI: new coffee machine installed in break room", "signal_type": "fyi"},
    {"label": "irrelevant", "entity": "Newsletter", "text": "AI newsletter: GPT-5 rumors and what they mean", "signal_type": "newsletter"},
    {"label": "irrelevant", "entity": "Marketing", "text": "Webinar invite: join us for a product demo", "signal_type": "marketing"},
    {"label": "irrelevant", "entity": "Eng Team", "text": "Standup: finished the refactor, moving to next sprint", "signal_type": "reported_statement"},
    {"label": "irrelevant", "entity": "Blog", "text": "Engineering blog: our journey to microservices", "signal_type": "blog"},
    {"label": "irrelevant", "entity": "Newsletter", "text": "Product newsletter: new features shipping this month", "signal_type": "newsletter"},
    {"label": "irrelevant", "entity": "Social", "text": "LinkedIn: celebrating 5 years as a company", "signal_type": "social"},
    {"label": "irrelevant", "entity": "FYI", "text": "FYI: parking lot maintenance on Saturday", "signal_type": "fyi"},
    {"label": "irrelevant", "entity": "Newsletter", "text": "Dev newsletter: best VS Code extensions 2026", "signal_type": "newsletter"},
    {"label": "irrelevant", "entity": "Marketing", "text": "Black Friday sale: 50% off all plans", "signal_type": "marketing"},
    {"label": "irrelevant", "entity": "Eng Team", "text": "Daily standup: nothing to report", "signal_type": "reported_statement"},
    {"label": "irrelevant", "entity": "Blog", "text": "Company blog: year in review 2025", "signal_type": "blog"},
    {"label": "irrelevant", "entity": "Newsletter", "text": "Weekly digest: AI news roundup", "signal_type": "newsletter"},
    {"label": "irrelevant", "entity": "Social", "text": "Twitter: excited about our new hire", "signal_type": "social"},
    {"label": "irrelevant", "entity": "FYI", "text": "FYI: lunch will be catered on Friday", "signal_type": "fyi"},
    {"label": "irrelevant", "entity": "Newsletter", "text": "Tech news: 10 startups to watch", "signal_type": "newsletter"},
    {"label": "irrelevant", "entity": "Marketing", "text": "Email: refer a friend and get $100", "signal_type": "marketing"},
    {"label": "irrelevant", "entity": "Eng Team", "text": "Standup: everything on track, no blockers", "signal_type": "reported_statement"},
    {"label": "irrelevant", "entity": "Blog", "text": "Engineering: why we chose Rust", "signal_type": "blog"},
    {"label": "irrelevant", "entity": "Newsletter", "text": "Monthly: best open source projects", "signal_type": "newsletter"},
    {"label": "irrelevant", "entity": "Social", "text": "Facebook: company picnic photos", "signal_type": "social"},
    {"label": "irrelevant", "entity": "FYI", "text": "FYI: new VPN setup instructions", "signal_type": "fyi"},
    {"label": "irrelevant", "entity": "Newsletter", "text": "AI weekly: transformer architectures explained", "signal_type": "newsletter"},
    {"label": "irrelevant", "entity": "Marketing", "text": "Spring sale: 30% off annual subscriptions", "signal_type": "marketing"},
    {"label": "irrelevant", "entity": "Eng Team", "text": "Sprint review: all stories completed", "signal_type": "reported_statement"},
    {"label": "irrelevant", "entity": "Blog", "text": "DevOps: our CI/CD pipeline journey", "signal_type": "blog"},
    {"label": "irrelevant", "entity": "Newsletter", "text": "Cloud newsletter: AWS vs Azure comparison", "signal_type": "newsletter"},
    {"label": "irrelevant", "entity": "Social", "text": "Instagram: behind the scenes at our hackathon", "signal_type": "social"},
    {"label": "irrelevant", "entity": "FYI", "text": "FYI: fire drill scheduled for Wednesday", "signal_type": "fyi"},
    {"label": "irrelevant", "entity": "Newsletter", "text": "Startup newsletter: funding rounds this week", "signal_type": "newsletter"},
    {"label": "irrelevant", "entity": "Marketing", "text": "Early bird: register for our conference", "signal_type": "marketing"},
    {"label": "irrelevant", "entity": "Eng Team", "text": "Retrospective: what went well this sprint", "signal_type": "reported_statement"},
    {"label": "irrelevant", "entity": "Blog", "text": "Design blog: our new brand identity", "signal_type": "blog"},
]

# ── Setup ─────────────────────────────────────────────────────────
tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="silence_")
tmp_db.close()
DB_PATH = tmp_db.name
os.environ["MAESTRO_PERSONAL_DB"] = DB_PATH
os.environ["MAESTRO_PERSONAL_TOKEN"] = TOKEN
os.environ["MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL"] = "1"

from maestro_personal_shell.db_util import get_db_conn
from maestro_personal_shell import api as pa
pa.init_db()

conn = get_db_conn(DB_PATH)
now = datetime.now(timezone.utc)
for i, m in enumerate(MOMENTS):
    conn.execute(
        "INSERT OR REPLACE INTO signals (signal_id, entity, text, signal_type, timestamp, metadata, source_acl, created_at, user_email) VALUES (?,?,?,?,?,?,?,?,?)",
        (str(uuid4()), m["entity"], m["text"], m["signal_type"],
         now.isoformat(), json.dumps({"label": m["label"]}), "public", now.isoformat(), "bootstrap"))
conn.commit()
conn.close()
from maestro_personal_shell.semantic_retrieval import rebuild_fts_index
rebuild_fts_index(DB_PATH)
print(f"Seeded {len(MOMENTS)} moments ({sum(1 for m in MOMENTS if m['label']=='critical')} critical, {sum(1 for m in MOMENTS if m['label']=='moderate')} moderate, {sum(1 for m in MOMENTS if m['label']=='irrelevant')} irrelevant)", flush=True)

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

# ── Run whisper endpoint ──────────────────────────────────────────
H = {"Authorization": f"Bearer {TOKEN}"}
BASE = f"http://127.0.0.1:{PORT}"

print("\nCalling GET /api/whisper...", flush=True)
req = urllib.request.Request(f"{BASE}/api/whisper", headers=H)
resp = urllib.request.urlopen(req, timeout=60)
whispers = json.loads(resp.read())
print(f"Got {len(whispers)} whispers", flush=True)

# ── Analyze ───────────────────────────────────────────────────────
# For each whisper, check if it corresponds to a critical/moderate/irrelevant moment
whisper_entities = {w.get("entity", "").lower() for w in whispers}
whisper_texts = [w.get("body", "").lower() + " " + w.get("title", "").lower() for w in whispers]

critical_moments = [m for m in MOMENTS if m["label"] == "critical"]
moderate_moments = [m for m in MOMENTS if m["label"] == "moderate"]
irrelevant_moments = [m for m in MOMENTS if m["label"] == "irrelevant"]

# Check: did whispers catch critical moments?
critical_caught = 0
for m in critical_moments:
    m_entity = m["entity"].lower()
    m_text = m["text"].lower()
    for wt in whisper_texts:
        if m_entity in wt or any(word in wt for word in m_text.split()[:3] if len(word) > 3):
            critical_caught += 1
            break

# Check: did whispers suppress irrelevant moments?
irrelevant_whispered = 0
for w in whispers:
    w_text = (w.get("body", "") + " " + w.get("title", "")).lower()
    for m in irrelevant_moments:
        if m["entity"].lower() in w_text and m["text"][:20].lower() in w_text:
            irrelevant_whispered += 1
            break

critical_recall = critical_caught / len(critical_moments) if critical_moments else 0
false_silence = 1 - critical_recall
low_value_suppression = 1 - (irrelevant_whispered / len(irrelevant_moments)) if irrelevant_moments else 0

print(f"\n{'='*70}", flush=True)
print(f"  TRUSTED SILENCE BENCHMARK — 100 MOMENTS", flush=True)
print(f"{'='*70}", flush=True)
print(f"  Moments: {len(MOMENTS)} ({len(critical_moments)} critical, {len(moderate_moments)} moderate, {len(irrelevant_moments)} irrelevant)", flush=True)
print(f"  Whispers generated: {len(whispers)}", flush=True)
print(f"  Critical moments caught: {critical_caught}/{len(critical_moments)}", flush=True)
print(f"  Irrelevant moments whispered: {irrelevant_whispered}/{len(irrelevant_moments)}", flush=True)
print(f"", flush=True)
print(f"  Critical recall:     {critical_recall:.1%} (bar: >=95%)", flush=True)
print(f"  False silence:       {false_silence:.1%} (bar: <=5%)", flush=True)
print(f"  Low-value suppression: {low_value_suppression:.1%} (bar: >=85%)", flush=True)
print(f"", flush=True)
if critical_recall >= 0.95: print(f"  Critical recall PASS", flush=True)
else: print(f"  Critical recall FAIL ({critical_recall:.1%} < 95%)", flush=True)
if low_value_suppression >= 0.85: print(f"  Suppression PASS", flush=True)
else: print(f"  Suppression {'PASS' if low_value_suppression >= 0.85 else 'FAIL'} ({low_value_suppression:.1%})", flush=True)

# Whisper details
print(f"\n  Whispers by type:", flush=True)
by_type = {}
for w in whispers:
    t = w.get("type", "unknown")
    by_type[t] = by_type.get(t, 0) + 1
for t, c in sorted(by_type.items()):
    print(f"    {t}: {c}", flush=True)

# Save
out = {
    "total_moments": len(MOMENTS),
    "critical_count": len(critical_moments),
    "moderate_count": len(moderate_moments),
    "irrelevant_count": len(irrelevant_moments),
    "whispers_generated": len(whispers),
    "critical_caught": critical_caught,
    "irrelevant_whispered": irrelevant_whispered,
    "critical_recall": round(critical_recall, 4),
    "false_silence": round(false_silence, 4),
    "low_value_suppression": round(low_value_suppression, 4),
    "whisper_types": by_type,
}
out_path = "/home/z/my-project/download/silence_benchmark_100.json"
with open(out_path, "w") as f:
    json.dump(out, f, indent=2)
print(f"\nResults saved to: {out_path}", flush=True)

server_proc.terminate()
server_proc.wait(timeout=5)
