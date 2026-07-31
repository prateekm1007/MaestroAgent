#!/usr/bin/env python3
"""CTO <-> Engineer Loop -- Multi-model OpenRouter orchestrator.

This is the second-generation loop. The first generation (ops/cto_loop.py)
hard-pinned to moonshotai/kimi-k3, which was too slow for the iterative
audit-driven workflow. This version supports a small set of fast, capable
engineering models on OpenRouter, with strict per-call model verification
(P46: verify the served instrument, not the requested one).

ALLOWED ENGINEERS (per user direction):
    - qwen/qwen3-coder                  (code-focused, fast)
    - deepseek/deepseek-chat-v3.1:free  (drafts, general reasoning)
    - tencent/hunyuan-a13b              (governance-grade reasoning)

NO GEMINI. This is a hard rule from the user. Gemini models are not in
ALLOWED_ENGINEERS and the script refuses to dispatch to them. This is
enforced in two places: (1) the --engineer flag is validated against
ALLOWED_ENGINEERS, and (2) the served-model check rejects any response
whose model field contains "gemini".

GOVERNANCE PRIMER:
Every task dispatched to an engineer is prefixed with a governance primer
drawn from the project's anti-entropy files:
    - The Prime Directive (reduce entropy in the trust surface)
    - The No-Gaming Rule (do not narrow a metric to silence a red)
    - The Trace-Before-Fix Rule (capture the failure before patching)
    - The Honest-Boundary Rule (state the boundary, do not blur it)
    - P1 (a claim is not true until executed)
    - P46 (verify the served instrument, not the requested one)
    - P54 (fix the data the user sees, not just the path)
    - FA13 (do not relabel a fallback as the requested instrument)

The engineer is told to cite the P-number each fix satisfies and to write
"UNVERIFIED -- reasoning only" instead of a checkmark it cannot back with
execution evidence in the same turn.

P46 ENFORCEMENT:
After every OpenRouter call, response.model is read and compared against
the requested engineer. If OpenRouter silently fell back to a different
model (which it does on timeouts and quota errors), the script:
    1. Writes a P46 VIOLATION block to stdout and the worklog.
    2. Refuses to relabel the work as if it came from the requested engineer.
    3. Exits non-zero so the caller can retry with a smaller prompt (P47).

USAGE:
    export OPENROUTER_API_KEY="sk-or-..."
    python cto_loop.py \\
        --task /path/to/task.md \\
        --engineer qwen/qwen3-coder \\
        --out /home/z/my-project/scripts/cto_loop/out

OUTPUT:
    - A timestamped JSON file under --out containing the full OpenRouter
      response (choices, model, id, usage).
    - A markdown summary under --out with the assistant content + the
      governance read receipt + the served-model verification.
    - An appended entry in /home/z/my-project/worklog.md.

REFERENCE FILES:
    - ENTROPY_RECOVERY.md  (P1-P87)
    - governance/FORBIDDEN_ACTIONS.md  (FA1-FA34)
    - governance/ANTI_ENTROPY.md  (Prime Directive, No-Gaming, Trace-Before-Fix)
    - GOVERNANCE_LOOP.md  (mutual read protocol)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
WORKLOG_PATH = Path("/home/z/my-project/worklog.md")

# Hard allow-list. NO GEMINI. Adding a model here is the ONLY way to
# dispatch a task to it; the --engineer flag is validated against this set.
ALLOWED_ENGINEERS: dict[str, dict] = {
    "qwen/qwen3-coder": {
        "label": "Qwen 3 Coder",
        "strength": "code generation, refactoring, test writing",
        "max_tokens": 8000,
        "timeout_s": 180,
        "temperature": 0.2,
    },
    "deepseek/deepseek-chat-v3.1:free": {
        "label": "DeepSeek Chat V3.1 (free tier)",
        "strength": "draft generation, general reasoning, summarization",
        "max_tokens": 8000,
        "timeout_s": 180,
        "temperature": 0.3,
    },
    "tencent/hunyuan-a13b": {
        "label": "Tencent Hunyuan A13B",
        "strength": "governance-grade reasoning, principle application",
        "max_tokens": 6000,
        "timeout_s": 240,
        "temperature": 0.2,
    },
}

# Names that must NEVER be served. If response.model matches any of these
# (case-insensitive substring), the script refuses to relabel and exits.
FORBIDDEN_MODEL_SUBSTRINGS = ("gemini",)

# The governance primer prepended to every task brief. Keep it short -- the
# engineer's context window is finite and the task itself is the point.
GOVERNANCE_PRIMER = """\
You are an engineering lead on MaestroAgent. Before writing any code or
making any claim, you MUST apply the project's anti-entropy principles.
Read each one and apply it to the task below.

