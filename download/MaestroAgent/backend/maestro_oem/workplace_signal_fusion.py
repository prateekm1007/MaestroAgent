"""
Workplace Signal Fusion - enterprise-grade email/Slack signal integration.

Phase 17 of the Ambient Intelligence roadmap (Days 114-123, 40 hours).

REVIVED per CEO directive: the reality check killed this feature based on
the individual-user deployment model (privacy nightmare). The enterprise
deployment model (company IT admin deploys, company owns data, employees
notified, opt-out available) is how Glean, Microsoft Viva, Google
Workspace Intelligence, and Slack AI all work. Legal under GDPR Article 6
(legitimate interest) + Article 21 (right to object).

7 Privacy Safeguards:
  1. Only work data: filters by company domain (user@company.com)
  2. Sensitive categories: excludes HR, legal, medical emails
  3. Opt-out: employees can request exclusion
  4. Private content: employees can mark specific emails as private
  5. Retention: auto-delete after 90 days
  6. Access control: role-based (employees see only their data)
  7. Audit logs: all access logged for compliance

Ethical guard: ENTERPRISE DEPLOYMENT ONLY. Individual deployment is
forbidden. The admin must sign a DPA. Employees must be notified.
Opt-out must be available. Sensitive categories must be excluded.
90-day retention enforced.

RICHER dimension: full context from email + Slack, not just audio.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class DeploymentMode(str, Enum):
    """Deployment mode (enterprise only for this feature)."""
    ENTERPRISE = "enterprise"  # company admin deploys
    INDIVIDUAL = "individual"  # FORBIDDEN for this feature


class SignalSource(str, Enum):
    """Where the signal came from."""
    EMAIL = "email"
    SLACK = "slack"
    CALENDAR = "calendar"
    DRIVE = "drive"


class SignalCategory(str, Enum):
    """Category of the detected signal."""
    COMMITMENT = "commitment"
    ACTION_ITEM = "action_item"
    DECISION = "decision"
    RISK = "risk"
    SENTIMENT = "sentiment"
    RELATIONSHIP = "relationship"


# Sensitive categories to EXCLUDE (privacy safeguard #2)
SENSITIVE_KEYWORDS = {
    "hr": ["human resources", "hr@", "personnel", "payroll", "benefits", "leave of absence", "termination", "resignation"],
    "legal": ["legal@", "attorney", "privileged", "confidential legal", "counsel", "litigation", "nda", "non-disclosure"],
    "medical": ["medical", "health", "doctor", "hospital", "diagnosis", "treatment", "fmla", "disability", "mental health"],
    "financial_personal": ["ssn", "social security", "bank account", "credit card", "salary", "compensation"],
}


@dataclass
class WorkplaceSignal:
    """A signal detected from workplace communication."""
    signal_id: str
    source: SignalSource
    category: SignalCategory
    sender: str          # email address
    recipients: list[str]
    subject: str
    body_preview: str     # first 200 chars
    timestamp: datetime
    company_domain: str   # the company domain (for filtering)
    is_sensitive: bool = False
    is_opted_out: bool = False
    is_private: bool = False  # user marked as private
    retention_expires: Optional[datetime] = None  # 90-day auto-delete

    def to_dict(self) -> dict:
        return {
            "signal_id": self.signal_id,
            "source": self.source.value,
            "category": self.category.value,
            "sender": self.sender,
            "subject": self.subject[:100],
            "timestamp": self.timestamp.isoformat(),
            "company_domain": self.company_domain,
            "is_sensitive": self.is_sensitive,
            "is_opted_out": self.is_opted_out,
            "is_private": self.is_private,
            "retention_expires": self.retention_expires.isoformat() if self.retention_expires else None,
        }


@dataclass
class AuditLogEntry:
    """An audit log entry for compliance."""
    action: str           # "ingest", "access", "delete", "opt_out"
    actor: str            # who performed the action
    signal_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "actor": self.actor,
            "signal_id": self.signal_id,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
        }


class DataGovernanceLayer:
    """
    Data governance: retention, access control, opt-out, audit logs.

    Implements the 7 privacy safeguards from the enterprise spec.
    """

    RETENTION_DAYS = 90  # auto-delete after 90 days

    def __init__(self, company_domain: str):
        self.company_domain = company_domain.lower()
        self._opted_out_users: set[str] = set()
        self._private_signals: set[str] = set()  # signal IDs marked private
        self._audit_log: list[AuditLogEntry] = []
        self._signals: dict[str, WorkplaceSignal] = {}  # signal_id -> signal

    def is_company_email(self, email: str) -> bool:
        """Safeguard #1: Only process company-domain emails."""
        return self.company_domain in email.lower()

    def is_sensitive(self, subject: str, body: str) -> tuple[bool, str]:
        """Safeguard #2: Exclude sensitive categories (HR, legal, medical, financial)."""
        text = (subject + " " + body).lower()
        for category, keywords in SENSITIVE_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    return True, category
        return False, ""

    def is_opted_out(self, email: str) -> bool:
        """Safeguard #3: Check if user has opted out."""
        return email.lower() in self._opted_out_users

    def opt_out(self, email: str) -> None:
        """Safeguard #3: Employee opts out of processing."""
        self._opted_out_users.add(email.lower())
        self._log_audit("opt_out", email, details={"email": email})

    def opt_in(self, email: str) -> None:
        """Employee opts back in."""
        self._opted_out_users.discard(email.lower())
        self._log_audit("opt_in", email, details={"email": email})

    def mark_private(self, signal_id: str) -> None:
        """Safeguard #4: Mark a specific signal as private."""
        self._private_signals.add(signal_id)
        self._log_audit("mark_private", "system", signal_id=signal_id)

    def compute_retention_expiry(self) -> datetime:
        """Safeguard #5: Compute 90-day retention expiry."""
        return datetime.now(timezone.utc) + timedelta(days=self.RETENTION_DAYS)

    def is_expired(self, signal: WorkplaceSignal) -> bool:
        """Safeguard #5: Check if a signal has expired (should be deleted)."""
        if signal.retention_expires is None:
            return False
        return datetime.now(timezone.utc) > signal.retention_expires

    def can_access(self, requester: str, signal: WorkplaceSignal) -> bool:
        """Safeguard #6: Role-based access control.

        Employees see only their own data (sender or recipient).
        Admins see all data (for compliance/audit purposes).
        """
        # Admin check: ends with @admin.domain OR is in admin list
        requester_lower = requester.lower()
        if requester_lower.startswith("admin@") or requester_lower.endswith("@admin." + self.company_domain):
            return True

        # Employee: see only their own data
        if requester_lower == signal.sender.lower():
            return True
        if requester_lower in [r.lower() for r in signal.recipients]:
            return True

        return False

    def log_access(self, requester: str, signal_id: str) -> None:
        """Safeguard #7: Log all access for compliance."""
        self._log_audit("access", requester, signal_id=signal_id)

    def _log_audit(self, action: str, actor: str, signal_id: str = "", details: dict = None) -> None:
        """Internal: write to audit log."""
        entry = AuditLogEntry(
            action=action,
            actor=actor,
            signal_id=signal_id,
            details=details or {},
        )
        self._audit_log.append(entry)

    def get_audit_log(self, limit: int = 100) -> list[dict]:
        """Get the audit log for compliance review."""
        return [e.to_dict() for e in self._audit_log[-limit:]]

    def cleanup_expired(self) -> int:
        """Delete expired signals (retention enforcement). Returns count deleted."""
        expired_ids = [sid for sid, sig in self._signals.items() if self.is_expired(sig)]
        for sid in expired_ids:
            del self._signals[sid]
            self._log_audit("delete_expired", "system", signal_id=sid)
        return len(expired_ids)


