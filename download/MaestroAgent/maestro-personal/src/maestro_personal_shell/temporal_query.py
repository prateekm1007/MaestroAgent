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
