"""
Tests for the 3 remaining P0 fixes:
  1. Backend packaging (pip install -e . works, import without PYTHONPATH)
  2. Mobile auth (login no longer falls back to 'any')
  3. Audio transcription endpoint (POST /api/copilot/transcribe)

P22: Integration tests run the REAL production path (TestClient + real HTTP).
"""

import sys
import os
import tempfile
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


# ---------------------------------------------------------------------------
# P0 #3: Backend packaging — import without PYTHONPATH
# ---------------------------------------------------------------------------

class TestBackendPackaging:
    """P0 #3: The backend should be importable without PYTHONPATH manipulation."""

    def test_pyproject_toml_exists(self):
        """pyproject.toml must exist at the package root."""
        pyproject = os.path.join(os.path.dirname(__file__), "..", "pyproject.toml")
        assert os.path.exists(pyproject), "pyproject.toml missing"

    def test_pyproject_has_correct_package_name(self):
        """pyproject.toml must declare the maestro-personal package."""
        pyproject = os.path.join(os.path.dirname(__file__), "..", "pyproject.toml")
        with open(pyproject) as f:
            content = f.read()
        assert 'name = "maestro-personal"' in content
        assert "[project.scripts]" in content
        assert "maestro-personal" in content  # CLI entry point

    def test_pyproject_finds_src_layout(self):
        """pyproject.toml must configure src/ layout."""
        pyproject = os.path.join(os.path.dirname(__file__), "..", "pyproject.toml")
        with open(pyproject) as f:
            content = f.read()
        assert "[tool.setuptools.packages.find]" in content
        assert 'where = ["src"]' in content

    def test_import_works_from_any_directory(self):
        """P1: Execute — import from /tmp (not the package dir) to prove no PYTHONPATH needed."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "-c", "from maestro_personal_shell.connectors import ConnectorStore; print('OK')"],
            capture_output=True, text=True, cwd="/tmp",
        )
        assert result.returncode == 0, f"Import failed: {result.stderr}"
        assert "OK" in result.stdout


# ---------------------------------------------------------------------------
# P0 #4: Mobile auth — login no longer accepts 'any'
# ---------------------------------------------------------------------------

class TestMobileAuthFix:
    """P0 #4: The mobile login must NOT fall back to 'any' password."""

    def test_login_screen_has_no_any_fallback(self):
        """P1: Execute — grep the LoginScreen source for the 'any' fallback."""
        login_screen = os.path.join(os.path.dirname(__file__), "..", "mobile", "src", "screens", "LoginScreen.tsx")
        with open(login_screen) as f:
            source = f.read()
        # The old code had: await login(password || 'any');
        assert "password || 'any'" not in source, "Login still falls back to 'any'"
        assert "login(password ||" not in source, "Login still has a fallback"

    def test_login_screen_requires_non_empty_password(self):
        """The login handler must check for empty password before calling login()."""
        login_screen = os.path.join(os.path.dirname(__file__), "..", "mobile", "src", "screens", "LoginScreen.tsx")
        with open(login_screen) as f:
            source = f.read()
        # Must have some form of empty password check (trim or direct)
        assert "!password" in source or "password.trim()" in source, "Login doesn't validate empty password"
        # Must not fall back to 'any'
        assert "password || 'any'" not in source, "Login still falls back to 'any'"

    def test_login_placeholder_no_longer_says_any(self):
        """The placeholder text must not say 'any for now'."""
        login_screen = os.path.join(os.path.dirname(__file__), "..", "mobile", "src", "screens", "LoginScreen.tsx")
        with open(login_screen) as f:
            source = f.read()
        assert "any for now" not in source, "Placeholder still says 'any for now'"
        assert "access code" in source.lower() or "access token" in source.lower(), "Placeholder should say 'access code' or 'access token'"

    def test_backend_rejects_empty_password(self):
        """P22: Integration test — the backend must reject empty passwords."""
        import importlib
        os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-auth"
        os.environ.pop("MAESTRO_PERSONAL_ENV", None)
        import maestro_personal_shell.api as api_module
        importlib.reload(api_module)
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            api_module.DB_PATH = f.name
        api_module.init_db(f.name)
        client = TestClient(api_module.app)
        response = client.post("/api/auth/login", json={"password": ""})
        assert response.status_code == 401, f"Empty password should be rejected, got {response.status_code}"
        os.unlink(f.name)


# ---------------------------------------------------------------------------
# P0 #5: Audio transcription endpoint
# ---------------------------------------------------------------------------

