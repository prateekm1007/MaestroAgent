"""
Personal Knowledge Graph — longitudinal entity/commitment/outcome graph.

CEO Directive 2: Build a richer SituationStore as a dynamic knowledge
graph (entities, commitments, contradictions, outcomes). Use it for
better entity resolution and predictive anticipation.

The graph stores:
- Entities (people, companies, projects)
- Edges (commitments, completions, disputes, corrections)
- Completion rates per entity
- Predictive patterns ("this pattern historically led to missed follow-ups")

Usage:
    graph = PersonalGraph(db_path)
    graph.add_entity("AcmeCorp", type="company")
    graph.add_edge("AcmeCorp", "proposal", "commitment", {"confidence": 0.8})
    graph.update_outcome("AcmeCorp", "proposal", "hit")
    rate = graph.get_completion_rate("AcmeCorp")
    predictions = graph.predict_risk("AcmeCorp", "contract")
"""

from __future__ import annotations

import logging
import sqlite3
from maestro_personal_shell.db_util import get_db_conn
import json
import os
from typing import Any
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter

logger = logging.getLogger(__name__)


def _get_db_path() -> str:
    return os.environ.get(
        "MAESTRO_PERSONAL_DB",
        str(Path(__file__).resolve().parent / "personal.db"),
    )


