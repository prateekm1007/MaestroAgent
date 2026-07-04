"""
Persistence layer for the OEM.

Survives restart. Cold boot reconstructs OEM. Incremental updates only.

Storage: SQLite (zero-config, file-based, perfect for single-org design partner phase).
Production: swap SQLiteStore for PostgresStore — same interface.

What persists:
  - ExecutionModel state (health, knowledge, approvals, risks)
  - All LearningObjects
  - All Patterns (from PatternDetector)
  - All OrganizationalLaws
  - All Receipts and ReceiptChains
  - All processed signal IDs (for deduplication)
  - ContradictionLog (append-only history)
  - Connected providers

What does NOT persist:
  - ModelDelta (transient — produced per signal, not needed after application)
  - EvidenceGraph (rebuilt from model state — it's a view, not a store)

Cold boot:
  1. Load all persisted state from SQLite
  2. Reconstruct ExecutionModel with all LOs, patterns, laws, receipts
  3. Continue processing new signals incrementally
  No full recompute. No reprocessing of historical signals.
"""

from __future__ import annotations

import json
from maestro_db import sqlite_compat as sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from maestro_oem.contradiction import ContradictionEvent, ContradictionLog, FeedbackAction
from maestro_oem.law import LawStatus, OrganizationalLaw
from maestro_oem.learning_object import LearningObject
from maestro_oem.engine import OEMEngine
from maestro_oem.model import ExecutionHealth, ExecutionModel, KnowledgeGraph, ApprovalNetwork, RiskSurface
from maestro_oem.pattern import Pattern, PatternDetector, PatternType
from maestro_oem.receipt import Receipt, ReceiptChain
from maestro_oem.signal import ExecutionSignal, SignalProvider, SignalType


SCHEMA_VERSION = 1

