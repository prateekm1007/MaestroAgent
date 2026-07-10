"""
Depth wiring tests — verify Core modules are wired to Personal.

Per CEO directive: "80% depth on Core. The complexity behind the screens."
"""

import sys
import os
import pathlib
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "backend"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import pytest


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-depth"
    import importlib
    import maestro_personal_shell.api as api_module
    importlib.reload(api_module)
    api_module.init_db(db_path)
    yield api_module
    os.unlink(db_path)
    del os.environ["MAESTRO_PERSONAL_DB"]
    del os.environ["MAESTRO_PERSONAL_TOKEN"]


@pytest.fixture
def client(temp_db):
    from fastapi.testclient import TestClient
    return TestClient(temp_db.app)


@pytest.fixture
def auth_headers(client):
    response = client.post("/api/auth/login", json={"password": os.environ.get("MAESTRO_PERSONAL_TOKEN", "test")})
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


class TestCoreWiring:
    """Verify Core modules are wired to Personal via CoreWiring."""

    def test_shell_has_core_property(self):
        """The shell must expose a .core property (CoreWiring)."""
        from maestro_personal_shell.shell import PersonalShell
        from maestro_personal_shell.personal_oem_state import PersonalOemState
        shell = PersonalShell(oem_state=PersonalOemState(signals=[]))
        assert hasattr(shell, 'core')

    def test_core_wiring_has_judgment_synthesizer(self):
        """CoreWiring must expose judgment_synthesizer."""
        from maestro_personal_shell.shell import PersonalShell
        from maestro_personal_shell.personal_oem_state import PersonalOemState
        shell = PersonalShell(oem_state=PersonalOemState(signals=[]))
        # The property should exist (may be None if import fails, but the property must exist)
        assert shell.core.judgment_synthesizer is not None  # must initialize (no or True)

    def test_core_wiring_has_calibration_primitives(self):
        """CoreWiring must expose calibration_primitives."""
        from maestro_personal_shell.shell import PersonalShell
        from maestro_personal_shell.personal_oem_state import PersonalOemState
        shell = PersonalShell(oem_state=PersonalOemState(signals=[]))
        _ = shell.core.calibration_primitives  # should not raise

    def test_core_wiring_has_briefing_bridge(self):
        """CoreWiring must expose briefing_bridge."""
        from maestro_personal_shell.shell import PersonalShell
        from maestro_personal_shell.personal_oem_state import PersonalOemState
        shell = PersonalShell(oem_state=PersonalOemState(signals=[]))
        _ = shell.core.briefing_bridge  # should not raise

    def test_core_wiring_has_copilot_bridge(self):
        """CoreWiring must expose copilot_bridge (Cluely-class)."""
        from maestro_personal_shell.shell import PersonalShell
        from maestro_personal_shell.personal_oem_state import PersonalOemState
        shell = PersonalShell(oem_state=PersonalOemState(signals=[]))
        _ = shell.core.copilot_bridge  # should not raise

    def test_core_wiring_has_epistemic_barrier(self):
        """CoreWiring must expose epistemic_barrier."""
        from maestro_personal_shell.shell import PersonalShell
        from maestro_personal_shell.personal_oem_state import PersonalOemState
        shell = PersonalShell(oem_state=PersonalOemState(signals=[]))
        _ = shell.core.epistemic_barrier  # should not raise

    def test_core_wiring_has_whisper_bridge(self):
        """CoreWiring must expose whisper_bridge (Core's WhisperSituationBridge)."""
        from maestro_personal_shell.shell import PersonalShell
        from maestro_personal_shell.personal_oem_state import PersonalOemState
        shell = PersonalShell(oem_state=PersonalOemState(signals=[]))
        _ = shell.core.whisper_bridge  # should not raise


class TestDepthEndpoint:
    """Verify the /api/depth endpoint reports wiring status."""

    def test_depth_endpoint_returns_count(self, client, auth_headers):
        """GET /api/depth returns the wiring count."""
        response = client.get("/api/depth", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "wired_count" in data
        assert "total_core_modules" in data
        assert "coverage_pct" in data
        assert data["total_core_modules"] == 23

    def test_depth_endpoint_lists_wired_modules(self, client, auth_headers):
        """GET /api/depth lists which modules are wired."""
        response = client.get("/api/depth", headers=auth_headers)
        data = response.json()
        assert "wired_modules" in data
        assert isinstance(data["wired_modules"], list)
        # At minimum, the 5 originally-wired modules must be present
        assert "situation_engine" in data["wired_modules"]
        assert "audit_safety" in data["wired_modules"]
        assert "ask_bridge" in data["wired_modules"]
        assert "delivery_governor" in data["wired_modules"]
        assert "preparation_bridge" in data["wired_modules"]


class TestAskDepth:
    """Verify Ask response includes depth fields from Core."""

    def test_ask_response_has_depth_fields(self, client, auth_headers):
        """Ask response must include decision_boundary, perspectives, reasoning_chain."""
        client.post("/api/signals", json={
            "entity": "Alex",
            "text": "I will send the proposal by Friday",
            "signal_type": "commitment_made",
        }, headers=auth_headers)

        response = client.post("/api/ask", json={
            "query": "What did I promise Alex?"
        }, headers=auth_headers)

        data = response.json()
        # Depth fields must exist (may be empty if Core modules aren't available,
        # but the fields must be present in the response)
        assert "decision_boundary" in data
        assert "perspectives" in data
        assert "reasoning_chain" in data
        assert "calibration_note" in data
        assert "consequence_paths" in data