class PersonalGraph:
    """Personal knowledge graph for longitudinal intelligence.

    Stores entities, their relationships, commitments, outcomes, and
    patterns. Enables predictive anticipation ("this entity historically
    misses follow-ups on contracts").

    P0 fix: all reads/writes are user-scoped. Every entity, edge, and
    pattern is tagged with user_email and queries filter by it.
    """

    def __init__(self, db_path: str | None = None, user_email: str = "bootstrap"):
        self._db_path = db_path or _get_db_path()
        self._user_email = user_email
        self._init_schema()

    def _init_schema(self) -> None:
        """Initialize graph tables."""
        conn = get_db_conn(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS graph_entities (
                entity_id TEXT NOT NULL,
                entity_name TEXT NOT NULL,
                entity_type TEXT DEFAULT 'unknown',
                user_email TEXT NOT NULL DEFAULT 'bootstrap',
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                PRIMARY KEY (entity_id, user_email)
            )
        """)
        # Migration: add user_email to edges if missing
        try:
            conn.execute("ALTER TABLE graph_edges ADD COLUMN user_email TEXT DEFAULT 'bootstrap'")
        except sqlite3.OperationalError:
            pass  # column already exists
        try:
            conn.execute("ALTER TABLE graph_patterns ADD COLUMN user_email TEXT DEFAULT 'bootstrap'")
        except sqlite3.OperationalError as e:
            logger.debug("execute failed: %s", e)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS graph_edges (
                edge_id TEXT PRIMARY KEY,
                source_entity TEXT NOT NULL,
                target_entity TEXT,
                edge_type TEXT NOT NULL,
                topic TEXT DEFAULT '',
                confidence REAL DEFAULT 0.5,
                status TEXT DEFAULT 'active',
                created_at TEXT NOT NULL,
                resolved_at TEXT,
                outcome TEXT,
                metadata TEXT DEFAULT '{}',
                user_email TEXT DEFAULT 'bootstrap'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS graph_patterns (
                pattern_id TEXT PRIMARY KEY,
                entity_id TEXT,
                pattern_type TEXT NOT NULL,
                pattern_description TEXT,
                occurrence_count INTEGER DEFAULT 1,
                last_occurred TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                user_email TEXT DEFAULT 'bootstrap'
            )
        """)
        conn.commit()
        conn.close()

    def add_entity(
        self,
        entity_name: str,
        entity_type: str = "unknown",
        user_email: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        """Add or update an entity in the graph (user-scoped)."""
        ue = user_email or self._user_email
        entity_id = entity_name.lower().strip()
        now = datetime.now(timezone.utc).isoformat()

        conn = get_db_conn(self._db_path)
        conn.execute(
            """INSERT OR REPLACE INTO graph_entities
               (entity_id, entity_name, entity_type, user_email, first_seen, last_seen, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                entity_id,
                entity_name,
                entity_type,
                ue,
                now,
                now,
                json.dumps(metadata or {}),
            ),
        )
        conn.commit()
        conn.close()
        return entity_id

    def add_edge(
        self,
        source_entity: str,
        edge_type: str,
        topic: str = "",
        target_entity: str = "",
        confidence: float = 0.5,
        metadata: dict | None = None,
        user_email: str | None = None,
    ) -> str:
        """Add an edge (user-scoped)."""
        from uuid import uuid4
        ue = user_email or self._user_email
        edge_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()

        self.add_entity(source_entity, user_email=ue)

        conn = get_db_conn(self._db_path)
        conn.execute(
            """INSERT INTO graph_edges
               (edge_id, source_entity, target_entity, edge_type, topic,
                confidence, status, created_at, resolved_at, outcome, metadata, user_email)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                edge_id,
                source_entity.lower().strip(),
                target_entity.lower().strip() if target_entity else "",
                edge_type,
                topic,
                confidence,
                "active",
                now,
                None,
                None,
                json.dumps(metadata or {}),
                ue,
            ),
        )
        conn.commit()
        conn.close()
        return edge_id

    def update_outcome(
        self,
        entity_name: str,
        topic: str,
        outcome: str,
        user_email: str | None = None,
    ) -> bool:
        """Update the outcome of an edge (user-scoped)."""
        ue = user_email or self._user_email
        conn = get_db_conn(self._db_path)
        now = datetime.now(timezone.utc).isoformat()
        entity_id = entity_name.lower().strip()

        row = conn.execute(
            """SELECT edge_id FROM graph_edges
               WHERE source_entity = ? AND topic LIKE ? AND status = 'active' AND user_email = ?
               ORDER BY created_at DESC LIMIT 1""",
            (entity_id, f"%{topic.lower()}%", ue),
        ).fetchone()

        if not row:
            conn.close()
            return False

        edge_id = row[0]
        conn.execute(
            """UPDATE graph_edges
               SET status = 'resolved', resolved_at = ?, outcome = ?
               WHERE edge_id = ?""",
            (now, outcome, edge_id),
        )
        conn.commit()
        conn.close()

        if outcome == "miss":
            self._record_pattern(entity_id, "missed_commitment", f"Missed commitment on '{topic}'", ue)

        return True

    def resolve_completion_signal(
        self,
        entity_name: str,
        completion_text: str,
        outcome: str,
        user_email: str | None = None,
    ) -> int:
        """Resolve the most recent active commitment edge for an entity.

        Called from create_signal when a completion/break signal is ingested.
        This closes the P11 wiring gap: update_outcome existed but was only
        called from the manual /api/signals/{id}/correct path, never from
        the ingest path. Result: completion_rate stayed None forever even
        after explicit "Item 0 has been delivered" signals.

        Returns the number of edges resolved (0 if no match).
        """
        if outcome not in ("hit", "miss"):
            return 0
        ue = user_email or self._user_email
        conn = get_db_conn(self._db_path)
        now = datetime.now(timezone.utc).isoformat()
        entity_id = entity_name.lower().strip()

        # Find the most recent active commitment edge for this entity
        rows = conn.execute(
            """SELECT edge_id, topic FROM graph_edges
               WHERE source_entity = ? AND edge_type = 'commitment'
               AND status = 'active' AND user_email = ?
               ORDER BY created_at DESC""",
            (entity_id, ue),
        ).fetchall()

        if not rows:
            conn.close()
            return 0

        # Match by topic overlap with the completion text.
        # completion_text e.g. "Item 0 has been delivered" should match
        # topic "I will deliver item 0" via shared significant tokens.
        text_lower = completion_text.lower()
        resolved = 0
        for edge_id, topic in rows:
            topic_lower = (topic or "").lower()
            # Cheap heuristic: any 3+ char token from topic appears in text
            topic_tokens = [t for t in topic_lower.split() if len(t) >= 3]
            if not topic_tokens:
                continue
            matches = sum(1 for tok in topic_tokens if tok in text_lower)
            if matches >= max(1, len(topic_tokens) // 3):
                conn.execute(
                    """UPDATE graph_edges
                       SET status = 'resolved', resolved_at = ?, outcome = ?
                       WHERE edge_id = ?""",
                    (now, outcome, edge_id),
                )
                resolved += 1
                if outcome == "miss":
                    self._record_pattern(
                        entity_id, "missed_commitment",
                        f"Missed commitment on '{topic}'", ue,
                    )

        conn.commit()
        conn.close()
        return resolved

    def get_completion_rate(self, entity_name: str, user_email: str | None = None) -> float | None:
        """Get the historical completion rate for an entity (user-scoped).

        P1-Audit-F5 fix: returns None when there are 0 resolved edges, NOT 0.5.
        The auditor found that a 0.5 default with zero resolutions produces
        fake "moderate risk" advice. None signals "insufficient data" so
        callers can display "unknown" instead of a fabricated percentage.
        """
        ue = user_email or self._user_email
        entity_id = entity_name.lower().strip()
        conn = get_db_conn(self._db_path)

        rows = conn.execute(
            """SELECT outcome FROM graph_edges
               WHERE source_entity = ? AND status = 'resolved' AND user_email = ?""",
            (entity_id, ue),
        ).fetchall()
        conn.close()

        if not rows:
            return None  # P1-Audit-F5: was 0.5 — fake confidence

        hits = sum(1 for r in rows if r[0] == "hit")
        return hits / len(rows)

    def get_entity_summary(self, entity_name: str, user_email: str | None = None) -> dict[str, Any]:
        """Get a summary of an entity's history (user-scoped).

        F3c fix (auditor round 2): when exact match fails, try word-boundary
        partial match (same rules as threads endpoint) so Graph and Threads
        can't disagree on "Alex" vs "Alex Chen"."""
        import re as _re_graph
        ue = user_email or self._user_email
        entity_id = entity_name.lower().strip()
        conn = get_db_conn(self._db_path)
        conn.row_factory = sqlite3.Row

        entity = conn.execute(
            "SELECT * FROM graph_entities WHERE entity_id = ? AND user_email = ?",
            (entity_id, ue),
        ).fetchone()

        # F3c: if exact match fails, try partial word-boundary match
        if not entity and len(entity_id) >= 3:
            all_entities = conn.execute(
                "SELECT * FROM graph_entities WHERE user_email = ?",
                (ue,),
            ).fetchall()
            for e in all_entities:
                e_id = str(e["entity_id"]).lower().strip()
                if _re_graph.search(r'\b' + _re_graph.escape(entity_id) + r'\b', e_id):
                    entity = e
                    break
                elif _re_graph.search(r'\b' + _re_graph.escape(e_id) + r'\b', entity_id):
                    entity = e
                    break

        if not entity:
            conn.close()
            return {"exists": False}

        edges = conn.execute(
            """SELECT * FROM graph_edges WHERE source_entity = ? AND user_email = ?
               ORDER BY created_at DESC LIMIT 20""",
            (entity_id, ue),
        ).fetchall()

        patterns = conn.execute(
            """SELECT * FROM graph_patterns WHERE entity_id = ? AND user_email = ?
               ORDER BY last_occurred DESC LIMIT 5""",
            (entity_id, ue),
        ).fetchall()

        conn.close()

        total_edges = len(edges)
        # Phase 1.3 fix (roadmap): separate edge types. The audit found
        # 'Newsletter: 20 active commitments' because signal_observed edges
        # were counted as active commitments. Only edge_type='commitment'
        # counts as a commitment; edge_type='signal' is just an interaction.
        commitment_edges = [e for e in edges if e["edge_type"] == "commitment"]
        signal_edges = [e for e in edges if e["edge_type"] == "signal"]

        resolved = [e for e in commitment_edges if e["status"] == "resolved"]
        hits = sum(1 for e in resolved if e["outcome"] == "hit")
        misses = sum(1 for e in resolved if e["outcome"] == "miss")
        active = [e for e in commitment_edges if e["status"] == "active"]

        # Phase 1.3: three completion-rate denominators per roadmap
        resolved_completion_rate = hits / len(resolved) if resolved else None
        all_cohort_completion_rate = hits / len(commitment_edges) if commitment_edges else None
        # overdue active rate: active commitments with no resolution
        overdue_active = len(active)  # simplified: all active are overdue-pending
        overdue_active_rate = overdue_active / len(commitment_edges) if commitment_edges else None

        return {
            "exists": True,
            "entity_name": entity["entity_name"],
            "entity_type": entity["entity_type"],
            "total_interactions": total_edges,
            "active_commitments": len(active),  # Phase 1.3: only commitment edges
            "resolved_commitments": len(resolved),
            "completion_rate": resolved_completion_rate,  # resolved-only (backward compat)
            "resolved_completion_rate": resolved_completion_rate,  # Phase 1.3: explicit
            "all_cohort_completion_rate": all_cohort_completion_rate,  # Phase 1.3: all commitments
            "overdue_active_rate": overdue_active_rate,  # Phase 1.3: active / all
            "miss_rate": misses / len(resolved) if resolved else None,
            "patterns": [
                {
                    "type": p["pattern_type"],
                    "description": p["pattern_description"],
                    "count": p["occurrence_count"],
                }
                for p in patterns
            ],
            "recent_edges": [
                {
                    "type": e["edge_type"],
                    "topic": e["topic"],
                    "status": e["status"],
                    "outcome": e["outcome"],
                    "confidence": e["confidence"],
                }
                for e in edges[:5]
            ],
        }

    def predict_risk(self, entity_name: str, topic: str = "", user_email: str | None = None) -> dict[str, Any]:
        """Predict the risk of a new commitment (user-scoped).

        P0 fix (auditor finding A): if the entity doesn't exist for this user,
        return exists=false instead of a generic 'medium' risk. This prevents
        side-channel information leakage (an attacker can probe entity names
        and get generic risk data for entities they shouldn't know about).
        """
        ue = user_email or self._user_email
        entity_id = entity_name.lower().strip()

        # P0 fix: check entity exists for this user before returning risk data
        conn = get_db_conn(self._db_path)
        conn.row_factory = sqlite3.Row
        entity_row = conn.execute(
            "SELECT * FROM graph_entities WHERE entity_id = ? AND user_email = ?",
            (entity_id, ue),
        ).fetchone()

        if entity_row is None:
            conn.close()
            return {
                "entity": entity_name,
                "exists": False,
                "risk_level": "unknown",
                "completion_rate": None,  # P1-Audit-F5: was 0.0 — use None for "no data"
                "risk_factors": [],
                "recommendation": "Entity not found — no risk data available.",
            }

        completion_rate = self.get_completion_rate(entity_name, ue)
        patterns = conn.execute(
            "SELECT * FROM graph_patterns WHERE entity_id = ? AND user_email = ?",
            (entity_id, ue),
        ).fetchall()
        conn.close()

        risk_level = "low"
        risk_factors = []

        # P1-Audit-F5 fix: when completion_rate is None (insufficient data),
        # do NOT fabricate a risk level from a fake 0.5. Report "unknown"
        # and recommend gathering more history.
        if completion_rate is None:
            risk_level = "unknown"
            risk_factors.append("Insufficient history — no resolved commitments for this entity")
        elif completion_rate < 0.5:
            risk_level = "high"
            risk_factors.append(f"Low completion rate ({completion_rate:.0%})")
        elif completion_rate < 0.7:
            risk_level = "medium"
            risk_factors.append(f"Moderate completion rate ({completion_rate:.0%})")

        for p in patterns:
            if p["pattern_type"] == "missed_commitment" and topic.lower() in (p["pattern_description"] or "").lower():
                risk_level = "high"
                risk_factors.append(f"Pattern: {p['pattern_description']}")

        recommendation = (
            "Insufficient data — track more commitments for this entity before assessing risk."
            if risk_level == "unknown"
            else "Set an earlier internal deadline and follow up proactively."
            if risk_level == "high"
            else "Monitor progress and send a reminder closer to deadline."
            if risk_level == "medium"
            else "Standard tracking is sufficient."
        )

        return {
            "entity": entity_name,
            "exists": True,
            "risk_level": risk_level,
            "completion_rate": completion_rate,
            "risk_factors": risk_factors,
            "recommendation": recommendation,
        }

    def _record_pattern(
        self,
        entity_id: str,
        pattern_type: str,
        description: str,
        user_email: str | None = None,
    ) -> None:
        """Record or update a behavioral pattern (user-scoped)."""
        from uuid import uuid4
        ue = user_email or self._user_email
        now = datetime.now(timezone.utc).isoformat()

        conn = get_db_conn(self._db_path)

        existing = conn.execute(
            """SELECT pattern_id, occurrence_count FROM graph_patterns
               WHERE entity_id = ? AND pattern_type = ? AND pattern_description = ? AND user_email = ?""",
            (entity_id, pattern_type, description, ue),
        ).fetchone()

        if existing:
            conn.execute(
                """UPDATE graph_patterns
                   SET occurrence_count = ?, last_occurred = ?
                   WHERE pattern_id = ?""",
                (existing[1] + 1, now, existing[0]),
            )
        else:
            conn.execute(
                """INSERT INTO graph_patterns
                   (pattern_id, entity_id, pattern_type, pattern_description,
                    occurrence_count, last_occurred, metadata, user_email)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(uuid4()), entity_id, pattern_type, description, 1, now, "{}", ue),
            )

        conn.commit()
        conn.close()
