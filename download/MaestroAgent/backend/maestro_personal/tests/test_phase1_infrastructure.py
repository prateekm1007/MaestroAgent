"""
V8 Personal Mode — Phase 1 Infrastructure Tests.

Tests all 12 coding guidelines (P1-P12) for Personal Mode.
"""

from __future__ import annotations

import os
import pathlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clear_personal_stores():
    from maestro_personal.consent import ConsentStore
    from maestro_personal.mode import ModeManager
    from maestro_personal.incognito import IncognitoManager
    from maestro_personal.expiry import DataExpiry
    from maestro_personal.store import PersonalDataStore
    from maestro_personal.local import LocalFirstConfig
    ConsentStore.clear()
    ModeManager.clear()
    IncognitoManager.clear()
    DataExpiry.clear()
    PersonalDataStore.clear()
    LocalFirstConfig.clear()
    yield
    ConsentStore.clear()
    ModeManager.clear()
    IncognitoManager.clear()
    DataExpiry.clear()
    PersonalDataStore.clear()
    LocalFirstConfig.clear()


# ============================================================
# P1: Constitutional Amendment
# ============================================================

class TestConstitutionalAmendment:
    """The constitution must be amended before any Personal Mode code."""

    def test_constitution_has_personal_mode_amendment(self) -> None:
        import pathlib
        import maestro_personal
        constitution_path = pathlib.Path(maestro_personal.__file__).resolve().parents[2] / "CONSTITUTION.md"
        if not constitution_path.exists():
            pytest.skip("CONSTITUTION.md not found")
        source = open(constitution_path).read()
        assert "PERSONAL MODE" in source
        assert "more capable, not more dependent" in source.lower()

    def test_constitution_has_four_guardrails(self) -> None:
        import pathlib
        import maestro_personal
        constitution_path = pathlib.Path(maestro_personal.__file__).resolve().parents[2] / "CONSTITUTION.md"
        if not constitution_path.exists():
            pytest.skip("CONSTITUTION.md not found")
        source = open(constitution_path).read()
        assert "Self-facing only by default" in source
        assert "Consent is bilateral" in source
        assert "Indispensable, not addictive" in source
        assert "Mode separation" in source

    def test_constitution_rejects_manipulation_features(self) -> None:
        import pathlib
        import maestro_personal
        constitution_path = pathlib.Path(maestro_personal.__file__).resolve().parents[2] / "CONSTITUTION.md"
        if not constitution_path.exists():
            pytest.skip("CONSTITUTION.md not found")
        source = open(constitution_path).read()
        assert "flirt" in source.lower()
        assert "surveillance" in source.lower()


# ============================================================
# P2: Separate Codebase Namespace
# ============================================================

class TestSeparateNamespace:
    """maestro_personal/ must NOT import from maestro_oem/."""

    def test_no_maestro_oem_imports_in_personal(self) -> None:
        import pathlib
        personal_dir = pathlib.Path(__file__).resolve().parent.parent
        for py_file in personal_dir.rglob("*.py"):
            if "test_" in py_file.name:
                continue
            source = open(py_file).read()
            lines = source.split("\n")
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'"):
                    continue
                if "from maestro_oem" in stripped or "import maestro_oem" in stripped:
                    pytest.fail(f"{py_file.name}:{i+1} imports from maestro_oem: {stripped}")

    def test_personal_namespace_exists(self) -> None:
        import maestro_personal
        assert maestro_personal.__version__ == "0.1.0"


# ============================================================
# P3: ConsentStore
# ============================================================

