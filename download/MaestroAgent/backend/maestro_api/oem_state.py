"""
OEM application state — a singleton OEMEngine + DecisionEngine + EvidenceGraph
seeded with REAL signal data from all 5 providers.

This is the bridge between maestro_oem (the inference engine) and maestro_api
(the HTTP layer). The OEM is built once at server startup, then continuously
updated as the HistoricalImportEngine streams in real signals from connected
providers (GitHub, Jira, Slack, Confluence, Gmail).

The OEM is also wired to a CheckpointStore, OAuthManager, ConnectionManager,
ProgressTracker, and HistoricalImportEngine — see `import_state` below.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any

from maestro_oem import (
    OEMEngine,
    DecisionEngine,
    EvidenceGraph,
    ExecutionSignal,
)
from maestro_oem.providers import (
    normalize_github,
    normalize_jira,
    normalize_slack,
    normalize_confluence,
    normalize_gmail,
)
from maestro_oem.checkpoint_store import CheckpointStore
from maestro_oem.oauth_manager import OAuthManager
from maestro_oem.connection_manager import ConnectionManager
from maestro_oem.progress_tracker import ProgressTracker
from maestro_oem.importers.factory import ProviderFactory
from maestro_oem.historical_engine import HistoricalImportEngine

logger = logging.getLogger(__name__)


# Path to the import state DB (persisted checkpoints + OAuth tokens).
# Override with MAESTRO_IMPORT_DB env var; defaults to a sibling of the OEM DB.
_IMPORT_DB_PATH = os.environ.get(
    "MAESTRO_IMPORT_DB",
    str(Path(__file__).parent.parent.parent / "import_state.db"),
)


# ─── Realistic signal data (mirrors the test fixtures in test_oem.py) ───────
# These are the same events the OEM test suite uses to verify the engine
# produces laws, patterns, and recommendations. They represent a mid-size
# engineering org (acme-corp) with 5 connected signal sources.

GITHUB_EVENTS = [
    {"event_type": "pull_request", "repository": "acme/payments-edge", "actor": "priya.m@acme.com",
     "artifact": "github:acme/payments-edge/pull/447", "timestamp": "2024-11-12T09:00:00Z",
     "metadata": {"action": "opened", "domain": "payments", "title": "Add circuit breaker"}},
    {"event_type": "review", "repository": "acme/payments-edge", "actor": "priya.m@acme.com",
     "artifact": "github:acme/payments-edge/pull/447", "timestamp": "2024-11-12T09:30:00Z",
     "metadata": {"reviewer": "carlos.r@acme.com", "domain": "payments", "action": "approved"}},
    {"event_type": "merge", "repository": "acme/payments-edge", "actor": "priya.m@acme.com",
     "artifact": "github:acme/payments-edge/pull/447", "timestamp": "2024-11-12T10:00:00Z",
     "metadata": {"domain": "payments", "action": "merged"}},
    {"event_type": "pull_request", "repository": "acme/auth-service", "actor": "carlos.r@acme.com",
     "artifact": "github:acme/auth-service/pull/102", "timestamp": "2024-11-10T14:00:00Z",
     "metadata": {"action": "opened", "domain": "auth", "title": "OAuth consolidation"}},
    {"event_type": "review", "repository": "acme/auth-service", "actor": "carlos.r@acme.com",
     "artifact": "github:acme/auth-service/pull/102", "timestamp": "2024-11-10T16:00:00Z",
     "metadata": {"reviewer": "priya.m@acme.com", "domain": "auth", "action": "approved"}},
    {"event_type": "commit", "repository": "acme/platform-tools", "actor": "aisha.k@acme.com",
     "artifact": "github:acme/platform-tools/commit/abc123", "timestamp": "2024-11-08T11:00:00Z",
     "metadata": {"domain": "platform"}},
    {"event_type": "commit", "repository": "acme/platform-tools", "actor": "aisha.k@acme.com",
     "artifact": "github:acme/platform-tools/commit/def456", "timestamp": "2024-11-09T11:00:00Z",
     "metadata": {"domain": "platform"}},
    {"event_type": "commit", "repository": "acme/platform-tools", "actor": "aisha.k@acme.com",
     "artifact": "github:acme/platform-tools/commit/ghi789", "timestamp": "2024-11-10T11:00:00Z",
     "metadata": {"domain": "platform"}},
    # Additional PRs to strengthen Priya's hidden-expert signal
    {"event_type": "pull_request", "repository": "acme/payments-edge", "actor": "priya.m@acme.com",
     "artifact": "github:acme/payments-edge/pull/448", "timestamp": "2024-11-13T09:00:00Z",
     "metadata": {"action": "opened", "domain": "payments", "title": "Retry logic"}},
    {"event_type": "pull_request", "repository": "acme/auth-service", "actor": "priya.m@acme.com",
     "artifact": "github:acme/auth-service/pull/103", "timestamp": "2024-11-14T09:00:00Z",
     "metadata": {"action": "opened", "domain": "auth", "title": "Token refresh"}},
    {"event_type": "pull_request", "repository": "acme/platform-tools", "actor": "priya.m@acme.com",
     "artifact": "github:acme/platform-tools/pull/50", "timestamp": "2024-11-15T09:00:00Z",
     "metadata": {"action": "opened", "domain": "platform", "title": "Build script"}},
]

JIRA_EVENTS = [
    {"event_type": "issue_created", "project": "EMEA", "actor": "sara.k@acme.com",
     "artifact": "jira:EMEA-1247", "timestamp": "2024-11-05T09:00:00Z",
     "metadata": {"priority": "P1", "issue_type": "Bug"}},
    {"event_type": "issue_created", "project": "EMEA", "actor": "chris.t@acme.com",
     "artifact": "jira:EMEA-1248", "timestamp": "2024-11-06T09:00:00Z",
     "metadata": {"priority": "P1", "issue_type": "Bug"}},
    {"event_type": "issue_created", "project": "EMEA", "actor": "chris.t@acme.com",
     "artifact": "jira:EMEA-1249", "timestamp": "2024-11-07T09:00:00Z",
     "metadata": {"priority": "P1", "issue_type": "Bug"}},
    {"event_type": "issue_transitioned", "project": "EMEA", "actor": "sara.k@acme.com",
     "artifact": "jira:EMEA-1247", "timestamp": "2024-11-08T14:00:00Z",
     "metadata": {"transition": "Approved", "assignee": "sara.k@acme.com"}},
    {"event_type": "issue_transitioned", "project": "EMEA", "actor": "sara.k@acme.com",
     "artifact": "jira:EMEA-1248", "timestamp": "2024-11-09T14:00:00Z",
     "metadata": {"transition": "Approved", "assignee": "sara.k@acme.com"}},
    {"event_type": "issue_transitioned", "project": "EMEA", "actor": "sara.k@acme.com",
     "artifact": "jira:EMEA-1249", "timestamp": "2024-11-10T14:00:00Z",
     "metadata": {"transition": "Approved", "assignee": "sara.k@acme.com"}},
    {"event_type": "sprint_completed", "project": "EMEA", "actor": "chris.t@acme.com",
     "artifact": "jira:SPRINT-Q4-3", "timestamp": "2024-11-08T17:00:00Z",
     "metadata": {"velocity": 42}},
    # More Sara K. approvals to make her a clear bottleneck
    {"event_type": "issue_transitioned", "project": "EMEA", "actor": "sara.k@acme.com",
     "artifact": "jira:EMEA-1250", "timestamp": "2024-11-11T14:00:00Z",
     "metadata": {"transition": "Approved", "assignee": "sara.k@acme.com"}},
    {"event_type": "issue_transitioned", "project": "EMEA", "actor": "sara.k@acme.com",
     "artifact": "jira:EMEA-1251", "timestamp": "2024-11-12T14:00:00Z",
     "metadata": {"transition": "Approved", "assignee": "sara.k@acme.com"}},
    # Issue assignments to populate gate_counts (Sara K. as the approval gate)
    {"event_type": "issue_assigned", "project": "EMEA", "actor": "chris.t@acme.com",
     "artifact": "jira:EMEA-1252", "timestamp": "2024-11-12T15:00:00Z",
     "metadata": {"assignee": "sara.k@acme.com", "issue_type": "Story"}},
    {"event_type": "issue_assigned", "project": "EMEA", "actor": "chris.t@acme.com",
     "artifact": "jira:EMEA-1253", "timestamp": "2024-11-13T15:00:00Z",
     "metadata": {"assignee": "sara.k@acme.com", "issue_type": "Story"}},
    {"event_type": "issue_assigned", "project": "EMEA", "actor": "chris.t@acme.com",
     "artifact": "jira:EMEA-1254", "timestamp": "2024-11-14T15:00:00Z",
     "metadata": {"assignee": "sara.k@acme.com", "issue_type": "Story"}},
]

SLACK_EVENTS = [
    {"event_type": "message", "channel": "#engineering", "actor": "priya.m@acme.com",
     "artifact": "slack:C-123/p-1", "timestamp": "2024-11-12T09:14:00Z",
     "metadata": {"text": "the payments-edge circuit breaker is ready for review. who can take a look today?",
      "participants": ["priya.m@acme.com", "carlos.r@acme.com"]}},
    {"event_type": "message", "channel": "#engineering", "actor": "carlos.r@acme.com",
     "artifact": "slack:C-123/p-2", "timestamp": "2024-11-12T09:16:00Z",
     "metadata": {"text": "I can review after lunch. does this cover the retry logic too?",
      "participants": ["carlos.r@acme.com", "priya.m@acme.com"]}},
    {"event_type": "message", "channel": "#leadership", "actor": "pat.s@acme.com",
     "artifact": "slack:C-456/p-3", "timestamp": "2024-11-11T10:00:00Z",
     "metadata": {"text": "I disagree with the Q3 hiring plan — we need APAC not EMEA",
      "participants": ["pat.s@acme.com", "jane.d@acme.com"]}},
    {"event_type": "message", "channel": "#engineering", "actor": "marcus.t@acme.com",
     "artifact": "slack:C-123/p-4", "timestamp": "2024-11-12T09:22:00Z",
     "metadata": {"text": "security review needed? this touches auth flow",
      "participants": ["marcus.t@acme.com", "priya.m@acme.com"]}},
    {"event_type": "message", "channel": "#engineering", "actor": "anya.r@acme.com",
     "artifact": "slack:C-123/p-5", "timestamp": "2024-11-10T15:00:00Z",
     "metadata": {"text": "I'm thinking about a new opportunity...", "participants": ["anya.r@acme.com"]}},
    # Decision signals to build decision-velocity data
    {"event_type": "message", "channel": "#leadership", "actor": "jane.d@acme.com",
     "artifact": "slack:C-456/p-6", "timestamp": "2024-11-11T10:05:00Z",
     "metadata": {"text": "let's go with the compromise — reduce EMEA by 3, add 2 APAC",
      "participants": ["jane.d@acme.com", "pat.s@acme.com"]}},
]

CONFLUENCE_EVENTS = [
    {"event_type": "postmortem_created", "space": "Engineering", "actor": "chris.t@acme.com",
     "artifact": "confluence:PM-2024-11-09", "timestamp": "2024-11-09T16:00:00Z",
     "metadata": {"title": "Postmortem: payments-edge incident Nov 9", "has_owner": False, "page_type": "postmortem"}},
    {"event_type": "rfc_created", "space": "Engineering", "actor": "carlos.r@acme.com",
     "artifact": "confluence:RFC-412", "timestamp": "2024-10-28T10:00:00Z",
     "metadata": {"title": "OAuth Consolidation RFC", "domain": "auth", "has_owner": True, "page_type": "rfc"}},
    {"event_type": "page_created", "space": "Engineering", "actor": "priya.m@acme.com",
     "artifact": "confluence:DOC-789", "timestamp": "2024-11-01T11:00:00Z",
     "metadata": {"title": "Deployment Runbook", "domain": "deployment", "page_type": "documentation"}},
    {"event_type": "page_created", "space": "Payments", "actor": "anya.r@acme.com",
     "artifact": "confluence:DOC-790", "timestamp": "2024-11-03T14:00:00Z",
     "metadata": {"title": "Payments Integration Guide", "domain": "payments", "page_type": "documentation"}},
    # More postmortems without owners to strengthen the "postmortem owner reduces recurrence" law
    {"event_type": "postmortem_created", "space": "Engineering", "actor": "chris.t@acme.com",
     "artifact": "confluence:PM-2024-10-15", "timestamp": "2024-10-15T16:00:00Z",
     "metadata": {"title": "Postmortem: auth-service incident Oct 15", "has_owner": False, "page_type": "postmortem"}},
    {"event_type": "postmortem_created", "space": "Engineering", "actor": "priya.m@acme.com",
     "artifact": "confluence:PM-2024-09-20", "timestamp": "2024-09-20T16:00:00Z",
     "metadata": {"title": "Postmortem: platform-tools incident Sep 20", "has_owner": True, "page_type": "postmortem"}},
]

GMAIL_EVENTS = [
    {"event_type": "meeting_completed", "actor": "jane.d@acme.com",
     "artifact": "cal:event-001", "timestamp": "2024-11-11T15:00:00Z",
     "metadata": {"participants": ["jane.d@acme.com", "raj@globex.com"], "duration": 30, "subject": "Q4 renewal discussion"}},
    {"event_type": "email_sent", "actor": "jane.d@acme.com",
     "artifact": "gmail:msg-001", "timestamp": "2024-11-11T16:00:00Z",
     "metadata": {"recipient": "raj@globex.com", "recipient_type": "external", "subject": "Re: Q4 renewal discussion"}},
    {"event_type": "meeting_completed", "actor": "chris.t@acme.com",
     "artifact": "cal:event-002", "timestamp": "2024-11-08T10:00:00Z",
     "metadata": {"participants": ["chris.t@acme.com", "casey.f@acme.com", "priya.e@acme.com"], "duration": 45, "subject": "Eng leadership sync"}},
    {"event_type": "meeting_completed", "actor": "jane.d@acme.com",
     "artifact": "cal:event-003", "timestamp": "2024-11-12T09:00:00Z",
     "metadata": {"participants": ["jane.d@acme.com", "chris.t@acme.com", "casey.f@acme.com", "pat.s@acme.com"],
      "duration": 60, "subject": "Q3 Hiring Decision"}},
]


def _build_signals() -> list[ExecutionSignal]:
    """Normalize all raw events into ExecutionSignal objects."""
    signals: list[ExecutionSignal] = []
    for ev in GITHUB_EVENTS:
        signals.append(normalize_github(ev))
    for ev in JIRA_EVENTS:
        signals.append(normalize_jira(ev))
    for ev in SLACK_EVENTS:
        signals.append(normalize_slack(ev))
    for ev in CONFLUENCE_EVENTS:
        signals.append(normalize_confluence(ev))
    for ev in GMAIL_EVENTS:
        signals.append(normalize_gmail(ev))
    return signals


class OEMState:
    """
    Singleton holding the initialized OEM engine, decision engine, and evidence graph.

    Built once at server startup. The OEM is seeded with realistic signal data
    from all 5 providers. As the HistoricalImportEngine streams in real signals
    from connected providers, the OEM is incrementally updated — every API
    response reflects the latest state.

    Thread-safe via a single RLock (the underlying OEMEngine.process_signal
    is not async).
    """

    def __init__(self) -> None:
        self.engine: OEMEngine | None = None
        self.decision_engine: DecisionEngine | None = None
        self.evidence_graph: EvidenceGraph | None = None
        self.signals: list[ExecutionSignal] = []
        self._initialized = False
        self._lock = threading.RLock()
        self._live_signals_ingested = 0
        self._contradiction_log = None  # Set on first contradict() call

    def initialize(self) -> None:
        """Build the OEM from real signal data. Idempotent."""
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            logger.info("Initializing OEM from real signal data (5 providers, %d events)",
                        len(GITHUB_EVENTS) + len(JIRA_EVENTS) + len(SLACK_EVENTS)
                        + len(CONFLUENCE_EVENTS) + len(GMAIL_EVENTS))
            self.engine = OEMEngine()
            self.signals = _build_signals()
            self.engine.ingest(self.signals)
            model = self.engine.get_model()
            self.evidence_graph = EvidenceGraph()
            self.evidence_graph.build_from_model(model)
            self.decision_engine = DecisionEngine(model, self.evidence_graph)
            self._initialized = True
            summary = model.get_summary()
            logger.info("OEM ready: %d signals → %d learning objects → %d patterns → %d laws",
                        summary["signals_processed"], summary["learning_objects"],
                        summary["patterns_detected"], summary["laws_inferred"])

    def live_ingest(self, new_signals: list[ExecutionSignal]) -> None:
        """Stream new signals into the live OEM.

        Called by HistoricalImportEngine after each page of historical data
        is fetched. The OEM engine is incremental — process_signal updates
        the model without rebuilding from scratch.

        After ingest, the decision engine and evidence graph are refreshed
        so every API response reflects the new data.
        """
        if not new_signals:
            return
        if not self._initialized:
            self.initialize()
        with self._lock:
            assert self.engine is not None
            for sig in new_signals:
                try:
                    self.engine.ingest([sig])
                    self.signals.append(sig)
                    self._live_signals_ingested += 1
                except Exception as e:
                    logger.warning("Live signal ingest failed: %s", e)
            self._refresh_downstream_locked()

    def _refresh_downstream(self) -> None:
        """Rebuild the decision engine + evidence graph from the current model.

        Public version — acquires the lock. Called after contradiction
        feedback or any other mutation that doesn't go through live_ingest.
        """
        if not self._initialized:
            return
        with self._lock:
            self._refresh_downstream_locked()

    def _refresh_downstream_locked(self) -> None:
        """Refresh downstream artifacts (caller holds the lock)."""
        assert self.engine is not None
        model = self.engine.get_model()
        self.evidence_graph = EvidenceGraph()
        self.evidence_graph.build_from_model(model)
        self.decision_engine = DecisionEngine(model, self.evidence_graph)

    def snapshot(self) -> dict[str, int]:
        """Return a count snapshot for the ProgressTracker."""
        if not self._initialized:
            self.initialize()
        assert self.engine is not None
        with self._lock:
            model = self.engine.get_model()
            summary = model.get_summary()
            return {
                "signals_processed": summary["signals_processed"],
                "learning_objects": summary["learning_objects"],
                "patterns_detected": summary["patterns_detected"],
                "laws_inferred": summary["laws_inferred"],
                "recommendations": len(self.decision_engine.get_recommendations()) if self.decision_engine else 0,
                "validated_laws": sum(
                    1 for l in model.laws.values()
                    if hasattr(l, "status") and str(l.status).endswith("VALIDATED")
                ),
            }

    @property
    def live_signals_ingested(self) -> int:
        """Number of signals ingested since startup via live_ingest."""
        return self._live_signals_ingested

    @property
    def model(self) -> Any:
        if not self._initialized:
            self.initialize()
        assert self.engine is not None
        return self.engine.get_model()

    @property
    def decisions(self) -> DecisionEngine:
        if not self._initialized:
            self.initialize()
        assert self.decision_engine is not None
        return self.decision_engine

    @property
    def graph(self) -> EvidenceGraph:
        if not self._initialized:
            self.initialize()
        assert self.evidence_graph is not None
        return self.evidence_graph


# Module-level singleton — imported by the route handlers.
oem_state = OEMState()


# ─── Import state — wires together the historical import pipeline ──────────

class ImportState:
    """
    Singleton holding all the infrastructure for live historical imports.

    Lazily initialized on first access (so test environments that only use
    the OEM engine don't pay the cost of creating SQLite stores / OAuth
    managers / etc.).

    Wires together:
      - CheckpointStore       (SQLite-backed persistence)
      - OAuthManager          (5-provider OAuth flows)
      - ConnectionManager     (provider connection state)
      - ProgressTracker       (live progress for UI)
      - ProviderFactory       (creates PageFetcher per provider)
      - HistoricalImportEngine (orchestrator)
    """

    def __init__(self) -> None:
        self._initialized = False
        self.store: CheckpointStore | None = None
        self.oauth: OAuthManager | None = None
        self.connections: ConnectionManager | None = None
        self.tracker: ProgressTracker | None = None
        self.factory: ProviderFactory | None = None
        self.engine: HistoricalImportEngine | None = None

    def initialize(self) -> None:
        if self._initialized:
            return
        # Build the wiring
        self.store = CheckpointStore(_IMPORT_DB_PATH)
        self.oauth = OAuthManager(self.store)
        self.factory = ProviderFactory(self.oauth)
        self.tracker = ProgressTracker()
        # on_signals streams into the live OEM
        # on_oem_update returns a fresh snapshot for the progress UI
        self.engine = HistoricalImportEngine(
            store=self.store,
            oauth=self.oauth,
            factory=self.factory,
            tracker=self.tracker,
            on_signals=oem_state.live_ingest,
            on_oem_update=oem_state.snapshot,
        )
        self.connections = ConnectionManager(
            store=self.store, oauth=self.oauth, import_engine=self.engine,
        )
        self._initialized = True
        logger.info("ImportState initialized (db=%s)", _IMPORT_DB_PATH)

    def ensure_initialized(self) -> None:
        if not self._initialized:
            self.initialize()


import_state = ImportState()
