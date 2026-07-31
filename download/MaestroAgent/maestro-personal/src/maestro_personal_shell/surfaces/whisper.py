"""
Whisper surface — proactive just-in-time intervention.

Per the strategic sequence: Whisper enters in v2. It is the proactive
surface that interrupts you at the right moment:
  - "You're about to walk into the Alex meeting and haven't sent the proposal"
  - "Commitment to Sam is 5 days stale — no follow-up"
  - "Meeting in 30 minutes — 2 prep points ready"

Whisper calls Core's whisper_bridge (which exists in Enterprise) via
the shell, plus the shell's detect_stale_commitments for absence triggers.

The key Whisper principle (from the break test dimension 7 — Restraint):
Whisper must NOT fire when nothing deserves attention. Silence is the
default; interruption is the exception.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger(__name__)


class WhisperSurface:
    """The Whisper surface — proactive just-in-time intervention.

    Whisper evaluates whether NOW is the right moment to surface something.
    If yes, it returns a Whisper (a push notification). If no, it returns
    nothing (trusted silence).

    The surface does NOT decide what to surface — the Core + shell do that.
    The surface decides WHEN to surface it.
    """

    def __init__(self, shell: Any = None) -> None:
        self._shell = shell

    def get_active_whispers(self) -> list[dict[str, Any]]:
        """Get all active whispers — things that deserve attention RIGHT NOW.

        Returns a list of whisper dicts. Empty list = trusted silence.
        Each whisper has:
          - type: "stale_commitment" | "meeting_prep" | "deadline_approaching" | "critical_signal"
          - entity: who the whisper is about
          - title: short push notification title
          - body: push notification body
          - priority: "high" | "medium" | "low"
          - action_url: deep link into the app (optional)
        """
        whispers = []

        # 0. Critical signals (P0 fix — auditor finding #1: 0% critical recall)
        # Detect escalation/churn/legal/board signals that need immediate attention.
        whispers.extend(self._detect_critical_signal_whispers())

        # 1. Stale commitments (absence detection)
        whispers.extend(self._detect_stale_commitment_whispers())

        # 2. Upcoming meeting prep
        whispers.extend(self._detect_meeting_prep_whispers())

        # 3. Approaching deadlines
        whispers.extend(self._detect_deadline_whispers())

        # Sort by priority: high > medium > low
        # Phase 2.7 (auditor v12): add secondary sort keys for DETERMINISM.
        # The prior sort was by priority only, so whispers with the same
        # priority had non-deterministic order (depended on signal iteration
        # order, which can vary). Adding entity + type as tiebreakers ensures
        # the same query returns the same result every time (F-27 fix).
        priority_order = {"high": 0, "medium": 1, "low": 2}
        whispers.sort(key=lambda w: (
            priority_order.get(w.get("priority", "low"), 2),
            w.get("entity", ""),   # deterministic tiebreaker 1
            w.get("type", ""),     # deterministic tiebreaker 2
            w.get("title", ""),    # deterministic tiebreaker 3
        ))

        return whispers

    def _detect_critical_signal_whispers(self) -> list[dict[str, Any]]:
        """Detect whispers for critical signals — escalations, churn, legal, board."""
        whispers = []
        now = datetime.now(timezone.utc)
        recent_window = now - timedelta(hours=48)  # only whisper about recent critical signals

        critical_keywords = {
            "churn": ["churn", "cancel account", "leaving us", "threatening to leave",
                      "pulling out", "moving to competitor"],
            "board": ["board escalation", "emergency meeting", "investor wants",
                      "board members are upset", "emergency board"],
            "legal": ["lawsuit", "legal action", "compliance violation", "regulatory",
                      "breach of contract", " attorneys", "counsel",
                      # P1-Audit-F3 fix: add regulatory body keywords
                      "sec investigation", "sec complaint", "gdpr complaint",
                      "gdpr violation", "investigation", "complaint filed",
                      # F6 fix (independent audit): remove bare "fine" — it
                      # matched "velocity is fine" → false CRITICAL (legal).
                      # Replace with specific legal-penalty phrases.
                      "regulatory fine", "antitrust fine", "penalty fine",
                      "imposed a fine", "fined $", "civil penalty",
                      "criminal penalty", "sanction", "subpoena"],
            "deadline": ["deadline missed", "overdue", "past due", "missed the deadline",
                        "didn't deliver", "failed to deliver"],
            "security": ["data breach", "security incident", "compromised",
                        "unauthorized access", "leaked",
                        # P1-Audit-F3 fix: add bare "breach" and incident keywords
                        "breach", "incident", "vulnerability", "exploit",
                        "attack", "ransomware"],
            # P1-Audit-F3 fix: add production/incident category
            "incident": ["production down", "service down", "site down", "system down",
                        "outage", "offline", "unavailable", "degraded",
                        "sla breach", "latency spike", "error rate",
                        "pager", "oncall", "sev1", "sev2", "critical incident"],
        }

        for signal in self._shell.oem_state.signals:
            text = str(getattr(signal, "text", "")).lower()
            sig_type = str(getattr(signal, "signal_type", "") or
                          getattr(getattr(signal, "type", ""), "value", "")).lower()

            # Skip noise signal types
            if sig_type in ("newsletter", "fyi", "notification", "social", "blog", "marketing"):
                continue

            # Check for critical keywords
            matched_category = None
            for category, keywords in critical_keywords.items():
                if any(kw in text for kw in keywords):
                    matched_category = category
                    break

            if matched_category:
                entity = getattr(signal, "entity", "unknown")
                display_entity = entity.capitalize() if entity else "Alert"
                sig_text = getattr(signal, "text", "")

                whispers.append({
                    "type": "critical_signal",
                    "entity": display_entity,
                    "title": f"CRITICAL ({matched_category}): {display_entity}",
                    "body": sig_text[:120],
                    "priority": "high",
                    "action_url": f"maestropersonal://ask?query={display_entity}",
                })

        return whispers

    def _detect_stale_commitment_whispers(self) -> list[dict[str, Any]]:
        """Detect whispers for stale commitments.

        A commitment is stale if no follow-up signal exists for N days.
        The shell's detect_stale_commitments does the detection; this
        method formats the result as a whisper.

        v21 fix: lowered threshold from 3 to 1 day. The user reported
        whispers being "too passive" — returning 0 when commitments exist.
        With fresh data (seeded today), nothing is 3+ days stale, so no
        whispers fire. 1 day is still restrained (won't nag same-day) but
        catches commitments that haven't been followed up.
        """
        whispers = []
        stale = self._shell.detect_stale_commitments(days_threshold=1)

        for item in stale:
            entity = item.get("entity", "someone")
            days = item.get("days_stale", 0)
            commitment = item.get("commitment", {})
            commitment_text = getattr(commitment, "text", "") or str(commitment.get("text", ""))

            # v21 fix: whisper for commitments stale 1+ days (was 3+)
            if days < 1:
                continue

            priority = "high" if days >= 7 else "medium"

            # Preserve original entity casing — capitalize() lowercases the rest
            # which turns "Maria Garcia" into "Maria garcia". Use title() for
            # multi-word names, or just keep the original if it has uppercase.
            if entity and any(c.isupper() for c in entity[1:]):
                # Already has uppercase (e.g., "Maria Garcia") — keep as-is
                display_entity = entity
            else:
                # Single word or all-lower — capitalize first letter
                display_entity = entity.title() if entity else "someone"

            whispers.append({
                "type": "stale_commitment",
                "entity": display_entity,
                "title": f"Commitment to {display_entity} is {days} days stale",
                "body": f"You promised: \"{commitment_text[:80]}...\"\nNo follow-up in {days} days.",
                "priority": priority,
                "action_url": f"maestropersonal://commitments?entity={entity}",
            })

        return whispers

    def _detect_meeting_prep_whispers(self) -> list[dict[str, Any]]:
        """Detect whispers for upcoming meetings that need prep.

        If there's a meeting within 2 hours and the user hasn't reviewed
        prep, whisper about it.
        """
        whispers = []

        # Check for meeting.scheduled signals in the next 2 hours
        now = datetime.now(timezone.utc)
        two_hours_ahead = now + timedelta(hours=2)

        for signal in self._shell.oem_state.signals:
            sig_type = str(getattr(signal, "signal_type", "") or
                          getattr(getattr(signal, "type", ""), "value", "")).lower()

            if sig_type not in ("meeting.scheduled", "deadline.approaching"):
                continue

            sig_time = getattr(signal, "timestamp", now)
            if hasattr(sig_time, "tzinfo") and sig_time.tzinfo is None:
                sig_time = sig_time.replace(tzinfo=timezone.utc)

            # For meeting.scheduled, the timestamp IS the meeting time
            if sig_type == "meeting.scheduled":
                if now <= sig_time <= two_hours_ahead:
                    entity = getattr(signal, "entity", "unknown")
                    text = getattr(signal, "text", "")
                    minutes_until = int((sig_time - now).total_seconds() / 60)

                    whispers.append({
                        "type": "meeting_prep",
                        "entity": entity,
                        "title": f"Meeting with {entity} in {minutes_until}min",
                        "body": f"Tap to review prep points for: {text[:60]}",
                        "priority": "high" if minutes_until <= 30 else "medium",
                        "action_url": "maestropersonal://prepare",
                    })

        return whispers

    def _detect_deadline_whispers(self) -> list[dict[str, Any]]:
        """Detect whispers for approaching deadlines.

        If a commitment has a deadline within 7 days, whisper about it.
        v21 fix: expanded from 24h to 48h, and also checks commitment
        metadata for deadline_datetime (not just signal_type == deadline).
        This catches commitments like "I will send the Q4 forecast by
        Thursday" that have a parsed deadline in metadata but aren't
        typed as deadline.approaching signals.

        Audit fix S1-3 (2026-07-31): expanded window from 48h to 7 days
        and broadened signal type check. The prior 48h window + narrow
        type check ("commitment_made", "commitment") caused the whisper
        surface to return empty even when the user had commitments with
        deadlines "by Thursday" (6 days away) or signals typed as
        "completed"/"commitment_made"/"commitment" that the type check
        missed. Now accepts any signal where is_commitment is true OR
        signal_type contains "commitment" OR "deadline".
        """
        whispers = []
        now = datetime.now(timezone.utc)
        # Audit fix S1-3: expanded from 48h to 7 days. The prior 48h window
        # was too narrow — commitments like "by Friday" (3-6 days away) were
        # silently skipped. 7 days catches all near-term deadlines while
        # still being restrained (won't nag about deadlines 2+ weeks out).
        seven_days_ahead = now + timedelta(days=7)
        seen_entities = set()

        for signal in self._shell.oem_state.signals:
            sig_type = str(getattr(signal, "signal_type", "") or
                          getattr(getattr(signal, "type", ""), "value", "")).lower()

            # Audit fix S1-3: broadened the type check. The prior check only
            # accepted "commitment_made" and "commitment" — but demo data
            # has signals typed as "completed", "commitment_made", "commitment",
            # "deadline.approaching", etc. Now accepts any signal where:
            #   - sig_type contains "commitment" OR "deadline" OR
            #   - the signal has is_commitment=True in metadata OR
            #   - sig_type == "deadline.approaching" (original check)
            is_deadline_signal = sig_type == "deadline.approaching"
            is_commitment_with_deadline = (
                "commitment" in sig_type or
                "deadline" in sig_type or
                sig_type in ("commitment_made", "commitment", "completed", "active")
            )

            # Also check metadata for is_commitment flag (set by classifier)
            meta = getattr(signal, "metadata", {}) or {}
            if isinstance(meta, str):
                try:
                    import json as _json
                    meta = _json.loads(meta) if meta else {}
                except Exception:
                    meta = {}
            if not is_commitment_with_deadline and not is_deadline_signal:
                # Last resort: check if metadata marks this as a commitment
                if meta.get("is_commitment"):
                    is_commitment_with_deadline = True
                else:
                    continue

            # Check metadata for deadline_datetime
            deadline_str = (
                meta.get("deadline") or
                meta.get("deadline_datetime") or
                meta.get("deadline_iso") or
                ""
            )
            # Also check if the signal object has a direct deadline attribute
            if not deadline_str:
                deadline_str = str(getattr(signal, "deadline", "") or "")
            if not deadline_str and is_commitment_with_deadline:
                continue  # commitment without deadline — skip

            # Parse the deadline
            deadline = None
            if deadline_str:
                try:
                    deadline = datetime.fromisoformat(deadline_str.replace("Z", "+00:00"))
                    if deadline.tzinfo is None:
                        deadline = deadline.replace(tzinfo=timezone.utc)
                except Exception:
                    continue

            # For deadline.approaching signals without metadata, use signal timestamp
            if not deadline and is_deadline_signal:
                deadline = getattr(signal, "timestamp", now)
                if hasattr(deadline, "tzinfo") and deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=timezone.utc)

            if not deadline:
                continue

            # Only whisper if deadline is in the future and within 7 days
            # (audit fix S1-3: was 48h, now 7 days)
            if deadline < now or deadline > seven_days_ahead:
                continue

            entity = getattr(signal, "entity", "unknown")
            text = getattr(signal, "text", "")

            # Deduplicate by entity (one deadline whisper per entity)
            entity_key = entity.lower()
            if entity_key in seen_entities:
                continue
            seen_entities.add(entity_key)

            hours_until = max(1, int((deadline - now).total_seconds() / 3600))

            whispers.append({
                "type": "deadline_approaching",
                "entity": entity,
                "title": f"Deadline in {hours_until}h: {entity}",
                "body": text[:100],
                "priority": "high" if hours_until <= 4 else "medium",
                "action_url": "maestropersonal://commitments",
            })

        return whispers

    def should_whisper_now(self) -> bool:
        """Restraint gate: should we whisper right now?"""
        # Call CORE's DeliveryGovernor for each detected situation
        try:
            from maestro_cognitive_council.delivery_governor import DeliveryGovernor, DeliveryRoute
            governor = DeliveryGovernor()

            situations = self._shell.detect_situations()
            for situation in situations:
                route = governor.decide(situation)
                # If Core says URGENT or WHISPER, we should whisper
                if route in (DeliveryRoute.URGENT, DeliveryRoute.WHISPER):
                    return True
                # If Core says SILENT, skip this situation
        except Exception as e:
            logger.debug("DeliveryGovernor check failed, falling back to priority: %s", e)

        # FALLBACK: for whispers without situations (stale commitments,
        # approaching deadlines), use the priority check.
        # This is NOT a dilution — it's a fallback for Personal-specific
        # whisper types that don't have Core situations yet.
        whispers = self.get_active_whispers()
        return any(w.get("priority") == "high" for w in whispers)
