"""
V8 Personal Mode — Mode Manager (Guideline P10).

Work Mode and Personal Mode are strictly partitioned. Cross-mode data
sharing requires explicit user action per item. A work colleague who is
also a friend gets TWO separate profiles — one in Work, one in Personal.
They are never merged without explicit user action, and the merge is logged.

Round 46 Amendment — One App, One Person:
The USER's mode is no longer stored as state. The user does not "switch
modes" — they open Maestro and see their whole life (work + personal)
interleaved by priority. The "mode" is a FILTER (a query parameter on
endpoints: ?filter=all|work|personal), not a stored state.

The dual-profile merge locking (Guideline P10) STILL holds — a contact
can still have separate work and personal profiles that require explicit
merging. That logic is unchanged. Only the USER's mode concept is
deprecated.

set_mode() and get_mode() are kept for backward compatibility but are
deprecated. New code should use the filter query parameter instead.
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


class Filter(str, Enum):
    """Round 46 — the filter replaces the stored mode.

    The filter is a VIEW parameter, not user state. It defaults to ALL
    (the user sees everything). The user can narrow to WORK or PERSONAL
    for focus, but the underlying data does not change.
    """
    ALL = "all"
    WORK = "work"
    PERSONAL = "personal"

    @classmethod
    def from_param(cls, value: str | None) -> "Filter":
        """Parse a filter query parameter. Defaults to ALL.

        Accepts: 'all', 'work', 'personal' (case-insensitive).
        Anything else (including None) defaults to ALL.
        """
        if not value:
            return cls.ALL
        try:
            return cls(value.lower())
        except ValueError:
            return cls.ALL


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
    """Manages strict Work/Personal mode separation for CONTACT profiles.

    A person who exists in both Work and Personal mode gets TWO separate
    profiles. They are NEVER merged without explicit user action.
    Every merge is logged.

    Round 46: The USER's mode (set_mode/get_mode) is DEPRECATED. The user
    does not have a stored mode — they have a view filter (the ?filter=
    query parameter). The contact-profile separation (create_profile,
    merge_profiles, undo_merge) is UNCHANGED — that is Guideline P10 and
    it still holds.
    """

    _profiles: dict[str, list[ModeProfile]] = {}  # entity_id → list of profiles (one per mode)
    _merges: list[MergeRecord] = []
    # Round 46: _current_mode is DEPRECATED. Kept for backward compat only.
    # New code should use the Filter query parameter, not stored mode.
    _current_mode: dict[str, Mode] = {}

    # ─── DEPRECATED: User mode state (Round 46) ──────────────────────
    # These methods are kept for backward compatibility but should not
    # be called by new code. The user's "mode" is now a view filter
    # (Filter enum + ?filter= query parameter), not a stored state.

    @classmethod
    def set_mode(cls, user_id: str, mode: Mode) -> None:
        """DEPRECATED (Round 46). Set the current mode for a user.

        New code should NOT call this. The user's "mode" is a view
        filter, not a stored state. Use the Filter enum and the ?filter=
        query parameter on endpoints instead.

        This method is kept for backward compatibility with existing
        callers (onboarding.js, mode-tabs.js) and will be removed once
        those callers are migrated.
        """
        import warnings
        warnings.warn(
            "ModeManager.set_mode() is deprecated (Round 46). The user's "
            "mode is now a view filter (?filter= query parameter), not a "
            "stored state. Use Filter.from_param() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        cls._current_mode[user_id] = mode
        logger.info("Mode set (DEPRECATED): user=%s mode=%s", user_id, mode.value)

    @classmethod
    def get_mode(cls, user_id: str) -> Mode:
        """DEPRECATED (Round 46). Get the current mode for a user.

        Returns Mode.BOTH by default (the unified experience). New code
        should use the Filter query parameter instead.
        """
        # Round 46: default to BOTH (unified) instead of WORK.
        # This makes existing callers see the unified experience by default.
        return cls._current_mode.get(user_id, Mode.BOTH)

    # ─── Contact profile separation (Guideline P10 — UNCHANGED) ──────

    @classmethod
    def create_profile(cls, entity_id: str, mode: Mode, name: str = "", context: str = "", notes: str = "") -> ModeProfile:
        """Create a profile for a person in a specific mode.

        If a profile already exists for this (entity_id, mode) pair,
        it is returned unchanged (idempotent).

        This is the contact-profile separation (Guideline P10). It is
        NOT affected by the Round 46 mode deprecation — contacts still
        get separate work and personal profiles until explicitly merged.
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
    def undo_merge(cls, merge_id: str) -> dict[str, Any]:
        """Reverse a merge within 30 days of the merge timestamp.

        After 30 days, the merge becomes permanent and cannot be reversed.
        This implements the 30-day reversibility window from the Round-37
        audit (Gap 1 fix).

        Returns:
            {reversed: bool, merge_id: str, reason: str}
        """
        from datetime import datetime, timedelta, timezone

        # Find the merge record
        merge = None
        for m in cls._merges:
            if m.entity_id == merge_id or f"{m.work_profile_id}:{m.personal_profile_id}" == merge_id:
                merge = m
                break

        if merge is None:
            return {"reversed": False, "merge_id": merge_id, "reason": "Merge not found."}

        # Check 30-day window
        try:
            merged_at = datetime.fromisoformat(merge.merged_at)
            if merged_at.tzinfo is None:
                merged_at = merged_at.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            if (now - merged_at) > timedelta(days=30):
                return {
                    "reversed": False,
                    "merge_id": merge_id,
                    "reason": f"Merge was created on {merge.merged_at}, which is more than 30 days ago. The merge is now permanent.",
                }
        except Exception:
            pass  # If we can't parse the timestamp, allow the undo

        # Reverse the merge: remove the merge record
        cls._merges = [m for m in cls._merges if m is not merge]
        logger.info("Merge reversed: entity=%s merge_id=%s", merge.entity_id, merge_id)
        return {
            "reversed": True,
            "merge_id": merge_id,
            "entity_id": merge.entity_id,
            "reason": "Merge reversed successfully. Work and Personal profiles are now separate again.",
        }

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
