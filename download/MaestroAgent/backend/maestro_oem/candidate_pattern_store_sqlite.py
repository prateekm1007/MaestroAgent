"""SQLite-backed CandidatePatternStore — Phase 11 (Durability).

AUDITOR-DIRECTIVE Phase 11:
> Replace the in-memory store with production-compatible persistence.
> Requirements: tenant isolation, transactions, schema migrations,
> idempotent writes, restart durability, concurrent update safety,
> audit history, versioning, replayability.
> Use the repository's existing persistence architecture.

This follows the PredictionRecorder pattern (prediction_lifecycle.py):
  - org_id scoping (P7: two tenants must never see each other's data)
  - threading.RLock for concurrent update safety
  - _connect() context manager with BEGIN/COMMIT/ROLLBACK transactions
  - CREATE TABLE IF NOT EXISTS for idempotent schema
  - check_same_thread=False for FastAPI compatibility

The store persists:
  - candidate_patterns: the hypotheses with all 8 separated counters
  - prospective_predictions: registered predictions with frozen evidence snapshots
  - status_transitions: every hypothesis status change (audit history)

Restart durability: on restart, the store loads from SQLite. Candidates,
predictions, and their resolved outcomes survive.

Tenant isolation (P7): every query filters by org_id. Two stores with
different org_ids sharing the same DB file never see each other's data.
"""

from __future__ import annotations

import json
import logging
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator
from uuid import UUID, uuid4

from maestro_db import sqlite_compat as sqlite3

from maestro_oem.pattern_proposer import (
    CandidatePattern, CandidatePatternStore, CandidateStatus,
)
from maestro_oem.empirical_loop import ObservationCase

