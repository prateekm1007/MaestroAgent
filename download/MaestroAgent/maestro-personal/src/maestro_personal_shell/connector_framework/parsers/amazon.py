"""Amazon email parser — extracts delivery/order/return commitments from Amazon emails.

No OAuth needed. Amazon sends "ships by X", "delivery window Y", "return window closes Z"
emails that we already ingest via Gmail/Outlook. This parser recognizes them and
extracts structured commitment data with source:"amazon".
"""
from __future__ import annotations

import re
import logging
from datetime import datetime, timedelta, timezone

from maestro_personal_shell.connector_framework import Signal
from maestro_personal_shell.connector_framework.parsers import register_parser

logger = logging.getLogger(__name__)

AMAZON_SENDERS = re.compile(r"amazon|amazonses", re.IGNORECASE)


@register_parser(r"amazon\.com|@amazon|shipment.*amazon|order.*confirm", re.IGNORECASE)
def parse_amazon(signal: Signal) -> list[Signal]:
    """Extract Amazon delivery/order/return commitments from email signals."""
    text = signal.text
    signals = []

    # Delivery date: "Arriving by Friday, July 25" or "Estimated delivery: July 23-25"
    delivery_match = re.search(
        r"(?:arriving|delivery|deliver).{0,20}(by|:)\s*(.+?)(?:\.|$|\n)",
        text, re.IGNORECASE,
    )
    if delivery_match:
        date_str = delivery_match.group(2).strip()
        signals.append(Signal(
            source="amazon",
            source_id=f"amazon_delivery_{signal.source_id}",
            thread_id=signal.thread_id,
            entity="Amazon",
            text=f"Amazon delivery expected: {date_str}",
            timestamp=signal.timestamp,
            direction="commitment_theirs",
            metadata={
                "source": "amazon",
                "type": "delivery_promise",
                "promised_date": date_str,
                "original_from": signal.metadata.get("from", ""),
                "parent_signal_id": signal.source_id,
            },
            confidence=0.8,
        ))

    # Return window: "Return window closes on August 3" or "Return by Jul 28"
    return_match = re.search(
        r"(?:return\s+window|return\s+by|returns?\s+close).{0,20}(?:on|by)?\s*(.+?)(?:\.|$|\n)",
        text, re.IGNORECASE,
    )
    if return_match:
        date_str = return_match.group(1).strip()
        signals.append(Signal(
            source="amazon",
            source_id=f"amazon_return_{signal.source_id}",
            thread_id=signal.thread_id,
            entity="Amazon",
            text=f"Amazon return window closes: {date_str}",
            timestamp=signal.timestamp,
            direction="commitment_mine",
            metadata={
                "source": "amazon",
                "type": "return_deadline",
                "deadline": date_str,
                "original_from": signal.metadata.get("from", ""),
                "parent_signal_id": signal.source_id,
            },
            confidence=0.8,
        ))

    # Order confirmation: "Your order #12345 has been confirmed"
    order_match = re.search(r"order\s*[#:]?\s*(\w+).{0,30}(confirm|ship)", text, re.IGNORECASE)
    if order_match:
        order_id = order_match.group(1)
        signals.append(Signal(
            source="amazon",
            source_id=f"amazon_order_{order_id}_{signal.source_id}",
            thread_id=signal.thread_id,
            entity="Amazon",
            text=f"Amazon order {order_id} confirmed",
            timestamp=signal.timestamp,
            direction="commitment_theirs",
            metadata={
                "source": "amazon",
                "type": "order_confirmation",
                "order_id": order_id,
                "original_from": signal.metadata.get("from", ""),
                "parent_signal_id": signal.source_id,
            },
            confidence=0.7,
        ))

    if not signals:
        # No structured commitment found, but it IS from Amazon — record as FYI
        signals.append(Signal(
            source="amazon",
            source_id=f"amazon_fyi_{signal.source_id}",
            thread_id=signal.thread_id,
            entity="Amazon",
            text=f"Amazon notification: {text[:200]}",
            timestamp=signal.timestamp,
            direction="inbound",
            metadata={
                "source": "amazon",
                "type": "notification",
                "original_from": signal.metadata.get("from", ""),
                "parent_signal_id": signal.source_id,
            },
            confidence=0.3,
        ))

    return signals
