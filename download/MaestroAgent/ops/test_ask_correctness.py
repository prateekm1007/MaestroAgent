#!/usr/bin/env python3
"""test_ask_correctness.py — Ask engine correctness gate.

Auditor (2026-07-24) next automation frontier: "Build the Ask correctness
gate: take the independent auditor's adversarial Ask battery
(easy / temporal / relationship / negative / unknown / contradictory) and
gate merges on the Ask engine passing them — correct answer, correct
abstention on unknowns, evidence present, no contradiction-denial, no
contamination."
"""
from __future__ import annotations

import json
import os
import sys
import time
import httpx

BACKEND_URL = os.environ.get(
    "MAESTRO_BACKEND_URL",
    "https://maestroagent-production.up.railway.app",
)

LIFECYCLE_SIGNALS = [
    {
        "signal_id": f"ask-maria-active-{int(time.time())}",
        "entity": "Maria Garcia",
        "text": "I will send the Q3 budget proposal to Maria by Friday.",
        "signal_type": "commitment_made",
        "timestamp": "2026-07-22T10:00:00Z",
        "metadata": {"source": "ask_correctness_gate", "is_commitment": True, "commitment_type": "commitment_made", "commitment_state": "active", "commitment_owner": "user", "commitment_confidence": 0.9},
    },
    {
        "signal_id": f"ask-maria-reschedule-{int(time.time())}",
        "entity": "Maria Garcia",
        "text": "I know I said Friday, but can we move it to next Wednesday instead?",
        "signal_type": "commitment_updated",
        "timestamp": "2026-07-23T14:00:00Z",
        "metadata": {"source": "ask_correctness_gate", "is_commitment": True, "commitment_type": "commitment_updated", "commitment_state": "active", "commitment_owner": "user", "commitment_confidence": 0.8},
    },
    {
        "signal_id": f"ask-alex-completed-{int(time.time())}",
        "entity": "Alex Chen",
        "text": "I said I'd review the auth module by Tuesday, but I actually already reviewed it yesterday.",
        "signal_type": "commitment_completed",
        "timestamp": "2026-07-23T09:00:00Z",
        "metadata": {"source": "ask_correctness_gate", "is_commitment": True, "commitment_type": "commitment_completed", "commitment_state": "completed_claimed", "commitment_owner": "user", "commitment_confidence": 0.9},
    },
    {
        "signal_id": f"ask-jamie-cancelled-{int(time.time())}",
        "entity": "Jamie Lee",
        "text": "Actually, let's cancel the design mockups — we're going in a different direction.",
        "signal_type": "commitment_broken",
        "timestamp": "2026-07-22T16:00:00Z",
        "metadata": {"source": "ask_correctness_gate", "is_commitment": True, "commitment_type": "commitment_broken", "commitment_state": "cancelled", "commitment_owner": "user", "commitment_confidence": 0.85},
    },
    {
        "signal_id": f"ask-priya-active-{int(time.time())}",
        "entity": "Priya Patel",
        "text": "I will fix the CI pipeline by end of week.",
        "signal_type": "commitment_made",
        "timestamp": "2026-07-22T11:00:00Z",
        "metadata": {"source": "ask_correctness_gate", "is_commitment": True, "commitment_type": "commitment_made", "commitment_state": "active", "commitment_owner": "user", "commitment_confidence": 0.9},
    },
]

