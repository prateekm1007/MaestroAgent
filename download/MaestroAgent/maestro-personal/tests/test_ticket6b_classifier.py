"""TICKET-6b: Commitment classifier rejects marketing noise.

Regression tests for the marketing sender filter, marketing copy filter,
and commitment context validation.

The original bug: the classifier matched "I will" anywhere in text, so
marketing copy like "I will conquer the moon haha" (from a Slack marketing
email) was classified as an explicit commitment. 5/5 "commitments" from
real Gmail were false positives from marketing emails.

Fix: three-layer defense —
  1. Marketing sender domain filter (reject by sender)
  2. Marketing copy pattern filter (reject by content)
  3. Commitment context validation (temporal/deliverable markers)

The sender filter takes PRIORITY over keyword matching.
"""
from __future__ import annotations

import pytest

from maestro_personal_shell.commitment_classifier import (
    _rule_based_classify,
    is_marketing_sender,
    is_marketing_copy,
    has_commitment_context,
    MARKETING_DOMAINS,
)


class TestMarketingSenderFilter:
    """Test the is_marketing_sender function."""

    @pytest.mark.parametrize("email,expected", [
        ("noreply@cursor.com", True),
        ("notifications@slack.com", True),
        ("no-reply@github.com", True),
        ("newsletter@substack.com", True),
        ("marketing@hubspot.com", True),
        ("updates@twitter.com", True),
        ("alerts@reddit.com", True),
        ("donotreply@kotak.com", True),
        ("noreply@amazon.com", True),
        ("notification@facebook.com", True),
        # Subdomain of marketing domain
        ("news@mail.cursor.sh", True),
        ("updates@email.slack.com", True),
    ])
    def test_marketing_senders_rejected(self, email, expected):
        assert is_marketing_sender(email) is expected

    @pytest.mark.parametrize("email,expected", [
        ("maria.garcia@gmail.com", False),
        ("alex.chen@company.com", False),
        ("priya.patel@startup.io", False),
        ("founder@realstartup.co", False),
        ("ceo@enterprise.com", False),
        # Personal email providers are NOT marketing senders
        ("user@gmail.com", False),
        ("user@outlook.com", False),
        ("user@yahoo.com", False),
    ])
    def test_real_senders_accepted(self, email, expected):
        assert is_marketing_sender(email) is expected

    def test_empty_sender_accepted(self):
        """Empty sender should not be rejected (backward compatibility)."""
        assert is_marketing_sender("") is False
        assert is_marketing_sender(None) is False


class TestMarketingCopyFilter:
    """Test the is_marketing_copy function."""

    @pytest.mark.parametrize("text", [
        "Get started today with our free trial!",
        "Sign up now for exclusive access",
        "Limited time offer — act now!",
        "Don't miss out on this exclusive deal",
        "Subscribe to our newsletter for updates",
        "Click here to learn more",
        "Shop now and save 50%",
        "Hurry! Last chance to register",
        "You're invited to our webinar",
        "Congratulations on your achievement!",
        "We're excited to introduce our new feature",
        "Introducing the all-new dashboard",
        "What's new in our latest release",
        "Unsubscribe to stop receiving these emails",
        "Your OTP is 123456. Valid for 10 minutes.",
        "Dear Customer, Important Update Scheduled Downtime",
        "Your verification code is 987654",
        "Posted in r/opencode by u/user",
        "See what Richard posted in FA Hayek",
    ])
    def test_marketing_copy_rejected(self, text):
        assert is_marketing_copy(text) is True

    @pytest.mark.parametrize("text", [
        "I will send the Q3 budget proposal by Friday EOD",
        "I promise to review the pull request",
        "Let me take care of that",
        "I'll have the report ready by tomorrow",
        "I am going to deliver the deck next week",
        "Maria said she would review the auth module",
    ])
    def test_real_commitments_not_marketing(self, text):
        assert is_marketing_copy(text) is False


class TestCommitmentContext:
    """Test the has_commitment_context function."""

    @pytest.mark.parametrize("text", [
        "I will send the proposal by Friday",
        "I'll review it by tomorrow EOD",
        "I will deliver the deck next week",
        "I promise to finish the report by July 25",
        "I will send it within 2 days",
        "I'll get back to you before Monday",
        "The deadline is Friday",
        "I will send the report ASAP",
        "I'll review the pull request",
        "I will send the budget proposal",
        "Let me follow up on that",
        "I'll get back to you",
    ])
    def test_real_commitments_have_context(self, text):
        assert has_commitment_context(text) is True

    @pytest.mark.parametrize("text", [
        "I will conquer the moon",
        "Get started today",
        "Move your next project into a channel",
        "Important Update Scheduled Downtime",
    ])
    def test_marketing_copy_lacks_context(self, text):
        assert has_commitment_context(text) is False


