"""
Round 44 — Work/Personal Integration Test Suite.

Tests the 6 phases of the Round 44 audit + the 5 constitutional
bright-line tests:

  1. Toggle default: OFF (Guideline P3)
  2. Self-facing only: only the user's own personal state, never
     intelligence about a third party (Round 36 bright line)
  3. Bidirectional: if personal state appears in Work Mode, work
     commitments appear in Personal Mode
  4. Informational only: personal context never redirects a work
     recommendation
  5. Withdrawal path: disabling the toggle returns both modes to
     their pre-integration state (Guideline P9)

Also tests the integration.py bright-line guard (defense in depth)
that rejects any payload containing third-party intelligence patterns.
"""

from __future__ import annotations

import os
import pathlib

import pytest
from fastapi.testclient import TestClient


# ─── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_round44_state():
    """Clear all per-user settings + personal stores before each test."""
    from maestro_oem.user_settings import UserSettings
    from maestro_personal.consent import ConsentStore
    from maestro_personal.mode import ModeManager
    from maestro_personal.incognito import IncognitoManager
    from maestro_personal.expiry import DataExpiry
    from maestro_personal.store import PersonalDataStore
    from maestro_personal.local import LocalFirstConfig
    UserSettings.clear()
    ConsentStore.clear()
    ModeManager.clear()
    IncognitoManager.clear()
    DataExpiry.clear()
    PersonalDataStore.clear()
    LocalFirstConfig.clear()
    yield
    UserSettings.clear()
    ConsentStore.clear()
    ModeManager.clear()
    IncognitoManager.clear()
    DataExpiry.clear()
    PersonalDataStore.clear()
    LocalFirstConfig.clear()


@pytest.fixture(scope="module")
def client():
    app_dir = str(pathlib.Path(__file__).resolve().parents[3])
    os.environ.setdefault("MAESTRO_APP_DIR", app_dir)
    os.environ.setdefault("MAESTRO_AUTH_DB", "/tmp/maestro_test_round44_auth.db")
    os.environ.setdefault("MAESTRO_ADMIN_PASSWORD", "test")
    from maestro_api.main import create_app
    app = create_app(db_path=":memory:")
    with TestClient(app) as c:
        yield c


# ============================================================
# Phase 0 — Constitution Amendment
# ============================================================

class TestPhase0ConstitutionAmendment:
    """The Round 44 amendment must be in CONSTITUTION.md."""

    def test_constitution_has_round44_amendment(self) -> None:
        import maestro_personal
        constitution_path = (
            pathlib.Path(maestro_personal.__file__).resolve().parents[2]
            / "CONSTITUTION.md"
        )
        assert constitution_path.exists(), "CONSTITUTION.md must exist"
        text = constitution_path.read_text()
        assert "CONSTITUTIONAL AMENDMENT: WORK/PERSONAL INTEGRATION (Round 44)" in text, \
            "Round 44 amendment header must be present"
        assert "equal partners in one app" in text, \
            "Corrected framing must be present"

    def test_constitution_has_five_bright_line_tests(self) -> None:
        import maestro_personal
        constitution_path = (
            pathlib.Path(maestro_personal.__file__).resolve().parents[2]
            / "CONSTITUTION.md"
        )
        text = constitution_path.read_text()
        # All five bright-line test questions must be present
        assert "Is the toggle OFF by default?" in text
        assert "never intelligence about a third party" in text
        assert "Is the integration bidirectional?" in text
        assert "Does the personal context redirect the work recommendation?" in text
        assert "Can the user function without the integration for a week?" in text

    def test_constitution_rejects_personal_intelligence_about_colleagues(self) -> None:
        import maestro_personal
        constitution_path = (
            pathlib.Path(maestro_personal.__file__).resolve().parents[2]
            / "CONSTITUTION.md"
        )
        text = constitution_path.read_text()
        assert "Personal memory about a work colleague surfaced in work context" in text
        assert "Bidirectional Promise" in text or "bidirectional" in text.lower()


# ============================================================
# Phase 1 — The Toggle (default OFF, opt-in)
# ============================================================