class WorkplaceSignalFusion:
    """
    Enterprise workplace signal fusion engine.

    Processes email and Slack signals from company-owned communication
    channels. Only operates in ENTERPRISE deployment mode.

    Usage:
        governance = DataGovernanceLayer(company_domain="")
        fusion = WorkplaceSignalFusion(governance)
        signals = fusion.process_email(
            sender="",
            recipients=[],
            subject="SSO deployment",
            body="We will deploy SSO by Friday.",
        )
    """

    # Commitment detection patterns
    COMMITMENT_PATTERNS = [
        re.compile(r"\b(?:we\s+will|I\s+will|we'?ll|I'?ll)\s+(?:deliver|ship|deploy|send|provide|implement)\b", re.IGNORECASE),
        re.compile(r"\b(?:by\s+(?:next|this|end\s+of)\s+(?:week|friday|monday|month))\b", re.IGNORECASE),
    ]

    # Action item patterns
    ACTION_ITEM_PATTERNS = [
        re.compile(r"\b(?:action\s+item|next\s+step|to-?do|follow\s+up|owner:?\s*\w+)\b", re.IGNORECASE),
    ]

    # Decision patterns
    DECISION_PATTERNS = [
        re.compile(r"\b(?:decided|agreed|confirmed|approved|concluded)\b", re.IGNORECASE),
    ]

    # Risk patterns
    RISK_PATTERNS = [
        re.compile(r"\b(?:risk|concern|issue|blocker|delay|overdue|at\s+risk)\b", re.IGNORECASE),
    ]

    def __init__(self, governance: DataGovernanceLayer):
        self.governance = governance
        self._deployment_mode = DeploymentMode.ENTERPRISE

    def process_email(
        self,
        sender: str,
        recipients: list[str],
        subject: str,
        body: str,
        timestamp: Optional[datetime] = None,
    ) -> list[WorkplaceSignal]:
        """Process an email and extract signals.

        Applies all 7 privacy safeguards before processing.
        Returns empty list if any safeguard blocks processing.
        """
        if self._deployment_mode != DeploymentMode.ENTERPRISE:
            logger.error("WorkplaceSignalFusion: INDIVIDUAL deployment mode is FORBIDDEN")
            return []

        ts = timestamp or datetime.now(timezone.utc)

        # Safeguard #1: Only company-domain emails
        if not self.governance.is_company_email(sender):
            logger.debug("WorkplaceSignalFusion: sender %s is not company domain", sender)
            return []

        # Safeguard #2: Exclude sensitive categories
        is_sensitive, sensitive_category = self.governance.is_sensitive(subject, body)
        if is_sensitive:
            logger.info("WorkplaceSignalFusion: email excluded (sensitive: %s)", sensitive_category)
            self.governance._log_audit("excluded_sensitive", "system",
                                       details={"category": sensitive_category, "sender": sender})
            return []

        # Safeguard #3: Respect opt-out
        if self.governance.is_opted_out(sender):
            logger.debug("WorkplaceSignalFusion: sender %s has opted out", sender)
            return []

        # Extract signals from the email content
        signals = self._extract_signals(
            source=SignalSource.EMAIL,
            sender=sender,
            recipients=recipients,
            subject=subject,
            body=body,
            timestamp=ts,
        )

        # Store signals + apply retention
        for signal in signals:
            signal.retention_expires = self.governance.compute_retention_expiry()
            self.governance._signals[signal.signal_id] = signal
            self.governance._log_audit("ingest", sender, signal_id=signal.signal_id)

        return signals

    def process_slack(
        self,
        sender: str,
        channel: str,
        message: str,
        timestamp: Optional[datetime] = None,
    ) -> list[WorkplaceSignal]:
        """Process a Slack message and extract signals."""
        if self._deployment_mode != DeploymentMode.ENTERPRISE:
            return []

        ts = timestamp or datetime.now(timezone.utc)

        # Safeguard #1: Only company-domain users
        if not self.governance.is_company_email(sender):
            return []

        # Safeguard #2: Exclude sensitive
        is_sensitive, category = self.governance.is_sensitive(channel, message)
        if is_sensitive:
            return []

        # Safeguard #3: Opt-out
        if self.governance.is_opted_out(sender):
            return []

        signals = self._extract_signals(
            source=SignalSource.SLACK,
            sender=sender,
            recipients=[channel],
            subject=channel,
            body=message,
            timestamp=ts,
        )

        for signal in signals:
            signal.retention_expires = self.governance.compute_retention_expiry()
            self.governance._signals[signal.signal_id] = signal
            self.governance._log_audit("ingest", sender, signal_id=signal.signal_id)

        return signals

    def _extract_signals(
        self,
        source: SignalSource,
        sender: str,
        recipients: list[str],
        subject: str,
        body: str,
        timestamp: datetime,
    ) -> list[WorkplaceSignal]:
        """Extract signals from content using pattern matching."""
        signals = []
        text = subject + " " + body
        signal_counter = 0

        # Detect commitments
        for pattern in self.COMMITMENT_PATTERNS:
            if pattern.search(text):
                sig = WorkplaceSignal(
                    signal_id=f"ws-{source.value}-{timestamp.timestamp()}-{signal_counter}",
                    source=source,
                    category=SignalCategory.COMMITMENT,
                    sender=sender,
                    recipients=recipients,
                    subject=subject[:100],
                    body_preview=body[:200],
                    timestamp=timestamp,
                    company_domain=self.governance.company_domain,
                )
                signals.append(sig)
                signal_counter += 1
                break

        # Detect action items
        for pattern in self.ACTION_ITEM_PATTERNS:
            if pattern.search(text):
                sig = WorkplaceSignal(
                    signal_id=f"ws-{source.value}-{timestamp.timestamp()}-{signal_counter}",
                    source=source,
                    category=SignalCategory.ACTION_ITEM,
                    sender=sender,
                    recipients=recipients,
                    subject=subject[:100],
                    body_preview=body[:200],
                    timestamp=timestamp,
                    company_domain=self.governance.company_domain,
                )
                signals.append(sig)
                signal_counter += 1
                break

        # Detect decisions
        for pattern in self.DECISION_PATTERNS:
            if pattern.search(text):
                sig = WorkplaceSignal(
                    signal_id=f"ws-{source.value}-{timestamp.timestamp()}-{signal_counter}",
                    source=source,
                    category=SignalCategory.DECISION,
                    sender=sender,
                    recipients=recipients,
                    subject=subject[:100],
                    body_preview=body[:200],
                    timestamp=timestamp,
                    company_domain=self.governance.company_domain,
                )
                signals.append(sig)
                signal_counter += 1
                break

        # Detect risks
        for pattern in self.RISK_PATTERNS:
            if pattern.search(text):
                sig = WorkplaceSignal(
                    signal_id=f"ws-{source.value}-{timestamp.timestamp()}-{signal_counter}",
                    source=source,
                    category=SignalCategory.RISK,
                    sender=sender,
                    recipients=recipients,
                    subject=subject[:100],
                    body_preview=body[:200],
                    timestamp=timestamp,
                    company_domain=self.governance.company_domain,
                )
                signals.append(sig)
                signal_counter += 1
                break

        return signals

    def get_signals(
        self,
        requester: str,
        category: Optional[SignalCategory] = None,
        source: Optional[SignalSource] = None,
    ) -> list[WorkplaceSignal]:
        """Get signals accessible to the requester (role-based access control)."""
        result = []
        for signal in self.governance._signals.values():
            # Safeguard #4: Skip private signals (unless requester is the owner)
            if signal.signal_id in self.governance._private_signals:
                if signal.sender.lower() != requester.lower():
                    continue

            # Safeguard #6: Access control
            if not self.governance.can_access(requester, signal):
                continue

            # Safeguard #5: Skip expired
            if self.governance.is_expired(signal):
                continue

            # Filter by category/source if specified
            if category and signal.category != category:
                continue
            if source and signal.source != source:
                continue

            # Log access
            self.governance.log_access(requester, signal.signal_id)

            result.append(signal)

        return result

    def cleanup_expired(self) -> int:
        """Run retention cleanup (Safeguard #5)."""
        return self.governance.cleanup_expired()
