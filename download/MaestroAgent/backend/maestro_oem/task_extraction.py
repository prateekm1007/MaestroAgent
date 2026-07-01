"""
V8 Daily Work #2 — Task & Action-Item Intelligence.

Auto-extract to-dos from signals during ingestion. Scan signal text for
action-item patterns:
  - "priya to review by Friday"
  - "carlos will draft the RFC"
  - "raj should follow up with legal"
  - "TODO: update the docs"
  - "ACTION ITEM: schedule the retro"

Each extracted task has:
  - description: what needs to be done
  - assignee: who should do it (email or name)
  - due_date: when it's due (if mentioned, else None)
  - source_signal_id: the signal that produced this task
  - priority: "high" | "medium" | "low"
  - status: "open" | "done"

Tasks are stored as learning objects with type=TASK. This feeds the
constitutional layers — the model learns what the org has committed to
and can track completion.

API: GET /api/oem/tasks
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from maestro_oem.learning_object import LearningObject, LearningObjectType

logger = logging.getLogger(__name__)


class TaskExtractor:
    """Extract action items from signal text during ingestion.

    The extractor scans signal metadata for text fields (text, title,
    description) and applies regex patterns to identify action items.
    It's intentionally conservative — false positives are worse than
    false negatives because every extracted task creates a learning
    object that the org will see.
    """

    # Action-item patterns. Each pattern captures:
    #   - assignee (name or email)
    #   - action verb + description
    #   - optional due date
    #
    # Patterns are ordered by specificity — most specific first so
    # we don't double-match.
    _PATTERNS = [
        # "priya to review by Friday" / "raj to follow up"
        # Assignee is a first name (any case) or email before "to <verb>"
        re.compile(
            r'\b([a-z][a-z._-]*@(?:[a-z]+\.)+[a-z]{2,}|[A-Za-z][a-z]+)\s+to\s+'
            r'(review|follow\s+up|draft|update|create|schedule|send|prepare|investigate|fix|deploy|merge|test|design|implement|write|share|check)\b'
            r'(.+?)(?=\s+by\s+|\s+before\s+|\s+due\s+|[.;!]|\n|$)',
            re.IGNORECASE,
        ),
        # "carlos will draft the RFC" / "raj should update the docs"
        re.compile(
            r'\b([a-z][a-z._-]*@(?:[a-z]+\.)+[a-z]{2,}|[A-Za-z][a-z]+)\s+'
            r'(will|should|needs?\s+to|has\s+to|must)\s+'
            r'(review|follow\s+up|draft|update|create|schedule|send|prepare|investigate|fix|deploy|merge|test|design|implement|write|share|check)\b'
            r'(.+?)(?=\s+by\s+|\s+before\s+|\s+due\s+|[.;!]|\n|$)',
            re.IGNORECASE,
        ),
        # "TODO: update the docs" / "ACTION ITEM: schedule the retro"
        re.compile(
            r'\b(?:TODO|ACTION\s+ITEM|ACTIONITEM|TASK|FOLLOWUP|FOLLOW\s+UP)\s*[:\-]\s*'
            r'(.+?)(?=\s+by\s+|\s+before\s+|\s+due\s+|[.;!]|\n|$)',
            re.IGNORECASE,
        ),
    ]

    # Due-date patterns — extract "by Friday", "by EOW", "by 2024-12-01", etc.
    _DUE_DATE_PATTERNS = [
        # "by Friday" / "by Monday" — day of week
        re.compile(r'\bby\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', re.IGNORECASE),
        # "by EOW" / "by EOD" / "by COB"
        re.compile(r'\bby\s+(eow|eod|cob|end\s+of\s+(?:week|day|business\s+day))\b', re.IGNORECASE),
        # "by 2024-12-01" / "by 12/01" — date
        re.compile(r'\bby\s+(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b', re.IGNORECASE),
        # "by tomorrow" / "by next week"
        re.compile(r'\bby\s+(tomorrow|next\s+week|next\s+month|this\s+week|this\s+month)\b', re.IGNORECASE),
    ]

    # Priority keywords
    _HIGH_PRIORITY_KEYWORDS = {"urgent", "asap", "critical", "blocker", "p0", "p1", "immediately"}
    _LOW_PRIORITY_KEYWORDS = {"when convenient", "no rush", "low priority", "nice to have", "someday"}

    # Text fields in signal metadata to scan
    _TEXT_FIELDS = ("text", "title", "description", "body", "content", "summary")

    def __init__(self, model: Any) -> None:
        self.model = model

    def extract_from_signal(self, signal: Any) -> list[LearningObject]:
        """Extract tasks from a single signal.

        Scans the signal's metadata text fields for action-item patterns.
        Returns a list of LearningObjects with type=TASK. Each task is
        linked to the source signal via signal_ids. Deduplicates tasks
        that appear in multiple text fields (e.g. same text in 'title'
        and 'description') by checking description+assignee uniqueness.

        Args:
            signal: An ExecutionSignal to scan.

        Returns:
            list[LearningObject] — may be empty if no action items found.
        """
        tasks: list[LearningObject] = []
        seen_keys: set[tuple[str, str]] = set()  # (description, assignee) for dedup
        try:
            # Gather all text from metadata
            texts = []
            for field in self._TEXT_FIELDS:
                val = signal.metadata.get(field, "")
                if val and isinstance(val, str) and len(val) > 5:
                    texts.append(val)

            if not texts:
                return tasks

            signal_id = signal.signal_id if hasattr(signal, "signal_id") else None
            domain = signal.metadata.get("domain", "unknown")
            provider = signal.provider.value if hasattr(signal.provider, "value") else str(signal.provider)

            for text in texts:
                for pattern in self._PATTERNS:
                    for match in pattern.finditer(text):
                        task = self._build_task_from_match(match, text, signal, signal_id, domain, provider)
                        if task:
                            # Deduplicate by (description, assignee)
                            dedup_key = (task.description.lower(), task.metadata.get("assignee", "").lower())
                            if dedup_key in seen_keys:
                                continue
                            seen_keys.add(dedup_key)
                            tasks.append(task)
        except Exception as e:
            logger.debug("Task extraction failed for signal: %s", e)

        return tasks

    def extract_from_signals(self, signals: list[Any]) -> list[LearningObject]:
        """Extract tasks from a batch of signals.

        Args:
            signals: list of ExecutionSignals to scan.

        Returns:
            list[LearningObject] with type=TASK.
        """
        all_tasks: list[LearningObject] = []
        for sig in signals:
            all_tasks.extend(self.extract_from_signal(sig))
        return all_tasks

    def _build_task_from_match(
        self,
        match: re.Match,
        full_text: str,
        signal: Any,
        signal_id: Any,
        domain: str,
        provider: str,
    ) -> LearningObject | None:
        """Build a LearningObject (type=TASK) from a regex match.

        Handles the 3 pattern types:
          1. "name to verb..." — assignee is group(1), action is group(2)+group(3)
          2. "name will/should verb..." — assignee is group(1), action is group(2)+group(3)
          3. "TODO: ..." — assignee unknown, action is group(1)
        """
        groups = match.groups()

        # Determine assignee and description based on pattern type
        assignee = signal.actor  # default to the signal's actor
        description = ""

        if len(groups) == 3:
            # Pattern 0: "name to verb..." — assignee is group(0), verb is group(1), rest is group(2)
            assignee_raw = groups[0] or ""
            verb = groups[1] or ""
            rest = (groups[2] or "").strip().strip(".,;:!")
            description = f"{verb} {rest}".strip()
            assignee = self._normalize_assignee(assignee_raw, signal)
        elif len(groups) == 4:
            # Pattern 1: "name will/should verb..." — assignee(0), modal(1), verb(2), rest(3)
            assignee_raw = groups[0] or ""
            verb = groups[2] or ""
            rest = (groups[3] or "").strip().strip(".,;:!")
            description = f"{verb} {rest}".strip()
            assignee = self._normalize_assignee(assignee_raw, signal)
        elif len(groups) == 1:
            # Pattern 2: TODO: description
            description = (groups[0] or "").strip().strip(".,;:!")
            assignee = signal.actor

        if not description or len(description) < 3:
            return None

        # Extract due date from the full text (not just the match)
        due_date = self._extract_due_date(full_text)

        # Determine priority
        priority = self._determine_priority(full_text)

        # Build the task as a LearningObject
        task = LearningObject(
            lo_id=uuid4(),
            type=LearningObjectType.TASK,
            title=description[:120],  # truncate for title
            description=description,
            entities=[assignee] if assignee else [],
            artifacts=[signal.artifact] if hasattr(signal, "artifact") and signal.artifact else [],
            signal_ids=[signal_id] if signal_id else [],
            providers={provider} if provider else set(),
            confidence=0.8,  # tasks extracted from text are 80% confident
            evidence_count=1,
            first_seen=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
            metadata={
                "kind": "task",
                "assignee": assignee,
                "due_date": due_date,
                "priority": priority,
                "status": "open",
                "source_signal_id": str(signal_id) if signal_id else None,
                "domain": domain,
                "extracted_from": match.group(0)[:100],
            },
        )

        return task

    def _normalize_assignee(self, assignee_raw: str, signal: Any) -> str:
        """Normalize an assignee string to an email if possible.

        If the assignee looks like an email, use it. If it's a first name,
        try to find a matching email in the signal's participants or the
        model's knowledge graph. If no match, use the raw name.
        """
        assignee = assignee_raw.strip()
        if "@" in assignee:
            return assignee

        # Try to find a matching email in participants
        participants = signal.metadata.get("participants", [])
        if participants and assignee:
            for p in participants:
                if p.lower().startswith(assignee.lower()):
                    return p

        # Try the knowledge graph
        try:
            for entity in self.model.knowledge.influence.keys():
                if entity.lower().startswith(assignee.lower()):
                    return entity
        except Exception:
            pass

        return assignee

    def _extract_due_date(self, text: str) -> str | None:
        """Extract a due date from text. Returns ISO date string or None."""
        text_lower = text.lower()
        now = datetime.now(timezone.utc)

        # Day of week
        days = {
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6,
        }
        for day_name, day_num in days.items():
            if f"by {day_name}" in text_lower:
                today = now.weekday()
                days_ahead = (day_num - today) % 7
                if days_ahead == 0:
                    days_ahead = 7  # next week's same day
                due = now + timedelta(days=days_ahead)
                return due.date().isoformat()

        # Relative dates
        if "by tomorrow" in text_lower:
            return (now + timedelta(days=1)).date().isoformat()
        if "by next week" in text_lower or "by eow" in text_lower or "by end of week" in text_lower:
            # End of week = next Friday
            today = now.weekday()
            days_to_friday = (4 - today) % 7 or 7
            return (now + timedelta(days=days_to_friday)).date().isoformat()
        if "by next month" in text_lower or "by end of month" in text_lower:
            return (now + timedelta(days=30)).date().isoformat()

        # ISO date "by 2024-12-01"
        m = re.search(r'\bby\s+(\d{4}-\d{2}-\d{2})\b', text_lower)
        if m:
            return m.group(1)

        return None

    def _determine_priority(self, text: str) -> str:
        """Determine priority from text keywords."""
        text_lower = text.lower()
        for kw in self._HIGH_PRIORITY_KEYWORDS:
            if kw in text_lower:
                return "high"
        for kw in self._LOW_PRIORITY_KEYWORDS:
            if kw in text_lower:
                return "low"
        return "medium"


def get_tasks(model: Any, assignee: str = "", domain: str = "", priority: str = "",
              status: str = "") -> list[dict[str, Any]]:
    """Get all tasks from the model's learning objects, with optional filters.

    Args:
        model: The ExecutionModel to query.
        assignee: Filter by assignee email (case-insensitive substring match).
        domain: Filter by domain (exact match).
        priority: Filter by priority (high/medium/low).
        status: Filter by status (open/done).

    Returns:
        list of task dicts with: id, description, assignee, due_date,
        priority, status, source_signal_id, domain, created_at.
    """
    tasks: list[dict[str, Any]] = []
    for lo in model.learning_objects.values():
        lo_type = lo.type.value if hasattr(lo.type, "value") else str(lo.type)
        if lo_type != "task":
            continue

        meta = lo.metadata or {}
        task_assignee = meta.get("assignee", "")
        task_domain = meta.get("domain", "")
        task_priority = meta.get("priority", "medium")
        task_status = meta.get("status", "open")

        # Apply filters
        if assignee and assignee.lower() not in task_assignee.lower():
            continue
        if domain and task_domain != domain:
            continue
        if priority and task_priority != priority:
            continue
        if status and task_status != status:
            continue

        tasks.append({
            "id": str(lo.lo_id),
            "description": lo.description,
            "assignee": task_assignee,
            "due_date": meta.get("due_date"),
            "priority": task_priority,
            "status": task_status,
            "source_signal_id": meta.get("source_signal_id"),
            "domain": task_domain,
            "created_at": lo.first_seen.isoformat() if hasattr(lo.first_seen, "isoformat") else str(lo.first_seen),
            "confidence": lo.confidence,
        })

    # Sort by priority (high first), then by due_date (earliest first)
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    tasks.sort(key=lambda t: (
        priority_rank.get(t["priority"], 3),
        t["due_date"] or "9999-12-31",
    ))
    return tasks
