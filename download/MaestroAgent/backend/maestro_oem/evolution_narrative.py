"""
V6 Spec #6 — Evolution Narrative: the organization's autobiography.

"Your organization started fast but fragile. It learned that review
produces better outcomes."

Composes DNA + Evolution Tracker + Identity + Principles into chapters.
Each chapter has: title, period, narrative, lessons.

Command-palette only (NOT in sidebar — sidebar stays at 4).

API: GET /api/oem/autobiography
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class EvolutionNarrative:
    """Write the organization's autobiography.

    The autobiography is not a timeline of events. It's a story of how
    the organization changed — what it was, what it learned, what it
    became. Each chapter covers a period of evolution.
    """

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def write(self) -> dict[str, Any]:
        """Write the organization's autobiography."""
        chapters = []

        # Chapter 1: Who you are now
        chapters.append(self._chapter_identity())

        # Chapter 2: What you've learned
        chapters.append(self._chapter_learning())

        # Chapter 3: What you've stopped doing
        chapters.append(self._chapter_mistakes())

        # Chapter 4: What you've earned the right to trust
        chapters.append(self._chapter_principles())

        # Chapter 5: Where you're heading
        chapters.append(self._chapter_trajectory())

        # Generate the overarching narrative
        narrative = self._overarching_narrative(chapters)

        return {
            "chapters": chapters,
            "narrative": narrative,
            "summary": narrative[:120] + "..." if len(narrative) > 120 else narrative,
            "chapter_count": len(chapters),
        }

    def _chapter_identity(self) -> dict[str, Any]:
        """Chapter: Who you are now."""
        try:
            from maestro_oem.identity import IdentityEngine
            engine = IdentityEngine(self.model, self.signals)
            identity = engine.compute()
            summary = identity.get("summary", "Your organization is still discovering who it is.")
            return {
                "title": "Who you are",
                "period": "now",
                "narrative": summary,
                "lessons": [identity.get("largest_gap", "The organization is still learning about itself.")],
            }
        except Exception:
            return {"title": "Who you are", "period": "now", "narrative": "Still discovering.", "lessons": []}

    def _chapter_learning(self) -> dict[str, Any]:
        """Chapter: What you've learned."""
        try:
            laws = list(self.model.laws.values())
            validated = sum(1 for l in laws if l.status and l.status.value == "validated")
            total = len(laws)
            narrative = f"Your organization has discovered {total} {'pattern' if total == 1 else 'patterns'} and validated {validated}. "
            if validated > 0:
                narrative += "It has earned the right to trust what it has observed consistently."
            else:
                narrative += "It is still building its pattern library — each new signal adds to the understanding."
            lessons = [l.statement[:60] + "..." if l.statement and len(l.statement) > 60 else (l.statement or "A pattern") for l in laws[:2] if l.status and l.status.value == "validated"]
            return {"title": "What you've learned", "period": "recent history", "narrative": narrative, "lessons": lessons}
        except Exception:
            return {"title": "What you've learned", "period": "recent", "narrative": "Still learning.", "lessons": []}

    def _chapter_mistakes(self) -> dict[str, Any]:
        """Chapter: What you've stopped doing."""
        try:
            from maestro_oem.evolution_tracker import EvolutionTracker
            engine = EvolutionTracker(self.model, self.signals)
            tracker = engine.track()
            eliminated = tracker.get("eliminated_count", 0)
            active = tracker.get("active_count", 0)
            modes = tracker.get("failure_modes", [])

            if eliminated > 0:
                narrative = f"Your organization has eliminated {eliminated} {'mistake' if eliminated == 1 else 'mistakes'}. "
                eliminated_modes = [m for m in modes if m.get("current_status") == "eliminated"]
                lessons = [m.get("failure_mode", "")[:60] for m in eliminated_modes[:2]]
            else:
                narrative = f"Your organization is tracking {active} active {'failure mode' if active == 1 else 'failure modes'}. "
                narrative += "No mistakes have been eliminated yet — the pilot is too young. But the tracking has begun."
                lessons = [m.get("narrative", "")[:60] for m in modes[:2]]

            return {"title": "What you've stopped doing", "period": "ongoing", "narrative": narrative, "lessons": lessons}
        except Exception:
            return {"title": "What you've stopped doing", "period": "ongoing", "narrative": "Tracking has begun.", "lessons": []}

    def _chapter_principles(self) -> dict[str, Any]:
        """Chapter: What you've earned the right to trust."""
        try:
            from maestro_oem.principles import PrinciplesEngine
            engine = PrinciplesEngine(self.model, self.signals)
            principles = engine.discover()
            count = principles.get("principle_count", 0)
            summary = principles.get("summary", "")

            if count > 0:
                lesson_list = [p.get("statement", "")[:60] for p in principles.get("principles", [])[:2]]
            else:
                lesson_list = []

            return {"title": "What you've earned the right to trust", "period": "accumulated wisdom", "narrative": summary, "lessons": lesson_list}
        except Exception:
            return {"title": "What you've earned", "period": "accumulating", "narrative": "Still earning.", "lessons": []}

    def _chapter_trajectory(self) -> dict[str, Any]:
        """Chapter: Where you're heading."""
        try:
            from maestro_oem.trajectories import TrajectoryEngine
            engine = TrajectoryEngine(self.model, self.signals)
            result = engine.compute()
            summary = result.get("summary", "The organization is in equilibrium.")
            active = result.get("active_count", 0)

            return {"title": "Where you're heading", "period": "trajectory", "narrative": summary, "lessons": []}
        except Exception:
            return {"title": "Where you're heading", "period": "trajectory", "narrative": "Still determining direction.", "lessons": []}

    def _overarching_narrative(self, chapters: list[dict]) -> str:
        """Write the overarching narrative connecting all chapters."""
        parts = []
        for ch in chapters:
            title = ch.get("title", "")
            narrative = ch.get("narrative", "")
            if narrative:
                parts.append(f"{title}: {narrative}")

        if not parts:
            return "Your organization's story is still being written."

        return ". ".join(parts) + "."
