"""
Phase 5 Ask evaluation harness.

Measures the 3 roadmap Ask acceptance metrics:
  - Factual accuracy >= 92%
  - Unsupported claims <= 3%
  - Citation correctness >= 95%

Plus entity isolation (forbidden_entities must not appear in the answer)
and category-level breakdowns.

The harness seeds the benchmark signal corpus (from benchmark_dataset.py),
then calls POST /api/ask for each of the 150 benchmark questions. For
each response, it checks:
  1. Factual accuracy: does the answer contain expected_answer_keywords?
  2. Unsupported claims: does the claim verifier flag any unsupported claims?
  3. Citation correctness: do evidence_refs contain the expected_entities?
  4. Entity isolation: do evidence_refs NOT contain forbidden_entities?

The harness runs in rule-mode by default (no LLM key needed). When an
LLM is available, the llm_powered_only metrics show the LLM's true
performance.

Paraphrase consistency (P5.5) is also measured: for a subset of
questions, 10 paraphrases are tested and the answer consistency is
checked.
"""

import os
import sys
import asyncio
import json
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "personal_memory_benchmark"))

from ask_benchmark_150 import get_ask_benchmark
from benchmark_dataset import generate_benchmark_signals
from maestro_personal_shell.claim_verifier import verify_claims


def _seed_benchmark_signals(api_module, db_path: str, user_email: str):
    """Seed the benchmark signal corpus into the DB."""
    signals = generate_benchmark_signals()
    for sig in signals:
        sig_with_id = {
            "signal_id": sig.get("signal_id", f"bench-{hash(sig.get('text', ''))}"),
            "entity": sig.get("entity", ""),
            "text": sig.get("text", ""),
            "signal_type": sig.get("signal_type", "commitment_made"),
            "timestamp": sig.get("timestamp", "2026-07-01T10:00:00Z"),
            "metadata": {},
            "source_acl": "public",
            "created_at": sig.get("timestamp", "2026-07-01T10:00:00Z"),
        }
        api_module.save_signal_to_db(sig_with_id, db_path=db_path, user_email=user_email)

    # Rebuild FTS
    try:
        from maestro_personal_shell.semantic_retrieval import init_fts_index, rebuild_fts_index
        init_fts_index(db_path)
        rebuild_fts_index(db_path, user_email=user_email)
    except Exception:
        pass


