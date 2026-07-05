"""
Instrumentation for the 90-day pilot.

Three lightweight instrumentation surfaces that prepare the ground for the
advisor's vision (Principles, Genome, Gravity, Fragility) WITHOUT building
those capabilities prematurely. The advisor's directive: "instrument the
system so that, after 90 days, you can derive Principles, Genome, Gravity,
and Fragility from customer data."

1. SnapshotStore — weekly snapshot of learning-loop metrics
   Records: prediction count, resolution rate, Brier score, calibration
   error, hypothesis accuracy, assumption validation rate.
   Answers: "does it get smarter every week?"

2. DecisionLog — append-only log of approved/rejected Prepared Decisions
   Records: preparation_id, intent_id, decision (approved/rejected),
   decided_by, linked assumptions, linked hypotheses, linked evidence,
   confidence at decision time, outcome (filled in later).
   After 90 days, this log is the raw material for the Principle
   extraction engine.

3. CapabilityImpactQuery — "what would collapse if person X disappeared?"
   Cascades: person → domains orphaned → laws that lose evidence →
   recommendations that weaken. This is the data the Gravity UI will
   eventually surface. We capture the query now; we build the UI later.

All three follow the CheckpointStore pattern: SQLite/Postgres via the
sqlite_compat shim, single RLock, _cursor() context manager, WAL mode.
The data lands in the learning DB (MAESTRO_LEARNING_DB) alongside the
existing predictions, feedback_events, and calibration_history tables.
"""

from __future__ import annotations

import json
import logging
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from maestro_db import sqlite_compat as sqlite3
from maestro_db.sqlite_compat import safe_pragma

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# SCHEMA
# ═══════════════════════════════════════════════════════════════════════════

_SCHEMA = """
CREATE TABLE IF NOT EXISTS weekly_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_at TEXT NOT NULL,
    week_label TEXT NOT NULL,
    signals_processed INTEGER DEFAULT 0,
    learning_objects INTEGER DEFAULT 0,
    laws_inferred INTEGER DEFAULT 0,
    validated_laws INTEGER DEFAULT 0,
    recommendations_active INTEGER DEFAULT 0,
    predictions_total INTEGER DEFAULT 0,
    predictions_resolved INTEGER DEFAULT 0,
    predictions_pending INTEGER DEFAULT 0,
    predictions_correct INTEGER DEFAULT 0,
    predictions_incorrect INTEGER DEFAULT 0,
    resolution_rate REAL DEFAULT 0,
    accuracy_rate REAL DEFAULT 0,
    brier_score REAL DEFAULT 0,
    calibration_error REAL DEFAULT 0,
    is_well_calibrated INTEGER DEFAULT 0,
    is_learning INTEGER DEFAULT 0,
    hidden_experts_count INTEGER DEFAULT 0,
    concentration_risks_count INTEGER DEFAULT 0,
    intents_count INTEGER DEFAULT 0,
    hypotheses_count INTEGER DEFAULT 0,
    assumptions_count INTEGER DEFAULT 0,
    assumptions_validated INTEGER DEFAULT 0,
    assumptions_invalidated INTEGER DEFAULT 0,
    assumptions_open INTEGER DEFAULT 0,
    contradictions_count INTEGER DEFAULT 0,
    preparations_count INTEGER DEFAULT 0,
    preparations_approved INTEGER DEFAULT 0,
    metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS decision_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    logged_at TEXT NOT NULL,
    preparation_id TEXT NOT NULL,
    preparation_type TEXT DEFAULT '',
    title TEXT DEFAULT '',
    decision TEXT NOT NULL,
    decided_by TEXT DEFAULT '',
    intent_id TEXT DEFAULT '',
    linked_assumption_ids TEXT DEFAULT '[]',
    linked_hypothesis_ids TEXT DEFAULT '[]',
    linked_evidence_count INTEGER DEFAULT 0,
    confidence_at_decision REAL DEFAULT 0,
    outcome TEXT DEFAULT '',
    outcome_notes TEXT DEFAULT '',
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_weekly_snapshots_at ON weekly_snapshots(snapshot_at);
CREATE INDEX IF NOT EXISTS idx_weekly_snapshots_week ON weekly_snapshots(week_label);
CREATE INDEX IF NOT EXISTS idx_decision_log_at ON decision_log(logged_at);
CREATE INDEX IF NOT EXISTS idx_decision_log_intent ON decision_log(intent_id);
CREATE INDEX IF NOT EXISTS idx_decision_log_decision ON decision_log(decision);
"""


