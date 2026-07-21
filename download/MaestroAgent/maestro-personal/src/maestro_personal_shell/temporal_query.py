"""
Temporal query parser — enables "Ask about last quarter" with provenance.

CEO Directive 3: Historical depth with temporal filtering.

Parses natural language time references in Ask queries and converts
them to as_of/from_date ranges for semantic retrieval.

Examples:
- "What did I commit to last quarter?" → from=Q_start, to=Q_end
- "What changed in the last 30 days?" → from=30d_ago, to=now
- "What did AcmeCorp promise in July?" → from=Jul 1, to=Jul 31
- "Show me commitments from last week" → from=last Mon, to=last Sun
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger(__name__)


def parse_temporal_query(query: str) -> dict[str, Any]:
    """Parse a natural language query for temporal references.

    Returns:
    {
        "from_date": ISO string or None,
        "to_date": ISO string or None,
        "time_range_description": "last quarter" | "last 30 days" | etc,
        "has_temporal_ref": True | False,
    }
    """
    query_lower = query.lower()
    now = datetime.now(timezone.utc)

    # Last quarter
    if "last quarter" in query_lower or "previous quarter" in query_lower:
        current_quarter = (now.month - 1) // 3
        if current_quarter == 0:
            # Q4 of previous year
            from_date = datetime(now.year - 1, 10, 1, tzinfo=timezone.utc)
            to_date = datetime(now.year, 1, 1, tzinfo=timezone.utc) - timedelta(seconds=1)
        else:
            from_month = (current_quarter - 1) * 3 + 1
            from_date = datetime(now.year, from_month, 1, tzinfo=timezone.utc)
            to_date = datetime(now.year, from_month + 3, 1, tzinfo=timezone.utc) - timedelta(seconds=1)

        return {
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "time_range_description": "last quarter",
            "has_temporal_ref": True,
        }

    # This quarter
    if "this quarter" in query_lower or "current quarter" in query_lower:
        current_quarter = (now.month - 1) // 3
        from_month = current_quarter * 3 + 1
        from_date = datetime(now.year, from_month, 1, tzinfo=timezone.utc)
        return {
            "from_date": from_date.isoformat(),
            "to_date": now.isoformat(),
            "time_range_description": "this quarter",
            "has_temporal_ref": True,
        }

    # Last N days/weeks/months
    match = re.search(r'last\s+(\d+)\s*(day|week|month|year)s?', query_lower)
    if match:
        n = int(match.group(1))
        unit = match.group(2)

        if unit == "day":
            from_date = now - timedelta(days=n)
        elif unit == "week":
            from_date = now - timedelta(weeks=n)
        elif unit == "month":
            from_date = now - timedelta(days=n * 30)
        elif unit == "year":
            from_date = now - timedelta(days=n * 365)
        else:
            from_date = now - timedelta(days=30)

        return {
            "from_date": from_date.isoformat(),
            "to_date": now.isoformat(),
            "time_range_description": f"last {n} {unit}s",
            "has_temporal_ref": True,
        }

    # "last week" / "last month" / "last year" (without number)
    if "last week" in query_lower:
        from_date = now - timedelta(weeks=1)
        return {
            "from_date": from_date.isoformat(),
            "to_date": now.isoformat(),
            "time_range_description": "last week",
            "has_temporal_ref": True,
        }

    if "last month" in query_lower:
        from_date = now - timedelta(days=30)
        return {
            "from_date": from_date.isoformat(),
            "to_date": now.isoformat(),
            "time_range_description": "last month",
            "has_temporal_ref": True,
        }

    if "last year" in query_lower:
        from_date = now - timedelta(days=365)
        return {
            "from_date": from_date.isoformat(),
            "to_date": now.isoformat(),
            "time_range_description": "last year",
            "has_temporal_ref": True,
        }

    # Named months
    month_names = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
        "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }

    for month_name, month_num in month_names.items():
        if f"in {month_name}" in query_lower or f"from {month_name}" in query_lower:
            # Try to find a year
            year_match = re.search(r'\b(20\d{2})\b', query)
            year = int(year_match.group(1)) if year_match else now.year

            from_date = datetime(year, month_num, 1, tzinfo=timezone.utc)
            if month_num == 12:
                to_date = datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
            else:
                to_date = datetime(year, month_num + 1, 1, tzinfo=timezone.utc) - timedelta(seconds=1)

            return {
                "from_date": from_date.isoformat(),
                "to_date": to_date.isoformat(),
                "time_range_description": f"{month_name} {year}",
                "has_temporal_ref": True,
            }

    # Phase 1.3 Block A2 fix (2026-07-21): additional temporal patterns.
    #
    # ROOT CAUSE (verified by execution): the benchmark's 20 temporal
    # questions use 7 patterns. 4 were handled (last quarter/month/week,
    # last N days). 3 were missing: "the first week", "recently",
    # "N months ago". Each missing pattern caused the temporal ref to be
    # ignored, so retrieval didn't apply a date filter — and the answer
    # either abstained or returned wrong-period evidence.
    #
    # FIX: add the 3 missing patterns. "first week" = first 7 days of
    # current month. "recently" = last 14 days (generous). "N months ago"
    # = a 1-month window N months back.

    # "the first week" — first 7 days of the current month
    if "first week" in query_lower:
        from_date = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        to_date = from_date + timedelta(days=7)
        return {
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "time_range_description": "first week",
            "has_temporal_ref": True,
        }

    # "recently" — last 14 days (generous window)
    if "recently" in query_lower or "recent" in query_lower:
        from_date = now - timedelta(days=14)
        return {
            "from_date": from_date.isoformat(),
            "to_date": now.isoformat(),
            "time_range_description": "recently",
            "has_temporal_ref": True,
        }

    # "N months ago" / "N days ago" / "N weeks ago" — a 1-unit window
    # N units back. E.g. "2 months ago" = the month that was 2 months ago.
    ago_match = re.search(r'(\d+)\s+(day|week|month|year)s?\s+ago', query_lower)
    if ago_match:
        n = int(ago_match.group(1))
        unit = ago_match.group(2)
        if unit == "day":
            # N days ago = a 1-day window N days back
            target = now - timedelta(days=n)
            from_date = datetime(target.year, target.month, target.day, tzinfo=timezone.utc)
            to_date = from_date + timedelta(days=1)
        elif unit == "week":
            target = now - timedelta(weeks=n)
            from_date = target - timedelta(days=target.weekday())  # Monday of that week
            to_date = from_date + timedelta(days=7)
        elif unit == "month":
            # N months ago = that entire month
            target_month = now.month - n
            target_year = now.year
            while target_month <= 0:
                target_month += 12
                target_year -= 1
            from_date = datetime(target_year, target_month, 1, tzinfo=timezone.utc)
            if target_month == 12:
                to_date = datetime(target_year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
            else:
                to_date = datetime(target_year, target_month + 1, 1, tzinfo=timezone.utc) - timedelta(seconds=1)
        elif unit == "year":
            target_year = now.year - n
            from_date = datetime(target_year, 1, 1, tzinfo=timezone.utc)
            to_date = datetime(target_year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        else:
            from_date = now - timedelta(days=30)
            to_date = now
        return {
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "time_range_description": f"{n} {unit}s ago",
            "has_temporal_ref": True,
        }

    # "since <weekday>" — e.g. "since Tuesday" = from last Tuesday to now
    weekday_match = re.search(r'since\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)', query_lower)
    if weekday_match:
        day_name = weekday_match.group(1)
        days_of_week = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        target_weekday = days_of_week.index(day_name)
        days_back = (now.weekday() - target_weekday) % 7
        if days_back == 0:
            days_back = 7  # last occurrence, not today
        from_date = now - timedelta(days=days_back)
        return {
            "from_date": from_date.isoformat(),
            "to_date": now.isoformat(),
            "time_range_description": f"since {day_name}",
            "has_temporal_ref": True,
        }

    # "before Q3" / "before Q1" etc — quarter boundaries
    before_q_match = re.search(r'before\s+q([1-4])', query_lower)
    if before_q_match:
        q_num = int(before_q_match.group(1))
        quarter_month = {1: 1, 2: 4, 3: 7, 4: 10}[q_num]
        to_date = datetime(now.year, quarter_month, 1, tzinfo=timezone.utc) - timedelta(seconds=1)
        return {
            "from_date": None,
            "to_date": to_date.isoformat(),
            "time_range_description": f"before Q{q_num}",
            "has_temporal_ref": True,
        }

    # "after <event>" — can't parse event dates, but mark as temporal ref
    # so retrieval knows to consider temporal context. Use a generous
    # window (last 90 days).
    if re.search(r'\bafter\s+(the\s+)?(meeting|call|sync|standup|review)', query_lower):
        from_date = now - timedelta(days=90)
        return {
            "from_date": from_date.isoformat(),
            "to_date": now.isoformat(),
            "time_range_description": "after meeting (last 90d)",
            "has_temporal_ref": True,
        }

    # No temporal reference found
    return {
        "from_date": None,
        "to_date": None,
        "time_range_description": "",
        "has_temporal_ref": False,
    }


def filter_signals_by_date_range(
    signals: list[dict[str, Any]],
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict[str, Any]]:
    """Filter signals by a date range.

    Args:
        signals: List of signal dicts with 'timestamp' field
        from_date: ISO datetime string (inclusive)
        to_date: ISO datetime string (inclusive)

    Returns: Filtered list of signals
    """
    if not from_date and not to_date:
        return signals

    try:
        from_dt = datetime.fromisoformat(from_date.replace("Z", "+00:00")) if from_date else None
        to_dt = datetime.fromisoformat(to_date.replace("Z", "+00:00")) if to_date else None

        if from_dt and from_dt.tzinfo is None:
            from_dt = from_dt.replace(tzinfo=timezone.utc)
        if to_dt and to_dt.tzinfo is None:
            to_dt = to_dt.replace(tzinfo=timezone.utc)
    except Exception:
        return signals

    filtered = []
    for sig in signals:
        ts = sig.get("timestamp", "")
        if not ts:
            continue

        try:
            sig_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if sig_dt.tzinfo is None:
                sig_dt = sig_dt.replace(tzinfo=timezone.utc)

            if from_dt and sig_dt < from_dt:
                continue
            if to_dt and sig_dt > to_dt:
                continue

            filtered.append(sig)
        except Exception:
            filtered.append(sig)  # keep if can't parse

    return filtered
