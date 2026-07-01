"""
V8 Daily Work #3 — Proactive Daily Briefing (upgraded). Regression tests.

Each brief item gets a DRAFTED artifact (email/doc) with evidence citations.
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
    os.environ.setdefault("MAESTRO_AUTH_DB", "/tmp/maestro_test_briefing_auth.db")
    os.environ.setdefault("MAESTRO_ADMIN_PASSWORD", "test")
    from maestro_api.main import create_app
    app = create_app(db_path=":memory:")
    with TestClient(app) as c:
        yield c


class TestDraftedArtifacts:
    """The CEO briefing must include drafted artifacts with evidence citations."""

    def test_briefing_has_drafted_artifacts(self, client) -> None:
        r = client.get("/api/oem/ceo-briefing")
        data = r.json()
        assert "drafted_artifacts" in data, "Briefing missing drafted_artifacts field"

    def test_drafted_artifacts_have_required_fields(self, client) -> None:
        r = client.get("/api/oem/ceo-briefing")
        data = r.json()
        for draft in data["drafted_artifacts"]:
            assert "type" in draft, f"Draft missing type: {draft}"
            assert draft["type"] in ("email", "doc", "ticket"), f"Invalid draft type: {draft['type']}"
            assert "to" in draft
            assert "subject" in draft
            assert "body" in draft
            assert "evidence" in draft
            assert "source_item" in draft

    def test_drafted_artifacts_have_evidence_citations(self, client) -> None:
        """Each draft must have evidence citations (not just a body)."""
        r = client.get("/api/oem/ceo-briefing")
        data = r.json()
        for draft in data["drafted_artifacts"]:
            assert len(draft["evidence"]) > 0, (
                f"Draft for {draft['source_item']} has no evidence citations"
            )

    def test_drafted_artifacts_bodies_reference_evidence(self, client) -> None:
        """The draft body must reference the evidence (not be generic)."""
        r = client.get("/api/oem/ceo-briefing")
        data = r.json()
        for draft in data["drafted_artifacts"]:
            # The body should contain "Evidence:" section
            assert "Evidence:" in draft["body"] or "evidence" in draft["body"].lower(), (
                f"Draft body for {draft['source_item']} missing evidence section"
            )

    def test_drafted_artifacts_cover_brief_items(self, client) -> None:
        """Drafts should cover multiple brief items (one_thing, money, knowledge, decisions)."""
        r = client.get("/api/oem/ceo-briefing")
        data = r.json()
        sources = {d["source_item"] for d in data["drafted_artifacts"]}
        # At least 2 different source items should have drafts
        assert len(sources) >= 2, (
            f"Expected drafts from multiple brief items, got sources: {sources}"
        )

    def test_drafted_email_has_recipient(self, client) -> None:
        """Email drafts must have a recipient (not empty)."""
        r = client.get("/api/oem/ceo-briefing")
        data = r.json()
        for draft in data["drafted_artifacts"]:
            if draft["type"] == "email":
                assert draft["to"], f"Email draft has empty recipient: {draft}"
                assert draft["to"] != "", f"Email draft has empty 'to' field"

    def test_drafted_body_is_substantial(self, client) -> None:
        """Draft bodies must be substantial (not just a one-liner)."""
        r = client.get("/api/oem/ceo-briefing")
        data = r.json()
        for draft in data["drafted_artifacts"]:
            assert len(draft["body"]) > 50, (
                f"Draft body for {draft['source_item']} too short: {len(draft['body'])} chars"
            )
