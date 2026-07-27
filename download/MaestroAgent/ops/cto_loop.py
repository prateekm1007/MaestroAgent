#!/usr/bin/env python3
"""CTO ↔ Kimi K3 Loop — Engineering Orchestrator (P46-enforced).

This script is the CTO's interface to Kimi K3 (engineering lead) via OpenRouter.
It enforces P46 (verify the served instrument, not the requested one) by reading
`response.model` on every call and FAILING LOUDLY if the served model is not
`moonshotai/kimi-k3` — never relabeling a fallback as Kimi K3.

Usage:
    export OPENROUTER_API_KEY="sk-or-..."
    python ops/cto_loop.py --task <task_file.md> --out <output_dir>

The script:
  1. Reads the task brief from --task (a markdown file with the engineering directive)
  2. Calls OpenRouter with model="moonshotai/kimi-k3"
  3. Verifies response.model == "moonshotai/kimi-k3" (P46 enforcement)
  4. Saves the full response + generation ID to --out
  5. Logs the served-model verification to /home/z/my-project/worklog.md

If the served model is NOT kimi-k3 (e.g., fallback to Gemma on timeout), the
script exits non-zero and writes a P46 VIOLATION report. The CTO does NOT
relabel the work — it is honestly marked "NOT DONE BY KIMI K3" and the task
is retried with a smaller, decomposed prompt per P47 (structure delegation
to the model's latency budget).

Reference: ENTROPY_RECOVERY.md P46, P47; FORBIDDEN_ACTIONS.md FA13.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# ---- Constants (P46 enforcement) ----
EXPECTED_MODEL = "moonshotai/kimi-k3"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
WORKLOG_PATH = Path("/home/z/my-project/worklog.md")

# Kimi K3 is a deep-reasoning model with high latency on long prompts.
# Per P47, we keep the max_tokens budget bounded and decompose large tasks.
# OpenRouter's own timeout is ~300s for non-streaming; we set 290s client-side
# to fail before OpenRouter's silent fallback kicks in.
DEFAULT_TIMEOUT_S = 290
DEFAULT_MAX_TOKENS = 8000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_task(task_path: Path) -> str:
    if not task_path.exists():
        sys.exit(f"cto_loop: task file not found: {task_path}")
    return task_path.read_text(encoding="utf-8")


def _call_openrouter(
    api_key: str,
    task_brief: str,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> dict:
    """Call OpenRouter with model=moonshotai/kimi-k3. Returns the raw JSON response.

    Raises on any HTTP error, timeout, or non-kimi-k3 served model.
    """
    system_prompt = (
        "You are Kimi K3, the engineering lead on MaestroAgent. "
        "You have read ENTROPY_RECOVERY.md (P1-P87), FORBIDDEN_ACTIONS.md "
        "(FA1-FA34), GOVERNANCE.md, and STATE.md. You write production-grade "
        "Python and TypeScript. You never fabricate verification — you say "
        "'UNVERIFIED — reasoning only' instead of ✓. You cite the P-number "
        "principle each fix satisfies. You write tests for every new code path."
    )

    payload = {
        "model": EXPECTED_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task_brief},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.2,  # engineering work — low temperature
    }

    req = Request(
        OPENROUTER_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/prateekm1007/MaestroAgent",
            "X-Title": "MaestroAgent CTO Loop",
        },
        method="POST",
    )

    try:
        with urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except HTTPError as e:
        sys.exit(
            f"cto_loop: OpenRouter HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}"
        )
    except URLError as e:
        sys.exit(f"cto_loop: network error calling OpenRouter: {e}")
    except TimeoutError:
        sys.exit(
            f"cto_loop: OpenRouter timed out after {timeout_s}s. "
            f"Per P47, decompose the task into smaller prompts and retry."
        )


def _verify_served_model(response: dict) -> str:
    """P46 enforcement: read response.model, assert it equals kimi-k3.

    Returns the served model name. Exits non-zero on mismatch.
    """
    served_model = response.get("model", "")
    if not served_model:
        sys.exit(
            "cto_loop: P46 VIOLATION — response.model field is missing or empty. "
            "Cannot verify the served instrument. Refusing to proceed."
        )
    # OpenRouter sometimes prefixes with the provider; normalize for comparison.
    served_norm = served_model.lower()
    expected_norm = EXPECTED_MODEL.lower()
    if served_norm != expected_norm and not served_norm.endswith(expected_norm):
        sys.exit(
            f"cto_loop: P46 VIOLATION — requested {EXPECTED_MODEL} but OpenRouter "
            f"served {served_model}. The work below was NOT done by Kimi K3. "
            f"Per FA13, refusing to relabel. Per P47, decompose the task and retry."
        )
    return served_model


def _save_response(response: dict, out_dir: Path, task_name: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"{task_name}_{ts}.json"
    out_path.write_text(json.dumps(response, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


def _log_to_worklog(
    task_name: str,
    task_path: Path,
    served_model: str,
    generation_id: str | None,
    out_path: Path,
    latency_s: float,
) -> None:
    entry = f"""
