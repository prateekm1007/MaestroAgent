"""
Synthetic Inbox — 20 mutable demo emails for beta users to experience the
full commitment lifecycle without Gmail OAuth.

Per audit Session 8: "Build synthetic inbox (20 mutable emails) — PMF 4→6,
Consumer Readiness 7→8, Memory 6→7"

The inbox contains 20 realistic emails across 6 categories:
  - 5 new commitments ("I'll send the report by Friday")
  - 3 completion confirmations ("Got it, thanks!")
  - 2 cancellations ("Actually, forget about that")
  - 5 FYI/newsletter (should NOT create commitments)
  - 3 contradictions ("I said Tuesday but now it's Thursday")
  - 2 ambiguous ("I'll try to get it done")

Users can:
  - "Receive" a new email → triggers commitment extraction
  - "Reply" to an email → triggers reconciliation
  - See the commitment lifecycle: detected → active → resolved
  - Experience the full product thesis without OAuth

API endpoints:
  GET  /api/inbox/synthetic    — list all 20 emails with their state
  POST /api/inbox/synthetic/{email_id}/receive  — ingest the email as a signal
  POST /api/inbox/synthetic/{email_id}/reply    — send a reply (triggers reconciliation)
  GET  /api/inbox/synthetic/status  — summary of what happened (commitments created, resolved, etc.)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger(__name__)


# 20 synthetic emails across 6 categories
# Each email has: id, from, subject, body, category, expected_effect
SYNTHETIC_EMAILS: list[dict[str, Any]] = [
    # === 5 new commitments ===
    {
        "id": "email_01",
        "from": "maria.garcia@acme.com",
        "from_name": "Maria Garcia",
        "subject": "Re: Q3 Budget Proposal",
        "body": "Thanks for the call. I will send the Q3 budget proposal by Friday EOD.",
        "category": "new_commitment",
        "expected_effect": "Creates active commitment: 'send Q3 budget proposal' → Maria Garcia, deadline Friday",
    },
    {
        "id": "email_02",
        "from": "alex.chen@tech.io",
        "from_name": "Alex Chen",
        "subject": "PR Review",
        "body": "I'll review the auth module PR by Tuesday next week.",
        "category": "new_commitment",
        "expected_effect": "Creates active commitment: 'review auth module PR' → Alex Chen, deadline Tuesday",
    },
    {
        "id": "email_03",
        "from": "jamie.lee@design.co",
        "from_name": "Jamie Lee",
        "subject": "Design mockups",
        "body": "I will deliver the design mockups by Wednesday.",
        "category": "new_commitment",
        "expected_effect": "Creates active commitment: 'deliver design mockups' → Jamie Lee, deadline Wednesday",
    },
    {
        "id": "email_04",
        "from": "sam.rivera@pm.org",
        "from_name": "Sam Rivera",
        "subject": "Roadmap presentation",
        "body": "I'll finalize the Q3 roadmap presentation by next Monday.",
        "category": "new_commitment",
        "expected_effect": "Creates active commitment: 'finalize Q3 roadmap presentation' → Sam Rivera",
    },
    {
        "id": "email_05",
        "from": "priya.patel@eng.dev",
        "from_name": "Priya Patel",
        "subject": "CI pipeline",
        "body": "I will fix the flaky CI pipeline this week.",
        "category": "new_commitment",
        "expected_effect": "Creates active commitment: 'fix flaky CI pipeline' → Priya Patel",
    },

    # === 3 completion confirmations ===
    {
        "id": "email_06",
        "from": "maria.garcia@acme.com",
        "from_name": "Maria Garcia",
        "subject": "Re: Pricing proposal received",
        "body": "Maria confirmed she received the pricing proposal. Thanks!",
        "category": "completion",
        "expected_effect": "Resolves the 'send pricing proposal' commitment → completed_claimed",
    },
    {
        "id": "email_07",
        "from": "jamie.lee@design.co",
        "from_name": "Jamie Lee",
        "subject": "Re: Design mockups delivered",
        "body": "Design mockups delivered — 12 screens uploaded to Figma.",
        "category": "completion",
        "expected_effect": "Resolves the 'deliver design mockups' commitment → completed_claimed",
    },
    {
        "id": "email_08",
        "from": "alex.chen@tech.io",
        "from_name": "Alex Chen",
        "subject": "Re: PR reviewed",
        "body": "Thanks, got it! The PR has been reviewed and merged.",
        "category": "completion",
        "expected_effect": "Resolves the 'review auth module PR' commitment → completed_claimed",
    },

    # === 2 cancellations ===
    {
        "id": "email_09",
        "from": "sam.rivera@pm.org",
        "from_name": "Sam Rivera",
        "subject": "Re: Roadmap presentation",
        "body": "Actually, forget about the roadmap presentation — we're pushing it to Q4.",
        "category": "cancellation",
        "expected_effect": "Cancels the 'finalize Q3 roadmap presentation' commitment",
    },
    {
        "id": "email_10",
        "from": "priya.patel@eng.dev",
        "from_name": "Priya Patel",
        "subject": "Re: CI pipeline",
        "body": "Never mind, we don't need to fix the CI pipeline — it was a false alarm.",
        "category": "cancellation",
        "expected_effect": "Cancels the 'fix flaky CI pipeline' commitment",
    },

    # === 5 FYI/newsletter (should NOT create commitments) ===
    {
        "id": "email_11",
        "from": "newsletter@producthunt.com",
        "from_name": "Product Hunt",
        "subject": "Daily digest: 10 new products",
        "body": "Check out today's top products: AI-powered todo app, new calendar tool, etc.",
        "category": "fyi",
        "expected_effect": "Should NOT create a commitment (newsletter)",
    },
    {
        "id": "email_12",
        "from": "hr@company.com",
        "from_name": "HR",
        "subject": "Office closure notice",
        "body": "The office will be closed on Monday for the holiday. Enjoy the long weekend!",
        "category": "fyi",
        "expected_effect": "Should NOT create a commitment (FYI)",
    },
    {
        "id": "email_13",
        "from": "billing@aws.com",
        "from_name": "AWS Billing",
        "subject": "Your monthly invoice",
        "body": "Your AWS bill for this month is $342.18. Payment will be processed automatically.",
        "category": "fyi",
        "expected_effect": "Should NOT create a commitment (billing notice)",
    },
    {
        "id": "email_14",
        "from": "github@notifications.com",
        "from_name": "GitHub",
        "subject": "Security alert",
        "body": "A new SSH key was added to your account. If this was you, no action needed.",
        "category": "fyi",
        "expected_effect": "Should NOT create a commitment (security notification)",
    },
    {
        "id": "email_15",
        "from": "linkedin@notifications.com",
        "from_name": "LinkedIn",
        "subject": "You appeared in 3 searches this week",
        "body": "See who's been looking at your profile. Upgrade to Premium for more insights.",
        "category": "fyi",
        "expected_effect": "Should NOT create a commitment (social notification)",
    },

    # === 3 contradictions ===
    {
        "id": "email_16",
        "from": "maria.garcia@acme.com",
        "from_name": "Maria Garcia",
        "subject": "Re: Deadline change",
        "body": "I know I said Friday, but can we move it to next Wednesday instead?",
        "category": "contradiction",
        "expected_effect": "Updates the deadline (if a commitment exists) or creates a new one with Wednesday deadline",
    },
    {
        "id": "email_17",
        "from": "alex.chen@tech.io",
        "from_name": "Alex Chen",
        "subject": "Re: PR review status",
        "body": "I said I'd review by Tuesday, but I actually already reviewed it yesterday.",
        "category": "contradiction",
        "expected_effect": "May resolve the commitment (already done) despite the Tuesday deadline",
    },
    {
        "id": "email_18",
        "from": "jamie.lee@design.co",
        "from_name": "Jamie Lee",
        "subject": "Re: Mockup count",
        "body": "Wait, I said 12 screens but it's actually 15 — I added 3 more sections.",
        "category": "contradiction",
        "expected_effect": "Updates the commitment details (12 → 15 screens)",
    },

    # === 2 ambiguous ===
    {
        "id": "email_19",
        "from": "dana.wong@consulting.com",
        "from_name": "Dana Wong",
        "subject": "Re: Follow up",
        "body": "I'll try to get it done, but don't count on it.",
        "category": "ambiguous",
        "expected_effect": "Creates a TENTATIVE commitment (low confidence) — not a firm promise",
    },
    {
        "id": "email_20",
        "from": "david.kim@startup.io",
        "from_name": "David Kim",
        "subject": "Re: Coffee?",
        "body": "Maybe we can grab coffee next week? I'll let you know.",
        "category": "ambiguous",
        "expected_effect": "Should NOT create a commitment (tentative social plan)",
    },
]


def get_synthetic_emails() -> list[dict[str, Any]]:
    """Return all 20 synthetic emails."""
    return SYNTHETIC_EMAILS


def get_email_by_id(email_id: str) -> dict[str, Any] | None:
    """Find a synthetic email by ID."""
    for e in SYNTHETIC_EMAILS:
        if e["id"] == email_id:
            return e
    return None


def get_inbox_summary(received_emails: list[str]) -> dict[str, Any]:
    """Summarize what happened when the user received specific emails.
    
    Args:
        received_emails: list of email IDs the user has 'received'
    
    Returns:
        summary dict with counts by category + expected effects
    """
    by_category = {}
    for eid in received_emails:
        email = get_email_by_id(eid)
        if not email:
            continue
        cat = email["category"]
        by_category.setdefault(cat, []).append({
            "id": eid,
            "from": email["from_name"],
            "subject": email["subject"],
            "expected_effect": email["expected_effect"],
        })
    
    return {
        "total_received": len(received_emails),
        "by_category": {cat: len(items) for cat, items in by_category.items()},
        "emails": by_category,
    }
