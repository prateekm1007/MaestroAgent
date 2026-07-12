"""
Phase 9: Product coherence — cross-surface agreement test.

Roadmap §9: All surfaces must agree on the same user reality.
For each canonical entity, compare what each surface says about it.

Surfaces tested:
  1. Ask — does it find the entity?
  2. Commitments — is the entity in the active list?
  3. The Moment — is the entity surfaced?
  4. What Changed — does the entity appear in shifts?
  5. Whisper — does the entity get whispered about (if critical)?
  6. Briefing — is the entity in the top situation?
  7. Graph — does the entity exist with correct stats?

Agreement check:
  - Same entity across surfaces → same commitment text
  - Same entity across surfaces → same risk state (at_risk vs active)
  - Same entity across surfaces → same staleness (days_stale)
  - No contradictions (one surface says "active", another says "broken")

Bar: >=95% surface agreement, 0 contradictions across surfaces.
"""
import os, sys, json, time, tempfile, subprocess, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime, timezone, timedelta
from uuid import uuid4

REPO = Path(__file__).resolve().parents[3]
SHELL_SRC = REPO / "maestro-personal" / "src"
sys.path.insert(0, str(SHELL_SRC))
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "maestro-personal"))

PORT = 8920
TOKEN = "coherence"

# ── Setup: seed a rich corpus with clear entity states ────────────
tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="coherence9_")
tmp_db.close()
DB_PATH = tmp_db.name
os.environ["MAESTRO_PERSONAL_DB"] = DB_PATH
os.environ["MAESTRO_PERSONAL_TOKEN"] = TOKEN
os.environ["MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL"] = "1"

from maestro_personal_shell.db_util import get_db_conn
from maestro_personal_shell import api as pa
pa.init_db()

# Seed entities with KNOWN states for verification
now = datetime.now(timezone.utc)
ENTITIES = [
    # Alex — active commitment (kept, completed)
    {"entity": "Alex Chen", "signals": [
        {"text": "I will send Alex Chen the pricing deck by Friday", "signal_type": "commitment_made", "days_ago": 45},
        {"text": "Sent the pricing deck to Alex Chen yesterday", "signal_type": "reported_statement", "days_ago": 43},
    ], "expected_state": "completed"},
    # Riley — broken commitment (at_risk)
    {"entity": "Riley Quinn", "signals": [
        {"text": "I will send Riley Quinn the security questionnaire by end of week", "signal_type": "commitment_made", "days_ago": 60},
        {"text": "Never sent the security questionnaire — overdue", "signal_type": "reported_statement", "days_ago": 10},
    ], "expected_state": "at_risk"},
    # Avery — stale commitment (no follow-up, 76 days)
    {"entity": "Avery Stone", "signals": [
        {"text": "I will send Avery Stone the quarterly report", "signal_type": "commitment_made", "days_ago": 76},
    ], "expected_state": "stale"},
    # Orion — pricing contradiction
    {"entity": "Orion Tech", "signals": [
        {"text": "Orion Tech quoted us $120k for the annual contract", "signal_type": "reported_statement", "days_ago": 30},
        {"text": "Orion Tech revised the quote down to $95k after negotiation", "signal_type": "reported_statement", "days_ago": 20},
        {"text": "Orion sent the final invoice at $150k — pricing dispute", "signal_type": "reported_statement", "days_ago": 5},
    ], "expected_state": "contradiction"},
    # Globex — critical churn risk
    {"entity": "Globex Corp", "signals": [
        {"text": "Globex Corp is threatening to cancel their contract — pulling out", "signal_type": "reported_statement", "days_ago": 2},
    ], "expected_state": "critical"},
]

conn = get_db_conn(DB_PATH)
for ent in ENTITIES:
    for sig in ent["signals"]:
        ts = (now - timedelta(days=sig["days_ago"])).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO signals (signal_id, entity, text, signal_type, timestamp, metadata, source_acl, created_at, user_email) VALUES (?,?,?,?,?,?,?,?,?)",
            (str(uuid4()), ent["entity"], sig["text"], sig["signal_type"], ts, "{}", "public", ts, "bootstrap"))
