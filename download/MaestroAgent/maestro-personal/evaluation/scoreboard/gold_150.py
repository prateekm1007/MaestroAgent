"""
Gold-150 evaluation dataset for Maestro AI quality.

150 questions across 5 types (30 each):
  - commitment: "What did I promise X?" — tests commitment extraction + retrieval
  - contradiction: "Did I contradict myself about X?" — tests contradiction detection
  - temporal: "When was the last time I heard from X?" — tests temporal reasoning
  - abstention: questions Maestro should NOT answer (no evidence) — tests trusted silence
  - multilingual: questions in mixed English/other — tests robustness

Each question has:
  - id: unique identifier
  - type: question category
  - query: the question text
  - expected_keywords: keywords that MUST appear in a correct answer
  - forbidden_keywords: keywords that MUST NOT appear (hallucination check)
  - should_abstain: if True, Maestro should say "I don't have enough evidence"
  - seed_signals: signals to seed before asking (the evidence Maestro should retrieve)
"""

GOLD_150: list[dict] = []


def _add(qid, qtype, query, expected=None, forbidden=None, abstain=False, signals=None):
    GOLD_150.append({
        "id": qid,
        "type": qtype,
        "query": query,
        "expected_keywords": expected or [],
        "forbidden_keywords": forbidden or [],
        "should_abstain": abstain,
        "seed_signals": signals or [],
    })


# ═══ COMMITMENT QUESTIONS (30) ═══
# Tests: "What did I promise X?" — must retrieve the exact commitment text

for i in range(1, 16):
    _add(
        f"commit-{i:03d}",
        "commitment",
        f"What did I promise Person{i}?",
        expected=["promise", f"Person{i}"],
        signals=[{
            "entity": f"Person{i}",
            "text": f"I will send Person{i} the deliverable by Friday",
            "signal_type": "commitment_made",
            "timestamp": "2026-07-10T10:00:00Z",
        }],
    )

for i in range(16, 31):
    _add(
        f"commit-{i:03d}",
        "commitment",
        f"What commitment did I make to Entity{i}?",
        expected=["commitment", f"Entity{i}"],
        signals=[{
            "entity": f"Entity{i}",
            "text": f"I committed to delivering the report to Entity{i} by next week",
            "signal_type": "commitment_made",
            "timestamp": "2026-07-09T14:00:00Z",
        }],
    )


# ═══ CONTRADICTION QUESTIONS (30) ═══
# Tests: "Did I contradict myself about X?" — must detect conflicting signals

for i in range(1, 16):
    _add(
        f"contradict-{i:03d}",
        "contradiction",
        f"Did I contradict myself about Topic{i}?",
        expected=["contradict", f"Topic{i}"],
        signals=[
            {
                "entity": f"Topic{i}",
                "text": f"I promised Topic{i} would be done by Monday",
                "signal_type": "commitment_made",
                "timestamp": "2026-07-08T10:00:00Z",
            },
            {
                "entity": f"Topic{i}",
                "text": f"Topic{i} has been cancelled",
                "signal_type": "observed_fact",
                "timestamp": "2026-07-10T15:00:00Z",
            },
        ],
    )

for i in range(16, 31):
    _add(
        f"contradict-{i:03d}",
        "contradiction",
        f"Is there a conflict regarding Project{i}?",
        expected=["conflict", f"Project{i}"],
        signals=[
            {
                "entity": f"Project{i}",
                "text": f"Project{i} budget is $50k",
                "signal_type": "reported_statement",
                "timestamp": "2026-07-07T09:00:00Z",
            },
            {
                "entity": f"Project{i}",
                "text": f"Project{i} budget was increased to $80k",
                "signal_type": "reported_statement",
                "timestamp": "2026-07-09T11:00:00Z",
            },
        ],
    )


# ═══ TEMPORAL QUESTIONS (30) ═══
# Tests: "When was the last time I heard from X?" — must use timestamps

for i in range(1, 16):
    _add(
        f"temporal-{i:03d}",
        "temporal",
        f"When was the last time I heard from Contact{i}?",
        expected=[f"Contact{i}", "2026-07"],
        signals=[
            {
                "entity": f"Contact{i}",
                "text": f"Contact{i} sent an email about the proposal",
                "signal_type": "reported_statement",
                "timestamp": "2026-07-05T10:00:00Z",
            },
            {
                "entity": f"Contact{i}",
                "text": f"Contact{i} followed up about the contract",
                "signal_type": "follow_up_required",
                "timestamp": "2026-07-10T14:00:00Z",
            },
        ],
    )

for i in range(16, 31):
    _add(
        f"temporal-{i:03d}",
        "temporal",
        f"What's the latest update on Deal{i}?",
        expected=[f"Deal{i}", "2026"],
        signals=[
            {
                "entity": f"Deal{i}",
                "text": f"Deal{i} is in initial discussions",
                "signal_type": "reported_statement",
                "timestamp": "2026-06-15T09:00:00Z",
            },
            {
                "entity": f"Deal{i}",
                "text": f"Deal{i} moved to negotiation phase",
                "signal_type": "observed_fact",
                "timestamp": "2026-07-08T16:00:00Z",
            },
        ],
    )


# ═══ ABSTENTION QUESTIONS (30) ═══
# Tests: questions Maestro should NOT answer (no evidence) — trusted silence

for i in range(1, 16):
    _add(
        f"abstain-{i:03d}",
        "abstention",
        f"What did I promise Nonexistent{i}?",
        abstain=True,  # No seed signals → Maestro should say "insufficient evidence"
    )

for i in range(16, 31):
    _add(
        f"abstain-{i:03d}",
        "abstention",
        f"Tell me about Unknown{i}'s commitments",
        abstain=True,
    )


# ═══ MULTILINGUAL / EDGE CASES (30) ═══
# Tests: mixed language, ambiguous pronouns, negation, conditional

for i in range(1, 11):
    _add(
        f"multi-{i:03d}",
        "multilingual",
        f"What did I say about Client{i}?",
        expected=[f"Client{i}"],
        signals=[{
            "entity": f"Client{i}",
            "text": f"Client{i} requested a demo next week",
            "signal_type": "reported_statement",
            "timestamp": "2026-07-11T10:00:00Z",
        }],
    )

for i in range(11, 21):
    _add(
        f"multi-{i:03d}",
        "multilingual",
        f"Did I NOT promise anything to Party{i}?",  # Negation — should handle
        expected=[f"Party{i}"],
        signals=[{
            "entity": f"Party{i}",
            "text": f"No commitment was made to Party{i}",
            "signal_type": "reported_statement",
            "timestamp": "2026-07-10T12:00:00Z",
        }],
    )

for i in range(21, 31):
    _add(
        f"multi-{i:03d}",
        "multilingual",
        f"If I committed to Group{i}, what was it?",  # Conditional
        expected=[f"Group{i}"],
        signals=[{
            "entity": f"Group{i}",
            "text": f"I will send Group{i} the proposal by end of month",
            "signal_type": "commitment_made",
            "timestamp": "2026-07-09T15:00:00Z",
        }],
    )


# Verify we have 150
assert len(GOLD_150) == 150, f"Expected 150 questions, got {len(GOLD_150)}"

# Type distribution
_type_counts = {}
for q in GOLD_150:
    _type_counts[q["type"]] = _type_counts.get(q["type"], 0) + 1
