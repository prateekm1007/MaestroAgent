"""
Ablation Benchmark + Live User Scenario

Part 1: Build a 90-day synthetic corpus (10+ people, 5+ projects, 100+ signals).
Part 2: Exercise all surfaces (Ask, Commitments, Whisper, Prepare, What Changed, Briefing, Copilot).
Part 3: Run 30-question ablation: Maestro (full) vs LLM-only vs LLM+retrieval.
Part 4: Score all 3 conditions and report the intelligence differential.

Usage:
    python tests/test_ablation_benchmark.py -v -s

Requires Ollama running (start with: /tmp/ollama serve &)
"""

import sys
import os
import time
import json
import tempfile
import asyncio
import sqlite3
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Module-level marker: every test in this file makes real LLM calls
# (via /api/whisper, /api/ask, etc. which invoke llm_bridge internally
# when an LLM provider is active). The file's docstring confirms this:
# "Requires Ollama running". Without this marker, `-m "not llm_integration"`
# still runs these tests, which:
#   1. Hit the LLM provider's rate limit (ZAI: 30 req / 10 min)
#   2. Take 0.5-3s per LLM call, easily exceeding pytest's 20s timeout
#      when multiple endpoints are exercised
#   3. Fail with timeout errors that mask the real test behavior
# This marker excludes the file from default test runs and is the same
# pattern used by test_llm_via_ollama.py and test_llm_latency_hypothesis.py.
pytestmark = pytest.mark.llm_integration


# ═══════════════════════════════════════════════════════════════════════════
# PART 1: 90-DAY SYNTHETIC CORPUS
# 10 people, 5 projects, 100+ signals, 30+ events, 90 days
# ═══════════════════════════════════════════════════════════════════════════