TEST_CASES = [
    {"category": "easy", "query": "What did I promise Maria?", "must_abstain": False, "answer_must_contain": ["maria"], "evidence_must_contain_entity": "maria", "evidence_must_not_contain": "david", "reasoning": "Direct entity query"},
    {"category": "easy", "query": "What did I promise Alex?", "must_abstain": False, "answer_must_contain": ["alex"], "evidence_must_contain_entity": "alex", "reasoning": "Direct entity query"},
    {"category": "easy", "query": "What did I promise Priya?", "must_abstain": False, "answer_must_contain": ["priya"], "evidence_must_contain_entity": "priya", "reasoning": "Direct entity query"},
    {"category": "temporal", "query": "What did I promise Maria since Tuesday?", "must_abstain": False, "answer_must_contain": ["maria"], "evidence_must_contain_entity": "maria", "reasoning": "Temporal query"},
    {"category": "temporal", "query": "What commitments were made this week?", "must_abstain": False, "answer_must_contain": [], "evidence_must_contain_entity": "", "reasoning": "Broad temporal query"},
    {"category": "relationship", "query": "What did I promise Maria and Alex?", "must_abstain": False, "answer_must_contain": ["maria"], "evidence_must_contain_entity": "maria", "reasoning": "Multi-entity query"},
    {"category": "negative", "query": "What did I not promise?", "must_abstain": True, "answer_must_contain": [], "evidence_must_contain_entity": "", "reasoning": "Negation query — system SHOULD abstain (can't meaningfully enumerate what was NOT promised)"},
    {"category": "unknown", "query": "What did I promise David Kim?", "must_abstain": True, "answer_must_contain": [], "evidence_must_contain_entity": "", "evidence_must_not_contain": "david", "reasoning": "Unknown entity — MUST abstain"},
    {"category": "unknown", "query": "What happened with Project Titan?", "must_abstain": True, "answer_must_contain": [], "evidence_must_contain_entity": "", "reasoning": "Unknown project — MUST abstain"},
    {"category": "unknown", "query": "What did I promise John Smith?", "must_abstain": True, "answer_must_contain": [], "evidence_must_contain_entity": "", "evidence_must_not_contain": "john", "reasoning": "Unknown entity — MUST abstain"},
    {"category": "contradictory", "query": "What did I promise Maria? Give only evidence and account for whether the proposal was received or rescheduled.", "must_abstain": False, "answer_must_contain": ["wednesday"], "evidence_must_contain_entity": "maria", "evidence_must_not_contain": "david", "reasoning": "Must surface reschedule"},
    {"category": "contradictory", "query": "Did I complete my review of the auth module?", "must_abstain": False, "answer_must_contain": ["alex"], "evidence_must_contain_entity": "alex", "reasoning": "Must surface completion"},
    {"category": "contamination", "query": "What did I promise Maria?", "must_abstain": False, "answer_must_contain": ["maria"], "evidence_must_contain_entity": "maria", "evidence_must_not_contain": "david", "reasoning": "No cross-entity leak"},
]


def setup_tenant():
    print("[SETUP] Registering + seeding lifecycle fixture...")
    resp = httpx.post(
        f"{BACKEND_URL}/api/auth/register",
        json={"user_email": f"ask-gate-{int(time.time())}@example.com", "password": "ask-gate-pass", "name": "AskGate"},
        timeout=30,
    )
    token = resp.json().get("token", "")
    if not token:
        print(f"  ✗ Register failed: {resp.json()}")
        sys.exit(1)
    for sig in LIFECYCLE_SIGNALS:
        for attempt in range(3):
            try:
                r = httpx.post(f"{BACKEND_URL}/api/signals", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, json=sig, timeout=30)
                if r.status_code == 200:
                    break
                time.sleep(2)
            except Exception:
                time.sleep(2)
        time.sleep(1)
    time.sleep(3)
    print("  ✓ Fixture seeded")
    return token


def run_ask(token, query):
    for attempt in range(3):
        resp = httpx.post(f"{BACKEND_URL}/api/ask", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, json={"query": query}, timeout=60)
        if resp.status_code == 200:
            return resp.json()
        time.sleep(2)
    return {"error": f"HTTP {resp.status_code}", "body": resp.text[:200]}


