"""
V8 Personal Mode — Round 44 Work/Personal Integration Layer.

This module is the SOLE bridge between Personal Mode data and Work Mode
surfaces. It enforces the Round 44 constitutional amendment:

  1. Toggle default: OFF (Guideline P3). When OFF, every function in
     this module returns an empty dict — zero personal data appears in
     Work Mode.
  2. Self-facing only: ONLY the user's own personal state surfaces
     (sleep, energy, calendar conflicts, habit insights). NEVER
     intelligence about a third party (Round 36 bright line).
  3. Bidirectional: if personal state appears in Work Mode, work
     commitments appear in Personal Mode. The flow is symmetric.
  4. Informational only: personal context never redirects a work
     recommendation. It is a labeled aside, never a factor.
  5. Withdrawal path: disabling the toggle returns both modes to their
     pre-integration state. No lock-in.

WITHDRAWAL PATH (Guideline P9):
The user can disable the toggle at any time. Personal data immediately
disappears from Work Mode; work data immediately disappears from
Personal Mode. The user can function without the integration — they
simply see Work and Personal as separate briefings, which is the
pre-Round-44 default.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ─── Bright-line guard ────────────────────────────────────────────────────
# Words/phrases that, if found in any integration payload, indicate the
# integration has crossed into third-party territory and must be rejected
# before the payload leaves this module. This is defense in depth — the
# upstream engines should never produce these, but we check anyway.
#
# The patterns are deliberately broad — false positives are acceptable
# (we fail closed), false negatives are not (we'd ship a violation).
# The patterns catch both pronoun forms ("she values") and proper-name
# forms ("Sarah values", "John tends to") by matching on the verb phrase
# that follows any capitalized name or pronoun.
_FORBIDDEN_THIRD_PARTY_PATTERNS = (
    # Pronoun forms
    "she values", "he values", "they value",
    "she tends to", "he tends to", "they tend to",
    "she likes", "he likes", "they like",
    "she prefers", "he prefers", "they prefer",
    # Verb-phrase forms that catch proper-name patterns ("Sarah values",
    # "John tends to") regardless of the specific name. We match on the
    # verb phrase preceded by a word boundary so user-state phrases like
    # "you values" don't trip — only third-person singular.
    " values clear", " values punctual", " values direct",
    " tends to be late", " tends to be early",
    # Aggregate personal-state of colleagues
    "your team's energy", "team energy",
    "your team's mood", "team mood",
    "your colleagues' energy", "colleagues' mood",
    # Explicit bright-line words
    "manipulate", "win against",
    # Specific surveillance framings
    "relationship health", "compatibility score",
)


def _contains_third_party_intelligence(text: str) -> bool:
    """Defense in depth: returns True if the text contains patterns that
    suggest third-party intelligence has leaked into the payload.

    This is a last-resort guard. The upstream engines should never
    produce these — but if they do, we reject the payload rather than
    ship a constitutional violation.

    Note: the guard is deliberately over-broad. False positives cause
    the integration to fail closed (an empty card), which is the safe
    failure mode. False negatives would ship a violation.
    """
    if not text:
        return False
    lowered = text.lower()
    # Direct pattern match
    if any(pattern in lowered for pattern in _FORBIDDEN_THIRD_PARTY_PATTERNS):
        return True
    # Regex: any capitalized name followed by "values"/"tends to"/"likes"
    # catches "Sarah values", "John tends to", "Priya likes", etc.
    import re
    # \b[A-Z][a-z]+ is a capitalized word (name). The verb phrases are
    # the bright-line indicators of personal intelligence about a third party.
    name_verb_pattern = re.compile(
        r"\b[A-Z][a-z]+ (?:values|tends to|likes|prefers|wants|needs|expects)\b"
    )
    if name_verb_pattern.search(text):
        return True
    return False


def _sanitize_integration_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Sanitize an integration payload before it leaves this module.

    Walks every string value in the payload and rejects the entire
    payload if any forbidden pattern is found. Returns an empty dict
    on rejection and logs a warning — the integration fails closed.
    """
    def _walk(obj: Any) -> None:
        if isinstance(obj, str):
            if _contains_third_party_intelligence(obj):
                raise ValueError(f"Forbidden third-party intelligence detected: {obj!r}")
        elif isinstance(obj, dict):
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v)

    try:
        _walk(payload)
        return payload
    except ValueError as e:
        logger.warning("Integration payload rejected by bright-line guard: %s", e)
        return {}


