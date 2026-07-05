"""
V8 Personal Mode — Phase 2-12: Self-Reflection Prompts.

Context-aware journaling prompts based only on the user's own signals.
Never uses sentiment analysis of a third party's messages.

Round 44 (Phase 4) — Post-Event Self-Reflection Prompts:
Detects major work events (board meeting, big release, tough 1:1) from
the USER'S OWN calendar and signals — never from analyzing a colleague's
messages. Offers an optional reflection prompt. The reflection is
private (incognito-aware). No sentiment analysis of colleagues.

WITHDRAWAL PATH (Guideline P9):
The user could journal without prompts. The tool adds structure;
without it, the user relies on their own initiative, which is harder
but fully functional.
"""

from __future__ import annotations

import logging
from typing import Any

from maestro_personal.knowledge_graph import PersonalKG
from maestro_personal.habits import HabitCoach
from maestro_personal.contradictions import PersonalContradictions

logger = logging.getLogger(__name__)


# Round 44 — Major work event keywords. These are detected from the
# user's OWN calendar entries (consent-gated) — NOT from analyzing
# anyone else's messages. The detection is content-based, not sentiment-based.
_MAJOR_WORK_EVENT_KEYWORDS = (
    "board meeting", "board sync", "all-hands", "all hands",
    "release", "ship day", "launch", "go-live", "go live",
    "performance review", "1:1 with manager", "skip level",
    "quarterly review", "qbr", "okr review",
    "incident review", "postmortem", "retro",
    "interview loop", "hiring loop",
)