class TestConsentStore:
    """Per-source consent primitive. No data without consent."""

    def test_consent_required_raises_without_consent(self) -> None:
        from maestro_personal.consent import ConsentStore, ConsentError
        with pytest.raises(ConsentError):
            ConsentStore.require_consent("user1", "calendar", "store")

    def test_grant_consent_allows_access(self) -> None:
        from maestro_personal.consent import ConsentStore
        ConsentStore.grant_consent("user1", "calendar", "store")
        assert ConsentStore.has_consent("user1", "calendar", "store")
        ConsentStore.require_consent("user1", "calendar", "store")

    def test_revoke_consent_blocks_access(self) -> None:
        from maestro_personal.consent import ConsentStore, ConsentError
        ConsentStore.grant_consent("user1", "calendar", "store")
        ConsentStore.revoke_consent("user1", "calendar", "store")
        assert not ConsentStore.has_consent("user1", "calendar", "store")
        with pytest.raises(ConsentError):
            ConsentStore.require_consent("user1", "calendar", "store")

    def test_third_party_consent_required(self) -> None:
        from maestro_personal.consent import ConsentStore, ConsentError
        with pytest.raises(ConsentError):
            ConsentStore.require_third_party_consent("sarah@example.com", "message_generation")
        ConsentStore.grant_third_party_consent("sarah@example.com", "message_generation")
        ConsentStore.require_third_party_consent("sarah@example.com", "message_generation")

    def test_user_consent_not_sufficient_for_third_party(self) -> None:
        from maestro_personal.consent import ConsentStore, ConsentError
        ConsentStore.grant_consent("user1", "user_notes", "store")
        assert not ConsentStore.has_third_party_consent("sarah@example.com", "message_generation")
        with pytest.raises(ConsentError):
            ConsentStore.require_third_party_consent("sarah@example.com", "message_generation")


# ============================================================
# P4: No Third-Party Scraping
# ============================================================

class TestNoScraping:
    """No HTTP calls to social media APIs in maestro_personal/."""

    def test_no_social_media_urls(self) -> None:
        import pathlib
        personal_dir = pathlib.Path(__file__).resolve().parent.parent
        for py_file in personal_dir.rglob("*.py"):
            if "test_" in py_file.name:
                continue
            source = open(py_file).read().lower()
            for url in ["instagram.com", "facebook.com", "twitter.com", "x.com", "linkedin.com"]:
                assert url not in source, f"{py_file.name} contains social media URL: {url}"


# ============================================================
# P5: Local-First Processing
# ============================================================

class TestLocalFirst:
    """LOCAL_ONLY mode disables all cloud calls."""

    def test_local_only_blocks_cloud(self) -> None:
        from maestro_personal.local import LocalFirstConfig
        LocalFirstConfig.set_local_only(True)
        with pytest.raises(RuntimeError, match="LOCAL_ONLY"):
            LocalFirstConfig.require_cloud_consent("llm_inference")

    def test_cloud_requires_consent(self) -> None:
        from maestro_personal.local import LocalFirstConfig
        LocalFirstConfig.set_local_only(False)
        with pytest.raises(RuntimeError, match="consent"):
            LocalFirstConfig.require_cloud_consent("llm_inference")
        LocalFirstConfig.grant_cloud_consent("llm_inference")
        LocalFirstConfig.require_cloud_consent("llm_inference")


# ============================================================
# P6: Incognito Mode
# ============================================================

class TestIncognito:
    """Incognito mode: no data persisted."""

    def test_incognito_does_not_persist(self) -> None:
        from maestro_personal.incognito import IncognitoManager
        from maestro_personal.store import PersonalDataStore
        from maestro_personal.consent import ConsentStore

        ConsentStore.grant_consent("user1", "user_notes", "store")
        session = IncognitoManager.start_session("user1")
        assert IncognitoManager.is_incognito("user1")

        item = PersonalDataStore.store("user1", "note", "user_notes", "sensitive info")
        assert len(PersonalDataStore._items) == 0, "Item was persisted during incognito!"

        IncognitoManager.end_session("user1")
        assert not IncognitoManager.is_incognito("user1")
        assert len(session._ephemeral_data) == 0, "Ephemeral data was not discarded!"


# ============================================================
# P7: Data Expiration
# ============================================================

class TestDataExpiry:
    """Personal data expires after 24 months by default."""

    def test_expired_data_is_archived(self) -> None:
        from maestro_personal.expiry import DataExpiry
        from datetime import datetime, timedelta, timezone

        old_ts = (datetime.now(timezone.utc) - timedelta(days=365 * 3)).isoformat()
        DataExpiry.register_item("item-1", "memory", old_ts)
        DataExpiry.register_item("item-2", "memory", datetime.now(timezone.utc).isoformat())

        result = DataExpiry.sweep()
        assert result["archived"] >= 1
        assert result["remaining"] >= 1

    def test_keep_flag_prevents_expiry(self) -> None:
        from maestro_personal.expiry import DataExpiry
        from datetime import datetime, timedelta, timezone

        old_ts = (datetime.now(timezone.utc) - timedelta(days=365 * 3)).isoformat()
        DataExpiry.register_item("item-keep", "memory", old_ts, keep=True)

        result = DataExpiry.sweep()
        assert result["archived"] == 0

    def test_custom_expiry_months(self) -> None:
        from maestro_personal.expiry import DataExpiry
        DataExpiry.set_expiry_months("user1", 1)
        assert DataExpiry.get_expiry_months("user1") == 1
        assert DataExpiry.get_expiry_months("default") == 24