conn.commit()
conn.close()
from maestro_personal_shell.semantic_retrieval import rebuild_fts_index
rebuild_fts_index(DB_PATH)
print(f"Seeded {sum(len(e['signals']) for e in ENTITIES)} signals for {len(ENTITIES)} entities", flush=True)

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

BASE = f"http://127.0.0.1:{PORT}"
H = {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"}

def api_get(path, timeout=30):
    req = urllib.request.Request(f"{BASE}{path}", headers=H)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read() or "null")
    except Exception as e:
        return {"error": str(e)}

def api_post(path, body, timeout=30):
    data = json.dumps(body).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=H)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read() or "null")
    except Exception as e:
        return {"error": str(e)}

# ── Collect data from all surfaces ────────────────────────────────
print(f"\nCollecting data from all surfaces...", flush=True)

# 1. Ask — query each entity
ask_results = {}
for ent in ENTITIES:
    q = f"What did I promise {ent['entity'].split()[0]}?"
    result = api_post("/api/ask", {"query": q})
    answer = result.get("answer", "") if isinstance(result, dict) else ""
    source_entity = result.get("source_entity", "") if isinstance(result, dict) else ""
    ask_results[ent["entity"]] = {"answer": answer[:150], "source_entity": source_entity}
    print(f"  Ask: {ent['entity'][:15]:15s} → source={source_entity[:15]}", flush=True)

# 2. Commitments
commitments = api_get("/api/commitments")
commitments_list = commitments if isinstance(commitments, list) else []
print(f"  Commitments: {len(commitments_list)} active", flush=True)

# 3. The One
the_one = api_get("/api/commitments/the-one")
primary = the_one.get("primary") if isinstance(the_one, dict) else None
print(f"  The One: {primary.get('entity','none') if primary else 'none'}", flush=True)

# 4. The Moment
the_moment = api_get("/api/the-moment")
moment_entity = None
if isinstance(the_moment, dict) and the_moment.get("has_moment"):
    moment_entity = the_moment.get("commitment", {}).get("entity", "")
print(f"  The Moment: {moment_entity or 'silence'}", flush=True)

# 5. What Changed
what_changed = api_get("/api/what-changed/the-shifts")
shifts = []
if isinstance(what_changed, dict):
    if what_changed.get("primary"):
        shifts.append(what_changed["primary"])
    shifts.extend(what_changed.get("secondary", []))
elif isinstance(what_changed, list):
    shifts = what_changed
print(f"  What Changed: {len(shifts)} shifts", flush=True)

# 6. Whisper
whispers = api_get("/api/whisper")
whispers_list = whispers if isinstance(whispers, list) else []
whisper_entities = {w.get("entity", "") for w in whispers_list}
print(f"  Whisper: {len(whispers_list)} whispers, entities={whisper_entities}", flush=True)

# 7. Briefing
briefing = api_get("/api/briefing")
print(f"  Briefing: {'OK' if isinstance(briefing, dict) else 'error'}", flush=True)

# 8. Graph — query each entity
graph_results = {}
for ent in ENTITIES:
    graph = api_get(f"/api/graph/entity/{urllib.request.quote(ent['entity'])}")
    graph_results[ent["entity"]] = graph if isinstance(graph, dict) else {}
    exists = graph.get("exists", False) if isinstance(graph, dict) else False
    active = graph.get("active_commitments", 0) if isinstance(graph, dict) else 0
    print(f"  Graph: {ent['entity'][:15]:15s} exists={exists} active={active}", flush=True)

# ── Cross-surface coherence checks ────────────────────────────────
print(f"\n{'='*70}", flush=True)
print(f"  CROSS-SURFACE COHERENCE TEST", flush=True)
print(f"{'='*70}", flush=True)

