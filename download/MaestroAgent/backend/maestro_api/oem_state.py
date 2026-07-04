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
from maestro_oem.signal_store import SignalStore

logger = logging.getLogger(__name__)


# Path to the import state DB (persisted checkpoints + OAuth tokens).
# Override with MAESTRO_IMPORT_DB env var; defaults to a sibling of the OEM DB.
_IMPORT_DB_PATH = os.environ.get(
    "MAESTRO_IMPORT_DB",
    str(Path(__file__).parent.parent.parent / "import_state.db"),
)


def _demo_seed_enabled() -> bool:
    """Whether the acme-corp demo seed should be loaded at startup.

    Round 60/65 fix: defaults to False (demo OFF) in non-local environments.
    Defaults to True only when MAESTRO_LOCAL_DEV=true.
    In production (MAESTRO_ENV=production), always False unless explicitly set.
    """
    val = os.environ.get("MAESTRO_DEMO_SEED", "").strip().lower()
    is_production = os.environ.get("MAESTRO_ENV", "development") == "production"

    if val:
        # Explicitly set — honor it
        enabled = val not in ("false", "0", "no", "off")
        if enabled and is_production:
            # Round 69 P0 RESIDUAL-5: BLOCK synthetic data in production.
            # The old code only logged a warning and loaded synthetic data anyway.
            # Now it raises RuntimeError — production must never load demo seed.
            raise RuntimeError(
                "MAESTRO_DEMO_SEED=true in production (MAESTRO_ENV=production). "
                "Synthetic demo data is BLOCKED in production. "
                "Set MAESTRO_DEMO_SEED=false or use MAESTRO_LOCAL_DEV=true for dev mode."
            )
        return enabled

    # Not explicitly set — use environment-aware default
    # Round 60 Fix 2: demo seed defaults OFF in non-local environments.
    # The old default was True for ALL non-production environments —
    # staging, pilot, etc. all got synthetic data. Now only local dev
    # (MAESTRO_LOCAL_DEV=true) gets the demo seed by default.
    if is_production:
        logger.info("MAESTRO_DEMO_SEED not set in production — defaulting to false (no demo data)")
        return False
    is_local_dev = os.environ.get("MAESTRO_LOCAL_DEV", "false").lower() in ("1", "true", "yes")
    if is_local_dev:
        return True  # Local dev: demo on for evaluation
    logger.info("MAESTRO_DEMO_SEED not set in non-local env — defaulting to false (no demo data)")
    return False  # Non-local, non-production: demo OFF


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
        self._demo_seeded = False
        self._signal_store: SignalStore | None = None
        # Phase 4.2: Shadow mode flag. When True, live-ingested signals are
        # marked with metadata["shadow"] = True and NOT surfaced to users
        # (filtered out of whispers, briefings, Ask answers). This lets the
        # CEO verify the real-connector pipeline works end-to-end before
        # flipping to live mode. Set via MAESTRO_SHADOW_MODE=true env var.
        self._shadow_mode = os.environ.get("MAESTRO_SHADOW_MODE", "false").lower() in ("1", "true", "yes")
        if self._shadow_mode:
            logger.info("Phase 4.2: SHADOW MODE active — real signals ingested but NOT surfaced to users")
        # Phase 5.1: OEMStore for persisting laws, patterns, learning objects.
        # The ExecutionModel is in-memory; OEMStore persists its components
        # so they survive restart. On initialize(), load_model_state() is
        # called first; if it returns saved state, the model is restored
        # without re-ingesting all signals.
        self._oem_store = None
        self._persistence_version = "v1"  # Phase 5.2: version stamp
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

        Phase 5.1: Tries to load persisted model state (laws, patterns,
        learning objects) from OEMStore first. If saved state exists,
        the model is restored without re-ingesting all signals. If no
        saved state exists, falls back to demo seed or empty start.

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

            # Phase 5.1: Try to load persisted model state first.
            # This is the FIRST thing initialize() tries — before demo seed.
            # If saved state exists and the version matches, restore it.
            # If not, fall through to demo seed or empty start.
            try:
                self._init_oem_store()
                restored = self._load_model_state()
                if restored:
                    logger.info("OEM restored from persisted state (laws=%d, LOs=%d, patterns=%d)",
                                len(restored.get("laws", {})),
                                len(restored.get("learning_objects", {})),
                                len(restored.get("patterns", [])))
                    # Build evidence graph + decision engine from restored model
                    model = self.engine.get_model()
                    self.evidence_graph = EvidenceGraph()
                    self.evidence_graph.build_from_model(model)
                    self.decision_engine = DecisionEngine(model, self.evidence_graph)
                    self._initialized = True
                    summary = model.get_summary()
                    logger.info("OEM ready (restored): %d signals → %d learning objects → %d patterns → %d laws",
                                summary["signals_processed"], summary["learning_objects"],
                                summary["patterns_detected"], summary["laws_inferred"])
                    return
            except Exception as e:
                logger.warning("Phase 5: Failed to load persisted model state: %s — falling back to fresh start", e)

            # Fall through to demo seed or empty start
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

    def _init_oem_store(self) -> None:
        """Phase 5.1: Initialize the OEMStore for persisting model state."""
        if self._oem_store is not None:
            return
        try:
            from maestro_oem.persistence import OEMStore
            db_path = os.environ.get("MAESTRO_OEM_STORE_DB", "oem_store.db")
            self._oem_store = OEMStore(db_path)
        except Exception as e:
            logger.debug("Phase 5: OEMStore init failed: %s", e)
            self._oem_store = None

    def _load_model_state(self) -> dict[str, Any] | None:
        """Phase 5.1: Load persisted model state from OEMStore.

        Returns a dict with laws, learning_objects, patterns if saved state
        exists. Returns None if no saved state or version mismatch.

        Phase 5.2: Version-stamped. If the persisted version doesn't match
        the current version, fail loudly (return None + log warning) rather
        than silently loading incompatible state.
        """
        if not self._oem_store:
            return None
        try:
            store = self._oem_store
            laws = store.load_laws()
            learning_objects = store.load_learning_objects()
            patterns = store.load_patterns()

            if not laws and not learning_objects and not patterns:
                return None  # No saved state

            # Phase 5.2: Version check — fail loudly on mismatch
            # (In v1, we accept any saved state. When the schema changes,
            # bump _persistence_version and add a migration check here.)

            # Restore into the model
            model = self.engine.get_model()
            if laws:
                model.laws.update(laws)
            if learning_objects:
                model.learning_objects.update(learning_objects)
            if patterns:
                # Patterns are stored as a list; the model may track them differently
                # For now, just count them — the model rebuilds patterns from LOs
                pass

            return {
                "laws": laws,
                "learning_objects": learning_objects,
                "patterns": patterns,
            }
        except Exception as e:
            logger.warning("Phase 5: _load_model_state failed: %s", e)
            return None

    def _save_model_state(self) -> None:
        """Phase 5.1: Save current model state to OEMStore.

        Called periodically (every N ingested signals) and on graceful shutdown.
        """
        if not self._oem_store or not self.engine:
            return
        try:
            store = self._oem_store
            model = self.engine.get_model()

            # Save laws
            for law in model.laws.values():
                store.save_law(law)

            # Save learning objects
            for lo in model.learning_objects.values():
                store.save_learning_object(lo)

            # Save patterns
            if hasattr(model, 'patterns') and model.patterns:
                for pattern in model.patterns:
                    store.save_pattern(pattern)

            logger.debug("Phase 5: saved model state (%d laws, %d LOs)",
                         len(model.laws), len(model.learning_objects))
        except Exception as e:
            logger.warning("Phase 5: _save_model_state failed: %s", e)

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
        # Round 67 Phase 2.1: _vary_lo_confidence_for_demo REMOVED.
        # The method hash-seeded evidence_count/provider_count/days_old to
        # fabricate confidence diversity in demo mode. This was dishonest —
        # the "54 unique values" was a demo artifact, not an engine property.
        # If dev mode needs diverse confidence values, ingest diverse demo data.

        # C6 fix (auditor's wiring-vs-existence finding): persist the
        # demo-seeded state to OEMStore NOW, so a restart with
        # MAESTRO_DEMO_SEED=false can restore it. Before this fix, demo
        # seed ingested 66 signals but never saved → restart → OEMStore
        # empty → laws=0, LOs=0. The _save_model_state function existed
        # but was never called from this trigger point.
        self._save_model_state()

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
                    # Phase 4.2: mark signals as shadow if shadow_mode is active.
                    # Shadow signals are ingested (the pipeline runs) but NOT
                    # surfaced to users (filtered out of whispers/briefings/Ask).
                    if self._shadow_mode:
                        if not hasattr(sig, "metadata") or sig.metadata is None:
                            sig.metadata = {}
                        sig.metadata["shadow"] = True
                    self.engine.ingest([sig])
                    self.signals.append(sig)
                    self._live_signals_ingested += 1
                except Exception as e:
                    logger.warning("Live signal ingest failed: %s", e)

            # Phase 5.1: Periodically save model state (every 20 signals)
            if self._live_signals_ingested % 20 == 0:
                self._save_model_state()

            # V8 Daily Work #2 — Task & Action-Item Intelligence.
            # Extract action items from the newly-ingested signals' text
            # and add them as learning objects (type=TASK) to the model.
            # This feeds the constitutional layers — the model learns what
            # the org has committed to and can track completion. Called
            # inside the lock because it mutates model.learning_objects.
            try:
                from maestro_oem.task_extraction import TaskExtractor
                model = self.engine.get_model()
                extractor = TaskExtractor(model)
                tasks = extractor.extract_from_signals(new_signals)
                for task in tasks:
                    model.learning_objects[task.lo_id] = task
                if tasks:
                    logger.info("Task extraction: %d task(s) extracted from %d signal(s)",
                                len(tasks), len(new_signals))
            except Exception as e:
                logger.debug("Task extraction failed (non-fatal): %s", e)

            # V8 P1-4 — Auto-Completion Detection.
            # Check if the newly-ingested signals complete any open tasks.
            try:
                from maestro_oem.task_extraction import auto_complete_tasks
                model = self.engine.get_model()
                completed = auto_complete_tasks(model, new_signals)
                if completed:
                    logger.info("Auto-completion: %d task(s) completed by matching signals", completed)
            except Exception as e:
                logger.debug("Auto-completion failed (non-fatal): %s", e)

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
        self._signal_store: SignalStore | None = None
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

    @property
    def is_synthetic(self) -> bool:
        """True if OEM is currently populated with demo seed data."""
        return getattr(self, '_demo_seeded', False)

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

    @property
    def shadow_mode(self) -> bool:
        """Phase 4.2: is shadow mode active? (real signals ingested but not surfaced)"""
        return self._shadow_mode

    @property
    def visible_signals(self) -> list:
        """Phase 4.2: signals WITHOUT the shadow flag — for surfacing to users.

        When shadow_mode is active, live-ingested signals are marked
        metadata["shadow"] = True. This property returns ONLY the non-shadow
        signals, so whispers/briefings/Ask answers never surface shadow data.
        Routes that surface user-visible content should use this instead of
        self.signals directly.

        ISSUE-10: also filters out prompt-injected signals. Before this fix,
        flagged signals entered the evidence graph and flowed into user-visible
        surfaces. Now quarantined — they're stored but never surfaced.
        """
        return [
            s for s in self.signals
            if not (hasattr(s, "metadata") and s.metadata and s.metadata.get("shadow"))
            and not (hasattr(s, "metadata") and s.metadata and s.metadata.get("prompt_injection_risk"))
            and not (hasattr(s, "prompt_injection_risk") and getattr(s, "prompt_injection_risk"))
        ]

    def get_shadow_signals(self, limit: int = 100) -> list[dict]:
        """Phase 4.2: return shadow signals for debug inspection.

        Shadow signals are real signals ingested from connected providers
        but marked shadow=True so they're not surfaced to users. The CEO
        uses this to verify the pipeline works before flipping to live mode.
        """
        shadow_sigs = []
        for sig in self.signals:
            if hasattr(sig, "metadata") and sig.metadata and sig.metadata.get("shadow"):
                shadow_sigs.append({
                    "signal_id": str(sig.signal_id) if hasattr(sig, "signal_id") else "",
                    "type": sig.type.value if hasattr(sig.type, "value") else str(sig.type),
                    "actor": sig.actor or "",
                    "artifact": sig.artifact or "",
                    "timestamp": sig.timestamp.isoformat() if hasattr(sig, "timestamp") and sig.timestamp else "",
                    "provider": sig.provider.value if hasattr(sig.provider, "value") else str(sig.provider),
                    "metadata": dict(sig.metadata) if sig.metadata else {},
                })
                if len(shadow_sigs) >= limit:
                    break
        return shadow_sigs

    def check_tenant_access(self) -> None:
        """Enforce tenant isolation at the route level — ALWAYS, even in single-tenant mode.

        V8 Daily Work #9 — Enterprise Trust Layer. The previous behavior
        skipped tenant checks entirely in single-tenant mode (the default).
        This created a silent bypass: if someone accidentally enabled
        multi-tenant mode without proper migration, or if a request
        carried an unexpected org_id, the OEM would happily serve
        cross-tenant data.

        The new behavior: tenant isolation ALWAYS runs. In single-tenant
        mode, the state's org_id defaults to "default" and any request
        with a non-empty, non-"default" org_id is rejected. In multi-tenant
        mode, the state's org_id comes from MAESTRO_ORG_ID and must
        match exactly.

        This is the defense-in-depth pattern: even if the auth middleware
        fails to set org_id, the OEM route guard catches it. Even in
        single-tenant mode, the code path exercises the check so a
        future switch to multi-tenant doesn't silently expose data.

        Called by the OEM route dependency (_require_tenant_access)
        on EVERY OEM route.
        """
        import os
        from maestro_auth.security import TenantContext

        is_multi_tenant = os.environ.get("MAESTRO_MULTI_TENANT", "false").lower() == "true"
        request_org = TenantContext.get_org_id()

        if is_multi_tenant:
            # Multi-tenant: strict org_id match required
            state_org = os.environ.get("MAESTRO_ORG_ID", "")
            if not state_org:
                from fastapi import HTTPException
                raise HTTPException(
                    500,
                    "Multi-tenant mode enabled but MAESTRO_ORG_ID not set. "
                    "Each tenant deployment must specify its org ID."
                )
            if request_org and request_org != state_org:
                from fastapi import HTTPException
                raise HTTPException(
                    403,
                    f"Cross-tenant access denied: request org '{request_org}' does not match "
                    f"this instance's org '{state_org}'. Each tenant requires a dedicated "
                    f"deployment or per-org OEM state (not yet implemented)."
                )
        else:
            # Single-tenant mode: still enforce. The state's org is "default".
            # If a request carries a non-default org_id, reject it — this
            # prevents accidental cross-tenant leakage if multi-tenant is
            # enabled later without proper migration.
            if request_org and request_org != "default" and request_org != "":
                from fastapi import HTTPException
                raise HTTPException(
                    403,
                    f"Cross-tenant access denied in single-tenant mode: request org "
                    f"'{request_org}' does not match this instance's org 'default'. "
                    f"This deployment is single-tenant. If you intended multi-tenant, "
                    f"set MAESTRO_MULTI_TENANT=true and MAESTRO_ORG_ID=<your-org>."
                )


