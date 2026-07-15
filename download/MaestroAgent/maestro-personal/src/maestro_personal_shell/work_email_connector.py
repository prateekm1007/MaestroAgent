"""
Work Email connector — IMAP/SMTP for any work email provider.

Supports: Exchange, Outlook, ProtonMail Bridge, custom domains, any
provider that exposes IMAP + SMTP.

Unlike Gmail (which uses OAuth2), work_email uses app passwords or
basic auth (IMAP username + password). This is the standard pattern
for enterprise email.

Configuration (env vars):
  - MAESTRO_WORK_EMAIL_IMAP_HOST: IMAP server (e.g., outlook.office365.com)
  - MAESTRO_WORK_EMAIL_IMAP_PORT: IMAP port (default 993 for SSL)
  - MAESTRO_WORK_EMAIL_SMTP_HOST: SMTP server (e.g., smtp.office365.com)
  - MAESTRO_WORK_EMAIL_SMTP_PORT: SMTP port (default 587 for TLS)
  - MAESTRO_WORK_EMAIL_USERNAME: email address
  - MAESTRO_WORK_EMAIL_PASSWORD: app password (NOT the account password)

When NOT set, falls back to demo mode (no real ingestion).
"""
from __future__ import annotations

import os
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any
from email.utils import parsedate_to_datetime

logger = logging.getLogger(__name__)


def is_work_email_configured() -> bool:
    """Check if work email IMAP/SMTP credentials are configured."""
    return bool(
        os.environ.get("MAESTRO_WORK_EMAIL_IMAP_HOST")
        and os.environ.get("MAESTRO_WORK_EMAIL_USERNAME")
        and os.environ.get("MAESTRO_WORK_EMAIL_PASSWORD")
    )


def get_work_email_config() -> dict[str, str]:
    """Get work email configuration from env."""
    return {
        "imap_host": os.environ.get("MAESTRO_WORK_EMAIL_IMAP_HOST", ""),
        "imap_port": os.environ.get("MAESTRO_WORK_EMAIL_IMAP_PORT", "993"),
        "smtp_host": os.environ.get("MAESTRO_WORK_EMAIL_SMTP_HOST", ""),
        "smtp_port": os.environ.get("MAESTRO_WORK_EMAIL_SMTP_PORT", "587"),
        "username": os.environ.get("MAESTRO_WORK_EMAIL_USERNAME", ""),
        "password": os.environ.get("MAESTRO_WORK_EMAIL_PASSWORD", ""),
    }


class WorkEmailIngester:
    """Ingest commitments from work email via IMAP."""

    def __init__(self, config: dict[str, str] | None = None):
        self.config = config or get_work_email_config()

    def ingest(self, days_back: int = 30) -> list[dict[str, Any]]:
        """Pull emails from last N days, extract commitments.

        Returns list of signals:
          {entity, text, signal_type, timestamp, source}
        """
        if not is_work_email_configured():
            logger.info("Work email not configured — returning demo data")
            return self._demo_data()

        try:
            import imaplib
            import email
            from email.header import decode_header

            signals: list[dict[str, Any]] = []

            # Connect to IMAP
            imap = imaplib.IMAP4_SSL(
                self.config["imap_host"],
                int(self.config["imap_port"]),
            )
            imap.login(
                self.config["username"],
                self.config["password"],
            )
            imap.select("INBOX")

            # Search for emails from last N days
            since_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%d-%b-%Y")
            _, message_ids = imap.search(None, f'(SINCE {since_date})')

            for msg_id in message_ids[0].split()[:100]:  # limit to 100
                try:
                    _, msg_data = imap.fetch(msg_id, "(RFC822)")
                    raw = msg_data[0][1]
                    msg = email.message_from_bytes(raw)

                    # Extract sender
                    sender = msg.get("From", "")
                    sender_name = re.match(r'"?([^"<]+)"?\s*<?', sender)
                    entity = sender_name.group(1).strip() if sender_name else sender

                    # Extract body
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                                break
                    else:
                        body = msg.get_payload(decode=True).decode("utf-8", errors="replace") if msg.get_payload(decode=True) else ""

                    # Extract timestamp
                    date_str = msg.get("Date", "")
                    try:
                        timestamp = parsedate_to_datetime(date_str).isoformat()
                    except Exception:
                        timestamp = datetime.now(timezone.utc).isoformat()

                    # Commitment detection
                    commitment = self._detect_commitment(body)
                    if commitment:
                        signals.append({
                            "entity": entity,
                            "text": commitment,
                            "signal_type": "commitment_made",
                            "timestamp": timestamp,
                            "source": "work_email:imap",
                        })

                except Exception as e:
                    logger.debug("Failed to parse email %s: %s", msg_id, e)

            imap.logout()
            logger.info("Work email ingestion: %d signals from %d emails", len(signals), len(message_ids[0].split()))
            return signals

        except Exception as e:
            logger.warning("Work email IMAP ingestion failed: %s", e)
            return []

    def _detect_commitment(self, text: str) -> str:
        """Simple commitment detection from email body."""
        text_lower = text.lower()
        commitment_patterns = [
            r"i (?:will|will be|'ll) (.+?)(?:\.|$)",
            r"i (?:promise|commit) (?:to )?(.+?)(?:\.|$)",
            r"i (?:need to|have to|must) (.+?)(?:\.|$)",
            r"let me (?:get back to|send you|follow up) (.+?)(?:\.|$)",
            r"i'll (?:send|share|provide|deliver) (.+?)(?:\.|$|by)",
        ]
        for pattern in commitment_patterns:
            match = re.search(pattern, text_lower)
            if match:
                return match.group(0).capitalize()
        return ""

    def _demo_data(self) -> list[dict[str, Any]]:
        """Return demo signals when IMAP not configured."""
        return [
            {
                "entity": "Demo Client",
                "text": "I will send the quarterly report by Friday",
                "signal_type": "commitment_made",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "work_email:demo",
            },
        ]


class WorkEmailSender:
    """Send emails via SMTP."""

    def __init__(self, config: dict[str, str] | None = None):
        self.config = config or get_work_email_config()

    def send(self, to: str, subject: str, body: str) -> bool:
        """Send an email via SMTP."""
        if not is_work_email_configured():
            logger.warning("Work email SMTP not configured — cannot send")
            return False

        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            msg = MIMEMultipart()
            msg["From"] = self.config["username"]
            msg["To"] = to
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            smtp = smtplib.SMTP(
                self.config["smtp_host"],
                int(self.config["smtp_port"]),
            )
            smtp.starttls()
            smtp.login(
                self.config["username"],
                self.config["password"],
            )
            smtp.send_message(msg)
            smtp.quit()
            logger.info("Work email sent to %s: %s", to, subject)
            return True

        except Exception as e:
            logger.warning("Work email SMTP send failed: %s", e)
            return False