---
Task ID: cto-loop-{task_name}
Agent: CTO Loop (orchestrator)
Task: Dispatched engineering task to Kimi K3 via OpenRouter. Task brief: {task_path}

Work Log:
- Read task brief from {task_path} ({task_path.stat().st_size} bytes)
- Called OpenRouter with model={EXPECTED_MODEL}
- P46 verification: response.model = {served_model} ✓ matches expected
- Generation ID: {generation_id or "(not provided by OpenRouter)"}
- Latency: {latency_s:.1f}s
- Saved full response to {out_path}

Stage Summary:
- Engineering task dispatched and response captured.
- P46 (verify served instrument) enforced: served model verified as Kimi K3.
- Generation ID recorded for external cross-check on OpenRouter dashboard.
- CTO will review the response and apply the proposed changes to the codebase.
"""
    with WORKLOG_PATH.open("a", encoding="utf-8") as f:
        f.write(entry)


def main() -> int:
    parser = argparse.ArgumentParser(description="CTO ↔ Kimi K3 Loop (P46-enforced)")
    parser.add_argument(
        "--task",
        type=Path,
        required=True,
        help="Path to a markdown file containing the engineering task brief.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("/home/z/my-project/scripts/cto_loop_out"),
        help="Directory to save the full OpenRouter response JSON.",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Task name (used in output filename). Defaults to the task file stem.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_S,
        help=f"OpenRouter call timeout in seconds (default {DEFAULT_TIMEOUT_S}).",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help=f"Max tokens for the response (default {DEFAULT_MAX_TOKENS}).",
    )
    args = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        sys.exit(
            "cto_loop: OPENROUTER_API_KEY environment variable is not set. "
            "The CTO cannot dispatch tasks to Kimi K3 without it. "
            "Request the key from the user, then re-run."
        )

    task_brief = _read_task(args.task)
    task_name = args.name or args.task.stem

    print(f"cto_loop: dispatching task '{task_name}' to {EXPECTED_MODEL}")
    print(f"cto_loop: task brief size = {len(task_brief)} chars")
    print(f"cto_loop: timeout = {args.timeout}s, max_tokens = {args.max_tokens}")

    t0 = time.monotonic()
    response = _call_openrouter(
        api_key,
        task_brief,
        timeout_s=args.timeout,
        max_tokens=args.max_tokens,
    )
    latency_s = time.monotonic() - t0

    served_model = _verify_served_model(response)
    generation_id = response.get("id")

    out_path = _save_response(response, args.out, task_name)
    _log_to_worklog(task_name, args.task, served_model, generation_id, out_path, latency_s)

    # Print the assistant's content to stdout for the CTO to review
    choices = response.get("choices", [])
    if choices:
        content = choices[0].get("message", {}).get("content", "")
        print("\n" + "=" * 78)
        print(f"KIMI K3 RESPONSE (served_model={served_model}, gen_id={generation_id})")
        print("=" * 78)
        print(content)
        print("=" * 78)
        print(f"Full response saved to: {out_path}")
        print(f"P46 verification: ✓ served model is {EXPECTED_MODEL}")
        print(f"Latency: {latency_s:.1f}s")
    else:
        sys.exit("cto_loop: response had no choices. Full response saved to: " + str(out_path))

    return 0


if __name__ == "__main__":
    sys.exit(main())