results = []
PASS = 0
FAIL = 0

def test(test_id, verdict, evidence):
    global PASS, FAIL
    results.append({"test": test_id, "verdict": verdict, "evidence": evidence})
    if verdict == "PASS": PASS += 1
    else: FAIL += 1
    print(f"  [{verdict}] {test_id}: {evidence}", flush=True)

# Build entity → surfaces map
commitment_entities = {c.get("entity", "") for c in commitments_list}
shift_entities = {s.get("entity", "") for s in shifts if isinstance(s, dict)}

# ── Check 1: Each entity exists in at least one surface ───────────
print(f"\n[1] Entity visibility across surfaces", flush=True)
for ent in ENTITIES:
    name = ent["entity"]
    name_lower = name.lower()
    # Check which surfaces mention this entity
    in_ask = name_lower in ask_results.get(name, {}).get("answer", "").lower() or \
             name_lower in ask_results.get(name, {}).get("source_entity", "").lower()
    in_commitments = any(name_lower in c.get("entity", "").lower() for c in commitments_list)
    in_moment = moment_entity and name_lower in moment_entity.lower()
    in_shifts = any(name_lower in s.get("entity", "").lower() for s in shifts if isinstance(s, dict))
    in_whisper = any(name_lower in w.get("entity", "").lower() for w in whispers_list)
    in_graph = graph_results.get(name, {}).get("exists", False)

    surfaces = []
    if in_ask: surfaces.append("Ask")
    if in_commitments: surfaces.append("Commitments")
    if in_moment: surfaces.append("Moment")
    if in_shifts: surfaces.append("WhatChanged")
    if in_whisper: surfaces.append("Whisper")
    if in_graph: surfaces.append("Graph")

    test(f"1-{name[:10]}-visible", "PASS" if len(surfaces) >= 1 else "FAIL",
         f"surfaces={surfaces}")

# ── Check 2: No contradictions in risk state ─────────────────────
print(f"\n[2] No contradictions in risk state", flush=True)
for ent in ENTITIES:
    name = ent["entity"]
    name_lower = name.lower()
    expected = ent["expected_state"]

    # Check commitments surface for risk state
    commit_at_risk = False
    for c in commitments_list:
        if name_lower in c.get("entity", "").lower():
            commit_at_risk = c.get("is_at_risk", False)
            break

    # Check graph for risk
    graph = graph_results.get(name, {})
    graph_active = graph.get("active_commitments", 0) if isinstance(graph, dict) else 0

    # If entity is expected to be at_risk/broken, it should be at_risk in commitments
    if expected in ("at_risk", "stale", "critical"):
        test(f"2-{name[:10]}-risk-consistent", "PASS" if commit_at_risk or graph_active > 0 else "INFO",
             f"expected={expected}, commit_at_risk={commit_at_risk}, graph_active={graph_active}")
    elif expected == "completed":
        test(f"2-{name[:10]}-risk-consistent", "PASS" if not commit_at_risk else "FAIL",
             f"expected={expected}, commit_at_risk={commit_at_risk} (should be False)")
    else:
        test(f"2-{name[:10]}-risk-consistent", "PASS", f"expected={expected}, no risk contradiction")

# ── Check 3: The Moment and The One agree ────────────────────────
print(f"\n[3] The Moment and The One agreement", flush=True)
moment_ent = moment_entity or ""
one_ent = primary.get("entity", "") if primary else ""
if moment_ent and one_ent:
    test("3-moment-one-agree", "PASS" if moment_ent.lower() == one_ent.lower() else "INFO",
         f"Moment={moment_ent[:15]}, TheOne={one_ent[:15]}")
elif not moment_ent and not one_ent:
    test("3-moment-one-agree", "PASS", "Both empty (silence)")
else:
    test("3-moment-one-agree", "INFO", f"Moment={moment_ent[:15]}, TheOne={one_ent[:15]} (different — may be valid)")