class TestClassifierRejectsMarketing:
    """Integration tests: _rule_based_classify rejects marketing noise."""

    def test_rejects_marketing_sender(self):
        """Marketing sender → is_commitment=False, even with commitment text."""
        r = _rule_based_classify(
            "I will send the report by Friday",
            entity="Cursor",
            sender_email="noreply@cursor.com",
        )
        assert r["is_commitment"] is False
        assert r["commitment_type"] == "not_a_commitment"
        assert "marketing sender" in r["reasoning"]

    def test_rejects_marketing_copy_conquer_moon(self):
        """'I will conquer the moon haha' → rejected (joke + marketing)."""
        r = _rule_based_classify("I will conquer the moon haha")
        assert r["is_commitment"] is False
        assert r["commitment_type"] == "not_a_commitment"

    def test_rejects_marketing_copy_get_started(self):
        """'Get started today' → rejected (marketing copy)."""
        r = _rule_based_classify("Get started today with our free trial!")
        assert r["is_commitment"] is False
        assert r["commitment_type"] == "not_a_commitment"
        assert "marketing copy" in r["reasoning"]

    def test_rejects_newsletter_signup(self):
        """Newsletter signup copy → rejected."""
        r = _rule_based_classify("Sign up now for exclusive access to our platform!")
        assert r["is_commitment"] is False

    def test_rejects_bank_notification(self):
        """Bank 'Important Update Scheduled Downtime' → rejected."""
        r = _rule_based_classify(
            "Dear Customer, Important Update Scheduled Downtime. "
            "Your account will be unavailable on Saturday from 2-4 AM."
        )
        assert r["is_commitment"] is False

    def test_rejects_otp_email(self):
        """OTP email → rejected (marketing copy)."""
        r = _rule_based_classify("Your OTP is 123456. Valid for 10 minutes.")
        assert r["is_commitment"] is False

    def test_rejects_social_media_notification(self):
        """Social media notification → rejected."""
        r = _rule_based_classify(
            "See what Richard posted in FA Hayek - the great liberal. "
            "Richard Ebeling posted in the group."
        )
        assert r["is_commitment"] is False

    def test_rejects_slack_marketing(self):
        """Slack marketing email → rejected (marketing sender)."""
        r = _rule_based_classify(
            "Move your next project into a channel",
            entity="Slack",
            sender_email="notifications@slack.com",
        )
        assert r["is_commitment"] is False
        assert "marketing sender" in r["reasoning"]

    def test_rejects_reddit_notification(self):
        """Reddit notification → rejected (marketing sender)."""
        r = _rule_based_classify(
            "r/opencode: OPENCODE NEW VERSION I just updated my Opencode",
            entity="Reddit",
            sender_email="noreply@reddit.com",
        )
        assert r["is_commitment"] is False

    def test_marketing_sender_priority_over_text(self):
        """Even if text looks like a commitment, marketing sender wins."""
        r = _rule_based_classify(
            "I will send the Q3 budget proposal by Friday EOD",
            entity="Cursor",
            sender_email="noreply@cursor.com",
        )
        assert r["is_commitment"] is False
        assert r["commitment_type"] == "not_a_commitment"


class TestClassifierAcceptsRealCommitments:
    """Regression: real commitments must still be accepted."""

    def test_accepts_real_commitment_with_deadline(self):
        """'I will send the Q3 budget by Friday' → accepted."""
        r = _rule_based_classify(
            "I will send the Q3 budget proposal to Maria by Friday EOD",
            entity="Maria Garcia",
        )
        assert r["is_commitment"] is True
        assert r["commitment_type"] == "explicit"

    def test_accepts_real_commitment_no_temporal(self):
        """'I promise to review the PR' → accepted (no temporal marker)."""
        r = _rule_based_classify(
            "I promise to review the pull request",
            entity="Alex Chen",
        )
        assert r["is_commitment"] is True
        assert r["commitment_type"] == "explicit"

    def test_accepts_implicit_commitment(self):
        """'Let me take care of that' → accepted as implicit."""
        r = _rule_based_classify(
            "Let me take care of that",
            entity="Jamie Lee",
        )
        assert r["is_commitment"] is True

    def test_accepts_third_party_report(self):
        """'Maria said she would review' → accepted (third_party_report)."""
        r = _rule_based_classify(
            "Maria said she would review the auth module",
            entity="Maria Garcia",
        )
        # Third-party reports contain "she will" / "he will" — should be
        # classified (not as explicit user commitment, but as some type)
        # The key: it's NOT rejected as marketing.
        assert "marketing" not in r.get("reasoning", "").lower()

    def test_accepts_commitment_from_real_email_sender(self):
        """Real email sender (gmail.com) → not rejected as marketing."""
        r = _rule_based_classify(
            "I will send the proposal by Friday",
            entity="Maria Garcia",
            sender_email="maria.garcia@gmail.com",
        )
        assert r["is_commitment"] is True
        assert r["commitment_type"] == "explicit"

    def test_accepts_commitment_from_company_sender(self):
        """Company email sender → not rejected as marketing."""
        r = _rule_based_classify(
            "I'll review the auth module PR by Tuesday next week",
            entity="Alex Chen",
            sender_email="alex.chen@company.com",
        )
        assert r["is_commitment"] is True


