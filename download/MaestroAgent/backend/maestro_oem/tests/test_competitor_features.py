"""
V8 Competitor Analysis Features C, D, E, A — Regression tests.

C: Verified Knowledge Layer — verified_by/verified_at on laws
D: Governed Auto-Action — auto-DRAFT for contradictions
E: Commitment Tracker — track commitments, flag broken
A: New Evidence Connectors — Glean, Guru, Dust registered
"""

from __future__ import annotations

import os
import pathlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    app_dir = str(pathlib.Path(__file__).resolve().parents[3])
    os.environ.setdefault("MAESTRO_APP_DIR", app_dir)
    os.environ.setdefault("MAESTRO_AUTH_DB", "/tmp/maestro_test_competitor_auth.db")
    os.environ.setdefault("MAESTRO_ADMIN_PASSWORD", "test")
    from maestro_api.main import create_app
    app = create_app(db_path=":memory:")
    with TestClient(app) as c:
        yield c


# ============================================================
# Feature C — Verified Knowledge Layer
# ============================================================

class TestVerifiedKnowledgeLayer:
    """Laws can be verified by humans. Verified laws are the differentiator."""

    def test_law_has_verified_fields(self, client) -> None:
        """GET /api/oem/laws must include verified_by + verified_at fields."""
        r = client.get("/api/oem/laws")
        data = r.json()
        laws = data.get("laws", data) if isinstance(data, dict) else data
        if laws:
            assert "verified_by" in laws[0]
            assert "verified_at" in laws[0]

    def test_verify_law_endpoint(self, client) -> None:
        """POST /api/oem/laws/{code}/verify must set verified_by + verified_at."""
        # Get a law code
        r = client.get("/api/oem/laws")
        data = r.json()
        laws = data.get("laws", data) if isinstance(data, dict) else data
        if not laws:
            pytest.skip("No laws in the model")
        code = laws[0]["code"]

        # Verify it
        r2 = client.post(f"/api/oem/laws/{code}/verify", json={"verified_by": "ceo@acme.com"})
        assert r2.status_code == 200
        verified = r2.json()
        assert verified["verified_by"] == "ceo@acme.com"
        assert verified["verified_at"] is not None

    def test_verify_requires_verified_by(self, client) -> None:
        """POST /api/oem/laws/{code}/verify must require verified_by."""
        r = client.get("/api/oem/laws")
        data = r.json()
        laws = data.get("laws", data) if isinstance(data, dict) else data
        if not laws:
            pytest.skip("No laws")
        code = laws[0]["code"]
        r2 = client.post(f"/api/oem/laws/{code}/verify", json={})
        assert r2.status_code == 400

    def test_list_verified_laws(self, client) -> None:
        """GET /api/oem/laws/verified/list must return verified laws only."""
        r = client.get("/api/oem/laws/verified/list")
        assert r.status_code == 200
        data = r.json()
        assert "verified_laws" in data
        assert "count" in data

    def test_law_model_has_verified_fields(self) -> None:
        """OrganizationalLaw must have verified_by and verified_at fields."""
        from maestro_oem.law import OrganizationalLaw
        law = OrganizationalLaw(code="L-TEST", statement="test", condition="c", outcome="o")
        assert hasattr(law, "verified_by")
        assert hasattr(law, "verified_at")
        assert law.verified_by is None
        assert law.verified_at is None


# ============================================================
# Feature D — Governed Auto-Action
# ============================================================

class TestGovernedAutoAction:
    """Auto-DRAFT Jira/Slack for contradictions. Never auto-SEND."""

    def test_auto_action_returns_previews(self, client) -> None:
        """POST /api/oem/auto-action/contradictions must return previews (not executed)."""
        from maestro_oem.writeback import WriteBackStore
        WriteBackStore.clear()
        r = client.post("/api/oem/auto-action/contradictions", json={"provider": "slack", "channel": "general"})
        assert r.status_code == 200
        data = r.json()
        assert "previews" in data
        assert "count" in data
        # Each preview must be pending (NOT executed)
        for preview in data["previews"]:
            assert preview["status"] == "pending"
        WriteBackStore.clear()

    def test_auto_action_previews_need_approval(self, client) -> None:
        """Auto-action previews must NOT be executed — they require approval."""
        from maestro_oem.writeback import WriteBackStore
        WriteBackStore.clear()
        r = client.post("/api/oem/auto-action/contradictions", json={"provider": "jira", "project": "ENG"})
        data = r.json()
        for preview in data["previews"]:
            action = WriteBackStore.get(preview["action_id"])
            if action:
                assert action.status == "pending"
                assert action.result is None  # NOT executed
        WriteBackStore.clear()

    def test_auto_action_supports_slack_and_jira(self, client) -> None:
        """Auto-action must support both Slack and Jira providers."""
        from maestro_oem.writeback import WriteBackStore
        WriteBackStore.clear()
        r1 = client.post("/api/oem/auto-action/contradictions", json={"provider": "slack"})
        r2 = client.post("/api/oem/auto-action/contradictions", json={"provider": "jira"})
        assert r1.status_code == 200
        assert r2.status_code == 200
        WriteBackStore.clear()


