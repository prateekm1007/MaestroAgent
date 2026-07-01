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
from maestro_db.db_helper import get_db_url_for_learning
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

    In production (MAESTRO_ENV=production), defaults to False — a production
    deployment must never silently load synthetic data. If demo seed is
    explicitly enabled in production, a warning is logged.
    """
    val = os.environ.get("MAESTRO_DEMO_SEED", "").strip().lower()
    is_production = os.environ.get("MAESTRO_ENV", "development") == "production"

    if val:
        # Explicitly set — honor it
        enabled = val not in ("false", "0", "no", "off")
        if enabled and is_production:
            logger.warning(
                "MAESTRO_DEMO_SEED=true in production (MAESTRO_ENV=production). "
                "Synthetic demo data will be loaded. This is NOT recommended for "
                "production deployments — set MAESTRO_DEMO_SEED=false."
            )
        return enabled

    # Not explicitly set — use environment-aware default
    if is_production:
        logger.info("MAESTRO_DEMO_SEED not set in production — defaulting to false (no demo data)")
        return False
    return True  # Development default: demo on


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
        # V6 Spec #3 — Background Adaptation Loop cache.
        # Populated by live_ingest() so the loop runs on every signal ingest
        # (V6 Law 2: "improves even when nobody opens Maestro"), not only when
        # the GET /api/oem/background-loop endpoint is called. Read by the
        # endpoint as the cached result; callers wanting a fresh run can pass
        # ?fresh=1.
        from datetime import datetime as _dt
        self._last_background_loop_result: dict[str, Any] | None = None
        self._last_background_loop_at: _dt | None = None

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

        DEMO SEED PURGING: If the OEM was initialized with demo seed data
        and this is the first batch of real signals, the demo signals are
        purged first to prevent synthetic + real data contamination (the
        auditor's HIGH 5 finding). The purge is logged.
        """
        if not new_signals:
            return
        if not self._initialized:
            self.initialize()
        with self._lock:
            # Purge demo seed data when the first real signals arrive
            if self._demo_seeded and self._live_signals_ingested == 0:
                self._purge_demo_seed_locked()

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

        # V6 Spec #3 / V6 Law 2 — run the Background Adaptation Loop on every
        # signal ingest so the organization improves even when nobody opens
        # Maestro. This is the wire the Round-24 audit flagged as missing:
        # previously the loop only ran when the GET /api/oem/background-loop
        # endpoint was hit. Called OUTSIDE the lock because the loop's
        # contradiction check calls back into oem_state via the routes layer
        # (which would re-acquire the RLock — safe but unnecessary contention)
        # and because a loop failure must never break ingest. The result is
        # cached so the next GET /background-loop returns the latest run
        # without recomputing. The call is double-wrapped: _run_background_loop
        # swallows internal BackgroundAdaptationLoop errors, and this outer
        # try/except swallows any other failure (e.g., a broken monkey-patch
        # in tests, or an unexpected AttributeError). Ingest MUST survive.
        try:
            self._run_background_loop()
        except Exception as e:
            logger.warning("Background adaptation loop invocation failed: %s", e)

    def _run_background_loop(self) -> None:
        """Run the V6 Background Adaptation Loop and cache the result.

        Called from live_ingest() after every signal batch. Also callable
        directly. Failures are logged and swallowed — a background-loop
        error must never break signal ingest (the loop is observational,
        not transactional).
        """
        try:
            from maestro_oem.background_loop import BackgroundAdaptationLoop
            from datetime import datetime, timezone
            assert self.engine is not None
            model = self.engine.get_model()
            loop = BackgroundAdaptationLoop(model, self.signals)
            result = loop.run()
            self._last_background_loop_result = result
            self._last_background_loop_at = datetime.now(timezone.utc)
            logger.debug(
                "Background loop ran on ingest: %s notices",
                result.get("notice_count", 0),
            )
        except Exception as e:
            logger.warning("Background adaptation loop failed on ingest: %s", e)

    def _purge_demo_seed_locked(self) -> None:
        """Purge demo seed signals from the OEM state.

        Called when the first real signals arrive via live_ingest(). Rebuilds
        the engine from scratch (without the demo seed) to ensure only real
        data remains. This closes the auditor's HIGH 5: demo signals were
        silently coexisting with real signals after OAuth connection.
        """
        logger.info("Purging demo seed data — real signals detected, preventing data contamination")
        # Rebuild the engine from scratch (no demo seed)
        self.engine = OEMEngine()
        self.signals = []
        self._demo_seeded = False
        # Note: we do NOT reset _live_signals_ingested here — it stays at 0
        # so the purge only happens once (on the first real signal batch).

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
                get_db_url_for_learning(),
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

    def check_tenant_access(self) -> None:
        """Enforce multi-tenant isolation at the route level.

        In multi-tenant mode (MAESTRO_MULTI_TENANT=true), the OEM state is
        scoped to a single org (set via MAESTRO_ORG_ID at startup). If a
        request's TenantContext.org_id doesn't match, this raises 403.

        In single-tenant mode (default), this is a no-op — the OEM serves
        all requests from one shared state.

        This guard is called by the OEM route dependency (_require_tenant_access)
        to prevent cross-tenant data leakage. True multi-tenancy (per-org OEM
        state) requires keying OEMState by org_id — a future architectural
        change. For now, this guard prevents the route-level bypass the auditor
        identified.
        """
        import os
        is_multi_tenant = os.environ.get("MAESTRO_MULTI_TENANT", "false").lower() == "true"
        if not is_multi_tenant:
            return  # Single-tenant mode: no isolation needed

        from maestro_auth.security import TenantContext
        request_org = TenantContext.get_org_id()
        state_org = os.environ.get("MAESTRO_ORG_ID", "")

        if request_org and state_org and request_org != state_org:
            from fastapi import HTTPException
            raise HTTPException(
                403,
                f"Cross-tenant access denied: request org '{request_org}' does not match "
                f"this instance's org '{state_org}'. Each tenant requires a dedicated "
                f"deployment or per-org OEM state (not yet implemented)."
            )


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
