"""
V8 Personal Mode — Mode Manager (Guideline P10).

Work Mode and Personal Mode are strictly partitioned. Cross-mode data
sharing requires explicit user action per item. A work colleague who is
also a friend gets TWO separate profiles — one in Work, one in Personal.
They are never merged without explicit user action, and the merge is logged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class Mode(str, Enum):
    WORK = "work"
    PERSONAL = "personal"
    BOTH = "both"  # shows both, but data stays partitioned


@dataclass
class ModeProfile:
    """A person's profile in a specific mode (Work or Personal)."""
    entity_id: str  # email or ID
    mode: Mode
    name: str = ""
    context: str = ""  # "colleague", "friend", "family", etc.
    notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "mode": self.mode.value,
            "name": self.name,
            "context": self.context,
            "notes": self.notes,
            "created_at": self.created_at,
        }


@dataclass
class MergeRecord:
    """A logged merge of two mode profiles for the same entity."""
    entity_id: str
    work_profile_id: str
    personal_profile_id: str
    merged_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    merged_by: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "work_profile_id": self.work_profile_id,
            "personal_profile_id": self.personal_profile_id,
            "merged_at": self.merged_at,
            "merged_by": self.merged_by,
        }


class ModeManager:
    """Manages strict Work/Personal mode separation.

    A person who exists in both Work and Personal mode gets TWO separate
    profiles. They are NEVER merged without explicit user action.
    Every merge is logged.
    """

    _profiles: dict[str, list[ModeProfile]] = {}  # entity_id → list of profiles (one per mode)
    _merges: list[MergeRecord] = []
    _current_mode: dict[str, Mode] = {}  # user_id → current mode

    @classmethod
    def set_mode(cls, user_id: str, mode: Mode) -> None:
        """Set the current mode for a user."""
        cls._current_mode[user_id] = mode
        logger.info("Mode set: user=%s mode=%s", user_id, mode.value)

    @classmethod
    def get_mode(cls, user_id: str) -> Mode:
        """Get the current mode for a user. Default: WORK."""
        return cls._current_mode.get(user_id, Mode.WORK)

    @classmethod
    def create_profile(cls, entity_id: str, mode: Mode, name: str = "", context: str = "", notes: str = "") -> ModeProfile:
        """Create a profile for a person in a specific mode.

        If a profile already exists for this (entity_id, mode) pair,
        it is returned unchanged (idempotent).
        """
        if entity_id not in cls._profiles:
            cls._profiles[entity_id] = []
        # Check if a profile already exists for this mode
        for p in cls._profiles[entity_id]:
            if p.mode == mode:
                return p
        profile = ModeProfile(
            entity_id=entity_id, mode=mode, name=name,
            context=context, notes=notes,
        )
        cls._profiles[entity_id].append(profile)
        logger.info("Profile created: entity=%s mode=%s", entity_id, mode.value)
        return profile

    @classmethod
    def get_profiles(cls, entity_id: str) -> list[ModeProfile]:
        """Get all profiles for an entity (may be multiple — one per mode)."""
        return cls._profiles.get(entity_id, [])

    @classmethod
    def get_profile(cls, entity_id: str, mode: Mode) -> ModeProfile | None:
        """Get the profile for an entity in a specific mode."""
        for p in cls.get_profiles(entity_id):
            if p.mode == mode:
                return p
        return None

    @classmethod
    def are_separated(cls, entity_id: str) -> bool:
        """Check if an entity has separate Work and Personal profiles."""
        profiles = cls.get_profiles(entity_id)
        has_work = any(p.mode == Mode.WORK for p in profiles)
        has_personal = any(p.mode == Mode.PERSONAL for p in profiles)
        return has_work and has_personal

    @classmethod
    def merge_profiles(
        cls, entity_id: str, work_profile_id: str, personal_profile_id: str, merged_by: str = "",
    ) -> MergeRecord:
        """Merge two mode profiles for the same entity.

        This is the ONLY way to link Work and Personal profiles. The
        merge is logged. The profiles remain separate but are linked
        so the user can see both when in BOTH mode.
        """
        record = MergeRecord(
            entity_id=entity_id,
            work_profile_id=work_profile_id,
            personal_profile_id=personal_profile_id,
            merged_by=merged_by,
        )
        cls._merges.append(record)
        logger.info("Profiles merged: entity=%s by=%s", entity_id, merged_by)
        return record

    @classmethod
    def get_merges(cls) -> list[MergeRecord]:
        """Get all merge records (audit trail)."""
        return cls._merges

    @classmethod
    def clear(cls) -> None:
        """Clear all profiles and merges (for testing)."""
        cls._profiles = {}
        cls._merges = []
        cls._current_mode = {}