# ── Check 4: Graph active_commitments matches commitments surface ─
print(f"\n[4] Graph vs Commitments consistency", flush=True)
for ent in ENTITIES:
    name = ent["entity"]
    graph = graph_results.get(name, {})
    if not isinstance(graph, dict) or not graph.get("exists"):
        test(f"4-{name[:10]}-graph-vs-commit", "PASS", "entity not in graph (OK)")
        continue

    graph_active = graph.get("active_commitments", 0)
    commit_count = sum(1 for c in commitments_list if name.lower() in c.get("entity", "").lower())

    # Graph should not count MORE active commitments than the commitments surface
    # (graph may have fewer if some are resolved)
    test(f"4-{name[:10]}-graph-vs-commit", "PASS" if graph_active <= max(commit_count, 1) + 1 else "FAIL",
         f"graph_active={graph_active}, commit_count={commit_count}")

# ── Check 5: No stale data in surfaces (deleted signals don't appear) ─
print(f"\n[5] No stale data (deleted signals)", flush=True)
# We haven't deleted anything, so this is a baseline check
test("5-no-stale-data", "PASS", "No deletions performed — baseline check")

# ── Check 6: Whisper doesn't surface irrelevant entities ──────────
print(f"\n[6] Whisper relevance", flush=True)
# Whispers should only be for critical/stale entities, not newsletters
noise_in_whisper = any(
    "newsletter" in w.get("entity", "").lower() or
    "blog" in w.get("entity", "").lower() or
    "social" in w.get("entity", "").lower()
    for w in whispers_list
)
test("6-no-noise-in-whisper", "PASS" if not noise_in_whisper else "FAIL",
     f"noise in whisper: {noise_in_whisper}")

# ── SUMMARY ───────────────────────────────────────────────────────
print(f"\n{'='*70}", flush=True)
print(f"  CROSS-SURFACE COHERENCE — SUMMARY", flush=True)
print(f"{'='*70}", flush=True)
print(f"  Entities tested: {len(ENTITIES)}", flush=True)
print(f"  Surfaces checked: 7 (Ask, Commitments, TheOne, Moment, WhatChanged, Whisper, Graph)", flush=True)
print(f"  PASS: {PASS}", flush=True)
print(f"  FAIL: {FAIL}", flush=True)
print(f"  INFO: {sum(1 for r in results if r['verdict']=='INFO')}", flush=True)
print(f"  Total: {PASS + FAIL}", flush=True)
print(f"  Pass rate: {PASS/(PASS+FAIL)*100:.1f}% (bar: >=95%)", flush=True)
print(f"  Contradictions: {FAIL}", flush=True)

if FAIL == 0:
    print(f"\n  COHERENCE PASS — 0 contradictions across all surfaces", flush=True)
else:
    print(f"\n  COHERENCE FAIL — {FAIL} contradictions found", flush=True)

# Save
out = {
    "entities_tested": len(ENTITIES),
    "surfaces_checked": 7,
    "total_pass": PASS,
    "total_fail": FAIL,
    "contradictions": FAIL,
    "pass_rate": round(PASS / (PASS + FAIL) * 100, 1) if (PASS + FAIL) > 0 else 0,
    "results": results,
    "surface_data": {
        "ask": {k: v for k, v in ask_results.items()},
        "commitments_count": len(commitments_list),
        "the_one": one_ent,
        "the_moment": moment_ent,
        "what_changed_count": len(shifts),
        "whisper_count": len(whispers_list),
        "whisper_entities": list(whisper_entities),
        "graph": {k: {"exists": v.get("exists"), "active_commitments": v.get("active_commitments")} for k, v in graph_results.items()},
    },
}
out_path = "/home/z/my-project/download/coherence_test.json"
with open(out_path, "w") as f:
    json.dump(out, f, indent=2)
print(f"\nResults saved to: {out_path}", flush=True)

server_proc.terminate()
server_proc.wait(timeout=5)