# ============================================================
# P8: "What Maestro Knows" Dashboard
# ============================================================

class TestDashboard:
    """The dashboard shows everything Maestro knows, with revocation."""

    def test_dashboard_shows_sources(self) -> None:
        from maestro_personal.dashboard import WhatMaestroKnows
        from maestro_personal.store import PersonalDataStore
        from maestro_personal.consent import ConsentStore

        ConsentStore.grant_consent("user1", "user_notes", "store")
        ConsentStore.grant_consent("user1", "user_notes", "retrieve")
        PersonalDataStore.store("user1", "note", "user_notes", "my note")

        dashboard = WhatMaestroKnows.get_dashboard("user1")
        assert "sources" in dashboard
        assert dashboard["total_items"] >= 1

    def test_revoke_source_deletes_data(self) -> None:
        from maestro_personal.dashboard import WhatMaestroKnows
        from maestro_personal.store import PersonalDataStore
        from maestro_personal.consent import ConsentStore

        ConsentStore.grant_consent("user1", "user_notes", "store")
        ConsentStore.grant_consent("user1", "user_notes", "retrieve")
        PersonalDataStore.store("user1", "note", "user_notes", "my note")

        result = WhatMaestroKnows.revoke_source("user1", "user_notes")
        assert result["deleted_items"] >= 1
        assert result["revoked"] is True


# ============================================================
# P10: Mode Separation
# ============================================================

class TestModeSeparation:
    """Work and Personal profiles are strictly partitioned."""

    def test_same_entity_gets_separate_profiles(self) -> None:
        from maestro_personal.mode import ModeManager, Mode

        work_profile = ModeManager.create_profile("sarah@acme.com", Mode.WORK, name="Sarah (colleague)", context="engineering")
        personal_profile = ModeManager.create_profile("sarah@acme.com", Mode.PERSONAL, name="Sarah (friend)", context="friend")

        assert work_profile.mode == Mode.WORK
        assert personal_profile.mode == Mode.PERSONAL
        assert work_profile is not personal_profile

    def test_profiles_are_not_merged_automatically(self) -> None:
        from maestro_personal.mode import ModeManager, Mode

        ModeManager.create_profile("sarah@acme.com", Mode.WORK, name="Sarah (work)")
        ModeManager.create_profile("sarah@acme.com", Mode.PERSONAL, name="Sarah (friend)")

        assert ModeManager.are_separated("sarah@acme.com")
        profiles = ModeManager.get_profiles("sarah@acme.com")
        assert len(profiles) == 2

    def test_merge_is_logged(self) -> None:
        from maestro_personal.mode import ModeManager, Mode

        work = ModeManager.create_profile("sarah@acme.com", Mode.WORK, name="Sarah (work)")
        personal = ModeManager.create_profile("sarah@acme.com", Mode.PERSONAL, name="Sarah (friend)")

        merge = ModeManager.merge_profiles("sarah@acme.com", work.entity_id, personal.entity_id, "user1")
        merges = ModeManager.get_merges()
        assert len(merges) >= 1
        assert merges[0].merged_by == "user1"


# ============================================================
# P12: No "Addictive" Framing
# ============================================================

class TestNoAddictiveFraming:
    """The word 'addictive' and its synonyms are forbidden in code."""

    def test_no_addictive_in_personal_code(self) -> None:
        import pathlib
        personal_dir = pathlib.Path(__file__).resolve().parent.parent
        forbidden = ["addict", "hooked", "can't live without", "obsessive"]
        for py_file in personal_dir.rglob("*.py"):
            if "test_" in py_file.name:
                continue
            source = open(py_file).read().lower()
            for word in forbidden:
                assert word not in source, f"{py_file.name} contains forbidden word: '{word}'"
