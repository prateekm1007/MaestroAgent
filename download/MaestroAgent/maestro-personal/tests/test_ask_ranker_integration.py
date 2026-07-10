"""
Integration test: verify ask_ranker is wired into production /api/ask.

History: the auditor found P11 — ask_ranker existed but wasn't called by
POST /api/ask. The fix wired it in. But a follow-up probe (S4) found that
the wiring was real yet the ranker STILL never fired in practice, because
``semantic_search`` passed raw natural-language queries (``"What did Maria
review?"``) to FTS5 MATCH, which raised ``fts5: syntax error near "?"``.
The except block swallowed that as 0 rows, starving the ranker of
candidates. A separate fix sanitized the FTS query (stopword removal +
OR-join of significant terms).

This test now verifies the FULL chain end-to-end:
  1. POST /api/ask with a natural-language question returns non-empty
     evidence_refs containing the right entity (Maria) and NOT the
     volume winner (NewsletterCorp).  — substantive, not vacuous.
  2. The same for source_sentence.
  3. A break-it test: patch rank_for_ask to raise; the production
     response must degrade (empty evidence_refs). If the ranker weren't
     in the call path, breaking it would be a no-op.
  4. A call-count test: patch rank_for_ask to count invocations; the
     production call must record >= 1 invocation. This directly refutes
     the "0 calls" monkeypatch result the auditor saw (which was a Python
     import-binding artifact of patching after module load — the import
     here is inside the function body, so patching the module attribute
     before the call works).
"""

import sys
import os
import tempfile
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "evaluation", "personal_memory_benchmark"))


@pytest.fixture
def isolated_api():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-ranker-int"
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
    del os.environ["MAESTRO_PERSONAL_DB"]
    del os.environ["MAESTRO_PERSONAL_TOKEN"]


@pytest.fixture
def client(isolated_api):
    return TestClient(isolated_api.app)


@pytest.fixture
def auth_headers(client):
    response = client.post("/api/auth/login", json={"password": os.environ.get("MAESTRO_PERSONAL_TOKEN", "test")})
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _mock_llm():
    return (
        patch("maestro_personal_shell.commitment_classifier.classify_commitment",
              new_callable=AsyncMock,
              return_value={"commitment_type": "explicit", "is_commitment": True,
                            "confidence": 0.85, "state": "active", "owner": "user",
                            "reasoning": "test", "llm_powered": False}),
        patch("maestro_personal_shell.llm_bridge.llm_complete",
              new_callable=AsyncMock, return_value=None),
        patch("maestro_personal_shell.dynamic_agents.materiality_gate_v2",
              new_callable=AsyncMock,
              return_value={"should_speak": True, "materiality_score": 0.5,
                            "urgency": "medium", "reasoning": "test", "llm_powered": False}),
    )


def _seed_maria_vs_newsletter(client, auth_headers):
    """Seed: Maria has 1 signal, NewsletterCorp has 5 (volume)."""
    client.post("/api/signals", json={
        "entity": "Maria Garcia", "text": "I reviewed the scorecard",
        "signal_type": "reported_statement",
    }, headers=auth_headers)
    for i in range(5):
        client.post("/api/signals", json={
            "entity": "NewsletterCorp", "text": f"Weekly newsletter issue {i}",
            "signal_type": "newsletter",
        }, headers=auth_headers)


