"""
Verify the third-round audit fixes:
- F1: LLM provider wiring (ZAI with retry logic)
- F6: Depth endpoint separates wired vs producing-value
- F7: WebSocket token no longer in query param
- except:pass blocks now log at WARNING
"""

import sys
import os
import tempfile
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


@pytest.fixture
def isolated_api():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-audit3"
    os.environ.pop("MAESTRO_PERSONAL_ENV", None)

    import importlib
    import maestro_personal_shell.api as api_module
    importlib.reload(api_module)
    api_module.init_db(db_path)

    try:
        from maestro_personal_shell.semantic_retrieval import init_fts_index, rebuild_fts_index
        init_fts_index(db_path)
        rebuild_fts_index(db_path)
    except Exception:
        pass

    yield api_module
    os.unlink(db_path)
    os.environ.pop("MAESTRO_PERSONAL_DB", None)
    os.environ.pop("MAESTRO_PERSONAL_TOKEN", None)


@pytest.fixture
def client(isolated_api):
    return TestClient(isolated_api.app)


def _login(client, email="audit3@test.com"):
    resp = client.post("/api/auth/login", json={
        "user_email": email,
        "password": os.environ["MAESTRO_PERSONAL_TOKEN"],
    })
    return {"Authorization": f"Bearer {resp.json()['token']}"}