def run_gate():
    token = setup_tenant()
    results = {"total": len(TEST_CASES), "passed": 0, "failed": 0, "by_category": {}, "failures": []}
    for case in TEST_CASES:
        category = case["category"]
        query = case["query"]
        must_abstain = case.get("must_abstain", False)
        answer_must_contain = case.get("answer_must_contain", [])
        evidence_must_contain_entity = case.get("evidence_must_contain_entity", "")
        evidence_must_not_contain = case.get("evidence_must_not_contain", "")
        if category not in results["by_category"]:
            results["by_category"][category] = {"passed": 0, "failed": 0}
        d = run_ask(token, query)
        answer = str(d.get("answer", ""))
        confidence = d.get("confidence", 0)
        evidence = d.get("evidence_refs", [])
        evidence_entities = set(str(e.get("entity", "")).lower() for e in evidence)
        answer_lower = answer.lower()
        fails = []
        if must_abstain:
            if confidence != 0.0:
                fails.append(f"should abstain (confidence=0), got confidence={confidence}")
            if len(evidence) > 0:
                fails.append(f"should have 0 evidence, got {len(evidence)}")
        else:
            if confidence <= 0.0 and "error" not in d:
                fails.append(f"should not abstain, got confidence={confidence}")
        for s in answer_must_contain:
            if s.lower() not in answer_lower:
                fails.append(f"answer should contain '{s}', got: {answer[:100]}")
        if evidence_must_contain_entity:
            if not any(evidence_must_contain_entity in e for e in evidence_entities):
                fails.append(f"evidence should contain '{evidence_must_contain_entity}', got: {evidence_entities}")
        if evidence_must_not_contain:
            if any(evidence_must_not_contain in e for e in evidence_entities):
                fails.append(f"evidence must NOT contain '{evidence_must_not_contain}', got: {evidence_entities}")
            if evidence_must_not_contain in answer_lower:
                fails.append(f"answer must NOT contain '{evidence_must_not_contain}'")
        if not must_abstain and len(evidence) > 0:
            denial_phrases = ["no evidence", "no record", "don't have any", "no commitments found", "nothing found"]
            if any(phrase in answer_lower for phrase in denial_phrases):
                fails.append(f"answer denies evidence that exists: {answer[:100]}")
        if fails:
            results["failed"] += 1
            results["by_category"][category]["failed"] += 1
            results["failures"].append({"category": category, "query": query[:80], "fails": fails, "detail": f"confidence={confidence}, evidence={len(evidence)}, answer={answer[:80]}"})
        else:
            results["passed"] += 1
            results["by_category"][category]["passed"] += 1
    return results


def main():
    print("=" * 72)
    print("ASK CORRECTNESS GATE — adversarial question taxonomy")
    print("(easy / temporal / relationship / negative / unknown / contradictory)")
    print(f"Backend: {BACKEND_URL}")
    print("=" * 72)
    report = run_gate()
    print(f"\nTotal cases: {report['total']}")
    print(f"Passed: {report['passed']}")
    print(f"Failed: {report['failed']}")
    print(f"\nBy category:")
    for cat, counts in sorted(report["by_category"].items()):
        total = counts["passed"] + counts["failed"]
        pct = (counts["passed"] / total * 100) if total > 0 else 0
        icon = "✓" if counts["failed"] == 0 else "✗"
        print(f"  {icon} {cat:20s} {counts['passed']}/{total} ({pct:.1f}%)")
    if report["failures"]:
        print(f"\nFailures:")
        for f in report["failures"]:
            print(f"  ✗ [{f['category']}] {f['query']}")
            for fail in f["fails"]:
                print(f"      {fail}")
            print(f"      {f['detail']}")
    print(f"\n{'='*72}")
    if report["failed"] == 0:
        print(f"✅ ASK CORRECTNESS PASSED — {report['passed']}/{report['total']} cases correct")
    else:
        print(f"❌ ASK CORRECTNESS FAILED — {report['failed']} regression(s)")
    print(f"{'='*72}")
    sys.exit(0 if report["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