class ReflectionPrompts:
    """Generates journaling prompts from the user's own signals.

    Never analyzes a third party's messages. "Tough meeting" detection
    comes from the user's own self-report or journal entry, not from
    analyzing the boss's messages.

    Round 44 addition: detects major work events from the user's own
    calendar/signals and offers an optional reflection prompt. The
    detection is keyword-based (not sentiment-based) and uses only the
    user's own data.
    """

    @staticmethod
    def generate(user_id: str = "") -> dict[str, Any]:
        """Generate reflection prompts based on the user's recent activity.

        Returns:
            {
                prompts: list[{prompt, context, type}],
                count: int,
                withdrawal_path: str,
                work_events_detected: list[str],  # Round 44
            }
        """
        prompts: list[dict[str, Any]] = []

        # ─── Round 44: Post-event self-reflection prompts ─────────────
        # Detect major work events from the user's OWN calendar/signals.
        # The detection uses only the user's own data. The prompt is
        # offered, not imposed. The reflection is private (incognito-aware).
        # No sentiment analysis of colleagues' messages.
        work_events: list[str] = []
        try:
            work_events = ReflectionPrompts._detect_major_work_events(user_id)
            for event in work_events[:2]:  # cap at 2 prompts
                prompts.append({
                    "prompt": f"You had {event} today. Want to reflect on how it went?",
                    "context": "Detected from your own calendar (consent-gated). Private reflection.",
                    "type": "work_event_reflection",
                })
        except Exception as e:
            logger.debug("Work event detection failed: %s", e)

        # Check habits for reflection opportunities
        habits = HabitCoach.get_habits()
        for habit in habits:
            if habit.current_streak == 0:
                prompts.append({
                    "prompt": f"You haven't checked in for '{habit.name}' recently. What's getting in the way?",
                    "context": f"Habit '{habit.name}' has 0 current streak.",
                    "type": "habit_gap",
                })
            elif habit.current_streak >= 7:
                prompts.append({
                    "prompt": f"You're on a {habit.current_streak}-day streak for '{habit.name}'. What's working well?",
                    "context": f"Habit '{habit.name}' streak: {habit.current_streak}",
                    "type": "habit_success",
                })

        # Check contradictions for reflection
        contradictions = PersonalContradictions.detect()
        for c in contradictions.get("contradictions", [])[:2]:
            prompts.append({
                "prompt": f"I noticed: {c['description']} What's your perspective on this?",
                "context": c["evidence"],
                "type": "contradiction",
            })

        # Check KG goals for progress reflection
        goals = PersonalKG.get_entities(entity_type="goal")
        for goal in goals[:2]:
            prompts.append({
                "prompt": f"You set a goal: '{goal.name}'. How is it going? What progress have you made?",
                "context": f"Goal from your knowledge graph.",
                "type": "goal_progress",
            })

        # Check KG memories for reflection
        memories = PersonalKG.get_entities(entity_type="memory")
        if memories:
            recent = memories[-1]
            prompts.append({
                "prompt": f"You recently recorded: '{recent.name}'. Want to reflect on this?",
                "context": f"Memory from your knowledge graph.",
                "type": "memory_reflection",
            })

        # General prompt if no specific triggers
        if not prompts:
            prompts.append({
                "prompt": "What's on your mind today? Take a moment to write freely.",
                "context": "No specific triggers — general journaling prompt.",
                "type": "general",
            })

        # Limit to 5 prompts
        prompts = prompts[:5]

        return {
            "prompts": prompts,
            "count": len(prompts),
            "work_events_detected": work_events,
            "withdrawal_path": (
                "The user could journal without prompts. The tool adds structure; without it, "
                "the user relies on their own initiative, which is harder but fully functional."
            ),
        }

    @staticmethod
    def _detect_major_work_events(user_id: str) -> list[str]:
        """Detect major work events from the user's OWN calendar/signals.

        Round 44 Phase 4 constraints:
          - Uses ONLY the user's own data (consent-gated calendar).
          - Never analyzes a colleague's messages.
          - Detection is keyword-based, not sentiment-based.
          - Returns up to 3 event descriptions.
          - Returns [] if consent not granted or incognito is active.

        Args:
            user_id: The user whose calendar to scan.

        Returns:
            list[str]: Up to 3 human-readable event descriptions like
                       "the board meeting" or "the release ship day".
        """
        from maestro_personal.consent import ConsentStore
        from maestro_personal.incognito import IncognitoManager
        from maestro_personal.store import PersonalDataStore

        # Incognito check — privacy is absolute. No work-event detection
        # while incognito (the user explicitly chose not to be observed).
        if IncognitoManager.is_incognito(user_id):
            return []

        # Consent check — calendar access requires explicit consent.
        if not ConsentStore.has_consent(user_id, "work_calendar", "retrieve"):
            return []

        try:
            items = PersonalDataStore.retrieve(user_id, "work_calendar")
        except Exception as e:
            logger.debug("Work calendar retrieval for event detection failed: %s", e)
            return []

        events: list[str] = []
        seen_lower: set[str] = set()
        for item in items[:20]:  # cap at 20 reads
            content_lower = (item.content or "").lower()
            for keyword in _MAJOR_WORK_EVENT_KEYWORDS:
                if keyword in content_lower and keyword not in seen_lower:
                    seen_lower.add(keyword)
                    # Build a human-readable description
                    if "board" in keyword:
                        events.append("the board meeting")
                    elif "all-hands" in keyword or "all hands" in keyword:
                        events.append("the all-hands")
                    elif "release" in keyword or "ship" in keyword or "launch" in keyword:
                        events.append("the release ship day")
                    elif "go-live" in keyword or "go live" in keyword:
                        events.append("the go-live")
                    elif "performance review" in keyword:
                        events.append("your performance review")
                    elif "1:1" in keyword:
                        events.append("your 1:1 with your manager")
                    elif "skip level" in keyword:
                        events.append("your skip-level")
                    elif "quarterly" in keyword or "qbr" in keyword:
                        events.append("the quarterly review")
                    elif "okr" in keyword:
                        events.append("the OKR review")
                    elif "incident" in keyword or "postmortem" in keyword:
                        events.append("the incident review")
                    elif "retro" in keyword:
                        events.append("the retrospective")
                    elif "interview" in keyword or "hiring" in keyword:
                        events.append("the interview loop")
                    else:
                        events.append(f"your {keyword}")
                    break  # one keyword per item
            if len(events) >= 3:
                break

        return events