THE PRIME DIRECTIVE: The swarm exists to reduce entropy in the product's
trust surface, never to increase it. If an action would make a metric
read greener without making the product genuinely greener, it is forbidden.

THE NO-GAMING RULE: Do not lower a threshold to silence a red. Do not
narrow a metric's scope to exclude failures. Do not seed synthetic data
and present it as real. Do not claim a capability exists when it's only
wired but not verified.

THE TRACE-BEFORE-FIX RULE: Before fixing a bug, capture the traceback /
error output / observed behavior. Trace the code path to the root cause.
Inspect the actual data before labeling it. Fix the root cause, not the
symptom.

THE HONEST-BOUNDARY RULE: When you hit a limit you cannot cross via API,
state the boundary precisely, diagnose as far as you CAN go, and report
the exact remaining step -- not a vague "please investigate."

P1: A claim is not true until it has been executed. Never write
"[VERIFIED]" next to anything you have not personally executed. If
you cannot run it, write "UNVERIFIED -- reasoning only" instead.

P46: Verify the served instrument, not the requested one. If you are
asked to use a specific model and a fallback is served, you MUST report
the fallback honestly. Never relabel a fallback as the requested model.

P54 (the master principle): Fix the data the user sees, not just the
path. A fix applied to the code path but not to the corpus the user
actually reads is NOT A FIX.

FA13: Do not relabel a fallback as the requested instrument.

Cite the P-number each fix satisfies. Write tests for every new code
path. Prefer small, decomposed changes over large rewrites (P47).

---
TASK BRIEF FOLLOWS.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_task(task_path: Path) -> str:
    if not task_path.exists():
        sys.exit(f"cto_loop: task file not found: {task_path}")
    return task_path.read_text(encoding="utf-8")


def _validate_engineer(engineer: str) -> dict:
    """Validate the --engineer flag against ALLOWED_ENGINEERS.

    Refuses unknown models and any Gemini variant, even if the user types
    one explicitly. This is the first of two enforcement points for the
    NO-GEMINI rule.
    """
    if engineer not in ALLOWED_ENGINEERS:
        sys.exit(
            f"cto_loop: engineer '{engineer}' is not in the allow-list.\n"
            f"Allowed engineers:\n"
            + "\n".join(
                f"  - {k}  ({v['label']}: {v['strength']})"
                for k, v in ALLOWED_ENGINEERS.items()
            )
            + "\n\nNO GEMINI is permitted. This is a hard rule."
        )
    forbidden_hit = next(
        (s for s in FORBIDDEN_MODEL_SUBSTRINGS if s in engineer.lower()), None
    )
    if forbidden_hit:
        sys.exit(
            f"cto_loop: REFUSING to dispatch to '{engineer}'. "
            f"The substring '{forbidden_hit}' is on the forbidden list. "
            f"NO GEMINI is permitted."
        )
    return ALLOWED_ENGINEERS[engineer]


def _call_openrouter(
    api_key: str,
    engineer: str,
    task_brief: str,
    timeout_s: int,
    max_tokens: int,
    temperature: float,
) -> dict:
    """Call OpenRouter with the given engineer model. Returns raw JSON.

    Raises SystemExit on HTTP error, timeout, or network failure so the
    caller can decompose the task per P47 instead of silently retrying.
    """
    system_prompt = (
        f"You are {engineer}, an engineering lead on MaestroAgent. "
        "You write production-grade Python and TypeScript. You never "
        "fabricate verification -- you say 'UNVERIFIED -- reasoning "
        "only' instead of a checkmark. You cite the P-number principle "
        "each fix satisfies. You write tests for every new code path."
    )

    payload = {
        "model": engineer,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": GOVERNANCE_PRIMER + task_brief},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
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
            f"cto_loop: OpenRouter HTTP {e.code}: "
            f"{e.read().decode('utf-8', errors='replace')}"
        )
    except URLError as e:
        sys.exit(f"cto_loop: network error calling OpenRouter: {e}")
    except TimeoutError:
        sys.exit(
            f"cto_loop: OpenRouter timed out after {timeout_s}s. "
            f"Per P47, decompose the task into smaller prompts and retry."
        )


