"""
100K signal benchmark — bulk-insert 100K signals directly into SQLite,
then measure Ask latency at scale via the HTTP API.

Phase 8 of Roadmap to 9/10:
  - Ask p95 at 100K signals < 2000ms (rules/local)
  - DB size documented
  - FTS rebuild time documented

Runs in RULE MODE (no LLM) so it's not blocked by tunnel congestion.
"""
import os, sys, json, time, tempfile, threading, statistics, sqlite3, urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta
from uuid import uuid4

REPO = Path(__file__).resolve().parents[3]
SHELL_SRC = REPO / "maestro-personal" / "src"
sys.path.insert(0, str(SHELL_SRC))
sys.path.insert(0, str(REPO / "backend"))

tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="bench100k_")
tmp_db.close()
DB_PATH = tmp_db.name
os.environ["MAESTRO_PERSONAL_DB"] = DB_PATH
os.environ["MAESTRO_PERSONAL_TOKEN"] = "bench100k-token"
os.environ["MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL"] = "1"
os.environ.pop("MAESTRO_PERSONAL_ENV", None)
os.environ.pop("OLLAMA_HOST", None)
os.environ.pop("OLLAMA_MODEL", None)

# ── Phase 1: Bulk insert 100K signals directly into SQLite ────────
print("[bench] Phase 1: Bulk-inserting 100,000 signals directly into SQLite...")
TOTAL = 100_000
ENTITIES = [f"Entity{i:04d}" for i in range(200)]
SIGNAL_TYPES = ["commitment_made", "reported_statement", "newsletter", "follow_up_required"]

from maestro_personal_shell.db_util import get_db_conn
from maestro_personal_shell import api as personal_api
personal_api.init_db()

t0 = time.time()
conn = get_db_conn(DB_PATH)
now = datetime.now(timezone.utc)
batch = []
for i in range(TOTAL):
    entity = ENTITIES[i % len(ENTITIES)]
    sig_type = SIGNAL_TYPES[i % len(SIGNAL_TYPES)]
    days_ago = i % 90
    ts = (now - timedelta(days=days_ago)).isoformat()
    sig_id = str(uuid4())
    batch.append((
        sig_id, entity,
        f"Signal {i} from {entity}: commitment to deliver item {i % 50} by Friday",
        sig_type, ts, "{}", "public", ts, "default@personal.local",
    ))