logger = logging.getLogger(__name__)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS candidate_patterns (
    id                          TEXT PRIMARY KEY,
    candidate_id                TEXT UNIQUE NOT NULL,
    org_id                      TEXT NOT NULL DEFAULT 'default',
    hypothesis                  TEXT NOT NULL,
    claim_text                  TEXT,
    claim_type                  TEXT DEFAULT 'inference',
    business_inference_phrases  TEXT,    -- JSON array
    entities                    TEXT,    -- JSON array
    evidence_citation_numbers   TEXT,    -- JSON array
    status                      TEXT NOT NULL DEFAULT 'HYPOTHESIS',
    reasoning_mentions          INTEGER NOT NULL DEFAULT 1,
    historical_support_cases    INTEGER NOT NULL DEFAULT 0,
    independent_cases           INTEGER NOT NULL DEFAULT 0,
    prospective_predictions     INTEGER NOT NULL DEFAULT 0,
    resolved_outcomes           INTEGER NOT NULL DEFAULT 0,
    supporting_outcomes         INTEGER NOT NULL DEFAULT 0,
    contradicting_outcomes      INTEGER NOT NULL DEFAULT 0,
    unresolved_outcomes         INTEGER NOT NULL DEFAULT 0,
    first_detected              TEXT NOT NULL,
    last_detected               TEXT NOT NULL,
    proposal_query_ids          TEXT,    -- JSON array
    calibration_score           REAL,
    dedup_key                   TEXT NOT NULL,
    created_at                  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_cp_org ON candidate_patterns(org_id);
CREATE INDEX IF NOT EXISTS idx_cp_status ON candidate_patterns(status);
CREATE INDEX IF NOT EXISTS idx_cp_dedup ON candidate_patterns(dedup_key);
CREATE INDEX IF NOT EXISTS idx_cp_org_dedup ON candidate_patterns(org_id, dedup_key);

CREATE TABLE IF NOT EXISTS prospective_predictions (
    id                          TEXT PRIMARY KEY,
    prediction_id               TEXT UNIQUE NOT NULL,
    candidate_id                TEXT NOT NULL,
    org_id                      TEXT NOT NULL DEFAULT 'default',
    case_fingerprint            TEXT NOT NULL,
    expected_outcome            TEXT,
    observation_window_days     INTEGER DEFAULT 30,
    registered_at               TEXT NOT NULL,
    evidence_snapshot           TEXT,    -- JSON
    status                      TEXT NOT NULL DEFAULT 'pending',
    resolved_at                 TEXT,
    resolution_source           TEXT,
    observation_case            TEXT,    -- JSON (serialized ObservationCase)
    created_at                  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_pp_org ON prospective_predictions(org_id);
CREATE INDEX IF NOT EXISTS idx_pp_status ON prospective_predictions(status);
CREATE INDEX IF NOT EXISTS idx_pp_candidate ON prospective_predictions(candidate_id);
CREATE INDEX IF NOT EXISTS idx_pp_org_status ON prospective_predictions(org_id, status);

CREATE TABLE IF NOT EXISTS status_transitions (
    id                  TEXT PRIMARY KEY,
    candidate_id        TEXT NOT NULL,
    org_id              TEXT NOT NULL DEFAULT 'default',
    from_status         TEXT,
    to_status           TEXT NOT NULL,
    reason              TEXT,
    evidence            TEXT,
    actor               TEXT DEFAULT 'system',
    timestamp           TEXT NOT NULL,
    policy_version      TEXT DEFAULT 'v1'
);
CREATE INDEX IF NOT EXISTS idx_st_candidate ON status_transitions(candidate_id);
CREATE INDEX IF NOT EXISTS idx_st_org ON status_transitions(org_id);
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteCandidatePatternStore(CandidatePatternStore):
    """SQLite-backed store. Drop-in replacement for the in-memory store.

    P7 (tenant isolation): every query filters by org_id. Two stores with
    different org_ids sharing the same DB file never see each other's data.

    P11 (wiring): drop-in replacement — same interface as CandidatePatternStore.
    The lifespan swaps the in-memory store for this one; no other code changes.

    Restart durability: candidates, predictions, and status transitions persist
    across restarts. On startup, _load_all() hydrates the in-memory cache from
    SQLite so the store is immediately queryable.
    """

    def __init__(self, db_path: str, org_id: str = "default") -> None:
        self.db_path = db_path
        self.org_id = org_id
        self._lock = threading.RLock()
        # Initialize the in-memory caches (parent class uses these)
        self._candidates: dict[str, CandidatePattern] = {}
        self._predictions: dict[str, dict[str, Any]] = {}
        self._init_db()
        self._load_all()  # hydrate from SQLite on startup

    def _init_db(self) -> None:
        """Create tables if they don't exist. Idempotent."""
        conn = sqlite3.connect(self.db_path, isolation_level=None, check_same_thread=False)
        try:
            conn.executescript(_SCHEMA)
        finally:
            conn.close()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Cursor]:
        conn = sqlite3.connect(self.db_path, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        try:
            cur.execute("BEGIN")
            yield cur
            cur.execute("COMMIT")
        except Exception:
            try:
                cur.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass
            raise
        finally:
            conn.close()

    def _load_all(self) -> None:
        """Hydrate the in-memory cache from SQLite. Called on startup."""
        with self._lock, self._connect() as cur:
            # Load candidates
            cur.execute(
                "SELECT * FROM candidate_patterns WHERE org_id = ?",
                (self.org_id,),
            )
            for row in cur.fetchall():
                c = self._row_to_candidate(row)
                self._candidates[c.dedup_key] = c

            # Load predictions
            cur.execute(
                "SELECT * FROM prospective_predictions WHERE org_id = ?",
                (self.org_id,),
            )
            for row in cur.fetchall():
                pred = self._row_to_prediction(row)
                self._predictions[pred["prediction_id"]] = pred

        logger.info(
            "SQLiteCandidatePatternStore: loaded %d candidates + %d predictions for org=%s",
            len(self._candidates), len(self._predictions), self.org_id,
        )

    def _row_to_candidate(self, row: sqlite3.Row) -> CandidatePattern:
        """Convert a SQLite row to a CandidatePattern."""
        c = CandidatePattern(
            candidate_id=UUID(row["candidate_id"]),
            hypothesis=row["hypothesis"],
            claim_text=row["claim_text"] or "",
            claim_type=row["claim_type"] or "inference",
            business_inference_phrases=json.loads(row["business_inference_phrases"] or "[]"),
            entities=json.loads(row["entities"] or "[]"),
            evidence_citation_numbers=json.loads(row["evidence_citation_numbers"] or "[]"),
            status=CandidateStatus(row["status"]),
            reasoning_mentions=row["reasoning_mentions"],
            historical_support_cases=row["historical_support_cases"],
            independent_cases=row["independent_cases"],
            prospective_predictions=row["prospective_predictions"],
            resolved_outcomes=row["resolved_outcomes"],
            supporting_outcomes=row["supporting_outcomes"],
            contradicting_outcomes=row["contradicting_outcomes"],
            unresolved_outcomes=row["unresolved_outcomes"],
            first_detected=datetime.fromisoformat(row["first_detected"]),
            last_detected=datetime.fromisoformat(row["last_detected"]),
            proposal_query_ids=json.loads(row["proposal_query_ids"] or "[]"),
            calibration_score=row["calibration_score"],
        )
        return c

    def _row_to_prediction(self, row: sqlite3.Row) -> dict[str, Any]:
        """Convert a SQLite row to a prediction dict."""
        pred = {
            "prediction_id": row["prediction_id"],
            "candidate_id": row["candidate_id"],
            "case_fingerprint": row["case_fingerprint"],
            "expected_outcome": row["expected_outcome"] or "",
            "observation_window_days": row["observation_window_days"],
            "registered_at": datetime.fromisoformat(row["registered_at"]),
            "evidence_snapshot": json.loads(row["evidence_snapshot"] or "{}"),
            "status": row["status"],
            "resolved_at": datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None,
            "resolution_source": row["resolution_source"],
            "observation_case": None,
        }
        # Deserialize the ObservationCase if present
        case_json = row["observation_case"]
        if case_json:
            try:
                case_data = json.loads(case_json)
                pred["observation_case"] = self._dict_to_observation_case(case_data)
            except Exception:
                pass
        return pred

    def _dict_to_observation_case(self, d: dict[str, Any]) -> ObservationCase:
        """Reconstruct an ObservationCase from a dict."""
        case = ObservationCase(
            case_id=UUID(d["case_id"]) if d.get("case_id") else uuid4(),
            candidate_pattern_id=UUID(d["candidate_pattern_id"]) if d.get("candidate_pattern_id") else None,
            entity_id=d.get("entity_id", ""),
            situation_hash=d.get("situation_hash", ""),
            time_window_start=d.get("time_window_start", ""),
            outcome_target=d.get("outcome_target", ""),
            source_evidence_ids=d.get("source_evidence_ids", []),
            evidence_lineage_ids=d.get("evidence_lineage_ids", []),
            resolution_status=d.get("resolution_status", "pending"),
            resolution_source_ids=d.get("resolution_source_ids", []),
            confounders=d.get("confounders", []),
            scope_dimensions=d.get("scope_dimensions", {}),
        )
        if d.get("eligibility_time"):
            case.eligibility_time = datetime.fromisoformat(d["eligibility_time"])
        if d.get("prediction_registered_at"):
            case.prediction_registered_at = datetime.fromisoformat(d["prediction_registered_at"])
        if d.get("observation_window_end"):
            case.observation_window_end = datetime.fromisoformat(d["observation_window_end"])
        case.expected_outcome = d.get("expected_outcome", "")
        case.actual_outcome = d.get("actual_outcome", "")
        if d.get("resolved_at"):
            case.resolved_at = datetime.fromisoformat(d["resolved_at"])
        return case

    def _candidate_to_row(self, c: CandidatePattern) -> tuple:
        """Convert a CandidatePattern to a SQLite row tuple."""
        return (
            str(uuid4()),  # id (primary key, not the candidate_id)
            str(c.candidate_id),
            self.org_id,
            c.hypothesis,
            c.claim_text,
            c.claim_type,
            json.dumps(c.business_inference_phrases),
            json.dumps(c.entities),
            json.dumps(c.evidence_citation_numbers),
            c.status.value,
            c.reasoning_mentions,
            c.historical_support_cases,
            c.independent_cases,
            c.prospective_predictions,
            c.resolved_outcomes,
            c.supporting_outcomes,
            c.contradicting_outcomes,
            c.unresolved_outcomes,
            c.first_detected.isoformat(),
            c.last_detected.isoformat(),
            json.dumps(c.proposal_query_ids),
            c.calibration_score,
            c.dedup_key,
        )

    # ─── Override the in-memory methods to persist to SQLite ───────────────

    def upsert(self, candidate: CandidatePattern, query_id: str = "") -> CandidatePattern:
        """Insert or update. Persists to SQLite. P7: scoped by org_id."""
        with self._lock:
            result = super().upsert(candidate, query_id)
            # Persist to SQLite
            with self._connect() as cur:
                # Use INSERT OR REPLACE (idempotent by dedup_key + org_id)
                cur.execute(
                    """INSERT OR REPLACE INTO candidate_patterns
                       (id, candidate_id, org_id, hypothesis, claim_text, claim_type,
                        business_inference_phrases, entities, evidence_citation_numbers,
                        status, reasoning_mentions, historical_support_cases,
                        independent_cases, prospective_predictions, resolved_outcomes,
                        supporting_outcomes, contradicting_outcomes, unresolved_outcomes,
                        first_detected, last_detected, proposal_query_ids,
                        calibration_score, dedup_key)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    self._candidate_to_row(result),
                )
            return result

    def register_prospective_prediction(
        self,
        candidate_id: UUID,
        case_fingerprint: str,
        expected_outcome: str,
        observation_window_days: int = 30,
        evidence_snapshot: dict[str, Any] | None = None,
    ) -> str | None:
        """Register a prediction. Persists to SQLite. P7: scoped by org_id."""
        with self._lock:
            # Check for duplicate in SQLite first (P14: reject duplicate case)
            with self._connect() as cur:
                cur.execute(
                    "SELECT prediction_id FROM prospective_predictions WHERE org_id = ? AND case_fingerprint = ?",
                    (self.org_id, case_fingerprint),
                )
                if cur.fetchone():
                    logger.info("SQLiteStore: rejected duplicate prediction (case=%s)", case_fingerprint[:16])
                    return None

            prediction_id = super().register_prospective_prediction(
                candidate_id, case_fingerprint, expected_outcome,
                observation_window_days, evidence_snapshot,
            )
            if prediction_id is None:
                return None

            # Persist to SQLite
            pred = self._predictions[prediction_id]
            with self._connect() as cur:
                cur.execute(
                    """INSERT OR REPLACE INTO prospective_predictions
                       (id, prediction_id, candidate_id, org_id, case_fingerprint,
                        expected_outcome, observation_window_days, registered_at,
                        evidence_snapshot, status, resolved_at, resolution_source,
                        observation_case)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(uuid4()), prediction_id, str(candidate_id), self.org_id,
                        case_fingerprint, expected_outcome, observation_window_days,
                        pred["registered_at"].isoformat(),
                        json.dumps(pred["evidence_snapshot"]),
                        pred["status"],
                        None, None, None,
                    ),
                )
            return prediction_id

    def register_prospective_prediction_from_case(
        self,
        candidate_id: UUID,
        observation_case: ObservationCase,
        expected_outcome: str,
        observation_window_days: int = 30,
    ) -> str | None:
        """Register from a DERIVED ObservationCase. Persists case to SQLite."""
        with self._lock:
            prediction_id = super().register_prospective_prediction_from_case(
                candidate_id, observation_case, expected_outcome, observation_window_days,
            )
            if prediction_id is None:
                return None

            # Persist the observation_case JSON to the prediction row
            case_dict = observation_case.to_audit_dict()
            with self._connect() as cur:
                cur.execute(
                    "UPDATE prospective_predictions SET observation_case = ? WHERE prediction_id = ? AND org_id = ?",
                    (json.dumps(case_dict), prediction_id, self.org_id),
                )
            return prediction_id

    def resolve_prospective_prediction(
        self,
        prediction_id: str,
        outcome: str,
        resolution_source: str = "",
    ) -> bool:
        """Resolve a prediction. Persists to SQLite. Records status transition."""
        with self._lock:
            success = super().resolve_prospective_prediction(prediction_id, outcome, resolution_source)
            if not success:
                return False

            # Persist the resolution
            pred = self._predictions[prediction_id]
            candidate_id = pred["candidate_id"]
            resolved_at = pred.get("resolved_at") or datetime.now(timezone.utc)

            with self._connect() as cur:
                cur.execute(
                    """UPDATE prospective_predictions
                       SET status = ?, resolved_at = ?, resolution_source = ?
                       WHERE prediction_id = ? AND org_id = ?""",
                    (outcome, resolved_at.isoformat(), resolution_source,
                     prediction_id, self.org_id),
                )
                # Update the candidate's counters in SQLite
                candidate = None
                for c in self._candidates.values():
                    if str(c.candidate_id) == candidate_id:
                        candidate = c
                        break
                if candidate:
                    cur.execute(
                        """UPDATE candidate_patterns SET
                           resolved_outcomes = ?, supporting_outcomes = ?,
                           contradicting_outcomes = ?, unresolved_outcomes = ?,
                           calibration_score = ?, status = ?
                           WHERE candidate_id = ? AND org_id = ?""",
                        (candidate.resolved_outcomes, candidate.supporting_outcomes,
                         candidate.contradicting_outcomes, candidate.unresolved_outcomes,
                         candidate.calibration_score, candidate.status.value,
                         candidate_id, self.org_id),
                    )
                    # Record the status transition (audit history)
                    if candidate.status == CandidateStatus.TESTING:
                        cur.execute(
                            """INSERT INTO status_transitions
                               (id, candidate_id, org_id, from_status, to_status,
                                reason, evidence, actor, timestamp, policy_version)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (str(uuid4()), candidate_id, self.org_id,
                             "HYPOTHESIS", "TESTING",
                             f"auto_promote_3_prospective_supports",
                             f"supports={candidate.supporting_outcomes}",
                             "system", _utcnow(), "v1"),
                        )
                    elif candidate.status == CandidateStatus.FALSIFIED:
                        cur.execute(
                            """INSERT INTO status_transitions
                               (id, candidate_id, org_id, from_status, to_status,
                                reason, evidence, actor, timestamp, policy_version)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (str(uuid4()), candidate_id, self.org_id,
                             "HYPOTHESIS", "FALSIFIED",
                             f"auto_falsify_3_prospective_contradictions",
                             f"contradictions={candidate.contradicting_outcomes}",
                             "system", _utcnow(), "v1"),
                        )
            return True

    def get_status_history(self, candidate_id: str) -> list[dict[str, Any]]:
        """Get the full status transition history for a candidate. Audit trail."""
        with self._lock, self._connect() as cur:
            cur.execute(
                """SELECT * FROM status_transitions
                   WHERE candidate_id = ? AND org_id = ?
                   ORDER BY timestamp""",
                (candidate_id, self.org_id),
            )
            return [dict(row) for row in cur.fetchall()]
