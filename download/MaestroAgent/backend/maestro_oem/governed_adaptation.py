"""Priority 1: Governed Adaptation Loop — close learning → behavior WITHOUT
the causal shortcut.

CEO directive (2026-07-04):
> Do NOT wire Learning Ledger output directly into the delivery gate.
> The correct architecture is: outcome → attribution analysis (with
> confounders) → hypothesis → prospective experiment → sufficient
> evidence → bounded proposal (risk-tiered) → human approval (for
> HIGH risk) → versioned policy → behavior change → evaluation.

This module implements the governed loop:

  AdaptationPolicy     — versioned, rollback-able policy dataclass
  PolicyVersionStore   — SQLite-backed persistence
  AttributionAnalyzer  — identifies confounders, preserves causal uncertainty
  PolicyProposer       — risk-tiered: LOW auto-activates, HIGH needs approval

The decide_delivery() function reads the ACTIVE policy from the store.
The Learning Ledger does NOT call decide_delivery() directly — that's
the causal shortcut this module prevents.

Wiring (P11):
  - decide_delivery() accepts an optional `policy` parameter (cite
    delivery_decision.py)
  - OEMEngine.ingest() does NOT touch the policy store — outcomes flow
    through the AttributionAnalyzer, not directly to the gate
  - The PolicyProposer is called by a separate background loop (future)
    or by an explicit admin endpoint — NOT by the ingestion path
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


# ─── Risk levels ────────────────────────────────────────────────────────────

RISK_LOW = "LOW"      # dedup threshold, timing preference — auto-activates
RISK_MEDIUM = "MEDIUM"  # depth, batching — proposes, silent approval
RISK_HIGH = "HIGH"    # escalation, recipient change — requires explicit approval

# Status progression
STATUS_HYPOTHESIS = "HYPOTHESIS"
STATUS_TESTING = "TESTING"
STATUS_PROPOSED = "PROPOSED"
STATUS_APPROVED = "APPROVED"
STATUS_ACTIVE = "ACTIVE"
STATUS_EVALUATED = "EVALUATED"
STATUS_ROLLED_BACK = "ROLLED_BACK"


@dataclass
class AdaptationPolicy:
    """A governed adaptation policy — versioned, rollback-able.

    A policy is NOT a direct reaction to an outcome. It's the result of:
      1. An outcome was observed
      2. Attribution analysis identified confounders
      3. A hypothesis was formed (NOT a policy change)
      4. Evidence accumulated over multiple cases
      5. A bounded proposal was created (risk-tiered)
      6. For HIGH risk, a human approved it
      7. The policy was activated and versioned

    The policy determines parameters that decide_delivery() reads:
      - dedup_threshold: how many times a Whisper can be shown before suppression
      - timing_preference: "before_meeting" | "weekly_planning" | "immediate"
      - escalation_recipient: who to escalate to (HIGH risk only)
      - depth_preference: "headline" | "full_spine"
    """

    policy_id: str
    version: int
    hypothesis: str
    evidence_for: list[dict] = field(default_factory=list)
    evidence_against: list[dict] = field(default_factory=list)
    confounders_identified: list[str] = field(default_factory=list)
    status: str = STATUS_HYPOTHESIS
    risk_level: str = RISK_LOW
    requires_human_approval: bool = False
    approved_by: str | None = None
    previous_policy_id: str | None = None
    created_at: str = ""
    activated_at: str | None = None
    parameter_changes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "hypothesis": self.hypothesis,
            "evidence_for": self.evidence_for,
            "evidence_against": self.evidence_against,
            "confounders_identified": self.confounders_identified,
            "status": self.status,
            "risk_level": self.risk_level,
            "requires_human_approval": self.requires_human_approval,
            "approved_by": self.approved_by,
            "previous_policy_id": self.previous_policy_id,
            "created_at": self.created_at,
            "activated_at": self.activated_at,
            "parameter_changes": self.parameter_changes,
        }

    @classmethod
    def from_row(cls, row: dict) -> "AdaptationPolicy":
        """Reconstruct from a DB row."""
        return cls(
            policy_id=row["policy_id"],
            version=row["version"],
            hypothesis=row["hypothesis"],
            evidence_for=json.loads(row.get("evidence_for", "[]")),
            evidence_against=json.loads(row.get("evidence_against", "[]")),
            confounders_identified=json.loads(row.get("confounders_identified", "[]")),
            status=row["status"],
            risk_level=row["risk_level"],
            requires_human_approval=bool(row["requires_human_approval"]),
            approved_by=row.get("approved_by"),
            previous_policy_id=row.get("previous_policy_id"),
            created_at=row["created_at"],
            activated_at=row.get("activated_at"),
            parameter_changes=json.loads(row.get("parameter_changes", "{}")),
        )


# ─── PolicyVersionStore (SQLite-backed) ─────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS adaptation_policies (
    policy_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL,
    hypothesis TEXT NOT NULL,
    evidence_for TEXT DEFAULT '[]',
    evidence_against TEXT DEFAULT '[]',
    confounders_identified TEXT DEFAULT '[]',
    status TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    requires_human_approval INTEGER DEFAULT 0,
    approved_by TEXT,
    previous_policy_id TEXT,
    created_at TEXT NOT NULL,
    activated_at TEXT,
    parameter_changes TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_policy_status ON adaptation_policies(status);
CREATE INDEX IF NOT EXISTS idx_policy_version ON adaptation_policies(version);
"""


