"""
V8 Competitor Analysis Feature E — Commitment Tracker.

Track every "I'll get back to you" across signals. Flag broken commitments.
The Bond lesson: commitment tracking is Bond's core feature on Maestro's
evidence graph.

Scans signal text for commitment patterns:
  - "I'll get back to you"
  - "will follow up by"
  - "should have this done by"
  - "I'll send you"
  - "will have it ready by"
  - "promised to"
  - "committed to"

Each commitment has: description, who_committed, to_whom, due_date,
source_signal_id, status (open/kept/broken).

A commitment is "broken" if the due_date has passed and no corresponding
completion signal was found. A commitment is "kept" if a later signal
from the same actor references the same topic/artifact.

API: GET /api/oem/commitments
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class CommitmentTracker:
    """Track commitments made in signal text and flag broken ones.

    The tracker scans signal metadata text fields for commitment patterns.
    It's conservative — false positives are worse than false negatives
    because a broken commitment flag is a serious claim.
    """

    # Commitment patterns. Each captures:
    #   - who committed (the actor)
    #   - what they committed to (the description)
    #   - optional due date
    _PATTERNS = [
        # "I'll get back to you" / "I will follow up"
        re.compile(
            r'\b(?:I\'ll|I\s+will|we\'ll|we\s+will)\s+'
            r'(get\s+back\s+to\s+you|follow\s+up|send\s+you|have\s+\w+\s+ready|get\s+you\s+)'
            r'(.+?)(?=\s+by\s+|\s+before\s+|[.;!]|\n|$)',
            re.IGNORECASE,
        ),
        # "will follow up by" / "will have it ready by"
        re.compile(
            r'\bwill\s+(follow\s+up|have\s+\w+\s+ready|send|provide|deliver|share)\b'
            r'(.+?)(?=\s+by\s+|\s+before\s+|[.;!]|\n|$)',
            re.IGNORECASE,
        ),
        # "promised to" / "committed to"
        re.compile(
            r'\b(promised|committed)\s+to\s+'
            r'(.+?)(?=\s+by\s+|\s+before\s+|[.;!]|\n|$)',
            re.IGNORECASE,
        ),
        # "should have this done by"
        re.compile(
            r'\bshould\s+have\s+(this|it|that)\s+(done|ready|finished|complete)\b'
            r'(.+?)(?=\s+by\s+|\s+before\s+|[.;!]|\n|$)',
            re.IGNORECASE,
        ),
    ]

    # Due-date extraction
    _DUE_DATE_RE = re.compile(
        r'\bby\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|'
        r'tomorrow|next\s+week|next\s+month|eow|eod|cob|'
        r'\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b',
        re.IGNORECASE,
    )

    _TEXT_FIELDS = ("text", "title", "description", "body", "content", "summary")

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def track(self) -> dict[str, Any]:
        """Track all commitments across signals.

        Returns:
            {
                commitments: list[commitment],
                total: int,
                open_count: int,
                kept_count: int,
                broken_count: int,
                summary: str,
            }
        """
        commitments = self._extract_all_commitments()
        commitments = self._assess_status(commitments)

        open_count = sum(1 for c in commitments if c["status"] == "open")
        kept_count = sum(1 for c in commitments if c["status"] == "kept")
        broken_count = sum(1 for c in commitments if c["status"] == "broken")

        summary = (
            f"{len(commitments)} commitment{'s' if len(commitments) != 1 else ''} tracked. "
            f"{open_count} open, {kept_count} kept, {broken_count} broken."
        )

        return {
            "commitments": commitments,
            "total": len(commitments),
            "open_count": open_count,
            "kept_count": kept_count,
            "broken_count": broken_count,
            "summary": summary,
        }

    def _extract_all_commitments(self) -> list[dict[str, Any]]:
        """Extract commitments from all signals."""
        commitments: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str]] = set()

        for sig in self.signals:
            for field in self._TEXT_FIELDS:
                text = sig.metadata.get(field, "")
                if not text or not isinstance(text, str) or len(text) < 5:
                    continue

                for pattern in self._PATTERNS:
                    for match in pattern.finditer(text):
                        commitment = self._build_commitment(match, text, sig)
                        if commitment:
                            dedup_key = (commitment["description"].lower(), commitment["who_committed"].lower())
                            if dedup_key in seen_keys:
                                continue
                            seen_keys.add(dedup_key)
                            commitments.append(commitment)

        return commitments

    def _build_commitment(self, match: re.Match, full_text: str, signal: Any) -> dict[str, Any] | None:
        """Build a commitment dict from a regex match."""
        groups = match.groups()
        # The commitment description is the matched text
        description = match.group(0).strip()[:200]

        # Extract due date
        due_date = None
        date_match = self._DUE_DATE_RE.search(full_text)
        if date_match:
            due_date = self._parse_due_date(date_match.group(1))

        # Determine who committed and to whom
        who_committed = signal.actor
        # Try to find participants (to whom)
        to_whom = ""
        participants = signal.metadata.get("participants", [])
        if participants:
            # Find a participant that isn't the actor
            to_whom = next((p for p in participants if p != who_committed), "")

        return {
            "description": description,
            "who_committed": who_committed,
            "to_whom": to_whom,
            "due_date": due_date,
            "source_signal_id": str(signal.signal_id) if hasattr(signal, "signal_id") else None,
            "source_artifact": signal.artifact if hasattr(signal, "artifact") else "",
            "source_timestamp": signal.timestamp.isoformat() if hasattr(signal, "timestamp") and signal.timestamp else None,
            "status": "open",  # will be assessed later
        }

    def _parse_due_date(self, date_str: str) -> str | None:
        """Parse a due date string into ISO format."""
        date_lower = date_str.lower()
        now = datetime.now(timezone.utc)

        days = {
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6,
        }
        for day_name, day_num in days.items():
            if day_name in date_lower:
                today = now.weekday()
                days_ahead = (day_num - today) % 7 or 7
                return (now + __import__("datetime").timedelta(days=days_ahead)).date().isoformat()

        if "tomorrow" in date_lower:
            from datetime import timedelta
            return (now + timedelta(days=1)).date().isoformat()
        if "next week" in date_lower or "eow" in date_lower:
            from datetime import timedelta
            today = now.weekday()
            days_to_friday = (4 - today) % 7 or 7
            return (now + timedelta(days=days_to_friday)).date().isoformat()
        if "next month" in date_lower:
            from datetime import timedelta
            return (now + timedelta(days=30)).date().isoformat()

        # ISO date
        import re
        m = re.match(r'\d{4}-\d{2}-\d{2}', date_str)
        if m:
            return m.group(0)

        return date_str  # return the raw string if we can't parse it

    def _assess_status(self, commitments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Assess the status of each commitment (open/kept/broken).

        A commitment is "broken" if its due_date has passed.
        A commitment is "kept" if a later signal from the same actor
        references the same artifact (completion signal).
        Otherwise it's "open".
        """
        now = datetime.now(timezone.utc)

        for commitment in commitments:
            due_date = commitment.get("due_date")
            source_artifact = commitment.get("source_artifact", "")
            who_committed = commitment.get("who_committed", "")

            # Check if a later signal from the same actor references the same artifact
            kept = False
            for sig in self.signals:
                if sig.actor != who_committed:
                    continue
                if hasattr(sig, "artifact") and sig.artifact == source_artifact:
                    continue  # skip the source signal itself
                # Check if this signal is a "completion" signal
                sig_type = sig.type.value if hasattr(sig.type, "value") else str(sig.type)
                if sig_type in ("pr.merged", "issue.transitioned", "customer.commitment_kept", "deployment"):
                    # Check if the signal text references the commitment
                    sig_text = sig.metadata.get("text", "") or sig.metadata.get("title", "")
                    if source_artifact and source_artifact in sig_text:
                        kept = True
                        break

            if kept:
                commitment["status"] = "kept"
            elif due_date:
                # Check if the due date has passed
                try:
                    due_dt = datetime.fromisoformat(due_date)
                    if due_dt.tzinfo is None:
                        due_dt = due_dt.replace(tzinfo=timezone.utc)
                    if due_dt < now:
                        commitment["status"] = "broken"
                except Exception:
                    pass  # can't parse the date, leave as "open"

        # Sort: broken first, then open, then kept
        status_rank = {"broken": 0, "open": 1, "kept": 2}
        commitments.sort(key=lambda c: status_rank.get(c["status"], 3))
        return commitments
