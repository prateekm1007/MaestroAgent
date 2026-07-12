"""
BM25 baseline scorer — runs the 50-question gold set against a plain
BM25/FTS-only baseline (no Maestro ranking, no LLM) and against the
full Maestro Ask endpoint. Reports composite scores for both so the
+15-point lift can be measured.

Phase 1 gold-set evaluation per Roadmap to 9/10:
  Maestro composite must be ≥ baseline + 15 absolute points.

Usage:
    python evaluation/scoreboard/bm25_baseline.py [--api-url http://127.0.0.1:8766]

If --api-url is not provided, the script runs in offline mode and only
scores the BM25 baseline (no Maestro comparison).
"""
import argparse
import json
import math
import re
import sqlite3
import sys
import urllib.request
import urllib.error
from pathlib import Path

# Add the maestro-personal/src to path
SCRIPT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPT_DIR / "src"))
sys.path.insert(0, str(SCRIPT_DIR))  # so 'evaluation' is importable

from evaluation.scoreboard.memory_v1 import get_corpus, get_questions


# ── BM25 baseline (plain FTS, no Maestro ranking) ──────────────────

def bm25_score(query, document, k1=1.5, b=0.75):
    """Plain BM25 score for a single query/document pair."""
    query_tokens = [t.lower() for t in re.findall(r'\b\w+\b', query) if len(t) >= 3]
    doc_tokens = [t.lower() for t in re.findall(r'\b\w+\b', document) if len(t) >= 3]
    if not query_tokens or not doc_tokens:
        return 0.0
    doc_len = len(doc_tokens)
    avg_len = doc_len  # single-doc BM25
    tf = {}
    for t in doc_tokens:
        tf[t] = tf.get(t, 0) + 1
    score = 0.0
    for term in query_tokens:
        if term not in tf:
            continue
        idf = 1.0  # single-doc, no IDF
        tf_val = tf[term]
        score += idf * (tf_val * (k1 + 1)) / (tf_val + k1 * (1 - b + b * doc_len / max(avg_len, 1)))
    return score


def bm25_retrieve(query, corpus, top_k=5):
    """Return top_k documents by BM25 score."""
    scored = []
    for sig in corpus:
        text = sig.get("text", "") + " " + sig.get("entity", "")
        score = bm25_score(query, text)
        scored.append((score, sig))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [sig for _, sig in scored[:top_k] if _ > 0]


# ── Scoring ────────────────────────────────────────────────────────

def score_answer(question, answer, retrieved):
    """Score an answer against gold labels. Returns 0.0-1.0."""
    q = question
    answer_lower = str(answer).lower()
    retrieved_text = " ".join(str(r.get("text", "")) + " " + str(r.get("entity", "")) for r in retrieved).lower()

    # Type-specific scoring
    if q["expected_type"] == "abstention":
        # Should admit no data
        return 1.0 if any(kw in answer_lower for kw in ["don't have", "no matching", "not enough", "no information"]) else 0.0

    # Check expected entities present
    expected = q.get("expected_entities", [])
    expected_lower = [e.lower() for e in expected]
    found = sum(1 for e in expected_lower if e in answer_lower or e in retrieved_text)
    entity_score = found / max(len(expected_lower), 1) if expected_lower else 0.5

    # Check NOT-expected entities absent
    not_expected = q.get("expected_not_entities", [])
    not_expected_lower = [e.lower() for e in not_expected]
    noise_present = sum(1 for e in not_expected_lower if e in answer_lower)
    noise_penalty = noise_present / max(len(not_expected_lower), 1) if not_expected_lower else 0.0

    # Priority check (for silence tests)
    if "expected_not_priority" in q:
        # Can't check priority from text alone; skip for BM25 baseline
        pass

    # Composite: entity_score - noise_penalty
    composite = entity_score * (1.0 - noise_penalty)
    return composite


def run_bm25_baseline():
    """Run all 50 questions through plain BM25. Returns list of (question, score)."""
    corpus = get_corpus()
    questions = get_questions()
    results = []
    for q in questions:
        retrieved = bm25_retrieve(q["q"], corpus, top_k=5)
        # BM25 "answer" is the concatenation of retrieved texts
        answer = " ".join(r.get("text", "") for r in retrieved)
        score = score_answer(q, answer, retrieved)
        results.append({"question": q["q"], "type": q["expected_type"], "score": score, "retrieved_count": len(retrieved)})
    return results