conn.executemany(
    """INSERT OR REPLACE INTO signals
       (signal_id, entity, text, signal_type, timestamp, metadata, source_acl, created_at, user_email)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
    batch,
)
conn.commit()
conn.close()
bulk_time = time.time() - t0
print(f"  Inserted {TOTAL} signals in {bulk_time:.1f}s ({TOTAL/bulk_time:.0f} sig/s)")
print(f"  DB size: {os.path.getsize(DB_PATH) // 1024 // 1024} MB")

# ── Phase 2: Rebuild FTS index ────────────────────────────────────
print("\n[bench] Phase 2: Rebuilding FTS index...")
t0 = time.time()
from maestro_personal_shell.semantic_retrieval import rebuild_fts_index
count = rebuild_fts_index(DB_PATH)
fts_time = time.time() - t0
print(f"  FTS index rebuilt: {count} signals in {fts_time:.1f}s")

# ── Phase 3: Start API + measure Ask latency ──────────────────────
print("\n[bench] Phase 3: Starting API + measuring Ask latency...")
import uvicorn
config = uvicorn.Config(personal_api.app, host="127.0.0.1", port=8782, log_level="error")
server = uvicorn.Server(config)
t = threading.Thread(target=server.run, daemon=True)
t.start()
for i in range(40):
    try:
        urllib.request.urlopen("http://127.0.0.1:8782/api/health", timeout=2)
        print(f"  API ready after {i}s")
        break
    except Exception:
        time.sleep(0.5)

BASE = "http://127.0.0.1:8782"
TOKEN = "bench100k-token"

def http_post(path, body, timeout=120):
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

# Login (get a real bearer token)
r, body = http_post("/api/auth/login", {"password": TOKEN})
assert r == 200
# Use AUTH_TOKEN directly (it's the same as TOKEN in dev mode)
H_TOKEN = TOKEN

ASK_QUERIES = [
    "What did I promise Entity0001?",
    "Which promises are overdue?",
    "What's the latest from Entity0042?",
    "Who am I repeatedly disappointing?",
    "What should I prepare for tomorrow?",
    "What did I commit to last quarter?",
    "What's the oldest unfulfilled commitment?",
    "What keeps recurring?",
    "Are there any legal issues?",
    "What's my most important commitment?",
]

print(f"\n  Firing {len(ASK_QUERIES)} Ask queries at {TOTAL} signals (rule mode)...")
ask_latencies = []
for q in ASK_QUERIES:
    t0 = time.time()
    r, body = http_post("/api/ask", {"query": q}, timeout=120)
    elapsed = time.time() - t0
    if r == 200:
        ask_latencies.append(elapsed * 1000)
        marker = "OK" if elapsed < 2.0 else "SLOW"
        print(f"    [{marker}] {elapsed:.3f}s  {q[:50]}")
    else:
        print(f"    [ERR] {r}  {q[:50]}")

# ── Phase 4: GET /api/signals latency ─────────────────────────────
print(f"\n[bench] Phase 4: GET /api/signals latency...")
t0 = time.time()
req = urllib.request.Request(f"{BASE}/api/signals", headers={"Authorization": f"Bearer {H_TOKEN}"})
try:
    resp = urllib.request.urlopen(req, timeout=60)
    signals_count = len(json.loads(resp.read()))
    get_latency = (time.time() - t0) * 1000
    print(f"  GET /api/signals: {get_latency:.1f}ms ({signals_count} signals)")
except Exception as e:
    get_latency = -1
    print(f"  GET /api/signals FAILED: {e}")

# ── Summary ───────────────────────────────────────────────────────
db_size_mb = os.path.getsize(DB_PATH) // 1024 // 1024
print("\n" + "=" * 70)
print(f"  100K SIGNAL BENCHMARK — RULE MODE")
print("=" * 70)
print(f"\n  Signals in DB:       {TOTAL}")
print(f"  Bulk insert time:    {bulk_time:.1f}s ({TOTAL/bulk_time:.0f} sig/s)")
print(f"  FTS rebuild time:    {fts_time:.1f}s")
print(f"  DB size:             {db_size_mb} MB")

if ask_latencies:
    ask_p50 = statistics.median(ask_latencies)
    ask_p95 = sorted(ask_latencies)[int(len(ask_latencies)*0.95)] if len(ask_latencies) > 1 else ask_latencies[0]
    ask_max = max(ask_latencies)
    print(f"\n  Ask p50:             {ask_p50:.1f}ms")
    print(f"  Ask p95:             {ask_p95:.1f}ms")
    print(f"  Ask max:             {ask_max:.1f}ms")
    bar = "PASS" if ask_p95 < 2000 else "FAIL"
    print(f"  9/10 bar (p95<2000ms): {bar}")
else:
    print(f"\n  Ask: no successful queries")

if get_latency > 0:
    print(f"  GET /api/signals:    {get_latency:.1f}ms")

out = {
    "signals_in_db": TOTAL,
    "bulk_insert_time_s": bulk_time,
    "fts_rebuild_time_s": fts_time,
    "db_size_mb": db_size_mb,
    "ask_latencies_ms": ask_latencies,
    "ask_p50_ms": statistics.median(ask_latencies) if ask_latencies else None,
    "ask_p95_ms": sorted(ask_latencies)[int(len(ask_latencies)*0.95)] if len(ask_latencies) > 1 else (ask_latencies[0] if ask_latencies else None),
    "ask_max_ms": max(ask_latencies) if ask_latencies else None,
    "get_signals_latency_ms": get_latency if get_latency > 0 else None,
}
out_path = "/home/z/my-project/download/benchmark_100k_results.json"
with open(out_path, "w") as f:
    json.dump(out, f, indent=2)
print(f"\n  Results: {out_path}")

server.should_exit = True
time.sleep(1)