MIGRATION_SQL = """
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- Signals (for deduplication and replay)
CREATE TABLE IF NOT EXISTS signals (
    signal_id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    actor TEXT NOT NULL,
    team TEXT NOT NULL,
    artifact TEXT NOT NULL,
    decision INTEGER NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 1.0,
    metadata TEXT NOT NULL DEFAULT '{}',
    provider TEXT NOT NULL
);

-- Learning Objects
CREATE TABLE IF NOT EXISTS learning_objects (
    lo_id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    entities TEXT NOT NULL DEFAULT '[]',
    artifacts TEXT NOT NULL DEFAULT '[]',
    signal_ids TEXT NOT NULL DEFAULT '[]',
    providers TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 0.0,
    evidence_count INTEGER NOT NULL DEFAULT 0,
    contradiction_count INTEGER NOT NULL DEFAULT 0,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}'
);

-- Patterns
CREATE TABLE IF NOT EXISTS patterns (
    pattern_id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    description TEXT NOT NULL,
    learning_object_ids TEXT NOT NULL DEFAULT '[]',
    strength REAL NOT NULL DEFAULT 0.0,
    coverage INTEGER NOT NULL DEFAULT 0,
    providers TEXT NOT NULL DEFAULT '[]',
    first_detected TEXT NOT NULL,
    last_detected TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}'
);

-- Laws
CREATE TABLE IF NOT EXISTS laws (
    law_id TEXT PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    statement TEXT NOT NULL,
    condition TEXT NOT NULL,
    outcome TEXT NOT NULL,
    status TEXT NOT NULL,
    evidence_count INTEGER NOT NULL DEFAULT 0,
    counter_examples INTEGER NOT NULL DEFAULT 0,
    validated_runtimes INTEGER NOT NULL DEFAULT 0,
    failed_runtimes INTEGER NOT NULL DEFAULT 0,
    pattern_ids TEXT NOT NULL DEFAULT '[]',
    signal_ids TEXT NOT NULL DEFAULT '[]',
    providers TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 0.0,
    known_to_leadership INTEGER NOT NULL DEFAULT 0,
    first_inferred TEXT NOT NULL,
    last_validated TEXT,
    drift_detected INTEGER NOT NULL DEFAULT 0,
    metadata TEXT NOT NULL DEFAULT '{}'
);

-- Receipts
CREATE TABLE IF NOT EXISTS receipts (
    receipt_id TEXT PRIMARY KEY,
    signal_id TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    signal_provider TEXT NOT NULL,
    signal_timestamp TEXT NOT NULL,
    signal_actor TEXT NOT NULL,
    signal_artifact TEXT NOT NULL,
    oem_change TEXT NOT NULL,
    oem_target TEXT NOT NULL,
    change_timestamp TEXT NOT NULL,
    change_data TEXT NOT NULL DEFAULT '{}'
);

-- Receipt chains (target → list of receipt IDs)
CREATE TABLE IF NOT EXISTS receipt_chains (
    target TEXT PRIMARY KEY,
    target_type TEXT NOT NULL DEFAULT 'auto',
    receipt_ids TEXT NOT NULL DEFAULT '[]'
);

-- Contradiction events (append-only)
CREATE TABLE IF NOT EXISTS contradiction_events (
    event_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    action TEXT NOT NULL,
    reasoning TEXT NOT NULL DEFAULT '',
    predicted_confidence REAL NOT NULL DEFAULT 0.0,
    predicted_outcome TEXT NOT NULL DEFAULT '',
    actual_outcome TEXT NOT NULL DEFAULT '',
    affected_laws TEXT NOT NULL DEFAULT '[]',
    confidence_before TEXT NOT NULL DEFAULT '{}',
    confidence_after TEXT NOT NULL DEFAULT '{}',
    law_status_changes TEXT NOT NULL DEFAULT '{}',
    actor TEXT NOT NULL DEFAULT '',
    metadata TEXT NOT NULL DEFAULT '{}'
);

-- Model state (single row — the current OEM state)
CREATE TABLE IF NOT EXISTS model_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    health TEXT NOT NULL DEFAULT '{}',
    knowledge TEXT NOT NULL DEFAULT '{}',
    approvals TEXT NOT NULL DEFAULT '{}',
    risks TEXT NOT NULL DEFAULT '{}',
    connected_providers TEXT NOT NULL DEFAULT '[]',
    next_law_number INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_updated TEXT NOT NULL
);

-- Processed signal IDs (for deduplication)
CREATE TABLE IF NOT EXISTS processed_signals (
    signal_id TEXT PRIMARY KEY,
    processed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS situations (
    entity TEXT PRIMARY KEY,
    situation_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class OEMStore:
    """
    Persistence interface for the OEM.

    SQLite implementation. Swap for PostgresStore in production — same interface.
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None
        self._connect()

    def _connect(self) -> None:
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self) -> None:
        """Run migrations."""
        cursor = self._conn.cursor()
        cursor.executescript(MIGRATION_SQL)

        # Check schema version
        cursor.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
        row = cursor.fetchone()
        current = row["version"] if row else 0

        if current < 1:
            cursor.execute(
                "INSERT OR REPLACE INTO schema_version (version, applied_at) VALUES (?, ?)",
                (1, datetime.now(timezone.utc).isoformat()),
            )

        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ─── Signals ───

    def save_signal(self, signal: ExecutionSignal) -> None:
        cursor = self._conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO signals
            (signal_id, type, timestamp, actor, team, artifact, decision, confidence, metadata, provider)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(signal.signal_id),
            signal.type.value,
            signal.timestamp.isoformat(),
            signal.actor,
            signal.team,
            signal.artifact,
            int(signal.decision),
            signal.confidence,
            json.dumps(signal.metadata),
            signal.provider.value,
        ))
        self._conn.commit()

    def get_processed_signal_ids(self) -> set[str]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT signal_id FROM processed_signals")
        return {row["signal_id"] for row in cursor.fetchall()}

    def mark_signal_processed(self, signal_id: UUID) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO processed_signals (signal_id, processed_at) VALUES (?, ?)",
            (str(signal_id), datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    def get_all_signals(self) -> list[ExecutionSignal]:
        """Load all signals (for replay)."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM signals ORDER BY timestamp")
        signals = []
        for row in cursor.fetchall():
            signals.append(ExecutionSignal(
                signal_id=UUID(row["signal_id"]),
                type=SignalType(row["type"]),
                timestamp=datetime.fromisoformat(row["timestamp"]),
                actor=row["actor"],
                team=row["team"],
                artifact=row["artifact"],
                decision=bool(row["decision"]),
                confidence=row["confidence"],
                metadata=json.loads(row["metadata"]),
                provider=SignalProvider(row["provider"]),
            ))
        return signals

    # ─── Learning Objects ───

    def save_learning_object(self, lo: LearningObject) -> None:
        cursor = self._conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO learning_objects
            (lo_id, type, title, description, entities, artifacts, signal_ids, providers,
             confidence, evidence_count, contradiction_count, first_seen, last_seen, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(lo.lo_id),
            lo.type.value,
            lo.title,
            lo.description,
            json.dumps(lo.entities),
            json.dumps(lo.artifacts),
            json.dumps([str(sid) for sid in lo.signal_ids]),
            json.dumps(list(lo.providers)),
            lo.confidence,
            lo.evidence_count,
            lo.contradiction_count,
            lo.first_seen.isoformat(),
            lo.last_seen.isoformat(),
            json.dumps(lo.metadata),
        ))
        self._conn.commit()

    def load_learning_objects(self) -> dict[UUID, LearningObject]:
        from maestro_oem.learning_object import LearningObjectType
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM learning_objects")
        los = {}
        for row in cursor.fetchall():
            lo = LearningObject(
                lo_id=UUID(row["lo_id"]),
                type=LearningObjectType(row["type"]),
                title=row["title"],
                description=row["description"],
                entities=json.loads(row["entities"]),
                artifacts=json.loads(row["artifacts"]),
                signal_ids=[UUID(sid) for sid in json.loads(row["signal_ids"])],
                providers=set(json.loads(row["providers"])),
                confidence=row["confidence"],
                evidence_count=row["evidence_count"],
                contradiction_count=row["contradiction_count"],
                first_seen=datetime.fromisoformat(row["first_seen"]),
                last_seen=datetime.fromisoformat(row["last_seen"]),
                metadata=json.loads(row["metadata"]),
            )
            los[lo.lo_id] = lo
        return los

    # ─── Patterns ───

    def save_pattern(self, pattern: Pattern) -> None:
        cursor = self._conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO patterns
            (pattern_id, type, description, learning_object_ids, strength, coverage,
             providers, first_detected, last_detected, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(pattern.pattern_id),
            pattern.type.value,
            pattern.description,
            json.dumps([str(pid) for pid in pattern.learning_object_ids]),
            pattern.strength,
            pattern.coverage,
            json.dumps(list(pattern.providers)),
            pattern.first_detected.isoformat(),
            pattern.last_detected.isoformat(),
            json.dumps(pattern.metadata),
        ))
        self._conn.commit()

    def load_patterns(self) -> list[Pattern]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM patterns")
        patterns = []
        for row in cursor.fetchall():
            p = Pattern(
                pattern_id=UUID(row["pattern_id"]),
                type=PatternType(row["type"]),
                description=row["description"],
                learning_object_ids=[UUID(pid) for pid in json.loads(row["learning_object_ids"])],
                strength=row["strength"],
                coverage=row["coverage"],
                providers=set(json.loads(row["providers"])),
                first_detected=datetime.fromisoformat(row["first_detected"]),
                last_detected=datetime.fromisoformat(row["last_detected"]),
                metadata=json.loads(row["metadata"]),
            )
            patterns.append(p)
        return patterns

    # ─── Laws ───

    def save_law(self, law: OrganizationalLaw) -> None:
        cursor = self._conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO laws
            (law_id, code, statement, condition, outcome, status, evidence_count,
             counter_examples, validated_runtimes, failed_runtimes, pattern_ids,
             signal_ids, providers, confidence, known_to_leadership, first_inferred,
             last_validated, drift_detected, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(law.law_id),
            law.code,
            law.statement,
            law.condition,
            law.outcome,
            law.status.value,
            law.evidence_count,
            law.counter_examples,
            law.validated_runtimes,
            law.failed_runtimes,
            json.dumps([str(pid) for pid in law.pattern_ids]),
            json.dumps([str(sid) for sid in law.signal_ids]),
            json.dumps(list(law.providers)),
            law.confidence,
            int(law.known_to_leadership),
            law.first_inferred.isoformat(),
            law.last_validated.isoformat() if law.last_validated else None,
            int(law.drift_detected),
            json.dumps(law.metadata),
        ))
        self._conn.commit()

    def load_laws(self) -> dict[str, OrganizationalLaw]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM laws")
        laws = {}
        for row in cursor.fetchall():
            law = OrganizationalLaw(
                law_id=UUID(row["law_id"]),
                code=row["code"],
                statement=row["statement"],
                condition=row["condition"],
                outcome=row["outcome"],
                status=LawStatus(row["status"]),
                evidence_count=row["evidence_count"],
                counter_examples=row["counter_examples"],
                validated_runtimes=row["validated_runtimes"],
                failed_runtimes=row["failed_runtimes"],
                pattern_ids=[UUID(pid) for pid in json.loads(row["pattern_ids"])],
                signal_ids=[UUID(sid) for sid in json.loads(row["signal_ids"])],
                providers=set(json.loads(row["providers"])),
                confidence=row["confidence"],
                known_to_leadership=bool(row["known_to_leadership"]),
                first_inferred=datetime.fromisoformat(row["first_inferred"]),
                last_validated=datetime.fromisoformat(row["last_validated"]) if row["last_validated"] else None,
                drift_detected=bool(row["drift_detected"]),
                metadata=json.loads(row["metadata"]),
            )
            laws[law.code] = law
        return laws

    # ─── Situations (Phase 2: Situation persistence) ───

    def save_situation(self, entity: str, situation: Any) -> None:
        """Save a Situation for an entity (keyed by entity name)."""
        cursor = self._conn.cursor()
        sit_dict = situation.to_dict() if hasattr(situation, "to_dict") else situation
        cursor.execute("""
            INSERT OR REPLACE INTO situations
            (entity, situation_json, updated_at)
            VALUES (?, ?, ?)
        """, (
            entity,
            json.dumps(sit_dict, default=str),
            datetime.now(timezone.utc).isoformat(),
        ))
        self._conn.commit()

    def load_situations(self) -> dict[str, Any]:
        """Load all saved Situations, keyed by entity."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT entity, situation_json FROM situations")
        rows = cursor.fetchall()
        return {
            row["entity"]: json.loads(row["situation_json"])
            for row in rows
        } if rows else {}

    def load_situation(self, entity: str) -> Any | None:
        """Load a single Situation for an entity."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT situation_json FROM situations WHERE entity = ?", (entity,))
        row = cursor.fetchone()
        if not row:
            return None
        return json.loads(row["situation_json"])

    # ─── Receipts ───

    def save_receipt(self, receipt: Receipt) -> None:
        cursor = self._conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO receipts
            (receipt_id, signal_id, signal_type, signal_provider, signal_timestamp,
             signal_actor, signal_artifact, oem_change, oem_target, change_timestamp, change_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(receipt.receipt_id),
            str(receipt.signal_id),
            receipt.signal_type,
            receipt.signal_provider,
            receipt.signal_timestamp.isoformat(),
            receipt.signal_actor,
            receipt.signal_artifact,
            receipt.oem_change,
            receipt.oem_target,
            receipt.change_timestamp.isoformat(),
            json.dumps(receipt.change_data),
        ))
        self._conn.commit()

    def load_receipt_chains(self) -> dict[str, ReceiptChain]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM receipt_chains")
        chains = {}
        for row in cursor.fetchall():
            target = row["target"]
            receipt_ids = json.loads(row["receipt_ids"])
            chain = ReceiptChain(
                target=target,
                target_type=row["target_type"],
            )
            # Load receipts by ID
            for rid in receipt_ids:
                cursor.execute("SELECT * FROM receipts WHERE receipt_id = ?", (rid,))
                r = cursor.fetchone()
                if r:
                    chain.add(Receipt(
                        receipt_id=UUID(r["receipt_id"]),
                        signal_id=UUID(r["signal_id"]),
                        signal_type=r["signal_type"],
                        signal_provider=r["signal_provider"],
                        signal_timestamp=datetime.fromisoformat(r["signal_timestamp"]),
                        signal_actor=r["signal_actor"],
                        signal_artifact=r["signal_artifact"],
                        oem_change=r["oem_change"],
                        oem_target=r["oem_target"],
                        change_timestamp=datetime.fromisoformat(r["change_timestamp"]),
                        change_data=json.loads(r["change_data"]),
                    ))
            chains[target] = chain
        return chains

    def save_receipt_chain(self, chain: ReceiptChain) -> None:
        cursor = self._conn.cursor()
        receipt_ids = [str(r.receipt_id) for r in chain.receipts]
        cursor.execute("""
            INSERT OR REPLACE INTO receipt_chains
            (target, target_type, receipt_ids)
            VALUES (?, ?, ?)
        """, (
            chain.target,
            chain.target_type,
            json.dumps(receipt_ids),
        ))
        # Also save individual receipts
        for receipt in chain.receipts:
            self.save_receipt(receipt)
        self._conn.commit()

    # ─── Contradiction Events ───

    def save_contradiction_event(self, event: ContradictionEvent) -> None:
        cursor = self._conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO contradiction_events
            (event_id, timestamp, target_type, target_id, action, reasoning,
             predicted_confidence, predicted_outcome, actual_outcome, affected_laws,
             confidence_before, confidence_after, law_status_changes, actor, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(event.event_id),
            event.timestamp.isoformat(),
            event.target_type,
            event.target_id,
            event.action.value,
            event.reasoning,
            event.predicted_confidence,
            event.predicted_outcome,
            event.actual_outcome,
            json.dumps(event.affected_laws),
            json.dumps(event.confidence_before),
            json.dumps(event.confidence_after),
            json.dumps(event.law_status_changes),
            event.actor,
            json.dumps(event.metadata),
        ))
        self._conn.commit()

    def load_contradiction_log(self) -> ContradictionLog:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM contradiction_events ORDER BY timestamp")
        log = ContradictionLog()
        for row in cursor.fetchall():
            event = ContradictionEvent(
                event_id=UUID(row["event_id"]),
                timestamp=datetime.fromisoformat(row["timestamp"]),
                target_type=row["target_type"],
                target_id=row["target_id"],
                action=FeedbackAction(row["action"]),
                reasoning=row["reasoning"],
                predicted_confidence=row["predicted_confidence"],
                predicted_outcome=row["predicted_outcome"],
                actual_outcome=row["actual_outcome"],
                affected_laws=json.loads(row["affected_laws"]),
                confidence_before=json.loads(row["confidence_before"]),
                confidence_after=json.loads(row["confidence_after"]),
                law_status_changes=json.loads(row["law_status_changes"]),
                actor=row["actor"],
                metadata=json.loads(row["metadata"]),
            )
            log.append(event)
        return log

    # ─── Model State ───

    def save_model_state(self, model: ExecutionModel) -> None:
        """Save the ENTIRE model state — health, knowledge, approvals, risks,
        AND cognitive state (laws, learning_objects, patterns).

        Phase 4.2 fix (auditor's Gap 2): before this fix, save_model_state()
        only saved health/knowledge/approvals/risks but NOT laws/LOs/patterns.
        Those were saved by separate methods (save_law, save_learning_object,
        save_pattern). Callers like oem_state.py:_save_model_state() called
        BOTH save_model_state() AND the separate methods. But direct callers
        who used only save_model_state() lost cognitive state on restart.
        Now save_model_state() saves EVERYTHING.
        """
        cursor = self._conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO model_state
            (id, health, knowledge, approvals, risks, connected_providers,
             next_law_number, created_at, last_updated)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            model.health.model_dump_json(),
            _serialize_knowledge(model.knowledge),
            model.approvals.model_dump_json(),
            model.risks.model_dump_json(),
            json.dumps(list(model.connected_providers)),
            model.next_law_number,
            model.created_at.isoformat(),
            model.last_updated.isoformat(),
        ))
        self._conn.commit()

        # Also save cognitive state (laws, learning_objects, patterns)
        for law in model.laws.values():
            self.save_law(law)
        for lo in model.learning_objects.values():
            self.save_learning_object(lo)
        if hasattr(model, 'patterns') and model.patterns:
            for pattern in model.patterns:
                self.save_pattern(pattern)

    def load_model_state(self) -> dict[str, Any] | None:
        """Load the ENTIRE model state — health, knowledge, approvals, risks,
        AND cognitive state (laws, learning_objects, patterns).

        Phase 4.2 fix (auditor's Gap 2): before this fix, load_model_state()
        returned only health/knowledge/approvals/risks but NOT laws/LOs/
        patterns. Callers who used load_model_state() directly (not via
        oem_state.py:_load_model_state()) got partial state — cognitive
        state was lost. Now load_model_state() returns EVERYTHING.
        """
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM model_state WHERE id = 1")
        row = cursor.fetchone()
        if not row:
            return None

        health = ExecutionHealth.model_validate_json(row["health"])
        approvals = ApprovalNetwork.model_validate_json(row["approvals"])
        risks = RiskSurface.model_validate_json(row["risks"])
        knowledge = _deserialize_knowledge(row["knowledge"])

        # Phase 4.2 fix: also load cognitive state
        laws = self.load_laws()
        learning_objects = self.load_learning_objects()
        patterns = self.load_patterns()

        return {
            "health": health,
            "knowledge": knowledge,
            "approvals": approvals,
            "risks": risks,
            "connected_providers": set(json.loads(row["connected_providers"])),
            "next_law_number": row["next_law_number"],
            "created_at": datetime.fromisoformat(row["created_at"]),
            "last_updated": datetime.fromisoformat(row["last_updated"]),
            # Phase 4.2 fix: cognitive state now included
            "laws": laws,
            "learning_objects": learning_objects,
            "patterns": patterns,
        }


# ─── Serialization helpers for defaultdict-based fields ───

def _serialize_knowledge(kg: KnowledgeGraph) -> str:
    """Serialize KnowledgeGraph (has defaultdict fields)."""
    return json.dumps({
        "expertise": {k: list(v) for k, v in kg.expertise.items()},
        "influence": {k: v for k, v in kg.influence.items()},
        "domain_holders": {k: list(v) for k, v in kg.domain_holders.items()},
        "collaboration": {k: list(v) for k, v in kg.collaboration.items()},
        "artifact_authors": {k: list(v) for k, v in kg.artifact_authors.items()},
    })


def _deserialize_knowledge(data: str) -> KnowledgeGraph:
    """Deserialize KnowledgeGraph."""
    d = json.loads(data)
    kg = KnowledgeGraph()
    kg.expertise = {k: set(v) for k, v in d.get("expertise", {}).items()}
    kg.influence = {k: v for k, v in d.get("influence", {}).items()}
    kg.domain_holders = {k: set(v) for k, v in d.get("domain_holders", {}).items()}
    kg.collaboration = {k: set(v) for k, v in d.get("collaboration", {}).items()}
    kg.artifact_authors = {k: set(v) for k, v in d.get("artifact_authors", {}).items()}
    return kg


# ─── High-level persistence API ───

class PersistentOEM:
    """
    Wraps OEMEngine with automatic persistence.

    Every signal processed is saved. Every law/LO/pattern update is saved.
    On restart, cold boot reconstructs the full OEM from SQLite — no reprocessing.

    Usage:
        # First run
        persistent = PersistentOEM(db_path="maestro.db")
        persistent.ingest(signals)
        persistent.close()

        # Restart (cold boot)
        persistent = PersistentOEM(db_path="maestro.db")
        model = persistent.get_model()  # Fully reconstructed — no reprocessing
        # Continue with new signals
        persistent.ingest(new_signals)
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.store = OEMStore(db_path)
        self.engine = OEMEngine()

        # Cold boot: reconstruct from persisted state
        self._load()

    def _load(self) -> None:
        """Cold boot: reconstruct OEM from persisted state. No full recompute."""
        model_state = self.store.load_model_state()
        if model_state is None:
            # Fresh start — no persisted state
            return

        model = self.engine.get_model()

        # Restore model state
        model.health = model_state["health"]
        model.knowledge = model_state["knowledge"]
        model.approvals = model_state["approvals"]
        model.risks = model_state["risks"]
        model.connected_providers = model_state["connected_providers"]
        model.next_law_number = model_state["next_law_number"]
        model.created_at = model_state["created_at"]
        model.last_updated = model_state["last_updated"]

        # Restore learning objects
        model.learning_objects = self.store.load_learning_objects()

        # Restore patterns
        patterns = self.store.load_patterns()
        model.pattern_detector.patterns = patterns

        # Restore laws
        model.laws = self.store.load_laws()

        # Restore receipt chains
        model.receipt_chains = self.store.load_receipt_chains()

        # Restore processed signal IDs (for deduplication)
        processed = self.store.get_processed_signal_ids()
        model.processed_signals = [UUID(sid) for sid in processed]

    def _save(self) -> None:
        """Save entire model state to persistence."""
        model = self.engine.get_model()
        self.store.save_model_state(model)

        # Save all learning objects
        for lo in model.learning_objects.values():
            self.store.save_learning_object(lo)

        # Save all patterns
        for pattern in model.pattern_detector.patterns:
            self.store.save_pattern(pattern)

        # Save all laws
        for law in model.laws.values():
            self.store.save_law(law)

        # Save receipt chains
        for target, chain in model.receipt_chains.items():
            self.store.save_receipt_chain(chain)

    def ingest(self, signals: list[ExecutionSignal]) -> list:
        """
        Process signals and persist all changes.

        Each signal is:
        1. Saved to the signals table
        2. Processed by the OEM (incremental update)
        3. Marked as processed
        4. Model state saved
        """
        from maestro_oem.model import ModelDelta

        deltas: list[ModelDelta] = []
        for signal in signals:
            # Save signal first
            self.store.save_signal(signal)

            # Process
            delta = self.engine.ingest_one(signal)
            deltas.append(delta)

            # Mark processed
            self.store.mark_signal_processed(signal.signal_id)

        # Save model state after batch
        self._save()

        return deltas

    def ingest_one(self, signal: ExecutionSignal):
        """Process a single signal and persist."""
        self.store.save_signal(signal)
        delta = self.engine.ingest_one(signal)
        self.store.mark_signal_processed(signal.signal_id)
        self._save()
        return delta

    def get_model(self) -> ExecutionModel:
        return self.engine.get_model()

    def get_summary(self) -> dict[str, Any]:
        return self.engine.get_summary()

    def save_contradiction(self, event: ContradictionEvent) -> None:
        """Persist a contradiction event (append-only)."""
        self.store.save_contradiction_event(event)

    def load_contradiction_log(self) -> ContradictionLog:
        """Load the full contradiction log from persistence."""
        return self.store.load_contradiction_log()

    def close(self) -> None:
        """Save and close."""
        self._save()
        self.store.close()