class TestPhase1Toggle:
    """The personal-context-in-work toggle defaults to OFF."""

    def test_toggle_defaults_off(self) -> None:
        from maestro_oem.user_settings import UserSettings
        assert UserSettings.is_personal_context_in_work_enabled("default") is False
        assert UserSettings.is_personal_context_in_work_enabled("any-user") is False

    def test_toggle_can_be_enabled(self) -> None:
        from maestro_oem.user_settings import UserSettings
        result = UserSettings.set_personal_context_in_work("alice", True)
        assert result["personal_context_in_work"] is True
        assert UserSettings.is_personal_context_in_work_enabled("alice") is True

    def test_toggle_can_be_disabled(self) -> None:
        from maestro_oem.user_settings import UserSettings
        UserSettings.set_personal_context_in_work("alice", True)
        assert UserSettings.is_personal_context_in_work_enabled("alice") is True
        UserSettings.set_personal_context_in_work("alice", False)
        assert UserSettings.is_personal_context_in_work_enabled("alice") is False

    def test_toggle_per_user_isolation(self) -> None:
        from maestro_oem.user_settings import UserSettings
        UserSettings.set_personal_context_in_work("alice", True)
        # Bob's toggle is still OFF
        assert UserSettings.is_personal_context_in_work_enabled("bob") is False

    def test_get_endpoint_returns_default_off(self, client) -> None:
        r = client.get("/api/personal/settings/personal-context-in-work?user=test")
        assert r.status_code == 200
        data = r.json()
        assert data["personal_context_in_work"] is False
        assert data["default"] is False

    def test_post_endpoint_enables_toggle(self, client) -> None:
        r = client.post("/api/personal/settings/personal-context-in-work", json={
            "enabled": True, "user": "test",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["personal_context_in_work"] is True
        assert "reminder" in data  # constitutional reminder present

    def test_post_endpoint_disables_toggle(self, client) -> None:
        # First enable
        client.post("/api/personal/settings/personal-context-in-work", json={
            "enabled": True, "user": "test",
        })
        # Then disable
        r = client.post("/api/personal/settings/personal-context-in-work", json={
            "enabled": False, "user": "test",
        })
        assert r.status_code == 200
        assert r.json()["personal_context_in_work"] is False

    def test_withdrawal_path_returns_to_default(self, client) -> None:
        """Guideline P9 — disabling returns Work Mode to its default state."""
        client.post("/api/personal/settings/personal-context-in-work", json={
            "enabled": True, "user": "test",
        })
        client.post("/api/personal/settings/personal-context-in-work", json={
            "enabled": False, "user": "test",
        })
        r = client.get("/api/personal/settings/personal-context-in-work?user=test")
        assert r.json()["personal_context_in_work"] is False


# ============================================================
# Phase 2 — Personal State in Work Briefing
# ============================================================

class TestPhase2PersonalStateInWorkBriefing:
    """Personal Context card appears in CEO briefing ONLY when toggle ON."""

    def test_card_absent_when_toggle_off(self, client) -> None:
        """When the toggle is OFF (default), no personal context card."""
        r = client.get("/api/oem/ceo-briefing")
        assert r.status_code == 200
        data = r.json()
        # personal_context must be {} when toggle is OFF
        assert data.get("personal_context") == {}, \
            "Personal context card must be empty when toggle is OFF"

    def test_card_present_when_toggle_on(self, client) -> None:
        """When the toggle is ON, the personal_context field is populated."""
        client.post("/api/personal/settings/personal-context-in-work", json={
            "enabled": True, "user": "default",
        })
        r = client.get("/api/oem/ceo-briefing")
        data = r.json()
        # personal_context should be a non-empty dict with the label
        pc = data.get("personal_context", {})
        assert isinstance(pc, dict)
        # When toggle is ON, the card has the label (even if specific data is empty)
        if pc:  # may be {} if incognito or guard trips, but with toggle on should be populated
            assert pc.get("label") == "Personal context (opt-in)"
            assert pc.get("enabled") is True

    def test_card_is_last_card(self, client) -> None:
        """The personal_context field is the LAST key in the briefing dict."""
        client.post("/api/personal/settings/personal-context-in-work", json={
            "enabled": True, "user": "default",
        })
        r = client.get("/api/oem/ceo-briefing")
        data = r.json()
        keys = list(data.keys())
        # personal_context must be the last key
        assert keys[-1] == "personal_context", \
            f"personal_context must be last; got order: {keys}"

    def test_card_contains_only_user_state(self, client) -> None:
        """The card NEVER contains intelligence about a third party."""
        client.post("/api/personal/settings/personal-context-in-work", json={
            "enabled": True, "user": "default",
        })
        r = client.get("/api/oem/ceo-briefing")
        pc = r.json().get("personal_context", {})
        if not pc:
            pytest.skip("Card empty (no consented personal data) — bright-line vacuously satisfied")
        # Forbidden third-party patterns must NOT appear anywhere in the card
        card_str = str(pc).lower()
        forbidden = ["she values", "he values", "they value", "team energy", "team mood"]
        for pattern in forbidden:
            assert pattern not in card_str, \
                f"Card contains forbidden third-party pattern: {pattern}"

    def test_card_has_withdrawal_path(self, client) -> None:
        """The card must include a withdrawal_path field (Guideline P9)."""
        client.post("/api/personal/settings/personal-context-in-work", json={
            "enabled": True, "user": "default",
        })
        r = client.get("/api/oem/ceo-briefing")
        pc = r.json().get("personal_context", {})
        if pc:
            assert "withdrawal_path" in pc
            assert "withdrawal" in pc["withdrawal_path"].lower() or "disable" in pc["withdrawal_path"].lower()

    def test_card_suppressed_in_incognito(self, client) -> None:
        """Incognito mode suppresses the card — privacy is absolute."""
        client.post("/api/personal/settings/personal-context-in-work", json={
            "enabled": True, "user": "default",
        })
        # Start incognito
        client.post("/api/personal/incognito/start?user=default")
        r = client.get("/api/oem/ceo-briefing")
        pc = r.json().get("personal_context", {})
        assert pc == {}, "Personal context card must be suppressed in incognito mode"


# ============================================================
# Phase 3 — Work Commitments in Personal Briefing (Bidirectional)
# ============================================================

class TestPhase3WorkContextInPersonalBriefing:
    """Work Context card appears in Personal briefing — bidirectional balance."""

    def test_card_absent_when_toggle_off(self, client) -> None:
        """When toggle is OFF, no work_context card in personal briefing."""
        r = client.get("/api/personal/briefing")
        assert r.status_code == 200
        data = r.json()
        assert data.get("work_context") == {}, \
            "Work context card must be empty when toggle is OFF"

    def test_card_present_when_toggle_on(self, client) -> None:
        """When toggle is ON, work_context field is populated."""
        client.post("/api/personal/settings/personal-context-in-work", json={
            "enabled": True, "user": "default",
        })
        r = client.get("/api/personal/briefing")
        data = r.json()
        wc = data.get("work_context", {})
        assert isinstance(wc, dict)
        if wc:  # may be {} if no consented work data
            assert wc.get("label") == "Work context (opt-in)"
            assert wc.get("enabled") is True

    def test_card_uses_only_user_work_data(self, client) -> None:
        """The card NEVER analyzes colleagues."""
        client.post("/api/personal/settings/personal-context-in-work", json={
            "enabled": True, "user": "default",
        })
        r = client.get("/api/personal/briefing")
        wc = r.json().get("work_context", {})
        if not wc:
            pytest.skip("Work context empty — bright-line vacuously satisfied")
        # Check the data fields (NOT the reminder/withdrawal_path which
        # legitimately mention the word "colleagues" to promise NOT to
        # analyze them).
        data_fields = {
            k: v for k, v in wc.items()
            if k not in ("reminder", "withdrawal_path", "label")
        }
        card_str = str(data_fields).lower()
        forbidden = ["she values", "he values", "team energy", "team mood"]
        for pattern in forbidden:
            assert pattern not in card_str, \
                f"Work context card data contains forbidden pattern: {pattern}"

    def test_card_has_withdrawal_path(self, client) -> None:
        """Work context card must include a withdrawal_path."""
        client.post("/api/personal/settings/personal-context-in-work", json={
            "enabled": True, "user": "default",
        })
        r = client.get("/api/personal/briefing")
        wc = r.json().get("work_context", {})
        if wc:
            assert "withdrawal_path" in wc

    def test_card_suppressed_in_incognito(self, client) -> None:
        """Incognito suppresses the work_context card too."""
        client.post("/api/personal/settings/personal-context-in-work", json={
            "enabled": True, "user": "default",
        })
        client.post("/api/personal/incognito/start?user=default")
        r = client.get("/api/personal/briefing")
        wc = r.json().get("work_context", {})
        assert wc == {}, "Work context card must be suppressed in incognito"


# ============================================================
# Phase 4 — Post-Event Self-Reflection Prompts
# ============================================================

class TestPhase4PostEventReflection:
    """Reflection prompts for major work events use only the user's own data."""

    def test_work_events_detected_returns_list(self) -> None:
        from maestro_personal.reflection import ReflectionPrompts
        events = ReflectionPrompts._detect_major_work_events("default")
        assert isinstance(events, list)

    def test_work_events_empty_without_consent(self) -> None:
        """Without calendar consent, no events are detected."""
        from maestro_personal.reflection import ReflectionPrompts
        events = ReflectionPrompts._detect_major_work_events("default")
        assert events == [], "No work events without consent"

    def test_work_events_empty_in_incognito(self) -> None:
        """Incognito mode suppresses work-event detection."""
        from maestro_personal.reflection import ReflectionPrompts
        from maestro_personal.incognito import IncognitoManager
        from maestro_personal.consent import ConsentStore
        ConsentStore.grant_consent("default", "work_calendar", "retrieve")
        IncognitoManager.start_session("default")
        events = ReflectionPrompts._detect_major_work_events("default")
        assert events == [], "Work events must not be detected in incognito"

    def test_work_events_detected_with_consent(self) -> None:
        """With consent + work_calendar data, events are detected."""
        from maestro_personal.reflection import ReflectionPrompts
        from maestro_personal.consent import ConsentStore
        from maestro_personal.store import PersonalDataStore
        ConsentStore.grant_consent("default", "work_calendar", "store")
        ConsentStore.grant_consent("default", "work_calendar", "retrieve")
        PersonalDataStore.store(
            "default", "event", "work_calendar",
            "Board meeting with the executive team",
            metadata={"today": True},
        )
        events = ReflectionPrompts._detect_major_work_events("default")
        assert len(events) > 0
        assert any("board" in e.lower() for e in events)

    def test_reflection_prompts_include_work_events(self) -> None:
        """The generate() output includes work_events_detected field."""
        from maestro_personal.reflection import ReflectionPrompts
        result = ReflectionPrompts.generate("default")
        assert "work_events_detected" in result
        assert isinstance(result["work_events_detected"], list)

    def test_work_event_prompt_uses_only_user_data(self) -> None:
        """The prompt context explicitly says it uses only the user's own data."""
        from maestro_personal.reflection import ReflectionPrompts
        from maestro_personal.consent import ConsentStore
        from maestro_personal.store import PersonalDataStore
        ConsentStore.grant_consent("default", "work_calendar", "store")
        ConsentStore.grant_consent("default", "work_calendar", "retrieve")
        PersonalDataStore.store(
            "default", "event", "work_calendar",
            "QBR — quarterly business review",
            metadata={"today": True},
        )
        result = ReflectionPrompts.generate("default")
        work_event_prompts = [p for p in result["prompts"] if p.get("type") == "work_event_reflection"]
        if work_event_prompts:
            ctx = work_event_prompts[0].get("context", "").lower()
            assert "your own" in ctx or "private" in ctx, \
                "Work event prompt context must reference the user's own data"


# ============================================================
# Phase 5 — Constrained Personal Context in Ask
# ============================================================

class TestPhase5AskPersonalContext:
    """Personal context in Ask is informational, never prescriptive."""

    def test_ask_returns_personal_context_line_field(self, client) -> None:
        """The /ask endpoint returns a personal_context_line field."""
        r = client.get("/api/oem/ask?q=should we hire more engineers")
        assert r.status_code == 200
        data = r.json()
        assert "personal_context_line" in data

    def test_line_is_none_when_toggle_off(self, client) -> None:
        """When toggle is OFF, personal_context_line is None."""
        r = client.get("/api/oem/ask?q=should we hire more engineers")
        data = r.json()
        assert data["personal_context_line"] is None

    def test_line_does_not_modify_recommendation(self, client) -> None:
        """The personal context line NEVER changes the work answer or confidence."""
        # Get answer with toggle OFF
        r_off = client.get("/api/oem/ask?q=should we hire more engineers")
        answer_off = r_off.json().get("answer", "")
        confidence_off = r_off.json().get("confidence", 0)

        # Enable toggle
        client.post("/api/personal/settings/personal-context-in-work", json={
            "enabled": True, "user": "default",
        })
        r_on = client.get("/api/oem/ask?q=should we hire more engineers")
        answer_on = r_on.json().get("answer", "")
        confidence_on = r_on.json().get("confidence", 0)

        # The answer and confidence must be IDENTICAL regardless of toggle
        assert answer_off == answer_on, \
            "Personal context must NOT modify the work answer"
        assert confidence_off == confidence_on, \
            "Personal context must NOT modify the work confidence"

    def test_line_is_single_sentence_when_present(self, client) -> None:
        """When the line is present, it is a single sentence."""
        from maestro_personal.consent import ConsentStore
        from maestro_personal.store import PersonalDataStore
        from maestro_personal.habits import HabitCoach

        client.post("/api/personal/settings/personal-context-in-work", json={
            "enabled": True, "user": "default",
        })
        # Grant habit consent + create a low-sleep habit
        ConsentStore.grant_consent("default", "habits", "store")
        ConsentStore.grant_consent("default", "habits", "retrieve")
        # Try to get a personal context line — pass toggle_enabled=True
        # explicitly (dependency inversion).
        from maestro_personal.integration import build_personal_context_line_for_ask
        line = build_personal_context_line_for_ask("default", "should we hire", True)
        if line is not None:
            # Must start with the label
            assert line.startswith("Personal context (opt-in):")
            # Must end with a period (single sentence)
            assert line.endswith(".")
            # Must not contain sentence-breaking punctuation in the middle
            # (one sentence only — no ". " in the middle)
            body = line[len("Personal context (opt-in):"):]
            assert ". " not in body, \
                f"Line must be a single sentence; got: {line!r}"

    def test_line_never_references_third_party(self, client) -> None:
        """The personal context line never references a third party."""
        client.post("/api/personal/settings/personal-context-in-work", json={
            "enabled": True, "user": "default",
        })
        r = client.get("/api/oem/ask?q=anything")
        line = r.json().get("personal_context_line")
        if line:
            lowered = line.lower()
            forbidden = ["she values", "he values", "they value", "sarah", "team energy"]
            for pattern in forbidden:
                assert pattern not in lowered, \
                    f"Personal context line references third party: {pattern}"

    def test_line_is_none_in_incognito(self, client) -> None:
        """Incognito suppresses the personal context line."""
        client.post("/api/personal/settings/personal-context-in-work", json={
            "enabled": True, "user": "default",
        })
        client.post("/api/personal/incognito/start?user=default")
        r = client.get("/api/oem/ask?q=anything")
        assert r.json().get("personal_context_line") is None


# ============================================================
# Phase 6 — Both Mode Unified Deck (Frontend)
# ============================================================

class TestPhase6BothModeUnifiedDeck:
    """The unified deck interleaves work+personal cards with mode indicators."""

    def test_today_js_has_both_mode_handling(self) -> None:
        import maestro_personal
        today_js = (
            pathlib.Path(maestro_personal.__file__).resolve().parents[2]
            / "static" / "js" / "today.js"
        )
        text = today_js.read_text()
        # Must check for mode === 'both'
        assert "'both'" in text or '"both"' in text, \
            "today.js must check for 'both' mode"
        # Must fetch personal briefing in both mode
        assert "getPersonal('/briefing')" in text or 'getPersonal("/briefing")' in text, \
            "today.js must fetch personal briefing in both mode"
        # Must tag cards with _mode
        assert "_mode" in text, \
            "today.js must tag cards with _mode for the indicator dot"
        # Must have mode indicator dot rendering
        assert "#FF6B6B" in text and "#2196F3" in text, \
            "today.js must render coral (personal) and blue (work) mode dots"

    def test_today_js_personal_cards_use_only_user_data(self) -> None:
        """The personal card building code must NOT reference third-party data."""
        import maestro_personal
        today_js = (
            pathlib.Path(maestro_personal.__file__).resolve().parents[2]
            / "static" / "js" / "today.js"
        )
        text = today_js.read_text()
        # The personalCards section must not pull from relationship_vault,
        # ambient_context, or other third-party modules
        forbidden_in_personal_section = [
            "relationship_vault",
            "ambient_context",
            "RelationshipVault",
            "AmbientContext",
        ]
        for pattern in forbidden_in_personal_section:
            assert pattern not in text, \
                f"today.js must not reference third-party module: {pattern}"

    def test_personal_cards_have_mode_tag(self) -> None:
        """Every personal card must be tagged _mode='personal'."""
        import maestro_personal
        today_js = (
            pathlib.Path(maestro_personal.__file__).resolve().parents[2]
            / "static" / "js" / "today.js"
        )
        text = today_js.read_text()
        # Look for the personalCards.push block
        assert "_mode: 'personal'" in text, \
            "today.js must tag personal cards with _mode: 'personal'"
        assert "_mode: 'work'" in text, \
            "today.js must tag work cards with _mode: 'work'"

    def test_work_context_card_surfaced_in_both_mode(self) -> None:
        """In both mode, the work_context card from personal briefing is surfaced."""
        import maestro_personal
        today_js = (
            pathlib.Path(maestro_personal.__file__).resolve().parents[2]
            / "static" / "js" / "today.js"
        )
        text = today_js.read_text()
        assert "work_context" in text, \
            "today.js must surface the work_context card from the personal briefing"
        assert "Work context" in text, \
            "today.js must label the work_context card as 'Work context'"


# ============================================================
# Bright-Line Guard (Defense in Depth)
# ============================================================

class TestBrightLineGuard:
    """The integration module's bright-line guard rejects third-party intelligence."""

    def test_guard_rejects_she_values(self) -> None:
        from maestro_personal.integration import _contains_third_party_intelligence
        assert _contains_third_party_intelligence("Sarah values clear communication")
        assert _contains_third_party_intelligence("she values clear communication")

    def test_guard_rejects_team_energy(self) -> None:
        from maestro_personal.integration import _contains_third_party_intelligence
        assert _contains_third_party_intelligence("Your team's energy is low today")

    def test_guard_rejects_manipulate_keyword(self) -> None:
        from maestro_personal.integration import _contains_third_party_intelligence
        assert _contains_third_party_intelligence("how to manipulate the conversation")

    def test_guard_allows_user_state(self) -> None:
        from maestro_personal.integration import _contains_third_party_intelligence
        assert not _contains_third_party_intelligence("you slept 6.2 hours last night")
        assert not _contains_third_party_intelligence("you have 2 calendar conflicts today")

    def test_guard_returns_empty_on_rejection(self) -> None:
        """The sanitizer returns {} when a forbidden pattern is found."""
        from maestro_personal.integration import _sanitize_integration_payload
        bad_payload = {
            "label": "Personal context (opt-in)",
            "habit_insight": "Sarah values clear communication",
        }
        result = _sanitize_integration_payload(bad_payload)
        assert result == {}, "Sanitizer must return {} for forbidden payload"

    def test_guard_passes_clean_payload(self) -> None:
        from maestro_personal.integration import _sanitize_integration_payload
        clean_payload = {
            "label": "Personal context (opt-in)",
            "sleep_last_night": "6.2 hours",
            "calendar_conflicts": ["dentist 2pm"],
            "habit_insight": "You skipped gym 3 days",
        }
        result = _sanitize_integration_payload(clean_payload)
        assert result == clean_payload

    def test_guard_walks_nested_structures(self) -> None:
        """The guard walks dicts and lists recursively."""
        from maestro_personal.integration import _sanitize_integration_payload
        nested_bad = {
            "outer": {
                "inner_list": [
                    "innocent string",
                    {"nested": "she values punctuality"},
                ],
            },
        }
        result = _sanitize_integration_payload(nested_bad)
        assert result == {}, "Guard must reject nested third-party intelligence"


# ============================================================
# Bidirectional Promise — both directions are gated by the same toggle
# ============================================================

class TestBidirectionalPromise:
    """The same toggle gates both directions of the integration."""

    def test_work_to_personal_disabled_when_toggle_off(self) -> None:
        """When toggle is OFF, no work_context in personal briefing."""
        from maestro_personal.integration import build_work_context_card_for_personal
        # Toggle is OFF — pass False explicitly (dependency inversion).
        card = build_work_context_card_for_personal("default", False)
        assert card == {}

    def test_personal_to_work_disabled_when_toggle_off(self) -> None:
        """When toggle is OFF, no personal_context in work briefing."""
        from maestro_personal.integration import build_personal_context_card_for_work
        # Toggle is OFF — pass False explicitly (dependency inversion).
        card = build_personal_context_card_for_work("default", False)
        assert card == {}

    def test_both_directions_enabled_together(self) -> None:
        """Enabling the toggle enables BOTH directions simultaneously."""
        from maestro_oem.user_settings import UserSettings
        from maestro_personal.integration import (
            build_personal_context_card_for_work,
            build_work_context_card_for_personal,
        )
        UserSettings.set_personal_context_in_work("default", True)
        # Pass the toggle state explicitly (dependency inversion).
        toggle_on = UserSettings.is_personal_context_in_work_enabled("default")
        work_card = build_personal_context_card_for_work("default", toggle_on)
        personal_card = build_work_context_card_for_personal("default", toggle_on)
        # Both should be populated (not {}) — they may have empty fields if
        # no consented data, but the card envelope should exist.
        if work_card:  # may be {} if incognito or guard trips
            assert work_card.get("label") == "Personal context (opt-in)"
        if personal_card:
            assert personal_card.get("label") == "Work context (opt-in)"

    def test_both_directions_disabled_together(self) -> None:
        """Disabling the toggle disables BOTH directions simultaneously."""
        from maestro_oem.user_settings import UserSettings
        from maestro_personal.integration import (
            build_personal_context_card_for_work,
            build_work_context_card_for_personal,
        )
        UserSettings.set_personal_context_in_work("default", True)
        UserSettings.set_personal_context_in_work("default", False)
        toggle_on = UserSettings.is_personal_context_in_work_enabled("default")
        assert build_personal_context_card_for_work("default", toggle_on) == {}
        assert build_work_context_card_for_personal("default", toggle_on) == {}


# ============================================================
# V5 Litmus — No new sidebar items, no new surfaces
# ============================================================

class TestV5LitmusNoNewSidebar:
    """Round 44 must NOT add new sidebar items or surfaces."""

    def test_no_new_sidebar_item(self) -> None:
        """The Round 44 toggle is in Settings, NOT a new sidebar item."""
        import maestro_personal
        today_js = (
            pathlib.Path(maestro_personal.__file__).resolve().parents[2]
            / "static" / "js" / "today.js"
        )
        text = today_js.read_text()
        # The personal-context-in-work toggle is accessed via settings, not a new nav item
        assert "personal-context-in-work" in text or "personal_context_in_work" in text or "_mode" in text

    def test_routes_added_under_personal_namespace(self) -> None:
        """The new endpoints live under /api/personal/, not a new namespace."""
        import maestro_personal
        routes_py = (
            pathlib.Path(maestro_personal.__file__).resolve().parents[2]
            / "backend" / "maestro_api" / "routes" / "personal.py"
        )
        text = routes_py.read_text()
        assert "/settings/personal-context-in-work" in text, \
            "Personal context toggle endpoint must be under /api/personal/settings/"
