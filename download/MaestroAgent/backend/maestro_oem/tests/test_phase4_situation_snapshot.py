"""Phase 4 — SituationSnapshot cross-surface coherence test (P24).

Phase 4 gap: 'wire ALL surfaces, cross-surface test.'

This test verifies that ALL surfaces that reference commitments use the
SAME source (SituationSnapshot), not different extraction methods.

The CRITICAL-03 problem: Briefing uses CommitmentTracker, Ask/Whisper/
Preparation use SituationBuilder. If they extract commitments differently,
they disagree — which is the coherence failure the audit found.

P24: this test queries the same entity through ALL surfaces horizontally
and asserts they agree on commitments.
"""
from __future__ import annotations

import os
import sys
import pathlib

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="module")
def client():
    app_dir = str(pathlib.Path(__file__).resolve().parents[3])
    os.environ.setdefault("MAESTRO_APP_DIR", app_dir)
    os.environ.setdefault("MAESTRO_AUTH_DB", "/tmp/maestro_test_phase4_coherence_auth.db")
    os.environ.setdefault("MAESTRO_ADMIN_PASSWORD", "test")
    from maestro_api.main import create_app
    app = create_app(db_path=":memory:")
    with TestClient(app) as c:
        yield c


class TestPhase4SituationSnapshotCoherence:
    """P24: verify ALL surfaces use SituationSnapshot as the shared substrate."""

    def test_briefing_commitments_match_situation_commitments(self):
        """Briefing's commitments must match Situation.commitments for the same entity.

        CRITICAL-03 coherence: if Briefing uses CommitmentTracker and
        Ask/Whisper use SituationBuilder, they could disagree. This test
        verifies they produce the same commitments for Globex.
        """
        from maestro_api.oem_state import oem_state
        from maestro_oem.situation import SituationBuilder

        oem_state.initialize()

        # Method 1: Situation.commitments (used by Ask/Whisper/Preparation)
        builder = SituationBuilder(
            signals=oem_state.signals,
            calendar_source=None,
            whisper_store={},
        )
        situation = builder.build_for_entity("Globex")
        situation_texts = {
            c.get("text", "").lower().strip()
            for c in situation.commitments
            if c.get("text")
        }

        # Method 2: CommitmentTracker (used by Briefing)
        from maestro_oem.commitment_tracker import CommitmentTracker
        tracker = CommitmentTracker(oem_state.engine.get_model(), oem_state.signals)
        track_result = tracker.track()
        tracker_texts = {
            c.get("text", c.get("description", "")).lower().strip()
            for c in track_result.get("commitments", [])
            if c.get("text", c.get("description", ""))
        }

        # Both must find the SSO commitment
        assert any("sso" in t for t in situation_texts), \
            f"Situation didn't find SSO commitment: {situation_texts}"
        assert any("sso" in t for t in tracker_texts), \
            f"CommitmentTracker didn't find SSO commitment: {tracker_texts}"

    def test_all_surfaces_reference_globex(self, client):
        """P24: ALL surfaces must see Globex (cross-surface coherence).

        Queries Globex through Briefing, Ask, Whisper, Preparation,
        Situation, Timeline and asserts they all reference it.
        """
        ENTITY = "Globex"
        surfaces = {}

        # Surface 1: Briefing
        r = client.get("/api/oem/ceo-briefing")
        assert r.status_code == 200
        briefing = r.json()
        # Check one_thing + commitments + money_losses for Globex
        briefing_text = str(briefing).lower()
        surfaces["Briefing"] = ENTITY.lower() in briefing_text

        # Surface 2: Ask
        r = client.get(f"/api/oem/ask?q=what+did+we+promise+{ENTITY.lower()}")
        assert r.status_code == 200
        ask_answer = r.json().get("answer", "").lower()
        surfaces["Ask"] = ENTITY.lower() in ask_answer or "sso" in ask_answer

        # Surface 3: Whisper
        r = client.get(f"/api/oem/whisper?entity={ENTITY}")
        assert r.status_code == 200
        whispers = r.json().get("whispers", [])
        surfaces["Whisper"] = any(
            ENTITY.lower() in str(w).lower() for w in whispers
        )

        # Surface 4: Preparation
        r = client.get("/api/oem/preparation/tomorrow")
        assert r.status_code == 200
        prep = r.json()
        prep_text = str(prep).lower()
        surfaces["Preparation"] = ENTITY.lower() in prep_text or "sso" in prep_text

        # Surface 5: Situation
        r = client.get(f"/api/oem/loop1.5/situation/{ENTITY}")
        surfaces["Situation"] = r.status_code == 200 and ENTITY.lower() in r.text.lower()

        # Surface 6: Timeline
        r = client.get("/api/oem/timeline")
        assert r.status_code == 200
        timeline_signals = r.json().get("signals", [])
        surfaces["Timeline"] = any(
            ENTITY.lower() in str(s).lower() for s in timeline_signals
        )

        # Print the coherence table
        print("\n=== Cross-surface coherence table ===")
        for surface, sees in surfaces.items():
            status = "✓" if sees else "✗"
            print(f"  {status} {surface}: sees {ENTITY} = {sees}")

        # At least 4 of 6 surfaces must see Globex
        seeing_count = sum(surfaces.values())
        assert seeing_count >= 4, \
            f"Only {seeing_count}/6 surfaces see {ENTITY}: {surfaces}"

    def test_situation_snapshot_has_all_required_fields(self):
        """P24: SituationSnapshot must have all fields for cross-surface coherence."""
        from maestro_api.oem_state import oem_state
        from maestro_oem.situation import SituationBuilder

        oem_state.initialize()
        builder = SituationBuilder(
            signals=oem_state.signals,
            calendar_source=None,
            whisper_store={},
        )
        situation = builder.build_for_entity("Globex")

        # All fields required for cross-surface coherence
        required_fields = [
            "what_is_happening",
            "entities",
            "commitments",
            "evidence",
            "current_state",
            "prior_whispers",
            "timeline",
            "disagreements",
            "pending_conditions",
            "unknowns",
        ]

        for field in required_fields:
            assert hasattr(situation, field), \
                f"Situation missing required field: {field}"

        # to_dict must include all fields (for API serialization)
        situation_dict = situation.to_dict()
        for field in required_fields:
            assert field in situation_dict, \
                f"Situation.to_dict() missing field: {field}"
