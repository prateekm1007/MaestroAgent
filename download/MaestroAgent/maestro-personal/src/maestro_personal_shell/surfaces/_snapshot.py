"""S2-4 SURFACES reconciliation — single source of truth for cross-surface consistency.

PRINCIPLE P41 (single source of truth): the Briefing, What-Changed, and
The-Moment surfaces MUST derive their commitment/changes counts from ONE
reconciled record — never parallel snapshots. The auditor found Briefing
saying "no changes" while What-Changed said "three changes" and The-Moment
said "nothing" — with 24 active commitments. Each surface had its own
snapshot that drifted.

This module exposes ONE function — reconcile_snapshot(shell, user_email) —
that returns the canonical reconciled record. All three surfaces call it
and embed the result in their `reconciliation` field. The journey gate
asserts all three surfaces return the SAME reconciliation block.

The reconciliation block shape:
  {
    "active_commitments_count": int,
    "overdue_count": int,
    "top_active_entity": str,         # highest-priority entity name
    "top_active_text": str,           # first 60 chars of top commitment text
    "changes_since_yesterday": int,   # count of new/changed signals in last 24h
    "snapshot_source": "CommitmentsSurface.get_active_commitments",  # P41 provenance
    "snapshot_timestamp": str,        # ISO 8601 UTC
  }
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def reconcile_snapshot(shell: Any, user_email: str = "") -> dict[str, Any]:
    """Return the canonical reconciled snapshot for cross-surface consistency.

    SINGLE SOURCE OF TRUTH (P41): reads from CommitmentsSurface — the SAME
    path /api/commitments uses. Never queries the DB directly. All three
    surfaces (Briefing, What-Changed, The-Moment) MUST call this function
    and embed the result in their response's `reconciliation` field.

    Args:
        shell: the PersonalShell instance (from build_shell)
        user_email: the user's email (for stale-map derivation)

    Returns:
        dict with the reconciliation block shape (see module docstring).
    """
    # Lazy import — avoid circular imports at module load time
    from maestro_personal_shell.surfaces.commitments import CommitmentsSurface

    # P41: CommitmentsSurface.get_active_commitments is the SAME function
    # /api/commitments calls. Never a parallel snapshot.
    commit_surface = CommitmentsSurface(shell=shell)
    active = commit_surface.get_active_commitments()

    # Read stale map with the SAME threshold as /api/commitments (days=2)
    # — no divergence.
    stale = shell.detect_stale_commitments(days_threshold=2)
    stale_sids: set[str] = set()
    for s in stale:
        commit = s.get("commitment")
        if not commit:
            continue
        if isinstance(commit, dict):
            sid = commit.get("signal_id", "")
        else:
            sid = getattr(commit, "signal_id", "")
        if sid:
            stale_sids.add(sid)

    # Count changes since yesterday — signals with timestamp in last 24h
    # (using the shell's signals, same source as What-Changed)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)
    changes_since_yesterday = 0
    for sig in shell.oem_state.signals:
        ts_str = str(getattr(sig, "timestamp", ""))
        if not ts_str:
            continue
        try:
            # Parse ISO 8601 (handle Z suffix)
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                changes_since_yesterday += 1
        except Exception:
            continue

    # Top active commitment: stale first, then by entity for determinism
    active_sorted = sorted(
        active,
        key=lambda c: (
            0 if c.get("signal_id", "") in stale_sids else 1,
            c.get("entity", "").lower(),
        ),
    )
    top = active_sorted[0] if active_sorted else None

    return {
        "active_commitments_count": len(active),
        "overdue_count": sum(1 for c in active if c.get("signal_id", "") in stale_sids),
        "top_active_entity": (top or {}).get("entity", ""),
        "top_active_text": ((top or {}).get("text", "") or "")[:60],
        "changes_since_yesterday": changes_since_yesterday,
        "snapshot_source": "CommitmentsSurface.get_active_commitments",
        "snapshot_timestamp": now.isoformat(),
    }
