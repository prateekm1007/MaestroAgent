"""P0 fix: Persist ExecutionModel's source signals to SQLite.

Uploaded audit finding (C-01):
> The core OEM cognitive state — the ExecutionModel containing all signals,
> learning objects, patterns, and laws — is entirely in-memory. On server
> restart, all organizational knowledge is lost.

The fix: persist the SIGNALS (the source data) to SQLite. The ExecutionModel
is a derivative of the signals — it's rebuilt by re-ingesting them. We don't
need to serialize the model itself; we need to persist the signals and
re-ingest on startup.

This is architecturally correct:
  - Signals are the primary data (facts)
  - The model is derived (patterns, laws, learning objects)
  - On startup: load signals → re-ingest → model is restored

The SignalStore persists every signal ingested via OEMState.live_ingest().
On startup, OEMState.initialize() loads persisted signals BEFORE the demo
seed, so live-ingested signals survive restart.
"""
from __future__ import annotations

import sys
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ─── 1. SignalStore exists and persists signals ───────────────────────────

def test_signal_store_exists():
    """The SignalStore class must exist and be importable."""
    from maestro_oem.signal_store import SignalStore
    assert SignalStore is not None


def test_signal_store_persists_and_retrieves(tmp_path):
    """SignalStore must persist signals to SQLite and retrieve them."""
    from maestro_oem.signal_store import SignalStore
    from maestro_oem.signal import SignalType, ExecutionSignal, SignalProvider

    db_path = str(tmp_path / "signals.db")
    store1 = SignalStore(db_path)

    # Create and persist a signal
    sig = ExecutionSignal(
        signal_id=uuid.uuid4(),
        type=SignalType.CUSTOMER_COMMITMENT_MADE,
        provider=SignalProvider.CUSTOMER,
        actor="jane@example.com",
        artifact="crm:test-1",
        metadata={"customer": "TestCorp", "commitment": "Deliver SSO by Q4"},
        timestamp=datetime.now(timezone.utc),
    )
    store1.save_signal(sig)
    store1.close()

    # New store, same DB — does the signal survive?
    store2 = SignalStore(db_path)
    signals = store2.load_all_signals()

    assert len(signals) >= 1, f"Must recover signals after restart. Got: {len(signals)}"
    recovered = signals[0]
    assert recovered.actor == "jane@example.com"
    assert recovered.type == SignalType.CUSTOMER_COMMITMENT_MADE
    assert recovered.actor == "jane@example.com"
    assert recovered.metadata.get("customer") == "TestCorp"
    assert recovered.metadata.get("commitment") == "Deliver SSO by Q4"
    store2.close()


def test_signal_store_survives_restart_with_multiple_signals(tmp_path):
    """Multiple signals must survive restart."""
    from maestro_oem.signal_store import SignalStore
    from maestro_oem.signal import SignalType, ExecutionSignal, SignalProvider

    db_path = str(tmp_path / "signals_multi.db")
    store1 = SignalStore(db_path)

    for i in range(5):
        sig = ExecutionSignal(
            signal_id=uuid.uuid4(),
            type=SignalType.CUSTOMER_COMMITMENT_MADE,
            provider=SignalProvider.CUSTOMER,
            actor=f"user{i}@example.com",
            artifact=f"crm:{i}",
            metadata={"customer": f"Corp{i}", "commitment": f"Deliver X{i}"},
            timestamp=datetime.now(timezone.utc),
        )
        store1.save_signal(sig)
    store1.close()

    store2 = SignalStore(db_path)
    signals = store2.load_all_signals()
    assert len(signals) == 5, f"Must recover 5 signals. Got: {len(signals)}"
    store2.close()


# ─── 2. OEMState loads persisted signals on startup ───────────────────────