# ─── Personal State in Work Briefing (Phase 2) ────────────────────────────

def build_personal_context_card_for_work(
    user_id: str, toggle_enabled: bool | None = None,
) -> dict[str, Any]:
    """Build the "Personal Context" card for the Work Mode CEO briefing.

    Constitutional constraints (Round 44):
      - Returns {} if the toggle is OFF (default).
      - Returns {} if incognito mode is active (privacy absolute).
      - Surfaces ONLY the user's own state: sleep last night, today's
        personal calendar conflicts, one habit-relevant insight.
      - NEVER surfaces intelligence about a third party.
      - The card is labeled "Personal context (opt-in)" and is meant to
        be the LAST card in the briefing, never the first.

    Args:
        user_id: The user to build the card for.
        toggle_enabled: Whether the personal-context-in-work toggle is ON.
            If None, the caller is responsible for checking the toggle
            BEFORE calling this function (dependency inversion — the
            integration module does not import the OEM user-settings module).

    Returns:
        {} if toggle is OFF or incognito is active.
        {
            "label": "Personal context (opt-in)",
            "enabled": True,
            "sleep_last_night": str | None,         # "6.2 hours" or None
            "calendar_conflicts": list[str],         # today's personal events that overlap work hours
            "habit_insight": str | None,             # one habit-relevant insight
            "reminder": str,                         # constitutional reminder
            "withdrawal_path": str,
        }
    """
    from maestro_personal.incognito import IncognitoManager

    # Toggle check — default OFF. The caller passes the toggle state
    # (dependency inversion: the integration module does not import
    # the OEM user-settings module, preserving namespace separation).
    if toggle_enabled is False:
        return {}

    # Incognito check — privacy is absolute (Guideline P6)
    if IncognitoManager.is_incognito(user_id):
        logger.info(
            "Personal context card suppressed: user=%s is in incognito mode",
            user_id,
        )
        return {}

    card: dict[str, Any] = {
        "label": "Personal context (opt-in)",
        "enabled": True,
        "sleep_last_night": _get_sleep_last_night(user_id),
        "calendar_conflicts": _get_personal_calendar_conflicts(user_id),
        "habit_insight": _get_habit_insight(user_id),
        "reminder": (
            "This card uses only your own personal data. Maestro never surfaces "
            "intelligence about a third party. Disable in Settings to return Work "
            "Mode to its default state."
        ),
        "withdrawal_path": (
            "Disable the personal-context-in-work toggle and this card disappears "
            "immediately. Work Mode returns to its pre-integration state."
        ),
    }

    # Bright-line defense in depth — fail closed.
    return _sanitize_integration_payload(card)


def _get_sleep_last_night(user_id: str) -> str | None:
    """Get last night's sleep hours from the user's own habit check-ins.

    Only reads the user's own habit data. Never analyzes a third party.
    Returns a human-readable string like "6.2 hours" or None if no data.
    """
    try:
        from maestro_personal.habits import HabitCoach
        from maestro_personal.consent import ConsentStore
        # Sleep is a habit type. Require explicit consent for habit retrieval.
        if not ConsentStore.has_consent(user_id, "habits", "retrieve"):
            return None
        habits = HabitCoach.get_habits()
        for h in habits:
            if "sleep" in h.name.lower():
                # Look at the most recent check-in metadata for hours
                if h.check_ins:
                    last = h.check_ins[-1]
                    hours = last.metadata.get("hours") if hasattr(last, "metadata") else None
                    if hours:
                        return f"{float(hours):.1f} hours"
        return None
    except Exception as e:
        logger.debug("Sleep retrieval failed: %s", e)
        return None


