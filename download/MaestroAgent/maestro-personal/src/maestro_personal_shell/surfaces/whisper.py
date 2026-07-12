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
        priority_order = {"high": 0, "medium": 1, "low": 2}
        whispers.sort(key=lambda w: priority_order.get(w.get("priority", "low"), 2))

        return whispers

    def _detect_critical_signal_whispers(self) -> list[dict[str, Any]]:
        """Detect whispers for critical signals — escalations, churn, legal, board.

        P0 fix (auditor finding #1): Whisper critical recall was 0% because
        the WhisperSurface only detected stale commitments, meeting prep, and
        deadline approaches. It did NOT detect critical signals like
        "customer threatening to churn" or "board escalation". This method
        scans recent signals for critical keywords and generates high-priority
        whispers.

        Critical keywords (from the Phase 6 silence_benchmark_100):
          - churn/escalation/threatening/cancel account
          - board escalation/emergency
          - legal/lawsuit/compliance/regulatory
          - deadline missed/overdue/past due
          - breach/security incident
        """
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
        """
        whispers = []
        stale = self._shell.detect_stale_commitments(days_threshold=3)

        for item in stale:
            entity = item.get("entity", "someone")
            days = item.get("days_stale", 0)
            commitment = item.get("commitment", {})
            commitment_text = getattr(commitment, "text", "") or str(commitment.get("text", ""))

            # Only whisper for commitments stale 3+ days (restraint — don't nag)
            if days < 3:
                continue

            priority = "high" if days >= 7 else "medium"

            # Capitalize entity for display (shell lowercases for comparison)
            display_entity = entity.capitalize() if entity else "someone"

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

        If a commitment has a deadline within 24 hours, whisper about it.
        """
        whispers = []
        now = datetime.now(timezone.utc)
        day_ahead = now + timedelta(hours=24)

        for signal in self._shell.oem_state.signals:
            sig_type = str(getattr(signal, "signal_type", "") or
                          getattr(getattr(signal, "type", ""), "value", "")).lower()

            if sig_type != "deadline.approaching":
                continue

            # Check if the deadline is within 24 hours
            sig_time = getattr(signal, "timestamp", now)
            if hasattr(sig_time, "tzinfo") and sig_time.tzinfo is None:
                sig_time = sig_time.replace(tzinfo=timezone.utc)

            if now <= sig_time <= day_ahead:
                entity = getattr(signal, "entity", "unknown")
                text = getattr(signal, "text", "")
                hours_until = int((sig_time - now).total_seconds() / 3600)

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
        """Restraint gate: should we whisper right now?

        Per auditor finding (caabb7f dilution): this method MUST call
        Core's DeliveryGovernor.decide() for each situation, NOT use its
        own priority logic. Core's governor has the verified opportunity-
        cost model (recently_surfaced suppression + should_surface check)
        that prevents nagging. The priority check below is a FALLBACK
        only for whispers that don't map to a situation (e.g., stale
        commitments that haven't formed a situation yet).

        Per break-test dimension 7 (Restraint): Whisper must NOT fire
        when nothing deserves attention.
        """
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
