"""
PersonalSalienceConfig — personal signal types for the salience gate.

Per auditor's verified finding: Core's _is_high_salience_signal checks
enterprise types (commitment_made, decision.proposed, org.reorganization).
Personal needs different types. The shell wraps the method (see shell.py)
to also accept personal types. This config defines them.

This is NOT a Core modification. It is a config the shell applies at
runtime via method wrapping. Core stays enterprise-compatible.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PersonalSalienceConfig:
    """Configuration for personal-mode salience.

    The shell wraps SituationEngine._is_high_salience_signal to also
    accept these types. Core's enterprise types are still accepted
    (the wrapper checks Core first, then personal types).
    """

    # Personal signal types that warrant immediate situation creation
    # (with only 1 signal). These are the personal equivalents of
    # Core's commitment_made / decision.proposed / org.reorganization.
    high_salience_types: set[str] = field(default_factory=lambda: {
        # Personal commitments
        "personal.promise",           # "I'll send the revised numbers"
        "personal.commitment",        # explicit personal commitment
        # Meeting events
        "meeting.scheduled",          # a meeting was booked
        "meeting.moved",              # a meeting was rescheduled
        "meeting.cancelled",          # a meeting was cancelled
        # Calendar changes
        "calendar_change",            # generic calendar change
        # Deadlines
        "deadline.approaching",      # a deadline is coming up
        "deadline.missed",           # a deadline was missed
        # Follow-ups
        "follow_up.required",         # someone is waiting on the user
        # Personal decisions
        "personal.decision",          # the user made a personal decision
    })

    # Personal signal types that are NOT high-salience (need a second signal)
    # These are the personal equivalents of pricing.exception /
    # security.condition — they need context to be meaningful.
    low_salience_types: set[str] = field(default_factory=lambda: {
        "reported_statement",        # someone said something (need context)
        "observed_fact",             # a fact was observed (need context)
        "tentative",                 # a tentative statement (need confirmation)
        "personal.note",             # a personal note (need context)
    })

    def is_high_salience(self, signal_type: str) -> bool:
        """Check if a signal type is high-salience in personal mode."""
        return signal_type.lower() in self.high_salience_types

    def add_personal_type(self, signal_type: str) -> None:
        """Add a new personal high-salience type (for experimentation)."""
        self.high_salience_types.add(signal_type.lower())