def _verify_served_model(response: dict, requested_engineer: str) -> str:
    """P46 enforcement: read response.model, assert it matches the request.

    Returns the served model name. Exits non-zero on:
        - missing/empty model field (P46 violation -- cannot verify)
        - forbidden substring (Gemini) in served model (hard NO-GEMINI rule)
        - served model != requested engineer (silent fallback -- FA13)

    The check is forgiving on provider prefixes: OpenRouter sometimes
    returns "openai/gpt-4o-mini" when "gpt-4o-mini" was requested, so we
    compare on suffix match. We do NOT forgive forbidden substrings.
    """
    served_model = response.get("model", "") or ""
    if not served_model:
        sys.exit(
            "cto_loop: P46 VIOLATION -- response.model is missing or empty. "
            "Cannot verify the served instrument. Refusing to proceed."
        )

    served_lower = served_model.lower()

    # Hard NO-GEMINI gate. Even if the user requested Gemini explicitly
    # (which _validate_engineer would already refuse), this catches the
    # case where OpenRouter silently fell back to a Gemini variant.
    for forbidden in FORBIDDEN_MODEL_SUBSTRINGS:
        if forbidden in served_lower:
            sys.exit(
                f"cto_loop: NO-GEMINI VIOLATION -- requested {requested_engineer} "
                f"but OpenRouter served {served_model}, which contains the "
                f"forbidden substring '{forbidden}'. The work below was NOT "
                f"done by an allowed engineer. Per FA13, refusing to relabel. "
                f"Per P47, decompose the task and retry."
            )

    requested_lower = requested_engineer.lower()
    if served_lower != requested_lower and not served_lower.endswith(
        requested_lower
    ):
        sys.exit(
            f"cto_loop: P46 VIOLATION -- requested {requested_engineer} but "
            f"OpenRouter served {served_model}. The work below was NOT done by "
            f"the requested engineer. Per FA13, refusing to relabel. Per P47, "
            f"decompose the task into a smaller prompt and retry."
        )

    return served_model


def _save_response(
    response: dict, out_dir: Path, task_name: str, engineer: str
) -> tuple[Path, Path]:
    """Persist the full JSON response and a markdown digest.

    Returns (json_path, md_path). The markdown digest is what a human
    reads; the JSON is the auditable artifact.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_engineer = engineer.replace("/", "_").replace(":", "_")
    json_path = out_dir / f"{task_name}__{safe_engineer}__{ts}.json"
    md_path = out_dir / f"{task_name}__{safe_engineer}__{ts}.md"

    json_path.write_text(
        json.dumps(response, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    served_model = response.get("model", "(missing)")
    generation_id = response.get("id", "(not provided)")
    choices = response.get("choices", []) or []
    content = (
        choices[0].get("message", {}).get("content", "") if choices else "(no choices)"
    )
    usage = response.get("usage", {}) or {}

    md_lines = [
        f"# CTO Loop dispatch -- {task_name}",
        "",
        f"- **Requested engineer**: `{engineer}`",
        f"- **Served model (P46-verified)**: `{served_model}`",
        f"- **Generation ID**: `{generation_id}`",
        f"- **Dispatched at (UTC)**: {ts}",
        f"- **Prompt tokens**: {usage.get('prompt_tokens', '?')}",
        f"- **Completion tokens**: {usage.get('completion_tokens', '?')}",
        "",
        "## Governance primer applied",
        "",
        "Every dispatch prepends the project's anti-entropy primer:",
        "Prime Directive, No-Gaming, Trace-Before-Fix, Honest-Boundary,",
        "P1, P46, P54, FA13. The engineer is told to cite the P-number",
        "each fix satisfies and to write 'UNVERIFIED -- reasoning only'",
        "instead of a checkmark it cannot back with execution evidence.",
        "",
        "## Engineer response",
        "",
        content,
        "",
        "---",
        f"Full JSON response: `{json_path}`",
    ]
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    return json_path, md_path


def _log_to_worklog(
    task_name: str,
    task_path: Path,
    engineer: str,
    served_model: str,
    generation_id: str | None,
    json_path: Path,
    md_path: Path,
    latency_s: float,
) -> None:
    entry = f"""
---
Task ID: cto-loop-{task_name}
Agent: CTO Loop (orchestrator, multi-engineer)
Task: Dispatched engineering task to {engineer} via OpenRouter.
      Task brief: {task_path}

