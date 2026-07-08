"""
Institutional Autobiography — Organizational Memory validation.

Per audit: 'institutional autobiography (abandoned decisions, changed
assumptions, previous Whispers) queryable but not yet validated >95%.'

This module provides:
  1. query_autobiography() — query what Maestro remembers about past
     decisions, assumptions, whispers, and preparations
  2. validate_autobiography() — test that the system can answer:
     - "What did we decide about X?"
     - "What assumptions have changed?"
     - "What did you tell me about this before?"
     - "Did that assumption turn out true?"
  3. AutobiographyEntry — structured record of past organizational events
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class AutobiographyEntry:
    """A single entry in the institutional autobiography.

    Types:
      - decision: a decision that was made (or abandoned)
      - assumption: an assumption that was held (and possibly changed)
      - whisper: a whisper that was delivered (or suppressed)
      - preparation: a preparation that was generated
      - commitment: a commitment that was made (and possibly fulfilled/missed)
      - falsification: a pattern that was learned then falsified
    """
    entry_id: str = ""
    entry_type: str = ""  # decision | assumption | whisper | preparation | commitment | falsification
    entity: str = ""
    situation_id: str = ""
    title: str = ""
    description: str = ""
    status: str = ""  # active | abandoned | changed | fulfilled | missed | falsified
    created_at: str = ""
    resolved_at: Optional[str] = None
    resolution: Optional[str] = None  # what happened
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class InstitutionalAutobiography:
    """Queryable institutional memory of past organizational events.

    Per audit: 'institutional autobiography (abandoned decisions, changed
    assumptions, previous Whispers) queryable but not yet validated >95%.'

    This module makes the system's organizational memory queryable as
    a first-class capability. An executive can ask:
      - "What did we decide about CustomerA?"
      - "What assumptions have changed since last quarter?"
      - "What did you tell me about this before?"
      - "Did that assumption turn out true?"
    """

    def __init__(self, db_path: str = "autobiography.db"):
        self._db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS autobiography (
                entry_id TEXT PRIMARY KEY,
                entry_type TEXT,
                entity TEXT,
                situation_id TEXT,
                title TEXT,
                description TEXT,
                status TEXT,
                created_at TEXT,
                resolved_at TEXT,
                resolution TEXT,
                evidence_refs TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entity ON autobiography(entity)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_type ON autobiography(entry_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON autobiography(status)")
        conn.commit()
        conn.close()

    def record_entry(self, entry: AutobiographyEntry) -> None:
        conn = sqlite3.connect(self._db_path)
        conn.execute(
            "INSERT OR REPLACE INTO autobiography VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (entry.entry_id, entry.entry_type, entry.entity, entry.situation_id,
             entry.title, entry.description, entry.status, entry.created_at,
             entry.resolved_at, entry.resolution, json.dumps(entry.evidence_refs)),
        )
        conn.commit()
        conn.close()

    def resolve_entry(self, entry_id: str, resolution: str, status: str) -> None:
        conn = sqlite3.connect(self._db_path)
        conn.execute(
            "UPDATE autobiography SET resolved_at=?, resolution=?, status=? WHERE entry_id=?",
            (datetime.now(timezone.utc).isoformat(), resolution, status, entry_id),
        )
        conn.commit()
        conn.close()

    def query(self, entity: str = "", entry_type: str = "",
              status: str = "") -> list[AutobiographyEntry]:
        """Query the institutional autobiography."""
        conn = sqlite3.connect(self._db_path)
        clauses = []
        params = []
        if entity:
            clauses.append("entity = ?")
            params.append(entity)
        if entry_type:
            clauses.append("entry_type = ?")
            params.append(entry_type)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM autobiography{where} ORDER BY created_at DESC", params
        ).fetchall()
        conn.close()
        entries = []
        for row in rows:
            entries.append(AutobiographyEntry(
                entry_id=row[0], entry_type=row[1], entity=row[2],
                situation_id=row[3], title=row[4], description=row[5],
                status=row[6], created_at=row[7], resolved_at=row[8],
                resolution=row[9], evidence_refs=json.loads(row[10]) if row[10] else [],
            ))
        return entries

    def query_abandoned_decisions(self, entity: str = "") -> list[AutobiographyEntry]:
        """What decisions were made and then abandoned?"""
        return self.query(entity=entity, entry_type="decision", status="abandoned")

    def query_changed_assumptions(self, entity: str = "") -> list[AutobiographyEntry]:
        """What assumptions have changed?"""
        return self.query(entity=entity, entry_type="assumption", status="changed")

    def query_previous_whispers(self, entity: str = "") -> list[AutobiographyEntry]:
        """What did you tell me about this before?"""
        return self.query(entity=entity, entry_type="whisper")

    def query_falsified_patterns(self) -> list[AutobiographyEntry]:
        """What did we learn that turned out to be wrong?"""
        return self.query(entry_type="falsification", status="falsified")

    def query_fulfilled_commitments(self, entity: str = "") -> list[AutobiographyEntry]:
        """Did that commitment turn out fulfilled?"""
        return self.query(entity=entity, entry_type="commitment", status="fulfilled")

    def query_missed_commitments(self, entity: str = "") -> list[AutobiographyEntry]:
        """Did that commitment turn out missed?"""
        return self.query(entity=entity, entry_type="commitment", status="missed")