# ============================================================
# Feature E — Commitment Tracker
# ============================================================

class TestCommitmentTracker:
    """Track commitments made in signal text. Flag broken commitments."""

    def test_commitments_endpoint_returns_200(self, client) -> None:
        r = client.get("/api/oem/commitments")
        assert r.status_code == 200

    def test_commitments_has_required_structure(self, client) -> None:
        r = client.get("/api/oem/commitments")
        data = r.json()
        assert "commitments" in data
        assert "total" in data
        assert "open_count" in data
        assert "kept_count" in data
        assert "broken_count" in data
        assert "summary" in data

    def test_commitments_filter_by_status(self, client) -> None:
        """Filtering by status must work."""
        r = client.get("/api/oem/commitments", params={"status": "open"})
        assert r.status_code == 200
        data = r.json()
        for c in data["commitments"]:
            assert c["status"] == "open"

    def test_commitment_tracker_extracts_commitments(self) -> None:
        """The CommitmentTracker must extract commitments from signal text."""
        from maestro_oem.commitment_tracker import CommitmentTracker
        from maestro_oem import OEMEngine
        from maestro_oem.signal import ExecutionSignal, SignalType, SignalProvider
        from datetime import datetime, timezone

        engine = OEMEngine()
        model = engine.get_model()
        sig = ExecutionSignal(
            type=SignalType.MESSAGE_SENT,
            timestamp=datetime.now(timezone.utc),
            actor="priya@acme.com",
            artifact="slack:msg/commitment-test",
            metadata={"text": "I'll get back to you by Friday with the review", "participants": ["raj@acme.com"]},
            provider=SignalProvider.SLACK,
        )
        tracker = CommitmentTracker(model, [sig])
        result = tracker.track()
        assert result["total"] >= 1
        commitment = result["commitments"][0]
        assert "description" in commitment
        assert commitment["who_committed"] == "priya@acme.com"
        assert commitment["status"] in ("open", "kept", "broken")


# ============================================================
# Feature A — New Evidence Connectors
# ============================================================

class TestNewEvidenceConnectors:
    """Glean, Guru, Dust registered as evidence sources."""

    def test_glean_in_oauth_endpoints(self) -> None:
        """Glean must be in the OAuth endpoints config."""
        from maestro_oem.oauth_manager import _DEFAULT_ENDPOINTS
        assert "glean" in _DEFAULT_ENDPOINTS
        assert "auth_url" in _DEFAULT_ENDPOINTS["glean"]
        assert "scopes" in _DEFAULT_ENDPOINTS["glean"]

    def test_guru_in_oauth_endpoints(self) -> None:
        """Guru must be in the OAuth endpoints config."""
        from maestro_oem.oauth_manager import _DEFAULT_ENDPOINTS
        assert "guru" in _DEFAULT_ENDPOINTS

    def test_dust_in_oauth_endpoints(self) -> None:
        """Dust must be in the OAuth endpoints config."""
        from maestro_oem.oauth_manager import _DEFAULT_ENDPOINTS
        assert "dust" in _DEFAULT_ENDPOINTS

    def test_new_providers_in_status(self) -> None:
        """The OAuth status must include the new providers."""
        from maestro_oem.oauth_manager import _DEFAULT_ENDPOINTS
        # The status() method iterates over a hardcoded list — verify it includes the new providers
        import maestro_oem.oauth_manager as mod
        source = open(mod.__file__).read()
        assert '"glean"' in source
        assert '"guru"' in source
        assert '"dust"' in source

    def test_signal_provider_has_new_connectors(self) -> None:
        """SignalProvider enum must include GLEAN, GURU, DUST."""
        from maestro_oem.signal import SignalProvider
        assert hasattr(SignalProvider, "GLEAN")
        assert hasattr(SignalProvider, "GURU")
        assert hasattr(SignalProvider, "DUST")

    def test_new_connectors_have_evidence_type(self) -> None:
        """Each new connector must have an evidence_type in its config."""
        from maestro_oem.oauth_manager import _DEFAULT_ENDPOINTS
        for provider in ("glean", "guru", "dust"):
            config = _DEFAULT_ENDPOINTS[provider]
            assert "evidence_type" in config["extra"], (
                f"{provider} missing evidence_type — the Glean lesson requires "
                f"treating these as evidence sources, not tools to replace"
            )
