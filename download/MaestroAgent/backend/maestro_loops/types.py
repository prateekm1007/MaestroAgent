"""Loop types and policies."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LoopKind(str, Enum):
    RECURSIVE = "recursive"  # until condition met
    CRON = "cron"
    WEBHOOK = "webhook"
    FILE_EVENT = "file_event"
    NESTED = "nested"
    PARALLEL = "parallel"
    META = "meta"


class OnExceedAction(str, Enum):
    ESCALATE = "escalate"  # pause + ask HITL
    PAUSE = "pause"
    FAIL = "fail"
    CONTINUE = "continue"  # ignore — keep going (rare)


@dataclass
class BackoffPolicy:
    """Exponential backoff with jitter."""

    initial_seconds: float = 1.0
    multiplier: float = 2.0
    max_seconds: float = 60.0
    jitter: float = 0.1  # +/- 10%


@dataclass
class CronSchedule:
    """Minimal cron expression (5-field). For v0.1 we support minute-level."""

    expression: str  # e.g. "0 */6 * * *" = every 6 hours


@dataclass
class WebhookTrigger:
    """Webhook trigger spec."""

    path: str  # the URL path that triggers the loop
    secret: str  # shared secret for HMAC verification


@dataclass
class FileEventTrigger:
    """Filesystem watch trigger."""

    path: str
    events: list[str]  # subset of {"create", "modify", "delete", "move"}