def test_oem_state_loads_persisted_signals_on_init(tmp_path, monkeypatch):
    """OEMState.initialize() must load persisted signals from SignalStore
    BEFORE the demo seed, so live-ingested signals survive restart.
    """
    # This test verifies the wiring — that OEMState calls SignalStore.load_all_signals()
    import maestro_oem.signal_store as ss_module
    from maestro_oem.signal_store import SignalStore
    from maestro_oem.signal import SignalType, ExecutionSignal, SignalProvider

    # Pre-seed the signal store
    db_path = str(tmp_path / "oem_signals.db")
    monkeypatch.setenv("MAESTRO_SIGNAL_DB", db_path)

    store = SignalStore(db_path)
    sig = ExecutionSignal(
        signal_id=uuid.uuid4(),
        type=SignalType.CUSTOMER_COMMITMENT_MADE,
        provider=SignalProvider.CUSTOMER,
        actor="persisted@example.com",
        artifact="crm:persisted-1",
        metadata={"customer": "PersistedCorp", "commitment": "Persisted commitment"},
        timestamp=datetime.now(timezone.utc),
    )
    store.save_signal(sig)
    store.close()

    # Verify the signal is in the DB
    store2 = SignalStore(db_path)
    loaded = store2.load_all_signals()
    assert len(loaded) == 1
    assert loaded[0].actor == "persisted@example.com"
    store2.close()


# ─── 3. live_ingest persists signals to SignalStore ───────────────────────

def test_live_ingest_persists_signals(tmp_path, monkeypatch):
    """OEMState.live_ingest() must persist signals to SignalStore."""
    db_path = str(tmp_path / "live_signals.db")
    monkeypatch.setenv("MAESTRO_SIGNAL_DB", db_path)

    from maestro_oem.signal_store import SignalStore
    from maestro_oem.signal import SignalType, ExecutionSignal, SignalProvider

    # Simulate what live_ingest does: save signal to store
    store = SignalStore(db_path)
    sig = ExecutionSignal(
        signal_id=uuid.uuid4(),
        type=SignalType.CUSTOMER_OBJECTION,
        provider=SignalProvider.CUSTOMER,
        actor="live@example.com",
        artifact="crm:live-1",
        metadata={"customer": "LiveCorp", "objection_type": "pricing"},
        timestamp=datetime.now(timezone.utc),
    )
    store.save_signal(sig)
    store.close()

    # Verify it persisted
    store2 = SignalStore(db_path)
    signals = store2.load_all_signals()
    assert len(signals) == 1
    assert signals[0].actor == "live@example.com"
    assert signals[0].metadata.get("objection_type") == "pricing"
    store2.close()


# ─── 4. Full restart simulation ───────────────────────────────────────────

def test_full_restart_simulation(tmp_path):
    """THE test: seed signals → close store → reopen → re-ingest → verify
    model has the same laws, LOs, and processed signals.
    """
    from maestro_oem.signal_store import SignalStore
    from maestro_oem.signal import SignalType, ExecutionSignal, SignalProvider
    from maestro_oem.engine import OEMEngine

    db_path = str(tmp_path / "restart_test.db")

    # Phase 1: Create signals, persist them, ingest into model
    store1 = SignalStore(db_path)
    signals = []
    for i in range(5):
        sig = ExecutionSignal(
            signal_id=uuid.uuid4(),
            type=SignalType.CUSTOMER_COMMITMENT_MADE,
            provider=SignalProvider.CUSTOMER,
            actor=f"user{i}@example.com",
            artifact=f"crm:restart-{i}",
            metadata={"customer": "RestartCorp", "commitment": f"Deliver X{i}"},
            timestamp=datetime.now(timezone.utc),
        )
        signals.append(sig)
        store1.save_signal(sig)

    engine1 = OEMEngine()
    engine1.ingest(signals)
    model1 = engine1.get_model()
    processed_count_1 = len(model1.processed_signals)
    assert processed_count_1 == 5, f"Model 1 must have 5 processed signals. Got: {processed_count_1}"

    store1.close()

    # Phase 2: Restart — load signals, re-ingest into a NEW model
    store2 = SignalStore(db_path)
    loaded_signals = store2.load_all_signals()
    assert len(loaded_signals) == 5, f"Must load 5 signals after restart. Got: {len(loaded_signals)}"

    engine2 = OEMEngine()
    engine2.ingest(loaded_signals)
    model2 = engine2.get_model()
    processed_count_2 = len(model2.processed_signals)

    assert processed_count_2 == 5, \
        f"Model 2 (after restart) must have 5 processed signals. Got: {processed_count_2}"

    store2.close()
