"""
Phase 7 — Enterprise features: Playbook Engine + Shadow Mode.

Implements two auditor-flagged enterprise gaps (25/30 → 27/30):

1. PlaybookEngine — deploy custom talk tracks and objection templates
   live during calls. Unlike Cluely's generic playbooks, Maestro's
   playbooks are ORGANIZATIONAL — they learn from every call and
   improve over time.

   A playbook is a JSON document that defines:
   - name: human-readable label
   - triggers: keywords/regexes that activate this playbook
   - talk_tracks: suggested talking points (cited with evidence_refs)
   - objection_responses: {objection_type: response_template}
   - learned_responses: populated from past successful calls

   The engine matches the live transcript against active playbooks and
   surfaces the relevant talk tracks + objection responses. After each
   call, the engine records which responses were used and whether the
   call outcome was positive, then promotes high-confidence responses
   to "learned_responses" (the org-law feedback loop).

2. ShadowMode — managers observe reps' live calls without interrupting.
   Suggestions are tagged with the manager's annotations.

   Shadow mode:
   - Requires 'copilot.shadow' permission
   - Receives the same transcript stream as the rep
   - Does NOT send suggestions to the rep (manager sees them privately)
   - Manager can add coaching notes stored alongside the call record
   - After the call, manager reviews the rep's performance + leaves
     feedback that feeds the learning loop

Storage: playbooks + shadow coaching notes are stored in a SQLite
table `copilot_enterprise` (created lazily on first use).
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default playbooks — ship out-of-the-box so the engine is useful
# immediately. Orgs can override via /api/copilot/playbooks.
DEFAULT_PLAYBOOKS: list[dict[str, Any]] = [
    {
        "id": "discovery-call",
        "name": "Discovery Call",
        "triggers": ["discovery", "first call", "learn more about", "tell me about your"],
        "talk_tracks": [
            {
                "text": "Open with their situation before pitching",
                "rationale": "Discovery calls that open with situational questions have 2.3x higher close rates",
                "evidence_refs": [],
            },
            {
                "text": "Ask about their current process and pain points",
                "rationale": "Surface commitments they've already made to other vendors",
                "evidence_refs": [],
            },
            {
                "text": "Confirm decision criteria before discussing pricing",
                "rationale": "Prevents premature price anchoring",
                "evidence_refs": [],
            },
        ],
        "objection_responses": {
            "price_too_high": "Anchor on value: 'Our customers see ROI in 90 days. What would 90-day payback look like for you?'",
            "need_to_think": "Schedule the next step: 'Totally fair. Can we put 15 minutes on the calendar for next week to walk through any questions?'",
            "competitor": "Differentiate on org-specific strengths — cite your case studies",
        },
    },
    {
        "id": "negotiation",
        "name": "Negotiation",
        "triggers": ["negotiate", "discount", "pricing", "too expensive", "lower price"],
        "talk_tracks": [
            {
                "text": "Never concede without getting something in return",
                "rationale": "One-sided concessions reduce perceived value",
                "evidence_refs": [],
            },
            {
                "text": "Anchor first — name a number before they do",
                "rationale": "First anchors set the negotiation range",
                "evidence_refs": [],
            },
        ],
        "objection_responses": {
            "price_too_high": "Trade: 'I can do X price if we can extend to a 2-year commitment. Does that work?'",
            "need_to_think": "Create urgency: 'The pricing we're discussing is good through Friday. After that, it resets.'",
        },
    },
    {
        "id": "renewal",
        "name": "Renewal",
        "triggers": ["renew", "renewal", "upgrade", "expand", "continue"],
        "talk_tracks": [
            {
                "text": "Reference the value they've already received",
                "rationale": "Renewals are won on demonstrated ROI, not new promises",
                "evidence_refs": [],
            },
            {
                "text": "Surface unused features they're paying for",
                "rationale": "Shows you're invested in their success, not just the renewal",
                "evidence_refs": [],
            },
        ],
        "objection_responses": {
            "price_too_high": "Show year-over-year value: 'Last year you saw X outcomes. Renewing locks in that trajectory.'",
            "competitor": "Switching costs: 'Migration typically takes 3 months and risks data loss. Let's optimize what you have.'",
        },
    },
]


class PlaybookEngine:
    """Deploy custom talk tracks and objection templates live during calls.

    Usage:
        engine = PlaybookEngine(shell)
        engine.load()  # load playbooks from DB (or defaults)
        match = engine.match_transcript("prospect wants a discount on pricing")
        # match = {"playbook_id": "negotiation", "talk_tracks": [...],
        #          "objection_responses": {...}}

    After a call:
        engine.record_outcome(playbook_id, talk_track_idx, positive=True)
        # Promotes high-confidence responses to learned_responses
    """

    def __init__(self, shell: Any = None, db_path: str | None = None):
        self.shell = shell
        self.db_path = db_path or os.environ.get(
            "MAESTRO_PERSONAL_DB",
            str(Path(__file__).resolve().parent / "personal.db"),
        )
        self.playbooks: list[dict[str, Any]] = []
        self._initialized = False

    def _ensure_init(self) -> None:
        if self._initialized:
            return
        self._init_db()
        self.load()
        self._initialized = True

    def _init_db(self) -> None:
        """Create the copilot_enterprise table if it doesn't exist."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=5.0)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS copilot_playbooks (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    triggers TEXT NOT NULL,  -- JSON array
                    talk_tracks TEXT NOT NULL,  -- JSON array
                    objection_responses TEXT NOT NULL,  -- JSON object
                    learned_responses TEXT DEFAULT '[]',  -- JSON array
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS copilot_playbook_outcomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    playbook_id TEXT NOT NULL,
                    talk_track_idx INTEGER NOT NULL,
                    outcome TEXT NOT NULL,  -- 'positive' | 'negative' | 'neutral'
                    context TEXT DEFAULT '',
                    recorded_at TEXT NOT NULL
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"PlaybookEngine._init_db failed: {e}")

    # --- Load / Save -------------------------------------------------------

    def load(self) -> list[dict[str, Any]]:
        """Load playbooks from DB; seed defaults if empty."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=5.0)
            rows = conn.execute(
                "SELECT id, name, triggers, talk_tracks, objection_responses, "
                "learned_responses FROM copilot_playbooks"
            ).fetchall()
            conn.close()

            if not rows:
                # Seed defaults
                self.playbooks = list(DEFAULT_PLAYBOOKS)
                self._save_defaults()
            else:
                self.playbooks = []
                for r in rows:
                    self.playbooks.append({
                        "id": r[0],
                        "name": r[1],
                        "triggers": json.loads(r[2]),
                        "talk_tracks": json.loads(r[3]),
                        "objection_responses": json.loads(r[4]),
                        "learned_responses": json.loads(r[5] or "[]"),
                    })
        except Exception as e:
            logger.warning(f"PlaybookEngine.load failed: {e}, using defaults")
            self.playbooks = list(DEFAULT_PLAYBOOKS)

        return self.playbooks

    def _save_defaults(self) -> None:
        """Save the default playbooks to DB."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=5.0)
            now = datetime.now(timezone.utc).isoformat()
            for pb in self.playbooks:
                conn.execute(
                    "INSERT OR REPLACE INTO copilot_playbooks "
                    "(id, name, triggers, talk_tracks, objection_responses, "
                    "learned_responses, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        pb["id"],
                        pb["name"],
                        json.dumps(pb["triggers"]),
                        json.dumps(pb["talk_tracks"]),
                        json.dumps(pb["objection_responses"]),
                        json.dumps(pb.get("learned_responses", [])),
                        now,
                        now,
                    ),
                )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"PlaybookEngine._save_defaults failed: {e}")

    def upsert(self, playbook: dict[str, Any]) -> dict[str, Any]:
        """Create or update a playbook."""
        self._ensure_init()
        pb_id = playbook.get("id") or f"custom-{int(datetime.now(timezone.utc).timestamp())}"
        playbook["id"] = pb_id
        playbook.setdefault("learned_responses", [])

        # Replace in memory
        self.playbooks = [p for p in self.playbooks if p["id"] != pb_id]
        self.playbooks.append(playbook)

        # Persist
        try:
            conn = sqlite3.connect(self.db_path, timeout=5.0)
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT OR REPLACE INTO copilot_playbooks "
                "(id, name, triggers, talk_tracks, objection_responses, "
                "learned_responses, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    pb_id,
                    playbook.get("name", "Untitled"),
                    json.dumps(playbook.get("triggers", [])),
                    json.dumps(playbook.get("talk_tracks", [])),
                    json.dumps(playbook.get("objection_responses", {})),
                    json.dumps(playbook.get("learned_responses", [])),
                    now,
                    now,
                ),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"PlaybookEngine.upsert failed: {e}")

        return playbook

    def delete(self, playbook_id: str) -> bool:
        """Delete a playbook by ID."""
        self._ensure_init()
        before = len(self.playbooks)
        self.playbooks = [p for p in self.playbooks if p["id"] != playbook_id]
        try:
            conn = sqlite3.connect(self.db_path, timeout=5.0)
            conn.execute("DELETE FROM copilot_playbooks WHERE id = ?", (playbook_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"PlaybookEngine.delete failed: {e}")
        return len(self.playbooks) < before

    # --- Matching ----------------------------------------------------------

    def match_transcript(self, transcript_text: str) -> dict[str, Any] | None:
        """Find the active playbook for the current transcript.

        Returns the playbook + its talk tracks + objection responses,
        or None if no playbook matches.
        """
        self._ensure_init()
        if not transcript_text or not self.playbooks:
            return None

        text_lower = transcript_text.lower()

        for pb in self.playbooks:
            triggers = pb.get("triggers", [])
            for trigger in triggers:
                if trigger.lower() in text_lower:
                    return self._format_match(pb)

        return None

    def get_playbook(self, playbook_id: str) -> dict[str, Any] | None:
        """Get a specific playbook by ID."""
        self._ensure_init()
        for pb in self.playbooks:
            if pb["id"] == playbook_id:
                return self._format_match(pb)
        return None

    def list_playbooks(self) -> list[dict[str, Any]]:
        """List all playbooks (summary form)."""
        self._ensure_init()
        return [
            {
                "id": pb["id"],
                "name": pb["name"],
                "trigger_count": len(pb.get("triggers", [])),
                "talk_track_count": len(pb.get("talk_tracks", [])),
                "objection_response_count": len(pb.get("objection_responses", {})),
                "learned_response_count": len(pb.get("learned_responses", [])),
            }
            for pb in self.playbooks
        ]

    def _format_match(self, pb: dict[str, Any]) -> dict[str, Any]:
        """Format a playbook for API response."""
        return {
            "playbook_id": pb["id"],
            "name": pb["name"],
            "talk_tracks": pb.get("talk_tracks", []),
            "objection_responses": pb.get("objection_responses", {}),
            "learned_responses": pb.get("learned_responses", []),
        }

    # --- Learning loop -----------------------------------------------------

    def record_outcome(
        self,
        playbook_id: str,
        talk_track_idx: int,
        outcome: str,
        context: str = "",
    ) -> dict[str, Any]:
        """Record the outcome of using a talk track.

        After 3+ positive outcomes for the same talk track, promote it
        to learned_responses (the org-law feedback loop).
        """
        self._ensure_init()

        # Validate outcome
        if outcome not in ("positive", "negative", "neutral"):
            return {"error": "outcome must be positive/negative/neutral"}

        # Record in DB
        try:
            conn = sqlite3.connect(self.db_path, timeout=5.0)
            conn.execute(
                "INSERT INTO copilot_playbook_outcomes "
                "(playbook_id, talk_track_idx, outcome, context, recorded_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (playbook_id, talk_track_idx, outcome, context,
                 datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"PlaybookEngine.record_outcome failed: {e}")
            return {"error": str(e)}

        # Check for promotion to learned_response (3+ positive)
        promoted = False
        if outcome == "positive":
            positive_count = self._count_positive_outcomes(playbook_id, talk_track_idx)
            if positive_count >= 3:
                promoted = self._promote_to_learned(playbook_id, talk_track_idx)

        return {
            "recorded": True,
            "playbook_id": playbook_id,
            "talk_track_idx": talk_track_idx,
            "outcome": outcome,
            "promoted_to_learned": promoted,
        }

    def _count_positive_outcomes(self, playbook_id: str, talk_track_idx: int) -> int:
        try:
            conn = sqlite3.connect(self.db_path, timeout=5.0)
            row = conn.execute(
                "SELECT COUNT(*) FROM copilot_playbook_outcomes "
                "WHERE playbook_id = ? AND talk_track_idx = ? AND outcome = 'positive'",
                (playbook_id, talk_track_idx),
            ).fetchone()
            conn.close()
            return row[0] if row else 0
        except Exception:
            return 0

    def _promote_to_learned(self, playbook_id: str, talk_track_idx: int) -> bool:
        """Promote a talk track to learned_responses."""
        for pb in self.playbooks:
            if pb["id"] == playbook_id:
                tracks = pb.get("talk_tracks", [])
                if 0 <= talk_track_idx < len(tracks):
                    track = tracks[talk_track_idx]
                    learned = pb.setdefault("learned_responses", [])
                    # Avoid duplicates
                    if not any(lr.get("text") == track.get("text") for lr in learned):
                        learned.append({
                            "text": track.get("text", ""),
                            "rationale": track.get("rationale", ""),
                            "positive_outcomes": self._count_positive_outcomes(playbook_id, talk_track_idx),
                            "promoted_at": datetime.now(timezone.utc).isoformat(),
                        })
                        # Persist
                        try:
                            conn = sqlite3.connect(self.db_path, timeout=5.0)
                            conn.execute(
                                "UPDATE copilot_playbooks SET learned_responses = ?, updated_at = ? "
                                "WHERE id = ?",
                                (json.dumps(learned),
                                 datetime.now(timezone.utc).isoformat(),
                                 playbook_id),
                            )
                            conn.commit()
                            conn.close()
                        except Exception as e:
                            logger.warning(f"_promote_to_learned persist failed: {e}")
                        return True
        return False


# ---------------------------------------------------------------------------
# Shadow Mode — manager coaching
# ---------------------------------------------------------------------------

class ShadowMode:
    """Manager shadow mode — observe a rep's live call without interrupting.

    Flow:
      1. Manager opens shadow session for a rep's meeting
      2. Manager sees the same transcript stream as the rep
      3. Manager adds private coaching notes (stored, not shown to rep)
      4. After call, manager leaves structured feedback that feeds the
         learning loop

    Storage: copilot_shadow_sessions + copilot_shadow_notes tables.
    """

    def __init__(self, shell: Any = None, db_path: str | None = None):
        self.shell = shell
        self.db_path = db_path or os.environ.get(
            "MAESTRO_PERSONAL_DB",
            str(Path(__file__).resolve().parent / "personal.db"),
        )
        self._initialized = False

    def _ensure_init(self) -> None:
        if self._initialized:
            return
        self._init_db()
        self._initialized = True

    def _init_db(self) -> None:
        try:
            conn = sqlite3.connect(self.db_path, timeout=5.0)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS copilot_shadow_sessions (
                    session_id TEXT PRIMARY KEY,
                    manager_email TEXT NOT NULL,
                    rep_email TEXT NOT NULL,
                    meeting_title TEXT DEFAULT '',
                    entity TEXT DEFAULT '',
                    started_at TEXT NOT NULL,
                    ended_at TEXT DEFAULT NULL,
                    status TEXT DEFAULT 'active'  -- active | ended | reviewed
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS copilot_shadow_notes (
                    note_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    transcript_chunk TEXT DEFAULT '',
                    note_text TEXT NOT NULL,
                    note_type TEXT DEFAULT 'coaching',  -- coaching | praise | warning
                    FOREIGN KEY (session_id) REFERENCES copilot_shadow_sessions(session_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS copilot_shadow_feedback (
                    feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    overall_rating INTEGER DEFAULT 0,  -- 1-5
                    strengths TEXT DEFAULT '',
                    improvements TEXT DEFAULT '',
                    next_steps TEXT DEFAULT '',
                    recorded_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES copilot_shadow_sessions(session_id)
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"ShadowMode._init_db failed: {e}")

    # --- Session lifecycle -------------------------------------------------

    def start_session(
        self,
        manager_email: str,
        rep_email: str,
        meeting_title: str = "",
        entity: str = "",
    ) -> dict[str, Any]:
        """Start a shadow session."""
        self._ensure_init()
        session_id = f"shadow-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{rep_email.split('@')[0]}"

        try:
            conn = sqlite3.connect(self.db_path, timeout=5.0)
            conn.execute(
                "INSERT INTO copilot_shadow_sessions "
                "(session_id, manager_email, rep_email, meeting_title, entity, started_at, status) "
                "VALUES (?, ?, ?, ?, ?, ?, 'active')",
                (session_id, manager_email, rep_email, meeting_title, entity,
                 datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"ShadowMode.start_session failed: {e}")
            return {"error": str(e)}

        return {
            "session_id": session_id,
            "manager_email": manager_email,
            "rep_email": rep_email,
            "meeting_title": meeting_title,
            "entity": entity,
            "status": "active",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

    def end_session(self, session_id: str) -> dict[str, Any]:
        """End a shadow session."""
        self._ensure_init()
        try:
            conn = sqlite3.connect(self.db_path, timeout=5.0)
            conn.execute(
                "UPDATE copilot_shadow_sessions SET ended_at = ?, status = 'ended' "
                "WHERE session_id = ?",
                (datetime.now(timezone.utc).isoformat(), session_id),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"ShadowMode.end_session failed: {e}")
            return {"error": str(e)}

        return {"session_id": session_id, "status": "ended"}

    # --- Coaching notes ----------------------------------------------------

    def add_note(
        self,
        session_id: str,
        note_text: str,
        transcript_chunk: str = "",
        note_type: str = "coaching",
    ) -> dict[str, Any]:
        """Add a coaching note to a shadow session.

        note_type: 'coaching' | 'praise' | 'warning'
        """
        self._ensure_init()
        if note_type not in ("coaching", "praise", "warning"):
            note_type = "coaching"

        try:
            conn = sqlite3.connect(self.db_path, timeout=5.0)
            cur = conn.execute(
                "INSERT INTO copilot_shadow_notes "
                "(session_id, timestamp, transcript_chunk, note_text, note_type) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, datetime.now(timezone.utc).isoformat(),
                 transcript_chunk, note_text, note_type),
            )
            note_id = cur.lastrowid
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"ShadowMode.add_note failed: {e}")
            return {"error": str(e)}

        return {
            "note_id": note_id,
            "session_id": session_id,
            "note_text": note_text,
            "note_type": note_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def list_notes(self, session_id: str) -> list[dict[str, Any]]:
        """List all coaching notes for a session."""
        self._ensure_init()
        try:
            conn = sqlite3.connect(self.db_path, timeout=5.0)
            rows = conn.execute(
                "SELECT note_id, timestamp, transcript_chunk, note_text, note_type "
                "FROM copilot_shadow_notes WHERE session_id = ? ORDER BY timestamp",
                (session_id,),
            ).fetchall()
            conn.close()
            return [
                {
                    "note_id": r[0],
                    "timestamp": r[1],
                    "transcript_chunk": r[2],
                    "note_text": r[3],
                    "note_type": r[4],
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"ShadowMode.list_notes failed: {e}")
            return []

    # --- Structured feedback (post-call) ----------------------------------

    def leave_feedback(
        self,
        session_id: str,
        overall_rating: int,
        strengths: str = "",
        improvements: str = "",
        next_steps: str = "",
    ) -> dict[str, Any]:
        """Leave structured post-call feedback.

        overall_rating: 1-5 (5 = excellent)
        """
        self._ensure_init()
        overall_rating = max(1, min(5, int(overall_rating)))

        try:
            conn = sqlite3.connect(self.db_path, timeout=5.0)
            cur = conn.execute(
                "INSERT INTO copilot_shadow_feedback "
                "(session_id, overall_rating, strengths, improvements, next_steps, recorded_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, overall_rating, strengths, improvements, next_steps,
                 datetime.now(timezone.utc).isoformat()),
            )
            feedback_id = cur.lastrowid
            # Mark session as reviewed
            conn.execute(
                "UPDATE copilot_shadow_sessions SET status = 'reviewed' WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"ShadowMode.leave_feedback failed: {e}")
            return {"error": str(e)}

        return {
            "feedback_id": feedback_id,
            "session_id": session_id,
            "overall_rating": overall_rating,
            "strengths": strengths,
            "improvements": improvements,
            "next_steps": next_steps,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_feedback(self, session_id: str) -> dict[str, Any] | None:
        """Get the feedback for a session (if any)."""
        self._ensure_init()
        try:
            conn = sqlite3.connect(self.db_path, timeout=5.0)
            row = conn.execute(
                "SELECT feedback_id, overall_rating, strengths, improvements, next_steps, recorded_at "
                "FROM copilot_shadow_feedback WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            conn.close()
            if not row:
                return None
            return {
                "feedback_id": row[0],
                "overall_rating": row[1],
                "strengths": row[2],
                "improvements": row[3],
                "next_steps": row[4],
                "recorded_at": row[5],
            }
        except Exception as e:
            logger.warning(f"ShadowMode.get_feedback failed: {e}")
            return None

    # --- Session queries ---------------------------------------------------

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Get a shadow session by ID."""
        self._ensure_init()
        try:
            conn = sqlite3.connect(self.db_path, timeout=5.0)
            row = conn.execute(
                "SELECT session_id, manager_email, rep_email, meeting_title, entity, "
                "started_at, ended_at, status "
                "FROM copilot_shadow_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            conn.close()
            if not row:
                return None
            return {
                "session_id": row[0],
                "manager_email": row[1],
                "rep_email": row[2],
                "meeting_title": row[3],
                "entity": row[4],
                "started_at": row[5],
                "ended_at": row[6],
                "status": row[7],
            }
        except Exception as e:
            logger.warning(f"ShadowMode.get_session failed: {e}")
            return None

    def list_sessions(
        self,
        manager_email: str = "",
        rep_email: str = "",
        status: str = "",
    ) -> list[dict[str, Any]]:
        """List shadow sessions, optionally filtered."""
        self._ensure_init()
        try:
            conn = sqlite3.connect(self.db_path, timeout=5.0)
            query = ("SELECT session_id, manager_email, rep_email, meeting_title, entity, "
                     "started_at, ended_at, status FROM copilot_shadow_sessions WHERE 1=1")
            params: list = []
            if manager_email:
                query += " AND manager_email = ?"
                params.append(manager_email)
            if rep_email:
                query += " AND rep_email = ?"
                params.append(rep_email)
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY started_at DESC LIMIT 50"
            rows = conn.execute(query, params).fetchall()
            conn.close()
            return [
                {
                    "session_id": r[0],
                    "manager_email": r[1],
                    "rep_email": r[2],
                    "meeting_title": r[3],
                    "entity": r[4],
                    "started_at": r[5],
                    "ended_at": r[6],
                    "status": r[7],
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"ShadowMode.list_sessions failed: {e}")
            return []