def run_maestro(api_url, token):
    """Run all 50 questions through the Maestro Ask endpoint."""
    questions = get_questions()
    results = []
    for q in questions:
        try:
            data = json.dumps({"query": q["q"]}).encode()
            req = urllib.request.Request(
                f"{api_url}/api/ask",
                data=data,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
            )
            resp = urllib.request.urlopen(req, timeout=60)
            body = json.loads(resp.read())
            answer = body.get("answer", "")
            evidence = body.get("evidence_refs", [])
            score = score_answer(q, answer, evidence if isinstance(evidence, list) else [])
            results.append({"question": q["q"], "type": q["expected_type"], "score": score, "answer_preview": answer[:200], "evidence_count": len(evidence)})
        except Exception as e:
            results.append({"question": q["q"], "type": q["expected_type"], "score": 0.0, "error": str(e)[:100]})
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default=None, help="Maestro API URL (e.g. http://127.0.0.1:8766)")
    parser.add_argument("--token", default=None, help="Bearer token for the API")
    parser.add_argument("--seed", action="store_true", help="Seed the corpus into the API before scoring")
    args = parser.parse_args()

    print("=" * 70)
    print("  MEMORY GOLD SET — BM25 BASELINE vs MAESTRO")
    print("=" * 70)

    # BM25 baseline
    print("\n[1] BM25 baseline (no Maestro ranking, no LLM)...")
    bm25_results = run_bm25_baseline()
    bm25_avg = sum(r["score"] for r in bm25_results) / len(bm25_results)
    print(f"    Composite score: {bm25_avg:.3f} ({sum(r['score'] for r in bm25_results)}/{len(bm25_results)})")

    # Per-type breakdown
    by_type = {}
    for r in bm25_results:
        t = r["type"]
        by_type.setdefault(t, []).append(r["score"])
    print("\n    By type:")
    for t, scores in sorted(by_type.items()):
        avg = sum(scores) / len(scores)
        print(f"      {t:20s} {avg:.3f}  (n={len(scores)})")

    # Maestro comparison (if API available)
    if args.api_url and args.token:
        print(f"\n[2] Maestro Ask ({args.api_url})...")
        if args.seed:
            print("    Seeding corpus...")
            corpus = get_corpus()
            for sig in corpus:
                try:
                    data = json.dumps(sig).encode()
                    req = urllib.request.Request(
                        f"{args.api_url}/api/signals",
                        data=data,
                        headers={"Content-Type": "application/json", "Authorization": f"Bearer {args.token}"},
                    )
                    urllib.request.urlopen(req, timeout=30)
                except Exception as e:
                    print(f"      seed failed for {sig['entity']}: {e}")

        maestro_results = run_maestro(args.api_url, args.token)
        maestro_avg = sum(r["score"] for r in maestro_results) / len(maestro_results)
        print(f"    Composite score: {maestro_avg:.3f} ({sum(r['score'] for r in maestro_results)}/{len(maestro_results)})")

        by_type_m = {}
        for r in maestro_results:
            t = r["type"]
            by_type_m.setdefault(t, []).append(r["score"])
        print("\n    By type:")
        for t, scores in sorted(by_type_m.items()):
            avg = sum(scores) / len(scores)
            print(f"      {t:20s} {avg:.3f}  (n={len(scores)})")

        lift = (maestro_avg - bm25_avg) * 100
        print(f"\n[3] Lift: Maestro - BM25 = {lift:+.1f} points (target: ≥ +15)")
        if lift >= 15:
            print("    ✓ PASS — Maestro beats BM25 by ≥ 15 points")
        else:
            print("    ✗ FAIL — Maestro does not meet the +15-point bar")
    else:
        print("\n[2] Maestro comparison skipped (no --api-url). Run with:")
        print(f"    python {__file__} --api-url http://127.0.0.1:8766 --token <TOKEN> --seed")

    print("\n" + "=" * 70)
    print(f"  BM25 baseline: {bm25_avg:.3f}")
    if args.api_url and args.token:
        print(f"  Maestro:       {maestro_avg:.3f}")
        print(f"  Lift:          {lift:+.1f} points")
    print("=" * 70)


if __name__ == "__main__":
    main()
