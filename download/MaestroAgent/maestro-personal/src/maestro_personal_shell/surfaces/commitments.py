"""
Commitments surface — thin wrapper over Core's commitment classification.

Calls:
  - classify_transcript_chunk() from audit_safety
  - should_treat_as_commitment() from audit_safety

Does NOT reimplement commitment classification. Does NOT add enterprise
commitment tracking. Just calls Core with personal signals and formats
the result for personal use.
"""

from __future__ import annotations

from typing import Any


class CommitmentsSurface:
    """The Commitments surface — "what did I promise?"

    Calls Core's classify_transcript_chunk + should_treat_as_commitment
    on personal signals. Returns active commitments tracked by the shell.
    """

    def __init__(self, shell: Any = None) -> None:
        self._shell = shell

    def get_active_commitments(self) -> list[dict[str, Any]]:
        """Get all active commitments from personal signals.

        Uses Core's should_treat_as_commitment to classify, then groups
        by entity. Returns a list of commitment dicts.
        """
        from maestro_cognitive_council.audit_safety import (
            classify_transcript_chunk,
            should_treat_as_commitment,
        )

        commitments = []
        seen_ids = set()

        for signal in self._shell.oem_state.signals:
            text = getattr(signal, "text", "") or ""
            if not text:
                continue

            sig_id = getattr(signal, "signal_id", str(id(signal)))
            if sig_id in seen_ids:
                continue

            # Use Core's classifier — do NOT reimplement
            if should_treat_as_commitment(text):
                claim_type = classify_transcript_chunk(text)
                # S2-3 fix (auditor v11, 2026-07-29): propagate the signal's
                # metadata into the commitment dict so /api/commitments can
                # read deadline (and other classification fields) from
                # c["metadata"]["deadline"]. The prior code built the dict
                # from scratch and dropped metadata entirely, so the deadline
                # field was always empty even when the signal had it stored.
                _sig_meta = getattr(signal, "metadata", None) or {}
                if not isinstance(_sig_meta, dict):
                    _sig_meta = {}
                commitments.append({
                    "entity": getattr(signal, "entity", ""),
                    "text": text,
                    "claim_type": claim_type,
                    "signal_id": sig_id,
                    "timestamp": getattr(signal, "timestamp", None),
                    "is_commitment": True,
                    "metadata": _sig_meta,
                })
                seen_ids.add(sig_id)

        return commitments

    def get_commitments_for_entity(self, entity: str) -> list[dict[str, Any]]:
        """Get all commitments for a specific entity."""
        all_commitments = self.get_active_commitments()
        return [
            c for c in all_commitments
            if c["entity"].lower() == entity.lower()
        ]

    def get_stale_commitments(self, days_threshold: int = 5) -> list[dict[str, Any]]:
        """Get commitments with no follow-up for N days.

        Delegates to shell.detect_stale_commitments (the absence-detection
        mechanism built in the shell, not in Core).
        """
        return self._shell.detect_stale_commitments(days_threshold=days_threshold)
