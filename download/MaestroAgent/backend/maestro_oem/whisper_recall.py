"""Whisper Recall — associative organizational memory.

CEO's vision (2026-07-03): "Executives forget. Build for imperfect memory
deliberately. The executive should be able to type:
'What was that thing about Legal you showed me last month?'

Maestro should find the whisper, show what happened, and what changed since."

This requires treating Whispers as durable first-class objects with a lifecycle:
  Detected → Surfaced → Seen/Ignored/Deferred/Challenged/Acted On →
  Outcome Observed → Lesson Learned → Retrievable Memory
"""

from __future__ import annotations

import re
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class WhisperRecall:
    """Retrieve old whispers by vague description.

    Usage:
        recall = WhisperRecall(whisper_history_store, oem_state)
        result = recall.recall("What was that thing about Legal?")
        # Returns matching whispers with what_changed_since
    """

    # Common entities/topics to search for
    ENTITY_KEYWORDS = {
        "legal": ["legal", "law", "compliance", "contract", "regulation"],
        "security": ["security", "vulnerability", "cve", "auth", "oauth", "sso"],
        "pricing": ["pricing", "price", "cost", "budget", "discount"],
        "engineering": ["engineering", "deploy", "deployment", "pr", "merge", "rollback"],
        "customer": ["customer", "client", "globex", "initech", "hooli", "acme"],
        "timeline": ["timeline", "deadline", "delay", "late", "schedule"],
        "hiring": ["hiring", "hire", "recruit", "staff"],
    }

    def __init__(self, whisper_history_store: Any = None, oem_state: Any = None) -> None:
        self.store = whisper_history_store
        self.oem_state = oem_state

    def recall(self, query: str, org_id: str = "default") -> dict[str, Any]:
        """Find whispers matching a vague recollection.

        1. Extract entities and topics from the query
        2. Search whisper_history for matching whispers
        3. For each match, show: original insight, executive action, what changed
        """
        keywords = self._extract_keywords(query)

        # Get all whisper history from the store
        all_history = {}
        if self.store:
            try:
                all_history = self.store.get_all_history(org_id=org_id)
            except Exception as e:
                logger.warning("WhisperRecall: failed to get history: %s", e)

        # Search for matches
        matches = []
        for wid, history in all_history.items():
            insight = history.get("insight", "") if isinstance(history, dict) else ""
            if not insight:
                continue

            # Check if any keywords match the insight text
            insight_lower = insight.lower()
            matched_keywords = [k for k in keywords if k in insight_lower]

            if matched_keywords:
                matches.append({
                    "whisper_id": wid,
                    "original_insight": insight,
                    "executive_action": history.get("action_taken") if isinstance(history, dict) else None,
                    "shown_count": history.get("shown_count", 0) if isinstance(history, dict) else 0,
                    "first_shown": history.get("first_shown") if isinstance(history, dict) else None,
                    "last_shown": history.get("last_shown") if isinstance(history, dict) else None,
                    "matched_keywords": matched_keywords,
                    "what_changed": self._what_changed_since(history),
                })

        # Sort by most recent first
        matches.sort(key=lambda m: m.get("last_shown", ""), reverse=True)

        return {
            "query": query,
            "found": len(matches) > 0,
            "match_count": len(matches),
            "whispers": matches[:5],  # Top 5 matches
            "message": self._build_recall_message(matches, query),
        }

    def _extract_keywords(self, query: str) -> list[str]:
        """Extract meaningful keywords from a vague recollection query."""
        query_lower = query.lower()

        # Check for known entity keywords
        keywords = []
        for entity, synonyms in self.ENTITY_KEYWORDS.items():
            for syn in synonyms:
                if syn in query_lower:
                    keywords.append(entity)
                    keywords.append(syn)
                    break

        # Extract other significant words (not common words)
        stop_words = {"the", "a", "an", "is", "was", "were", "about", "you", "me",
                      "showed", "told", "warned", "thing", "that", "what", "who",
                      "when", "where", "why", "how", "did", "didn't", "don't",
                      "have", "has", "had", "to", "of", "in", "on", "at", "for",
                      "with", "from", "by", "and", "or", "but", "not", "this"}
        words = re.findall(r'\b[a-z]{3,}\b', query_lower)
        for word in words:
            if word not in stop_words and word not in keywords:
                keywords.append(word)

        return keywords

    def _what_changed_since(self, history: dict) -> str:
        """Describe what changed since the whisper was last shown."""
        if not isinstance(history, dict):
            return "No changes tracked."

        action = history.get("action_taken")
        shown_count = history.get("shown_count", 0)

        if action == "ignored" and shown_count >= 3:
            return f"This has been ignored {shown_count} times. The risk has increased."
        elif action == "ignored":
            return "You ignored this. The issue may have evolved."
        elif action == "acted":
            return "You acted on this. Check if the action resolved the issue."
        elif action == "overrode":
            return "You overrode this recommendation. The situation may have changed."
        else:
            return "This was surfaced but no action was recorded."

    def _build_recall_message(self, matches: list, query: str) -> str:
        """Build a conversational recall message."""
        if not matches:
            return "I couldn't find a whisper matching that description. Try different keywords."

        best_match = matches[0]
        insight = best_match.get("original_insight", "")
        action = best_match.get("executive_action", "")
        what_changed = best_match.get("what_changed", "")

        parts = [f"I think this is what you remember."]
        parts.append(f"")
        parts.append(f"On a previous occasion, I surfaced: {insight}")

        if action == "ignored":
            parts.append(f"You deferred it.")
        elif action == "acted":
            parts.append(f"You acted on it.")
        elif action == "overrode":
            parts.append(f"You overrode my recommendation.")

        if what_changed:
            parts.append(f"")
            parts.append(f"What changed: {what_changed}")

        return "\n".join(parts)
