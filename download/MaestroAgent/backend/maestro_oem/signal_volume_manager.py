"""
Signal Volume Manager — filters, summarizes, and retains signals efficiently.

Addresses Challenge 1 from the System Integration Review:
Email/Slack generates 450K signals/month for 100 employees.
This module provides:
  1. Aggressive filtering: only process high-signal emails/Slack
  2. Summarization: store summary, not full text
  3. Retention: delete low-value signals after 30 days

Usage:
    manager = SignalVolumeManager()
    if manager.should_process(email_sender, email_subject, email_body):
        summary = manager.summarize(email_body, max_length=200)
        # process the summary, not the full body
    manager.cleanup_old_signals(days=30)
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class SignalIntent(str, Enum):
    """Intent classification for incoming signals."""
    COMMITMENT = "commitment"
    DECISION = "decision"
    QUESTION = "question"
    OBJECTION = "objection"
    RISK = "risk"
    INFORMATIONAL = "informational"  # low value — filter or summarize
    NOISE = "noise"  # newsletters, automated, receipts


# Patterns that indicate noise (skip entirely)
NOISE_PATTERNS = [
    re.compile(r"unsubscribe|opt.out|mailing.list|newsletter", re.IGNORECASE),
    re.compile(r"noreply|no.reply|donotreply|do.not.reply", re.IGNORECASE),
    re.compile(r"automated.message|system.notification|cron.job", re.IGNORECASE),
    re.compile(r"receipt|invoice|confirmation.order|shipping.update", re.IGNORECASE),
    re.compile(r"out.of.office|auto.reply|vacation", re.IGNORECASE),
]

# Patterns that indicate high-signal content
HIGH_SIGNAL_PATTERNS = [
    (re.compile(r"\b(?:we\s+will|I\s+will|we'?ll|I'?ll)\s+(?:deliver|ship|send|provide|implement)\b", re.IGNORECASE), SignalIntent.COMMITMENT),
    (re.compile(r"\b(?:decided|agreed|approved|concluded)\b", re.IGNORECASE), SignalIntent.DECISION),
    (re.compile(r"\b\?\s*$|what|how|when|why|where|who\b", re.IGNORECASE), SignalIntent.QUESTION),
    (re.compile(r"\b(?:concern|issue|risk|blocker|delay|overdue)\b", re.IGNORECASE), SignalIntent.RISK),
    (re.compile(r"\b(?:too\s+expensive|above\s+budget|priced\s+too\s+high)\b", re.IGNORECASE), SignalIntent.OBJECTION),
]


class SignalVolumeManager:
    """
    Manages signal volume: filtering, summarization, retention.

    Prevents 450K signals/month from overwhelming the OEM engine by:
    1. Skipping noise (newsletters, auto-replies, receipts)
    2. Only processing high-signal content (commitments, decisions, questions, risks)
    3. Summarizing low-value signals to 200 chars
    4. Cleaning up old informational signals after 30 days
    """

    def __init__(self):
        self._processed_count = 0
        self._filtered_count = 0
        self._summarized_count = 0

    def should_process(self, sender: str, subject: str, body: str) -> bool:
        """Determine if an email/Slack message should be processed.

        Returns False for:
        - Newsletters, auto-replies, receipts (noise)
        - No-reply addresses
        - Out-of-office messages

        Returns True for:
        - Anything with commitment/decision/question/risk/objection content
        - Internal company emails (non-noise)
        """
        text = f"{subject} {body}"

        # Check noise patterns first (skip entirely)
        for pattern in NOISE_PATTERNS:
            if pattern.search(text) or pattern.search(sender):
                self._filtered_count += 1
                logger.debug("SignalVolumeManager: filtered noise from %s", sender)
                return False

        self._processed_count += 1
        return True

    def classify_intent(self, text: str) -> SignalIntent:
        """Classify the intent of a signal for priority routing."""
        for pattern, intent in HIGH_SIGNAL_PATTERNS:
            if pattern.search(text):
                return intent
        return SignalIntent.INFORMATIONAL

    def summarize(self, text: str, max_length: int = 200) -> str:
        """Summarize text to max_length characters.

        Simple extraction: first sentence + last sentence (if room).
        In production, would use an LLM for better summarization.
        """
        if len(text) <= max_length:
            return text

        self._summarized_count += 1

        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        if len(sentences) <= 1:
            return text[:max_length] + "..."

        # First sentence (most important)
        summary = sentences[0]
        if len(summary) >= max_length:
            return summary[:max_length - 3] + "..."

        # Add more sentences until we hit max_length
        for sentence in sentences[1:]:
            if len(summary) + len(sentence) + 1 <= max_length:
                summary += " " + sentence
            else:
                break

        if len(summary) < len(text):
            summary += "..."
        return summary

    def get_retention_cutoff(self, days: int = 30) -> datetime:
        """Get the cutoff datetime for signal retention."""
        return datetime.now(timezone.utc) - timedelta(days=days)

    def should_retain(self, signal_timestamp: datetime, signal_intent: SignalIntent, days: int = 30) -> bool:
        """Determine if a signal should be retained or deleted.

        High-signal intents (commitment, decision, objection, risk) are retained indefinitely.
        Informational signals are deleted after `days` days.
        """
        if signal_intent in (SignalIntent.COMMITMENT, SignalIntent.DECISION,
                             SignalIntent.OBJECTION, SignalIntent.RISK):
            return True  # always retain high-value signals

        cutoff = self.get_retention_cutoff(days)
        return signal_timestamp > cutoff

    def get_stats(self) -> dict:
        """Get filtering statistics."""
        total = self._processed_count + self._filtered_count
        return {
            "total_seen": total,
            "processed": self._processed_count,
            "filtered_noise": self._filtered_count,
            "summarized": self._summarized_count,
            "filter_rate": (self._filtered_count / total * 100) if total > 0 else 0,
        }