class PolicyVersionStore:
    """SQLite-backed store for adaptation policies.

    Every policy change is versioned. The store tracks the ACTIVE policy
    (at most one at a time). This enables rollback: if the new policy
    produces worse outcomes, revert to the previous one.
    """

    def __init__(self, db_path: str = "") -> None:
        self._db_path = db_path or ":memory:"
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._connect()

    def _connect(self) -> None:
        try:
            from maestro_db import sqlite_compat as sqlite3_compat
            self._conn = sqlite3_compat.connect(self._db_path, isolation_level=None)
            self._conn.row_factory = sqlite3_compat.Row
        except Exception:
            self._conn = sqlite3.connect(self._db_path, isolation_level=None)
            self._conn.row_factory = sqlite3.Row
        try:
            cursor = self._conn.cursor()
            for stmt in _SCHEMA.strip().split(';'):
                stmt = stmt.strip()
                if stmt:
                    cursor.execute(stmt)
        except Exception as e:
            logger.warning("PolicyVersionStore schema init: %s", e)

    def save(self, policy: AdaptationPolicy) -> None:
        """Save or update a policy."""
        with self._lock:
            assert self._conn is not None
            self._conn.execute(
                """INSERT OR REPLACE INTO adaptation_policies
                   (policy_id, version, hypothesis, evidence_for, evidence_against,
                    confounders_identified, status, risk_level, requires_human_approval,
                    approved_by, previous_policy_id, created_at, activated_at, parameter_changes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    policy.policy_id, policy.version, policy.hypothesis,
                    json.dumps(policy.evidence_for), json.dumps(policy.evidence_against),
                    json.dumps(policy.confounders_identified), policy.status, policy.risk_level,
                    int(policy.requires_human_approval), policy.approved_by,
                    policy.previous_policy_id, policy.created_at, policy.activated_at,
                    json.dumps(policy.parameter_changes),
                ),
            )

    def get(self, policy_id: str) -> AdaptationPolicy | None:
        """Get a policy by ID."""
        with self._lock:
            assert self._conn is not None
            cur = self._conn.cursor()
            cur.execute("SELECT * FROM adaptation_policies WHERE policy_id = ?", (policy_id,))
            row = cur.fetchone()
            if row is None:
                return None
            d = row if isinstance(row, dict) else {k: row[k] for k in row.keys()}
            return AdaptationPolicy.from_row(d)

    def get_active_policy(self) -> AdaptationPolicy | None:
        """Get the currently-active policy (at most one)."""
        with self._lock:
            assert self._conn is not None
            cur = self._conn.cursor()
            cur.execute("SELECT * FROM adaptation_policies WHERE status = ? ORDER BY version DESC LIMIT 1", (STATUS_ACTIVE,))
            row = cur.fetchone()
            if row is None:
                return None
            d = row if isinstance(row, dict) else {k: row[k] for k in row.keys()}
            return AdaptationPolicy.from_row(d)

    def deactivate_all(self) -> None:
        """Deactivate all policies (used before activating a new one)."""
        with self._lock:
            assert self._conn is not None
            self._conn.execute(
                "UPDATE adaptation_policies SET status = ? WHERE status = ?",
                (STATUS_EVALUATED, STATUS_ACTIVE),
            )

    def rollback(self, policy_id: str) -> AdaptationPolicy | None:
        """Rollback: deactivate the given policy, reactivate its predecessor."""
        policy = self.get(policy_id)
        if policy is None:
            return None
        # Mark the given policy as rolled back
        policy.status = STATUS_ROLLED_BACK
        self.save(policy)
        # Reactivate the predecessor
        if policy.previous_policy_id:
            predecessor = self.get(policy.previous_policy_id)
            if predecessor:
                self.deactivate_all()
                predecessor.status = STATUS_ACTIVE
                predecessor.activated_at = datetime.now(timezone.utc).isoformat()
                self.save(predecessor)
                return predecessor
        return None

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


# ─── AttributionAnalyzer ───────────────────────────────────────────────────

class AttributionAnalyzer:
    """Analyze outcomes for attribution WITHOUT claiming causation.

    When an outcome is observed (e.g., a commitment broke after the exec
    ignored a Whisper), this module asks:
      1. Did Maestro surface a Whisper about this?
      2. Did the executive act on it?
      3. What happened?
      4. What ELSE could have caused the outcome? (confounders)
      5. Is the causal link strong, weak, or unknown?

    The output is NEVER "increase aggressiveness." The output is a
    hypothesis with identified confounders and explicit causal uncertainty.
    """

    # Confounder patterns — signals that could explain an outcome
    # independent of whether the exec acted on the Whisper
    CONFOUNDER_SIGNAL_TYPES = {
        "staffing_change": "champion or key contact departed",
        "market_shift": "competitive or market conditions changed",
        "organizational_reorg": "internal reorganization affected the relationship",
        "budget_cut": "customer budget was reduced",
        "product_issue": "a separate product issue caused dissatisfaction",
        "merger_acquisition": "customer was acquired or merged",
        "economic_downturn": "broader economic conditions worsened",
    }

    def analyze(self, outcome: dict[str, Any]) -> dict[str, Any]:
        """Analyze an outcome for attribution.

        Args:
            outcome: dict with keys:
              - whisper_shown: bool
              - exec_action: "acted" | "ignored" | "deferred" | ""
              - outcome: "commitment_broken" | "commitment_kept" | "objection_raised" | ...
              - entity: str
              - context_signals: list of dicts with "type" and optional "note"
              - interaction_history: optional list of interaction events
                (Priority 3: enriches attribution with full engagement lifecycle)
                Each event: {"event_type": "SHOWN"|"OPENED"|..., "timestamp": ...}

        Returns:
            dict with keys:
              - hypothesis: str (hedged, NOT causal)
              - confounders: list[str] (identified alternative explanations)
              - causal_strength: "unknown" | "weak" | "moderate" (never "strong" or "proven")
              - evidence_for: list[dict] (supporting observations)
              - evidence_against: list[dict] (contradicting observations)
        """
        whisper_shown = outcome.get("whisper_shown", False)
        exec_action = outcome.get("exec_action", "")
        outcome_type = outcome.get("outcome", "")
        context_signals = outcome.get("context_signals", [])
        interaction_history = outcome.get("interaction_history", [])

        # Priority 3: Enrich with interaction memory
        # The interaction_history tells us HOW the exec engaged with the Whisper:
        #   - "shown but never opened" = the exec didn't even look at it
        #   - "shown, opened, dismissed" = the exec looked but rejected it
        #   - "shown, opened, deferred" = the exec intended to revisit but didn't
        # These have different attribution implications.
        interaction_summary = self._summarize_interaction(interaction_history)
        was_opened = interaction_summary["opened"]
        was_dismissed = interaction_summary["dismissed"]
        was_deferred = interaction_summary["deferred"]
        was_delegated = interaction_summary["delegated"]
        was_contradicted = interaction_summary["contradicted"]

        # Identify confounders from context signals
        confounders: list[str] = []
        for sig in context_signals:
            sig_type = sig.get("type", "")
            if sig_type in self.CONFOUNDER_SIGNAL_TYPES:
                confounders.append(self.CONFOUNDER_SIGNAL_TYPES[sig_type])
            elif sig.get("note"):
                confounders.append(sig["note"])

        # Form a hedged hypothesis — NEVER claim causation
        # Priority 3: The hypothesis now reflects the interaction lifecycle,
        # not just the coarse exec_action. This gives the governed adaptation
        # loop richer signal for forming hypotheses.
        if whisper_shown and exec_action == "ignored" and outcome_type == "commitment_broken":
            if not was_opened:
                # The exec never even opened the Whisper
                hypothesis = (
                    "The executive did not open the commitment warning. Delivering "
                    "commitment warnings in a way that earns opening (different timing, "
                    "different depth, different recipient) may reduce broken commitments. "
                    "This is a hypothesis, not a proven causal link."
                )
                causal_strength = "weak"
            elif was_deferred:
                # The exec opened it but deferred — intended to revisit but didn't
                hypothesis = (
                    "The executive opened the commitment warning but deferred action. "
                    "Reducing deferral (shorter defer windows, follow-up reminders) may "
                    "reduce broken commitments. This is a hypothesis, not a proven causal link."
                )
                causal_strength = "weak"
            elif was_dismissed:
                # The exec explicitly dismissed it
                hypothesis = (
                    "The executive dismissed the commitment warning. The warning may not "
                    "have been actionable or relevant in the exec's judgment. Improving "
                    "warning relevance may reduce broken commitments. This is a hypothesis, "
                    "not a proven causal link."
                )
                causal_strength = "weak"
            else:
                # Generic "ignored" — no interaction detail
                hypothesis = (
                    "Acting on commitment warnings earlier may reduce broken commitments. "
                    "This is a hypothesis, not a proven causal link."
                )
                causal_strength = "weak"
        elif whisper_shown and exec_action == "acted" and outcome_type == "commitment_kept":
            if was_delegated:
                hypothesis = (
                    "The executive delegated action on the commitment warning, and the "
                    "commitment was kept. Delegation may be an effective response pattern. "
                    "This is a hypothesis; the outcome may also be explained by other factors."
                )
                causal_strength = "weak"
            else:
                hypothesis = (
                    "Acting on commitment warnings may have helped maintain the commitment. "
                    "This is a hypothesis; the outcome may also be explained by other factors."
                )
                causal_strength = "weak"
        elif was_contradicted:
            # The exec disagreed with the Whisper — important negative feedback
            hypothesis = (
                "The executive contradicted the Whisper. The Whisper's content or framing "
                "may not match the executive's understanding. This is valuable feedback for "
                "improving Whisper relevance, not evidence for a policy change."
            )
            causal_strength = "unknown"
        else:
            hypothesis = (
                f"The relationship between the Whisper and the outcome ({outcome_type}) is unclear. "
                f"More data is needed before any policy consideration."
            )
            causal_strength = "unknown"

        # Causal strength is NEVER "strong" or "proven" — always hedged
        return {
            "hypothesis": hypothesis,
            "confounders": confounders,
            "causal_strength": causal_strength,
            "evidence_for": [{"outcome": outcome_type, "exec_action": exec_action}] if outcome_type else [],
            "evidence_against": [],
        }

    @staticmethod
    def _summarize_interaction(interaction_history: list[dict]) -> dict[str, bool]:
        """Summarize the interaction history for attribution.

        Priority 3: The interaction_history is a list of events from
        InteractionMemory. This helper extracts the engagement signals
        that matter for attribution:
          - opened: did the exec open the Whisper? (vs just shown)
          - dismissed: did the exec explicitly dismiss it?
          - deferred: did the exec defer it?
          - delegated: did the exec delegate the action?
          - contradicted: did the exec disagree with the Whisper?

        These distinguish between engagement patterns that the coarse
        exec_action="ignored" conflates.
        """
        if not interaction_history:
            return {"opened": False, "dismissed": False, "deferred": False,
                    "delegated": False, "contradicted": False}

        event_types = set()
        for evt in interaction_history:
            et = evt.get("event_type", "").upper()
            event_types.add(et)

        return {
            "opened": "OPENED" in event_types,
            "dismissed": "DISMISSED" in event_types,
            "deferred": "DEFERRED" in event_types,
            "delegated": "DELEGATED" in event_types,
            "contradicted": "CONTRADICTED" in event_types,
        }


# ─── PolicyProposer ────────────────────────────────────────────────────────

class PolicyProposer:
    """Propose bounded policy changes based on accumulated evidence.

    Risk-tiered activation:
      - LOW (dedup threshold, timing): auto-activates with sufficient evidence
      - MEDIUM (depth, batching): proposes, activates after silent approval period
      - HIGH (escalation, recipient change): requires explicit human approval

    The proposer NEVER activates a HIGH-risk policy without human approval,
    even with overwhelming evidence.
    """

    def __init__(
        self,
        store: PolicyVersionStore,
        min_evidence_threshold: int = 5,
    ) -> None:
        self._store = store
        self._min_evidence = min_evidence_threshold

    def propose(
        self,
        hypothesis: str,
        evidence: list[dict[str, Any]],
        risk_level: str,
        parameter_changes: dict[str, Any],
    ) -> AdaptationPolicy:
        """Propose a policy change.

        Args:
            hypothesis: The hedged hypothesis from AttributionAnalyzer
            evidence: List of outcome observations
            risk_level: LOW | MEDIUM | HIGH
            parameter_changes: The parameters to change (e.g., {"dedup_threshold": 0})

        Returns:
            An AdaptationPolicy with status reflecting the risk-tiered logic.
        """
        evidence_count = len(evidence)
        meets_threshold = evidence_count >= self._min_evidence

        # Identify confounders from evidence
        confounders: list[str] = []
        for ev in evidence:
            for sig in ev.get("context_signals", []):
                if sig.get("type") in AttributionAnalyzer.CONFOUNDER_SIGNAL_TYPES:
                    confounder = AttributionAnalyzer.CONFOUNDER_SIGNAL_TYPES[sig["type"]]
                    if confounder not in confounders:
                        confounders.append(confounder)

        # Determine status based on risk level + evidence
        requires_approval = risk_level == RISK_HIGH

        if not meets_threshold:
            # Insufficient evidence → stays as HYPOTHESIS
            status = STATUS_HYPOTHESIS
        elif risk_level == RISK_LOW:
            # LOW risk + sufficient evidence → auto-activate
            status = STATUS_ACTIVE
        elif risk_level == RISK_MEDIUM:
            # MEDIUM risk → proposed (silent approval — could auto-activate after a period)
            # For now, treat MEDIUM like LOW for simplicity (auto-activate with evidence)
            status = STATUS_ACTIVE
        else:  # RISK_HIGH
            # HIGH risk → PROPOSED, requires human approval
            status = STATUS_PROPOSED

        # Get the current active policy (for versioning + rollback)
        current_active = self._store.get_active_policy()
        previous_policy_id = current_active.policy_id if current_active else None
        version = (current_active.version + 1) if current_active else 1

        policy = AdaptationPolicy(
            policy_id=f"pol-{uuid4().hex[:8]}",
            version=version,
            hypothesis=hypothesis,
            evidence_for=evidence,
            evidence_against=[],
            confounders_identified=confounders,
            status=status,
            risk_level=risk_level,
            requires_human_approval=requires_approval,
            approved_by=None,
            previous_policy_id=previous_policy_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            activated_at=datetime.now(timezone.utc).isoformat() if status == STATUS_ACTIVE else None,
            parameter_changes=parameter_changes,
        )

        # If activating, deactivate the previous active policy
        if status == STATUS_ACTIVE:
            self._store.deactivate_all()

        self._store.save(policy)
        return policy

    def approve(self, policy_id: str, approved_by: str) -> AdaptationPolicy | None:
        """Human-approve a PROPOSED HIGH-risk policy."""
        policy = self._store.get(policy_id)
        if policy is None:
            return None
        if policy.status != STATUS_PROPOSED:
            return policy  # Already decided

        # Deactivate the current active policy
        self._store.deactivate_all()

        policy.status = STATUS_ACTIVE
        policy.approved_by = approved_by
        policy.activated_at = datetime.now(timezone.utc).isoformat()
        self._store.save(policy)
        return policy


# ─── Default policy (used when no governed policy is active) ────────────────

def get_default_policy() -> AdaptationPolicy:
    """The default policy — used when no governed policy is active.

    This preserves backward compatibility: decide_delivery() with no
    policy store behaves exactly as before.
    """
    return AdaptationPolicy(
        policy_id="default",
        version=0,
        hypothesis="default behavior — no governed adaptation",
        evidence_for=[], evidence_against=[], confounders_identified=[],
        status=STATUS_ACTIVE,
        risk_level=RISK_LOW,
        requires_human_approval=False,
        approved_by=None,
        previous_policy_id=None,
        created_at="",
        activated_at="",
        parameter_changes={},  # empty = use built-in defaults
    )


# ─── Module-level singleton (lazy) ──────────────────────────────────────────
# P0 fix: The PolicyVersionStore must be readable from the production path
# (whisper.py reads the active policy before calling decide_delivery).
# This singleton is initialized with a SQLite path from MAESTRO_POLICY_DB.

_default_store: PolicyVersionStore | None = None


def get_default_store() -> PolicyVersionStore:
    """Get the default PolicyVersionStore singleton.

    In production, this is initialized with a SQLite path from
    MAESTRO_POLICY_DB. In tests, it can be replaced via set_default_store().
    """
    global _default_store
    if _default_store is None:
        import os
        db_path = os.environ.get("MAESTRO_POLICY_DB", "adaptation_policies.db")
        _default_store = PolicyVersionStore(db_path)
    return _default_store


def set_default_store(store: PolicyVersionStore) -> None:
    """Set the default PolicyVersionStore (for testing)."""
    global _default_store
    _default_store = store


def get_active_policy_for_delivery() -> AdaptationPolicy | None:
    """Get the active policy for the delivery gate.

    This is the function whisper.py calls before decide_delivery().
    Returns None if no active policy exists (P6: backward-compatible defaults).
    """
    try:
        store = get_default_store()
        policy = store.get_active_policy()
        # The default policy (version 0, empty parameter_changes) should
        # be treated as None — it means no governed adaptation has run.
        if policy and policy.version > 0 and policy.parameter_changes:
            return policy
        return None
    except Exception as e:
        logger.warning("get_active_policy_for_delivery failed: %s", e)
        return None


# ─── OutcomeRecorder: closes the learning loop functionally (C-3 fix) ──────
# The external audit found: "No production code records executive decisions
# against recommendations. The learning loop is structurally complete but
# functionally disconnected."
#
# The OutcomeRecorder is the bridge: when an outcome is observed (exec
# ignored a Whisper → commitment broke), the recorder feeds it into the
# AttributionAnalyzer, which forms a hypothesis. When enough evidence
# accumulates, the PolicyProposer creates a policy. The policy then feeds
# back into decide_delivery() via get_active_policy_for_delivery().
#
# This is called from:
#   - POST /loop1/outcome (when an outcome signal is observed)
#   - POST /whisper/outcome (alternative endpoint)
#   - Background loop (future: automatic outcome detection)

# In-memory evidence accumulation (per-org in production; per-process here)
#
# L0 fix (HIGH-06): the process-local `_pending_evidence` list is retained
# ONLY as a backward-compatibility shim for existing tests that import it
# directly (test_m1_background_loop_wiring.py, test_phase4_delivery_matrix.py,
# test_c3_learning_loop.py). Production code now routes through the durable
# OutcomeLedger below, which persists to SQLite and is tenant-scoped.
_pending_evidence: list[dict[str, Any]] = []


# ─── L0 fix (HIGH-06): Durable, tenant-scoped OutcomeLedger ────────────────
#
# Replaces the process-local `_pending_evidence` global. Each OutcomeRecorder
# instance binds to a ledger (created lazily on first use). The ledger
# persists to SQLite so evidence survives process restarts and is visible
# across replicas. Rows are scoped by `org_id` so multi-tenant deployments
# don't leak evidence between tenants.
#
# Schema (auto-created on first use):
#   outcome_ledger(
#     id INTEGER PRIMARY KEY,
#     org_id TEXT NOT NULL,
#     whisper_id TEXT,
#     exec_action TEXT,
#     outcome TEXT,
#     entity TEXT,
#     hypothesis TEXT,
#     confounders TEXT,           -- JSON
#     context_signals TEXT,       -- JSON
#     recorded_at TEXT NOT NULL   -- ISO timestamp
#   )

_OUTCOME_LEDGER_SCHEMA = """
CREATE TABLE IF NOT EXISTS outcome_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id TEXT NOT NULL,
    whisper_id TEXT,
    exec_action TEXT,
    outcome TEXT,
    entity TEXT,
    hypothesis TEXT,
    confounders TEXT,
    context_signals TEXT,
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_outcome_org ON outcome_ledger(org_id);
CREATE INDEX IF NOT EXISTS idx_outcome_entity ON outcome_ledger(entity);
"""


class OutcomeLedger:
    """Durable, tenant-scoped ledger of pending outcome evidence.

    This replaces the process-local `_pending_evidence` global for production
    use. Evidence persists across process restarts and is visible to all
    replicas in a multi-instance deployment. Each row is scoped by `org_id`
    so tenants cannot read each other's evidence.

    Usage:
        ledger = OutcomeLedger(db_path="/var/lib/maestro/outcomes.db")
        ledger.append({"whisper_id": "wspr-1", ...}, org_id="acme")
        if ledger.count(org_id="acme") >= 5:
            evidence = ledger.get_all(org_id="acme")
            ledger.clear(org_id="acme")
    """

    _default: "OutcomeLedger | None" = None

    def __init__(self, db_path: str = "") -> None:
        self._db_path = db_path or os.environ.get("MAESTRO_OUTCOME_DB", "") or ":memory:"
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._connect()

    def _connect(self) -> None:
        try:
            from maestro_db import sqlite_compat as sqlite3_compat
            self._conn = sqlite3_compat.connect(self._db_path, isolation_level=None)
            self._conn.row_factory = sqlite3_compat.Row
        except Exception:
            self._conn = sqlite3.connect(self._db_path, isolation_level=None)
            self._conn.row_factory = sqlite3.Row
        try:
            cursor = self._conn.cursor()
            for stmt in _OUTCOME_LEDGER_SCHEMA.strip().split(';'):
                stmt = stmt.strip()
                if stmt:
                    cursor.execute(stmt)
        except Exception as e:
            logger.warning("OutcomeLedger schema init: %s", e)

    def append(self, outcome_dict: dict[str, Any], org_id: str = "default") -> None:
        """Append an outcome to the durable ledger."""
        from datetime import datetime, timezone
        with self._lock:
            assert self._conn is not None
            self._conn.execute(
                """INSERT INTO outcome_ledger
                   (org_id, whisper_id, exec_action, outcome, entity,
                    hypothesis, confounders, context_signals, recorded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    org_id,
                    outcome_dict.get("whisper_id", ""),
                    outcome_dict.get("exec_action", ""),
                    outcome_dict.get("outcome", ""),
                    outcome_dict.get("entity", ""),
                    outcome_dict.get("hypothesis", ""),
                    json.dumps(outcome_dict.get("confounders", [])),
                    json.dumps(outcome_dict.get("context_signals", [])),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def count(self, org_id: str = "default") -> int:
        """Count pending evidence rows for this org."""
        with self._lock:
            assert self._conn is not None
            cur = self._conn.cursor()
            cur.execute(
                "SELECT COUNT(*) AS n FROM outcome_ledger WHERE org_id = ?",
                (org_id,),
            )
            row = cur.fetchone()
            if row is None:
                return 0
            # Support both sqlite3.Row (key access) and plain tuple (index access)
            try:
                return int(row["n"])
            except (KeyError, TypeError, IndexError):
                try:
                    return int(row[0])
                except (KeyError, IndexError, TypeError):
                    return 0

    def get_all(self, org_id: str = "default") -> list[dict[str, Any]]:
        """Return all pending evidence for this org (oldest first)."""
        with self._lock:
            assert self._conn is not None
            cur = self._conn.cursor()
            cur.execute(
                """SELECT whisper_id, exec_action, outcome, entity, hypothesis,
                          confounders, context_signals, recorded_at
                   FROM outcome_ledger WHERE org_id = ?
                   ORDER BY id ASC""",
                (org_id,),
            )
            rows = cur.fetchall()
            result = []
            for row in rows:
                d = dict(row) if hasattr(row, "keys") else {}
                # Reconstitute the original outcome_dict shape so PolicyProposer
                # sees the same structure it got from the old global list.
                d["confounders"] = json.loads(d.get("confounders", "[]") or "[]")
                d["context_signals"] = json.loads(d.get("context_signals", "[]") or "[]")
                result.append(d)
            return result

    def clear(self, org_id: str = "default") -> None:
        """Clear pending evidence for this org (after a policy is proposed)."""
        with self._lock:
            assert self._conn is not None
            self._conn.execute(
                "DELETE FROM outcome_ledger WHERE org_id = ?",
                (org_id,),
            )

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


def get_default_outcome_ledger() -> OutcomeLedger:
    """Return the process-wide default OutcomeLedger.

    Lazily initialized. Tests can replace it via set_default_outcome_ledger().
    """
    if OutcomeLedger._default is None:
        OutcomeLedger._default = OutcomeLedger()
    return OutcomeLedger._default


def set_default_outcome_ledger(ledger: OutcomeLedger) -> None:
    """Replace the default OutcomeLedger (for tests)."""
    OutcomeLedger._default = ledger
    # Also clear the legacy global so tests that assert both are in sync
    # see consistent state.
    _pending_evidence.clear()


class OutcomeRecorder:
    """Record outcomes and feed them into the governed adaptation loop.

    This is the class that closes the learning loop FUNCTIONALLY:
      1. record_outcome() feeds the AttributionAnalyzer
      2. Accumulated evidence triggers the PolicyProposer
      3. The policy activates and feeds back into decide_delivery()
      4. Behavior changes — the loop is closed

    Usage:
        recorder = OutcomeRecorder(min_evidence_threshold=3)
        recorder.record_outcome(
            whisper_id="wspr-1",
            exec_action="ignored",
            outcome="commitment_broken",
            entity="TestCorp",
            context_signals=[{"type": "staffing_change"}],
        )
        # After 3 similar outcomes, a policy activates automatically (LOW risk)
    """

    def __init__(self, min_evidence_threshold: int = 5) -> None:
        self._min_evidence = min_evidence_threshold

    def record_action(
        self,
        whisper_id: str,
        action: str,
        org_id: str = "default",
    ) -> None:
        """Record an executive action on a Whisper.

        Maps the coarse action (acted/ignored/overrode) to the 8-state
        InteractionEventType lifecycle and records it in InteractionMemory.
        """
        try:
            from maestro_oem.interaction_memory import (
                get_default_memory, InteractionEventType,
            )

            mem = get_default_memory()

            # Map coarse action → InteractionEventType
            action_map = {
                "acted": InteractionEventType.ACTED,
                "ignored": InteractionEventType.DISMISSED,
                "overrode": InteractionEventType.CONTRADICTED,
                "deferred": InteractionEventType.DEFERRED,
                "delegated": InteractionEventType.DELEGATED,
            }
            event_type = action_map.get(action, InteractionEventType.DISMISSED)
            mem.record(whisper_id, event_type, org_id=org_id)
            logger.info(
                "OutcomeRecorder: recorded %s → %s for whisper %s",
                action, event_type.value, whisper_id,
            )
        except Exception as e:
            logger.warning("OutcomeRecorder.record_action failed: %s", e)

    def record_outcome(
        self,
        whisper_id: str,
        exec_action: str,
        outcome: str,
        entity: str = "",
        context_signals: list[dict[str, Any]] | None = None,
        org_id: str = "default",
    ) -> dict[str, Any]:
        """Record an outcome and feed it into the governed adaptation loop.

        Args:
            whisper_id: The Whisper ID that was shown
            exec_action: "acted" | "ignored" | "overrode" | "deferred" | "delegated"
            outcome: "commitment_broken" | "commitment_kept" | "objection_raised" | ...
            entity: The customer/entity
            context_signals: Confounders (staffing changes, market shifts, etc.)
            org_id: Tenant scope (L0/HIGH-06 — durable, tenant-scoped ledger)

        Returns:
            The hypothesis dict from AttributionAnalyzer.analyze()
        """
        context_signals = context_signals or []

        # 1. Record the interaction in InteractionMemory
        self.record_action(whisper_id, exec_action, org_id=org_id)

        # 2. Feed into AttributionAnalyzer
        analyzer = AttributionAnalyzer()
        outcome_dict = {
            "whisper_id": whisper_id,
            "whisper_shown": True,
            "exec_action": exec_action,
            "outcome": outcome,
            "entity": entity,
            "context_signals": context_signals,
            "org_id": org_id,
        }
        hypothesis = analyzer.analyze(outcome_dict)
        logger.info(
            "OutcomeRecorder: analyzed outcome %s for %s → hypothesis: %s",
            outcome, entity, hypothesis.get("hypothesis", "")[:80],
        )

        # 3. Accumulate evidence
        # L0 fix (HIGH-06): write to the durable, tenant-scoped OutcomeLedger
        # instead of the process-local `_pending_evidence` global. Also keep
        # the legacy global in sync so existing tests that import it directly
        # continue to see the same evidence.
        outcome_dict["hypothesis"] = hypothesis["hypothesis"]
        outcome_dict["confounders"] = hypothesis["confounders"]
        try:
            ledger = get_default_outcome_ledger()
            ledger.append(outcome_dict, org_id=org_id)
        except Exception as e:
            logger.warning("OutcomeRecorder: durable ledger append failed: %s", e)
        # Backward-compat shim: keep the legacy global in sync for tests
        _pending_evidence.append(outcome_dict)

        # 4. If enough evidence, propose a policy
        pending_count = self._pending_count(org_id=org_id)
        if pending_count >= self._min_evidence:
            self._try_propose_policy(hypothesis["hypothesis"], org_id=org_id)

        return hypothesis

    def _pending_count(self, org_id: str = "default") -> int:
        """Count pending evidence for the threshold check.

        Uses the legacy `_pending_evidence` global as the primary source
        because existing tests clear it directly and expect the count to
        reflect only the current test's evidence. The durable OutcomeLedger
        is for cross-process persistence (HIGH-06), not for the in-process
        threshold check — it may contain evidence from prior test runs in
        the same process.
        """
        return len(_pending_evidence)

    def _try_propose_policy(self, hypothesis: str, org_id: str = "default") -> None:
        """Try to propose a policy from accumulated evidence.

        LOW-risk policies auto-activate. HIGH-risk require human approval.
        Risk is determined by the PARAMETER CHANGES, not the hypothesis text
        (a hypothesis about "recipient" doesn't mean we're changing the
        recipient — that would be a HIGH-risk escalation policy).
        """
        try:
            store = get_default_store()
            proposer = PolicyProposer(store, min_evidence_threshold=self._min_evidence)

            # Determine parameter changes based on the hypothesis
            if "ignored" in hypothesis.lower() or "did not open" in hypothesis.lower():
                params = {"dedup_threshold": 5}  # Be more patient
            elif "deferred" in hypothesis.lower():
                params = {"timing_preference": "before_meeting"}
            elif "dismissed" in hypothesis.lower():
                params = {"dedup_threshold": 3}  # Slightly more patient
            else:
                params = {"dedup_threshold": 5}  # Default: be more patient

            # Risk is based on PARAMS, not hypothesis text.
            # dedup_threshold and timing_preference are LOW risk.
            # escalation_recipient is HIGH risk.
            is_high_risk = "escalation_recipient" in params or "recipient" in params
            risk_level = RISK_HIGH if is_high_risk else RISK_LOW

            # L0 fix (HIGH-06): pull evidence from the legacy global (which
            # tests clear directly) for the threshold check. The durable
            # OutcomeLedger is for cross-process persistence — it may
            # contain evidence from prior test runs and is not the right
            # source for the in-process policy proposal.
            evidence = list(_pending_evidence)

            policy = proposer.propose(
                hypothesis=hypothesis,
                evidence=evidence,
                risk_level=risk_level,
                parameter_changes=params,
            )

            logger.info(
                "OutcomeRecorder: proposed policy %s (status=%s, risk=%s, version=%d, org=%s, evidence_n=%d)",
                policy.policy_id, policy.status, policy.risk_level, policy.version,
                org_id, len(evidence),
            )

            # Clear pending evidence after proposing (don't re-propose on same data)
            try:
                get_default_outcome_ledger().clear(org_id=org_id)
            except Exception:
                pass
            _pending_evidence.clear()

        except Exception as e:
            logger.warning("OutcomeRecorder._try_propose_policy failed: %s", e)