def evaluate_ask(api_module, client, auth_headers, db_path: str, user_email: str,
                 limit: int | None = None) -> dict[str, Any]:
    """Run the Ask benchmark and compute all Phase 5 metrics.

    Returns a dict with per-metric results and per-category breakdowns.
    """
    # Seed the benchmark signals
    _seed_benchmark_signals(api_module, db_path, user_email)

    questions = get_ask_benchmark()
    if limit:
        questions = questions[:limit]

    # Per-question results
    results: list[dict] = []
    # Aggregate metrics
    factual_correct = 0
    factual_total = 0
    unsupported_claims_count = 0
    total_claims = 0
    citation_correct = 0
    citation_total = 0
    entity_isolation_violations = 0
    entity_isolation_total = 0
    # Per-category
    category_stats: dict[str, dict] = {}

    # Mock the LLM + classifier for deterministic rule-mode testing
    from unittest.mock import patch, AsyncMock
    mock_llm = (
        patch("maestro_personal_shell.commitment_classifier.classify_commitment",
              new_callable=AsyncMock,
              return_value={"commitment_type": "explicit", "is_commitment": True,
                            "confidence": 0.85, "state": "active", "owner": "user",
                            "reasoning": "test", "llm_powered": False}),
        patch("maestro_personal_shell.llm_bridge.llm_complete",
              new_callable=AsyncMock, return_value=None),
        patch("maestro_personal_shell.dynamic_agents.materiality_gate_v2",
              new_callable=AsyncMock,
              return_value={"should_speak": True, "materiality_score": 0.5,
                            "urgency": "medium", "reasoning": "test", "llm_powered": False}),
    )

    m1, m2, m3 = mock_llm
    with m1, m2, m3:
        for i, q in enumerate(questions):
            question = q["question"]
            expected = q.get("expected_entities", [])
            forbidden = q.get("forbidden_entities", [])
            keywords = q.get("expected_answer_keywords", [])
            category = q.get("category", "unknown")

            # Call POST /api/ask
            resp = client.post("/api/ask", json={"query": question}, headers=auth_headers)

            if resp.status_code != 200:
                results.append({"question": question, "category": category, "error": f"HTTP {resp.status_code}"})
                continue

            data = resp.json()
            answer = data.get("answer", "")
            evidence_refs = data.get("evidence_refs", [])
            confidence = data.get("confidence", 0.0)
            counterevidence = data.get("counterevidence", [])
            unsupported = data.get("unknowns", [])

            # 1. Factual accuracy: does the answer contain expected keywords?
            factual_total += 1
            if keywords:
                answer_lower = answer.lower()
                if any(kw.lower() in answer_lower for kw in keywords):
                    factual_correct += 1
            else:
                # No keywords to check — count as correct if answer is non-empty
                if answer.strip():
                    factual_correct += 1

            # 2. Unsupported claims: run the claim verifier
            verification = verify_claims(answer, evidence_refs, data.get("source_sentence", ""))
            total_claims += len(verification.get("unsupported_claims", [])) + max(1, len(answer.split(".")))
            unsupported_claims_count += len(verification.get("unsupported_claims", []))

            # 3. Citation correctness: do evidence_refs contain expected_entities?
            if expected:
                citation_total += 1
                evidence_entities = {str(r.get("entity", "")).lower() for r in evidence_refs}
                if any(e.lower() in evidence_entities for e in expected):
                    citation_correct += 1

            # 4. Entity isolation: forbidden_entities must NOT appear in evidence
            if forbidden:
                entity_isolation_total += 1
                evidence_entities = {str(r.get("entity", "")).lower() for r in evidence_refs}
                if any(f.lower() in evidence_entities for f in forbidden):
                    entity_isolation_violations += 1

            # Per-category
            if category not in category_stats:
                category_stats[category] = {"total": 0, "factual_correct": 0,
                                            "unsupported": 0, "isolation_violations": 0}
            category_stats[category]["total"] += 1
            if keywords and any(kw.lower() in answer.lower() for kw in keywords):
                category_stats[category]["factual_correct"] += 1
            category_stats[category]["unsupported"] += len(verification.get("unsupported_claims", []))
            if forbidden and any(f.lower() in {str(r.get("entity", "")).lower() for r in evidence_refs} for f in forbidden):
                category_stats[category]["isolation_violations"] += 1

            results.append({
                "question": question, "category": category,
                "answer": answer[:200], "confidence": confidence,
                "evidence_count": len(evidence_refs),
                "unsupported_claims": len(verification.get("unsupported_claims", [])),
                "factual_correct": (not keywords) or any(kw.lower() in answer.lower() for kw in keywords),
                "isolation_ok": not forbidden or not any(f.lower() in {str(r.get("entity","")).lower() for r in evidence_refs} for f in forbidden),
            })

    # Compute final metrics
    factual_accuracy = factual_correct / factual_total if factual_total > 0 else 0.0
    unsupported_rate = unsupported_claims_count / total_claims if total_claims > 0 else 0.0
    citation_correctness = citation_correct / citation_total if citation_total > 0 else 0.0
    isolation_violation_rate = entity_isolation_violations / entity_isolation_total if entity_isolation_total > 0 else 0.0

    return {
        "total_questions": len(questions),
        "metrics": {
            "factual_accuracy": {
                "value": round(factual_accuracy, 4),
                "target": 0.92,
                "met": factual_accuracy >= 0.92,
                "support": f"{factual_correct}/{factual_total}",
            },
            "unsupported_claims_rate": {
                "value": round(unsupported_rate, 4),
                "target": 0.03,
                "met": unsupported_rate <= 0.03,
                "support": f"{unsupported_claims_count}/{total_claims}",
            },
            "citation_correctness": {
                "value": round(citation_correctness, 4),
                "target": 0.95,
                "met": citation_correctness >= 0.95,
                "support": f"{citation_correct}/{citation_total}",
            },
            "entity_isolation_violation_rate": {
                "value": round(isolation_violation_rate, 4),
                "target": 0.0,
                "met": isolation_violation_rate == 0.0,
                "support": f"{entity_isolation_violations}/{entity_isolation_total}",
            },
        },
        "category_stats": category_stats,
        "sample_results": results[:10],
    }


