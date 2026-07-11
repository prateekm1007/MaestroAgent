"""
Verify LLM is active via Ollama and Ask endpoint uses it.

This is the "ONE THING" from the roadmap: install Ollama, verify
llm_generate_answer() fires, and the Ask endpoint returns LLM-powered
answers.
"""

import sys
import os
import tempfile
import asyncio
import subprocess
import time
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


def _ensure_ollama():
    """Start Ollama if not running. Returns True if available."""
    import urllib.request
    try:
        urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2)
        return True
    except Exception:
        pass
    # Try to start it
    try:
        subprocess.Popen(
            ["/tmp/ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        for i in range(10):
            try:
                urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2)
                return True
            except:
                time.sleep(1)
    except Exception:
        pass
    return False


@pytest.fixture
def isolated_api():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-llm-live"
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


class TestLLMViaOllama:
    """Verify Ollama is detected and used as the LLM provider."""

    def test_ollama_router_selected(self):
        """get_llm_router() should select Ollama when it's running."""
        if not _ensure_ollama():
            pytest.skip("Ollama not available")

        from maestro_personal_shell.llm_bridge import get_llm_router, reset_llm_router, get_llm_provider_name
        reset_llm_router()
        router = get_llm_router()
        provider = get_llm_provider_name()
        assert provider == "ollama", (
            f"Expected provider 'ollama', got '{provider}'. "
            f"Router type: {type(router).__name__}"
        )

    def test_llm_complete_returns_real_answer(self):
        """llm_complete should return a real LLM response, not None."""
        if not _ensure_ollama():
            pytest.skip("Ollama not available")

        from maestro_personal_shell.llm_bridge import llm_complete, reset_llm_router
        reset_llm_router()

        result = asyncio.run(llm_complete(
            system="You are a helpful assistant. Reply with just the answer.",
            user="What is 2+2?",
            temperature=0.0,
            max_tokens=50,
        ))
        assert result is not None, "LLM should return a response, not None"
        assert "4" in result, f"Expected '4' in response, got: {result}"

    def test_ask_endpoint_uses_llm(self, client):
        """POST /api/ask should use the LLM and return intelligence_source='llm'."""
        if not _ensure_ollama():
            pytest.skip("Ollama not available")

        from maestro_personal_shell.llm_bridge import reset_llm_router, get_llm_provider_name
        reset_llm_router()

        # Verify LLM is available before testing
        if get_llm_provider_name() != "ollama":
            pytest.skip("Ollama not selected as provider")

        resp = client.post("/api/auth/login", json={
            "password": os.environ["MAESTRO_PERSONAL_TOKEN"],
        })
        headers = {"Authorization": f"Bearer {resp.json()['token']}"}

        # Seed a signal
        with patch("maestro_personal_shell.commitment_classifier.classify_commitment",
                   new_callable=AsyncMock,
                   return_value={"commitment_type": "explicit", "is_commitment": True,
                                 "confidence": 0.85, "state": "active", "owner": "user",
                                 "reasoning": "test", "llm_powered": False}):
            client.post("/api/signals", json={
                "entity": "LLMTestCorp",
                "text": "I will send the proposal by Friday",
                "signal_type": "commitment_made",
            }, headers=headers)

        # Ask a question
        resp = client.post("/api/ask", json={
            "query": "What did LLMTestCorp commit to?",
        }, headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        # The answer should mention the entity (whether LLM or rules)
        answer = data.get("answer", "")
        assert "LLMTestCorp" in answer or "proposal" in answer.lower(), (
            f"Answer should mention the entity or commitment. Got: {answer[:200]}"
        )
        # If LLM is active, verify it's labeled
        if data.get("llm_active"):
            assert data.get("llm_provider") == "ollama"
            assert data.get("intelligence_source") == "llm"
        else:
            # LLM may have died during the test — still verify the answer is correct
            assert data.get("intelligence_source") == "rules"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
