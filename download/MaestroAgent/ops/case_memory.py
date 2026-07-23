"""Case Memory — FTS5-backed incident knowledge base.

The swarm's memory of past incidents. Starts as FTS5 over a ticket/case
table (symptom, root_cause, fix, outcome). On intake, FTS-match the new
symptom against past cases; high match → propose the known fix.

Seeded from the audit arc's real incidents — the swarm starts with
dozens of cases on day one instead of a cold start.

Graduates to vector+graph (maestro_memory) only after FTS proves the
pattern earns it.
"""
from __future__ import annotations

import json
import sqlite3
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parents[1] / "ops" / "case_memory.db"


@dataclass
class Case:
    """A single incident case — the swarm's memory unit."""
    id: str
    symptom: str  # what was observed
    root_cause: str  # why it happened
    fix: str  # what was done to fix it
    outcome: str  # "resolved" | "mitigated" | "escalated"
    autonomy_level: int = 1
    governance_verdict: str = "ALLOW"  # was the fix governance-approved?
    lesson: str = ""  # the crystallized lesson
    runbook: str = ""  # if this fix has been crystallized into a script
    created_at: str = ""
    tags: list[str] = field(default_factory=list)


# ── Seeded cases from the audit arc ─────────────────────────────────────────

SEEDED_CASES = [
    Case(
        id="AUDIT-001",
        symptom="Backend deploy stall — live commit d3b7ccf behind HEAD by 10+ commits for 7+ hours. Railway shows SUCCESS but image digest unchanged.",
        root_cause="Backend Railway service (MaestroAgent, c12adfcf) has ZERO repo triggers. Railway's GitHub App is installed but not authorized on the repo, so pushes don't trigger rebuilds and serviceInstanceDeploy reuses the cached image.",
        fix="Route around the Railway GitHub App entirely. Deploy from GitHub Actions (first-party to the repo) using `railway up --service $SERVICE_ID --detach` with RAILWAY_API_TOKEN. Add S0 health assertion: poll /api/health until commit == github.sha.",
        outcome="resolved",
        autonomy_level=1,
        governance_verdict="ALLOW",
        lesson="The Railway GitHub App path is a dead end (browser OAuth, can't be API-automated by design). GitHub Actions is first-party and already runs CI on push — use it as the deployer. Health is the source of truth, not Railway's SUCCESS status.",
        runbook="deploy_ops.ensure_deployed() → trigger deploy.yml via workflow_dispatch → poll /api/health",
        tags=["deploy", "railway", "drift", "s0"],
    ),
    Case(
        id="AUDIT-002",
        symptom="isolation_rate computed as 86.67% — David x2 tests counted as isolation failures but they return the correct entity (David Kim), only failing on the 'tentative' wording assertion.",
        root_cause="Scorer used r['pass'] (overall test pass/fail) to compute isolation_rate, conflating wording failures with isolation failures. The isolation assertion and the wording assertion are different checks, but the aggregate used the overall result.",
        fix="Add per-test isolation_assertion field (pass/fail/na). Compute isolation_rate from the field, not from overall pass. Count isolation across ALL categories (not just entity_specific).",
        outcome="resolved",
        autonomy_level=2,
        governance_verdict="ALLOW",
        lesson="A metric must measure what it claims to measure. If the aggregate uses the wrong signal, it mislabels failures. Widening inspection from one category to all revealed 98.86% (more honest) instead of 100% (narrow). The trustworthy direction is DOWN when you find the metric was too generous.",
        runbook="",
        tags=["scorer", "isolation", "metric-gaming", "benchmark"],
    ),
    Case(
        id="AUDIT-003",
        symptom="_fix_source_types spray caused UnboundLocalError on abstention paths — evidence_refs was undefined on early-return paths, crashing the request and dropping safety to 0%.",
        root_cause="The fix was inserted before all 12 return AskResponse statements, including early-return abstention paths where evidence_refs was never defined. Accessing an undefined variable raises UnboundLocalError.",
        fix="Delete the spray. Add ONE fix at the final return only, where evidence_refs is guaranteed to be defined. Set source_type at evidence_ref construction time, not post-hoc relabel.",
        outcome="resolved",
        autonomy_level=2,
        governance_verdict="ALLOW",
        lesson="Never spray a fix before all return paths. When touching multiple returns, verify the variable is defined on ALL paths — including early returns, error paths, and abstention paths. Test the abstention path explicitly.",
        runbook="",
        tags=["safety", "unboundlocalerror", "spray-fix", "abstention"],
    ),
    Case(
        id="AUDIT-004",
        symptom="Connect button showed optimistic toast 'Connected!' before the server confirmed the connection. User saw success but the connector wasn't actually connected.",
        root_cause="handleConnect in Connectors.tsx showed a success toast immediately, without waiting for the server's confirmation. This is the optimistic-toast pattern — claiming success before verification.",
        fix="handleConnect opens Google OAuth popup → popup polls for close → re-fetch GET /api/connectors → toast only on server-confirmed connected: true.",
        outcome="resolved",
        autonomy_level=2,
        governance_verdict="ALLOW",
        lesson="Never claim success before the server confirms it. The optimistic-toast pattern is the root anti-pattern this audit exists to prevent — it applies to UI toasts, benchmark metrics, deploy claims, and any state assertion. Verify, then report.",
        runbook="",
        tags=["optimistic-toast", "ui", "verification", "connectors"],
    ),
    Case(
        id="AUDIT-005",
        symptom="Correction endpoint existed and recorded metadata['correction'], but dismissed signals still surfaced in Ask evidence via specialist retrievers.",
        root_cause="BM25/FTS retriever and Commitments router filtered dismissed signals, but _load_all_signals (used by specialist retrievers) and Shell.filter_evidence did NOT filter them. Correction was partially write-only.",
        fix="Add dismissed-signal filter to _load_all_signals (checks metadata.status and metadata.correction). Add the same filter to Shell.filter_evidence after the EpistemicBarrier — last line of defense before the LLM.",
        outcome="resolved",
        autonomy_level=2,
        governance_verdict="ALLOW",
        lesson="Never accept 'exists' for 'works.' Trace the full data flow: does the correction actually propagate downstream? Does it change behavior? The endpoint existing is necessary but not sufficient. Trace before fix; verify the full loop after.",
        runbook="correction_roundtrip_test.py — correct a signal → re-ask → confirm excluded",
        tags=["correction", "write-only", "trust", "retrieval"],
    ),
    Case(
        id="AUDIT-006",
        symptom="'Alex's thing — what did I promise?' returned Maria Garcia instead of Alex Chen. The wrong entity was cited in the answer.",
        root_cause="top_entity was set from real_evidence[0] — the highest-RANKED evidence, which was Maria's. The entity was effectively chosen by BM25 ranking, not by the query's possessive. This made it stochastic (different evidence order → different entity).",
        fix="Deterministic possessive entity resolution at the routing layer. resolve_possessive_to_canonical extracts 'Alex' from 'Alex's thing', resolves to 'Alex Chen' against known entities, then filter_evidence_to_entity removes all non-Alex evidence before top_entity is set.",
        outcome="resolved",
        autonomy_level=2,
        governance_verdict="ALLOW",
        lesson="LLM nondeterminism in entity resolution is a trust-killer. Resolve entities deterministically at the routing layer BEFORE the LLM synthesizes, so the answer's entity can't depend on the model's stochastic choice. This retires the product leak, the CI flakiness, and the consistency-trust gap in one move.",
        runbook="possessive_resolution_test.py — extract → resolve → filter → verify determinism",
        tags=["entity-resolution", "possessive", "determinism", "ci-flakiness", "consistency"],
    ),
    Case(
        id="AUDIT-007",
        symptom="Frontend returned 'Loading…' on SSR — the page was a client component that rendered nothing until JS hydrated. Users saw a blank shell.",
        root_cause="page.tsx was 'use client' and returned a loading div until mounted=true. The server sent only the loading shell, so the first paint was blank.",
        fix="Restructure: page.tsx is a server component rendering <AppShell/>. AppShell renders ShellSkeleton (branded shell with nav + animate-pulse) on server + first client render, then swaps to real content after mount. Same markup → no hydration mismatch.",
        outcome="resolved",
        autonomy_level=2,
        governance_verdict="ALLOW",
        lesson="For client-rendered content, a non-JS HTTP fetch only sees the pre-hydration shell. To verify what a user sees, use a JS-executing instrument (real browser or headless). The SSR skeleton still has value for crawlers/slow-first-paint, but it's not what a real user experiences.",
        runbook="",
        tags=["ssr", "frontend", "hydration", "first-paint"],
    ),
    Case(
        id="AUDIT-008",
        symptom="Live-claim made that SSR was 'live' based on a local build artifact, but external auditor's fresh fetch showed Loading…. Second time a live-claim failed independent verification.",
        root_cause="The claim was made from a local build artifact (.next/standalone/.../index.html) which is a BUILD OUTPUT, not the deployed page. The claim was carried forward without a fresh fetch of the actual public endpoint.",
        fix="Adopt the live-claim rule: no statement that something is 'live' is accepted unless verified by a fresh, independent fetch at the moment the claim is made. For client-rendered content, use a JS-executing instrument.",
        outcome="resolved",
        autonomy_level=3,
        governance_verdict="ESCALATE",
        lesson="Claims about live state need to be checked by hitting the live thing at the moment they're made, not carried forward from an earlier check. A local build artifact is not the live site. Two contradictory fetches need instrument diagnosis, not guesswork.",
        runbook="",
        tags=["live-claim", "verification", "instrument", "governance"],
    ),
]