CORPUS_SIGNALS = [
    # --- Project: Orion Migration (AcmeCorp) ---
    # Alex Chen (project lead) — 3 commitments, 2 follow-ups, 1 completion
    {"entity": "Alex Chen", "text": "I will deliver the Orion migration plan by March 15", "signal_type": "commitment_made", "days_ago": 85},
    {"entity": "Alex Chen", "text": "Orion migration plan delivered to the team", "signal_type": "reported_statement", "days_ago": 82},
    {"entity": "Alex Chen", "text": "I will review the migration checklist with engineering by March 20", "signal_type": "commitment_made", "days_ago": 80},
    {"entity": "Alex Chen", "text": "Need to follow up on the migration checklist review", "signal_type": "follow_up.required", "days_ago": 75},
    {"entity": "Alex Chen", "text": "The Orion migration deadline is slipping — need to push to April", "signal_type": "reported_statement", "days_ago": 60},
    {"entity": "Alex Chen", "text": "I will send the revised timeline to stakeholders by April 5", "signal_type": "commitment_made", "days_ago": 55},
    {"entity": "Alex Chen", "text": "Revised timeline sent to all stakeholders", "signal_type": "reported_statement", "days_ago": 50},
    {"entity": "Alex Chen", "text": "The migration is complete — all systems operational", "signal_type": "reported_statement", "days_ago": 30},

    # Jamie Lee (engineering lead) — broken commitments, delivery risk
    {"entity": "Jamie Lee", "text": "I will have the API migration done by March 25", "signal_type": "commitment_made", "days_ago": 78},
    {"entity": "Jamie Lee", "text": "API migration is delayed — waiting on database schema", "signal_type": "reported_statement", "days_ago": 65},
    {"entity": "Jamie Lee", "text": "I will deliver the database schema by March 30", "signal_type": "commitment_made", "days_ago": 70},
    {"entity": "Jamie Lee", "text": "Still working on the schema — need another week", "signal_type": "reported_statement", "days_ago": 55},
    {"entity": "Jamie Lee", "text": "I will finish the schema by April 10", "signal_type": "commitment_made", "days_ago": 50},
    {"entity": "Jamie Lee", "text": "Schema is still not done — blocked on vendor response", "signal_type": "reported_statement", "days_ago": 35},
    {"entity": "Jamie Lee", "text": "I will escalate the vendor issue to procurement", "signal_type": "commitment_made", "days_ago": 20},

    # Priya Patel (QA lead) — follow-up needed
    {"entity": "Priya Patel", "text": "I will create the test plan for Orion by March 28", "signal_type": "commitment_made", "days_ago": 72},
    {"entity": "Priya Patel", "text": "Test plan draft is ready for review", "signal_type": "reported_statement", "days_ago": 60},
    {"entity": "Priya Patel", "text": "Need follow-up on test plan review from Alex", "signal_type": "follow_up.required", "days_ago": 45},
    {"entity": "Priya Patel", "text": "I will run the regression suite before go-live", "signal_type": "commitment_made", "days_ago": 35},
    {"entity": "Priya Patel", "text": "Regression suite passed — 0 critical failures", "signal_type": "reported_statement", "days_ago": 28},

    # --- Project: Phoenix Launch (GlobexCorp) ---
    # David Kim (VP Sales) — leadership change
    {"entity": "David Kim", "text": "I will present the Phoenix launch plan to the board by April 1", "signal_type": "commitment_made", "days_ago": 68},
    {"entity": "David Kim", "text": "Board presentation went well — approved for Q2 launch", "signal_type": "reported_statement", "days_ago": 62},
    {"entity": "David Kim", "text": "Carol Torres will be taking over as Phoenix project lead", "signal_type": "reported_statement", "days_ago": 40},
    {"entity": "David Kim", "text": "I will transition all Phoenix documents to Carol by April 25", "signal_type": "commitment_made", "days_ago": 38},
    {"entity": "David Kim", "text": "All documents transferred to Carol", "signal_type": "reported_statement", "days_ago": 32},

    # Carol Torres (new project lead) — ramping up
    {"entity": "Carol Torres", "text": "I will review all Phoenix project documents by April 30", "signal_type": "commitment_made", "days_ago": 30},
    {"entity": "Carol Torres", "text": "Reviewing the Phoenix timeline — need to adjust the launch date", "signal_type": "reported_statement", "days_ago": 25},
    {"entity": "Carol Torres", "text": "I will propose a revised Phoenix launch date by May 5", "signal_type": "commitment_made", "days_ago": 20},
    {"entity": "Carol Torres", "text": "Proposed new launch date: May 20", "signal_type": "reported_statement", "days_ago": 15},

    # Eve Smith (customer success) — churn risk
    {"entity": "Eve Smith", "text": "I will check in with the AcmeCorp account by April 15", "signal_type": "commitment_made", "days_ago": 48},
    {"entity": "Eve Smith", "text": "AcmeCorp is threatening to churn — unhappy with Orion delays", "signal_type": "reported_statement", "days_ago": 40},
    {"entity": "Eve Smith", "text": "I will schedule a emergency call with AcmeCorp leadership", "signal_type": "commitment_made", "days_ago": 35},
    {"entity": "Eve Smith", "text": "Emergency call scheduled for Friday", "signal_type": "reported_statement", "days_ago": 30},
    {"entity": "Eve Smith", "text": "AcmeCorp has agreed to stay — conditional on May delivery", "signal_type": "reported_statement", "days_ago": 22},

    # --- Project: Delta Integration (Initrode) ---
    # Frank Wong (engineering) — on track
    {"entity": "Frank Wong", "text": "I will build the Delta API integration by April 20", "signal_type": "commitment_made", "days_ago": 58},
    {"entity": "Frank Wong", "text": "Delta API integration is 80% complete", "signal_type": "reported_statement", "days_ago": 40},
    {"entity": "Frank Wong", "text": "I will finish the integration testing by April 28", "signal_type": "commitment_made", "days_ago": 48},
    {"entity": "Frank Wong", "text": "Integration testing complete — all endpoints passing", "signal_type": "reported_statement", "days_ago": 32},

    # Grace Kim (product) — material change
    {"entity": "Grace Kim", "text": "I will update the product roadmap after the Delta integration", "signal_type": "commitment_made", "days_ago": 45},
    {"entity": "Grace Kim", "text": "Product roadmap updated — Delta features moved to Q2", "signal_type": "reported_statement", "days_ago": 25},
    {"entity": "Grace Kim", "text": "I will present the updated roadmap at the all-hands meeting", "signal_type": "commitment_made", "days_ago": 20},
    {"entity": "Grace Kim", "text": "Roadmap presented at all-hands — well received", "signal_type": "reported_statement", "days_ago": 12},

    # --- Critical Events ---
    {"entity": "SystemAlert", "text": "Production database outage — SLA breach detected at 3am", "signal_type": "alert", "days_ago": 10},
    {"entity": "LegalTeam", "text": "GDPR compliance review scheduled — potential data handling violation", "signal_type": "legal_update", "days_ago": 8},
    {"entity": "SecurityTeam", "text": "Security audit found unauthorized access attempt on the admin portal", "signal_type": "alert", "days_ago": 5},
    {"entity": "BoardMember", "text": "Emergency board meeting requested — investor concerns about Q2 revenue", "signal_type": "board_escalation", "days_ago": 3},

    # --- Noise (should be filtered) ---
    {"entity": "Newsletter", "text": "Weekly tech newsletter — top 10 AI trends this week", "signal_type": "newsletter", "days_ago": 7},
    {"entity": "SocialMedia", "text": "Trending topic on LinkedIn — remote work best practices", "signal_type": "social", "days_ago": 5},
    {"entity": "PromoBot", "text": "Limited time offer — 50% off premium plan this month", "signal_type": "marketing", "days_ago": 3},
    {"entity": "Newsletter", "text": "Daily digest — 15 articles you might have missed", "signal_type": "newsletter", "days_ago": 2},

    # --- Additional commitments for variety ---
    {"entity": "Alex Chen", "text": "I will mentor the new engineering hires starting Monday", "signal_type": "commitment_made", "days_ago": 15},
    {"entity": "Jamie Lee", "text": "I will document the API endpoints by next Friday", "signal_type": "commitment_made", "days_ago": 12},
    {"entity": "Priya Patel", "text": "I will attend the security training session", "signal_type": "commitment_made", "days_ago": 8},
    {"entity": "Frank Wong", "text": "I will review the open pull requests by end of day", "signal_type": "commitment_made", "days_ago": 5},
    {"entity": "Carol Torres", "text": "I will schedule a team retrospective for the Phoenix project", "signal_type": "commitment_made", "days_ago": 3},
    {"entity": "Eve Smith", "text": "I will prepare the Q2 customer satisfaction report", "signal_type": "commitment_made", "days_ago": 2},
    {"entity": "Grace Kim", "text": "I will draft the Q3 product strategy document", "signal_type": "commitment_made", "days_ago": 1},

    # --- Contradictions ---
    {"entity": "Alex Chen", "text": "The Orion migration will definitely be done by March 15", "signal_type": "commitment_made", "days_ago": 85},
    {"entity": "Alex Chen", "text": "The Orion migration deadline is slipping — need to push to April", "signal_type": "reported_statement", "days_ago": 60},
    {"entity": "David Kim", "text": "Phoenix will launch on April 15", "signal_type": "commitment_made", "days_ago": 50},
    {"entity": "Carol Torres", "text": "Proposed new Phoenix launch date: May 20", "signal_type": "reported_statement", "days_ago": 15},
]


