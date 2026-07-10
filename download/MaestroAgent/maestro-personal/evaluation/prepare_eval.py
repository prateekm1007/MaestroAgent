"""
Phase 5 Prepare evaluation harness.

Measures the roadmap Prepare acceptance metric:
  - Prepare usefulness >= 4.3/5

Plus structural metrics:
  - Bullet count: max 3-5 bullets (penalize >5 or <3)
  - Irrelevant facts penalty: penalize briefs that include irrelevant_true_facts
  - Expected keyword coverage: does the brief contain expected_keywords?

The usefulness score is a composite (0-5 scale):
  - 2.0 points: relevant commitments surfaced (expected keywords present)
  - 1.0 point: correct bullet count (3-5)
  - 1.0 point: no irrelevant true facts
  - 0.5 point: stale/at-risk items flagged
  - 0.5 point: disputes/objections mentioned when relevant

Target: >= 4.3/5
"""

import os
import sys
import json
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from prepare_benchmark_50 import get_prepare_benchmark


def _seed_meeting_signals(api_module, db_path: str, user_email: str, meeting: dict):
    """Seed the meeting's signals into the DB."""
    for sig in meeting.get("signals", []):
        sig_with_id = {
            "signal_id": f"{meeting['meeting_id']}-sig-{hash(sig.get('text', ''))}",
            "entity": sig.get("entity", meeting.get("entity", "")),
            "text": sig.get("text", ""),
            "signal_type": sig.get("signal_type", "commitment_made"),
            "timestamp": sig.get("timestamp", "2026-07-10T10:00:00Z"),
            "metadata": {},
            "source_acl": "public",
            "created_at": sig.get("timestamp", "2026-07-10T10:00:00Z"),
        }
        api_module.save_signal_to_db(sig_with_id, db_path=db_path, user_email=user_email)

    try:
        from maestro_personal_shell.semantic_retrieval import init_fts_index, rebuild_fts_index
        init_fts_index(db_path)
        rebuild_fts_index(db_path, user_email=user_email)
    except Exception:
        pass


def _score_brief(
    brief_text: str,
    prep_points: list[str],
    meeting: dict,
) -> dict[str, Any]:
    """Score a Prepare brief against the reference (0-5 scale).

    Returns:
    {
        "usefulness_score": float,  # 0.0-5.0
        "bullet_count": int,
        "bullet_count_ok": bool,  # 3-5
        "keyword_coverage": float,  # 0.0-1.0
        "irrelevant_facts_present": bool,
        "stale_flagged": bool,
        "disputes_flagged": bool,
        "breakdown": dict,
    }
    """
    brief_lower = brief_text.lower()
    all_text = brief_lower + " " + " ".join(p.lower() for p in prep_points)

    # 1. Keyword coverage (2.0 points max)
    expected_keywords = meeting.get("expected_keywords", [])
    if expected_keywords:
        covered = sum(1 for kw in expected_keywords if kw.lower() in all_text)
        coverage = covered / len(expected_keywords)
        keyword_points = 2.0 * coverage
    else:
        coverage = 1.0
        keyword_points = 2.0

    # 2. Bullet count (1.0 point max)
    bullet_count = len(prep_points) if prep_points else brief_text.count("\n") + 1
    bullet_ok = 3 <= bullet_count <= 5
    bullet_points = 1.0 if bullet_ok else (0.5 if 1 <= bullet_count <= 7 else 0.0)

    # 3. No irrelevant facts (1.0 point max)
    irrelevant_facts = meeting.get("irrelevant_true_facts", [])
    irrelevant_present = False
    for fact in irrelevant_facts:
        # Check if any significant word from the irrelevant fact appears
        fact_words = [w.lower() for w in fact.split() if len(w) > 4]
        if fact_words and any(w in all_text for w in fact_words):
            irrelevant_present = True
            break
    irrelevant_points = 0.0 if irrelevant_present else 1.0

    # 4. Stale/at-risk flagged (0.5 points)
    stale_flagged = any(kw in all_text for kw in ["stale", "overdue", "at_risk", "at risk", "behind"])
    stale_points = 0.5 if stale_flagged else 0.0

    # 5. Disputes mentioned when relevant (0.5 points)
    disputes_flagged = any(kw in all_text for kw in ["dispute", "disputed", "objection", "missing"])
    meeting_has_dispute = any("dispute" in s.get("text", "").lower() or
                              "objection" in s.get("text", "").lower() or
                              "missing" in s.get("text", "").lower()
                              for s in meeting.get("signals", []))
    dispute_points = 0.5 if (meeting_has_dispute and disputes_flagged) else (0.25 if disputes_flagged else 0.0)

    total = keyword_points + bullet_points + irrelevant_points + stale_points + dispute_points
    total = min(5.0, total)

    return {
        "usefulness_score": round(total, 2),
        "bullet_count": bullet_count,
        "bullet_count_ok": bullet_ok,
        "keyword_coverage": round(coverage, 2),
        "irrelevant_facts_present": irrelevant_present,
        "stale_flagged": stale_flagged,
        "disputes_flagged": disputes_flagged,
        "breakdown": {
            "keyword": round(keyword_points, 2),
            "bullets": round(bullet_points, 2),
            "irrelevant": round(irrelevant_points, 2),
            "stale": round(stale_points, 2),
            "disputes": round(dispute_points, 2),
        },
    }