class TestAudioTranscription:
    """P0 #5: POST /api/copilot/transcribe endpoint exists and works."""

    def test_transcription_module_exists(self):
        """P1: Execute — import the transcription module."""
        from maestro_personal_shell.audio_transcription import transcribe_audio, is_transcription_configured
        assert callable(transcribe_audio)
        assert callable(is_transcription_configured)

    def test_transcribe_returns_honest_message_when_not_configured(self):
        """P18: When no provider is configured, return an honest message — not silent failure."""
        from maestro_personal_shell.audio_transcription import transcribe_audio
        # Ensure no provider is configured
        old_env = os.environ.copy()
        for key in ("MAESTRO_WHISPER_MODEL", "MAESTRO_OPENAI_API_KEY", "MAESTRO_GOOGLE_STT_KEY"):
            os.environ.pop(key, None)
        result = transcribe_audio(b"fake audio data", "test.m4a")
        assert result["configured"] is False
        assert result["provider"] == "none"
        assert "No transcription provider configured" in result["error"]
        assert result["text"] == ""
        os.environ.clear()
        os.environ.update(old_env)

    def test_is_transcription_configured_detects_whisper(self):
        """When MAESTRO_WHISPER_MODEL is set, configured should be True."""
        from maestro_personal_shell.audio_transcription import is_transcription_configured
        old_env = os.environ.copy()
        # Clear Wit.ai to ensure whisper is detected (Wit.ai has priority)
        os.environ.pop("MAESTRO_WITAI_TOKEN", None)
        os.environ["MAESTRO_WHISPER_MODEL"] = "base"
        assert is_transcription_configured() is True
        os.environ.clear()
        os.environ.update(old_env)

    def test_is_transcription_configured_detects_witai(self):
        """When MAESTRO_WITAI_TOKEN is set, configured should be True (priority provider)."""
        from maestro_personal_shell.audio_transcription import is_transcription_configured
        old_env = os.environ.copy()
        os.environ["MAESTRO_WITAI_TOKEN"] = "test-token"
        assert is_transcription_configured() is True
        # Wit.ai should be the detected provider (highest priority)
        from maestro_personal_shell.audio_transcription import _get_transcription_provider
        assert _get_transcription_provider() == "witai"
        os.environ.clear()
        os.environ.update(old_env)

    def test_is_transcription_configured_detects_openai(self):
        """When MAESTRO_OPENAI_API_KEY is set, configured should be True."""
        from maestro_personal_shell.audio_transcription import is_transcription_configured
        old_env = os.environ.copy()
        os.environ["MAESTRO_OPENAI_API_KEY"] = "sk-test"
        assert is_transcription_configured() is True
        os.environ.clear()
        os.environ.update(old_env)

    def test_transcribe_endpoint_exists(self):
        """P22: Integration test — the endpoint is registered and responds."""
        import importlib
        os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-transcribe"
        os.environ.pop("MAESTRO_PERSONAL_ENV", None)
        import maestro_personal_shell.api as api_module
        importlib.reload(api_module)
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            api_module.DB_PATH = f.name
        api_module.init_db(f.name)
        client = TestClient(api_module.app)

        # Login first
        login_resp = client.post("/api/auth/login", json={"password": "test-transcribe"})
        token = login_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Upload a fake audio file
        response = client.post(
            "/api/copilot/transcribe",
            headers=headers,
            files={"file": ("test.m4a", b"fake audio bytes", "audio/m4a")},
        )
        assert response.status_code == 200
        data = response.json()
        assert "text" in data
        assert "provider" in data
        assert "configured" in data
        # Without a provider configured, should return configured=False
        assert data["configured"] is False
        os.unlink(f.name)

    def test_transcribe_endpoint_rejects_empty_file(self):
        """P28: Edge case — empty audio file should return 400."""
        import importlib
        os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-empty"
        os.environ.pop("MAESTRO_PERSONAL_ENV", None)
        import maestro_personal_shell.api as api_module
        importlib.reload(api_module)
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            api_module.DB_PATH = f.name
        api_module.init_db(f.name)
        client = TestClient(api_module.app)

        login_resp = client.post("/api/auth/login", json={"password": "test-empty"})
        token = login_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        response = client.post(
            "/api/copilot/transcribe",
            headers=headers,
            files={"file": ("empty.m4a", b"", "audio/m4a")},
        )
        assert response.status_code == 400
        assert "Empty" in response.json()["detail"]
        os.unlink(f.name)

    def test_transcribe_endpoint_requires_auth(self):
        """The endpoint must require authentication."""
        import importlib
        os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-auth-required"
        os.environ.pop("MAESTRO_PERSONAL_ENV", None)
        import maestro_personal_shell.api as api_module
        importlib.reload(api_module)
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            api_module.DB_PATH = f.name
        api_module.init_db(f.name)
        client = TestClient(api_module.app)

        response = client.post(
            "/api/copilot/transcribe",
            files={"file": ("test.m4a", b"fake", "audio/m4a")},
        )
        assert response.status_code in (401, 403)
        os.unlink(f.name)

    def test_mobile_stop_recording_uploads_to_transcribe_endpoint(self):
        """P11: Verify the mobile app calls /api/copilot/transcribe (not just sends placeholder text)."""
        # Phase 2: Copilot code moved from App.tsx to CopilotScreen.tsx
        copilot_screen = os.path.join(os.path.dirname(__file__), "..", "mobile", "src", "screens", "CopilotScreen.tsx")
        app_tsx = os.path.join(os.path.dirname(__file__), "..", "mobile", "App.tsx")
        source = ""
        for f_path in [copilot_screen, app_tsx]:
            try:
                with open(f_path) as f:
                    source += f.read()
            except FileNotFoundError:
                pass
        assert "/api/copilot/transcribe" in source, "Mobile app doesn't call the transcribe endpoint"
        assert "FormData" in source, "Mobile app doesn't use FormData for audio upload"
        assert "[Transcribing…]" in source, "Mobile app doesn't show transcribing state"
        assert "no transcription provider configured" in source, "Mobile app doesn't handle the not-configured case"
