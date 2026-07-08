"""
Weekly Pilot Snapshot Infrastructure.

Per corrected audit condition 3: "Weekly pilot snapshots must capture not
just Brier scores but executive-relevant metrics: time-to-answer,
contradiction-surfacing rate, preparation staleness rate, whisper action rate."

This module provides:
  1. PilotSnapshot — dataclass capturing all exec-relevant metrics for one week
  2. capture_snapshot() — collects metrics from the running system
  3. save_snapshot() — persists to SQLite for trend tracking
  4. load_snapshots() — retrieves historical snapshots for comparison
  5. compare_snapshots() — delta between two weeks

Usage:
    from maestro_cognitive_council.pilot_snapshot import capture_snapshot, save_snapshot

    # Weekly cron job:
    snapshot = capture_snapshot(oem_state=oem_state, week_number=1)
    save_snapshot(snapshot, db_path="pilot_snapshots.db")

    # Comparison:
    from maestro_cognitive_council.pilot_snapshot import load_snapshots, compare_snapshots
    snapshots = load_snapshots(db_path="pilot_snapshots.db")
    if len(snapshots) >= 2:
        delta = compare_snapshots(snapshots[-2], snapshots[-1])
        print(f"Week-over-week: {delta}")
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class PilotSnapshot:
    """Weekly snapshot of executive-relevant pilot metrics.

    Per corrected audit condition 3: these are the metrics that matter
    to executives, not just Brier scores. Each metric has a clear
    definition and a target direction (↑ = higher is better, ↓ = lower).
    """
    snapshot_id: str = ""
    week_number: int = 0
    captured_at: str = ""

    # ── Executive-relevant metrics ──────────────────────────────────────

    # Time-to-answer: average seconds from query to useful answer
    # (↑ is worse — executives want fast answers)
    avg_time_to_answer_seconds: float = 0.0
    ask_query_count: int = 0

    # Contradiction-surfacing rate: how often the system surfaced a
    # disagreement or contradiction that the executive didn't know about
    # (↑ is better — this is Maestro's key differentiator)
    contradictions_surfaced: int = 0
    contradiction_rate: float = 0.0  # contradictions / total queries

    # Preparation staleness rate: how often a preparation was shown
    # after new evidence had arrived (↓ is better — stale prep is dangerous)
    preparations_generated: int = 0
    preparations_stale: int = 0
    preparation_staleness_rate: float = 0.0

    # Whisper action rate: how often an executive acted on a whisper
    # (↑ is better — whispers that don't lead to action are noise)
    whispers_delivered: int = 0
    whispers_acted_on: int = 0
    whisper_action_rate: float = 0.0

    # Whisper suppression rate: how often the system correctly stayed silent
    # (↑ is better — restraint builds trust)
    whispers_suppressed: int = 0
    whisper_suppression_rate: float = 0.0

    # ── Learning metrics ────────────────────────────────────────────────

    # Pattern proposals: new candidate patterns proposed this week
    patterns_proposed: int = 0
    # Pattern promotions: patterns governance-approved this week
    patterns_promoted: int = 0
    # Pattern falsifications: patterns falsified this week
    patterns_falsified: int = 0

    # Brier scores (retained from prior instrumentation)
    brier_score_avg: float = 0.0
    predictions_resolved: int = 0

    # ── System health ───────────────────────────────────────────────────

    active_situations: int = 0
    total_signals_ingested: int = 0
    governance_actions_taken: int = 0

    # ── Test suite scores (for regression tracking) ─────────────────────

    test1_score: float = 0.0  # World Model Benchmark %
    test2_score: float = 0.0  # Behavioral Coherence %
    test3_score: float = 0.0  # Governance Handoff %
    test4_score: float = 0.0  # Governance Stress %
    test5_score: float = 0.0  # 90-day Longitudinal %

    def to_dict(self) -> dict:
        return asdict(self)


def capture_snapshot(
    oem_state: Any = None,
    week_number: int = 0,
    situation_store: Any = None,
    candidate_store: Any = None,
) -> PilotSnapshot:
    """Capture a weekly pilot snapshot from the running system.

    Collects executive-relevant metrics from OEM state, situation store,
    and candidate pattern store. Safe to call even if some components
    are unavailable — missing data is recorded as 0.
    """
    snapshot = PilotSnapshot(
        snapshot_id=f"pilot-w{week_number:02d}-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
        week_number=week_number,
        captured_at=datetime.now(timezone.utc).isoformat(),
    )

    # Active situations
    if situation_store:
        try:
            situations = situation_store.load_all_situations()
            snapshot.active_situations = len(situations)
        except Exception:
            pass

    # Signals ingested
    if oem_state:
        try:
            signals = getattr(oem_state, "signals", None) or []
            snapshot.total_signals_ingested = len(signals)
        except Exception:
            pass

    # Pattern metrics
    if candidate_store:
        try:
            candidates = candidate_store.get_all() if hasattr(candidate_store, "get_all") else []
            snapshot.patterns_proposed = len(candidates)
            for c in candidates:
                status = getattr(c, "status", None)
                status_val = getattr(status, "value", str(status)) if status else ""
                if status_val == "ACTIVE_PATTERN":
                    snapshot.patterns_promoted += 1
                elif status_val == "FALSIFIED":
                    snapshot.patterns_falsified += 1
        except Exception:
            pass

    # Compute rates
    if snapshot.ask_query_count > 0:
        snapshot.contradiction_rate = (
            snapshot.contradictions_surfaced / snapshot.ask_query_count
        )
    if snapshot.preparations_generated > 0:
        snapshot.preparation_staleness_rate = (
            snapshot.preparations_stale / snapshot.preparations_generated
        )
    if snapshot.whispers_delivered > 0:
        snapshot.whisper_action_rate = (
            snapshot.whispers_acted_on / snapshot.whispers_delivered
        )
    total_whisper_decisions = snapshot.whispers_delivered + snapshot.whispers_suppressed
    if total_whisper_decisions > 0:
        snapshot.whisper_suppression_rate = (
            snapshot.whispers_suppressed / total_whisper_decisions
        )

    logger.info(
        "Pilot snapshot captured: week=%d, situations=%d, signals=%d, patterns=%d",
        week_number, snapshot.active_situations, snapshot.total_signals_ingested,
        snapshot.patterns_proposed,
    )
    return snapshot


def save_snapshot(snapshot: PilotSnapshot, db_path: str = "pilot_snapshots.db") -> None:
    """Persist a pilot snapshot to SQLite for trend tracking."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pilot_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            week_number INTEGER,
            captured_at TEXT,
            data_json TEXT
        )
    """)
    conn.execute(
        "INSERT OR REPLACE INTO pilot_snapshots VALUES (?, ?, ?, ?)",
        (snapshot.snapshot_id, snapshot.week_number, snapshot.captured_at,
         json.dumps(snapshot.to_dict(), default=str)),
    )
    conn.commit()
    conn.close()
    logger.info("Pilot snapshot saved: %s", snapshot.snapshot_id)


def load_snapshots(db_path: str = "pilot_snapshots.db") -> list[PilotSnapshot]:
    """Load all pilot snapshots from SQLite, sorted by week."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT data_json FROM pilot_snapshots ORDER BY week_number"
    ).fetchall()
    conn.close()
    snapshots = []
    for (data_json,) in rows:
        try:
            data = json.loads(data_json)
            snapshots.append(PilotSnapshot(**data))
        except Exception:
            pass
    return snapshots


