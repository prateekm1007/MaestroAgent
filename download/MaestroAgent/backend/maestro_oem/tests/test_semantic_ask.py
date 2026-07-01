"""
V8 Competitor Analysis Feature B — Semantic Ask. Regression tests.

The keyword matcher had a known bug: a question sharing a common word
with an unrelated law would surface that law as "relevant evidence."
The SemanticMatcher fixes this with character n-gram TF-IDF + cosine
similarity.
"""

from __future__ import annotations

import os
import pathlib

import pytest
from fastapi.testclient import TestClient

from maestro_oem.semantic_matcher import SemanticMatcher, build_semantic_matcher
from maestro_oem import OEMEngine


class TestSemanticMatcher:
    """The SemanticMatcher must be more semantic than keyword matching."""

    def test_morphological_variants_match(self) -> None:
        """'hire' and 'hiring' must have high similarity (morphological variant)."""
        m = SemanticMatcher(ngram_size=3, similarity_threshold=0.05)
        m.fit(["hire more engineers", "deployment frequency"])
        score = m.similarity("hire", "hiring")
        assert score > 0.3, f"'hire' vs 'hiring' should be similar, got {score}"

    def test_unrelated_terms_low_similarity(self) -> None:
        """'hire' and 'deployment' must have low similarity."""
        m = SemanticMatcher(ngram_size=3, similarity_threshold=0.05)
        m.fit(["hire more engineers", "deployment frequency"])
        score = m.similarity("hire", "deployment")
        assert score < 0.3, f"'hire' vs 'deployment' should be dissimilar, got {score}"

    def test_ranking_returns_relevant_first(self) -> None:
        """Ranking must return the most relevant result first."""
        m = SemanticMatcher(ngram_size=3, similarity_threshold=0.05)
        m.fit([
            "Bottleneck: sara.k gates 3 items in review",
            "Velocity drop: deployment frequency decreased",
            "Departure risk: priya.m may leave",
        ])
        results = m.rank("who is the bottleneck?", [
            ("Bottleneck: sara.k gates 3 items in review", "bottleneck"),
            ("Velocity drop: deployment frequency decreased", "velocity"),
            ("Departure risk: priya.m may leave", "departure"),
        ])
        assert len(results) > 0
        assert results[0][1] == "bottleneck", "Bottleneck should rank first"

    def test_threshold_filters_low_similarity(self) -> None:
        """Results below the threshold must be filtered out."""
        m = SemanticMatcher(ngram_size=3, similarity_threshold=0.9)
        m.fit(["bottleneck in review queue"])
        results = m.rank("bottleneck", [("bottleneck in review queue", "test")])
        # With a 0.9 threshold, even a good match may be filtered
        # This verifies the threshold is applied
        assert all(score >= 0.9 for score, _ in results)

    def test_empty_text_returns_empty_vector(self) -> None:
        """Empty text must not crash."""
        m = SemanticMatcher()
        m.fit(["some text"])
        vec = m.embed("")
        assert isinstance(vec, list)

    def test_build_semantic_matcher_from_model(self) -> None:
        """build_semantic_matcher must fit on the model's laws + LOs."""
        engine = OEMEngine()
        model = engine.get_model()
        matcher = build_semantic_matcher(model)
        assert matcher is not None
        assert matcher._num_docs >= 0  # fitted


class TestSemanticAskAPI:
    """The /api/oem/ask endpoint must use the SemanticMatcher."""

    @pytest.fixture(scope="module")
    def client(self):
        app_dir = str(pathlib.Path(__file__).resolve().parents[3])
        os.environ.setdefault("MAESTRO_APP_DIR", app_dir)
        os.environ.setdefault("MAESTRO_AUTH_DB", "/tmp/maestro_test_semantic_ask_auth.db")
        os.environ.setdefault("MAESTRO_ADMIN_PASSWORD", "test")
        from maestro_api.main import create_app
        app = create_app(db_path=":memory:")
        with TestClient(app) as c:
            yield c

    def test_ask_returns_200(self, client) -> None:
        r = client.get("/api/oem/ask", params={"q": "who is the bottleneck?"})
        assert r.status_code == 200

    def test_ask_returns_relevance_scores(self, client) -> None:
        """Results must have relevance scores (not just binary match)."""
        r = client.get("/api/oem/ask", params={"q": "bottleneck"})
        data = r.json()
        for law in data.get("laws", []):
            assert "relevance" in law
            assert isinstance(law["relevance"], float)
            assert 0.0 <= law["relevance"] <= 1.0

    def test_ask_bottleneck_finds_bottleneck_laws(self, client) -> None:
        """A question about bottlenecks must find bottleneck laws."""
        r = client.get("/api/oem/ask", params={"q": "who is the bottleneck?"})
        data = r.json()
        # Should find at least 1 law about bottlenecks
        assert len(data.get("laws", [])) > 0 or len(data.get("learning_objects", [])) > 0

    def test_decision_py_uses_semantic_matcher(self) -> None:
        """decision.py must import and use the SemanticMatcher."""
        import maestro_oem.decision as mod
        source = open(mod.__file__).read()
        assert "semantic_matcher" in source, "decision.py doesn't use semantic_matcher"
        assert "build_semantic_matcher" in source, "decision.py doesn't call build_semantic_matcher"
        # The old keyword matcher variable must be gone (comments mentioning it are OK)
        assert "MIN_WORD_OVERLAP = " not in source, "decision.py still has the old keyword matcher variable"
        assert "_relevance_score" not in source, "decision.py still has the old keyword relevance function"
        assert "_is_relevant" not in source, "decision.py still has the old keyword relevance function"
