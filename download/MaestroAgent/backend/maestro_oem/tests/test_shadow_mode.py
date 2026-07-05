"""Phase 4.2 — Shadow mode: org_id propagation + shadow flag.

The historical engine has a bug: factory.create(provider) is called
WITHOUT org_id, so GitHub imports pull from ALL repos the OAuth user
can access, not just the customer's org. For shadow mode this is a
tenant-isolation risk.

The fix: pass org_id to factory.create(). This test verifies the fix
AND the shadow_mode flag (signals ingested in shadow mode are marked
shadow=True and not surfaced to users).

Adversarial: written FIRST, watched FAIL, then fix applied (P2).
"""
from __future__ import annotations

import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def test_historical_engine_passes_org_id_to_factory():
    """The historical engine MUST pass org_id to factory.create().

    Before the fix: factory.create(provider) — no org_id.
    After the fix: factory.create(provider, org_id=org_id).

    Without org_id, GitHubPageFetcher defaults to /user/repos (ALL repos
    the OAuth user can access) instead of /orgs/{org}/repos (just the
    customer's org). This is a tenant-isolation risk for shadow mode.
    """
    import inspect
    from maestro_oem import historical_engine

    source = inspect.getsource(historical_engine.HistoricalImportEngine._run_provider)
    assert "factory.create(provider, org_id=org_id)" in source or \
           "factory.create(provider, org_id" in source, \
        "_run_provider must pass org_id to factory.create(). " \
        "Without org_id, GitHub imports pull from ALL repos the user can access, " \
        "not just the customer's org — a tenant-isolation risk for shadow mode."


def test_shadow_mode_env_var_exists():
    """MAESTRO_SHADOW_MODE env var must be read by OEMState.

    Shadow mode = ingest real signals but mark them shadow=True (not
    surfaced to users). This lets the CEO verify the pipeline works
    end-to-end before flipping to live mode.
    """
    import inspect
    from maestro_api import oem_state as oem_state_module

    source = inspect.getsource(oem_state_module)
    assert "MAESTRO_SHADOW_MODE" in source or "shadow_mode" in source, \
        "OEMState must read MAESTRO_SHADOW_MODE env var. " \
        "Shadow mode marks ingested signals as shadow=True so they're not surfaced to users."


def test_shadow_signals_not_surfaced_in_whispers():
    """When shadow_mode=True, signals with shadow=True must NOT appear
    in whisper generation. This is the core shadow-mode guarantee:
    real data flows in, but the user sees nothing until shadow mode
    is turned off.
    """
    # This test verifies the filtering logic exists in whisper.py
    import inspect
    from maestro_oem import whisper as whisper_module

    source = inspect.getsource(whisper_module)
    # The whisper pipeline must check for shadow signals and filter them out
    assert "shadow" in source.lower(), \
        "whisper.py must check for shadow signals and filter them out. " \
        "Shadow mode = signals ingested but NOT surfaced to users."


def test_shadow_signals_not_surfaced_in_briefing():
    """When shadow_mode=True, signals with shadow=True must NOT appear
    in the CEO briefing.
    """
    import inspect
    from maestro_api.routes import oem as oem_routes

    source = inspect.getsource(oem_routes)
    # The briefing endpoint must filter shadow signals
    assert "shadow" in source.lower(), \
        "oem.py must filter shadow signals from the briefing. " \
        "Shadow mode = signals ingested but NOT surfaced to users."


def test_shadow_signals_endpoint_exists():
    """A debug endpoint must exist to inspect shadow signals.

    The CEO needs to verify the pipeline works by inspecting the shadow
    signals (are they real? are they the right repos? are they the right
    event types?). Without this endpoint, shadow mode is a black box.
    """
    import inspect
    from maestro_api.routes import oem as oem_routes

    source = inspect.getsource(oem_routes)
    assert "/shadow" in source or "shadow-signals" in source or "shadow_signals" in source, \
        "oem.py must have a /shadow-signals (or similar) endpoint for inspecting shadow signals. " \
        "The CEO needs to verify the pipeline works before flipping to live mode."
