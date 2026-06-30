"""
OEM application state — a singleton OEMEngine + DecisionEngine + EvidenceGraph.

DEMO MODE: At startup the OEM is seeded with the acme-corp demo dataset
by running DemoPageFetcher through the SAME ingestion pipeline real
providers use (fetch_page -> normalize_item -> provider normalizer ->
ExecutionSignal -> OEMEngine.ingest). This means bugs in the ingestion
pipeline are caught in demo mode, not just in production.

To disable demo seeding: set MAESTRO_DEMO_SEED=false in env. When real
providers are connected via OAuth, their live signals are ingested on
top via live_ingest() — the demo seed is NOT removed automatically.

This is the bridge between maestro_oem (the inference engine) and maestro_api
(the HTTP layer).
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
from maestro_oem.checkpoint_store import CheckpointStore
from maestro_oem.oauth_manager import OAuthManager
from maestro_oem.connection_manager import ConnectionManager
from maestro_oem.progress_tracker import ProgressTracker
from maestro_oem.importers.factory import ProviderFactory
from maestro_oem.importers.demo_provider import (
    DemoPageFetcher,
    demo_provider_names,
    demo_total_events,
    get_demo_normalizer,
)
from maestro_oem.historical_engine import HistoricalImportEngine

logger = logging.getLogger(__name__)


# Path to the import state DB (persisted checkpoints + OAuth tokens).
# Override with MAESTRO_IMPORT_DB env var; defaults to a sibling of the OEM DB.
_IMPORT_DB_PATH = os.environ.get(
    "MAESTRO_IMPORT_DB",
    str(Path(__file__).parent.parent.parent / "import_state.db"),
)


def _demo_seed_enabled() -> bool:
    """Whether the acme-corp demo seed should be loaded at startup.

    Honors MAESTRO_DEMO_SEED env var. Defaults to True (demo on) so the
    product is evaluable without OAuth credentials. Set MAESTRO_DEMO_SEED=false
    to start with an empty OEM — useful for tests and production deployments.
    """
    val = os.environ.get("MAESTRO_DEMO_SEED", "true").strip().lower()
    return val not in ("false", "0", "no", "off")


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
        self._demo_seeded = False  # True after the demo seed has been loaded

    def initialize(self) -> None:
        """Build the OEM. Idempotent.

        If MAESTRO_DEMO_SEED is true (default), the acme-corp demo dataset
        is loaded through the real ingestion pipeline (DemoPageFetcher ->
        normalize_item -> provider normalizer -> ExecutionSignal -> ingest).
        Otherwise the OEM starts empty.
        """
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            self.engine = OEMEngine()

            if _demo_seed_enabled():
                logger.info(
                    "Initializing OEM with demo seed (acme-corp, %d events across %d providers) "
                    "via the real ingestion pipeline",
                    demo_total_events(), len(demo_provider_names()),
                )
                self._seed_from_demo_provider()
            else:
                logger.info("Initializing OEM with MAESTRO_DEMO_SEED=false — starting empty")

            model = self.engine.get_model()
            self.evidence_graph = EvidenceGraph()
            self.evidence_graph.build_from_model(model)
            self.decision_engine = DecisionEngine(model, self.evidence_graph)
            self._initialized = True
            summary = model.get_summary()
            logger.info("OEM ready: %d signals → %d learning objects → %d patterns → %d laws",
                        summary["signals_processed"], summary["learning_objects"],
                        summary["patterns_detected"], summary["laws_inferred"])

    def _seed_from_demo_provider(self) -> None:
        """Seed the OEM by running DemoPageFetcher through the ingestion pipeline.

        This is the SAME path a real provider takes at runtime:
            DemoPageFetcher.fetch_page_sync()  -> PageResult(items=[...])
            fetcher.normalize_item(item)       -> event dict
            normalize_<provider>(event)        -> ExecutionSignal
            oem_engine.ingest([sig])           -> laws / patterns / recommendations

        A bug in any of those steps would surface in demo mode, not just in
        production. Previously the demo seed bypassed this path entirely,
        hiding ingestion-pipeline bugs from the demo environment.

        Uses fetch_page_sync() (not the async fetch_page) because startup
        may already be inside a running event loop (FastAPI TestClient).
        The real provider fetchers do NOT have a sync version — they do
        real I/O and must be awaited by the HistoricalImportEngine.
        """
        assert self.engine is not None
        for provider in demo_provider_names():
            fetcher = DemoPageFetcher(provider)
            normalizer = get_demo_normalizer(provider)
            try:
                page_result = fetcher.fetch_page_sync(page=1)
            except Exception as e:
                logger.warning("Demo seed fetch failed for %s: %s", provider, e)
                continue

            new_signals: list[ExecutionSignal] = []
            for item in page_result.items:
                try:
                    event_dict = fetcher.normalize_item(item)
                    signal = normalizer(event_dict)
                    new_signals.append(signal)
                except Exception as e:
                    logger.warning(
                        "Demo seed normalize failed for %s item %s: %s",
                        provider, item.get("artifact", "?"), e,
                    )

            if new_signals:
                try:
                    self.engine.ingest(new_signals)
                    self.signals.extend(new_signals)
                except Exception as e:
                    logger.warning("Demo seed ingest failed for %s: %s", provider, e)

        self._demo_seeded = True

    def live_ingest(self, new_signals: list[ExecutionSignal]) -> None:
        """Stream new signals into the live OEM.

        Called by HistoricalImportEngine after each page of historical data
        is fetched. The OEM engine is incremental — process_signal updates
        the model without rebuilding from scratch.

        After ingest, the decision engine and evidence graph are refreshed
        so every API response reflects the new data. The closed learning loop
        is also triggered: any pending predictions whose outcome can now be
        determined are resolved and confidence is recalibrated. This is the
        "auto" in "predictions auto-resolve" — without this wire, the loop
        only fires when someone manually hits POST /api/oem/predictions/resolve.
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
            # Close the loop: resolve predictions that the new signals
            # (or earlier CEO feedback) can now settle.
            self._trigger_learning_resolution_locked()

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

    def _trigger_learning_resolution_locked(self) -> None:
        """Fire the closed learning loop (caller holds the lock).

        Constructs a ClosedLoopLearningManager pointing at the shared
        ContradictionLog and asks it to resolve any pending predictions
        whose outcome can now be determined from the model state or from
        CEO feedback already in the log. Resolved predictions flow into
        the CalibrationEngine, which updates the Brier score and the
        10-bucket reliability diagram.

        Failures here MUST NOT break ingest — the loop is best-effort and
        the worst case is "predictions resolve a bit later via the manual
        /predictions/resolve endpoint".
        """
        try:
            import os as _os
            from pathlib import Path as _Path
            from maestro_oem.prediction_lifecycle import ClosedLoopLearningManager
            from maestro_oem.learning import CalibrationEngine

            db_path = _os.environ.get(
                "MAESTRO_LEARNING_DB",
                str(_Path(_os.environ.get("DATABASE_URL", "file:maestro.db").replace("file:", "")).parent / "learning.db"),
            )
            _Path(db_path).parent.mkdir(parents=True, exist_ok=True)

            cal = CalibrationEngine(db_path)
            manager = ClosedLoopLearningManager(
                db_path,
                self.engine.get_model() if self.engine else None,
                self.signals,
                cal,
                contradiction_log=self._contradiction_log,
            )
            result = manager.on_signals_ingested(self.signals, self.model)
            if result.get("predictions_resolved", 0) or result.get("predictions_expired", 0):
                logger.info(
                    "Closed-loop resolution: %d resolved, %d expired, %d still pending",
                    result["predictions_resolved"],
                    result["predictions_expired"],
                    result["still_pending"],
                )
        except Exception as e:
            logger.warning("Closed-loop learning resolution failed (non-fatal): %s", e)

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
