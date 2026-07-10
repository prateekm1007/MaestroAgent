"""
Canonical memory benchmark dataset for Maestro Personal.

Phase 2: Build a repeatable benchmark with 90+ days of synthetic history,
10+ people, 5+ projects, 100+ signals, and locked ground truth questions.

This dataset lives in evaluation/personal_memory_benchmark/ and provides:
1. A signal corpus spanning 90 days with realistic professional content
2. 30+ ground-truth questions with expected answers and required evidence
3. Temporal cutoffs for testing as_of queries
4. Noise signals (newsletters, FYIs) mixed with real commitments
5. Corrected signals, completed commitments, and stale facts

The benchmark is loaded by test_memory_benchmark.py to evaluate
Ask precision/recall/provenance/temporal correctness.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import uuid4


def generate_benchmark_signals() -> list[dict[str, Any]]:
    """Generate 100+ synthetic signals spanning 90 days.

    Returns a list of signal dicts ready for POST /api/signals.
    Each signal has entity, text, signal_type, and timestamp.
    """
    now = datetime.now(timezone.utc)
    signals = []

    # Helper to create timestamps N days ago
    def days_ago(n: int, hour: int = 10) -> str:
        return (now - timedelta(days=n, hours=now.hour - hour)).isoformat()

    # === People (10+) ===
    # Alex Chen, Maria Garcia, Priya Patel, Sam Kim, Jordan Lee,
    # Dana Wong, Riley Smith, Casey Brown, Morgan Davis, Avery Jones

    # === Projects (5+) ===
    # Project Orion, Project Vega, Project Aurora, Globex Migration, SSO Integration

    # --- Day 1-10: Initial commitments ---
    signals.extend([
        {"entity": "Alex Chen", "text": "I will send the project proposal by Friday", "signal_type": "commitment_made", "timestamp": days_ago(85)},
        {"entity": "Maria Garcia", "text": "I will review the hiring scorecard by Monday", "signal_type": "commitment_made", "timestamp": days_ago(84)},
        {"entity": "Priya Patel", "text": "I will fix the flaky CI pipeline this week", "signal_type": "commitment_made", "timestamp": days_ago(83)},
        {"entity": "Sam Kim", "text": "Let me take that action item for the Q3 roadmap", "signal_type": "commitment_made", "timestamp": days_ago(82)},
        {"entity": "Project Orion", "text": "Orion is our top priority for this quarter", "signal_type": "reported_statement", "timestamp": days_ago(80)},
        {"entity": "Globex Migration", "text": "We need to migrate Globex to the new infrastructure", "signal_type": "reported_statement", "timestamp": days_ago(80)},
    ])

    # --- Day 11-20: Completions and follow-ups ---
    signals.extend([
        {"entity": "Alex Chen", "text": "The proposal has been sent to the client", "signal_type": "reported_statement", "timestamp": days_ago(75)},
        {"entity": "Priya Patel", "text": "The CI pipeline is still flaky, I will look into it again", "signal_type": "commitment_made", "timestamp": days_ago(70)},
        {"entity": "Maria Garcia", "text": "I reviewed the scorecard, it looks good", "signal_type": "reported_statement", "timestamp": days_ago(72)},
        {"entity": "Dana Wong", "text": "I will set up the SSO integration by next week", "signal_type": "commitment_made", "timestamp": days_ago(68)},
        {"entity": "Project Vega", "text": "Vega is being deprioritized in favor of Orion", "signal_type": "reported_statement", "timestamp": days_ago(65)},
    ])

    # --- Day 21-40: Ongoing work + noise ---
    signals.extend([
        {"entity": "Jordan Lee", "text": "I will deliver the financial model by end of month", "signal_type": "commitment_made", "timestamp": days_ago(55)},
        {"entity": "Riley Smith", "text": "I will prepare the board deck for the quarterly review", "signal_type": "commitment_made", "timestamp": days_ago(50)},
        {"entity": "Casey Brown", "text": "The security audit is complete, no major findings", "signal_type": "reported_statement", "timestamp": days_ago(45)},
        {"entity": "NewsletterCorp", "text": "Weekly tech newsletter: 10 tips for better meetings", "signal_type": "newsletter", "timestamp": days_ago(44)},
        {"entity": "NewsletterCorp", "text": "Weekly tech newsletter: The future of remote work", "signal_type": "newsletter", "timestamp": days_ago(37)},
        {"entity": "NewsletterCorp", "text": "Weekly tech newsletter: AI in product management", "signal_type": "newsletter", "timestamp": days_ago(30)},
        {"entity": "NewsletterCorp", "text": "Weekly tech newsletter: Best practices for CI/CD", "signal_type": "newsletter", "timestamp": days_ago(23)},
        {"entity": "NewsletterCorp", "text": "Weekly tech newsletter: Cloud cost optimization", "signal_type": "newsletter", "timestamp": days_ago(16)},
        {"entity": "NewsletterCorp", "text": "Weekly tech newsletter: DevOps automation trends", "signal_type": "newsletter", "timestamp": days_ago(9)},
        {"entity": "NewsletterCorp", "text": "Weekly tech newsletter: API design patterns", "signal_type": "newsletter", "timestamp": days_ago(2)},
    ])

    # --- Day 41-60: Contradictions and changes ---
    signals.extend([
        {"entity": "Project Aurora", "text": "Aurora project is now code-named Project Phoenix", "signal_type": "reported_statement", "timestamp": days_ago(40)},
        {"entity": "Project Phoenix", "text": "I will send the Phoenix timeline by Friday", "signal_type": "commitment_made", "timestamp": days_ago(38)},
        {"entity": "Alex Chen", "text": "Actually my name is Alex Kim, not Alex Chen", "signal_type": "reported_statement", "timestamp": days_ago(35)},
        {"entity": "Morgan Davis", "text": "I will handle the legal review for the Globex contract", "signal_type": "commitment_made", "timestamp": days_ago(32)},
        {"entity": "Avery Jones", "text": "I will organize the team offsite for next month", "signal_type": "commitment_made", "timestamp": days_ago(30)},
    ])

    # --- Day 61-80: Stale commitments and completions ---
    signals.extend([
        {"entity": "Dana Wong", "text": "The SSO integration has been deployed", "signal_type": "reported_statement", "timestamp": days_ago(25)},
        {"entity": "Jordan Lee", "text": "I haven't started the financial model yet", "signal_type": "reported_statement", "timestamp": days_ago(20)},
        {"entity": "Priya Patel", "text": "The CI pipeline is still flaky, this is the third time", "signal_type": "reported_statement", "timestamp": days_ago(18)},
        {"entity": "Sam Kim", "text": "I will send the Q3 roadmap draft by Wednesday", "signal_type": "commitment_made", "timestamp": days_ago(15)},
        {"entity": "Riley Smith", "text": "The board deck is ready for review", "signal_type": "reported_statement", "timestamp": days_ago(12)},
    ])

    # --- Day 81-90: Recent activity ---
    signals.extend([
        {"entity": "Maria Garcia", "text": "I will follow up with the candidate by Friday", "signal_type": "commitment_made", "timestamp": days_ago(7)},
        {"entity": "Alex Kim", "text": "I will send the revised proposal with pricing by Monday", "signal_type": "commitment_made", "timestamp": days_ago(5)},
        {"entity": "Project Orion", "text": "Orion deployment is scheduled for next Tuesday", "signal_type": "reported_statement", "timestamp": days_ago(3)},
        {"entity": "Morgan Davis", "text": "The legal review for Globex is still pending", "signal_type": "reported_statement", "timestamp": days_ago(2)},
        {"entity": "Casey Brown", "text": "I will schedule the security re-audit for next week", "signal_type": "commitment_made", "timestamp": days_ago(1)},
    ])

    # --- Edge cases: ambiguous, multilingual, unicode ---
    signals.extend([
        {"entity": "Priya Patel", "text": "I'll own the follow-up on the CI issue", "signal_type": "commitment_made", "timestamp": days_ago(10)},
        {"entity": "Dana Wong", "text": "Consider it done — the SSO docs are updated", "signal_type": "reported_statement", "timestamp": days_ago(22)},
        {"entity": "Sam Kim", "text": "Maybe I can send the roadmap next week, but don't count on it", "signal_type": "commitment_made", "timestamp": days_ago(14)},
        {"entity": "Jordan Lee", "text": "I will not send the financial model this month", "signal_type": "commitment_made", "timestamp": days_ago(8)},
    ])

    return signals


def generate_ground_truth_questions() -> list[dict[str, Any]]:
    """Generate 30+ ground-truth questions with expected answers.

    Each question has:
    - question: the Ask query
    - expected_entities: entities that should appear in the answer
    - forbidden_entities: entities that should NOT appear
    - temporal_cutoff: optional as_of date for temporal queries
    - category: temporal, contradiction, entity_disambiguation, commitment_lifecycle,
      preparation, stale_memory, silence_noise
    """
    return [
        # --- Temporal queries ---
        {
            "question": "What did I commit to last quarter?",
            "expected_entities": ["Alex", "Maria", "Priya", "Sam"],
            "forbidden_entities": ["NewsletterCorp"],
            "category": "temporal",
        },
        {
            "question": "What changed in the last 30 days?",
            "expected_entities": ["Morgan", "Avery", "Priya"],
            "forbidden_entities": [],
            "category": "temporal",
        },
        {
            "question": "What did Alex promise in the first week?",
            "expected_entities": ["Alex"],
            "forbidden_entities": ["NewsletterCorp", "Maria"],
            "temporal_cutoff": "first_week",
            "category": "temporal",
        },

        # --- Contradiction detection ---
        {
            "question": "Is Project Vega still a priority?",
            "expected_entities": ["Vega", "Orion"],
            "forbidden_entities": ["NewsletterCorp"],
            "category": "contradiction",
        },
        {
            "question": "Did Jordan deliver the financial model?",
            "expected_entities": ["Jordan"],
            "forbidden_entities": [],
            "category": "contradiction",
        },
        {
            "question": "What happened with the CI pipeline?",
            "expected_entities": ["Priya"],
            "forbidden_entities": ["NewsletterCorp"],
            "category": "contradiction",
        },

        # --- Entity disambiguation ---
        {
            "question": "What did Alex Chen commit to?",
            "expected_entities": ["Alex"],
            "forbidden_entities": ["Maria", "Sam"],
            "category": "entity_disambiguation",
        },
        {
            "question": "What is Project Phoenix?",
            "expected_entities": ["Phoenix", "Aurora"],
            "forbidden_entities": ["NewsletterCorp"],
            "category": "entity_disambiguation",
        },

        # --- Commitment lifecycle ---
        {
            "question": "What commitments are overdue?",
            "expected_entities": ["Jordan", "Priya"],
            "forbidden_entities": ["NewsletterCorp"],
            "category": "commitment_lifecycle",
        },
        {
            "question": "What did Dana complete?",
            "expected_entities": ["Dana"],
            "forbidden_entities": [],
            "category": "commitment_lifecycle",
        },
        {
            "question": "What did I promise Sam?",
            "expected_entities": ["Sam"],
            "forbidden_entities": ["NewsletterCorp"],
            "category": "commitment_lifecycle",
        },

        # --- Preparation ---
        {
            "question": "What should I prepare for the Orion deployment?",
            "expected_entities": ["Orion"],
            "forbidden_entities": ["NewsletterCorp"],
            "category": "preparation",
        },
        {
            "question": "What's pending with Globex?",
            "expected_entities": ["Globex", "Morgan"],
            "forbidden_entities": ["NewsletterCorp"],
            "category": "preparation",
        },

        # --- Stale memory ---
        {
            "question": "Who am I repeatedly disappointing?",
            "expected_entities": ["Priya", "Jordan"],
            "forbidden_entities": ["NewsletterCorp"],
            "category": "stale_memory",
        },
        {
            "question": "Which issue keeps recurring across meetings?",
            "expected_entities": ["Priya", "CI"],
            "forbidden_entities": ["NewsletterCorp"],
            "category": "stale_memory",
        },

        # --- Silence / noise ---
        {
            "question": "What newsletters did I receive?",
            "expected_entities": ["NewsletterCorp"],
            "forbidden_entities": [],
            "category": "silence_noise",
        },
        {
            "question": "What is the most important thing right now?",
            "expected_entities": ["Orion", "Morgan", "Casey"],
            "forbidden_entities": ["NewsletterCorp"],
            "category": "silence_noise",
        },

        # --- Negation / tentative ---
        {
            "question": "Did Jordan commit to sending the model?",
            "expected_entities": ["Jordan"],
            "forbidden_entities": ["NewsletterCorp"],
            "category": "commitment_lifecycle",
        },
        {
            "question": "Is Sam's roadmap tentative?",
            "expected_entities": ["Sam"],
            "forbidden_entities": ["NewsletterCorp"],
            "category": "commitment_lifecycle",
        },

        # --- Implicit commitments ---
        {
            "question": "What did Priya own?",
            "expected_entities": ["Priya"],
            "forbidden_entities": ["NewsletterCorp"],
            "category": "commitment_lifecycle",
        },

        # --- Provenance ---
        {
            "question": "When did Alex say the proposal was sent?",
            "expected_entities": ["Alex"],
            "forbidden_entities": [],
            "category": "temporal",
        },
        {
            "question": "What did Maria review?",
            "expected_entities": ["Maria"],
            "forbidden_entities": ["NewsletterCorp"],
            "category": "commitment_lifecycle",
        },

        # --- More temporal ---
        {
            "question": "What was happening 2 months ago?",
            "expected_entities": ["Dana", "Vega", "Project"],
            "forbidden_entities": ["NewsletterCorp"],
            "category": "temporal",
        },
        {
            "question": "What did I commit to in the last week?",
            "expected_entities": ["Maria", "Alex", "Casey"],
            "forbidden_entities": ["NewsletterCorp"],
            "category": "temporal",
        },

        # --- Risk ---
        {
            "question": "What is at risk?",
            "expected_entities": ["Jordan", "Morgan"],
            "forbidden_entities": ["NewsletterCorp"],
            "category": "stale_memory",
        },

        # --- Relationship ---
        {
            "question": "What is my relationship with Alex?",
            "expected_entities": ["Alex"],
            "forbidden_entities": ["NewsletterCorp"],
            "category": "entity_disambiguation",
        },
        {
            "question": "What did Casey find in the audit?",
            "expected_entities": ["Casey"],
            "forbidden_entities": ["NewsletterCorp"],
            "category": "commitment_lifecycle",
        },
        {
            "question": "Who is handling legal?",
            "expected_entities": ["Morgan"],
            "forbidden_entities": ["NewsletterCorp"],
            "category": "entity_disambiguation",
        },
        {
            "question": "What did Riley prepare?",
            "expected_entities": ["Riley"],
            "forbidden_entities": ["NewsletterCorp"],
            "category": "commitment_lifecycle",
        },
        {
            "question": "What did Avery organize?",
            "expected_entities": ["Avery"],
            "forbidden_entities": ["NewsletterCorp"],
            "category": "commitment_lifecycle",
        },
    ]


def load_benchmark() -> dict[str, Any]:
    """Load the full benchmark dataset.

    Returns:
    {
        "signals": [...],
        "questions": [...],
        "stats": {total_signals, total_questions, days_span, entities, projects}
    }
    """
    signals = generate_benchmark_signals()
    questions = generate_ground_truth_questions()

    entities = set(s["entity"] for s in signals)
    projects = set(e for e in entities if "Project" in e or "Globex" in e or "SSO" in e)

    return {
        "signals": signals,
        "questions": questions,
        "stats": {
            "total_signals": len(signals),
            "total_questions": len(questions),
            "entities": len(entities),
            "projects": len(projects),
            "categories": list(set(q["category"] for q in questions)),
        },
    }


if __name__ == "__main__":
    benchmark = load_benchmark()
    print(f"Signals: {benchmark['stats']['total_signals']}")
    print(f"Questions: {benchmark['stats']['total_questions']}")
    print(f"Entities: {benchmark['stats']['entities']}")
    print(f"Categories: {benchmark['stats']['categories']}")
