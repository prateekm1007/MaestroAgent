"""Deadline parser — converts natural language deadline phrases to ISO 8601.

'by Friday EOD' → '2026-07-31T17:00:00+00:00'
'by Monday' → '2026-08-03T23:59:00+00:00'
Returns None if no deadline phrase is found.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}
EOD_HOUR, DEFAULT_HOUR = 17, 23
EOD_MIN, DEFAULT_MIN = 0, 59


def parse_deadline(text: str, now: datetime | None = None) -> Optional[datetime]:
    """Parse a deadline phrase from text. Returns datetime or None."""
    now = now or datetime.now(timezone.utc)
    t = text.lower()
    eod = "eod" in t or "end of day" in t
    hh, mm = (EOD_HOUR, EOD_MIN) if eod else (DEFAULT_HOUR, DEFAULT_MIN)

    # Explicit time: "5pm", "3:30pm"
    if m := re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", t):
        h = int(m.group(1)) % 12 + (12 if m.group(3) == "pm" else 0)
        hh = h
        mm = int(m.group(2)) if m.group(2) else 0

    # "tomorrow"
    if "tomorrow" in t:
        return (now + timedelta(days=1)).replace(hour=hh, minute=mm, second=0, microsecond=0)

    # "today" / "tonight"
    if "today" in t or "tonight" in t:
        return now.replace(hour=hh, minute=mm, second=0, microsecond=0)

    # "end of week" / "eow"
    if "eow" in t or "end of week" in t:
        # Next Friday
        delta = (4 - now.weekday()) % 7
        if delta == 0:
            delta = 7
        return (now + timedelta(days=delta)).replace(hour=EOD_HOUR, minute=EOD_MIN, second=0, microsecond=0)

    # Weekday names
    for name, idx in WEEKDAYS.items():
        if re.search(rf"\b{name}\b", t):
            delta = (idx - now.weekday()) % 7
            if delta == 0 or "next" in t:
                delta += 7  # roll forward to next week
            return (now + timedelta(days=delta)).replace(
                hour=hh, minute=mm, second=0, microsecond=0)

    # "in N days/weeks"
    if m := re.search(r"\bin\s+(\d+)\s+(day|days|week|weeks)\b", t):
        n = int(m.group(1))
        if "week" in m.group(2):
            n *= 7
        return (now + timedelta(days=n)).replace(hour=EOD_HOUR, minute=EOD_MIN, second=0, microsecond=0)

    # ISO date: "by 2026-08-15"
    if m := re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t):
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                          hh, mm, 0, tzinfo=timezone.utc)
        except ValueError:
            pass

    # "by <month> <day>": "by August 15"
    if m := re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})\b", t):
        months = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
                  "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
        mon = months.get(m.group(1)[:3])
        if mon:
            try:
                target = datetime(now.year, mon, int(m.group(2)), hh, mm, 0, tzinfo=timezone.utc)
                if target < now:
                    target = target.replace(year=now.year + 1)
                return target
            except ValueError:
                pass

    return None


def is_overdue(deadline_iso: Optional[str]) -> bool:
    """Check if a deadline (ISO string) is in the past."""
    if not deadline_iso:
        return False
    try:
        dl = datetime.fromisoformat(deadline_iso)
        return dl < datetime.now(timezone.utc)
    except (ValueError, TypeError):
        return False