class TestClassifierRejectsNonCommitments:
    """Regression: non-commitments must still be rejected."""

    def test_rejects_question(self):
        """'Should I send the roadmap?' → rejected (not a commitment)."""
        r = _rule_based_classify(
            "Should I send the team the updated roadmap?",
            entity="Sam Rivera",
        )
        assert r["is_commitment"] is False

    def test_rejects_joke(self):
        """'I will conquer the moon haha' → rejected (joke marker)."""
        r = _rule_based_classify("I will conquer the moon haha")
        assert r["is_commitment"] is False

    def test_rejects_negation(self):
        """'I will not be able to send it' → rejected (negation)."""
        r = _rule_based_classify("I will not be able to send the proposal")
        assert r["is_commitment"] is False
        assert r["commitment_type"] == "negation"

    def test_rejects_tentative(self):
        """'Maybe I can send it next week, but don't count on it' → tentative."""
        r = _rule_based_classify(
            "Maybe I can send it next week, but don't count on it"
        )
        assert r["is_commitment"] is False
        assert r["commitment_type"] == "tentative"


class TestRealGmailFalsePositives:
    """Test against the ACTUAL false positives found in real Gmail sync.

    These are the 5 "commitments" that were false positives:
    1. "I will conquer the moon haha" (Slack marketing)
    2. "Important Update Scheduled Downtime" (Kotak Bank)
    3. Reddit notification
    4. Facebook notification
    5. KotakSecurities notification
    6. Railway newsletter
    """

    def test_slack_marketing_false_positive(self):
        """Slack: 'I will conquer the moon haha' → rejected."""
        r = _rule_based_classify(
            "I will conquer the moon haha",
            entity="Slack",
            sender_email="notifications@slack.com",
        )
        assert r["is_commitment"] is False

    def test_kotak_bank_false_positive(self):
        """Kotak Bank: 'Important Update Scheduled Downtime' → rejected."""
        r = _rule_based_classify(
            "Important Update Scheduled Downtime Dear Customer, "
            "Pursuing our endeavour to provide you the best service experience, "
            "we have scheduled a downtime.",
            entity="Kotak Bank",
            sender_email="noreply@kotak.com",
        )
        assert r["is_commitment"] is False

    def test_reddit_notification_false_positive(self):
        """Reddit notification → rejected."""
        r = _rule_based_classify(
            "r/opencode: OPENCODE NEW VERSION I just updated my Opencode "
            "to the new version.",
            entity="Reddit",
            sender_email="noreply@reddit.com",
        )
        assert r["is_commitment"] is False

    def test_facebook_notification_false_positive(self):
        """Facebook notification → rejected."""
        r = _rule_based_classify(
            "See what he posted. Richard Ebeling posted in FA Hayek "
            "- the great liberal July 12 at 2:30 PM.",
            entity="F.A. Hayek",
            sender_email="notification@facebook.com",
        )
        assert r["is_commitment"] is False

    def test_kotak_securities_false_positive(self):
        """KotakSecurities notification → rejected."""
        r = _rule_based_classify(
            "Dear Customer, With reference to your Trading & Demat account "
            "for client code, please find the statement.",
            entity="KotakSecurities",
            sender_email="noreply@kotak.com",
        )
        assert r["is_commitment"] is False

    def test_railway_newsletter_false_positive(self):
        """Railway newsletter → rejected (marketing copy)."""
        r = _rule_based_classify(
            "It's Friday and you know what that means! Here's a summary "
            "of the stuff we shipped this week. What's new: new features, "
            "best practices, and a case study.",
            entity="Railway",
        )
        assert r["is_commitment"] is False