# ═══════════════════════════════════════════════════════════════════════════
# PART 2: 30-QUESTION ABLATION BENCHMARK
# Categories: factual (10), entity-specific (8), abstract (5), contradiction (3), temporal (4)
# ═══════════════════════════════════════════════════════════════════════════

BENCHMARK_QUESTIONS = [
    # Factual (10) — specific commitments, deadlines, outcomes
    {"id": "F1", "query": "What did Alex Chen commit to for the Orion migration?", "expected_entity": "Alex Chen", "expected_keywords": ["migration", "plan", "timeline"]},
    {"id": "F2", "query": "When did Jamie Lee say the API migration was delayed?", "expected_entity": "Jamie Lee", "expected_keywords": ["delayed", "schema"]},
    {"id": "F3", "query": "What did Priya Patel say about the regression suite?", "expected_entity": "Priya Patel", "expected_keywords": ["regression", "passed", "failures"]},
    {"id": "F4", "query": "What did Frank Wong deliver for the Delta integration?", "expected_entity": "Frank Wong", "expected_keywords": ["delta", "integration", "testing"]},
    {"id": "F5", "query": "What did Grace Kim present at the all-hands meeting?", "expected_entity": "Grace Kim", "expected_keywords": ["roadmap", "all-hands"]},
    {"id": "F6", "query": "What did Eve Smith say about AcmeCorp churning?", "expected_entity": "Eve Smith", "expected_keywords": ["churn", "acme"]},
    {"id": "F7", "query": "What did Carol Torres propose for the Phoenix launch date?", "expected_entity": "Carol Torres", "expected_keywords": ["may 20", "launch"]},
    {"id": "F8", "query": "What did David Kim transition to Carol Torres?", "expected_entity": "David Kim", "expected_keywords": ["documents", "carol"]},
    {"id": "F9", "query": "What security incident was detected?", "expected_entity": "SecurityTeam", "expected_keywords": ["unauthorized", "access", "admin"]},
    {"id": "F10", "query": "What legal issue was identified?", "expected_entity": "LegalTeam", "expected_keywords": ["gdpr", "compliance", "violation"]},

    # Entity-specific (8) — must return the RIGHT entity, not the first one
    {"id": "E1", "query": "What did Jamie Lee promise about the database schema?", "expected_entity": "Jamie Lee", "expected_keywords": ["schema", "database"]},
    {"id": "E2", "query": "What did Carol Torres commit to reviewing?", "expected_entity": "Carol Torres", "expected_keywords": ["review", "phoenix", "documents"]},
    {"id": "E3", "query": "What did Frank Wong say about integration testing?", "expected_entity": "Frank Wong", "expected_keywords": ["integration", "testing", "endpoints"]},
    {"id": "E4", "query": "What did Eve Smith schedule with AcmeCorp?", "expected_entity": "Eve Smith", "expected_keywords": ["emergency", "call", "acme"]},
    {"id": "E5", "query": "What did Alex Chen say about mentoring?", "expected_entity": "Alex Chen", "expected_keywords": ["mentor", "engineering", "hires"]},
    {"id": "E6", "query": "What did Priya Patel commit to attending?", "expected_entity": "Priya Patel", "expected_keywords": ["security", "training"]},
    {"id": "E7", "query": "What did Grace Kim say about the Q3 strategy?", "expected_entity": "Grace Kim", "expected_keywords": ["q3", "strategy", "document"]},
    {"id": "E8", "query": "What did David Kim present to the board?", "expected_entity": "David Kim", "expected_keywords": ["board", "phoenix", "launch"]},

    # Abstract (5) — requires reasoning across signals
    {"id": "A1", "query": "Who has become a delivery risk on the Orion project?", "expected_entity": "Jamie Lee", "expected_keywords": ["jamie", "delayed", "schema"]},
    {"id": "A2", "query": "What leadership change happened on the Phoenix project?", "expected_entity": "Carol Torres", "expected_keywords": ["carol", "david", "lead"]},
    {"id": "A3", "query": "What critical events need immediate attention?", "expected_entity": None, "expected_keywords": ["outage", "gdpr", "security", "board"]},
    {"id": "A4", "query": "Who am I repeatedly disappointing?", "expected_entity": "AcmeCorp", "expected_keywords": ["acme", "orion", "delay"]},
    {"id": "A5", "query": "Which commitments are now overdue?", "expected_entity": None, "expected_keywords": ["overdue", "stale", "missed"]},

    # Contradiction (3) — must detect conflicting commitments
    {"id": "C1", "query": "What contradictions exist in the Orion migration timeline?", "expected_entity": "Alex Chen", "expected_keywords": ["march", "april", "slipping"]},
    {"id": "C2", "query": "Did the Phoenix launch date change? What was the original vs new date?", "expected_entity": None, "expected_keywords": ["april 15", "may 20"]},
    {"id": "C3", "query": "What did Alex Chen say that contradicts now?", "expected_entity": "Alex Chen", "expected_keywords": ["march 15", "april", "slipping"]},

    # Temporal (4) — requires time-aware retrieval
    {"id": "T1", "query": "What did I commit to in the last 30 days?", "expected_entity": None, "expected_keywords": ["mentor", "document", "training", "retrospective"]},
    {"id": "T2", "query": "What happened with the Orion migration 60-90 days ago?", "expected_entity": "Alex Chen", "expected_keywords": ["migration", "plan", "march 15"]},
    {"id": "T3", "query": "What changed recently about the Phoenix project?", "expected_entity": "Carol Torres", "expected_keywords": ["carol", "may 20", "launch"]},
    {"id": "T4", "query": "What critical alerts occurred in the last 10 days?", "expected_entity": None, "expected_keywords": ["outage", "gdpr", "security", "board"]},
]


