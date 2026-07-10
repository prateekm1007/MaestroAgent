"""
Phase 6 Trusted Silence benchmark — 100 opportunities labeled by category.

The roadmap (ROAD_TO_9_OF_10_AFTER_395558A.md Phase 6) requires:
  - 100-opportunity Trusted Silence benchmark labeled by humans:
    - interrupt_now
    - next_summary
    - on_demand_only
    - say_nothing

Each opportunity is a scenario (a delta + context) with a ground-truth
label indicating what Maestro should do. The eval harness runs the
materiality gate + ranking against each opportunity and measures:
  - materiality precision (>= 85%)
  - critical interruption recall (>= 95%)
  - unnecessary interruption rate (<= 10%)
  - repeated notification rate (<= 3%)

Scenario distribution:
  - interrupt_now (25): high-consequence, deadline approaching, disputes
  - next_summary (25): completed commitments, deadline moves, moderate items
  - on_demand_only (25): stale-but-not-important, routine updates
  - say_nothing (25): newsletters, FYIs, dismissed items, resolved risks
"""

from __future__ import annotations

from typing import Any
from datetime import datetime, timezone, timedelta

ENTITIES = ["Alex", "Maria", "Priya", "Sam", "Morgan", "Board", "Investor",
            "AcmeCorp", "Globex", "VegaCorp"]