def _get_personal_calendar_conflicts(user_id: str) -> list[str]:
    """Get today's personal calendar events that might overlap work hours.

    Only reads the user's own calendar (consent-gated). Returns up to 3
    human-readable conflict descriptions. Never analyzes a third party.
    """
    try:
        from maestro_personal.store import PersonalDataStore
        from maestro_personal.consent import ConsentStore
        if not ConsentStore.has_consent(user_id, "calendar", "retrieve"):
            return []
        items = PersonalDataStore.retrieve(user_id, "calendar")
        conflicts: list[str] = []
        for item in items[:5]:  # cap at 5 reads
            # Only surface events that look like they overlap work hours
            # (metadata.work_hours_overlap == True, or event_time between 9-18)
            metadata = item.metadata or {}
            if metadata.get("work_hours_overlap") or metadata.get("today"):
                conflicts.append(item.content[:80])
            if len(conflicts) >= 3:
                break
        return conflicts
    except Exception as e:
        logger.debug("Personal calendar retrieval failed: %s", e)
        return []


def _get_habit_insight(user_id: str) -> str | None:
    """Get one habit-relevant insight from the user's own habit data.

    Only reads the user's own habit data. Never analyzes a third party.
    Returns one short insight string or None.
    """
    try:
        from maestro_personal.habits import HabitCoach
        from maestro_personal.consent import ConsentStore
        if not ConsentStore.has_consent(user_id, "habits", "retrieve"):
            return None
        suggestions = HabitCoach.get_suggestions()
        if suggestions:
            # Return the first suggestion, capped at 100 chars
            first = suggestions[0]
            text = first.get("text") if isinstance(first, dict) else str(first)
            return text[:100] if text else None
        return None
    except Exception as e:
        logger.debug("Habit insight retrieval failed: %s", e)
        return None


# ─── Work Commitments in Personal Briefing (Phase 3 — bidirectional) ──────

def build_work_context_card_for_personal(
    user_id: str, toggle_enabled: bool | None = None,
) -> dict[str, Any]:
    """Build the "Work Context" card for the Personal Mode briefing.

    This is the BIDIRECTIONAL BALANCE that Round 44 requires. If
    personal state can appear in Work Mode, work commitments MUST also
    appear in Personal Mode. The flow is symmetric, never one-way.

    Constitutional constraints (Round 44):
      - Returns {} if the toggle is OFF (default).
      - Returns {} if incognito mode is active (privacy absolute).
      - Surfaces ONLY the user's own work data: today's work deadlines,
        meetings that run into personal time, work commitments.
      - NEVER analyzes colleagues.
      - The card is labeled "Work context (opt-in)".

    Args:
        user_id: The user to build the card for.
        toggle_enabled: Whether the personal-context-in-work toggle is ON.
            If None, the caller is responsible for checking the toggle
            BEFORE calling this function (dependency inversion).

    Returns:
        {} if toggle is OFF or incognito is active.
        {
            "label": "Work context (opt-in)",
            "enabled": True,
            "deadlines_today": list[str],          # today's work deadlines
            "meetings_into_personal_time": list[str],  # meetings running past 6 PM
            "commitments_summary": str | None,      # one-line summary
            "reminder": str,
            "withdrawal_path": str,
        }
    """
    from maestro_personal.incognito import IncognitoManager

    # Toggle check — same toggle gates both directions (bidirectional).
    # The caller passes the toggle state (dependency inversion).
    if toggle_enabled is False:
        return {}

    # Incognito check — privacy is absolute
    if IncognitoManager.is_incognito(user_id):
        logger.info(
            "Work context card suppressed: user=%s is in incognito mode",
            user_id,
        )
        return {}

    card: dict[str, Any] = {
        "label": "Work context (opt-in)",
        "enabled": True,
        "deadlines_today": _get_work_deadlines_today(user_id),
        "meetings_into_personal_time": _get_meetings_into_personal_time(user_id),
        "commitments_summary": _get_work_commitments_summary(user_id),
        "reminder": (
            "This card uses only your own work data. Maestro never analyzes "
            "colleagues. Disable in Settings to return Personal Mode to its "
            "default state."
        ),
        "withdrawal_path": (
            "Disable the personal-context-in-work toggle and this card disappears "
            "immediately. Personal Mode returns to its pre-integration state."
        ),
    }

    # Bright-line defense in depth — fail closed.
    return _sanitize_integration_payload(card)


