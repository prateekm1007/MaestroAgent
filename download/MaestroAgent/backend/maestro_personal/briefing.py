"""
V8 Personal Mode — Phase 2-1: Morning Personal Briefing.

Synthesizes the user's own data into a morning orientation:
- Today's personal calendar events (consent-gated)
- Weather (first-party API, consent-gated — stubbed for pilot)
- Reminders (user-entered, consent-gated)
- One personal nudge from the Contradictions engine (stubbed for now)

The briefing is opt-in: if the user has not consented to any personal
source, the briefing is empty with a friendly "Connect a source to get
started" message.

WITHDRAWAL PATH (Guideline P9):
The user could stop using the personal briefing and check their calendar
app and a weather app separately. The briefing saves 2-3 minutes of
app-switching; without it, the user is slightly less oriented but fully
functional. The feature does not create dependency — it aggregates
information the user would check anyway, just faster.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from maestro_personal.consent import ConsentStore
from maestro_personal.store import PersonalDataStore

logger = logging.getLogger(__name__)


class PersonalBriefingEngine:
    """Synthesizes the user's own data into a morning briefing.

    Every source access is consent-gated. If the user has not consented
    to a source, that source's data is simply omitted — no error, no
    crash, just empty. The briefing tells the user what they're missing
    and how to connect it.
    """

    # Sources the briefing can read (all require consent)
    SOURCES = [
        ("calendar", "retrieve", "Today's events"),
        ("reminders", "retrieve", "Your reminders"),
        ("weather", "retrieve", "Weather forecast"),
    ]

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        # Round 44 — the toggle state is injected by the caller (the
        # API route) via set_toggle_state(). This preserves namespace
        # separation: the personal namespace does not import the OEM
        # user-settings module.
        # Default: None (toggle not checked — caller must set it).
        self._toggle_enabled: bool | None = None

    def set_toggle_state(self, toggle_enabled: bool | None) -> None:
        """Inject the personal-context-in-work toggle state (Round 44).

        The caller (API route) checks the toggle via the OEM user-settings
        module and passes the state here. This preserves namespace
        separation: the personal namespace does not import the OEM module.

        Args:
            toggle_enabled: True if the user opted in to personal context
                in Work Mode. False if explicitly disabled. None if the
                caller has not checked (treated as False — fail safe).
        """
        self._toggle_enabled = toggle_enabled

    def generate(self) -> dict[str, Any]:
        """Generate the morning personal briefing.

        Returns:
            {
                items: list[{source, type, content, metadata}],
                missing_sources: list[str],  # sources without consent
                message: str,  # friendly summary
                generated_at: str,
                work_context: dict,  # Round 44 bidirectional card ({} when toggle OFF)
            }
        """
        items: list[dict[str, Any]] = []
        missing_sources: list[str] = []

        for source, purpose, label in self.SOURCES:
            if not ConsentStore.has_consent(self.user_id, source, purpose):
                missing_sources.append(f"{label} (connect {source})")
                continue

            try:
                source_items = PersonalDataStore.retrieve(self.user_id, source)
                for item in source_items:
                    items.append({
                        "source": source,
                        "type": item.item_type,
                        "content": item.content,
                        "metadata": item.metadata,
                        "timestamp": item.timestamp,
                    })
            except Exception as e:
                logger.debug("Briefing source %s failed: %s", source, e)
                missing_sources.append(f"{label} (error: {e})")

        # Build message
        if not items and not missing_sources:
            message = "Good morning! No data sources connected yet. Connect a source to get started."
        elif not items:
            message = f"Good morning! You have {len(missing_sources)} source(s) to connect: {', '.join(missing_sources)}."
        elif missing_sources:
            message = f"Good morning! {len(items)} item(s) today. Connect more sources for a fuller briefing: {', '.join(missing_sources)}."
        else:
            message = f"Good morning! {len(items)} item(s) today."

        # ─── Round 44: Work Context card (bidirectional balance) ───────
        # If personal state can appear in Work Mode, work commitments MUST
        # also appear in Personal Mode. This is the bidirectional promise.
        # Returns {} when the toggle is OFF (default), when incognito is
        # active, or when the bright-line guard trips. NEVER analyzes
        # colleagues — only the user's own work data.
        #
        # Dependency inversion: the toggle state was injected by the API
        # route via set_toggle_state(). The personal namespace does not
        # import the OEM user-settings module (preserves namespace separation).
        work_context_card: dict[str, Any] = {}
        try:
            from maestro_personal.integration import build_work_context_card_for_personal
            # Fail safe: if toggle state was never injected, treat as OFF.
            toggle_on = self._toggle_enabled is True
            work_context_card = build_work_context_card_for_personal(
                self.user_id, toggle_on,
            )
        except Exception as e:
            logger.debug("Work context card build failed: %s", e)

        return {
            "items": items,
            "missing_sources": missing_sources,
            "message": message,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            # Round 44 — bidirectional card. {} when toggle is OFF.
            "work_context": work_context_card,
        }
