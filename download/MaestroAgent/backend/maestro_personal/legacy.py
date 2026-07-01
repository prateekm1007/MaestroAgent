"""
V8 Personal Mode — Phase 2-13: Legacy Builder.

Helps the user document life stories, values, and wisdom in a
structured way. Private, user-controlled. Exportable, deletable,
never shared without explicit action.

WITHDRAWAL PATH (Guideline P9):
The user could write their legacy in a paper journal or a word
processor. The tool adds structure and searchability; without it,
the user relies on their own organization, which is slower but
fully functional.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class LegacyEntry:
    """A single legacy entry — a life story, value, or wisdom."""
    entry_id: str = field(default_factory=lambda: str(uuid4()))
    entry_type: str = ""  # "story", "value", "wisdom", "lesson"
    title: str = ""
    content: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    private: bool = True  # always private by default

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "entry_type": self.entry_type,
            "title": self.title,
            "content": self.content,
            "created_at": self.created_at,
            "private": self.private,
        }


class LegacyBuilder:
    """Helps the user document their legacy — private, exportable, deletable.

    No sharing, no social features. Entries are private by default.
    The user can export the document as text. Entries can be deleted
    individually or all at once.
    """

    _entries: dict[str, LegacyEntry] = {}

    # Prompt templates by entry type
    _PROMPTS = {
        "story": [
            "What did you learn from your first job?",
            "Tell the story of a time you failed and what it taught you.",
            "What was the most important decision of your life?",
            "Describe a moment that changed your perspective.",
        ],
        "value": [
            "What do you value most in relationships?",
            "What principle do you try to live by?",
            "What would you never compromise on?",
        ],
        "wisdom": [
            "What do you want your grandchildren to know about you?",
            "What advice would you give your younger self?",
            "What took you decades to understand?",
        ],
        "lesson": [
            "What did a difficult person teach you?",
            "What did success teach you that failure didn't?",
            "What would you do differently if you could start over?",
        ],
    }

    @classmethod
    def add_entry(cls, entry_type: str, title: str, content: str) -> LegacyEntry:
        """Add a legacy entry. Always private."""
        entry = LegacyEntry(
            entry_type=entry_type,
            title=title,
            content=content,
            private=True,
        )
        cls._entries[entry.entry_id] = entry
        logger.info("Legacy entry added: %s (%s)", title, entry_type)
        return entry

    @classmethod
    def get_entry(cls, entry_id: str) -> LegacyEntry | None:
        return cls._entries.get(entry_id)

    @classmethod
    def get_all_entries(cls) -> list[LegacyEntry]:
        return list(cls._entries.values())

    @classmethod
    def delete_entry(cls, entry_id: str) -> bool:
        """Delete a single entry."""
        if entry_id in cls._entries:
            del cls._entries[entry_id]
            return True
        return False

    @classmethod
    def delete_all(cls) -> int:
        """Delete all entries. Returns count deleted."""
        count = len(cls._entries)
        cls._entries = {}
        return count

    @classmethod
    def export_document(cls) -> dict[str, Any]:
        """Export the legacy document as structured text.

        Returns a structured document that can be saved to a file.
        """
        entries = cls.get_all_entries()
        sections: dict[str, list[str]] = {}
        for entry in entries:
            sections.setdefault(entry.entry_type, []).append(
                f"### {entry.title}\n\n{entry.content}\n"
            )

        document_parts = ["# My Legacy\n"]
        type_labels = {
            "story": "Life Stories",
            "value": "Values",
            "wisdom": "Wisdom",
            "lesson": "Lessons Learned",
        }
        for entry_type, label in type_labels.items():
            if entry_type in sections:
                document_parts.append(f"\n## {label}\n")
                document_parts.extend(sections[entry_type])

        return {
            "document": "\n".join(document_parts),
            "entry_count": len(entries),
            "format": "markdown",
            "withdrawal_path": (
                "The user could write their legacy in a paper journal or a word processor. "
                "The tool adds structure and searchability; without it, the user relies on "
                "their own organization, which is slower but fully functional."
            ),
        }

    @classmethod
    def get_prompts(cls, entry_type: str = "") -> list[str]:
        """Get writing prompts for a specific entry type, or all."""
        if entry_type and entry_type in cls._PROMPTS:
            return cls._PROMPTS[entry_type]
        all_prompts: list[str] = []
        for prompts in cls._PROMPTS.values():
            all_prompts.extend(prompts)
        return all_prompts

    @classmethod
    def clear(cls) -> None:
        cls._entries = {}