def evaluate_prepare(api_module, client, auth_headers, db_path: str, user_email: str,
                     limit: int | None = None) -> dict[str, Any]:
    """Run the Prepare benchmark and compute usefulness scores.

    For each meeting:
      1. Seed the meeting's signals.
      2. Call GET /api/prepare with the meeting's entity.
      3. Score the brief against the reference.
    """
    meetings = get_prepare_benchmark()
    if limit:
        meetings = meetings[:limit]

    results: list[dict] = []
    total_score = 0.0
    scored_count = 0
    bullet_ok_count = 0
    irrelevant_penalty_count = 0

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
        for meeting in meetings:
            # Seed signals
            _seed_meeting_signals(api_module, db_path, user_email, meeting)

            # Call GET /api/prepare
            entity = meeting["entity"]
            resp = client.get("/api/prepare", params={"entity": entity},
                              headers=auth_headers)

            if resp.status_code != 200:
                results.append({"meeting_id": meeting["meeting_id"], "error": f"HTTP {resp.status_code}"})
                continue

            data = resp.json()
            # The Prepare endpoint returns a LIST of PrepareResponse items.
            # Combine all items into a single brief for scoring.
            if isinstance(data, list):
                brief_parts = []
                prep_points = []
                for item in data:
                    brief_parts.append(item.get("meeting_context", ""))
                    brief_parts.append(item.get("the_forgotten", ""))
                    brief_parts.append(item.get("the_open_question", ""))
                    brief_parts.append(item.get("the_contradiction", ""))
                    prep_points.extend(item.get("prep_points", []))
                brief_text = " ".join(p for p in brief_parts if p)
            else:
                brief_text = data.get("meeting_context", "") + " " + data.get("the_forgotten", "") + \
                            " " + data.get("the_open_question", "") + " " + data.get("the_contradiction", "")
                prep_points = data.get("prep_points", [])

            score = _score_brief(brief_text, prep_points, meeting)
            total_score += score["usefulness_score"]
            scored_count += 1
            if score["bullet_count_ok"]:
                bullet_ok_count += 1
            if score["irrelevant_facts_present"]:
                irrelevant_penalty_count += 1

            results.append({
                "meeting_id": meeting["meeting_id"],
                "entity": entity,
                "score": score["usefulness_score"],
                "bullet_count": score["bullet_count"],
                "keyword_coverage": score["keyword_coverage"],
                "irrelevant_present": score["irrelevant_facts_present"],
            })

    avg_score = total_score / scored_count if scored_count > 0 else 0.0
    return {
        "total_meetings": len(meetings),
        "scored": scored_count,
        "metrics": {
            "usefulness_score": {
                "value": round(avg_score, 2),
                "target": 4.3,
                "met": avg_score >= 4.3,
                "support": f"{total_score:.1f}/{scored_count}",
            },
            "bullet_count_ok_rate": {
                "value": round(bullet_ok_count / scored_count, 4) if scored_count > 0 else 0.0,
                "target": 0.90,
                "met": (bullet_ok_count / scored_count if scored_count > 0 else 0) >= 0.90,
                "support": f"{bullet_ok_count}/{scored_count}",
            },
            "irrelevant_penalty_rate": {
                "value": round(irrelevant_penalty_count / scored_count, 4) if scored_count > 0 else 0.0,
                "target": 0.10,
                "met": (irrelevant_penalty_count / scored_count if scored_count > 0 else 0) <= 0.10,
                "support": f"{irrelevant_penalty_count}/{scored_count}",
            },
        },
        "sample_results": results[:10],
    }


if __name__ == "__main__":
    import tempfile
    import importlib

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "prep-eval"
    os.environ.pop("MAESTRO_PERSONAL_ENV", None)

    import maestro_personal_shell.api as api_module
    importlib.reload(api_module)
    api_module.init_db(db_path)

    from fastapi.testclient import TestClient
    client = TestClient(api_module.app)
    resp = client.post("/api/auth/login", json={"password": "prep-eval"})
    token = resp.json()["token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    report = evaluate_prepare(api_module, client, auth_headers, db_path, "prep-eval")
    print(json.dumps(report, indent=2, default=str))

    os.unlink(db_path)
    del os.environ["MAESTRO_PERSONAL_DB"]
    del os.environ["MAESTRO_PERSONAL_TOKEN"]
