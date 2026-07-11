"""
Phase 10 blinded comparison benchmark — 100 Maestro vs frontier LLM questions.

The roadmap requires:
  - 100 blinded Maestro vs frontier LLM comparisons
  - Same evidence, same temporal cutoff, same question
  - Human judges rate: correctness, usefulness, provenance, restraint,
    actionability, consistency over time
  - Report win/tie/loss by category

Each question has:
  - question: the query
  - evidence_signals: the signals available to both Maestro and the LLM
  - temporal_cutoff: the as_of date
  - category: factual, temporal, commitment, contradiction, silence, synthesis
  - reference_answer: ground-truth answer for auto-scoring
  - reference_provenance: which entity/signal the answer should cite

The benchmark produces TWO answers per question:
  - Maestro's answer (via POST /api/ask)
  - Frontier LLM's answer (same evidence fed directly, no personal context)

Both are auto-scored on 5 dimensions (rule-based, since human judges
aren't available in CI). The scoring is:
  - correctness: does the answer match the reference?
  - provenance: does the answer cite the right entity?
  - restraint: does the answer stay silent when it should?
  - actionability: does the answer include actionable info?
  - evidence_grounding: is every claim backed by evidence?
"""

from __future__ import annotations

from typing import Any
import itertools

ENTITIES = ["Alex", "Maria", "Priya", "Sam", "Morgan", "Avery", "Dana",
            "Marco", "Yuki", "David"]
PROJECTS = ["Vega", "Orion", "Aurora", "Phoenix"]