# ═══════════════════════════════════════════════════════════════════════════
# SNAPSHOT STORE — "does it get smarter every week?"
# ═══════════════════════════════════════════════════════════════════════════

class SnapshotStore:
    """Weekly snapshot of learning-loop metrics.

    One row per week (or per startup, whichever comes first). The advisor's
    "does it get smarter every week?" chart reads from this table.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._connect()

    def _connect(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        is_memory = self.db_path == ":memory:"
        self._conn = sqlite3.connect(
            self.db_path if not is_memory else "file::memory:?cache=shared",
            uri=is_memory,
            check_same_thread=False,
            isolation_level=None,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        # C1 fix: PRAGMA is SQLite-specific. Guard for Postgres compatibility.
        safe_pragma(self._conn, self.db_path, "PRAGMA journal_mode=WAL")

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        assert self._conn is not None
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute("BEGIN")
                yield cur
                cur.execute("COMMIT")
            except Exception:
                cur.execute("ROLLBACK")
                raise

    def record_snapshot(self, metrics: dict[str, Any]) -> dict[str, Any]:
        """Insert a weekly snapshot row.

        Args:
            metrics: dict with keys matching the weekly_snapshots columns.
                At minimum: signals_processed, predictions_total, brier_score.

        Returns:
            The stored snapshot dict (with snapshot_at and week_label).
        """
        now = datetime.now(timezone.utc)
        week_label = self._week_label(now)

        row = {
            "snapshot_at": now.isoformat(),
            "week_label": week_label,
            "signals_processed": metrics.get("signals_processed", 0),
            "learning_objects": metrics.get("learning_objects", 0),
            "laws_inferred": metrics.get("laws_inferred", 0),
            "validated_laws": metrics.get("validated_laws", 0),
            "recommendations_active": metrics.get("recommendations_active", 0),
            "predictions_total": metrics.get("predictions_total", 0),
            "predictions_resolved": metrics.get("predictions_resolved", 0),
            "predictions_pending": metrics.get("predictions_pending", 0),
            "predictions_correct": metrics.get("predictions_correct", 0),
            "predictions_incorrect": metrics.get("predictions_incorrect", 0),
            "resolution_rate": metrics.get("resolution_rate", 0.0),
            "accuracy_rate": metrics.get("accuracy_rate", 0.0),
            "brier_score": metrics.get("brier_score", 0.0),
            "calibration_error": metrics.get("calibration_error", 0.0),
            "is_well_calibrated": 1 if metrics.get("is_well_calibrated") else 0,
            "is_learning": 1 if metrics.get("is_learning") else 0,
            "hidden_experts_count": metrics.get("hidden_experts_count", 0),
            "concentration_risks_count": metrics.get("concentration_risks_count", 0),
            "intents_count": metrics.get("intents_count", 0),
            "hypotheses_count": metrics.get("hypotheses_count", 0),
            "assumptions_count": metrics.get("assumptions_count", 0),
            "assumptions_validated": metrics.get("assumptions_validated", 0),
            "assumptions_invalidated": metrics.get("assumptions_invalidated", 0),
            "assumptions_open": metrics.get("assumptions_open", 0),
            "contradictions_count": metrics.get("contradictions_count", 0),
            "preparations_count": metrics.get("preparations_count", 0),
            "preparations_approved": metrics.get("preparations_approved", 0),
            "metadata_json": json.dumps(metrics.get("metadata", {})),
        }

        cols = ", ".join(row.keys())
        placeholders = ", ".join(["?"] * len(row))
        with self._cursor() as cur:
            cur.execute(
                f"INSERT INTO weekly_snapshots ({cols}) VALUES ({placeholders})",
                tuple(row.values()),
            )

        logger.info("Weekly snapshot recorded: %s (brier=%.4f, predictions=%d)",
                     week_label, row["brier_score"], row["predictions_total"])
        return row

    def list_snapshots(self, limit: int = 52) -> list[dict[str, Any]]:
        """List snapshots, most recent first. Default: last 52 weeks."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM weekly_snapshots ORDER BY snapshot_at DESC LIMIT ?",
                (limit,),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def get_latest(self) -> dict[str, Any] | None:
        """Get the most recent snapshot, or None if none exist."""
        rows = self.list_snapshots(limit=1)
        return rows[0] if rows else None

    def _week_label(self, dt: datetime) -> str:
        """ISO week label, e.g. '2026-W27'."""
        iso_year, iso_week, _ = dt.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"