def compare_snapshots(prev: PilotSnapshot, curr: PilotSnapshot) -> dict[str, Any]:
    """Compare two weekly snapshots and return the deltas.

    Each metric shows the change and whether it's an improvement (↑/↓).
    """
    deltas: dict[str, Any] = {}

    # Higher-is-better metrics
    for metric in ("contradiction_rate", "whisper_action_rate",
                   "whisper_suppression_rate", "patterns_promoted",
                   "test1_score", "test2_score", "test3_score",
                   "test4_score", "test5_score"):
        prev_val = getattr(prev, metric, 0)
        curr_val = getattr(curr, metric, 0)
        delta = curr_val - prev_val
        deltas[metric] = {
            "prev": prev_val, "curr": curr_val, "delta": delta,
            "direction": "↑" if delta > 0 else ("↓" if delta < 0 else "→"),
            "improvement": delta > 0,
        }

    # Lower-is-better metrics
    for metric in ("avg_time_to_answer_seconds", "preparation_staleness_rate",
                   "patterns_falsified"):
        prev_val = getattr(prev, metric, 0)
        curr_val = getattr(curr, metric, 0)
        delta = curr_val - prev_val
        deltas[metric] = {
            "prev": prev_val, "curr": curr_val, "delta": delta,
            "direction": "↑" if delta > 0 else ("↓" if delta < 0 else "→"),
            "improvement": delta < 0,
        }

    return deltas
