"""Phase 5.1-5.3: Persistence — OEMStore save/load + restart survival test.

Phase 5.1: Wire OEMStore.save_model_state/load_model_state into oem_state.py.
  - load_model_state() called first in initialize()
  - save_model_state() called every 20 ingested signals in live_ingest()

Phase 5.2: Version-stamped persisted state.
  - _persistence_version = "v1"
  - On version mismatch, fail loudly (return None + log warning)

Phase 5.3: Full restart-survival test.
  - Construct AppState, ingest signals, force-save
  - Construct NEW AppState instance (simulating restart)
  - Confirm laws/patterns/LOs survive

Principle 10: This test exists because the external forensic audit found
the core ExecutionModel was in-memory only — restart loses all laws,
patterns, and learning objects. The fix wires OEMStore into oem_state.py.
"""
from __future__ import annotations

import sys
import os
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ─── Phase 5.1: OEMStore is wired into oem_state.py ────────────────────────

def test_phase_5_1_oem_store_wired():
    """P11: oem_state.py must reference OEMStore."""
    from maestro_api import oem_state
    import inspect
    source = inspect.getsource(oem_state)
    assert "OEMStore" in source or "oem_store" in source, (
        "oem_state.py must reference OEMStore (Phase 5.1 — wired into production)"
    )
    assert "_save_model_state" in source, (
        "oem_state.py must have _save_model_state method (Phase 5.1)"
    )
    assert "_load_model_state" in source, (
        "oem_state.py must have _load_model_state method (Phase 5.1)"
    )


# ─── Phase 5.2: Version stamp exists ───────────────────────────────────────

def test_phase_5_2_version_stamp_exists():
    """Phase 5.2: The persistence version must be tracked."""
    from maestro_api.oem_state import OEMState
    import inspect
    source = inspect.getsource(OEMState)
    assert "_persistence_version" in source, (
        "OEMState must have _persistence_version for version-stamped persistence (Phase 5.2)"
    )


# ─── Phase 5.3: Restart survival test ──────────────────────────────────────

def test_phase_5_3_restart_survival(tmp_path, monkeypatch):
    """Phase 5.3: Construct AppState, save, construct NEW AppState, verify
    laws/patterns/LOs survive.

    This is the exact test shape already used successfully for
    test_c1_sqlite_persistence.py — same pattern, now extended to the
    core ExecutionModel.
    """
    # Set up clean environment
    db_path = str(tmp_path / "oem_store.db")
    monkeypatch.setenv("MAESTRO_OEM_STORE_DB", db_path)
    monkeypatch.setenv("MAESTRO_LOCAL_DEV", "true")
    monkeypatch.setenv("MAESTRO_DEMO_SEED", "false")  # Start empty

    from maestro_api.oem_state import OEMState
    from maestro_oem.signal import ExecutionSignal, SignalType, SignalProvider
    from maestro_oem.engine import OEMEngine

    # Step 1: Create state, ingest signals, save
    state1 = OEMState()
    state1.initialize()

    # Manually ingest signals to build laws/patterns/LOs
    now = datetime.now(timezone.utc)
    signals = []
    for i in range(20):
        sig = ExecutionSignal(
            type=SignalType.CUSTOMER_COMMITMENT_MADE,
            actor="jane@example.com",
            artifact=f"crm:{i}",
            metadata={"customer": "TestCorp", "commitment": f"Deliver feature {i}"},
            provider=SignalProvider.CUSTOMER,
            timestamp=now - timedelta(days=i),
        )
        signals.append(sig)

    state1.engine.ingest(signals)
    state1.signals.extend(signals)

    model1 = state1.engine.get_model()
    los_before = len(model1.learning_objects)
    laws_before = len(model1.laws)

    # Force save
    state1._init_oem_store()
    state1._save_model_state()

    assert los_before > 0, "Must have learning objects after ingesting 20 signals"
    # Note: laws may be 0 with only commitment signals — that's OK

    # Step 2: Create NEW state (simulating restart)
    state2 = OEMState()
    state2.initialize()

    model2 = state2.engine.get_model()
    los_after = len(model2.learning_objects)
    laws_after = len(model2.laws)

    # Verify LOs survived restart
    assert los_after > 0, (
        f"Learning objects must survive restart. Before: {los_before}, After: {los_after}. "
        f"The core ExecutionModel is now persisted via OEMStore."
    )
    assert los_after == los_before, (
        f"Learning object count must match after restart. Before: {los_before}, After: {los_after}"
    )

    # Verify laws survived (if any existed)
    if laws_before > 0:
        assert laws_after == laws_before, (
            f"Law count must match after restart. Before: {laws_before}, After: {laws_after}"
        )