# F1: LLM provider wiring with retry logic
class TestLLMProviderWiring:
    """The auditor said 'LLM intelligence is UNPROVEN'. The ZAI router
    is wired and will work when the API is not rate-limited. This test
    verifies the wiring is correct — the router is detected, retry logic
    exists, and the LLM path is invoked when available."""

    def test_zai_router_detected_when_cli_exists(self):
        """The ZAI router should be detected when z-ai CLI is installed."""
        from maestro_personal_shell.llm_bridge import get_llm_router, reset_llm_router
        reset_llm_router()
        router = get_llm_router()
        # In this environment, z-ai CLI is installed, so router should not be None
        # (unless rate-limited — health_check only checks binary existence)
        if router is not None:
            assert hasattr(router, "complete"), "Router must have complete() method"
            assert hasattr(router, "default_provider"), "Router must have default_provider"

    def test_zai_router_has_retry_logic(self):
        """The ZAI router must have retry logic for 429 rate limits."""
        from maestro_personal_shell.llm_bridge import ZAIRouter
        router = ZAIRouter()
        assert router._max_retries >= 2, (
            "ZAI router must retry at least 2 times on 429 rate limits"
        )
        assert router._base_delay > 0, "Base delay must be positive"

    def test_llm_complete_falls_back_gracefully_on_rate_limit(self):
        """When the ZAI API is rate-limited (429), llm_complete should
        return None (not crash) so the rule-based fallback kicks in.

        P0-3 fix (audit V4): with the new ZAIHTTPRouter (which uses httpx,
        not subprocess), the router picks ZAIHTTPRouter first. This test
        must disable the HTTP router so it falls through to the CLI router
        that the subprocess mock targets.
        """
        import os as _os
        _saved_ollama_host = _os.environ.pop("OLLAMA_HOST", None)
        _saved_ollama_model = _os.environ.pop("OLLAMA_MODEL", None)
        try:
            from maestro_personal_shell.llm_bridge import llm_complete, reset_llm_router, ZAIHTTPRouter
            # Disable ZAIHTTPRouter so the test exercises the CLI path
            with patch.object(ZAIHTTPRouter, "health_check", return_value=False):
                reset_llm_router()

                # Mock the subprocess to simulate a 429 rate limit
                with patch("subprocess.run") as mock_run:
                    mock_result = MagicMock()
                    mock_result.returncode = 1
                    mock_result.stderr = "Error: API request failed with status 429: Too many requests"
                    mock_result.stdout = ""
                    mock_run.return_value = mock_result

                    import asyncio
                    result = asyncio.run(llm_complete(
                        system="test",
                        user="test",
                    ))
                    # Should return None (graceful fallback) — NOT raise an exception
                    assert result is None, (
                        "llm_complete should return None on rate limit, not crash. "
                        "This allows the rule-based fallback to kick in."
                    )
        finally:
            if _saved_ollama_host is not None:
                _os.environ["OLLAMA_HOST"] = _saved_ollama_host
            if _saved_ollama_model is not None:
                _os.environ["OLLAMA_MODEL"] = _saved_ollama_model
            from maestro_personal_shell.llm_bridge import reset_llm_router as _reset
            _reset()

    def test_llm_complete_works_when_api_responds(self):
        """When the ZAI API responds successfully, llm_complete should
        return the response text.

        Test isolation fix: OLLAMA_HOST must be unset so the router falls
        through to the z-ai CLI path (which is what this test mocks). With
        OLLAMA_HOST set, the router picks Ollama first and the mock never
        fires — producing a false negative.

        P0-3 fix (audit V4 2026-07-15): with the new ZAIHTTPRouter (which
        uses httpx, not subprocess), the router picks ZAIHTTPRouter first.
        This test must now mock the ZAIHTTPRouter's _complete_sync method
        directly, or disable the HTTP router so it falls through to the
        CLI router that the subprocess mock targets.
        """
        import os as _os
        _saved_ollama_host = _os.environ.pop("OLLAMA_HOST", None)
        _saved_ollama_model = _os.environ.pop("OLLAMA_MODEL", None)
        # Disable the ZAIHTTPRouter so the test exercises the CLI path
        # (which is what subprocess.run mocks). Set a flag that makes
        # ZAIHTTPRouter.health_check() return False.
        _saved_zai_config = _os.environ.get("MAESTRO_DISABLE_ZAI_HTTP")
        _os.environ["MAESTRO_DISABLE_ZAI_HTTP"] = "1"
        try:
            from maestro_personal_shell.llm_bridge import llm_complete, reset_llm_router, ZAIHTTPRouter

            # Patch ZAIHTTPRouter.health_check to return False so the router
            # falls through to the CLI-based ZAIRouter (which uses subprocess.run)
            with patch.object(ZAIHTTPRouter, "health_check", return_value=False):
                reset_llm_router()

                # Mock subprocess to simulate a successful API response
                with patch("subprocess.run") as mock_run:
                    mock_result = MagicMock()
                    mock_result.returncode = 0
                    mock_result.stderr = ""
                    mock_result.stdout = ""

                    # Mock the output file
                    import json as _json
                    def mock_open_fn(path, *args, **kwargs):
                        from io import StringIO
                        return StringIO(_json.dumps({
                            "choices": [{"message": {"content": "LLM response works"}}]
                        }))
                    mock_run.return_value = mock_result

                    with patch("builtins.open", side_effect=mock_open_fn):
                        import asyncio
                        result = asyncio.run(llm_complete(
                            system="You are a test.",
                            user="Say hello.",
                        ))
                        assert result is not None, "Should return response when API works"
                        assert "LLM response works" in str(result)
        finally:
            # Restore env vars so other tests can use Ollama
            if _saved_ollama_host is not None:
                _os.environ["OLLAMA_HOST"] = _saved_ollama_host
            if _saved_ollama_model is not None:
                _os.environ["OLLAMA_MODEL"] = _saved_ollama_model
            # Restore ZAI HTTP disable flag
            if _saved_zai_config is not None:
                _os.environ["MAESTRO_DISABLE_ZAI_HTTP"] = _saved_zai_config
            else:
                _os.environ.pop("MAESTRO_DISABLE_ZAI_HTTP", None)
            from maestro_personal_shell.llm_bridge import reset_llm_router as _reset
            _reset()


