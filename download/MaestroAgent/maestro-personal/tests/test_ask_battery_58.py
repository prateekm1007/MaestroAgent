"""Phase 3.3: 58-question Ask battery — measures accuracy by type.

The v13 auditor found: "58-question battery → ≥90% correct, 0 generic
fallbacks, 100% abstention accuracy."

This test runs against the production API (or local) and measures:
- Overall accuracy (target: ≥90%)
- Abstention accuracy (target: 100%)
- Zero generic fallbacks
- Per-type breakdown

Usage:
  MAESTRO_URL=https://maestroagent-production.up.railway.app \
  MAESTRO_TOKEN=<token> \
  pytest tests/test_ask_battery_58.py -v --tb=short

  # Or run directly:
  MAESTRO_URL=... MAESTRO_TOKEN=... python tests/test_ask_battery_58.py
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

import pytest
import requests

BASE = os.environ.get("MAESTRO_URL", "")
TOKEN = os.environ.get("MAESTRO_TOKEN", "")
H = {"Authorization": f"Bearer {TOKEN}"}


def _skip_if_no_endpoint():
    if not BASE or not TOKEN:
        pytest.skip("MAESTRO_URL/MAESTRO_TOKEN not set")


# ──────────────────────────────────────────────────────────────────────
# 58-QUESTION BATTERY
# Each question has: type, query, expected_behavior
# expected_behavior: "answer" (should return a real answer),
#                    "abstain" (should return "I don't have any records")
# ──────────────────────────────────────────────────────────────────────

BATTERY: list[dict[str, str]] = [
    # Direct lookup (10) — should answer
    {"type": "direct_lookup", "query": "What did I promise Alex?", "expected": "answer"},
    {"type": "direct_lookup", "query": "What did Maria ask for?", "expected": "answer"},
    {"type": "direct_lookup", "query": "What did I send Sam?", "expected": "answer"},
    {"type": "direct_lookup", "query": "What's the status of Project Atlas?", "expected": "answer"},
    {"type": "direct_lookup", "query": "What did Barack Obama promise?", "expected": "abstain"},
    {"type": "direct_lookup", "query": "What's new with Sarah Chen?", "expected": "answer"},
    {"type": "direct_lookup", "query": "What is Project Apollo about?", "expected": "answer"},
    {"type": "direct_lookup", "query": "Tell me about Acme Corp", "expected": "answer"},
    {"type": "direct_lookup", "query": "What did I promise Alex Chen?", "expected": "answer"},
    {"type": "direct_lookup", "query": "What did Maria promise?", "expected": "answer"},

    # Abstention (8) — unknown entities, should abstain
    {"type": "abstention", "query": "What did I promise Elon Musk?", "expected": "abstain"},
    {"type": "abstention", "query": "What did I promise Zzzznonexistent?", "expected": "abstain"},
    {"type": "abstention", "query": "What's the status of Nonexistent Project?", "expected": "abstain"},
    {"type": "abstention", "query": "What did John Doe promise?", "expected": "abstain"},
    {"type": "abstention", "query": "Tell me about Qqqq Nobody", "expected": "abstain"},
    {"type": "abstention", "query": "What's new with Fake Person?", "expected": "abstain"},
    {"type": "abstention", "query": "What did I promise Xyzabc?", "expected": "abstain"},
    {"type": "abstention", "query": "What's the status of Imaginary Entity?", "expected": "abstain"},

    # Temporal (6) — should diff, not list
    {"type": "temporal", "query": "What changed since Monday?", "expected": "answer"},
    {"type": "temporal", "query": "What changed since yesterday?", "expected": "answer"},
    {"type": "temporal", "query": "What's new since 3 days ago?", "expected": "answer"},
    {"type": "temporal", "query": "Updates since last week?", "expected": "answer"},
    {"type": "temporal", "query": "Anything new since this morning?", "expected": "answer"},
    {"type": "temporal", "query": "What happened since Tuesday?", "expected": "answer"},

    # Conflict/multi-hop (5) — should detect conflicts
    {"type": "conflict", "query": "Which commitments conflict?", "expected": "answer"},
    {"type": "conflict", "query": "Are there any clashes next week?", "expected": "answer"},
    {"type": "conflict", "query": "Do any deadlines overlap?", "expected": "answer"},
    {"type": "conflict", "query": "What contradictions exist for ContradictCorp?", "expected": "answer"},
    {"type": "conflict", "query": "Any competing commitments?", "expected": "answer"},

    # Relational (5) — involving queries
    {"type": "relational", "query": "History with Sam", "expected": "answer"},
    {"type": "relational", "query": "Everything about Nora", "expected": "answer"},
    {"type": "relational", "query": "Dealings with Alex", "expected": "answer"},
    {"type": "relational", "query": "What's happening with Maria?", "expected": "answer"},
    {"type": "relational", "query": "What's going on with Sam?", "expected": "answer"},

    # State queries (6) — aggregate counts
    {"type": "state_query", "query": "How many commitments are active?", "expected": "answer"},
    {"type": "state_query", "query": "What's cancelled?", "expected": "answer"},
    {"type": "state_query", "query": "How many promises do I have?", "expected": "answer"},
    {"type": "state_query", "query": "What's the status?", "expected": "answer"},
    {"type": "state_query", "query": "Any overdue commitments?", "expected": "answer"},
    {"type": "state_query", "query": "What's pending?", "expected": "answer"},

    # My commitments (5) — first-person
    {"type": "my_commitments", "query": "What did I promise to Alex?", "expected": "answer"},
    {"type": "my_commitments", "query": "What do I owe Nora?", "expected": "answer"},
    {"type": "my_commitments", "query": "My commitments to Sam", "expected": "answer"},
    {"type": "my_commitments", "query": "What have I committed to?", "expected": "answer"},
    {"type": "my_commitments", "query": "What did I commit to Maria?", "expected": "answer"},

    # Their commitments (4) — third-party
    {"type": "their_commitments", "query": "What are Jamie's commitments?", "expected": "answer"},
    {"type": "their_commitments", "query": "Did Alex promise anything?", "expected": "answer"},
    {"type": "their_commitments", "query": "What has Maria committed to?", "expected": "answer"},
    {"type": "their_commitments", "query": "Promises from Sam", "expected": "answer"},

    # Noise/resistance (5) — should not fabricate
    {"type": "noise", "query": "What is the weather?", "expected": "abstain"},
    {"type": "noise", "query": "Tell me a joke", "expected": "abstain"},
    {"type": "noise", "query": "What time is it?", "expected": "abstain"},
    {"type": "noise", "query": "Who won the game?", "expected": "abstain"},
    {"type": "noise", "query": "What's the stock market doing?", "expected": "abstain"},

    # Multilingual (4) — should handle non-English
    {"type": "multilingual", "query": "Que le prometí a Alex?", "expected": "answer"},
    {"type": "multilingual", "query": "Was hat Maria versprochen?", "expected": "answer"},
    {"type": "multilingual", "query": "Alexに何を約束した？", "expected": "answer"},
    {"type": "multilingual", "query": "Que promises Sam?", "expected": "answer"},
]


def _ask(query: str) -> dict[str, Any]:
    """Send a query to the Ask endpoint and return the response."""
    r = requests.post(
        f"{BASE}/api/ask",
        headers=H,
        json={"query": query},
        timeout=60,
    )
    assert r.status_code == 200, f"Ask failed: {r.status_code} {r.text[:200]}"
    return r.json()


def _is_abstention(answer: str) -> bool:
    """Check if the answer is an abstention response."""
    a = answer.lower()
    return any(p in a for p in [
        "i don't have any records",
        "i don't have any matching records",
        "no signals found",
        "no matching",
        "i don't have enough",
        "i don't have enough information",
        "no record of",
        "no evidence found",
        "not enough information",
        "i don't have any",
        "no commitments found",
        "no commitments in",
    ])


def _is_generic_fallback(answer: str) -> bool:
    """Check if the answer is a generic fallback (non-committal)."""
    a = answer.lower().strip()
    if len(a) < 20:
        return True
    generic_phrases = [
        "i'm not sure",
        "i can't help with that",
        "please try again",
        "an error occurred",
        "something went wrong",
    ]
    return any(p in a for p in generic_phrases)


def _evaluate(question: dict) -> dict:
    """Evaluate a single question and return the result."""
    query = question["query"]
    expected = question["expected"]
    qtype = question["type"]

    try:
        resp = _ask(query)
        answer = resp.get("answer", "")
        confidence = resp.get("confidence", 0)
        evidence_count = len(resp.get("evidence_refs", []))

        is_abstention = _is_abstention(answer)
        is_generic = _is_generic_fallback(answer)

        if expected == "abstain":
            # Correct if the answer IS an abstention
            correct = is_abstention
        else:
            # Correct if the answer is NOT an abstention AND NOT generic
            correct = not is_abstention and not is_generic

        return {
            "type": qtype,
            "query": query[:60],
            "expected": expected,
            "correct": correct,
            "is_abstention": is_abstention,
            "is_generic": is_generic,
            "confidence": confidence,
            "evidence_count": evidence_count,
            "answer_preview": answer[:100],
        }
    except Exception as e:
        return {
            "type": qtype,
            "query": query[:60],
            "expected": expected,
            "correct": False,
            "error": str(e)[:100],
        }


def test_battery_58_questions():
    """Run the full 58-question battery and check accuracy."""
    _skip_if_no_endpoint()

    assert len(BATTERY) >= 58, (
        f"Battery has {len(BATTERY)} questions, expected at least 58"
    )

    results = []
    for q in BATTERY:
        result = _evaluate(q)
        results.append(result)
        # Brief pause to avoid rate limiting
        time.sleep(0.3)

    # Calculate metrics
    total = len(results)
    correct = sum(1 for r in results if r.get("correct"))
    accuracy = correct / total if total > 0 else 0

    # Abstention accuracy
    abstention_results = [r for r in results if r.get("expected") == "abstain"]
    abstention_correct = sum(1 for r in abstention_results if r.get("correct"))
    abstention_accuracy = (
        abstention_correct / len(abstention_results) if abstention_results else 1.0
    )

    # Generic fallbacks (should be 0)
    generic_fallbacks = sum(1 for r in results if r.get("is_generic"))

    # Per-type breakdown
    by_type: dict[str, dict] = {}
    for r in results:
        t = r.get("type", "unknown")
        if t not in by_type:
            by_type[t] = {"total": 0, "correct": 0}
        by_type[t]["total"] += 1
        if r.get("correct"):
            by_type[t]["correct"] += 1

    # Print detailed results
    print(f"\n{'='*60}")
    print(f"  58-QUESTION BATTERY RESULTS")
    print(f"{'='*60}")
    print(f"  Total questions:  {total}")
    print(f"  Correct:          {correct}")
    print(f"  Accuracy:         {accuracy:.1%} (target: ≥90%)")
    print(f"  Abstention acc:   {abstention_accuracy:.1%} (target: 100%)")
    print(f"  Generic fallbacks: {generic_fallbacks} (target: 0)")
    print(f"{'='*60}")
    print(f"\n  Per-type breakdown:")
    for t, stats in sorted(by_type.items()):
        acc = stats["correct"] / stats["total"] if stats["total"] > 0 else 0
        print(f"    {t:25} {stats['correct']}/{stats['total']} ({acc:.0%})")

    print(f"\n  Failures:")
    failures = [r for r in results if not r.get("correct")]
    for f in failures[:10]:
        print(f"    [{f['type']}] {f['query']}")
        if "error" in f:
            print(f"      ERROR: {f['error']}")
        else:
            print(f"      expected={f['expected']} abstained={f.get('is_abstention')} generic={f.get('is_generic')}")
            print(f"      answer: {f.get('answer_preview','')[:80]}")

    # Assertions
    assert accuracy >= 0.90, (
        f"Battery accuracy {accuracy:.1%} below 90% target ({correct}/{total} correct)"
    )
    assert abstention_accuracy == 1.0, (
        f"Abstention accuracy {abstention_accuracy:.1%} below 100% target"
    )
    assert generic_fallbacks == 0, (
        f"{generic_fallbacks} generic fallbacks detected (target: 0)"
    )


if __name__ == "__main__":
    # Run directly without pytest
    if not BASE or not TOKEN:
        print("Set MAESTRO_URL and MAESTRO_TOKEN env vars")
        exit(1)
    test_battery_58_questions()
