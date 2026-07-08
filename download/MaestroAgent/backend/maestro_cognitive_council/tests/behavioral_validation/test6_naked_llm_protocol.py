"""
Test 6: Naked-LLM Comparison Protocol.

Per external reviewer: 'The pilot conditions include a naked-LLM baseline,
but the methodology does not specify how the comparison is conducted.
Suggest: a fixed set of 20 executive queries sent to both Maestro and a
strong frontier LLM, with the same permitted evidence, scored on factual
accuracy, evidence traceability, uncertainty honesty, and intervention
restraint. The comparison is the pilot's success criterion for
"differentiation from naked LLM." It must be defined before the pilot begins.'

This module defines:
  1. The 20 fixed executive queries (the protocol)
  2. The 4 scoring dimensions with rubrics
  3. The comparison runner (sends queries to both Maestro and LLM)
  4. The scoring rubric (how to evaluate each dimension)

NOTE: This is a PROTOCOL definition, not an executed comparison. Running
it requires:
  - A live LLM API (OpenAI/Anthropic) configured via environment
  - Maestro running with real OEM data
  - A human scorer (or LLM-as-judge) to apply the rubric

The protocol is fixed here so it can be reviewed and agreed upon BEFORE
the pilot begins. The actual execution happens during pilot preparation.
"""
import sys
import pathlib
import json
from datetime import datetime, timezone
from typing import Any

REPO = pathlib.Path("/home/z/my-project/MaestroAgent/download/MaestroAgent/backend")
sys.path.insert(0, str(REPO))


# ════════════════════════════════════════════════════════════════════════════
# The 20 Fixed Executive Queries
# ════════════════════════════════════════════════════════════════════════════

QUERIES = [
    # ── Factual recall (5 queries) — tests evidence traceability ────────
    {"id": "Q01", "category": "factual_recall", "query": "What did we promise CustomerA?"},
    {"id": "Q02", "category": "factual_recall", "query": "When is the CustomerA renewal meeting?"},
    {"id": "Q03", "category": "factual_recall", "query": "What did Security say about the OAuth migration?"},
    {"id": "Q04", "category": "factual_recall", "query": "What's the status of the Friday deployment pattern?"},
    {"id": "Q05", "category": "factual_recall", "query": "Who is the expert on the SSO integration?"},

    # ── Chronology (5 queries) — tests temporal reasoning ───────────────
    {"id": "Q06", "category": "chronology", "query": "What changed since yesterday?"},
    {"id": "Q07", "category": "chronology", "query": "What's new with the CustomerA renewal since last week?"},
    {"id": "Q08", "category": "chronology", "query": "How did the security approval situation evolve?"},
    {"id": "Q09", "category": "chronology", "query": "What was the sequence of events leading to the pricing exception?"},
    {"id": "Q10", "category": "chronology", "query": "When did we first learn about the customer's production access requirement?"},

    # ── Disagreement (5 queries) — tests uncertainty honesty ───────────
    {"id": "Q11", "category": "disagreement", "query": "Who disagrees about the pricing strategy?"},
    {"id": "Q12", "category": "disagreement", "query": "What's the debate around the OAuth migration timing?"},
    {"id": "Q13", "category": "disagreement", "query": "Where do Engineering and Security disagree on the SSO approach?"},
    {"id": "Q14", "category": "disagreement", "query": "What are the different positions on the Friday deployment pattern?"},
    {"id": "Q15", "category": "disagreement", "query": "What does Legal think about the contract ambiguity that Sales doesn't?"},

    # ── Decision support (5 queries) — tests intervention restraint ────
    {"id": "Q16", "category": "decision_support", "query": "Should we proceed with the phased OAuth migration?"},
    {"id": "Q17", "category": "decision_support", "query": "What decision only I can make this week?"},
    {"id": "Q18", "category": "decision_support", "query": "What should I prepare for the CustomerA renewal meeting?"},
    {"id": "Q19", "category": "decision_support", "query": "Is now the right time to expand the pricing exception to BetaCo?"},
    {"id": "Q20", "category": "decision_support", "query": "What's the one thing that needs my judgment today?"},
]


# ════════════════════════════════════════════════════════════════════════════
# The 4 Scoring Dimensions
# ════════════════════════════════════════════════════════════════════════════

