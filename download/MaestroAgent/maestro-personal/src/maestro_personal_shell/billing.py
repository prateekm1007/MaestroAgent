"""
Billing — freemium monetization for Maestro Personal (v3.1).

Tiers:
  - free: 1 user, 3 connectors, 30-day history
  - pro: $15/mo, unlimited connectors, unlimited history, Whisper push
  - team: $12/user/mo, shared situations, team Briefing

In production, tier changes are triggered by:
  - Stripe webhooks (web payments)
  - RevenueCat callbacks (mobile IAP)

For v1 dogfood, tier is set manually via /api/billing/upgrade.
"""

from __future__ import annotations

import sqlite3
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _get_db_path() -> str:
    import os
    return os.environ.get(
        "MAESTRO_PERSONAL_DB",
        str(__import__("pathlib").Path(__file__).resolve().parent / "personal.db"),
    )


def init_billing_db(db_path: str | None = None) -> None:
    """Initialize billing tables."""
    path = db_path or _get_db_path()
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS billing (
            user_id TEXT PRIMARY KEY DEFAULT 'default',
            tier TEXT NOT NULL DEFAULT 'free',
            stripe_customer_id TEXT,
            revenuecat_user_id TEXT,
            updated_at TEXT NOT NULL
        )
    """)
    # Insert default row if not exists
    existing = conn.execute("SELECT user_id FROM billing WHERE user_id = 'default'").fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO billing (user_id, tier, updated_at) VALUES ('default', 'free', ?)",
            (datetime.now(timezone.utc).isoformat(),),
        )
    conn.commit()
    conn.close()


TIER_LIMITS = {
    "free": {
        "connectors": 3,
        "history_days": 30,
        "whisper_push": False,
        "team_features": False,
        "price": "$0",
    },
    "pro": {
        "connectors": -1,  # unlimited
        "history_days": -1,  # unlimited
        "whisper_push": True,
        "team_features": False,
        "price": "$15/mo",
    },
    "team": {
        "connectors": -1,
        "history_days": -1,
        "whisper_push": True,
        "team_features": True,
        "price": "$12/user/mo",
    },
}


def get_user_tier(db_path: str | None = None) -> str:
    """Get the current user's billing tier."""
    path = db_path or _get_db_path()
    init_billing_db(path)
    conn = sqlite3.connect(path)
    row = conn.execute(
        "SELECT tier FROM billing WHERE user_id = 'default'"
    ).fetchone()
    conn.close()
    return row[0] if row else "free"


def set_user_tier(tier: str, db_path: str | None = None) -> None:
    """Set the user's billing tier."""
    if tier not in ("free", "pro", "team"):
        raise ValueError(f"Invalid tier: {tier}")
    path = db_path or _get_db_path()
    init_billing_db(path)
    conn = sqlite3.connect(path)
    conn.execute(
        "UPDATE billing SET tier = ?, updated_at = ? WHERE user_id = 'default'",
        (tier, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def get_tier_limits(tier: str) -> dict[str, Any]:
    """Get the limits for a billing tier."""
    return TIER_LIMITS.get(tier, TIER_LIMITS["free"])


def check_connector_limit(current_count: int, tier: str | None = None) -> bool:
    """Check if the user can add another connector.

    Returns True if within limit, False if exceeded.
    """
    t = tier or get_user_tier()
    limits = get_tier_limits(t)
    limit = limits["connectors"]
    if limit == -1:
        return True  # unlimited
    return current_count < limit


def check_history_limit(signal_age_days: int, tier: str | None = None) -> bool:
    """Check if a signal is within the history limit for the tier.

    Returns True if the signal should be retained, False if it should be
    pruned (free tier: 30-day history).
    """
    t = tier or get_user_tier()
    limits = get_tier_limits(t)
    limit = limits["history_days"]
    if limit == -1:
        return True  # unlimited
    return signal_age_days <= limit
