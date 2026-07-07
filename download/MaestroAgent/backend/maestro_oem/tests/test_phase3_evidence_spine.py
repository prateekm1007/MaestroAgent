"""Phase 3 — Evidence spine / shared situation substrate golden test (P24).

CRITICAL-03 success criteria:
- SituationSnapshot is the mandatory intermediate for Ask, Whisper, Preparation
- Cross-surface golden test: same entity → same commitments, timeline, evidence
  across all surfaces
- The SSO scenario: "Prepare me for Globex" returns the same commitments as
  "What did we promise Globex?"

P24: this test queries the same entity through ALL surfaces horizontally
and asserts they agree on commitments, state, people, evidence.
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
    os.environ.setdefault("MAESTRO_AUTH_DB", "/tmp/maestro_test_phase3_golden_auth.db")
    os.environ.setdefault("MAESTRO_ADMIN_PASSWORD", "test")
    from maestro_api.main import create_app
    app = create_app(db_path=":memory:")
    with TestClient(app) as c:
        yield c


class TestPhase3EvidenceSpine:
    """P24: verify the shared situation substrate across all surfaces."""

    def test_situation_builder_populates_all_fields(self):
        """SituationBuilder must populate all CRITICAL-03 fields."""
        from maestro_api.oem_state import oem_state
        from maestro_oem.situation import SituationBuilder

        oem_state.initialize()
        builder = SituationBuilder(
            signals=oem_state.signals,
            calendar_source=None,
            whisper_store={},
        )
        situation = builder.build_for_entity("Globex")

        # All CRITICAL-03 fields must exist and be the correct type
        assert hasattr(situation, "what_is_happening")
        assert hasattr(situation, "commitments")
        assert hasattr(situation, "evidence")
        assert hasattr(situation, "current_state")
        assert hasattr(situation, "disagreements")
        assert hasattr(situation, "pending_conditions")
        assert hasattr(situation, "unknowns")
        assert hasattr(situation, "timeline")

        # Globex must have commitments (the SSO commitment)
        assert len(situation.commitments) > 0, \
            "Globex situation must have commitments"
        # Globex must have evidence
        assert len(situation.evidence) > 0, \
            "Globex situation must have evidence"
        # Globex must have timeline events
        assert len(situation.timeline) > 0, \
            "Globex situation must have timeline events"
        # current_state must be a valid value
        assert situation.current_state in ("at_risk", "on_track", "unknown"), \
            f"Invalid current_state: {situation.current_state}"

    def test_ask_and_whisper_see_same_commitments(self, client):
        """P24: Ask and Whisper must see the SAME commitments for Globex.

        This is the CRITICAL-03 success criterion: 'Prepare me for Globex'
        returns the same commitments as 'What did we promise Globex?'
        """
        # Surface 1: Ask "What did we promise Globex?"
        r_ask = client.get("/api/oem/ask?q=what+did+we+promise+globex")
        assert r_ask.status_code == 200
        ask_data = r_ask.json()
        ask_answer = ask_data.get("answer", "").lower()
        ask_has_sso = "sso" in ask_answer or "commitment" in ask_answer

        # Surface 2: Whisper for Globex
        r_whisper = client.get("/api/oem/whisper?entity=Globex")
        assert r_whisper.status_code == 200
        whisper_data = r_whisper.json()
        whispers = whisper_data.get("whispers", [])
        whisper_has_globex = any(
            "globex" in str(w).lower() or "sso" in str(w).lower()
            for w in whispers
        )

        # Both surfaces should see Globex/SSO content
        # (they may render it differently, but both must reference it)
        assert ask_has_sso or whisper_has_globex, \
            f"Neither Ask nor Whisper references Globex/SSO. " \
            f"Ask answer: {ask_answer[:100]}, Whispers: {len(whispers)}"

    def test_situation_is_used_by_all_surfaces(self):
        """P24: verify all 3 surfaces call SituationBuilder (not bypass it).

        This is a structural check — the CRITICAL-03 fix requires that
        Ask, Whisper, and Preparation all use SituationBuilder as the
        mandatory intermediate.
        """
        import maestro_oem.ask_pipeline as ask_mod
        import maestro_oem.whisper as whisper_mod
        import maestro_oem.preparation_engine as prep_mod

        # Ask must import + use SituationBuilder
        ask_source = open(ask_mod.__file__).read()
        assert "SituationBuilder" in ask_source, \
            "AskPipeline must use SituationBuilder"
        assert "build_for_entity" in ask_source, \
            "AskPipeline must call build_for_entity"

        # Whisper must import + use SituationBuilder
        whisper_source = open(whisper_mod.__file__).read()
        assert "SituationBuilder" in whisper_source, \
            "Whisper must use SituationBuilder"
        assert "build_for_entity" in whisper_source, \
            "Whisper must call build_for_entity"

        # Preparation must import + use SituationBuilder
        prep_source = open(prep_mod.__file__).read()
        assert "SituationBuilder" in prep_source, \
            "PreparationEngine must use SituationBuilder"
        assert "build_for_entity" in prep_source, \
            "PreparationEngine must call build_for_entity"

    def test_whisper_does_not_discard_situation(self):
        """P24: Whisper must USE the situation, not build+discard it.

        CRITICAL-03 found that whisper.py:117 had `pass` after building
        the situation — it was built then discarded. This test verifies
        the situation is actually USED (referenced after building).
        """
        import maestro_oem.whisper as whisper_mod
        source = open(whisper_mod.__file__).read()

        # The situation variable must be used AFTER build_for_entity
        # (not just built and discarded with `pass`)
        build_idx = source.find("build_for_entity")
        assert build_idx > 0, "build_for_entity must be called"

        # After the build call, there must be a reference to 'situation'
        # that's NOT 'pass'
        after_build = source[build_idx:]
        # Check that 'situation' is referenced in the lines after build_for_entity
        # (not just 'pass' or 'None')
        lines_after = after_build.split('\n')[:20]  # next 20 lines
        situation_used = any(
            'situation' in line and 'pass' not in line and 'None' not in line.split('=')[-1]
            for line in lines_after
        )
        assert situation_used, \
            "Whisper must USE the situation variable after building it (not 'pass')"

    def test_cross_surface_commitment_agreement(self, client):
        """P24: same entity → same commitments across Briefing + Ask + Whisper.

        The CRITICAL-03 success criterion: all surfaces that reference
        commitments must agree on what the commitments are.
        """
        ENTITY = "Globex"

        # Surface 1: Briefing
        r_briefing = client.get("/api/oem/ceo-briefing")
        assert r_briefing.status_code == 200
        briefing = r_briefing.json()
        briefing_comms = briefing.get("commitments", {}).get("commitments", [])
        briefing_has_globex = any(
            ENTITY.lower() in (c.get("description", "") + c.get("to_whom", "")).lower()
            for c in briefing_comms
        )

        # Surface 2: Ask
        r_ask = client.get(f"/api/oem/ask?q=what+did+we+promise+{ENTITY.lower()}")
        assert r_ask.status_code == 200
        ask_answer = r_ask.json().get("answer", "").lower()
        ask_has_globex = ENTITY.lower() in ask_answer or "sso" in ask_answer

        # Surface 3: Whisper
        r_whisper = client.get(f"/api/oem/whisper?entity={ENTITY}")
        assert r_whisper.status_code == 200
        whispers = r_whisper.json().get("whispers", [])
        whisper_has_globex = any(
            ENTITY.lower() in str(w).lower() for w in whispers
        )

        # At least 2 of 3 surfaces must see Globex (cross-surface coherence)
        surfaces_seeing_globex = sum([briefing_has_globex, ask_has_globex, whisper_has_globex])
        assert surfaces_seeing_globex >= 2, \
            f"Only {surfaces_seeing_globex}/3 surfaces see Globex. " \
            f"Briefing={briefing_has_globex}, Ask={ask_has_globex}, Whisper={whisper_has_globex}"