SCORING_RUBRIC = {
    "factual_accuracy": {
        "description": "Does the answer state facts that are true and supported by the permitted evidence?",
        "scale": [0, 1, 2, 3],
        "rubric": {
            0: "Answer contains factual errors or fabrications",
            1: "Answer is mostly wrong or unsupported",
            2: "Answer is mostly accurate with minor errors",
            3: "Answer is fully accurate and supported by evidence",
        },
    },
    "evidence_traceability": {
        "description": "Can every claim in the answer be traced back to a specific piece of evidence?",
        "scale": [0, 1, 2, 3],
        "rubric": {
            0: "No evidence cited; claims are unsupported",
            1: "Some evidence cited but gaps remain",
            2: "Most claims have evidence references",
            3: "Every claim traces to specific evidence with full citation",
        },
    },
    "uncertainty_honesty": {
        "description": "Does the answer acknowledge what is unknown, disputed, or uncertain?",
        "scale": [0, 1, 2, 3],
        "rubric": {
            0: "Answer presents everything as certain; no unknowns acknowledged",
            1: "Answer acknowledges some uncertainty but understates it",
            2: "Answer acknowledges most unknowns and disputes",
            3: "Answer explicitly states what is known, unknown, and disputed",
        },
    },
    "intervention_restraint": {
        "description": "Does the answer avoid recommending action when the evidence doesn't warrant it?",
        "scale": [0, 1, 2, 3],
        "rubric": {
            0: "Answer makes confident recommendations without evidence support",
            1: "Answer recommends action but with weak justification",
            2: "Answer is appropriately cautious but slightly over-recommends",
            3: "Answer recommends action ONLY when evidence supports it; stays silent otherwise",
        },
    },
}


# ════════════════════════════════════════════════════════════════════════════
# Comparison Protocol
# ════════════════════════════════════════════════════════════════════════════

PROTOCOL = {
    "name": "Maestro vs Naked-LLM Comparison Protocol",
    "version": "1.0",
    "query_count": 20,
    "dimensions": list(SCORING_RUBRIC.keys()),
    "scale_max": 3,
    "total_possible_per_query": 12,  # 4 dimensions × 3 max each
    "total_possible": 240,  # 20 queries × 12
    "pass_threshold": {
        "maestro_must_beat_llm_by": 20,  # Maestro must score ≥20 points higher
        "maestro_min_score": 160,  # Maestro must score ≥160/240 (67%)
        "llm_max_score_for_maestro_advantage": 180,  # If LLM scores >180, Maestro's moat is gone
    },
    "execution_requirements": [
        "Same permitted evidence provided to both Maestro and the LLM",
        "LLM is a strong frontier model (GPT-4, Claude 3.5 Sonnet, or equivalent)",
        "Scoring is blind (scorer doesn't know which answer is Maestro vs LLM)",
        "Scorer uses the rubric for each dimension independently",
        "All 20 queries are scored; no skipping",
        "Results are published in full, not aggregated away",
    ],
    "success_criterion": (
        "Maestro is pilot-ready on the differentiation dimension if: "
        "(1) Maestro's total score ≥160/240, AND "
        "(2) Maestro beats the LLM by ≥20 points, AND "
        "(3) Maestro scores higher on evidence_traceability and uncertainty_honesty "
        "(the two dimensions where Maestro's architecture should provide structural advantage)"
    ),
}


def run_protocol_definition():
    """Output the protocol definition for review. Does NOT execute the comparison."""
    print("=" * 78)
    print("TEST 6: NAKED-LLM COMPARISON PROTOCOL (Definition)")
    print("=" * 78)
    print()
    print(f"Protocol: {PROTOCOL['name']} v{PROTOCOL['version']}")
    print(f"Queries: {PROTOCOL['query_count']}")
    print(f"Dimensions: {', '.join(PROTOCOL['dimensions'])}")
    print(f"Scale: 0-3 per dimension (max {PROTOCOL['total_possible_per_query']}/query)")
    print(f"Total possible: {PROTOCOL['total_possible']}")
    print()
    print("PASS THRESHOLD:")
    for k, v in PROTOCOL["pass_threshold"].items():
        print(f"  {k}: {v}")
    print()
    print("EXECUTION REQUIREMENTS:")
    for req in PROTOCOL["execution_requirements"]:
        print(f"  • {req}")
    print()
    print("SUCCESS CRITERION:")
    print(f"  {PROTOCOL['success_criterion']}")
    print()
    print("QUERIES (20 fixed):")
    for q in QUERIES:
        print(f"  {q['id']} [{q['category']}] {q['query']}")
    print()
    print("SCORING RUBRIC:")
    for dim, rubric in SCORING_RUBRIC.items():
        print(f"  {dim}:")
        print(f"    {rubric['description']}")
        for score, desc in rubric["rubric"].items():
            print(f"      {score}: {desc}")
    print()

    # Save protocol definition
    report = {
        "test": "Test 6: Naked-LLM Comparison Protocol (Definition)",
        "defined_at": datetime.now(timezone.utc).isoformat(),
        "protocol": PROTOCOL,
        "queries": QUERIES,
        "scoring_rubric": SCORING_RUBRIC,
        "note": (
            "This is a PROTOCOL DEFINITION, not an executed comparison. "
            "Execution requires: (1) a live LLM API, (2) Maestro running with "
            "real OEM data, (3) a blind scorer. The protocol is fixed here so "
            "it can be reviewed and agreed upon BEFORE the pilot begins."
        ),
    }
    report_path = "/home/z/my-project/download/behavioral_validation/test6_naked_llm_protocol.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"Protocol definition saved: {report_path}")
    print()
    print("STATUS: Protocol defined. Execution deferred to pilot preparation.")
    return 0


if __name__ == "__main__":
    sys.exit(run_protocol_definition())
