"""Unified Signal model — the spine of the connector moat.

Every source (Gmail, Slack, GitHub, Amazon email parser, etc.) normalizes
into this single model. Ask/provenance/drafts read ONLY this — they never
need to know which platform the data came from.

The metadata.source field MUST round-trip through DB → evidence_ref
(learned from the Gmail provenance bug). Every adapter sets it at ingest.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Signal:
    """A single piece of commitment-bearing content from any source.

    Attributes:
        source: Platform identifier ("gmail", "slack", "github", "amazon", etc.)
        source_id: Platform-native ID (Gmail Message-ID, Slack ts, GH node_id) — idempotency key
        thread_id: Conversation/thread grouping (Gmail thread, Slack thread_ts, GH issue#)
        entity: Normalized counterparty name
        text: The commitment-bearing content
        timestamp: When the signal was created (platform-native time)
        direction: "inbound" | "outbound" | "commitment_mine" | "commitment_theirs"
        metadata: Source-specific extras; metadata["source"] MUST be set
        confidence: Extraction confidence (0.0-1.0)
    """
    source: str
    source_id: str
    thread_id: str | None = None
    entity: str = "unknown"
    text: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    direction: str = "inbound"
    metadata: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5

    def __post_init__(self):
        """Ensure metadata.source is set — the provenance guarantee."""
        if "source" not in self.metadata:
            self.metadata["source"] = self.source

    def to_db_dict(self) -> dict[str, Any]:
        """Convert to the dict format expected by save_signal_to_db."""
        return {
            "signal_id": f"conn_{self.source}_{self.source_id}",
            "entity": self.entity,
            "text": self.text,
            "signal_type": self.metadata.get("signal_type", "reported_statement"),
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else str(self.timestamp),
            "metadata": self.metadata,
            "source_acl": "private",
        }

    @classmethod
    def from_db_dict(cls, d: dict[str, Any]) -> "Signal":
        """Reconstruct from a DB row dict."""
        import json
        meta = d.get("metadata", "{}")
        if isinstance(meta, str):
            try:
                meta = json.loads(meta) if meta else {}
            except (json.JSONDecodeError, TypeError):
                meta = {}

        # Extract source from signal_id prefix or metadata
        sid = str(d.get("signal_id", ""))
        if sid.startswith("conn_"):
            parts = sid.split("_", 2)
            source = parts[1] if len(parts) > 1 else "unknown"
        else:
            source = meta.get("source", "unknown")

        ts_str = str(d.get("timestamp", ""))
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            ts = datetime.now(timezone.utc)

        return cls(
            source=source,
            source_id=sid,
            thread_id=meta.get("thread_id"),
            entity=d.get("entity", "unknown"),
            text=d.get("text", ""),
            timestamp=ts,
            direction=meta.get("direction", "inbound"),
            metadata=meta,
            confidence=meta.get("confidence", 0.5),
        )