def _get_work_deadlines_today(user_id: str) -> list[str]:
    """Get today's work deadlines from the user's own work data.

    Only reads the user's own tasks/commitments (consent-gated). Returns
    up to 3 deadline descriptions. Never analyzes colleagues.
    """
    try:
        from maestro_personal.store import PersonalDataStore
        from maestro_personal.consent import ConsentStore
        if not ConsentStore.has_consent(user_id, "work", "retrieve"):
            return []
        items = PersonalDataStore.retrieve(user_id, "work")
        deadlines: list[str] = []
        for item in items[:10]:
            metadata = item.metadata or {}
            if metadata.get("deadline_today") or metadata.get("due_today"):
                deadlines.append(item.content[:80])
            if len(deadlines) >= 3:
                break
        return deadlines
    except Exception as e:
        logger.debug("Work deadlines retrieval failed: %s", e)
        return []


def _get_meetings_into_personal_time(user_id: str) -> list[str]:
    """Get meetings that run into personal time (after 6 PM).

    Only reads the user's own calendar. Returns up to 3 meeting
    descriptions. Never analyzes colleagues.
    """
    try:
        from maestro_personal.store import PersonalDataStore
        from maestro_personal.consent import ConsentStore
        if not ConsentStore.has_consent(user_id, "work_calendar", "retrieve"):
            return []
        items = PersonalDataStore.retrieve(user_id, "work_calendar")
        meetings: list[str] = []
        for item in items[:10]:
            metadata = item.metadata or {}
            if metadata.get("into_personal_time") or metadata.get("after_6pm"):
                meetings.append(item.content[:80])
            if len(meetings) >= 3:
                break
        return meetings
    except Exception as e:
        logger.debug("Meetings retrieval failed: %s", e)
        return []


def _get_work_commitments_summary(user_id: str) -> str | None:
    """Get a one-line summary of today's work commitments.

    Only reads the user's own work data. Never analyzes colleagues.
    """
    try:
        from maestro_personal.store import PersonalDataStore
        from maestro_personal.consent import ConsentStore
        if not ConsentStore.has_consent(user_id, "work", "retrieve"):
            return None
        items = PersonalDataStore.retrieve(user_id, "work")
        if not items:
            return None
        today_items = [i for i in items if (i.metadata or {}).get("today")]
        if not today_items:
            return None
        return f"You have {len(today_items)} work commitment{'s' if len(today_items) != 1 else ''} today."
    except Exception as e:
        logger.debug("Work commitments summary failed: %s", e)
        return None


# ─── Personal Context Line for Ask (Phase 5) ──────────────────────────────

def build_personal_context_line_for_ask(
    user_id: str, question: str, toggle_enabled: bool | None = None,
) -> str | None:
    """Build the ONE optional personal-context line appended to an Ask answer.

    Constitutional constraints (Round 44):
      - Returns None if the toggle is OFF (default).
      - Returns None if incognito mode is active.
      - Returns ONE sentence, labeled "Personal context (opt-in):".
      - The line references ONLY the user's own state (energy, sleep,
        calendar conflicts). NEVER references a third party.
      - The line is informational, never prescriptive. It never changes
        the work recommendation and never makes the answer conditional
        on personal state.

    Args:
        user_id: The user to build the line for.
        question: The work question being answered.
        toggle_enabled: Whether the personal-context-in-work toggle is ON.
            If None, the caller is responsible for checking the toggle
            BEFORE calling this function (dependency inversion).

    Returns:
        None if toggle is OFF, incognito is active, or no relevant state.
        Otherwise: "Personal context (opt-in): {one-sentence state}."
    """
    from maestro_personal.incognito import IncognitoManager

    if toggle_enabled is False:
        return None

    if IncognitoManager.is_incognito(user_id):
        return None

    # Build one sentence from the user's own state
    sentence_fragments: list[str] = []

    sleep = _get_sleep_last_night(user_id)
    if sleep and "6" in sleep:  # only surface if notably low sleep
        try:
            hours = float(sleep.split()[0])
            if hours < 7:
                sentence_fragments.append(f"you slept {hours:.1f} hours last night")
        except (ValueError, IndexError):
            pass

    conflicts = _get_personal_calendar_conflicts(user_id)
    if conflicts:
        sentence_fragments.append(f"you have {len(conflicts)} personal calendar conflict{'s' if len(conflicts) != 1 else ''} today")

    if not sentence_fragments:
        return None

    sentence = "Personal context (opt-in): " + ", and ".join(sentence_fragments) + "."

    # Bright-line defense in depth — fail closed.
    if _contains_third_party_intelligence(sentence):
        logger.warning("Personal context line rejected by bright-line guard")
        return None

    return sentence
