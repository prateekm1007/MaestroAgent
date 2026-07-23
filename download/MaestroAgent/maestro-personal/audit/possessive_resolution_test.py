#!/usr/bin/env python3
"""Unit test for deterministic possessive entity resolution.

Tests the three-benefit fix:
  1. "Alex's thing" → resolves to "Alex Chen" (not Maria Garcia)
  2. Deterministic — same result every time (no LLM stochasticity)
  3. Consistency — "Alex's thing" and "What did Alex promise?" resolve
     to the same canonical entity
"""
from __future__ import annotations
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from maestro_personal_shell.entity_resolver import (
    extract_possessive_entity,
    resolve_possessive_to_canonical,
    filter_evidence_to_entity,
)


# Synthetic signals simulating the benchmark corpus
SYNTHETIC_SIGNALS = [
    {"entity": "Alex Chen", "text": "review the auth module", "signal_id": "s1"},
    {"entity": "Maria Garcia", "text": "Q3 budget proposal", "signal_id": "s2"},
    {"entity": "Jamie Lee", "text": "design mockups", "signal_id": "s3"},
    {"entity": "David Kim", "text": "coffee next week, tentative", "signal_id": "s4"},
    {"entity": "Priya Patel", "text": "CI pipeline", "signal_id": "s5"},
    {"entity": "Sam Rivera", "text": "roadmap", "signal_id": "s6"},
]


def test_extraction():
    """extract_possessive_entity finds the first name in possessive queries."""
    print("\n[1] extract_possessive_entity")
    cases = [
        ("Alex's thing — what did I promise?", "Alex"),
        ("What did Maria promise?", None),  # no possessive
        ("Jamie's stuff", "Jamie"),
        ("Sam's situation", "Sam"),
        ("What did I promise Maria and Elon?", None),  # no possessive
    ]
    all_pass = True
    for query, expected in cases:
        result = extract_possessive_entity(query)
        ok = result == expected
        status = "✓" if ok else "✗"
        print(f"  {status} {query!r:50s} → {result!r} (expected {expected!r})")
        if not ok:
            all_pass = False
    return all_pass


def test_resolution():
    """resolve_possessive_to_canonical resolves first name to full entity."""
    print("\n[2] resolve_possessive_to_canonical")
    cases = [
        ("Alex's thing — what did I promise?", "Alex Chen"),
        ("Maria's stuff", "Maria Garcia"),
        ("Jamie's situation", "Jamie Lee"),
        ("David's matter", "David Kim"),
        ("Priya's item", "Priya Patel"),
        ("Sam's thing", "Sam Rivera"),
    ]
    all_pass = True
    for query, expected in cases:
        result = resolve_possessive_to_canonical(query, SYNTHETIC_SIGNALS)
        ok = result == expected
        status = "✓" if ok else "✗"
        print(f"  {status} {query!r:45s} → {result!r} (expected {expected!r})")
        if not ok:
            all_pass = False
    return all_pass


def test_consistency():
    """Same entity regardless of phrasing (consistency-trust gap)."""
    print("\n[3] Consistency — possessive vs explicit both resolve to same entity")
    queries_possessive = [
        "Alex's thing — what did I promise?",
        "Maria's stuff",
        "Jamie's situation",
    ]
    queries_explicit = [
        "What did Alex promise?",
        "What did Maria promise?",
        "What did Jamie promise?",
    ]
    all_pass = True
    for qp, qe in zip(queries_possessive, queries_explicit):
        # Possessive path uses resolve_possessive_to_canonical
        canon_poss = resolve_possessive_to_canonical(qp, SYNTHETIC_SIGNALS)
        # Explicit path: extract "Alex" from "What did Alex promise?" and resolve
        import re
        m = re.search(r'\b([A-Z][a-z]+)\b', qe.replace("What", "").replace("Did", ""))
        first_name = m.group(1) if m else None
        canon_expl = None
        if first_name:
            from maestro_personal_shell.entity_resolver import resolve_entity_with_signals
            canon_expl = resolve_entity_with_signals(first_name, SYNTHETIC_SIGNALS)
        ok = canon_poss == canon_expl
        status = "✓" if ok else "✗"
        print(f"  {status} possessive={canon_poss!r:20s} explicit={canon_expl!r:20s} {'MATCH' if ok else 'MISMATCH'}")
        if not ok:
            all_pass = False
    return all_pass