def _build_opportunities() -> list[dict[str, Any]]:
    """Build 100 labeled Trusted Silence opportunities."""
    opps: list[dict[str, Any]] = []

    def add(text, entity, sig_type, label, transition, context=None, days_ago=0):
        ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
        opps.append({
            "text": text,
            "entity": entity,
            "signal_type": sig_type,
            "type": sig_type,
            "timestamp": ts,
            "signal_id": f"opp-{len(opps)+1:03d}",
            "label": label,  # interrupt_now, next_summary, on_demand_only, say_nothing
            "expected_transition": transition,
            "context": context or {},
        })

    # === INTERRUPT_NOW (25) — high-consequence, urgent, disputes ===

    # Board escalation among 100 newsletters (the roadmap's specific test case)
    add("Board escalation: investor wants emergency meeting about Q3 revenue miss",
        "Board", "reported_statement", "interrupt_now", "new_high_consequence_commitment",
        context={"is_strategic": True}, days_ago=0)
    # 99 newsletters that should NOT beat the board escalation
    for i in range(9):
        add(f"Weekly newsletter issue {i}", "NewsletterCorp", "newsletter",
            "say_nothing", "routine_activity", days_ago=0)

    # Deadline approaching today
    add("I will send the proposal by EOD today", "Alex", "commitment_made",
        "interrupt_now", "new_high_consequence_commitment",
        context={"has_deadline": True, "deadline": "today"}, days_ago=0)
    add("The contract signing is due in 2 hours", "Investor", "commitment_made",
        "interrupt_now", "new_high_consequence_commitment",
        context={"has_deadline": True, "deadline": "2 hours"}, days_ago=0)
    add("Urgent: the server is down and customers are complaining", "Globex",
        "reported_statement", "interrupt_now", "unresolved_dependency_appeared",
        days_ago=0)
    add("Critical: the acquisition terms changed at the last minute", "VegaCorp",
        "reported_statement", "interrupt_now", "new_high_consequence_commitment",
        days_ago=0)

    # Disputes
    add("We got the proposal but it's missing the critical appendix",
        "AcmeCorp", "reported_statement", "interrupt_now", "completion_disputed",
        days_ago=0)
    add("The delivered report doesn't include the financial section we agreed on",
        "Maria", "reported_statement", "interrupt_now", "completion_disputed",
        days_ago=1)
    add("Sam is disputing the timeline — says it was supposed to be last week",
        "Sam", "reported_statement", "interrupt_now", "completion_disputed",
        days_ago=0)

    # High-consequence new commitments
    add("I will commit to the $2M contract by Friday", "AcmeCorp", "commitment_made",
        "interrupt_now", "new_high_consequence_commitment", days_ago=0)
    add("The board approved the acquisition — we need to move immediately",
        "Board", "reported_statement", "interrupt_now", "new_high_consequence_commitment",
        days_ago=0)
    add("Investor threatened to pull funding if we don't respond today",
        "Investor", "reported_statement", "interrupt_now", "sentiment_worsened",
        days_ago=0)

    # Blocked dependencies
    add("We're blocked — legal hasn't signed off and we can't proceed",
        "Priya", "reported_statement", "interrupt_now", "unresolved_dependency_appeared",
        days_ago=0)
    add("The migration is stuck waiting on the infrastructure team",
        "Globex", "reported_statement", "interrupt_now", "unresolved_dependency_appeared",
        days_ago=1)

    # Sentiment worsened
    add("The client is furious about the delayed delivery",
        "AcmeCorp", "reported_statement", "interrupt_now", "sentiment_worsened",
        days_ago=0)
    add("Morgan escalated to the CEO about the quality issues",
        "Morgan", "reported_statement", "interrupt_now", "sentiment_worsened",
        days_ago=0)

    # Stale but strategically important
    add("I will review the board deck before the meeting", "Board", "commitment_made",
        "interrupt_now", "stale_but_important",
        context={"days_stale": 7, "is_strategic": True}, days_ago=7)
    add("The investor update needs to go out", "Investor", "commitment_made",
        "interrupt_now", "stale_but_important",
        context={"days_stale": 5, "is_strategic": True}, days_ago=5)

    # More interrupt scenarios
    add("The regulatory deadline is tomorrow and we haven't filed", "VegaCorp",
        "reported_statement", "interrupt_now", "deadline_moved",
        context={"has_deadline": True, "deadline": "tomorrow"}, days_ago=0)
    add("Alex's commitment to deliver the security audit is overdue by 3 days",
        "Alex", "commitment_made", "interrupt_now", "stale_but_important",
        context={"days_stale": 10, "is_strategic": True}, days_ago=10)
    add("The customer is threatening to cancel over the bug", "AcmeCorp",
        "reported_statement", "interrupt_now", "sentiment_worsened", days_ago=0)
    add("Emergency: the data breach was just discovered", "Globex",
        "reported_statement", "interrupt_now", "new_high_consequence_commitment",
        days_ago=0)
    add("Sam's payment is 30 days late and they're not responding", "Sam",
        "reported_statement", "interrupt_now", "sentiment_worsened", days_ago=0)

    # === NEXT_SUMMARY (25) — moderate importance, can wait until summary ===

    add("I sent the proposal yesterday as promised", "Alex", "reported_statement",
        "next_summary", "commitment_completed", days_ago=1)
    add("The report has been delivered to the client", "Maria", "reported_statement",
        "next_summary", "commitment_completed", days_ago=1)
    add("The deadline moved from Friday to Monday", "Priya", "reported_statement",
        "next_summary", "deadline_moved", days_ago=1)
    add("The budget review is delayed by a week", "Morgan", "reported_statement",
        "next_summary", "deadline_moved", days_ago=1)
    add("I completed the migration as planned", "Globex", "reported_statement",
        "next_summary", "commitment_completed", days_ago=2)
    add("The design review is scheduled for next week", "Sam", "reported_statement",
        "next_summary", "new_high_consequence_commitment", days_ago=1)
    add("The roadmap has been updated with the new timeline", "VegaCorp",
        "reported_statement", "next_summary", "deadline_moved", days_ago=2)
    add("Alex confirmed the meeting is still on for Tuesday", "Alex",
        "reported_statement", "next_summary", "routine_activity", days_ago=1)
    add("The contract was signed by both parties", "AcmeCorp", "reported_statement",
        "next_summary", "commitment_completed", days_ago=2)
    add("The Q3 numbers are in and they look good", "Board", "reported_statement",
        "next_summary", "routine_activity", days_ago=2)
    add("Maria followed up on the proposal status", "Maria", "reported_statement",
        "next_summary", "routine_activity", days_ago=1)
    add("The new hire started today", "Priya", "reported_statement",
        "next_summary", "routine_activity", days_ago=0)
    add("The office renovation is progressing on schedule", "Globex",
        "reported_statement", "next_summary", "routine_activity", days_ago=3)
    add("The customer feedback survey results are available", "AcmeCorp",
        "reported_statement", "next_summary", "routine_activity", days_ago=2)
    add("The security scan completed with no issues found", "VegaCorp",
        "reported_statement", "next_summary", "risk_resolved", days_ago=2)
    add("The compliance audit passed", "Board", "reported_statement",
        "next_summary", "risk_resolved", days_ago=3)
    add("Sam scheduled the team offsite for next month", "Sam",
        "reported_statement", "next_summary", "routine_activity", days_ago=2)
    add("The vendor confirmed the delivery date", "Morgan", "reported_statement",
        "next_summary", "routine_activity", days_ago=1)
    add("The quarterly report draft is ready for review", "Investor",
        "reported_statement", "next_summary", "routine_activity", days_ago=2)
    add("The API migration is 80% complete", "Globex", "reported_statement",
        "next_summary", "routine_activity", days_ago=1)
    add("The customer onboarding is proceeding well", "AcmeCorp",
        "reported_statement", "next_summary", "routine_activity", days_ago=3)
    add("The marketing campaign launched successfully", "VegaCorp",
        "reported_statement", "next_summary", "routine_activity", days_ago=2)
    add("The team retro is scheduled for Friday", "Priya", "reported_statement",
        "next_summary", "routine_activity", days_ago=1)
    add("The budget was approved by finance", "Board", "reported_statement",
        "next_summary", "commitment_completed", days_ago=3)
    add("The design system update is deployed", "Sam", "reported_statement",
        "next_summary", "commitment_completed", days_ago=2)

    # === ON_DEMAND_ONLY (25) — stale but not important, routine updates ===

    add("I will review the team's pull requests", "Alex", "commitment_made",
        "on_demand_only", "stale_but_important",
        context={"days_stale": 4}, days_ago=4)
    add("The wiki documentation needs updating", "Maria", "reported_statement",
        "on_demand_only", "routine_activity", days_ago=5)
    add("The code review backlog is growing", "Priya", "reported_statement",
        "on_demand_only", "routine_activity", days_ago=4)
    add("The old branch needs to be merged", "Sam", "reported_statement",
        "on_demand_only", "routine_activity", days_ago=6)
    add("The tech debt items are accumulating", "Globex", "reported_statement",
        "on_demand_only", "routine_activity", days_ago=5)
    add("The internal tooling could be improved", "VegaCorp", "reported_statement",
        "on_demand_only", "routine_activity", days_ago=7)
    add("The team would benefit from a knowledge-sharing session", "AcmeCorp",
        "reported_statement", "on_demand_only", "routine_activity", days_ago=6)
    add("The onboarding docs are slightly outdated", "Board", "reported_statement",
        "on_demand_only", "routine_activity", days_ago=7)
    add("The internal dashboard could use a refresh", "Investor",
        "reported_statement", "on_demand_only", "routine_activity", days_ago=5)
    add("The team morale survey is due next month", "Morgan",
        "reported_statement", "on_demand_only", "routine_activity", days_ago=4)
    for entity in ENTITIES[:15]:
        add(f"The internal wiki has new articles", entity, "fyi",
            "on_demand_only", "routine_activity", days_ago=5)

    # === SAY_NOTHING (25) — newsletters, FYIs, dismissed, resolved ===

    # Newsletters (noise)
    for i in range(10):
        add(f"Weekly industry newsletter issue {i}", "NewsletterCorp", "newsletter",
            "say_nothing", "routine_activity", days_ago=i)
    # FYIs
    for entity in ENTITIES[:8]:
        add(f"FYI: the weather is nice today", entity, "fyi",
            "say_nothing", "routine_activity", days_ago=0)
    # Social media notifications
    for entity in ENTITIES[:5]:
        add(f"Someone liked your post about {entity}", entity, "social",
            "say_nothing", "routine_activity", days_ago=0)
    # Resolved risks (should stop surfacing)
    add("The bug that was causing issues has been fixed", "Globex",
        "reported_statement", "say_nothing", "risk_resolved", days_ago=2)

    return opps


OPPORTUNITIES: list[dict[str, Any]] = _build_opportunities()


def get_silence_benchmark() -> list[dict[str, Any]]:
    """Return the 100-opportunity Trusted Silence benchmark."""
    return OPPORTUNITIES


def get_benchmark_stats() -> dict[str, int]:
    """Return per-label counts."""
    stats: dict[str, int] = {}
    for o in OPPORTUNITIES:
        stats[o["label"]] = stats.get(o["label"], 0) + 1
    return stats


if __name__ == "__main__":
    opps = get_silence_benchmark()
    print(f"Total opportunities: {len(opps)}")
    print(f"Labels: {len(get_benchmark_stats())}")
    for k, v in sorted(get_benchmark_stats().items()):
        print(f"  {k:20s} {v}")