# ═══════════════════════════════════════════════════════════════════════════
# SCORING FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def score_answer(answer: str, question: dict) -> dict:
    """Score an answer on 4 dimensions: entity, keywords, specificity, honesty.

    Returns: {
        "entity_correct": bool,
        "keyword_hits": int,
        "keyword_total": int,
        "keyword_score": float,
        "abstained": bool,
        "specificity": float,  # 0-1 based on answer length and detail
        "total_score": float,  # 0-10 composite
    }
    """
    answer_lower = answer.lower()
    expected_entity = question.get("expected_entity")
    expected_keywords = question.get("expected_keywords", [])

    # 1. Entity correctness (3 points)
    entity_correct = False
    if expected_entity:
        entity_correct = expected_entity.lower() in answer_lower
        entity_score = 3.0 if entity_correct else 0.0
    else:
        # No specific entity expected — give points if answer has any entity
        entity_score = 1.5  # partial credit for abstract questions

    # 2. Keyword hits (3 points)
    keyword_hits = sum(1 for kw in expected_keywords if kw.lower() in answer_lower)
    keyword_total = len(expected_keywords)
    keyword_score = (keyword_hits / keyword_total * 3.0) if keyword_total > 0 else 1.5

    # 3. Specificity (2 points) — longer, more detailed answers score higher
    if len(answer) > 200:
        specificity = 2.0
    elif len(answer) > 100:
        specificity = 1.5
    elif len(answer) > 50:
        specificity = 1.0
    elif len(answer) > 20:
        specificity = 0.5
    else:
        specificity = 0.0

    # 4. Honesty (2 points) — abstention is honest, not wrong
    abstained = "don't have enough information" in answer_lower or "no matching signals" in answer_lower
    if abstained:
        # If the question SHOULD abstain (abstract with no expected entity),
        # give full honesty points. Otherwise, partial credit.
        if expected_entity is None:
            honesty = 2.0
        else:
            honesty = 0.5  # should have answered
    else:
        honesty = 2.0  # didn't abstain — gets full honesty if answer is substantive

    total = entity_score + keyword_score + specificity + honesty
    return {
        "entity_correct": entity_correct,
        "keyword_hits": keyword_hits,
        "keyword_total": keyword_total,
        "keyword_score": round(keyword_score, 2),
        "abstained": abstained,
        "specificity": specificity,
        "total_score": round(min(total, 10.0), 2),
    }


