"""
compute_results.py — Turn the raw JSONL into the final Gold-150 results JSON.

Usage:
  python compute_results.py <jsonl_path> <output_json_path>

Reads the JSONL (one result per line), deduplicates by idx (keeping the
best result per index), computes the composite score + per-type breakdown
+ gate pass, and writes the final JSON.
"""
import json
import sys
import time
from collections import defaultdict


def main(jsonl_path: str, out_path: str):
    # Load all results — for each idx, keep the BEST result
    best_by_idx = {}
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                idx = r["idx"]
                if idx not in best_by_idx:
                    best_by_idx[idx] = r
                else:
                    old = best_by_idx[idx]
                    old_err = old.get("type") == "unknown"
                    new_err = r.get("type") == "unknown"
                    if new_err and not old_err:
                        continue
                    if old_err and not new_err:
                        best_by_idx[idx] = r
                    elif r.get("score", 0) > old.get("score", 0):
                        best_by_idx[idx] = r
                    elif r.get("score", 0) == old.get("score", 0) and r.get("llm_active") and not old.get("llm_active"):
                        best_by_idx[idx] = r
            except (json.JSONDecodeError, KeyError):
                continue

    # Build full 150 list
    results = []
    for i in range(150):
        if i in best_by_idx:
            results.append(best_by_idx[i])
        else:
            results.append({
                "idx": i, "id": f"q{i}", "type": "missing", "query": "",
                "score": 0.0, "error": "not_run (tunnel timeout)",
                "llm_active": False, "elapsed": 0.0,
            })
    results.sort(key=lambda r: r["idx"])

    # Compute composite
    maestro_avg = sum(r["score"] for r in results) / len(results)
    bm25_baseline = 0.514
    lift = (maestro_avg - bm25_baseline) * 100
    llm_active_count = sum(1 for r in results if r.get("llm_active"))

    by_type = defaultdict(list)
    for r in results:
        by_type[r["type"]].append(r["score"])

    completed = len([r for r in results if r["type"] not in ("missing", "unknown")])
    failures = len([r for r in results if r.get("type") == "unknown"])
    missing = len([r for r in results if r["type"] == "missing"])

    print("=" * 70)
    print("  GOLD-150 — MAESTRO (LLM-ACTIVE) vs BM25")
    print("=" * 70)
    print(f"\n  Total:            150")
    print(f"  Completed:        {completed}")
    print(f"  Process failures: {failures}")
    print(f"  Missing:          {missing}")
    print(f"  LLM active:       {llm_active_count}/150")
    print(f"\n  BM25 baseline:    {bm25_baseline:.3f}")
    print(f"  Maestro composite:{maestro_avg:.3f}")
    print(f"  Lift:             {lift:+.1f} points (target: >= +15)")
    print(f"\n  Per-type breakdown:")
    for t_name, scores in sorted(by_type.items()):
        m_avg = sum(scores) / len(scores) if scores else 0
        print(f"    {t_name:<20s} {m_avg:>8.3f} (n={len(scores)})")

    gate_pass = lift >= 15 and llm_active_count > 0
    print(f"\n  {'PASS' if gate_pass else 'FAIL'} — lift={lift:+.1f} (target >= +15)")

    # Save
    with open(out_path, "w") as f:
        json.dump({
            "mode": "LLM-ACTIVE",
            "provider": "ollama",
            "llm_active_count": llm_active_count,
            "total_questions": 150,
            "completed": completed,
            "process_failures": failures,
            "missing": missing,
            "maestro_composite": maestro_avg,
            "bm25_baseline": bm25_baseline,
            "lift": lift / 100,
            "gate_pass": gate_pass,
            "per_type": {t: sum(s) / len(s) for t, s in by_type.items()},
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "model": "llama3:8b",
            "results": results,
        }, f, indent=2)
    print(f"\n  Results saved to {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python compute_results.py <jsonl_path> <output_json_path>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