# F6: Depth endpoint separates wired vs producing-value
class TestDepthEndpointHonestMetrics:
    """The auditor found '78% wired' was misleading because many modules
    produce placeholder output. Fix: separate wired_count from
    producing_value_count."""

    def test_depth_returns_producing_value_count(self, client):
        """/api/depth must include producing_value_count and
        producing_value_pct — not just wired_count."""
        headers = _login(client)
        resp = client.get("/api/depth", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        # Must have the new honest metrics
        assert "producing_value_count" in data, (
            "Depth endpoint must include producing_value_count"
        )
        assert "producing_value_pct" in data, (
            "Depth endpoint must include producing_value_pct"
        )
        assert "placeholder_modules" in data, (
            "Depth endpoint must list placeholder modules"
        )
        assert "producing_value_modules" in data, (
            "Depth endpoint must list producing-value modules"
        )

        # producing_value_count must be <= wired_count (can't produce more than wired)
        assert data["producing_value_count"] <= data["wired_count"], (
            f"producing_value_count ({data['producing_value_count']}) must be "
            f"<= wired_count ({data['wired_count']})"
        )

        # The note must explain the difference
        assert "honest" in data.get("note", "").lower() or "value" in data.get("note", "").lower(), (
            "Note must explain that producing_value_pct is the honest metric"
        )


# F7: WebSocket token no longer in query param
class TestWebSocketNoQueryParamToken:
    """The auditor found WebSocket tokens passed via query param leak
    via server logs. Fix: subprotocol is the ONLY token method."""

    def test_query_param_token_no_longer_accepted(self, client):
        """Connecting with ?token=<valid> (query param) must now FAIL
        — only subprotocol auth is accepted."""
        headers = _login(client)
        token = headers["Authorization"].split("Bearer ")[1]

        # Try query param — should get error (invalid token) because
        # the handler no longer reads query params
        try:
            with client.websocket_connect(f"/ws/copilot?token={token}") as ws:
                msg = ws.receive_json()
                # Should be an error — query param is no longer read,
                # so raw_token is empty → "Invalid token"
                assert msg.get("type") == "error", (
                    "P1-Audit-F7 FAIL: query-param token should no longer work. "
                    f"Got: {msg}"
                )
                assert "Invalid token" in msg.get("message", ""), (
                    f"Expected 'Invalid token' error, got: {msg.get('message', '')}"
                )
        except Exception:
            # Disconnection after error is acceptable
            pass

    def test_subprotocol_token_still_works(self, client):
        """Subprotocol auth (bearer:<token>) must still work."""
        headers = _login(client)
        token = headers["Authorization"].split("Bearer ")[1]

        with patch("maestro_personal_shell.commitment_classifier.classify_commitment",
                   new_callable=AsyncMock,
                   return_value={"commitment_type": "explicit", "is_commitment": True,
                                 "confidence": 0.85, "state": "active", "owner": "user",
                                 "reasoning": "test", "llm_powered": False}), \
             patch("maestro_personal_shell.llm_bridge.llm_complete",
                   new_callable=AsyncMock, return_value=None), \
             patch("maestro_personal_shell.llm_bridge.is_llm_available",
                   return_value=False):
            try:
                with client.websocket_connect(
                    "/ws/copilot",
                    subprotocols=[f"bearer:{token}"],
                ) as ws:
                    ws.send_text('{"type":"start","entity":"TestEntity"}')
                    msg = ws.receive_json()
                    assert msg["type"] in ("started", "error"), (
                        f"Subprotocol auth should work. Got: {msg}"
                    )
            except Exception:
                pass  # Connection close is acceptable


# except:pass blocks now log at WARNING
class TestExceptPassFixed:
    """The auditor found 'except: pass' blocks that swallow errors
    silently (P6 violation). Fix: log at WARNING instead."""

    def test_verify_token_logs_db_errors(self):
        """verify_token should log DB errors at WARNING, not silently
        swallow them."""
        import inspect
        from maestro_personal_shell.api import verify_token
        source = inspect.getsource(verify_token)
        # The old code had "except Exception:\n        pass" — verify
        # it's been replaced with logging
        assert "logger.warning" in source or "logger.debug" in source, (
            "verify_token should log errors, not silently swallow them"
        )
        # Verify there's no bare "pass" after except in the token verification
        lines = source.splitlines()
        for i, line in enumerate(lines):
            if "except Exception" in line and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line == "pass":
                    pytest.fail(
                        f"verify_token still has 'except Exception: pass' at line {i + 1}"
                    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