# ═══════════════════════════════════════════════════════════════════════════
# DECISION LOG — raw material for the Principle extraction engine
# ═══════════════════════════════════════════════════════════════════════════

class DecisionLog:
    """Append-only log of approved/rejected Prepared Decisions.

    Every approve/reject writes a row. After 90 days, this log is the raw
    material for the Principle extraction engine — "what did we decide,
    what were our assumptions, what was the outcome?"
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._connect()

    def _connect(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        is_memory = self.db_path == ":memory:"
        self._conn = sqlite3.connect(
            self.db_path if not is_memory else "file::memory:?cache=shared",
            uri=is_memory,
            check_same_thread=False,
            isolation_level=None,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        # C1 fix: PRAGMA is SQLite-specific. Guard for Postgres compatibility.
        safe_pragma(self._conn, self.db_path, "PRAGMA journal_mode=WAL")

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        assert self._conn is not None
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute("BEGIN")
                yield cur
                cur.execute("COMMIT")
            except Exception:
                cur.execute("ROLLBACK")
                raise

    def log_decision(
        self,
        preparation_id: str,
        decision: str,  # "approved" | "rejected"
        decided_by: str = "",
        preparation_type: str = "",
        title: str = "",
        intent_id: str = "",
        linked_assumption_ids: list[str] | None = None,
        linked_hypothesis_ids: list[str] | None = None,
        linked_evidence_count: int = 0,
        confidence_at_decision: float = 0.0,
    ) -> dict[str, Any]:
        """Append a decision to the log.

        Returns the stored row dict.
        """
        now = datetime.now(timezone.utc)
        row = {
            "logged_at": now.isoformat(),
            "preparation_id": preparation_id,
            "preparation_type": preparation_type,
            "title": title,
            "decision": decision,
            "decided_by": decided_by,
            "intent_id": intent_id,
            "linked_assumption_ids": json.dumps(linked_assumption_ids or []),
            "linked_hypothesis_ids": json.dumps(linked_hypothesis_ids or []),
            "linked_evidence_count": linked_evidence_count,
            "confidence_at_decision": confidence_at_decision,
            "outcome": "",
            "outcome_notes": "",
            "resolved_at": None,
        }

        cols = ", ".join(row.keys())
        placeholders = ", ".join(["?"] * len(row))
        with self._cursor() as cur:
            cur.execute(
                f"INSERT INTO decision_log ({cols}) VALUES ({placeholders})",
                tuple(row.values()),
            )

        logger.info("Decision logged: %s %s (prep=%s, intent=%s)",
                     decision, title[:40], preparation_id, intent_id or "—")
        return row

    def resolve_decision(
        self,
        preparation_id: str,
        outcome: str,
        notes: str = "",
    ) -> bool:
        """Update the outcome of a previously-logged decision.

        Called when the actual outcome is known (e.g., the RFC was merged,
        the rollback worked, the customer churned). This is what feeds
        Principle extraction: "we decided X based on assumptions A,B,C
        and the outcome was Y."
        """
        now = datetime.now(timezone.utc)
        with self._cursor() as cur:
            cur.execute(
                """UPDATE decision_log
                   SET outcome = ?, outcome_notes = ?, resolved_at = ?
                   WHERE preparation_id = (
                       SELECT preparation_id FROM decision_log
                       WHERE preparation_id = ?
                       ORDER BY logged_at DESC LIMIT 1
                   )""",
                (outcome, notes, now.isoformat(), preparation_id),
            )
            return cur.rowcount > 0

    def list_decisions(
        self,
        limit: int = 100,
        decision_filter: str | None = None,
        intent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """List decisions, most recent first."""
        query = "SELECT * FROM decision_log"
        clauses = []
        params: list[Any] = []
        if decision_filter:
            clauses.append("decision = ?")
            params.append(decision_filter)
        if intent_id:
            clauses.append("intent_id = ?")
            params.append(intent_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY logged_at DESC LIMIT ?"
        params.append(limit)

        with self._cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

        results = []
        for r in rows:
            d = dict(r)
            d["linked_assumption_ids"] = json.loads(d.get("linked_assumption_ids") or "[]")
            d["linked_hypothesis_ids"] = json.loads(d.get("linked_hypothesis_ids") or "[]")
            results.append(d)
        return results

    def get_decision_summary(self) -> dict[str, Any]:
        """Aggregate stats for the decision log."""
        with self._cursor() as cur:
            cur.execute("SELECT COUNT(*) as cnt FROM decision_log")
            total = cur.fetchone()["cnt"]
            cur.execute("SELECT COUNT(*) as cnt FROM decision_log WHERE decision = 'approved'")
            approved = cur.fetchone()["cnt"]
            cur.execute("SELECT COUNT(*) as cnt FROM decision_log WHERE decision = 'rejected'")
            rejected = cur.fetchone()["cnt"]
            cur.execute("SELECT COUNT(*) as cnt FROM decision_log WHERE outcome != ''")
            resolved = cur.fetchone()["cnt"]
            cur.execute("SELECT AVG(confidence_at_decision) as avg FROM decision_log")
            avg_row = cur.fetchone()
            avg_conf = avg_row["avg"] if avg_row["avg"] is not None else 0.0
        return {
            "total": total,
            "approved": approved,
            "rejected": rejected,
            "resolved_with_outcome": resolved,
            "avg_confidence_at_decision": round(avg_conf, 4),
        }


# ═══════════════════════════════════════════════════════════════════════════
# CAPABILITY IMPACT QUERY — "what collapses if person X disappeared?"
# ═══════════════════════════════════════════════════════════════════════════

class CapabilityImpactQuery:
    """Composite query: person → domains orphaned → laws weakened →
    recommendations that lose evidence.

    This is the data the Gravity UI will eventually surface. We capture
    the query now; we build the UI after the pilot proves the cognitive
    model works on real data.

    The query composes three existing primitives:
      1. KnowledgeGraph (who knows what) — person → domains
      2. EvidenceGraph (provenance) — which laws/recommendations cite
         signals from this person
      3. DecisionEngine (recommendations) — which active recommendations
         would lose evidence
    """

    def __init__(self, model, signals: list, decisions=None) -> None:
        self.model = model
        self.signals = signals
        self.decisions = decisions

    def analyze_person(self, person: str) -> dict[str, Any]:
        """What would collapse if this person disappeared?

        Returns:
            {
                "person": str,
                "influence": float,
                "domains_held": [...],
                "domains_orphaned": [...],  # domains where this person is the SOLE holder
                "signal_count": int,
                "laws_losing_evidence": [...],
                "recommendations_weakened": [...],
                "bottleneck_risk": "critical" | "high" | "medium" | "low",
                "blast_radius": int,  # total affected items
            }
        """
        person_lower = person.lower().strip()

        # 1. Domains this person holds
        kg = self.model.knowledge
        domains_held = sorted(kg.domain_holders_to_domains(person))
        influence = kg.influence.get(person, 0.0)

        # 2. Domains where this person is the SOLE holder (orphaned if they leave)
        domains_orphaned = []
        for domain in domains_held:
            holders = kg.domain_holders.get(domain, set())
            # Remove this person; if no holders remain, domain is orphaned
            remaining = {h for h in holders if h.lower() != person_lower}
            if not remaining:
                domains_orphaned.append(domain)

        # 3. Signals from this person
        person_signals = [s for s in self.signals if s.actor and s.actor.lower() == person_lower]
        signal_count = len(person_signals)

        # 4. Laws that cite signals from this person (evidence weakening)
        laws_losing_evidence = self._laws_citing_person(person_lower)

        # 5. Recommendations that would weaken (those whose evidence includes
        #    signals from this person)
        recommendations_weakened = []
        if self.decisions:
            try:
                recs = self.decisions.get_recommendations()
                for rec in recs:
                    prov = rec.get("provenance", [])
                    person_in_evidence = any(
                        p.get("actor", "").lower() == person_lower for p in prov
                    )
                    if person_in_evidence:
                        recommendations_weakened.append({
                            "title": rec.get("title", ""),
                            "confidence": rec.get("confidence", 0),
                            "urgency": rec.get("urgency", ""),
                        })
            except Exception:
                pass

        # 6. Blast radius + bottleneck risk
        blast_radius = (
            len(domains_orphaned)
            + len(laws_losing_evidence)
            + len(recommendations_weakened)
        )
        if len(domains_orphaned) > 0:
            bottleneck_risk = "critical"
        elif blast_radius >= 5:
            bottleneck_risk = "high"
        elif blast_radius >= 2:
            bottleneck_risk = "medium"
        else:
            bottleneck_risk = "low"

        return {
            "person": person,
            "influence": round(influence, 2),
            "domains_held": domains_held,
            "domains_orphaned": domains_orphaned,
            "signal_count": signal_count,
            "laws_losing_evidence": laws_losing_evidence,
            "recommendations_weakened": recommendations_weakened,
            "bottleneck_risk": bottleneck_risk,
            "blast_radius": blast_radius,
        }

    def _laws_citing_person(self, person_lower: str) -> list[dict[str, Any]]:
        """Find laws whose evidence includes signals from this person."""
        affected = []
        try:
            for law in self.model.laws:
                # Check if any evidence receipt for this law came from this person
                evidence = law.evidence or []
                person_evidence = [
                    e for e in evidence
                    if isinstance(e, dict) and e.get("actor", "").lower() == person_lower
                ]
                if person_evidence:
                    affected.append({
                        "law_code": law.code,
                        "statement": law.statement[:80] if law.statement else "",
                        "confidence": law.confidence,
                        "status": law.status,
                        "evidence_from_person": len(person_evidence),
                        "total_evidence": len(evidence),
                    })
        except Exception as e:
            logger.debug("Law scan failed: %s", e)
        return affected

    def list_high_impact_people(self, limit: int = 10) -> list[dict[str, Any]]:
        """List people by blast radius (highest first).

        This is the "bus factor" view — who would cause the most collapse
        if they disappeared?
        """
        # Get all known people from the knowledge graph
        all_people = set()
        kg = self.model.knowledge
        all_people.update(kg.expertise.keys())
        all_people.update(kg.influence.keys())

        results = []
        for person in all_people:
            if not person:
                continue
            try:
                impact = self.analyze_person(person)
                if impact["blast_radius"] > 0:
                    results.append(impact)
            except Exception:
                continue

        # Sort by blast radius descending, then by influence
        results.sort(key=lambda x: (x["blast_radius"], x["influence"]), reverse=True)
        return results[:limit]


# ═══════════════════════════════════════════════════════════════════════════
# SNAPSHOT COLLECTOR — gathers metrics from OEM state + learning DB
# ═══════════════════════════════════════════════════════════════════════════

def collect_snapshot_metrics(oem_state, learning_db_path: str) -> dict[str, Any]:
    """Collect all metrics for a weekly snapshot.

    This is the function the weekly scheduler calls. It reads from:
      - oem_state.snapshot() for counts
      - oem_state.model.knowledge for capability metrics
      - ClosedLoopLearningManager.get_improvement_report() for Brier/calibration
      - IntentStore / HypothesisStore / AssumptionGraph for cognitive-model counts

    Thread-safe: acquires oem_state._lock for a consistent read.
    """
    metrics: dict[str, Any] = {}

    with oem_state._lock:
        # 1. Core counts (signals, laws, recommendations)
        try:
            counts = oem_state.snapshot()
            metrics.update({
                "signals_processed": counts.get("signals_processed", 0),
                "learning_objects": counts.get("learning_objects", 0),
                "laws_inferred": counts.get("laws_inferred", 0),
                "validated_laws": counts.get("validated_laws", 0),
                "recommendations_active": counts.get("recommendations", 0),
            })
        except Exception as e:
            logger.warning("snapshot() failed: %s", e)

        # 2. Learning-loop metrics (Brier, calibration, accuracy)
        try:
            from maestro_oem.prediction_lifecycle import (
                ClosedLoopLearningManager, PredictionRecorder,
            )
            from maestro_oem.learning import CalibrationEngine
            cal = CalibrationEngine(learning_db_path)
            mgr = ClosedLoopLearningManager(
                learning_db_path, oem_state.model, oem_state.signals, cal,
                contradiction_log=oem_state._contradiction_log,
            )
            report = mgr.get_improvement_report()
            summary = report.get("summary", {})
            calibration = report.get("calibration", {})
            improvement = report.get("improvement_evidence", {})
            metrics.update({
                "predictions_total": summary.get("total_predictions", 0),
                "predictions_resolved": summary.get("resolved", 0),
                "predictions_pending": summary.get("pending", 0),
                "predictions_correct": summary.get("correct", 0),
                "predictions_incorrect": summary.get("incorrect", 0),
                "resolution_rate": summary.get("resolution_rate", 0.0),
                "accuracy_rate": summary.get("accuracy_rate", 0.0),
                "brier_score": calibration.get("brier_score", 0.0),
                "calibration_error": calibration.get("mean_calibration_error", 0.0),
                "is_well_calibrated": calibration.get("is_well_calibrated", False),
                "is_learning": improvement.get("is_learning", False),
            })
        except Exception as e:
            logger.warning("Learning report collection failed: %s", e)

        # 3. Capability metrics (hidden experts, concentration risks)
        try:
            kg = oem_state.model.knowledge
            metrics["hidden_experts_count"] = len(kg.get_hidden_experts())
            metrics["concentration_risks_count"] = len(kg.get_concentration_risk())
        except Exception as e:
            logger.warning("Capability metrics failed: %s", e)

        # 4. Cognitive-model counts (intents, hypotheses, assumptions, preparations)
        try:
            from maestro_api.routes.oem import (
                _get_intent_store, _get_hypothesis_store,
                _get_assumption_graph, _get_preparations,
            )
            intent_store = _get_intent_store()
            hypotheses = _get_hypothesis_store()
            assumption_graph = _get_assumption_graph()
            preparations = _get_preparations()

            metrics["intents_count"] = len(intent_store.list_intents())
            metrics["hypotheses_count"] = len(hypotheses.list_hypotheses())

            all_assumptions = assumption_graph.list_assumptions()
            metrics["assumptions_count"] = len(all_assumptions)
            metrics["assumptions_validated"] = sum(
                1 for a in all_assumptions if a.get("status") == "validated"
            )
            metrics["assumptions_invalidated"] = sum(
                1 for a in all_assumptions if a.get("status") == "invalidated"
            )
            metrics["assumptions_open"] = sum(
                1 for a in all_assumptions if a.get("status") in ("open", None, "")
            )

            metrics["preparations_count"] = len(preparations)
            metrics["preparations_approved"] = sum(
                1 for p in preparations if p.get("status") == "approved"
            )
        except Exception as e:
            logger.warning("Cognitive-model counts failed: %s", e)

        # 5. Contradictions count
        try:
            from maestro_oem.contradictions import ContradictionDetector
            assumption_graph = _get_assumption_graph()
            detector = ContradictionDetector(
                oem_state.model, oem_state.signals, assumption_graph,
            )
            contradictions = detector.detect_all()
            metrics["contradictions_count"] = len(contradictions)
        except Exception as e:
            logger.warning("Contradictions count failed: %s", e)

    return metrics


# ═══════════════════════════════════════════════════════════════════════════
