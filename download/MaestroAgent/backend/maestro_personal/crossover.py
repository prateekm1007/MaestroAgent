"""
V8 Personal Mode — Phase 3-3: Professional-Personal Crossover.

Explicit merge with logging for contacts appearing in both Work and
Personal modes. Uses the dual-profile merge locking from Phase 1.

WITHDRAWAL PATH (Guideline P9):
The user could keep separate notes for work and personal contacts.
The crossover adds unified context; without it, the user switches
between two notebooks, which is slower but fully functional.
"""

from __future__ import annotations

import logging
from typing import Any

from maestro_personal.mode import ModeManager, Mode

logger = logging.getLogger(__name__)


class ProfessionalPersonalCrossover:
    """Manages contacts that appear in both Work and Personal modes.

    Uses the ModeManager's dual-profile system. A contact who is both
    a colleague and a friend gets TWO separate profiles. The user can
    explicitly merge them (logged, reversible for 30 days) to see
    unified context in BOTH mode.
    """

    @staticmethod
    def find_crossover_contacts() -> list[dict[str, Any]]:
        """Find contacts that exist in both Work and Personal modes.

        Returns contacts that have separate Work and Personal profiles
        but have NOT been merged.
        """
        # Collect all entity IDs from both modes
        all_entities: set[str] = set()
        for profiles in ModeManager._profiles.values():
            for p in profiles:
                all_entities.add(p.entity_id)

        crossover: list[dict[str, Any]] = []
        for entity_id in all_entities:
            if ModeManager.are_separated(entity_id):
                work_profile = ModeManager.get_profile(entity_id, Mode.WORK)
                personal_profile = ModeManager.get_profile(entity_id, Mode.PERSONAL)
                crossover.append({
                    "entity_id": entity_id,
                    "work_name": work_profile.name if work_profile else "",
                    "personal_name": personal_profile.name if personal_profile else "",
                    "work_context": work_profile.context if work_profile else "",
                    "personal_context": personal_profile.context if personal_profile else "",
                    "merged": False,
                })

        return crossover

    @staticmethod
    def merge_contact(
        entity_id: str, user_id: str = "user",
    ) -> dict[str, Any]:
        """Merge a contact's Work and Personal profiles.

        The merge is logged and reversible for 30 days (Gap 1 fix).
        """
        work_profile = ModeManager.get_profile(entity_id, Mode.WORK)
        personal_profile = ModeManager.get_profile(entity_id, Mode.PERSONAL)

        if not work_profile or not personal_profile:
            return {
                "merged": False,
                "reason": "Contact must exist in both Work and Personal modes to merge.",
            }

        merge = ModeManager.merge_profiles(
            entity_id=entity_id,
            work_profile_id=work_profile.entity_id,
            personal_profile_id=personal_profile.entity_id,
            merged_by=user_id,
        )

        return {
            "merged": True,
            "entity_id": entity_id,
            "merge_record": merge.to_dict(),
            "reversible_for_days": 30,
            "message": f"Merged Work and Personal profiles for {entity_id}. Reversible for 30 days.",
            "withdrawal_path": (
                "The user could keep separate notes for work and personal contacts. The crossover "
                "adds unified context; without it, the user switches between two notebooks, which "
                "is slower but fully functional."
            ),
        }

    @staticmethod
    def unmerge_contact(entity_id: str) -> dict[str, Any]:
        """Unmerge a contact's profiles (within the 30-day window)."""
        result = ModeManager.undo_merge(entity_id)
        return {
            "unmerged": result["reversed"],
            "entity_id": entity_id,
            "reason": result["reason"],
        }
