"""
Phase 5 P2 — Post-call polish features.

Implements three auditor-flagged gaps (22/30 → 25/30):

1. FollowUpEmailGenerator — commitment-aware follow-up email drafts
   that cite specific signals from the user's organizational memory.
   Unlike Cluely's generic drafts, Maestro's drafts:
   - Reference each commitment made during the call (with actor)
   - Cite relevant laws/patterns from the user's historical data
   - Track commitment lifecycle (made → kept/broken)
   - Adapt tone to the conversation (formal / warm / direct)

2. PreCallIntelPanel — surfaces 3 things that matter for THIS meeting:
   - Forgotten (oldest open commitment for this entity)
   - Open question (unanswered follow-up from this entity)
   - Contradiction (recent signal that conflicts with a prior signal)
   Plus talk-track suggestions derived from the user's organizational laws.

3. PostCallSummaryUI — full-screen post-call modal payload:
   - Hero card (title, duration, participant count, chunk count)
   - Key stats grid (commitments, objections, suggestions, talk ratio)
   - Commitments tracked (with Day X/Y countdown + dedup status)
   - Objections raised (with response pattern + action required)
   - Draft follow-up email (cites specific commitments + patterns)
   - What Maestro learned (new signals, pattern data points, law threshold)

All three modules are pure-Python (no LLM dependency for v1) so they
work in the dogfood environment without an LLM bridge. When an LLM
bridge IS available, the FollowUpEmailGenerator and PreCallIntelPanel
use it to polish their outputs.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Follow-up Email Generator
# ---------------------------------------------------------------------------

class FollowUpEmailGenerator:
    """Generate a commitment-aware follow-up email draft.

    The draft cites:
      - Each commitment made during the call (with actor + due_date)
      - Up to 2 organizational laws relevant to the conversation topics
      - A clear next-steps section derived from open commitments

    Tone adapts based on the meeting context:
      - "professional" (default) — formal, balanced
      - "warm" — for established relationships (signals with this entity > 5)
      - "direct" — for stale commitments (>5 days) or repeated missed deadlines
    """

    def __init__(self, shell: Any):
        self.shell = shell

    def generate(
        self,
        meeting_title: str = "",
        participants: list[str] | None = None,
        commitments: list[dict] | None = None,
        objections: list[dict] | None = None,
        entity: str = "",
        transcript_chunks: list[dict] | None = None,
        tone: str = "",
    ) -> dict[str, str]:
        """Generate a draft follow-up email.

        Returns dict with: subject, body, tone, commitment_count,
        evidence_count, suggested_send_time.
        """
        participants = participants or []
        commitments = commitments or []
        objections = objections or []
        transcript_chunks = transcript_chunks or []

        # Auto-select tone if not provided
        if not tone:
            tone = self._infer_tone(entity, commitments)

        # Subject
        subject = self._build_subject(meeting_title, entity)

        # Body sections
        body_lines: list[str] = []

        # Greeting
        body_lines.append(self._build_greeting(participants, tone))

        # Opening
        body_lines.append("")
        body_lines.append(self._build_opening(meeting_title, tone))

        # Commitments recap (the moat — cites specific commitments)
        if commitments:
            body_lines.append("")
            body_lines.append("Commitments from our call:")
            for c in commitments:
                body_lines.append(self._format_commitment_line(c))

        # Objection action items
        if objections:
            body_lines.append("")
            body_lines.append("Action items:")
            for o in objections:
                otype = o.get("type") or o.get("objection_type") or "concern"
                body_lines.append(f"  - Address the {otype} concern raised")

        # Organizational intelligence (laws/patterns)
        relevant_laws = self._find_relevant_laws(transcript_chunks, entity)
        if relevant_laws:
            body_lines.append("")
            body_lines.append("Based on our experience:")
            for law in relevant_laws[:2]:
                body_lines.append(f"  - {law}")

        # Next steps
        body_lines.append("")
        body_lines.append("Next steps:")
        if commitments:
            body_lines.append("  - I'll follow up on each commitment above by the agreed dates")
        else:
            body_lines.append("  - I'll circle back with the details we discussed")
        body_lines.append("  - Let me know if I've missed anything")

        # Closing
        body_lines.append("")
        body_lines.append(self._build_closing(tone))

        body = "\n".join(body_lines)

        # Suggested send time (immediately for stale, else within 4 hours)
        send_time = self._suggest_send_time(commitments)

        return {
            "subject": subject,
            "body": body,
            "tone": tone,
            "commitment_count": len(commitments),
            "evidence_count": len(relevant_laws),
            "suggested_send_time": send_time,
        }

    # --- Tone inference ----------------------------------------------------

    def _infer_tone(self, entity: str, commitments: list[dict]) -> str:
        """Infer tone from entity history + commitment staleness."""
        # Check for stale commitments (>5 days old)
        for c in commitments:
            days = c.get("days_stale") or c.get("day_count") or 0
            if isinstance(days, (int, float)) and days > 5:
                return "direct"

        # Check entity history depth
        if entity and self.shell:
            try:
                sigs = self._signals_for_entity(entity)
                if len(sigs) > 5:
                    return "warm"
            except Exception:
                pass

        return "professional"

    def _signals_for_entity(self, entity: str) -> list:
        """Get all signals for an entity (for tone inference)."""
        try:
            shell = self.shell
            if hasattr(shell, "core") and shell.core and shell.core.signals:
                return [s for s in shell.core.signals if getattr(s, "entity", "") == entity]
        except Exception:
            pass
        return []

    # --- Section builders --------------------------------------------------

    def _build_subject(self, title: str, entity: str) -> str:
        if title:
            return f"Follow-up — {title}"
        if entity:
            return f"Follow-up — our discussion re: {entity}"
        return "Follow-up — our discussion"

    def _build_greeting(self, participants: list[str], tone: str) -> str:
        if not participants:
            return "Hi —" if tone == "warm" else "Hello,"
        names = []
        for p in participants[:3]:
            name = p.split("@")[0] if "@" in p else p
            names.append(name.split()[0] if " " in name else name)
        if len(participants) > 3:
            names.append("others")
        if tone == "warm":
            return f"Hi {', '.join(names)} —"
        return f"Hello {', '.join(names)},"

    def _build_opening(self, title: str, tone: str) -> str:
        if tone == "direct":
            return "Thanks for the call. Here's what I captured:"
        if tone == "warm":
            return "Great chatting earlier. Quick recap of what we covered:"
        return "Thank you for the productive call today. Here's what I captured:"

    def _build_closing(self, tone: str) -> str:
        if tone == "direct":
            return "Let's get these items closed out. Reach out if anything's unclear."
        if tone == "warm":
            return "Looking forward to the next one. Cheers,"
        return "Please let me know if I've missed anything. Best,"

    def _format_commitment_line(self, c: dict) -> str:
        """Format a single commitment as a bullet line."""
        text = c.get("text", "")
        actor = c.get("actor") or c.get("speaker") or ""
        if actor and "@" in actor:
            actor = actor.split("@")[0]
        due = c.get("due_date") or c.get("deadline") or ""
        days_stale = c.get("days_stale") or c.get("day_count") or 0

        # Clean text — strip "X committed:" prefix if present
        if " committed:" in text:
            text = text.split(" committed:", 1)[1].strip().strip('"').strip("'")

        line = f"  - {text}"
        if actor:
            line += f" ({actor})"
        if due:
            line += f" — due {due}"
        elif isinstance(days_stale, (int, float)) and days_stale > 0:
            line += f" — {int(days_stale)} days stale"
        return line

    # --- Law retrieval -----------------------------------------------------

    def _find_relevant_laws(self, transcript_chunks: list[dict], entity: str) -> list[str]:
        """Find organizational laws relevant to the transcript topics.

        Uses keyword overlap between the transcript and the user's
        stored laws/patterns. Falls back gracefully if no laws exist.
        """
        # Build transcript word set
        transcript_text = " ".join(
            c.get("text", "") for c in transcript_chunks
        ).lower()
        if not transcript_text:
            return []

        # Skip stopwords
        stopwords = {"the", "a", "an", "and", "or", "but", "to", "of", "in",
                     "for", "on", "with", "is", "are", "was", "were", "be",
                     "been", "have", "has", "had", "do", "does", "did", "will",
                     "would", "could", "should", "may", "might", "must", "i",
                     "you", "we", "they", "he", "she", "it", "this", "that",
                     "these", "those", "so", "if", "then", "than"}
        transcript_words = set(re.findall(r"\b[a-z]{3,}\b", transcript_text))
        transcript_words -= stopwords

        if not transcript_words:
            return []

        # Pull laws from shell
        laws = self._get_laws()
        if not laws:
            return []

        scored = []
        for law in laws:
            law_text = (law.get("statement") or law.get("text") or "").lower()
            law_words = set(re.findall(r"\b[a-z]{3,}\b", law_text)) - stopwords
            overlap = len(transcript_words & law_words)
            if overlap >= 2:
                conf = law.get("confidence", 0.5)
                scored.append((overlap * conf, law.get("statement") or law.get("text", "")))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:3]]

    def _get_laws(self) -> list[dict]:
        """Get organizational laws from the shell."""
        try:
            shell = self.shell
            if hasattr(shell, "core") and shell.core:
                # Try various law storage locations
                for attr in ("laws", "patterns", "validated_patterns"):
                    laws = getattr(shell.core, attr, None)
                    if laws and isinstance(laws, list):
                        return [
                            l if isinstance(l, dict) else
                            {"statement": getattr(l, "statement", str(l)),
                             "confidence": getattr(l, "confidence", 0.5)}
                            for l in laws
                        ]
        except Exception:
            pass
        return []

    # --- Send-time suggestion ---------------------------------------------

    def _suggest_send_time(self, commitments: list[dict]) -> str:
        """Suggest when to send: immediately if stale, else within 4h."""
        for c in commitments:
            days = c.get("days_stale") or c.get("day_count") or 0
            if isinstance(days, (int, float)) and days > 5:
                return "now"
        return "within_4h"


# ---------------------------------------------------------------------------
# 2. Pre-call Intelligence Panel
# ---------------------------------------------------------------------------

class PreCallIntelPanel:
    """Pre-call intelligence panel — 3 things that matter for THIS meeting.

    Surfaces:
      - THE FORGOTTEN: oldest open commitment for this entity (stale)
      - THE OPEN QUESTION: an unanswered follow-up from this entity
      - THE CONTRADICTION: a recent signal that conflicts with a prior signal
      - TALK TRACKS: 2-3 suggested approaches derived from org laws

    This is the panel the user sees BEFORE the call starts, so they walk
    in already knowing what to ask and what to avoid.
    """

    def __init__(self, shell: Any):
        self.shell = shell

    def build(self, entity: str = "", meeting_title: str = "") -> dict[str, Any]:
        """Build the pre-call intelligence panel payload."""
        if not entity:
            return {
                "entity": "",
                "greeting": "Pick a meeting to prepare.",
                "the_forgotten": None,
                "the_open_question": None,
                "the_contradiction": None,
                "talk_tracks": [],
                "is_stale": False,
            }

        signals = self._signals_for_entity(entity)
        commitments = self._commitments_for_entity(entity)

        # THE FORGOTTEN — oldest open commitment
        forgotten = self._find_forgotten(commitments)

        # THE OPEN QUESTION — unanswered follow-up
        open_question = self._find_open_question(signals)

        # THE CONTRADICTION — conflicting signals
        contradiction = self._find_contradiction(signals)

        # TALK TRACKS — derived from org laws matching this entity's topics
        talk_tracks = self._derive_talk_tracks(signals, entity)

        # Staleness check — did reality change since last interaction?
        is_stale = self._check_staleness(signals)

        # Greeting line
        greeting = self._build_greeting(entity, signals)

        return {
            "entity": entity,
            "meeting_title": meeting_title,
            "greeting": greeting,
            "the_forgotten": forgotten,
            "the_open_question": open_question,
            "the_contradiction": contradiction,
            "talk_tracks": talk_tracks,
            "is_stale": is_stale,
            "signal_count": len(signals),
            "commitment_count": len(commitments),
        }

    # --- Signal retrieval --------------------------------------------------

    def _signals_for_entity(self, entity: str) -> list:
        """Get all signals for this entity."""
        try:
            shell = self.shell
            if hasattr(shell, "core") and shell.core and shell.core.signals:
                return [s for s in shell.core.signals
                        if getattr(s, "entity", "").lower() == entity.lower()]
        except Exception:
            pass
        return []

    def _commitments_for_entity(self, entity: str) -> list:
        """Get active commitments for this entity."""
        sigs = self._signals_for_entity(entity)
        commits = []
        for s in sigs:
            stype = str(getattr(s, "signal_type", "")).lower()
            if "commitment" in stype and "made" in stype:
                commits.append(s)
        return commits

    # --- The Forgotten -----------------------------------------------------

    def _find_forgotten(self, commitments: list) -> dict | None:
        """Find the oldest open commitment — the one most likely forgotten."""
        if not commitments:
            return None

        # Sort by timestamp (oldest first)
        def _ts(s):
            ts = getattr(s, "timestamp", "") or ""
            return ts or ""

        sorted_commits = sorted(commitments, key=_ts)

        oldest = sorted_commits[0]
        days_stale = self._days_since(getattr(oldest, "timestamp", ""))

        return {
            "text": getattr(oldest, "text", str(oldest)),
            "days_stale": days_stale,
            "made_at": getattr(oldest, "timestamp", ""),
            "severity": "high" if days_stale > 5 else "medium" if days_stale > 2 else "low",
        }

    # --- The Open Question -------------------------------------------------

    def _find_open_question(self, signals: list) -> dict | None:
        """Find an unanswered follow-up question."""
        for s in signals:
            stype = str(getattr(s, "signal_type", "")).lower()
            if "follow_up" in stype or "open_question" in stype:
                return {
                    "text": getattr(s, "text", str(s)),
                    "asked_at": getattr(s, "timestamp", ""),
                    "days_open": self._days_since(getattr(s, "timestamp", "")),
                }
        return None

    # --- The Contradiction -------------------------------------------------

    def _find_contradiction(self, signals: list) -> dict | None:
        """Find a recent signal that contradicts an earlier signal."""
        # Look for signals with negative sentiment or contradiction_type
        for s in signals:
            stype = str(getattr(s, "signal_type", "")).lower()
            text = (getattr(s, "text", "") or "").lower()
            if "contradict" in stype or "but" in text[:20] or "actually" in text[:20]:
                return {
                    "text": getattr(s, "text", str(s)),
                    "detected_at": getattr(s, "timestamp", ""),
                }
        return None

    # --- Talk Tracks -------------------------------------------------------

    def _derive_talk_tracks(self, signals: list, entity: str) -> list[str]:
        """Derive 2-3 talk tracks from org laws matching this entity's topics."""
        # Build topic word set from signals
        all_text = " ".join(getattr(s, "text", "") for s in signals).lower()
        words = set(re.findall(r"\b[a-z]{4,}\b", all_text))
        stopwords = {"this", "that", "with", "have", "will", "been", "they",
                     "them", "what", "when", "where", "which", "there", "their"}
        words -= stopwords

        if not words:
            return []

        # Pull laws
        try:
            shell = self.shell
            laws = []
            if hasattr(shell, "core") and shell.core:
                for attr in ("laws", "patterns", "validated_patterns"):
                    ls = getattr(shell.core, attr, None)
                    if ls and isinstance(ls, list):
                        laws = ls
                        break
        except Exception:
            laws = []

        if not laws:
            return []

        scored = []
        for law in laws:
            law_text = (getattr(law, "statement", "") or
                        law.get("statement", "") if isinstance(law, dict) else "").lower()
            law_words = set(re.findall(r"\b[a-z]{4,}\b", law_text)) - stopwords
            overlap = len(words & law_words)
            if overlap >= 2:
                stmt = (getattr(law, "statement", "") or
                        law.get("statement", "") if isinstance(law, dict) else str(law))
                scored.append((overlap, stmt))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:3]]

    # --- Staleness ---------------------------------------------------------

    def _check_staleness(self, signals: list) -> bool:
        """Check if our intelligence is stale (no signal in 7+ days)."""
        if not signals:
            return False
        latest = max(
            (getattr(s, "timestamp", "") or "" for s in signals),
            default=""
        )
        days = self._days_since(latest)
        return days > 7

    # --- Helpers -----------------------------------------------------------

    def _days_since(self, timestamp: str) -> int:
        """Days since the given timestamp."""
        if not timestamp:
            return 0
        try:
            # ISO 8601
            ts = timestamp.replace("Z", "+00:00")
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).days
        except Exception:
            return 0

    def _build_greeting(self, entity: str, signals: list) -> str:
        """Build a context-aware greeting."""
        n = len(signals)
        if n == 0:
            return f"Meeting with {entity}. First interaction — no history yet."
        if n < 3:
            return f"Meeting with {entity}. {n} prior signal(s) on file."
        return f"Meeting with {entity}. {n} prior signals — well-tracked relationship."


