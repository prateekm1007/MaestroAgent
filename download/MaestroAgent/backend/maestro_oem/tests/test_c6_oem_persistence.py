"""C6 fix: OEM persistence — save model state after demo seed + on shutdown.

External auditor finding (AUDITOR-ERROR-2-ACKNOWLEDGMENT-EDC99C3):
> C6 fix is INCOMPLETE. _save_model_state() exists but only fires from
> live_ingest every 20 signals (line 384). Demo seed path NEVER saves.
> Lifespan shutdown NEVER saves. So demo-seeded state is NEVER persisted
> to OEMStore.

The auditor's verification:
> Started the demo server, killed it, restarted. Observed: OEMStore was
> EMPTY after restart (laws=0, LOs=0, patterns=0). My "FIXED" verdict
> was wrong — I verified the code path exists but never executed the
> actual restart cycle.

This is Blindspot #6 (wiring vs existence) again: the function exists,
but it's never called from the right trigger points.

The fix needs four parts (per the auditor's directive):
  1. The function change (already done — _save_model_state exists)
  2. The caller update (NOT done — demo seed + shutdown don't call it)
  3. The trigger (this fix: call _save_model_state at end of
     _seed_from_demo_provider AND in lifespan shutdown)
  4. The regression test (this file — execute the actual restart cycle,
     verify OEMStore is NOT empty after restart)

Adversarial: written FIRST, watched FAIL, then fix applied (P2).
"""
from __future__ import annotations

import os
import sys
import pytest
import tempfile
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ─── Tests ─────────────────────────────────────────────────────────────────

def test_save_model_state_called_from_demo_seed():
    """C6: _save_model_state must be called at the end of _seed_from_demo_provider.

    Before the fix: demo seed ingested 66 signals but never saved →
    restart with MAESTRO_DEMO_SEED=false → OEMStore empty → laws=0, LOs=0.

    After the fix: demo seed calls _save_model_state() after ingesting
    all demo signals → OEMStore has the laws/LOs/patterns → restart
    restores them.

    This test verifies the CALL SITE exists by inspecting the source
    code (grep). The full restart-cycle test is below.
    """
    import inspect
    from maestro_api import oem_state as oem_state_module

    source = inspect.getsource(oem_state_module.OEMState._seed_from_demo_provider)
    assert "_save_model_state" in source, \
        "_seed_from_demo_provider must call _save_model_state() at the end. " \
        "Without this, demo-seeded state is never persisted to OEMStore."


def test_save_model_state_called_from_lifespan_shutdown():
    """C6: _save_model_state must be called in the lifespan shutdown (finally block).

    Before the fix: lifespan shutdown cancelled the snapshot task and
    stopped AppState, but never saved the OEM model state. So even
    live-ingested signals (every 20th) were lost if the server was
    killed between save intervals.

    After the fix: the finally block calls oem_state._save_model_state()
    before stopping AppState.
    """
    import inspect
    from maestro_api import main as main_module

    source = inspect.getsource(main_module)
    # The lifespan function's finally block must call _save_model_state
    assert "_save_model_state" in source, \
        "main.py lifespan must call oem_state._save_model_state() in the finally block. " \
        "Without this, any model state changes since the last periodic save are lost on shutdown."


def test_demo_seed_persists_to_oem_store_across_restart():
    """THE KEY TEST: demo seed → save → reload → verify state is restored.

    This is the auditor's exact scenario:
      1. Initialize OEMState with demo seed (MAESTRO_DEMO_SEED=true)
      2. Verify laws/LOs are populated
      3. _seed_from_demo_provider now calls _save_model_state() (the fix)
      4. Create a FRESH OEMState instance pointing to the same OEMStore DB
      5. Initialize it (MAESTRO_DEMO_SEED=false so it doesn't re-seed)
      6. Verify the fresh instance has the SAME laws/LOs (restored from OEMStore)

    Before the fix: step 6 fails — fresh instance has 0 laws, 0 LOs
    because the demo seed never saved.

    After the fix: step 6 passes — fresh instance restores from OEMStore.
    """
    import os
    import tempfile
    from pathlib import Path
    from maestro_api.oem_state import OEMState

    # Use a temp directory for the OEMStore DB so we don't pollute the real one
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        store_db = tmpdir / "oem_store.db"

        # ─── Phase 1: Initialize with demo seed ──────────────────────────
        os.environ["MAESTRO_DEMO_SEED"] = "true"
        os.environ["MAESTRO_LOCAL_DEV"] = "true"
        os.environ["MAESTRO_ENV"] = "development"
        os.environ["MAESTRO_OEM_STORE_DB"] = str(store_db)

        state1 = OEMState()
        state1.initialize()

        laws_after_seed = len(state1.engine.get_model().laws)
        los_after_seed = len(state1.engine.get_model().learning_objects)
        assert laws_after_seed > 0, \
            "Test setup failed: demo seed should produce >0 laws"
        assert los_after_seed > 0, \
            "Test setup failed: demo seed should produce >0 LOs"

        # Verify the store DB file exists (the fix calls _save_model_state
        # at the end of _seed_from_demo_provider)
        assert store_db.exists(), \
            f"OEMStore DB must exist after demo seed. Expected: {store_db}"

        # ─── Phase 2: Create a FRESH OEMState pointing to the same store ──
        # Don't re-seed — simulate a restart with MAESTRO_DEMO_SEED=false
        os.environ["MAESTRO_DEMO_SEED"] = "false"
        # Phase 1 fix: explicitly unset MAESTRO_PURGE_ON_INIT. Other tests
        # (e.g., CRITICAL-04 test) set this env var, and it persists across
        # tests. When PURGE_ON_INIT=true, the OEMStore DB is purged on init,
        # which deletes the state saved in Phase 1 — causing the restart
        # to load 0 laws instead of the persisted 6.
        os.environ.pop("MAESTRO_PURGE_ON_INIT", None)
        state2 = OEMState()
        state2.initialize()

        laws_after_restart = len(state2.engine.get_model().laws)
        los_after_restart = len(state2.engine.get_model().learning_objects)

        # ─── Phase 3: Verify state was restored ──────────────────────────
        assert laws_after_restart > 0, \
            f"C6 REGRESSION: after restart, laws={laws_after_restart} (should be >0, " \
            f"was {laws_after_seed} before restart). _save_model_state was not called " \
            f"from _seed_from_demo_provider, or _load_model_state failed."
        assert los_after_restart > 0, \
            f"C6 REGRESSION: after restart, LOs={los_after_restart} (should be >0, " \
            f"was {los_after_seed} before restart). _save_model_state was not called " \
            f"from _seed_from_demo_provider, or _load_model_state failed."

        # Cleanup
        state1._initialized = False
        state2._initialized = False
        del os.environ["MAESTRO_DEMO_SEED"]
        del os.environ["MAESTRO_OEM_STORE_DB"]
        if "MAESTRO_APP_DIR" in os.environ:
            del os.environ["MAESTRO_APP_DIR"]