Work Log:
- Read task brief from {task_path} ({task_path.stat().st_size} bytes)
- Prepended governance primer (Prime Directive, No-Gaming, Trace-Before-Fix,
  Honest-Boundary, P1, P46, P54, FA13) to the task brief
- Called OpenRouter with model={engineer}
- P46 verification: response.model = {served_model}
- Generation ID: {generation_id or "(not provided by OpenRouter)"}
- Latency: {latency_s:.1f}s
- Saved full JSON response to {json_path}
- Saved markdown digest to {md_path}
- NO-GEMINI rule: enforced (engineer allow-list + served-model substring check)

Stage Summary:
- Engineering task dispatched and response captured.
- P46 (verify served instrument) enforced: served model verified as the
  requested engineer (no silent fallback).
- NO-GEMINI rule: enforced on both the request side (--engineer validated
  against ALLOWED_ENGINEERS) and the response side (served model checked
  against FORBIDDEN_MODEL_SUBSTRINGS).
- Generation ID recorded for external cross-check on OpenRouter dashboard.
- CTO will review the markdown digest and apply the proposed changes.
"""
    with WORKLOG_PATH.open("a", encoding="utf-8") as f:
        f.write(entry)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CTO-Engineer Loop (multi-model, P46-enforced, NO GEMINI)"
    )
    parser.add_argument(
        "--task",
        type=Path,
        required=True,
        help="Path to a markdown file containing the engineering task brief.",
    )
    parser.add_argument(
        "--engineer",
        type=str,
        required=True,
        choices=sorted(ALLOWED_ENGINEERS.keys()),
        help="OpenRouter model ID of the engineer to dispatch to. "
        "Must be in the allow-list. NO GEMINI.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("/home/z/my-project/scripts/cto_loop/out"),
        help="Directory to save the full OpenRouter response + markdown digest.",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Task name (used in output filenames). Defaults to the task file stem.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Override the engineer's default OpenRouter timeout (seconds).",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Override the engineer's default max_tokens.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Override the engineer's default temperature.",
    )
    args = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        sys.exit(
            "cto_loop: OPENROUTER_API_KEY environment variable is not set. "
            "The CTO cannot dispatch tasks without it."
        )

    config = _validate_engineer(args.engineer)
    timeout_s = args.timeout or config["timeout_s"]
    max_tokens = args.max_tokens or config["max_tokens"]
    temperature = (
        args.temperature if args.temperature is not None else config["temperature"]
    )

    task_brief = _read_task(args.task)
    task_name = args.name or args.task.stem

    print(f"cto_loop: dispatching task '{task_name}' to {args.engineer}")
    print(f"cto_loop: engineer label = {config['label']} ({config['strength']})")
    print(
        f"cto_loop: task brief size = {len(task_brief)} chars (incl. primer)"
    )
    print(
        f"cto_loop: timeout = {timeout_s}s, max_tokens = {max_tokens}, temp = {temperature}"
    )
    print(f"cto_loop: NO-GEMINI rule enforced (allow-list + served-model check)")

    t0 = time.monotonic()
    response = _call_openrouter(
        api_key=api_key,
        engineer=args.engineer,
        task_brief=task_brief,
        timeout_s=timeout_s,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    latency_s = time.monotonic() - t0

    served_model = _verify_served_model(response, args.engineer)
    generation_id = response.get("id")

    json_path, md_path = _save_response(
        response, args.out, task_name, args.engineer
    )
    _log_to_worklog(
        task_name=task_name,
        task_path=args.task,
        engineer=args.engineer,
        served_model=served_model,
        generation_id=generation_id,
        json_path=json_path,
        md_path=md_path,
        latency_s=latency_s,
    )

    choices = response.get("choices", []) or []
    if choices:
        content = choices[0].get("message", {}).get("content", "")
        print("\n" + "=" * 78)
        print(
            f"ENGINEER RESPONSE (served={served_model}, gen_id={generation_id})"
        )
        print("=" * 78)
        print(content)
        print("=" * 78)
        print(f"Full JSON: {json_path}")
        print(f"Digest:    {md_path}")
        print(
            f"P46 verification: served model matches requested engineer"
        )
        print(
            f"NO-GEMINI: verified (no forbidden substring in served model)"
        )
        print(f"Latency: {latency_s:.1f}s")
    else:
        sys.exit(
            "cto_loop: response had no choices. Full response saved to: "
            + str(json_path)
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
