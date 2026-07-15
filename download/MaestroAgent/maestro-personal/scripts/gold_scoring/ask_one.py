"""
ask_one.py — Ask ONE Gold-150 question in a fresh process.

Each call: load app → login → ask 1 question → append result to JSONL → exit.
No memory accumulation across questions because each is a fresh process.

Usage:
  python ask_one.py <question_index> <db_path> <jsonl_path>

The JSONL file is the progress — each line is one result. The wrapper
script loops through 0-149, calling this for each.
"""
import os
import sys
import json
import time
import asyncio

# Args
q_idx = int(sys.argv[1])
DB_PATH = sys.argv[2]
JSONL_PATH = sys.argv[3]

TUNNEL = "https://piano-lovers-automation-subdivision.trycloudflare.com"
MODEL = "llama3:8b"
TOKEN = "gold-test-token"

# Set env BEFORE any imports
os.environ["MAESTRO_PERSONAL_DB"] = DB_PATH
os.environ["MAESTRO_PERSONAL_TOKEN"] = TOKEN
os.environ["MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL"] = "1"
os.environ["MAESTRO_ENV"] = "dev"
os.environ["OLLAMA_HOST"] = TUNNEL
os.environ["OLLAMA_MODEL"] = MODEL

REPO = "/home/z/my-project/MaestroAgent/download/MaestroAgent/maestro-personal"
sys.path.insert(0, f"{REPO}/src")
sys.path.insert(0, REPO)

# Import + init
from maestro_personal_shell.api import init_db, app
init_db()

# Reset LLM router AFTER imports (critical)
from maestro_personal_shell.llm_bridge import reset_llm_router
reset_llm_router()

# Rebuild FTS if needed
try:
    from maestro_personal_shell.semantic_retrieval import rebuild_fts_index
    rebuild_fts_index()
except Exception:
    pass

# Get the question
from evaluation.scoreboard.gold_150 import GOLD_150
q = GOLD_150[q_idx]

# Login
from fastapi.testclient import TestClient
client = TestClient(app)
r = client.post("/api/auth/login", json={"user_email": "default@personal.local", "password": TOKEN})
H = {"Authorization": f"Bearer {r.json()['token']}"}

# Ask
t0 = time.time()
try:
    r = client.post("/api/ask", json={"query": q["query"]}, headers=H, timeout=120)
    elapsed = time.time() - t0
    if r.status_code != 200:
        result = {"id": q["id"], "type": q["type"], "query": q["query"],
                  "score": 0.0, "error": f"HTTP {r.status_code}", "llm_active": False, "elapsed": elapsed, "idx": q_idx}
    else:
        body = r.json()
        answer = body.get("answer", "")
        llm_active = body.get("llm_active", False)
        confidence = body.get("confidence", 0)
        evidence = body.get("evidence_refs", [])

        expected = q.get("expected_keywords", [])
        forbidden = q.get("forbidden_keywords", [])
        should_abstain = q.get("should_abstain", False)
        answer_lower = answer.lower()
        if should_abstain:
            abstain_phrases = ["don't have", "insufficient", "no evidence", "not enough"]
            score = 1.0 if any(p in answer_lower for p in abstain_phrases) else 0.0
        else:
            has_all_expected = all(kw.lower() in answer_lower for kw in expected)
            has_forbidden = any(kw.lower() in answer_lower for kw in forbidden)
            score = 1.0 if (has_all_expected and not has_forbidden) else 0.0

        result = {"id": q["id"], "type": q["type"], "query": q["query"], "score": score,
                  "answer_preview": answer[:150],
                  "evidence_count": len(evidence) if isinstance(evidence, list) else 0,
                  "llm_active": llm_active, "confidence": confidence, "elapsed": elapsed, "idx": q_idx}
except Exception as e:
    elapsed = time.time() - t0
    result = {"id": q["id"], "type": q["type"], "query": q["query"],
              "score": 0.0, "error": str(e)[:200], "llm_active": False, "elapsed": elapsed, "idx": q_idx}

# Append to JSONL (atomic write — open in append mode, write 1 line, close)
with open(JSONL_PATH, "a") as f:
    f.write(json.dumps(result) + "\n")
    f.flush()
    os.fsync(f.fileno())

print(f"[{q_idx+1}/150] {result.get('score',0):.2f} llm={result.get('llm_active')} {q['type']:15s} {q['query'][:40]} ({result.get('elapsed',0):.1f}s)", flush=True)
os._exit(0)
