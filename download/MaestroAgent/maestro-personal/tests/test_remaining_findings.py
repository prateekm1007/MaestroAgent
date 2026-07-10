"""
Tests for F3 (entity resolution), F5 (real confidence), F4 (agent pruning).
"""

import sys
import os
import tempfile
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


@pytest.fixture
def isolated_api():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-rem"
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
    response = client.post("/api/auth/login", json={"password": "any"})
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# F3: Entity Resolution
# ===========================================================================


class TestEntityResolution:
    """F3: entity fragmentation fix."""

    def test_normalize_strips_corporate_suffixes(self):
        """Corporate suffixes like 'Corp', 'Inc', 'LLC' must be normalized."""
        from maestro_personal_shell.entity_resolver import _normalize
        assert _normalize("Acme Corp") == _normalize("Acme")
        assert _normalize("Acme Corporation") == _normalize("Acme")
        assert _normalize("Acme, Inc.") == _normalize("Acme")
        assert _normalize("ACME") == _normalize("acme")

    def test_fuzzy_match_catches_near_misses(self):
        """Fuzzy matching must catch 'AcmeCorp' vs 'Acme Corp'."""
        from maestro_personal_shell.entity_resolver import _fuzzy_match
        assert _fuzzy_match("AcmeCorp", "Acme Corp")
        assert _fuzzy_match("acme", "Acme Corporation")
        assert not _fuzzy_match("Acme", "Completely Different Corp")

    def test_resolve_entity_against_known(self):
        """resolve_entity must match against known entities."""
        from maestro_personal_shell.entity_resolver import resolve_entity
        known = ["Acme Corp", "Globex"]
        # "acme corp" (lowercase) should resolve to "Acme Corp"
        assert resolve_entity("acme corp", known_entities=known) == "Acme Corp"
        # "AcmeCorp" (no space) should fuzzy-match to "Acme Corp"
        assert resolve_entity("AcmeCorp", known_entities=known) == "Acme Corp"

    def test_entity_resolution_on_signal_ingest(self, client, auth_headers):
        """F3: when a signal is created, the entity must be resolved."""
        # Create a signal with "Acme Corp"
        with patch(
            "maestro_personal_shell.commitment_classifier.classify_commitment",
            new_callable=AsyncMock,
            return_value={"commitment_type": "explicit", "is_commitment": True, "confidence": 0.9, "state": "active", "owner": "user", "reasoning": "test", "llm_powered": False},
        ):
            client.post(
                "/api/signals",
                json={"entity": "Acme Corp", "text": "I will send the proposal", "signal_type": "commitment_made"},
                headers=auth_headers,
            )

            # Now create a signal with "AcmeCorp" — should resolve to "Acme Corp"
            response = client.post(
                "/api/signals",
                json={"entity": "AcmeCorp", "text": "Follow up on proposal", "signal_type": "follow_up"},
                headers=auth_headers,
            )
            assert response.status_code == 200
            assert response.json()["entity"] == "Acme Corp", \
                "F3: 'AcmeCorp' should resolve to 'Acme Corp'"

    def test_manual_alias_mapping(self, client, auth_headers):
        """F3: user can manually map 'client' → 'Acme Corp'."""
        from maestro_personal_shell.entity_resolver import add_alias, resolve_entity

        # Add manual alias
        add_alias("client", "Acme Corp", user_email="bootstrap")

        # Resolve "client" → should return "Acme Corp"
        result = resolve_entity("client", user_email="bootstrap")
        assert result == "Acme Corp"


# ===========================================================================
# F5: Real Confidence Calculation
# ===========================================================================


