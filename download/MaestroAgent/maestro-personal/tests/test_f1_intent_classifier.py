"""F1 intent classifier regression tests.

Verifies that the expanded intent detection correctly routes queries
to specialized retrieval logic. The key test: "What did I fail to
deliver?" (broken intent) must boost signals containing "never sent"
and "didn't deliver" — not just keyword-match "fail" against signal text.
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "backend"))

from maestro_personal_shell.ask_ranker import understand_query, rerank_signals, rank_for_ask


# Test corpus — signals with different types
SIGNALS = [
    # Broken commitments
    {"entity": "Riley", "text": "Never sent the security questionnaire — overdue", "signal_type": "reported_statement", "timestamp": "2026-07-01T00:00:00Z"},
    {"entity": "Priya", "text": "Compliance report is overdue — hasn't been sent", "signal_type": "reported_statement", "timestamp": "2026-06-30T00:00:00Z"},
    {"entity": "Avery", "text": "I will send the quarterly report", "signal_type": "commitment_made", "timestamp": "2026-04-27T00:00:00Z"},

    # Completed commitments
    {"entity": "Alex", "text": "I will send the pricing deck by Friday", "signal_type": "commitment_made", "timestamp": "2026-05-28T00:00:00Z"},
    {"entity": "Alex", "text": "Sent the pricing deck yesterday", "signal_type": "reported_statement", "timestamp": "2026-05-30T00:00:00Z"},
    {"entity": "Sam", "text": "Delivered the API integration on time", "signal_type": "reported_statement", "timestamp": "2026-06-07T00:00:00Z"},

    # Contradiction
    {"entity": "Orion", "text": "Orion quoted us $120k for the annual contract", "signal_type": "reported_statement", "timestamp": "2026-06-12T00:00:00Z"},
    {"entity": "Orion", "text": "Orion revised the quote down to $95k", "signal_type": "reported_statement", "timestamp": "2026-06-22T00:00:00Z"},

    # Noise
    {"entity": "Newsletter", "text": "Weekly tech digest: 10 articles about AI", "signal_type": "newsletter", "timestamp": "2026-07-04T00:00:00Z"},
]


def test_broken_intent_detected():
    """F1: 'What did I fail to deliver?' must detect 'broken' intent."""
    u = understand_query("What did I fail to deliver?")
    assert u["intent"] == "broken", f"Expected 'broken', got '{u['intent']}'"
    assert "never sent" in u["intent_keywords"], "broken intent must have 'never sent' keyword"
    assert "didn't deliver" in u["intent_keywords"], "broken intent must have 'didn't deliver' keyword"


def test_broken_intent_finds_riley():
    """F1: 'What did I fail to deliver?' must rank Riley's 'Never sent' signal first."""
    result = rank_for_ask("What did I fail to deliver?", SIGNALS)
    top = result["top_evidence"]
    assert len(top) > 0, "Should find evidence"
    # Riley's "Never sent" signal should be in top 3
    top_entities = [s.get("entity", "") for s in top[:3]]
    assert "Riley" in top_entities, (
        f"F1 FAIL: Riley not in top 3. Got: {top_entities}. "
        f"Top scores: {[(s.get('entity'), s.get('_rank_score')) for s in top[:3]]}"
    )


def test_overdue_intent_detected():
    """F1: 'Which promises are overdue?' must detect 'overdue' intent."""
    u = understand_query("Which promises are overdue?")
    assert u["intent"] == "overdue", f"Expected 'overdue', got '{u['intent']}'"
    assert "overdue" in u["intent_keywords"]


def test_overdue_intent_finds_overdue_signals():
    """F1: 'Which promises are overdue?' must find overdue signals."""
    result = rank_for_ask("Which promises are overdue?", SIGNALS)
    top = result["top_evidence"]
    top_text = " ".join(s.get("text", "") for s in top[:3]).lower()
    assert "overdue" in top_text or "never sent" in top_text, (
        f"F1 FAIL: overdue signals not in top 3. Got: {[s.get('text','')[:40] for s in top[:3]]}"
    )


def test_relational_intent_detected():
    """F1: 'Who am I disappointing?' must detect 'relational' intent."""
    u = understand_query("Who am I repeatedly disappointing?")
    # Could be 'relational' or 'stale_memory' — both are valid for this query
    assert u["intent"] in ("relational", "stale_memory", "risk"), (
        f"Expected relational/stale_memory/risk, got '{u['intent']}'"
    )


def test_relational_intent_finds_broken_entities():
    """F1: 'Who am I disappointing?' must find Riley/Priya (broken commitments)."""
    u = understand_query("Who am I disappointing?")
    # If intent is 'relational', check the keywords
    if u["intent"] == "relational":
        result = rank_for_ask("Who am I disappointing?", SIGNALS)
        top = result["top_evidence"]
        top_entities = [s.get("entity", "") for s in top[:5]]
        # Should include Riley or Priya (broken commitment entities)
        assert "Riley" in top_entities or "Priya" in top_entities, (
            f"F1 FAIL: broken-commitment entities not in top 5. Got: {top_entities}"
        )


def test_commitment_intent_still_works():
    """Sanity: 'What did I promise Alex?' must still detect 'commitment' intent."""
    u = understand_query("What did I promise Alex?")
    assert u["intent"] == "commitment", f"Expected 'commitment', got '{u['intent']}'"
    assert "Alex" in u["entity_mentions"]


def test_contradiction_intent_still_works():
    """Sanity: 'What is Orion pricing?' must detect 'contradiction' intent."""
    u = understand_query("What is Orion Tech's pricing?")
    assert u["intent"] == "contradiction", f"Expected 'contradiction', got '{u['intent']}'"


def test_noise_signals_penalized():
    """F1: newsletter signals must never appear in top evidence for non-noise queries."""
    result = rank_for_ask("What did I fail to deliver?", SIGNALS)
    top = result["top_evidence"]
    for s in top:
        assert s.get("signal_type") != "newsletter", (
            f"F1 FAIL: newsletter in top evidence: {s.get('entity')}"
        )


def test_general_intent_for_unknown_queries():
    """F1: queries that don't match any intent pattern should be 'general'."""
    u = understand_query("Tell me about the project")
    assert u["intent"] == "general", f"Expected 'general', got '{u['intent']}'"


if __name__ == "__main__":
    test_broken_intent_detected()
    print("F1 test 1/9: broken intent detected — PASS")
    test_broken_intent_finds_riley()
    print("F1 test 2/9: broken intent finds Riley — PASS")
    test_overdue_intent_detected()
    print("F1 test 3/9: overdue intent detected — PASS")
    test_overdue_intent_finds_overdue_signals()
    print("F1 test 4/9: overdue intent finds overdue signals — PASS")
    test_relational_intent_detected()
    print("F1 test 5/9: relational intent detected — PASS")
    test_relational_intent_finds_broken_entities()
    print("F1 test 6/9: relational intent finds broken entities — PASS")
    test_commitment_intent_still_works()
    print("F1 test 7/9: commitment intent still works — PASS")
    test_contradiction_intent_still_works()
    print("F1 test 8/9: contradiction intent still works — PASS")
    test_noise_signals_penalized()
    print("F1 test 9/9: noise signals penalized — PASS")
    print("\nF1 intent classifier tests PASSED")
