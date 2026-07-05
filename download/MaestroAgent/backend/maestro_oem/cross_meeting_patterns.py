"""Loop 2 — Cross-Meeting Pattern Detection.

CEO directive (auditor recommendation, CEO-validated): "Builds naturally
on Loop 1 (commitments surface in meetings, meetings have preparation,
preparation has recall)."

A single meeting is a data point. A pattern across meetings is a signal.
If pricing comes up in 3 meetings with <customer>, that's a pattern — Maestro
connects meetings into a narrative, not just a list.

The CrossMeetingPatternDetector:
  - Takes a list of meetings (all with topics_discussed populated)
  - Counts topic frequency across meetings for each entity
  - Returns CrossMeetingPattern objects for topics that appear in
    >= min_meetings meetings (default: 2)

A pattern includes:
  - topic: the recurring topic ("pricing")
  - entity: the entity it recurs for ("<customer>")
  - meeting_count: how many meetings discussed it (3)
  - meeting_titles: the titles of those meetings (for the narrative)
  - description: a human-readable sentence ("pricing has come up in 3
    meetings with <customer>: Review #1, Review #2, Review #3.")

This is the difference between "you have 3 meetings" and "you have 3
meetings about the same thing — this is a pattern, not a coincidence."
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CrossMeetingPattern:
    """A detected pattern across multiple meetings.

    Attributes:
        topic: The recurring topic ("pricing")
        entity: The entity it recurs for ("<customer>")
        meeting_count: How many meetings discussed it
        meeting_titles: The titles of those meetings (for the narrative)
        description: A human-readable sentence about the pattern
    """

    topic: str
    entity: str
    meeting_count: int
    meeting_titles: list[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "entity": self.entity,
            "meeting_count": self.meeting_count,
            "meeting_titles": list(self.meeting_titles),
            "description": self.description,
        }


class CrossMeetingPatternDetector:
    """Detect patterns across multiple meetings.

    Usage:
        detector = CrossMeetingPatternDetector()
        patterns = detector.detect(meetings, min_meetings=2)
    """

    # Ordinal lookup for human-readable frequency
    _ORDINALS = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth"}

    def detect(
        self,
        meetings: list,
        min_meetings: int = 2,
    ) -> list[CrossMeetingPattern]:
        """Detect cross-meeting patterns.

        Args:
            meetings: List of Meeting objects (each with topics_discussed populated)
            min_meetings: Minimum number of meetings for a topic to be a pattern

        Returns:
            List of CrossMeetingPattern objects, sorted by meeting_count descending.
        """
        if not meetings or min_meetings < 2:
            return []

        # Build a map: (entity, topic) → list of meeting titles
        pattern_map: dict[tuple[str, str], list[str]] = {}
        for meeting in meetings:
            try:
                entity = getattr(meeting, "entity", "")
                topics = getattr(meeting, "topics_discussed", []) or []
                title = getattr(meeting, "title", "Untitled")
                for topic in topics:
                    key = (entity, topic.lower())
                    if key not in pattern_map:
                        pattern_map[key] = []
                    pattern_map[key].append(title)
            except Exception:
                continue

        # Filter to patterns meeting the threshold
        patterns: list[CrossMeetingPattern] = []
        for (entity, topic), titles in pattern_map.items():
            if len(titles) >= min_meetings:
                count = len(titles)
                ordinal = self._ORDINALS.get(count, str(count))
                # Build the description
                if count <= 5:
                    titles_str = ", ".join(titles)
                else:
                    titles_str = ", ".join(titles[:3]) + f", and {count - 3} more"
                description = (
                    f"{topic} has come up in {count} meetings with {entity} "
                    f"({titles_str}). This is the {ordinal} time — this is a "
                    f"pattern, not a coincidence."
                )
                patterns.append(CrossMeetingPattern(
                    topic=topic,
                    entity=entity,
                    meeting_count=count,
                    meeting_titles=list(titles),
                    description=description,
                ))

        # Sort by meeting_count descending (most frequent patterns first)
        patterns.sort(key=lambda p: p.meeting_count, reverse=True)
        return patterns