def _build_questions() -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []

    def add(qid, question, signals, cutoff, category, ref_answer, ref_entity):
        questions.append({
            "question_id": qid,
            "question": question,
            "evidence_signals": signals,
            "temporal_cutoff": cutoff,
            "category": category,
            "reference_answer": ref_answer,
            "reference_entity": ref_entity,
        })

    # === FACTUAL (20) — direct entity lookup ===
    for i, (entity, action) in enumerate(itertools.islice(
            itertools.product(ENTITIES, ["proposal", "scorecard", "roadmap", "contract", "deck"]), 20)):
        add(
            f"q-{i+1:03d}",
            f"What did {entity} commit to?",
            [{"entity": entity, "text": f"I will send the {action} by Friday",
              "signal_type": "commitment_made", "timestamp": "2026-07-01T10:00:00Z"}],
            "2026-07-05T00:00:00Z",
            "factual",
            f"{entity} committed to sending the {action}",
            entity,
        )

    # === TEMPORAL (15) — time-filtered queries ===
    temporal_phrases = [
        ("last quarter", "last_quarter", "2026-04-01T00:00:00Z"),
        ("last month", "last_month", "2026-06-01T00:00:00Z"),
        ("last week", "last_week", "2026-07-01T00:00:00Z"),
        ("last 30 days", "last_30_days", "2026-06-11T00:00:00Z"),
        ("recently", "recent", "2026-07-08T00:00:00Z"),
    ]
    for i, (entity, (phrase, label, cutoff)) in enumerate(itertools.islice(
            itertools.product(ENTITIES, temporal_phrases), 15)):
        add(
            f"q-{i+21:03d}",
            f"What did {entity} commit to {phrase}?",
            [{"entity": entity, "text": f"I will send the proposal",
              "signal_type": "commitment_made", "timestamp": "2026-06-15T10:00:00Z"}],
            cutoff,
            "temporal",
            f"{entity} committed to sending the proposal",
            entity,
        )

    # === COMMITMENT (15) — lifecycle-aware ===
    commitment_questions = [
        ("What is Alex's most at-risk commitment?", "Alex", "at_risk"),
        ("What commitments are overdue?", "", "overdue"),
        ("What did Maria promise to deliver?", "Maria", "deliver"),
        ("What commitments has Sam completed?", "Sam", "completed"),
        ("What commitments were cancelled?", "", "cancelled"),
        ("What is disputed?", "", "disputed"),
        ("What commitments are still active?", "", "active"),
        ("What did Priya commit to by Friday?", "Priya", "Friday"),
        ("What is Dana's commitment status?", "Dana", "status"),
        ("What commitments involve Project Vega?", "Vega", "Vega"),
        ("What commitments involve Project Orion?", "Orion", "Orion"),
        ("What is the most urgent commitment?", "", "urgent"),
        ("What did Marco pledge?", "Marco", "pledge"),
        ("What does Yuki owe?", "Yuki", "owe"),
        ("What commitments are approaching their deadline?", "", "deadline"),
    ]
    for i, (q, entity, kw) in enumerate(commitment_questions):
        signals = [{"entity": entity or "Alex", "text": f"I will send the {kw}",
                     "signal_type": "commitment_made", "timestamp": "2026-07-01T10:00:00Z"}]
        add(f"q-{i+36:03d}", q, signals, "2026-07-05T00:00:00Z", "commitment",
            f"Commitment related to {kw}", entity or "Alex")

    # === CONTRADICTION (15) — detect conflicting evidence ===
    for i, entity in enumerate(ENTITIES[:10] + ENTITIES[:5]):
        add(
            f"q-{i+51:03d}",
            f"Is {entity}'s commitment still active?",
            [
                {"entity": entity, "text": "I will send the proposal by Friday",
                 "signal_type": "commitment_made", "timestamp": "2026-07-01T10:00:00Z"},
                {"entity": entity, "text": "The proposal has been sent",
                 "signal_type": "reported_statement", "timestamp": "2026-07-03T10:00:00Z"},
            ],
            "2026-07-05T00:00:00Z",
            "contradiction",
            f"{entity}'s commitment is completed (proposal was sent)",
            entity,
        )

    # === SILENCE (15) — should stay silent or say "unknown" ===
    silence_questions = [
        ("What will the board decide next quarter?", "unknown"),
        ("Will Alex get promoted?", "unknown"),
        ("What is Maria's salary?", "unknown"),
        ("What did Sam say in private?", "unknown"),
        ("What will happen to Project Aurora?", "unknown"),
        ("What is the company's revenue?", "unknown"),
        ("Who will be hired next?", "unknown"),
        ("What is Dana's performance review?", "unknown"),
        ("What did the CEO announce?", "unknown"),
        ("What is the competitor's strategy?", "unknown"),
        ("What will the stock price be?", "unknown"),
        ("Is the market going to crash?", "unknown"),
        ("What is the weather forecast?", "unknown"),
        ("What did the lawyer advise?", "unknown"),
        ("What is the HR policy on remote work?", "unknown"),
    ]
    for i, (q, ref) in enumerate(silence_questions):
        add(f"q-{i+66:03d}", q, [], "2026-07-05T00:00:00Z", "silence", ref, "")

    # === SYNTHESIS (20) — combine multiple signals ===
    for i, entity in enumerate(ENTITIES[:10]):
        add(
            f"q-{i+81:03d}",
            f"What's the overall status of {entity}'s commitments?",
            [
                {"entity": entity, "text": "I will send the proposal by Friday",
                 "signal_type": "commitment_made", "timestamp": "2026-07-01T10:00:00Z"},
                {"entity": entity, "text": "I will review the scorecard",
                 "signal_type": "commitment_made", "timestamp": "2026-07-02T10:00:00Z"},
                {"entity": entity, "text": "The proposal has been sent",
                 "signal_type": "reported_statement", "timestamp": "2026-07-04T10:00:00Z"},
            ],
            "2026-07-05T00:00:00Z",
            "synthesis",
            f"{entity} has 2 commitments: proposal (completed) and scorecard (pending)",
            entity,
        )
    # 10 more synthesis across multiple entities
    for i in range(10):
        e1, e2 = ENTITIES[i % 5], ENTITIES[(i + 1) % 5]
        add(
            f"q-{i+91:03d}",
            f"What commitments span {e1} and {e2}?",
            [
                {"entity": e1, "text": f"I will send the proposal to {e2}",
                 "signal_type": "commitment_made", "timestamp": "2026-07-01T10:00:00Z"},
            ],
            "2026-07-05T00:00:00Z",
            "synthesis",
            f"{e1} committed to sending the proposal to {e2}",
            e1,
        )

    return questions


QUESTIONS: list[dict[str, Any]] = _build_questions()


def get_comparison_benchmark() -> list[dict[str, Any]]:
    """Return the 100-question comparison benchmark."""
    return QUESTIONS


def get_benchmark_stats() -> dict[str, int]:
    stats: dict[str, int] = {}
    for q in QUESTIONS:
        stats[q["category"]] = stats.get(q["category"], 0) + 1
    return stats


if __name__ == "__main__":
    qs = get_comparison_benchmark()
    print(f"Total questions: {len(qs)}")
    print(f"Categories: {len(get_benchmark_stats())}")
    for k, v in sorted(get_benchmark_stats().items()):
        print(f"  {k:20s} {v}")