def test_evidence_filter():
    """filter_evidence_to_entity excludes wrong-entity evidence (Alex's-thing fix)."""
    print("\n[4] filter_evidence_to_entity — Alex's-thing must NOT return Maria's evidence")
    # Simulate what the ensemble might return: Maria's evidence ranked higher
    mixed_evidence = [
        {"entity": "Maria Garcia", "text": "Q3 budget proposal", "signal_id": "s2"},
        {"entity": "Alex Chen", "text": "review the auth module", "signal_id": "s1"},
        {"entity": "Jamie Lee", "text": "design mockups", "signal_id": "s3"},
    ]
    canonical = resolve_possessive_to_canonical("Alex's thing", SYNTHETIC_SIGNALS)
    filtered = filter_evidence_to_entity(mixed_evidence, canonical)

    # After filtering, ALL evidence should be for Alex Chen
    all_alex = all("alex chen" in str(ev.get("entity", "")).lower() for ev in filtered)
    no_maria = all("maria" not in str(ev.get("entity", "")).lower() for ev in filtered)

    print(f"  canonical entity: {canonical!r}")
    print(f"  pre-filter entities: {[ev['entity'] for ev in mixed_evidence]}")
    print(f"  post-filter entities: {[ev['entity'] for ev in filtered]}")
    print(f"  all evidence is Alex Chen: {all_alex} {'✓' if all_alex else '✗'}")
    print(f"  no Maria Garcia evidence:  {no_maria} {'✓' if no_maria else '✗'}")
    return all_alex and no_maria


def test_determinism():
    """Same result every time (CI flakiness fix)."""
    print("\n[5] Determinism — same query resolves identically across 10 runs")
    query = "Alex's thing — what did I promise?"
    results = [resolve_possessive_to_canonical(query, SYNTHETIC_SIGNALS) for _ in range(10)]
    all_same = len(set(results)) == 1
    print(f"  10 runs of {query!r}:")
    print(f"  results: {set(results)}")
    print(f"  all identical: {all_same} {'✓' if all_same else '✗'}")
    return all_same


def test_no_match_lowercase_possessive():
    """Edge case #1a: lowercase possessive (\"the project's status\") — no extraction, no over-abstention.

    The regex requires [A-Z][a-z]+ so lowercase possessives don't match.
    The filter is skipped entirely, evidence stays intact. This prevents
    spurious abstention on generic possessives like \"the project's status\".
    """
    print("\n[6a] No-match: lowercase possessive (\"the project's status\")")
    query = "the project's status — what's the latest?"
    extracted = extract_possessive_entity(query)
    canonical = resolve_possessive_to_canonical(query, SYNTHETIC_SIGNALS)
    mixed_evidence = [
        {"entity": "Alex Chen", "text": "auth module", "signal_id": "s1"},
        {"entity": "Maria Garcia", "text": "Q3 budget", "signal_id": "s2"},
    ]
    # canonical should be None (no regex match) → filter skipped
    if canonical is None:
        # Filter skipped — evidence intact
        ok = len(mixed_evidence) == 2
        print(f"  extracted: {extracted!r}, canonical: {canonical!r}")
        print(f"  filter skipped (canonical is None) → {len(mixed_evidence)} evidence rows intact")
        print(f"  {'✓ PASS — no over-abstention' if ok else '✗ FAIL'}")
        return ok
    else:
        # Shouldn't happen, but check the fallback
        filtered = filter_evidence_to_entity(mixed_evidence, canonical)
        ok = len(filtered) == len(mixed_evidence)  # fallback should preserve all
        print(f"  extracted: {extracted!r}, canonical: {canonical!r}")
        print(f"  filter fell back to unfiltered → {len(filtered)} rows (was {len(mixed_evidence)})")
        print(f"  {'✓ PASS — fallback preserved evidence' if ok else '✗ FAIL — over-filtered'}")
        return ok