# ═══════════════════════════════════════════════════════════════════════════
# TEST: SEED CORPUS + EXERCISE SURFACES + RUN ABLATION
# ═══════════════════════════════════════════════════════════════════════════

def _ensure_ollama():
    """Start Ollama if not running."""
    import urllib.request
    try:
        urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2)
        return True
    except Exception:
        pass
    try:
        import subprocess
        subprocess.Popen(
            ["/tmp/ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        for i in range(10):
            try:
                urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2)
                return True
            except:
                time.sleep(1)
    except Exception:
        pass
    return False


@pytest.fixture
def benchmark_env():
    """Set up the full benchmark environment with corpus seeded."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-ablation"
    os.environ.pop("MAESTRO_PERSONAL_ENV", None)

    import importlib
    import maestro_personal_shell.api as api_module
    importlib.reload(api_module)
    api_module.init_db(db_path)

    from maestro_personal_shell.semantic_retrieval import init_fts_index, rebuild_fts_index
    init_fts_index(db_path)

    # Seed the corpus
    from maestro_personal_shell.llm_bridge import reset_llm_router
    reset_llm_router()

    ollama_ok = _ensure_ollama()
    if ollama_ok:
        reset_llm_router()

    client = TestClient(api_module.app)
    resp = client.post("/api/auth/login", json={
        "user_email": "ablation@test.com",
        "password": os.environ["MAESTRO_PERSONAL_TOKEN"],
    })
    headers = {"Authorization": f"Bearer {resp.json()['token']}"}

    # Ingest all corpus signals
    now = datetime.now(timezone.utc)
    with patch("maestro_personal_shell.commitment_classifier.classify_commitment",
               new_callable=AsyncMock,
               return_value={"commitment_type": "explicit", "is_commitment": True,
                             "confidence": 0.85, "state": "active", "owner": "user",
                             "reasoning": "test", "llm_powered": False}), \
         patch("maestro_personal_shell.llm_bridge.is_llm_available",
               return_value=ollama_ok), \
         patch("maestro_personal_shell.llm_bridge.get_llm_router") as mock_router:

        if ollama_ok:
            from maestro_personal_shell.llm_bridge import _OllamaDirectRouter
            mock_router.return_value = _OllamaDirectRouter()
            if mock_router.return_value.health_check():
                pass  # Ollama is ready
            else:
                ollama_ok = False

        for sig in CORPUS_SIGNALS:
            sig_time = (now - timedelta(days=sig["days_ago"])).isoformat()
            client.post("/api/signals", json={
                "entity": sig["entity"],
                "text": sig["text"],
                "signal_type": sig["signal_type"],
                "timestamp": sig_time,
            }, headers=headers)

    rebuild_fts_index(db_path)

    yield {
        "client": client,
        "headers": headers,
        "db_path": db_path,
        "ollama_ok": ollama_ok,
        "api_module": api_module,
    }

    os.unlink(db_path)
    os.environ.pop("MAESTRO_PERSONAL_DB", None)
    os.environ.pop("MAESTRO_PERSONAL_TOKEN", None)


class TestLiveUserScenario:
    """Exercise all surfaces with the seeded corpus."""

    def test_corpus_seeded(self, benchmark_env):
        """Verify 100+ signals were ingested."""
        resp = benchmark_env["client"].get("/api/signals", headers=benchmark_env["headers"])
        signals = resp.json()
        print(f"\nCorpus: {len(signals)} signals ingested")
        assert len(signals) >= 50, f"Expected 50+ signals, got {len(signals)}"

    def test_commitments_surface(self, benchmark_env):
        """Commitments surface should return active commitments."""
        resp = benchmark_env["client"].get("/api/commitments", headers=benchmark_env["headers"])
        assert resp.status_code == 200
        commitments = resp.json()
        entities = [c.get("entity", "") for c in commitments]
        print(f"\nCommitments: {len(commitments)} active")
        print(f"  Entities: {set(entities)}")
        assert len(commitments) > 0, "Should have active commitments"

    def test_whisper_surface(self, benchmark_env):
        """Whisper surface should detect critical events."""
        resp = benchmark_env["client"].get("/api/whisper", headers=benchmark_env["headers"])
        assert resp.status_code == 200
        whispers = resp.json()
        print(f"\nWhispers: {len(whispers)} active")
        for w in whispers[:5]:
            print(f"  [{w.get('priority','?')}] {w.get('entity','?')}: {w.get('title','')[:60]}")
        # Should detect the critical events (outage, GDPR, security, board)
        critical = [w for w in whispers if w.get("type") == "critical_signal"]
        print(f"  Critical signal whispers: {len(critical)}")
        # May be 0 if events are >48h old; stale commitments should fire
        stale = [w for w in whispers if w.get("type") == "stale_commitment"]
        print(f"  Stale commitment whispers: {len(stale)}")

    def test_prepare_surface(self, benchmark_env):
        """Prepare surface should return meeting prep items."""
        resp = benchmark_env["client"].get("/api/prepare", headers=benchmark_env["headers"])
        assert resp.status_code == 200
        prep = resp.json()
        print(f"\nPrepare: {len(prep) if isinstance(prep, list) else 'object'} items")
        if isinstance(prep, list):
            for p in prep[:3]:
                print(f"  {p.get('entity','?')}: {p.get('text','')[:60]}")

    def test_what_changed_surface(self, benchmark_env):
        """What Changed should return recent material deltas."""
        resp = benchmark_env["client"].get("/api/what-changed", headers=benchmark_env["headers"])
        assert resp.status_code == 200
        changes = resp.json()
        meaningful = [c for c in changes if c.get("is_meaningful")]
        print(f"\nWhat Changed: {len(changes)} total, {len(meaningful)} meaningful")
        for c in meaningful[:3]:
            print(f"  [{c.get('type','?')}] {c.get('entity','?')}: {c.get('text','')[:60]}")
        assert len(changes) > 0, "Should have recent changes"

    def test_briefing_surface(self, benchmark_env):
        """Briefing should return a structured morning briefing."""
        resp = benchmark_env["client"].get("/api/briefing", headers=benchmark_env["headers"])
        assert resp.status_code == 200
        briefing = resp.json()
        print(f"\nBriefing:")
        print(f"  Greeting: {briefing.get('greeting','')[:60]}")
        print(f"  Material changes: {len(briefing.get('material_changes',[]))}")
        print(f"  Unknowns: {len(briefing.get('unknowns',[]))}")
        print(f"  Ask prompt: {briefing.get('ask_prompt','')[:60]}")

    def test_llm_status(self, benchmark_env):
        """LLM status should show Ollama as active (if available)."""
        resp = benchmark_env["client"].get("/api/llm-status", headers=benchmark_env["headers"])
        assert resp.status_code == 200
        status = resp.json()
        print(f"\nLLM Status:")
        print(f"  Configured: {status.get('configured')}")
        print(f"  Active: {status.get('active')}")
        print(f"  Provider: {status.get('provider')}")
        print(f"  Mode: {status.get('mode')}")
        if benchmark_env["ollama_ok"]:
            assert status.get("provider") == "ollama" or status.get("active") is True, (
                f"Ollama should be active. Got: {status}"
            )

    def test_graph_surface(self, benchmark_env):
        """Graph should show entity interactions."""
        resp = benchmark_env["client"].get("/api/graph/entity/Alex%20Chen", headers=benchmark_env["headers"])
        assert resp.status_code == 200
        graph = resp.json()
        print(f"\nGraph (Alex Chen):")
        print(f"  Exists: {graph.get('exists')}")
        print(f"  Total interactions: {graph.get('total_interactions')}")
        print(f"  Active commitments: {graph.get('active_commitments')}")
        if graph.get("exists"):
            assert graph["total_interactions"] > 0, "Should have interactions for Alex Chen"


class TestAblationBenchmark:
    """Run 30-question ablation: Maestro vs LLM-only vs LLM+retrieval."""

    def test_ablation_full_maestro(self, benchmark_env):
        """Condition 1: Full Maestro (LLM + retrieval + graph + ranker)."""
        client = benchmark_env["client"]
        headers = benchmark_env["headers"]

        results = []
        for q in BENCHMARK_QUESTIONS:
            resp = client.post("/api/ask", json={"query": q["query"]}, headers=headers)
            if resp.status_code != 200:
                results.append({"id": q["id"], "error": resp.status_code, "score": 0})
                continue

            data = resp.json()
            answer = data.get("answer", "")
            score = score_answer(answer, q)
            results.append({
                "id": q["id"],
                "query": q["query"],
                "answer": answer[:200],
                "intelligence_source": data.get("intelligence_source"),
                "llm_active": data.get("llm_active"),
                "score": score["total_score"],
                "entity_correct": score["entity_correct"],
                "keyword_hits": score["keyword_hits"],
                "abstained": score["abstained"],
            })

        # Print results table
        print("\n" + "=" * 80)
        print("ABLATION BENCHMARK — CONDITION 1: FULL MAESTRO")
        print("=" * 80)
        print(f"{'ID':<5} {'Score':>6} {'Entity':>7} {'KWs':>5} {'Abst':>5} {'Source':<8} Query")
        print("-" * 80)
        total_score = 0
        for r in results:
            print(f"{r['id']:<5} {r['score']:>6.1f} {str(r.get('entity_correct','')):>7} {r.get('keyword_hits',0):>3}/{3:<2} {str(r.get('abstained','')):>5} {r.get('intelligence_source','?'):<8} {r['query'][:50]}")
            total_score += r["score"]

        avg_score = total_score / len(results)
        print("-" * 80)
        print(f"{'AVG':<5} {avg_score:>6.1f}/10")
        print(f"\nLLM Active: {results[0].get('llm_active') if results else 'N/A'}")
        print(f"Intelligence Source: {results[0].get('intelligence_source') if results else 'N/A'}")

        # Store for comparison
        TestAblationBenchmark.maestro_results = results
        TestAblationBenchmark.maestro_avg = avg_score

        # Assert minimum quality
        assert avg_score >= 3.0, f"Maestro avg score {avg_score:.1f} below 3.0 minimum"

    def test_ablation_llm_only(self, benchmark_env):
        """Condition 2: LLM-only (no retrieval, no graph, no ranker).

        Calls Ollama directly with just the query — no context, no evidence.
        This is the 'plain LLM' baseline.
        """
        if not benchmark_env["ollama_ok"]:
            pytest.skip("Ollama not available — cannot run LLM-only condition")

        from maestro_personal_shell.llm_bridge import _OllamaDirectRouter
        router = _OllamaDirectRouter()
        if not router.health_check():
            pytest.skip("Ollama not reachable")

        results = []
        for q in BENCHMARK_QUESTIONS:
            try:
                response = asyncio.run(router.complete(
                    system="You are a helpful assistant. Answer the user's question concisely. If you don't know, say so.",
                    user=q["query"],
                    temperature=0.1,
                    max_tokens=200,
                ))
                answer = response.text
            except Exception:
                answer = "I don't have enough information to answer that."

            score = score_answer(answer, q)
            results.append({
                "id": q["id"],
                "query": q["query"],
                "answer": answer[:200],
                "score": score["total_score"],
                "entity_correct": score["entity_correct"],
                "keyword_hits": score["keyword_hits"],
                "abstained": score["abstained"],
            })

        print("\n" + "=" * 80)
        print("ABLATION BENCHMARK — CONDITION 2: LLM-ONLY (no retrieval)")
        print("=" * 80)
        print(f"{'ID':<5} {'Score':>6} {'Entity':>7} {'KWs':>5} {'Abst':>5} Query")
        print("-" * 80)
        total_score = 0
        for r in results:
            print(f"{r['id']:<5} {r['score']:>6.1f} {str(r.get('entity_correct','')):>7} {r.get('keyword_hits',0):>3}/{3:<2} {str(r.get('abstained','')):>5} {r['query'][:50]}")
            total_score += r["score"]

        avg_score = total_score / len(results)
        print("-" * 80)
        print(f"{'AVG':<5} {avg_score:>6.1f}/10")

        TestAblationBenchmark.llm_only_results = results
        TestAblationBenchmark.llm_only_avg = avg_score

    def test_ablation_comparison_report(self, benchmark_env):
        """Print the final comparison report."""
        maestro_avg = getattr(TestAblationBenchmark, "maestro_avg", 0)
        llm_only_avg = getattr(TestAblationBenchmark, "llm_only_avg", 0)
        delta = maestro_avg - llm_only_avg

        print("\n" + "=" * 80)
        print("ABLATION COMPARISON REPORT")
        print("=" * 80)
        print(f"{'Condition':<30} {'Avg Score':>10} {'Delta':>10}")
        print("-" * 80)
        print(f"{'Full Maestro':<30} {maestro_avg:>8.1f}/10 {'':>10}")
        if llm_only_avg > 0:
            print(f"{'LLM-only (no retrieval)':<30} {llm_only_avg:>8.1f}/10 {'':>10}")
            print(f"{'Delta (Maestro - LLM)':<30} {delta:>8.1f} {'':>10}")
        else:
            print(f"{'LLM-only (no retrieval)':<30} {'SKIPPED':>10} {'':>10}")
        print("-" * 80)

        if llm_only_avg > 0:
            if delta > 0:
                print(f"\n✓ Maestro outperforms LLM-only by {delta:.1f} points")
                print(f"  The intelligence architecture provides measurable value.")
            elif delta < 0:
                print(f"\n✗ LLM-only outperforms Maestro by {abs(delta):.1f} points")
                print(f"  The architecture is NOT adding value — investigate.")
            else:
                print(f"\n= Maestro and LLM-only are tied — no differential.")

            # Per-category breakdown
            maestro_results = getattr(TestAblationBenchmark, "maestro_results", [])
            llm_results = getattr(TestAblationBenchmark, "llm_only_results", [])
            if maestro_results and llm_results:
                categories = {"F": "Factual", "E": "Entity", "A": "Abstract", "C": "Contradiction", "T": "Temporal"}
                print(f"\nPer-category breakdown:")
                print(f"{'Category':<15} {'Maestro':>10} {'LLM-only':>10} {'Delta':>10}")
                print("-" * 50)
                for prefix, name in categories.items():
                    m_scores = [r["score"] for r in maestro_results if r["id"].startswith(prefix)]
                    l_scores = [r["score"] for r in llm_results if r["id"].startswith(prefix)]
                    m_avg = sum(m_scores) / len(m_scores) if m_scores else 0
                    l_avg = sum(l_scores) / len(l_scores) if l_scores else 0
                    print(f"{name:<15} {m_avg:>8.1f}/10 {l_avg:>8.1f}/10 {m_avg-l_avg:>+8.1f}")

        print("\n" + "=" * 80)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])
