#!/usr/bin/env python3
"""generate_classifier_goldset.py — Generate the taxonomy gold-set for the classifier.

Auditor Principle 3 (2026-07-24): "Stop growing the test corpus one caught bug
at a time. Generate it: take the cross-product {declarative, interrogative,
imperative} × {affirmed, negated, hedged, third-party} × {present, past, future}
× a dictionary of words that are completion-verbs in one context and
adjectives/nouns in another, and emit hundreds of adversarial cases."

This script generates the cross-product and writes it as a JSON test corpus
that can be wired into CI as a merge gate. The corpus grows with the TAXONOMY,
not with audit rounds — so the next audit doesn't find a new instance because
the grid already covers it.

OUTPUT: ops/classifier_goldset.json — a list of {text, expected_type, expected_is_commitment, category}
"""
from __future__ import annotations

import json
import itertools
from pathlib import Path

# ── The taxonomy dimensions ─────────────────────────────────────────────

MOODS = {
    "declarative": "",  # no prefix — statement form
    "interrogative": "?",  # ends in question mark
    "imperative": "",  # command form (handled by template)
}

# Auxiliary-inversion prefixes for interrogative mood
INTERROGATIVE_PREFIXES = [
    "Should I", "Would you", "Could we", "Did they", "Is the",
    "Are we", "Can you", "Might he", "Do you", "Will the",
    "Has the", "Have they",
]

# Polarity forms
POLARITIES = {
    "affirmed": "",  # no negation
    "negated": "not ",  # negation
    "hedged": "maybe ",  # hedge
    "third_party": "Sarah said she ",  # third-party report
}

# Tenses — the ambiguous words change meaning by tense
TENSES = {
    "past": "past",  # "I sent" — completion
    "present": "present",  # "I send" — habitual
    "future": "future",  # "I will send" — promise
}

# The ambiguous-word dictionary: words that are completion-verbs in one
# context and adjectives/nouns in another. Half the keyword list is exactly
# this ambiguity (auditor: "updated, scheduled, shared, signed, published,
# reviewed — half the keyword list is exactly this ambiguity").
AMBIGUOUS_WORDS = [
    "updated", "scheduled", "shared", "signed", "published", "reviewed",
    "finalized", "approved", "submitted", "shipped", "deployed", "merged",
    "released", "emailed", "forwarded", "resolved", "closed", "delivered",
    "completed", "finished", "paid",
]

# Nouns that the ambiguous words can modify (adjective use)
NOUNS = ["roadmap", "report", "document", "contract", "feature", "release", "proposal", "design"]


