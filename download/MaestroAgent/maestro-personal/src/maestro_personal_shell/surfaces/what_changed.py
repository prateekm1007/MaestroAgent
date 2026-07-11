"""
What Changed surface — surfaces meaningful deltas.

Calls Core's SituationEngine.apply_signal() → SituationDelta to detect
what changed. Also uses the shell's detect_stale_commitments for the
absence-detection dimension.
"""

from __future__ import annotations

from typing import Any


class WhatChangedSurface:
    """The What Changed surface — "what changed while I was away?"

    Calls Core's SituationEngine to detect deltas. Does NOT reimplement
    delta detection. Does NOT summarize inbox activity (the break-test
    dimension 5 forbids that).
    """

    def __init__(self, shell: Any = None) -> None:
        self._shell = shell

    def get_recent_deltas(self, since_timestamp: Any = None) -> list[dict[str, Any]]:
        """Get meaningful deltas since a timestamp.

        A "delta" is a signal that changed a situation's state. This is
        NOT an inbox summary — it's a Situation-centric view of what
        materially changed.
        """
        from datetime import datetime, timezone, timedelta

        if since_timestamp is None:
            # P1-Audit-3.1 fix: default to last 24 hours, NOT now.
            # The old code defaulted to datetime.now(), which filtered out
            # ALL signals (nothing is after "now"). This caused What Changed
            # to always return 0 changes. Fix: subtract 24h so recent
            # signals are included.
            since_timestamp = datetime.now(timezone.utc) - timedelta(hours=24)

        deltas = []

        # Get all signals since the timestamp
        for signal in self._shell.oem_state.signals:
            sig_time = getattr(signal, "timestamp", None)
            if sig_time is None:
                continue
            # Handle both tz-aware and tz-naive timestamps
            if hasattr(sig_time, "tzinfo") and sig_time.tzinfo is None:
                sig_time = sig_time.replace(tzinfo=timezone.utc)
            if hasattr(since_timestamp, "tzinfo") and since_timestamp.tzinfo is None:
                since_timestamp = since_timestamp.replace(tzinfo=timezone.utc)

            if sig_time > since_timestamp:
                sig_type = str(getattr(signal, "signal_type", "") or
                               getattr(getattr(signal, "type", ""), "value", ""))
                deltas.append({
                    "entity": getattr(signal, "entity", ""),
                    "text": getattr(signal, "text", ""),
                    "type": sig_type,
                    "timestamp": sig_time,
                    "signal_id": getattr(signal, "signal_id", ""),
                    "is_meaningful": self._is_meaningful_delta(signal),
                })

        return deltas

    def _is_meaningful_delta(self, signal: Any) -> bool:
        """Heuristic: is this delta meaningful (not noise)?

        Per break-test dimension 5: What Changed must surface meaningful
        deltas, not inbox activity. A delta is meaningful if it:
          - Is a commitment (promise/proposal)
          - Changes a meeting (scheduled/moved/cancelled)
          - Indicates a deadline (approaching/missed)
          - Is a follow-up required
        """
        sig_type = str(getattr(signal, "signal_type", "") or
                       getattr(getattr(signal, "type", ""), "value", "")).lower()

        meaningful_types = {
            "commitment_made", "personal.promise", "personal.commitment",
            "meeting.scheduled", "meeting.moved", "meeting.cancelled",
            "calendar_change",
            "deadline.approaching", "deadline.missed",
            "follow_up.required",
            "personal.decision",
        }
        return sig_type in meaningful_types

    def get_stale_commitments(self, days_threshold: int = 5) -> list[dict[str, Any]]:
        """Get commitments with no follow-up for N days.

        Delegates to shell.detect_stale_commitments.
        """
        return self._shell.detect_stale_commitments(days_threshold=days_threshold)