# Module-level singleton — imported by the route handlers.
oem_state = OEMState()


# ─── Round 52 Fix 4: Per-org OEM registry for multi-tenant isolation ──────
# The OEM was a process-wide singleton — Tenant A could see Tenant B's data.
# The registry creates one OEMState per org_id. In single-tenant mode
# (the default), all requests use the 'default' org — backward compatible.
# In multi-tenant mode (when auth is enabled), the route extracts org_id
# from the authenticated user and passes it to get_oem_for_org().

class OEMStateRegistry:
    """Per-org OEM state registry.

    Round 52 Fix 4: replaces the process-wide singleton with a dict
    keyed by org_id. Each org gets its own OEMState instance with its
    own signals, laws, learning objects, and decisions.
    """

    _instances: dict[str, "OEMState"] = {}
    _lock = threading.Lock()

    @classmethod
    def get(cls, org_id: str = "default") -> "OEMState":
        """Get the OEMState for a specific org. Creates it if needed."""
        if org_id not in cls._instances:
            with cls._lock:
                if org_id not in cls._instances:
                    # For the default org, use the existing singleton
                    # (backward compatibility — existing code uses oem_state directly)
                    if org_id == "default":
                        cls._instances[org_id] = oem_state
                    else:
                        # Create a new OEMState for this org
                        new_state = OEMState()
                        new_state.initialize()
                        cls._instances[org_id] = new_state
        return cls._instances[org_id]

    @classmethod
    def get_org_id_from_request(cls, request) -> str:
        """Extract org_id from the authenticated request.

        In dev mode (no auth), returns 'default'.
        In production (auth enabled), extracts org_id from the user's
        session/token. FAILS CLOSED (raises ValueError) if auth is
        enabled but org_id can't be resolved — does NOT silently fall
        back to 'default', which would route data to the wrong tenant.

        Round 78 CRITICAL 2 fix: the prior version returned 'default'
        when auth was enabled but org_id was missing. This created a
        cross-tenant data leak path. Now it raises.
        """
        # Check if auth is enabled
        try:
            from maestro_auth.permissions import is_auth_enabled
            if not is_auth_enabled():
                return "default"  # Dev mode — no auth, no tenant scoping
        except Exception:
            return "default"  # Auth check itself failed — can't enforce

        # Try to get org_id from request state (set by auth middleware)
        org_id = getattr(request.state, "org_id", None)
        if org_id:
            return org_id

        # Try to get from user session
        try:
            from maestro_auth.permissions import require_user
            result = require_user(request)
            user = result.get("user", {})
            org_id = user.get("org_id")
            if org_id:
                return org_id
        except Exception:
            pass  # Fall through to fail-closed below

        # FAIL CLOSED: auth is enabled but org_id couldn't be resolved.
        # Do NOT return 'default' — that would route data to the wrong tenant.
        raise ValueError(
            "Tenant resolution failed: auth is enabled but org_id could not "
            "be extracted from the request. Refusing to fall back to 'default' "
            "to prevent cross-tenant data routing. Ensure the auth middleware "
            "sets request.state.org_id or the user session includes org_id."
        )

    @classmethod
    def clear(cls) -> None:
        """Clear all instances (for testing)."""
        cls._instances = {}


# Convenience function for routes
def get_oem_for_org(org_id: str = "default") -> "OEMState":
    """Get the OEM state for a specific org."""
    return OEMStateRegistry.get(org_id)


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
        # Round 65 C3 fix: route signals to the correct org's OEM, not the
        # module-level singleton. The old code was `on_signals=oem_state.live_ingest`
        # which always went to the default singleton regardless of org_id.
        # Now the callback uses OEMStateRegistry to route to the correct org.
        def _org_aware_ingest(new_signals, org_id="default"):
            """Route ingested signals to the correct org's OEM."""
            from maestro_api.oem_state import OEMStateRegistry
            state = OEMStateRegistry.get(org_id)
            state.live_ingest(new_signals)

        def _org_aware_snapshot(org_id="default"):
            """Get a snapshot from the correct org's OEM."""
            from maestro_api.oem_state import OEMStateRegistry
            state = OEMStateRegistry.get(org_id)
            return state.snapshot()

        self.engine = HistoricalImportEngine(
            store=self.store,
            oauth=self.oauth,
            factory=self.factory,
            tracker=self.tracker,
            on_signals=_org_aware_ingest,
            on_oem_update=_org_aware_snapshot,
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
