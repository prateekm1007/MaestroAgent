"""
20-case materiality regression set.

Tests the materiality gate's rule-based fallback across scenarios:
- Should speak: stale commitments, deadlines, at-risk items (10 cases)
- Should stay silent / low materiality: routine, FYI, newsletters (10 cases)

Each case verifies the rule-based materiality gate produces the correct
should_speak decision.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from maestro_personal_shell.materiality_gate import _rule_based_materiality


# ===========================================================================
# Should speak: high-materiality items (10 cases)
# ===========================================================================

class TestShouldSpeak:
    """The materiality gate should speak for high-materiality items."""

    @pytest.mark.parametrize("commitment,context,description", [
        # 1. Stale commitment with deadline
        (
            {"entity": "AcmeCorp", "text": "I will send the proposal", "claim_type": "commitment"},
            {"days_stale": 5, "has_deadline": True, "age_days": 10},
            "stale commitment with deadline",
        ),
        # 2. Very stale commitment (10+ days)
        (
            {"entity": "Client", "text": "I will deliver the report", "claim_type": "commitment"},
            {"days_stale": 10, "has_deadline": False, "age_days": 14},
            "very stale commitment",
        ),
        # 3. User-made promise approaching deadline
        (
            {"entity": "Boss", "text": "I will have the numbers ready", "claim_type": "commitment"},
            {"days_stale": 0, "has_deadline": True, "age_days": 2},
            "user promise with deadline",
        ),
        # 4. Stale + old + user promise (triple signal)
        (
            {"entity": "Board", "text": "I will present the strategy", "claim_type": "commitment"},
            {"days_stale": 7, "has_deadline": True, "age_days": 14},
            "stale + old + deadline",
        ),
        # 5. At-risk: 3 days stale
        (
            {"entity": "Partner", "text": "I will send the contract", "claim_type": "commitment"},
            {"days_stale": 3, "has_deadline": False, "age_days": 5},
            "3 days stale",
        ),
        # 6. Deadline today
        (
            {"entity": "Legal", "text": "I will file the patent", "claim_type": "commitment"},
            {"days_stale": 0, "has_deadline": True, "age_days": 1},
            "deadline today",
        ),
        # 7. Old commitment (2 weeks)
        (
            {"entity": "AcmeCorp", "text": "I will review the terms", "claim_type": "commitment"},
            {"days_stale": 0, "has_deadline": False, "age_days": 14},
            "2-week-old commitment",
        ),
        # 8. Stale + user promise
        (
            {"entity": "Sam", "text": "I promise to deliver", "claim_type": "commitment"},
            {"days_stale": 4, "has_deadline": False, "age_days": 6},
            "stale user promise",
        ),
        # 9. Everything: stale + deadline + old + user promise
        (
            {"entity": "VIP", "text": "I guarantee delivery", "claim_type": "commitment"},
            {"days_stale": 8, "has_deadline": True, "age_days": 20},
            "all signals",
        ),
        # 10. Recent commitment with approaching deadline
        (
            {"entity": "Client", "text": "I will send the invoice", "claim_type": "commitment"},
            {"days_stale": 1, "has_deadline": True, "age_days": 2},
            "recent with deadline",
        ),
    ])
    def test_should_speak(self, commitment, context, description):
        result = _rule_based_materiality(commitment, context)
        assert result["should_speak"] is True, \
            f"Should speak for: {description} — got score {result['materiality_score']}"


# ===========================================================================
# Should stay silent / low materiality (10 cases)
# ===========================================================================

class TestShouldStaySilent:
    """The materiality gate should not over-interrupt for low-materiality items."""

    @pytest.mark.parametrize("commitment,context,description", [
        # 1. Fresh FYI (no deadline, not stale, not a commitment)
        (
            {"entity": "Newsletter", "text": "Check out our new features", "claim_type": "fyi"},
            {"days_stale": 0, "has_deadline": False, "age_days": 0},
            "fresh newsletter",
        ),
        # 2. Fresh FYI 1 day old
        (
            {"entity": "Blog", "text": "New blog post is up", "claim_type": "fyi"},
            {"days_stale": 0, "has_deadline": False, "age_days": 1},
            "1-day-old blog",
        ),
        # 3. Non-commitment received statement
        (
            {"entity": "Random", "text": "They mentioned something", "claim_type": "reported_statement"},
            {"days_stale": 0, "has_deadline": False, "age_days": 2},
            "reported statement",
        ),
        # 4. Fresh non-commitment
        (
            {"entity": "Newsletter", "text": "Weekly digest", "claim_type": "fyi"},
            {"days_stale": 0, "has_deadline": False, "age_days": 0},
            "fresh digest",
        ),
        # 5. Meeting notes (no deadline, not stale)
        (
            {"entity": "Team", "text": "We discussed the roadmap", "claim_type": "meeting_notes"},
            {"days_stale": 0, "has_deadline": False, "age_days": 1},
            "meeting notes",
        ),
        # 6. FYI with no action needed
        (
            {"entity": "HR", "text": "Office closed Monday", "claim_type": "fyi"},
            {"days_stale": 0, "has_deadline": False, "age_days": 0},
            "office closure notice",
        ),
        # 7. Automated notification
        (
            {"entity": "System", "text": "Your subscription renews soon", "claim_type": "notification"},
            {"days_stale": 0, "has_deadline": False, "age_days": 0},
            "subscription notice",
        ),
        # 8. Social media mention
        (
            {"entity": "Twitter", "text": "Someone mentioned you", "claim_type": "mention"},
            {"days_stale": 0, "has_deadline": False, "age_days": 0},
            "social mention",
        ),
        # 9. Calendar reminder (informational, not a commitment)
        (
            {"entity": "Calendar", "text": "Meeting in 1 hour", "claim_type": "calendar"},
            {"days_stale": 0, "has_deadline": False, "age_days": 0},
            "calendar reminder",
        ),
        # 10. Generic FYI
        (
            {"entity": "Info", "text": "Policy updated", "claim_type": "fyi"},
            {"days_stale": 0, "has_deadline": False, "age_days": 3},
            "policy update",
        ),
    ])
    def test_low_materiality(self, commitment, context, description):
        result = _rule_based_materiality(commitment, context)
        # Low-materiality items should have low scores
        assert result["materiality_score"] < 0.5, \
            f"Low materiality expected for: {description} — got {result['materiality_score']}"


# ===========================================================================
# Urgency escalation tests
# ===========================================================================

class TestUrgencyEscalation:
    """Urgency must escalate with staleness and deadlines."""

    def test_stale_escalates_to_high(self):
        result = _rule_based_materiality(
            {"entity": "X", "text": "test", "claim_type": "commitment"},
            {"days_stale": 5, "has_deadline": False, "age_days": 7},
        )
        assert result["urgency"] == "high", "Stale commitment should be high urgency"

    def test_deadline_escalates_to_medium(self):
        result = _rule_based_materiality(
            {"entity": "X", "text": "test", "claim_type": "fyi"},
            {"days_stale": 0, "has_deadline": True, "age_days": 0},
        )
        assert result["urgency"] == "medium", "Deadline should be at least medium urgency"

    def test_no_signals_stays_low(self):
        result = _rule_based_materiality(
            {"entity": "X", "text": "test", "claim_type": "fyi"},
            {"days_stale": 0, "has_deadline": False, "age_days": 0},
        )
        assert result["urgency"] == "low", "No signals should stay low urgency"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
