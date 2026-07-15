"""
Phase 5 Prepare benchmark — 50 meeting scenarios.

The roadmap (ROAD_TO_9_OF_10_AFTER_395558A.md Phase 5) requires:
  - 50-meeting benchmark
  - Human reference briefs
  - Meeting-specific retrieval: attendees, prior threads, commitments
    involving attendees, unresolved disputes, changed deadlines, prior objections
  - Output max 3-5 bullets
  - Penalize irrelevant true facts

Each meeting scenario has:
  - meeting_id: unique identifier
  - entity: the primary entity/person being met with
  - attendees: list of attendees (for retrieval scoping)
  - meeting_context: what the meeting is about
  - signals: list of signals to seed (prior threads, commitments, disputes)
  - reference_brief: the ideal 3-5 bullet points a human would write
  - irrelevant_true_facts: facts that are TRUE but should NOT appear (penalize)
  - expected_keywords: keywords that should appear in a good brief

The benchmark is used by the Prepare eval harness to measure usefulness
(target >= 4.3/5) and bullet count (max 3-5).
"""

from __future__ import annotations

from typing import Any
import itertools

ENTITIES = ["Alex", "Maria", "Priya", "Sam", "Morgan", "Avery", "Dana",
            "Marco", "Yuki", "David"]
PROJECTS = ["Vega", "Orion", "Aurora", "Phoenix", "Globex"]


def _build_meetings() -> list[dict[str, Any]]:
    meetings: list[dict[str, Any]] = []

    def add(meeting_id, entity, attendees, context, signals, brief, irrelevant, keywords):
        meetings.append({
            "meeting_id": meeting_id,
            "entity": entity,
            "attendees": attendees,
            "meeting_context": context,
            "signals": signals,
            "reference_brief": brief,
            "irrelevant_true_facts": irrelevant,
            "expected_keywords": keywords,
        })

    # Generate 50 meetings: 10 meeting types x 5 entities each
    meeting_types = [
        # 1. Commitment review (10 meetings)
        ("commitment_review", "Q3 commitment review with {entity}",
         "Review outstanding commitments and deadlines",
         ["I will send the proposal by Friday",
          "The roadmap needs updating"],
         ["Review the proposal commitment",
          "Check if the roadmap is on track"],
         ["Last quarter's revenue was $2M",
          "The office is being repainted"],
         ["proposal", "roadmap", "commitment"]),

        # 2. Project status (10 meetings)
        ("project_status", "{entity} project status check",
         "Check status of ongoing projects",
         ["Project Vega is behind schedule",
          "The Orion design review is next week"],
         ["Vega is behind schedule — discuss mitigation",
          "Orion design review next week — prepare feedback"],
         ["The company holiday party is planned",
          "HR is hiring a new recruiter"],
         ["Vega", "Orion", "status"]),

        # 3. Dispute resolution (5 meetings)
        ("dispute_resolution", "Dispute resolution with {entity}",
         "Resolve a disputed deliverable",
         ["We got the proposal but it's missing the appendix",
          "The contract terms are disputed"],
         ["Address the missing appendix in the proposal",
          "Resolve the contract term dispute"],
         ["The weather forecast is sunny",
          "Coffee machine is broken"],
         ["dispute", "appendix", "contract"]),

        # 4. Deadline change (5 meetings)
        ("deadline_change", "Deadline renegotiation with {entity}",
         "Renegotiate a changed deadline",
         ["The proposal deadline moved to next Monday",
          "The budget review is delayed by a week"],
         ["Confirm the new Monday proposal deadline",
          "Discuss the budget review delay"],
         ["The stock market is volatile",
          "A new coffee shop opened nearby"],
         ["deadline", "Monday", "delay"]),

        # 5. Prior objection (5 meetings)
        ("prior_objection", "Follow-up with {entity} on prior objection",
         "Address a prior objection raised by the entity",
         ["{entity} objected to the timeline last time",
          "The timeline was too aggressive per {entity}"],
         ["Acknowledge the timeline objection",
          "Propose a revised timeline"],
         ["The CEO is traveling next week",
          "IT is upgrading the servers"],
         ["objection", "timeline"]),

        # 6. Stale commitment (5 meetings)
        ("stale_commitment", "Stale commitment follow-up with {entity}",
         "Follow up on a stale commitment",
         ["I will send the scorecard by last Friday",
          "The dashboard update is overdue"],
         ["The scorecard is overdue — escalate",
          "Dashboard update is stale — get status"],
         ["The parking lot is being resurfaced",
          "Lunch is catered today"],
         ["stale", "overdue", "scorecard"]),

        # 7. Completion verification (5 meetings)
        ("completion_verification", "Completion verification with {entity}",
         "Verify whether a commitment was completed",
         ["I sent the proposal yesterday",
          "The report has been delivered"],
         ["Verify the proposal was actually sent",
          "Confirm the report delivery"],
         ["The gym is offering new classes",
          "A new policy was posted"],
         ["completed", "sent", "verify"]),

        # 8. New commitment (5 meetings)
        ("new_commitment", "New commitment planning with {entity}",
         "Plan a new commitment for the upcoming period",
         ["We need to plan the Q4 deliverables",
          "The new roadmap needs commitments"],
         ["Define Q4 deliverable commitments",
          "Assign roadmap ownership"],
         ["The holiday schedule is posted",
          "The vending machine is restocked"],
         ["Q4", "deliverable", "commitment"]),
    ]

    # Generate meetings by combining types x entities
    entity_idx = 0
    for mtype, title_template, context, signal_texts, brief, irrelevant, keywords in meeting_types:
        # Number of meetings per type: commitment_review=10, project_status=10, others=5
        count = 10 if "review" in mtype or "status" in mtype else 5
        for i in range(count):
            entity = ENTITIES[entity_idx % len(ENTITIES)]
            entity_idx += 1
            title = title_template.format(entity=entity)
            # Build signals with timestamps
            signals = []
            for j, text in enumerate(signal_texts):
                signals.append({
                    "entity": entity,
                    "text": text.format(entity=entity) if "{entity}" in text else text,
                    "signal_type": "commitment_made" if "will" in text or "need" in text else "reported_statement",
                    "timestamp": f"2026-07-{10+j:02d}T10:00:00Z",
                })
            # Build brief with entity substitution
            brief_with_entity = [b.format(entity=entity) if "{entity}" in b else b for b in brief]
            irrelevant_with_entity = [i.format(entity=entity) if "{entity}" in i else i for i in irrelevant]
            add(
                f"meeting-{len(meetings)+1:03d}",
                entity, [entity], context, signals,
                brief_with_entity, irrelevant_with_entity, keywords,
            )

    return meetings


MEETINGS: list[dict[str, Any]] = _build_meetings()


def get_prepare_benchmark() -> list[dict[str, Any]]:
    """Return the 50-meeting Prepare benchmark."""
    return MEETINGS


def get_benchmark_stats() -> dict[str, int]:
    """Return per-type counts."""
    stats: dict[str, int] = {}
    for m in MEETINGS:
        mtype = m.get("meeting_context", "unknown")
        stats[mtype] = stats.get(mtype, 0) + 1
    return stats


if __name__ == "__main__":
    meetings = get_prepare_benchmark()
    print(f"Total meetings: {len(meetings)}")
    print(f"Meeting types: {len(get_benchmark_stats())}")
    for k, v in sorted(get_benchmark_stats().items()):
        print(f"  {k:40s} {v}")
    print(f"\nSample meeting:")
    import json
    print(json.dumps(meetings[0], indent=2))