def test_no_match_capitalized_unresolvable():
    """Edge case #1b: capitalized possessive that doesn't resolve (\"Elon's stuff\" with no Elon).

    \"Elon\" is extracted but doesn't match any known entity. The resolver
    returns the bare name \"Elon\", the filter finds no matches, and the
    fallback returns ALL evidence (don't over-abstain). This is the
    over-abstention mirror of Alex's-thing — we must NOT force abstention
    when the possessive names an unknown entity.
    """
    print("\n[6b] No-match: capitalized unresolvable (\"Elon's stuff\" with no Elon in signals)")
    query = "Elon's stuff — what did I promise?"
    extracted = extract_possessive_entity(query)
    canonical = resolve_possessive_to_canonical(query, SYNTHETIC_SIGNALS)
    mixed_evidence = [
        {"entity": "Alex Chen", "text": "auth module", "signal_id": "s1"},
        {"entity": "Maria Garcia", "text": "Q3 budget", "signal_id": "s2"},
    ]
    filtered = filter_evidence_to_entity(mixed_evidence, canonical or "")
    # Fallback should preserve ALL evidence (no matches → return original)
    ok = len(filtered) == len(mixed_evidence)
    print(f"  extracted: {extracted!r}, canonical: {canonical!r}")
    print(f"  filter result: {len(filtered)} rows (was {len(mixed_evidence)})")
    print(f"  entities preserved: {[ev['entity'] for ev in filtered]}")
    print(f"  {'✓ PASS — no over-abstention (fallback preserved evidence)' if ok else '✗ FAIL — over-filtered to nothing'}")
    return ok


def test_multi_entity_possessive():
    """Edge case #2: multi-entity possessive (\"Maria and Alex's things\") — UNION, not first-only.

    The resolver now extracts ALL possessive entities and filters to their
    union. \"Maria and Alex's things\" resolves to BOTH Maria Garcia AND
    Alex Chen, keeping evidence for both.
    """
    print("\n[7] Multi-entity possessive (\"Maria and Alex's things\") — UNION")
    from maestro_personal_shell.entity_resolver import (
        extract_all_possessive_entities,
        resolve_possessives_to_canonical_set,
        filter_evidence_to_entities,
    )
    query = "Maria and Alex's things — what did I promise?"
    extracted = extract_all_possessive_entities(query)
    canonicals = resolve_possessives_to_canonical_set(query, SYNTHETIC_SIGNALS)
    mixed_evidence = [
        {"entity": "Maria Garcia", "text": "Q3 budget", "signal_id": "s2"},
        {"entity": "Alex Chen", "text": "auth module", "signal_id": "s1"},
        {"entity": "Jamie Lee", "text": "design mockups", "signal_id": "s3"},
    ]
    filtered = filter_evidence_to_entities(mixed_evidence, canonicals)

    print(f"  query: {query!r}")
    print(f"  extracted (all possessives): {extracted!r}")
    print(f"  canonicals: {canonicals!r}")
    print(f"  pre-filter entities: {[ev['entity'] for ev in mixed_evidence]}")
    print(f"  post-filter entities: {[ev['entity'] for ev in filtered]}")

    # After filtering: Maria + Alex kept, Jamie dropped
    has_maria = any("maria" in str(ev.get("entity", "")).lower() for ev in filtered)
    has_alex = any("alex" in str(ev.get("entity", "")).lower() for ev in filtered)
    no_jamie = all("jamie" not in str(ev.get("entity", "")).lower() for ev in filtered)

    ok = has_maria and has_alex and no_jamie
    print(f"  Maria kept: {has_maria}, Alex kept: {has_alex}, Jamie dropped: {no_jamie}")
    print(f"  {'✓ PASS — union filter keeps both Maria and Alex' if ok else '✗ FAIL'}")
    return ok


def main():
    print("=" * 72)
    print("THREE-BENEFIT FIX: Deterministic possessive entity resolution")
    print("=" * 72)

    results = {
        "Extraction": test_extraction(),
        "Resolution": test_resolution(),
        "Consistency": test_consistency(),
        "Evidence filter (Alex's-thing)": test_evidence_filter(),
        "Determinism (CI flakiness)": test_determinism(),
        "No-match lowercase (no over-abstain)": test_no_match_lowercase_possessive(),
        "No-match unresolvable (no over-abstain)": test_no_match_capitalized_unresolvable(),
        "Multi-entity possessive (documented)": test_multi_entity_possessive(),
    }

    print(f"\n{'='*72}")
    print("VERDICT")
    print(f"{'='*72}")
    all_pass = True
    for name, ok in results.items():
        print(f"  {name:45s} {'✓ PASS' if ok else '✗ FAIL'}")
        if not ok:
            all_pass = False
    print()
    if all_pass:
        print("ALL TESTS PASS — the three-benefit fix is working:")
        print("  1. Alex's-thing resolves to Alex Chen (not Maria Garcia)")
        print("  2. Same result every run (no LLM stochasticity)")
        print("  3. Possessive + explicit phrasings resolve to same entity")
        print("  4. No-match possessives don't over-abstain (fallback preserves evidence)")
        print("  5. Multi-entity possessives resolve to UNION (not first-only)")
    else:
        print("AT LEAST ONE TEST FAILED — fix needed.")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