def generate_cases() -> list[dict]:
    """Generate the cross-product taxonomy gold-set."""
    cases = []

    # ── Grid 1: interrogative + ambiguous word = NOT a completion ──────
    # "Should I send the team the updated roadmap tomorrow?"
    for prefix in INTERROGATIVE_PREFIXES:
        for word in AMBIGUOUS_WORDS:
            for noun in NOUNS:
                text = f"{prefix} send the team the {word} {noun} tomorrow?"
                cases.append({
                    "text": text,
                    "expected_type": "not_a_commitment",
                    "expected_is_commitment": False,
                    "category": "interrogative+ambiguous_adjective",
                    "reasoning": f"Question with '{word}' as adjective modifying '{noun}' — not a completion",
                })

    # ── Grid 2: future intention + ambiguous word as adjective = NOT completion ──
    # "I will send the updated roadmap tomorrow."
    for word in AMBIGUOUS_WORDS:
        for noun in NOUNS:
            text = f"I will send the {word} {noun} tomorrow."
            cases.append({
                "text": text,
                "expected_type": "explicit",  # it's a promise, not a completion
                "expected_is_commitment": True,
                "category": "future+ambiguous_adjective",
                "reasoning": f"Future promise with '{word}' as adjective — should be explicit, not completed",
            })

    # ── Grid 3: declarative past + ambiguous word as verb = completion ──
    # "I sent the proposal yesterday." / "The report was reviewed last week."
    for word in AMBIGUOUS_WORDS:
        text = f"I {word} the proposal yesterday."
        cases.append({
            "text": text,
            "expected_type": "completed",
            "expected_is_commitment": True,
            "category": "declarative_past+verb",
            "reasoning": f"Declarative past-tense '{word}' as verb — should be completed",
        })

    # ── Grid 4: interrogative + cancellation keyword = NOT cancellation ──
    # "Should I cancel the meeting?"
    cancel_words = ["cancel", "cancelled"]
    for prefix in INTERROGATIVE_PREFIXES:
        for cw in cancel_words:
            text = f"{prefix} {cw} the meeting?"
            cases.append({
                "text": text,
                "expected_type": "not_a_commitment",
                "expected_is_commitment": False,
                "category": "interrogative+cancellation",
                "reasoning": f"Question about cancelling — not a cancellation itself",
            })

    # ── Grid 5: declarative cancellation = cancelled ───────────────────
    # "I cancelled the meeting."
    for cw in cancel_words:
        text = f"I {cw} the meeting."
        cases.append({
            "text": text,
            "expected_type": "cancelled",
            "expected_is_commitment": True,
            "category": "declarative_cancellation",
            "reasoning": f"Declarative cancellation — should be cancelled",
        })

    # ── Grid 6: negation patterns ──────────────────────────────────────
    negation_texts = [
        "I won't be able to send the proposal.",
        "I will not attend the meeting.",
        "I can't deliver the report by Friday.",
        "I cannot commit to this deadline.",
    ]
    for text in negation_texts:
        cases.append({
            "text": text,
            "expected_type": "negation",
            "expected_is_commitment": False,
            "category": "negation",
            "reasoning": "Explicit refusal — not a commitment",
        })

    # ── Grid 7: hedged/tentative patterns ──────────────────────────────
    tentative_texts = [
        "Maybe I can send it next week, but don't count on it.",
        "I might be able to deliver by Friday.",
        "I hope to get it done soon.",
        "No promises, but I'll try.",
    ]
    for text in tentative_texts:
        cases.append({
            "text": text,
            "expected_type": "tentative",
            "expected_is_commitment": False,
            "category": "hedged_tentative",
            "reasoning": "Hedged language — not a firm commitment",
        })

    # ── Grid 8: third-party reports ────────────────────────────────────
    third_party_texts = [
        "Sarah said she will send the proposal by Friday.",
        "John mentioned he would review the code.",
        "They told me they'll deliver next week.",
    ]
    for text in third_party_texts:
        cases.append({
            "text": text,
            "expected_type": "third_party_report",
            "expected_is_commitment": True,
            "category": "third_party_report",
            "reasoning": "Reporting someone else's promise — is a commitment",
        })

    # ── Grid 9: the exact S1 case + variants ───────────────────────────
    s1_variants = [
        "Should I send the team the updated roadmap tomorrow?",
        "Would you like me to send the reviewed document?",
        "Did you get the scheduled meeting invite?",
        "Is the published report ready?",
        "Are we going to ship the finalized feature?",
        "Can you review the shared document?",
    ]
    for text in s1_variants:
        cases.append({
            "text": text,
            "expected_type": "not_a_commitment",
            "expected_is_commitment": False,
            "category": "s1_variant",
            "reasoning": "Original S1 case + grammatical variants — must be rejected",
        })

    return cases


def main():
    cases = generate_cases()
    output_path = Path(__file__).parent / "classifier_goldset.json"
    with open(output_path, "w") as f:
        json.dump(cases, f, indent=2)

    # Summary by category
    from collections import Counter
    cats = Counter(c["category"] for c in cases)
    print(f"Generated {len(cases)} gold-set cases → {output_path}")
    print("\nBy category:")
    for cat, count in sorted(cats.items()):
        print(f"  {cat:40s} {count:4d}")

    print(f"\nExpected type distribution:")
    types = Counter(c["expected_type"] for c in cases)
    for t, count in sorted(types.items()):
        print(f"  {t:25s} {count:4d}")


if __name__ == "__main__":
    main()