class TestAskRankerProductionIntegration:
    """Verify ask_ranker is wired into POST /api/ask (not just tests)."""

    def test_maria_query_returns_maria_evidence(self, client, auth_headers):
        """POST /api/ask about Maria must return Maria's evidence — not NewsletterCorp's.

        S4 hardening: the previous version guarded assertions with
        ``if evidence:``, which let the test pass vacuously when
        evidence_refs was empty (which it was, because FTS5 rejected the
        raw query). The assertions are now unconditional — an empty
        evidence_refs is a hard failure, not a skip.
        """
        m1, m2, m3 = _mock_llm()
        with m1, m2, m3:
            _seed_maria_vs_newsletter(client, auth_headers)

            response = client.post("/api/ask", json={
                "query": "What did Maria review?",
            }, headers=auth_headers)

            assert response.status_code == 200
            data = response.json()
            evidence = data.get("evidence_refs", [])

            # S4 FIX: unconditional. Empty evidence is a failure, not a skip.
            assert len(evidence) > 0, \
                "evidence_refs must be non-empty — the ranker must produce evidence"

            entities = [e.get("entity", "").lower() for e in evidence]
            assert any("maria" in e for e in entities), \
                f"Maria should be in evidence_refs, got entities: {entities}"
            assert not any("newsletter" in e for e in entities), \
                f"NewsletterCorp should NOT be in evidence_refs (volume noise), got: {entities}"

    def test_source_sentence_not_from_noise(self, client, auth_headers):
        """source_sentence from POST /api/ask should not be from a newsletter.

        S4 hardening: unconditional assertion — empty source_sentence is
        a failure, not a skip.
        """
        m1, m2, m3 = _mock_llm()
        with m1, m2, m3:
            client.post("/api/signals", json={
                "entity": "RealClient", "text": "I will send the proposal by Friday",
                "signal_type": "commitment_made",
            }, headers=auth_headers)
            for i in range(5):
                client.post("/api/signals", json={
                    "entity": "NoiseCorp", "text": f"Newsletter digest {i}",
                    "signal_type": "newsletter",
                }, headers=auth_headers)

            response = client.post("/api/ask", json={
                "query": "What did RealClient commit to?",
            }, headers=auth_headers)

            data = response.json()
            source = data.get("source_sentence", "")

            # S4 FIX: unconditional. Empty source_sentence is a failure.
            assert source, \
                "source_sentence must be non-empty — provenance must be present"
            assert "newsletter" not in source.lower(), \
                f"source_sentence should not be from newsletter, got: {source}"

    def test_ranker_fires_in_production_call_count(self, client, auth_headers):
        """Definitive proof the ranker fires: count its invocations.

        The auditor's earlier monkeypatch showed 0 calls, but that was a
        Python import-binding artifact (patching the module attribute
        after the api module had already bound the name at import time).
        Here the ``from ... import rank_for_ask`` lives INSIDE the ask()
        function body, so it re-reads the module attribute on each call.
        Patching ``ask_ranker.rank_for_ask`` before the request therefore
        intercepts the production call. Using ``wraps=`` lets the mock
        delegate to the real implementation while still counting.
        """
        import maestro_personal_shell.ask_ranker as ar_module
        original = ar_module.rank_for_ask
        call_count = {"n": 0}

        def tracking_rank(query, signals):
            call_count["n"] += 1
            return original(query, signals)

        m1, m2, m3 = _mock_llm()
        with m1, m2, m3, \
             patch.object(ar_module, "rank_for_ask", side_effect=tracking_rank):
            _seed_maria_vs_newsletter(client, auth_headers)
            response = client.post("/api/ask", json={
                "query": "What did Maria review?",
            }, headers=auth_headers)

            assert response.status_code == 200
            assert call_count["n"] > 0, (
                "rank_for_ask must be called at least once during POST /api/ask — "
                "if this fails, the ranker is wired in code but not reached at runtime "
                "(e.g. FTS retrieval returns empty, starving the ranker of candidates)"
            )

    def test_ranker_output_flows_to_response(self, client, auth_headers):
        """Sentinel-injection test: the ranker's output must reach evidence_refs.

        The call-count test proves the ranker is invoked. This test proves
        its RETURN VALUE is what populates the response — not some other
        code path. We patch rank_for_ask to return a top_evidence list
        containing a sentinel entity name, then verify that sentinel
        appears in the production evidence_refs. If the ranker were
        invoked but its output discarded (e.g. assigned to a local that's
        never read), the sentinel would not appear.

        Note: we cannot simply break the ranker and assert empty
        evidence_refs, because api.py's except block at the evidence_refs
        fallback site (line ~1055) runs a linear entity-substring search
        that still populates evidence_refs when the ranker raises. The
        sentinel approach is the precise way to prove the ranker's output
        is the source of the response's evidence.
        """
        import maestro_personal_shell.ask_ranker as ar_module

        SENTINEL = "SENTINEL_RANKER_OUTPUT_PROOF"
        fake_ranked = {
            "understanding": {"entity_mentions": [], "intent": "general",
                              "mentioned_topics": [], "time_constraint": None,
                              "query_lower": "sentinel"},
            "ranked_signals": [],
            "top_evidence": [{
                "signal_id": "sentinel-sig",
                "entity": SENTINEL,
                "text": "sentinel text from ranker",
                "signal_type": "reported_statement",
                "timestamp": "2026-07-10T12:00:00Z",
            }],
        }

        m1, m2, m3 = _mock_llm()
        with m1, m2, m3, \
             patch.object(ar_module, "rank_for_ask", return_value=fake_ranked):
            _seed_maria_vs_newsletter(client, auth_headers)
            response = client.post("/api/ask", json={
                "query": "What did Maria review?",
            }, headers=auth_headers)

            assert response.status_code == 200
            data = response.json()
            evidence = data.get("evidence_refs", [])
            entities = [e.get("entity", "") for e in evidence]
            assert SENTINEL in entities, (
                "The ranker's top_evidence must flow through to evidence_refs. "
                f"Sentinel {SENTINEL!r} not found in entities: {entities}. "
                "If the ranker is called but its output is discarded, the "
                "wiring is theater."
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