class TestRealConfidence:
    """F5: flat 0.5/0.0 confidence replaced with real calculation."""

    def test_explicit_commitment_higher_confidence(self):
        """Explicit commitments should have higher confidence than conditional."""
        from maestro_personal_shell.api import _compute_commitment_confidence

        explicit_conf = _compute_commitment_confidence(
            {"metadata": {"commitment_type": "explicit", "commitment_confidence": 0.9}},
            "Insufficient calibration history",
            days_stale=0,
        )
        conditional_conf = _compute_commitment_confidence(
            {"metadata": {"commitment_type": "conditional", "commitment_confidence": 0.9}},
            "Insufficient calibration history",
            days_stale=0,
        )
        assert explicit_conf > conditional_conf, \
            "F5: explicit commitment should have higher confidence than conditional"

    def test_stale_commitment_lower_confidence(self):
        """Stale commitments should have lower confidence."""
        from maestro_personal_shell.api import _compute_commitment_confidence

        fresh_conf = _compute_commitment_confidence(
            {"metadata": {"commitment_type": "explicit", "commitment_confidence": 0.9}},
            "Insufficient calibration history",
            days_stale=0,
        )
        stale_conf = _compute_commitment_confidence(
            {"metadata": {"commitment_type": "explicit", "commitment_confidence": 0.9}},
            "Insufficient calibration history",
            days_stale=10,
        )
        assert stale_conf < fresh_conf, \
            "F5: stale commitment should have lower confidence"

    def test_brier_score_adjusts_confidence(self):
        """A poor Brier score should reduce confidence."""
        from maestro_personal_shell.api import _compute_commitment_confidence

        good_brier_conf = _compute_commitment_confidence(
            {"metadata": {"commitment_type": "explicit", "commitment_confidence": 0.8}},
            "Brier score: 0.1500",
            days_stale=0,
        )
        poor_brier_conf = _compute_commitment_confidence(
            {"metadata": {"commitment_type": "explicit", "commitment_confidence": 0.8}},
            "Brier score: 0.4000",
            days_stale=0,
        )
        assert poor_brier_conf < good_brier_conf, \
            "F5: poor Brier score should reduce confidence"

    def test_confidence_in_range(self):
        """Confidence must always be 0.0-1.0."""
        from maestro_personal_shell.api import _compute_commitment_confidence

        for days in [0, 1, 5, 10, 30]:
            for ctype in ["explicit", "implicit", "conditional", "unclassified"]:
                for brier in [None, 0.1, 0.25, 0.4]:
                    cal = f"Brier score: {brier}" if brier else "Insufficient"
                    conf = _compute_commitment_confidence(
                        {"metadata": {"commitment_type": ctype, "commitment_confidence": 0.9}},
                        cal,
                        days_stale=days,
                    )
                    assert 0.0 <= conf <= 1.0, \
                        f"Confidence {conf} out of range for ctype={ctype}, days={days}, brier={brier}"


# ===========================================================================
# F4: Nerve Agent Pruning
# ===========================================================================


class TestAgentPruning:
    """F4: personal agents pruned from 14 to 8 (removed enterprise org functions)."""

    def test_personal_agents_count_is_8(self):
        """F4: PERSONAL_AGENTS must have exactly 8 agents (was 14)."""
        from maestro_personal_shell.nerve_wiring import NerveWiring
        assert len(NerveWiring.PERSONAL_AGENTS) == 8, \
            f"F4: expected 8 personal agents, got {len(NerveWiring.PERSONAL_AGENTS)}"

    def test_enterprise_agents_removed(self):
        """F4: HR, Legal, Operations, Data, Growth, Marketing must be removed."""
        from maestro_personal_shell.nerve_wiring import NerveWiring
        removed = ["hr", "legal", "operations", "data", "growth", "marketing"]
        for agent in removed:
            assert agent not in NerveWiring.PERSONAL_AGENTS, \
                f"F4: '{agent}' should be removed from personal agents (enterprise-only)"

    def test_personal_agents_kept(self):
        """F4: chief_of_staff, customer_success, sales, finance, engineering,
        product, strategy, communications must be kept."""
        from maestro_personal_shell.nerve_wiring import NerveWiring
        kept = ["chief_of_staff", "customer_success", "sales", "finance",
                "engineering", "product", "strategy", "communications"]
        for agent in kept:
            assert agent in NerveWiring.PERSONAL_AGENTS, \
                f"F4: '{agent}' should be in personal agents"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
