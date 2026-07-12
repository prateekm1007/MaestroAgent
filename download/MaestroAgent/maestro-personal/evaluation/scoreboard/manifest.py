"""
Evaluation manifest format — every scoring run produces a manifest with
corpus hash, code SHA, model config, raw outputs, and timings.

Phase 0 of Roadmap to 9/10:
  'Create evaluation/manifests/<run-id>.json containing:
   corpus hash, code SHA, model/provider configuration, prompts and
   subsystem switches, machine characteristics, raw outputs and timings.'

Usage:
    from evaluation.scoreboard.manifest import create_manifest, save_manifest
    manifest = create_manifest(corpus_signals, questions, results)
    save_manifest(manifest, "evaluation/manifests/")
"""
import hashlib
import json
import os
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def _git_sha():
    """Get current git commit SHA."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _git_branch():
    """Get current git branch."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _corpus_hash(signals, questions):
    """Compute a deterministic hash of the corpus + questions."""
    data = json.dumps({"signals": signals, "questions": questions}, sort_keys=True)
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def create_manifest(
    corpus_signals: list,
    questions: list,
    results: list,
    system_name: str = "maestro",
    extra_config: dict | None = None,
) -> dict:
    """Create an evaluation manifest for a scoring run.

    Per Phase 0: captures corpus hash, code SHA, model config, machine
    characteristics, raw outputs, and timings so any run is reproducible.
    """
    run_id = f"{system_name}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{str(uuid4())[:8]}"
    manifest = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system": system_name,
        "code": {
            "git_sha": _git_sha(),
            "git_branch": _git_branch(),
        },
        "corpus": {
            "hash": _corpus_hash(corpus_signals, questions),
            "signal_count": len(corpus_signals),
            "question_count": len(questions),
        },
        "model": {
            "ollama_host": os.environ.get("OLLAMA_HOST", "none"),
            "ollama_model": os.environ.get("OLLAMA_MODEL", "none"),
            "llm_active": any(r.get("llm") for r in results) if results else False,
        },
        "machine": {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
        "config": extra_config or {},
        "results": results,
        "summary": {
            "composite_score": sum(r.get("m", r.get("maestro_score", 0)) for r in results) / len(results) if results else 0,
            "llm_active_count": sum(1 for r in results if r.get("llm")),
            "total_questions": len(results),
            "avg_latency_s": sum(r.get("t", r.get("elapsed", 0)) for r in results) / len(results) if results else 0,
        },
    }
    return manifest


def save_manifest(manifest: dict, output_dir: str = "evaluation/manifests/") -> str:
    """Save manifest to <output_dir>/<run_id>.json. Returns the path."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    path = Path(output_dir) / f"{manifest['run_id']}.json"
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2, default=str)
    return str(path)


if __name__ == "__main__":
    # Quick self-test
    test_signals = [{"entity": "Test", "text": "test signal", "signal_type": "reported_statement"}]
    test_questions = [{"q": "test?", "expected_type": "general"}]
    test_results = [{"type": "general", "m": 1.0, "llm": True, "t": 1.5}]
    m = create_manifest(test_signals, test_questions, test_results)
    print(f"Run ID: {m['run_id']}")
    print(f"Corpus hash: {m['corpus']['hash']}")
    print(f"Git SHA: {m['code']['git_sha']}")
    print(f"Composite: {m['summary']['composite_score']:.2f}")
    print("Manifest format OK")