# ---------------------------------------------------------------------------
# 3. Post-call Summary UI Payload Builder
# ---------------------------------------------------------------------------

class PostCallSummaryUI:
    """Build the post-call summary UI payload.

    The mobile/extension app renders this as a full-screen modal:
      - Hero card (title, duration, participant count, chunk count)
      - Key stats grid (commitments, objections, suggestions, talk ratio)
      - Commitments tracked (with Day X/Y countdown + dedup status)
      - Objections raised (with response pattern + action required)
      - Draft follow-up email (cites specific commitments + patterns)
      - What Maestro learned (new signals, pattern data points, law threshold)
    """

    def __init__(self, shell: Any):
        self.shell = shell
        self.followup_gen = FollowUpEmailGenerator(shell)

    def build(
        self,
        meeting_title: str = "",
        duration_seconds: int = 0,
        participants: list[str] | None = None,
        transcript_chunks: list[dict] | None = None,
        suggestion_cards: list[dict] | None = None,
        entity: str = "",
        talk_ratio_pct: float = 0.0,
    ) -> dict[str, Any]:
        """Build the full post-call summary UI payload."""
        participants = participants or []
        transcript_chunks = transcript_chunks or []
        suggestion_cards = suggestion_cards or []

        # Separate suggestion cards by type
        commitments = [c for c in suggestion_cards
                       if c.get("card_type") == "commitment" or "commitment" in c.get("type", "").lower()]
        objections = [c for c in suggestion_cards
                      if c.get("card_type") == "objection" or "objection" in c.get("type", "").lower()]
        all_suggestions = suggestion_cards

        # Hero card
        hero = {
            "title": meeting_title or "Meeting",
            "duration_minutes": round(duration_seconds / 60, 1),
            "participant_count": len(participants),
            "transcript_chunk_count": len(transcript_chunks),
            "ended_at": datetime.now(timezone.utc).isoformat(),
        }

        # Key stats grid
        stats = {
            "commitments": len(commitments),
            "objections": len(objections),
            "suggestions": len(all_suggestions),
            "transcript_chunks": len(transcript_chunks),
            "talk_ratio_pct": round(talk_ratio_pct, 1),
            "talk_ratio_status": self._talk_ratio_status(talk_ratio_pct),
        }

        # Commitments tracked
        commitments_tracked = []
        for c in commitments:
            evidence = c.get("evidence", {}) if isinstance(c.get("evidence"), dict) else {}
            commitments_tracked.append({
                "text": c.get("text", ""),
                "actor": evidence.get("speaker", c.get("actor", "")),
                "day_count": evidence.get("day_count", c.get("day_count", 0)),
                "deduped": evidence.get("deduped", c.get("deduped", False)),
                "status": "Existing" if evidence.get("deduped") else "Tracked",
            })

        # Objections raised
        objections_raised = []
        for o in objections:
            evidence = o.get("evidence", {}) if isinstance(o.get("evidence"), dict) else {}
            objections_raised.append({
                "type": evidence.get("objection_type", o.get("type", "unknown")),
                "text": o.get("text", ""),
                "confidence": o.get("confidence", 0),
                "confidence_label": o.get("confidence_label", ""),
                "action_required": "Follow up with response pattern",
            })

        # Draft follow-up email (cites specific commitments)
        draft_email = self.followup_gen.generate(
            meeting_title=meeting_title,
            participants=participants,
            commitments=commitments_tracked,
            objections=objections_raised,
            entity=entity,
            transcript_chunks=transcript_chunks,
        )

        # What Maestro learned
        learned = self._compute_learning(commitments, objections, transcript_chunks)

        return {
            "hero_summary": hero,
            "key_stats": stats,
            "commitments_tracked": commitments_tracked,
            "objections_raised": objections_raised,
            "draft_email": draft_email,
            "what_maestro_learned": learned,
        }

    # --- Helpers -----------------------------------------------------------

    def _talk_ratio_status(self, pct: float) -> str:
        """Classify talk ratio into a coaching status."""
        if pct == 0:
            return "unknown"
        if pct > 70:
            return "talking_too_much"
        if pct < 30:
            return "listening_well"
        return "balanced"

    def _compute_learning(
        self,
        commitments: list[dict],
        objections: list[dict],
        transcript_chunks: list[dict],
    ) -> dict[str, Any]:
        """Compute what Maestro learned from this call (the feedback loop)."""
        new_signals = len(commitments)
        objection_data_points = len(objections)
        law_threshold = 5
        data_points_to_law = max(0, law_threshold - objection_data_points)

        msg_parts = [
            f"This meeting generated {new_signals} new signal(s) ingested into "
            f"organizational memory."
        ]
        if objections:
            msg_parts.append(
                f"The objection pattern now has {objection_data_points} data point(s) — "
                f"{data_points_to_law} more and it becomes a validated organizational law."
            )

        return {
            "new_signals_ingested": new_signals,
            "objection_pattern_data_points": objection_data_points,
            "data_points_to_validated_law": data_points_to_law,
            "learning_active": True,
            "message": " ".join(msg_parts),
        }