class CaseMemory:
    """FTS5-backed case memory for the ops swarm."""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self._init_db()
        self._seed_if_empty()

    def _init_db(self):
        """Initialize the cases table + FTS5 index."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cases (
                    id TEXT PRIMARY KEY,
                    symptom TEXT NOT NULL,
                    root_cause TEXT NOT NULL,
                    fix TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    autonomy_level INTEGER DEFAULT 1,
                    governance_verdict TEXT DEFAULT 'ALLOW',
                    lesson TEXT DEFAULT '',
                    runbook TEXT DEFAULT '',
                    created_at TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]'
                )
            """)
            # FTS5 index over symptom + root_cause (the searchable fields)
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS cases_fts USING fts5(
                    id UNINDEXED,
                    symptom,
                    root_cause,
                    content='cases',
                    content_rowid='rowid'
                )
            """)
            # Triggers to keep FTS in sync
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS cases_ai AFTER INSERT ON cases BEGIN
                    INSERT INTO cases_fts(id, symptom, root_cause)
                    VALUES (new.id, new.symptom, new.root_cause);
                END
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS cases_ad AFTER DELETE ON cases BEGIN
                    INSERT INTO cases_fts(cases_fts, id, symptom, root_cause)
                    VALUES ('delete', old.id, old.symptom, old.root_cause);
                END
            """)
            conn.commit()
        finally:
            conn.close()

    def _seed_if_empty(self):
        """Seed the case memory from the audit arc if it's empty."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            count = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
            if count == 0:
                for case in SEEDED_CASES:
                    self._insert_case(conn, case)
                conn.commit()
                logger.info(f"Seeded case memory with {len(SEEDED_CASES)} audit cases")
        finally:
            conn.close()

    def _insert_case(self, conn: sqlite3.Connection, case: Case):
        conn.execute(
            """INSERT OR REPLACE INTO cases
               (id, symptom, root_cause, fix, outcome, autonomy_level,
                governance_verdict, lesson, runbook, created_at, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                case.id, case.symptom, case.root_cause, case.fix, case.outcome,
                case.autonomy_level, case.governance_verdict, case.lesson,
                case.runbook, case.created_at or datetime.now(timezone.utc).isoformat(),
                json.dumps(case.tags),
            ),
        )

    def add_case(self, case: Case):
        """Add a new case to memory."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            self._insert_case(conn, case)
            conn.commit()
        finally:
            conn.close()

    def search(self, query: str, limit: int = 5) -> list[Case]:
        """FTS5 search for cases matching the query. Returns ranked matches."""
        if not query.strip():
            return []
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            # Build FTS5 query — use OR between terms for broader recall
            # Sanitize: remove special chars, wrap each term in quotes
            terms = [t.strip().lower() for t in query.split() if t.strip() and t.isalnum()]
            if not terms:
                # Fall back to LIKE if no alphanumeric terms
                rows = conn.execute(
                    """SELECT * FROM cases
                       WHERE symptom LIKE ? OR root_cause LIKE ?
                       LIMIT ?""",
                    (f"%{query}%", f"%{query}%", limit),
                ).fetchall()
                return [self._row_to_case(r) for r in rows]
            # Use OR query for recall (any term matches)
            fts_query = " OR ".join(terms)
            rows = conn.execute(
                """SELECT c.*, bm25(cases_fts) as rank
                   FROM cases_fts
                   JOIN cases c ON cases_fts.id = c.id
                   WHERE cases_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (fts_query, limit),
            ).fetchall()
            return [self._row_to_case(r) for r in rows]
        except sqlite3.OperationalError:
            # FTS syntax error — fall back to LIKE
            rows = conn.execute(
                """SELECT * FROM cases
                   WHERE symptom LIKE ? OR root_cause LIKE ?
                   LIMIT ?""",
                (f"%{query}%", f"%{query}%", limit),
            ).fetchall()
            return [self._row_to_case(r) for r in rows]
        finally:
            conn.close()

    def _row_to_case(self, row: sqlite3.Row) -> Case:
        return Case(
            id=row["id"],
            symptom=row["symptom"],
            root_cause=row["root_cause"],
            fix=row["fix"],
            outcome=row["outcome"],
            autonomy_level=row["autonomy_level"],
            governance_verdict=row["governance_verdict"],
            lesson=row["lesson"],
            runbook=row["runbook"],
            created_at=row["created_at"],
            tags=json.loads(row["tags"]) if row["tags"] else [],
        )

    def get_all_cases(self) -> list[Case]:
        """Get all cases (for inspection/debugging)."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT * FROM cases ORDER BY created_at DESC").fetchall()
            return [self._row_to_case(r) for r in rows]
        finally:
            conn.close()


# ── Self-test ───────────────────────────────────────────────────────────────

def run_self_test() -> bool:
    """Verify case memory works: seeded cases present + FTS search returns matches."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        db = Path(tmpdir) / "test_cases.db"
        memory = CaseMemory(db_path=db)

        # Check seeding
        cases = memory.get_all_cases()
        print(f"Seeded cases: {len(cases)}")
        for c in cases[:3]:
            print(f"  [{c.id}] {c.symptom[:60]}...")

        if len(cases) != len(SEEDED_CASES):
            print(f"✗ Expected {len(SEEDED_CASES)} seeded cases, got {len(cases)}")
            return False

        # Test FTS search — "deploy stall" should match AUDIT-001
        results = memory.search("deploy stall backend behind")
        print(f"\nSearch 'deploy stall backend behind': {len(results)} results")
        if results:
            print(f"  Top match: [{results[0].id}] {results[0].symptom[:60]}...")
            if results[0].id != "AUDIT-001":
                print(f"✗ Expected AUDIT-001, got {results[0].id}")
                return False
        else:
            print("✗ No results for deploy stall search")
            return False

        # Test FTS search — "isolation" should match AUDIT-002
        results = memory.search("isolation metric scorer")
        print(f"\nSearch 'isolation metric scorer': {len(results)} results")
        if results:
            print(f"  Top match: [{results[0].id}] {results[0].symptom[:60]}...")
            if results[0].id != "AUDIT-002":
                print(f"✗ Expected AUDIT-002, got {results[0].id}")
                return False
        else:
            print("✗ No results for isolation search")
            return False

        # Test FTS search — "optimistic toast" should match AUDIT-004
        results = memory.search("optimistic toast connected")
        print(f"\nSearch 'optimistic toast connected': {len(results)} results")
        if results:
            print(f"  Top match: [{results[0].id}] {results[0].symptom[:60]}...")
            if results[0].id != "AUDIT-004":
                print(f"✗ Expected AUDIT-004, got {results[0].id}")
                return False
        else:
            print("✗ No results for optimistic toast search")
            return False

        print("\n✓ ALL CASE MEMORY TESTS PASS")
        return True


if __name__ == "__main__":
    import sys
    sys.exit(0 if run_self_test() else 1)
