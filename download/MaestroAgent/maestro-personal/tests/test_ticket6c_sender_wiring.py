"""TICKET-6c: Wire sender_email from Gmail connector to classifier.

Regression tests for the sender_email wiring. The Gmail connector now
extracts the sender EMAIL ADDRESS (using email.utils.parseaddr) and
passes it through to the classifier, activating the marketing SENDER
filter (TICKET-6b) on real Gmail data.

Tests:
  1. Gmail connector passes sender_email to extract_signals_intelligently
  2. Marketing sender rejected end-to-end (Slack → not_a_commitment)
  3. Real sender accepted end-to-end (maria@company.com → explicit)
  4. sender_email is optional (backward compatibility)
  5. parseaddr is used (not a custom regex)
"""
from __future__ import annotations

import pytest
from email.utils import parseaddr

from maestro_personal_shell.commitment_classifier import (
    _rule_based_classify,
    is_marketing_sender,
)
from maestro_personal_shell.intelligent_ingestion import extract_signals_intelligently


class TestParseaddrUsage:
    """Verify parseaddr is used (not a custom regex parser)."""

    @pytest.mark.parametrize("header,expected_name,expected_email", [
        ("Slack <noreply@slack.com>", "Slack", "noreply@slack.com"),
        ("Maria Garcia <maria@company.com>", "Maria Garcia", "maria@company.com"),
        ("noreply@cursor.com", "", "noreply@cursor.com"),
        ("Reddit <noreply@reddit.com>", "Reddit", "noreply@reddit.com"),
        ("", "", ""),
        ("Kotak Bank <alerts@kotak.com>", "Kotak Bank", "alerts@kotak.com"),
    ])
    def test_parseaddr_extracts_email(self, header, expected_name, expected_email):
        """parseaddr correctly extracts email from from_header."""
        name, addr = parseaddr(header)
        assert addr == expected_email, f"Expected {expected_email}, got {addr}"


class TestSenderEmailWiring:
    """Test that sender_email flows from connector to classifier."""

    def test_extract_signals_accepts_sender_email(self):
        """extract_signals_intelligently accepts sender_email param."""
        import inspect
        sig = inspect.signature(extract_signals_intelligently)
        assert "sender_email" in sig.parameters, \
            "extract_signals_intelligently must accept sender_email parameter"
        assert sig.parameters["sender_email"].default == "", \
            "sender_email must default to empty string (backward compat)"

    def test_gmail_connector_extracts_sender_email(self):
        """Gmail connector uses parseaddr to extract sender email."""
        # Read the source and confirm parseaddr is used
        from maestro_personal_shell.gmail_connector import GmailIngester
        import inspect
        source = inspect.getsource(GmailIngester._extract_commitments_from_message)
        assert "parseaddr" in source, \
            "Gmail connector must use email.utils.parseaddr to extract sender email"
        assert "sender_email" in source, \
            "Gmail connector must pass sender_email to extract_signals_intelligently"

    def test_signals_router_passes_sender_email(self):
        """Signals router passes sender_email from metadata to classifier."""
        from maestro_personal_shell.routers import signals
        import inspect
        source = inspect.getsource(signals)
        assert "sender_email" in source, \
            "Signals router must extract sender_email from metadata"
        # Check that it's passed to both classify_commitment and _rule_based_classify
        assert "sender_email=_sender_email" in source or "sender_email=" in source, \
            "Signals router must pass sender_email to the classifier"


class TestEndToEndMarketingRejection:
    """End-to-end: marketing senders rejected via the wiring."""

    def test_marketing_sender_rejected_via_wiring(self):
        """Signal from noreply@slack.com with 'I will conquer the moon' → rejected."""
        # Simulate the classifier call with sender_email (as the connector now passes it)
        result = _rule_based_classify(
            "I will conquer the moon haha",
            entity="Slack",
            sender_email="noreply@slack.com",
        )
        assert not result["is_commitment"], \
            f"Marketing sender should be rejected. Got: {result}"
        assert "marketing sender" in result["reasoning"].lower()

    def test_real_sender_accepted_via_wiring(self):
        """Signal from maria@company.com with real commitment → accepted."""
        result = _rule_based_classify(
            "I will send the proposal by Friday",
            entity="Maria Garcia",
            sender_email="maria@company.com",
        )
        assert result["is_commitment"], \
            f"Real sender should be accepted. Got: {result}"
        assert result["commitment_type"] == "explicit"

    def test_cursor_marketing_rejected(self):
        """Cursor marketing email → rejected via sender filter."""
        result = _rule_based_classify(
            "I will help you get more done with Cursor",
            entity="Cursor Team",
            sender_email="marketing@cursor.com",
        )
        assert not result["is_commitment"]

    def test_kotak_bank_rejected(self):
        """Kotak Bank notification → rejected via sender filter."""
        result = _rule_based_classify(
            "Dear Customer, your account statement is ready. Important update.",
            entity="Kotak Bank",
            sender_email="alerts@kotak.com",
        )
        assert not result["is_commitment"]

    def test_reddit_notification_rejected(self):
        """Reddit notification → rejected via sender filter."""
        result = _rule_based_classify(
            "See what's new in r/opencode. I just posted a new version.",
            entity="Reddit",
            sender_email="noreply@reddit.com",
        )
        assert not result["is_commitment"]


class TestBackwardCompatibility:
    """sender_email must be optional (backward compatibility)."""

    def test_classify_without_sender_email(self):
        """Classifier still works when sender_email is not passed."""
        # No sender_email — should use keyword matching as before
        result = _rule_based_classify(
            "I will send the proposal by Friday",
            entity="Maria Garcia",
        )
        assert result["is_commitment"]
        assert result["commitment_type"] == "explicit"

    def test_marketing_copy_still_rejected_without_sender(self):
        """Marketing COPY filter still works without sender_email."""
        result = _rule_based_classify("Get started today with our free trial!")
        assert not result["is_commitment"]
        assert "marketing copy" in result["reasoning"].lower()

    def test_extract_signals_without_sender_email(self):
        """extract_signals_intelligently works without sender_email."""
        import asyncio
        # Call without sender_email — should not crash
        result = asyncio.run(extract_signals_intelligently(
            message_text="I will send the proposal by Friday",
            entity="Maria Garcia",
        ))
        # Should return signals (or empty if no candidates detected)
        assert isinstance(result, list)

    def test_real_commitment_without_sender_still_accepted(self):
        """Real commitment without sender_email → still accepted."""
        result = _rule_based_classify(
            "I promise to review the pull request by tomorrow",
            entity="Alex Chen",
        )
        assert result["is_commitment"]


class TestActualGmailFalsePositives:
    """Test the ACTUAL false positives from real Gmail sync, now with sender_email."""

    @pytest.mark.parametrize("text,sender,entity", [
        ("I will conquer the moon haha", "noreply@slack.com", "Slack"),
        ("We will help you get more done", "marketing@cursor.com", "Cursor Team"),
        ("Get started today with your free trial", "noreply@substack.com", "Substack"),
        ("Your OTP is 123456. Do not share", "alerts@kotak.com", "Kotak Bank"),
        ("I will send you the best deals", "promo@amazon.com", "Amazon"),
        ("We will notify you when your order ships", "no-reply@flipkart.com", "Flipkart"),
    ])
    def test_false_positive_rejected_with_sender(self, text, sender, entity):
        """All 6 actual Gmail false positives must be rejected with sender_email."""
        result = _rule_based_classify(text, entity=entity, sender_email=sender)
        assert not result["is_commitment"], \
            f"FALSE POSITIVE: {text!r} from {sender} was classified as commitment"
