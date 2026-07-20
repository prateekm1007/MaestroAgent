"""Demo data seeder — P0-3 fix (audit V5 2026-07-15).

The audit found that the first-run experience is empty — "watching quietly"
with zero data until manual signals are added. This makes the product feel
dead on arrival.

This module seeds a realistic demo corpus on first launch (when the DB has
zero signals). The corpus includes:
  - 3 people with active commitments
  - 1 stale commitment (triggers Whisper)
  - 1 completed commitment
  - 1 critical signal (triggers Whisper)
  - Realistic timestamps (recent, so they appear in The Moment)

The seeder is idempotent — it only runs when the signals table is empty.
It assigns all demo signals to the 'bootstrap' user (the default for
shared-token mode). Real users who register get their own empty state
and won't see demo data.

Usage (called from api.py lifespan):
    from maestro_personal_shell.demo_seeder import seed_demo_data_if_empty
    seeded = seed_demo_data_if_empty()
    if seeded:
        logger.info("Demo data seeded (%d signals)", seeded)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# Demo corpus — realistic personal intelligence scenario
# 3 people, 5 projects, 12 signals covering commitments, completions,
# stale items, and a critical event. All timestamps are relative to now
# so they always appear "recent" on first launch.
DEMO_SIGNALS: list[dict[str, Any]] = [
    # --- Maria Garcia (client) — active commitment + completion ---
    {
        "entity": "Maria Garcia",
        "text": "I will send the pricing proposal to Maria by Friday.",
        "signal_type": "commitment_made",
        "days_ago": 3,
    },
    {
        "entity": "Maria Garcia",
        "text": "Maria confirmed she received the pricing proposal.",
        "signal_type": "reported_statement",
        "days_ago": 1,
    },

    # --- Alex Chen (engineer) — stale commitment (triggers Whisper) ---
    {
        "entity": "Alex Chen",
        "text": "I will review the auth module PR by Tuesday.",
        "signal_type": "commitment_made",
        "days_ago": 8,  # 8 days ago = stale (past 3-day threshold)
    },
    {
        "entity": "Alex Chen",
        "text": "Auth module PR is ready for review — linked PR #142.",
        "signal_type": "reported_statement",
        "days_ago": 7,
    },

    # --- Jamie Lee (designer) — completed commitment ---
    {
        "entity": "Jamie Lee",
        "text": "I will deliver the design mockups by Wednesday.",
        "signal_type": "commitment_made",
        "days_ago": 5,
    },
    {
        "entity": "Jamie Lee",
        "text": "Design mockups delivered — 12 screens uploaded to Figma.",
        "signal_type": "reported_statement",
        "days_ago": 2,
    },

    # --- Sam Rivera (PM) — approaching deadline ---
    {
        "entity": "Sam Rivera",
        "text": "I will finalize the Q3 roadmap presentation by next Monday.",
        "signal_type": "commitment_made",
        "days_ago": 4,
    },

    # --- Critical signal (triggers Whisper) ---
    {
        "entity": "Globex Corp",
        "text": "Globex Corp is threatening to churn — unhappy with delivery delays.",
        "signal_type": "alert",
        "days_ago": 1,
    },

    # --- Follow-up needed ---
    {
        "entity": "Priya Patel",
        "text": "Need to follow up with Priya on the API documentation.",
        "signal_type": "follow_up.required",
        "days_ago": 6,
    },
]


def seed_demo_data_if_empty(user_email: str = "bootstrap") -> int:
    """Seed demo data if the signals table is empty.

    Also seeds for 'default@personal.local' (the demo-bypass-token user)
    so the demo mode shows data immediately.

    Args:
        user_email: The user to assign demo signals to. Defaults to
            'bootstrap' (the shared-token user). Real registered users
            get their own empty state.

    Returns:
        Number of signals seeded (0 if table was not empty).
    """
    from maestro_personal_shell.db_util import get_db_conn, default_sqlite_path
    from maestro_personal_shell.api import save_signal_to_db, init_db

    # Ensure DB + tables exist
    init_db()

    db_path = default_sqlite_path()
    db = get_db_conn(db_path)

    # Check if there are ANY signals for this user
    try:
        count = db.execute(
            "SELECT COUNT(*) FROM signals WHERE user_email = ?",
            (user_email,),
        ).fetchone()[0]
    except Exception as e:
        db.close()
        logger.warning("Demo seeder: could not count signals: %s", e)
        return 0
    finally:
        db.close()

    if count > 0:
        logger.info("Demo seeder: %d signals already exist for %s — skipping", count, user_email)
        return 0

    # Seed the demo corpus
    now = datetime.now(timezone.utc)
    seeded = 0
    for sig in DEMO_SIGNALS:
        timestamp = (now - timedelta(days=sig["days_ago"])).isoformat()
        signal_id = f"demo_{seeded+1}_{int(now.timestamp())}"
        signal = {
            "signal_id": signal_id,
            "entity": sig["entity"],
            "text": sig["text"],
            "signal_type": sig["signal_type"],
            "timestamp": timestamp,
            "metadata": {"source": "demo_seed"},
        }
        try:
            save_signal_to_db(signal, db_path=db_path, user_email=user_email)
            seeded += 1
        except Exception as e:
            logger.warning("Demo seeder: failed to save signal %d: %s", seeded + 1, e)

    if seeded > 0:
        logger.info("Demo seeder: seeded %d demo signals for %s", seeded, user_email)

        # Fix (P0 — audit 2026-07-18): also seed for 'default@personal.local'
        # so the web app user (who logs in as default@personal.local when
        # using the shared token) sees demo data immediately. This was removed
        # in commit 14a2337 to stop fabrication, but it broke the web app's
        # demo experience — the web user had 0 signals → 0 whispers.
        # The demo data IS legitimate (labeled with metadata.source=demo_seed).
        if user_email != "default@personal.local":
            for i, sig in enumerate(DEMO_SIGNALS):
                timestamp = (now - timedelta(days=sig["days_ago"])).isoformat()
                signal_id = f"demo_dpl_{i}_{int(now.timestamp())}"
                signal = {
                    "signal_id": signal_id,
                    "entity": sig["entity"],
                    "text": sig["text"],
                    "signal_type": sig["signal_type"],
                    "timestamp": timestamp,
                    "metadata": {"source": "demo_seed"},
                }
                try:
                    save_signal_to_db(signal, db_path=db_path, user_email="default@personal.local")
                except Exception as e:
                    logger.debug("save_signal_to_db failed: %s", e)
            logger.info("Demo seeder: also seeded for default@personal.local")

        # Rebuild FTS index so the new signals are searchable
        try:
            from maestro_personal_shell.semantic_retrieval import rebuild_fts_index
            rebuild_fts_index()
        except Exception as e:
            logger.warning("Demo seeder: FTS rebuild failed (non-fatal): %s", e)

        # F3 fix (auditor P24 cross-surface coherence): populate the
        # personal knowledge graph for seeded entities. Previously the
        # graph_entities/graph_edges tables were empty because the seeder
        # used save_signal_to_db directly, bypassing the graph population
        # in POST /api/signals. This caused /api/graph/entity/Alex%20Chen
        # to return exists=false for entities that clearly exist in signals.
        try:
            from maestro_personal_shell.personal_graph import PersonalGraph
            for target_email in ([user_email, "default@personal.local"]
                                 if user_email != "default@personal.local"
                                 else ["default@personal.local"]):
                graph = PersonalGraph(user_email=target_email)
                for sig in DEMO_SIGNALS:
                    entity = sig["entity"]
                    graph.add_entity(entity, entity_type="contact", user_email=target_email)
                    # Add signal edge
                    graph.add_edge(
                        source_entity=entity,
                        edge_type="signal",
                        topic=sig["text"][:100],
                        confidence=0.5,
                        metadata={"source": "demo_seed", "signal_type": sig["signal_type"]},
                    )
                    # Add commitment edge if it's a commitment
                    if sig["signal_type"] in ("commitment_made", "personal.commitment", "personal.promise"):
                        graph.add_edge(
                            source_entity=entity,
                            edge_type="commitment",
                            topic=sig["text"][:100],
                            confidence=0.5,
                            metadata={"source": "demo_seed"},
                        )
            logger.info("Demo seeder: populated graph for %d entities", len(DEMO_SIGNALS))
        except Exception as e:
            logger.warning("Demo seeder: graph population failed (non-fatal): %s", e)

    return seeded
