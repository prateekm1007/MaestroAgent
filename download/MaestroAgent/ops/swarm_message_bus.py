"""Swarm Message Bus — inter-leader communication, logged to the worklog.

Every message between Team Leaders is structured and recorded. The
coordination is transparent and reviewable, not a black box.

Messages: {from, to, subject, body, timestamp, ticket_id}
Logged to: ops/worklog/ (via the worklog system) + in-memory for the run
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LeaderMessage:
    """A structured message between Team Leaders."""
    from_leader: str
    to_leader: str
    subject: str
    body: str
    timestamp: str = ""
    ticket_id: str = ""
    message_id: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.message_id:
            self.message_id = f"msg-{int(datetime.now(timezone.utc).timestamp() * 1000)}"

    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "from": self.from_leader,
            "to": self.to_leader,
            "subject": self.subject,
            "body": self.body,
            "timestamp": self.timestamp,
            "ticket_id": self.ticket_id,
        }

    def to_markdown(self) -> str:
        return (
            f"### Inter-Leader Message: {self.message_id}\n"
            f"- **From:** {self.from_leader}\n"
            f"- **To:** {self.to_leader}\n"
            f"- **Subject:** {self.subject}\n"
            f"- **Timestamp:** {self.timestamp}\n"
            f"- **Ticket:** {self.ticket_id or 'N/A'}\n"
            f"\n{self.body}\n"
        )


class MessageBus:
    """Inter-leader message bus. All messages are logged and reviewable."""

    def __init__(self):
        self.messages: list[LeaderMessage] = []
        self.inbox: dict[str, list[LeaderMessage]] = {}  # by leader name

    def send(self, from_leader: str, to_leader: str, subject: str, body: str, ticket_id: str = "") -> LeaderMessage:
        """Send a message from one leader to another. Returns the message."""
        msg = LeaderMessage(
            from_leader=from_leader,
            to_leader=to_leader,
            subject=subject,
            body=body,
            ticket_id=ticket_id,
        )
        self.messages.append(msg)
        if to_leader not in self.inbox:
            self.inbox[to_leader] = []
        self.inbox[to_leader].append(msg)
        print(f"  📨 {from_leader} → {to_leader}: {subject}")
        return msg

    def receive(self, leader: str) -> list[LeaderMessage]:
        """Get all messages for a leader (and clear the inbox)."""
        msgs = self.inbox.get(leader, [])
        self.inbox[leader] = []
        return msgs

    def get_all_messages(self) -> list[LeaderMessage]:
        """Get all messages (for worklog recording)."""
        return self.messages

    def to_markdown(self) -> str:
        """Render all messages as markdown (for the worklog)."""
        if not self.messages:
            return "(no inter-leader messages)\n"
        lines = ["## Inter-Leader Messages\n"]
        for msg in self.messages:
            lines.append(msg.to_markdown())
        return "\n".join(lines)