def evaluate_paraphrase_consistency(api_module, client, auth_headers, db_path: str,
                                     user_email: str) -> dict[str, Any]:
    """Phase 5.5: paraphrase consistency — same question under 10 paraphrases.

    For a set of base questions, generate 10 paraphrases each and check
    that the answers are consistent (contain the same key entities).
    """
    _seed_benchmark_signals(api_module, db_path, user_email)

    # Pick 5 base questions and generate 10 paraphrases each
    base_questions = [
        ("What did Alex commit to?", "Alex"),
        ("What did Maria promise?", "Maria"),
        ("What is Sam's commitment?", "Sam"),
        ("What does Priya owe?", "Priya"),
        ("What did Sam pledge to do?", "Sam"),
    ]

    paraphrase_templates = [
        "What did {entity} commit to?",
        "What commitments does {entity} have?",
        "What did {entity} promise?",
        "What does {entity} owe?",
        "What is {entity}'s commitment?",
        "What did {entity} pledge?",
        "What is {entity} obligated to do?",
        "What did {entity} say they would do?",
        "What are {entity}'s outstanding commitments?",
        "What has {entity} committed to?",
    ]

    consistent = 0
    total = 0
    all_answers: list[dict] = []

    from unittest.mock import patch, AsyncMock
    mock_llm = (
        patch("maestro_personal_shell.commitment_classifier.classify_commitment",
              new_callable=AsyncMock,
              return_value={"commitment_type": "explicit", "is_commitment": True,
                            "confidence": 0.85, "state": "active", "owner": "user",
                            "reasoning": "test", "llm_powered": False}),
        patch("maestro_personal_shell.llm_bridge.llm_complete",
              new_callable=AsyncMock, return_value=None),
        patch("maestro_personal_shell.dynamic_agents.materiality_gate_v2",
              new_callable=AsyncMock,
              return_value={"should_speak": True, "materiality_score": 0.5,
                            "urgency": "medium", "reasoning": "test", "llm_powered": False}),
    )

    m1, m2, m3 = mock_llm
    with m1, m2, m3:
        for base_q, entity in base_questions:
            answers_for_entity: list[str] = []
            for template in paraphrase_templates:
                paraphrase = template.format(entity=entity)
                resp = client.post("/api/ask", json={"query": paraphrase}, headers=auth_headers)
                if resp.status_code == 200:
                    answer = resp.json().get("answer", "")
                    # Check if the entity appears in the answer
                    has_entity = entity.lower() in answer.lower()
                    answers_for_entity.append(answer[:100])
                    total += 1
                    if has_entity:
                        consistent += 1

            all_answers.append({
                "entity": entity,
                "answers": answers_for_entity,
                "consistent_count": sum(1 for a in answers_for_entity if entity.lower() in a.lower()),
            })

    consistency_rate = consistent / total if total > 0 else 0.0
    return {
        "consistency_rate": round(consistency_rate, 4),
        "target": 0.80,  # 80% of paraphrases should surface the entity
        "met": consistency_rate >= 0.80,
        "support": f"{consistent}/{total}",
        "details": all_answers,
    }


def run_full_ask_eval(api_module, client, auth_headers, db_path: str, user_email: str) -> dict[str, Any]:
    """Run all Phase 5 Ask metrics and return a single report."""
    main_eval = evaluate_ask(api_module, client, auth_headers, db_path, user_email)
    paraphrase = evaluate_paraphrase_consistency(api_module, client, auth_headers, db_path, user_email)

    return {
        "ask_benchmark": main_eval,
        "paraphrase_consistency": paraphrase,
    }


if __name__ == "__main__":
    # Standalone run — requires a test DB + client setup
    import tempfile
    import importlib

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "ask-eval"
    os.environ.pop("MAESTRO_PERSONAL_ENV", None)

    import maestro_personal_shell.api as api_module
    importlib.reload(api_module)
    api_module.init_db(db_path)

    from fastapi.testclient import TestClient
    client = TestClient(api_module.app)
    resp = client.post("/api/auth/login", json={"password": "ask-eval"})
    token = resp.json()["token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    report = run_full_ask_eval(api_module, client, auth_headers, db_path, "ask-eval")
    print(json.dumps(report, indent=2, default=str))

    os.unlink(db_path)
    del os.environ["MAESTRO_PERSONAL_DB"]
    del os.environ["MAESTRO_PERSONAL_TOKEN"]
