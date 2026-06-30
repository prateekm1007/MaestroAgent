#!/usr/bin/env python3
"""Surgically rewrite oem_state.py to use DemoProvider instead of hardcoded seed.

Replaces:
  - The module docstring (mention DemoProvider + MAESTRO_DEMO_SEED)
  - The imports (drop provider normalizers, add DemoPageFetcher)
  - Lines 56-218 (the GITHUB_EVENTS/JIRA_EVENTS/.../GMAIL_EVENTS constants
    and the _build_signals function) with a single _demo_seed_enabled()
    helper and the new OEMState class body.

The rest of the file (live_ingest, _refresh_downstream, snapshot,
ImportState, import_state singleton) is left intact.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TARGET = REPO / "backend" / "maestro_api" / "oem_state.py"

src = TARGET.read_text()

# ─── 1. Replace the docstring + imports block (lines 1-52) ───────────────
new_header = '''"""
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

import asyncio
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
'''

# Find the end of the old imports block — right before the GITHUB_EVENTS line.
old_header_end_marker = "_IMPORT_DB_PATH = os.environ.get(\n"
old_header_end = src.index(old_header_end_marker)
# Find the end of that _IMPORT_DB_PATH assignment (closing paren + newline)
old_header_end_full = src.index(")\n\n", old_header_end) + 3

src = new_header + src[old_header_end_full:]

# ─── 2. Remove the GITHUB_EVENTS ... _build_signals block ────────────────
# It now starts with "# ─── Realistic signal data" and ends right before "class OEMState:".
block_start_marker = "# ─── Realistic signal data"
block_start = src.index(block_start_marker)
# Back up to the preceding blank line / comment start
block_start = src.rindex("\n", 0, block_start) + 1

block_end_marker = "class OEMState:"
block_end = src.index(block_end_marker)
# Keep one blank line before the class.
src = src[:block_start] + "\n" + src[block_end:]

# ─── 3. Rewrite OEMState.initialize() to use _seed_from_demo_provider() ─
old_init = '''    def initialize(self) -> None:
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
'''

new_init = '''    def initialize(self) -> None:
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
            DemoPageFetcher.fetch_page()  -> PageResult(items=[...])
            fetcher.normalize_item(item)  -> event dict
            normalize_<provider>(event)   -> ExecutionSignal
            oem_engine.ingest([sig])      -> laws / patterns / recommendations

        A bug in any of those steps would surface in demo mode, not just in
        production. Previously the demo seed bypassed this path entirely,
        hiding ingestion-pipeline bugs from the demo environment.
        """
        assert self.engine is not None
        loop = asyncio.new_event_loop()
        try:
            for provider in demo_provider_names():
                fetcher = DemoPageFetcher(provider)
                normalizer = get_demo_normalizer(provider)
                try:
                    page_result = loop.run_until_complete(fetcher.fetch_page(page=1))
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
        finally:
            loop.close()

        self._demo_seeded = True
'''

if old_init not in src:
    raise SystemExit("Could not find old initialize() method — aborting.")
src = src.replace(old_init, new_init)

# Also add _demo_seeded to __init__
old_init_ctor = "        self._contradiction_log = None  # Set on first contradict() call\n"
new_init_ctor = (
    "        self._contradiction_log = None  # Set on first contradict() call\n"
    "        self._demo_seeded = False  # True after the demo seed has been loaded\n"
)
if old_init_ctor in src and "_demo_seeded" not in src.split("class OEMState")[1][:2000]:
    src = src.replace(old_init_ctor, new_init_ctor)

TARGET.write_text(src)
print(f"Rewrote {TARGET}")
print(f"  - removed hardcoded GITHUB_EVENTS/JIRA_EVENTS/SLACK_EVENTS/CONFLUENCE_EVENTS/GMAIL_EVENTS")
print(f"  - removed _build_signals()")
print(f"  - added _demo_seed_enabled() helper")
print(f"  - added _seed_from_demo_provider() method on OEMState")
print(f"  - initialize() now honors MAESTRO_DEMO_SEED env var")
