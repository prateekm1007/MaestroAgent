#!/usr/bin/env python3
"""
CTO ↔ Engineer Loop — UNFAKEABLE served-model verification (P46).

PRINCIPLE P46 (new, from the model-attribution breach):
  Any claim that a tool, model, connector, or path did the work is proven
  by the RESPONSE-SIDE evidence (served model, returned state, actual
  stored value, OpenRouter generation ID), NEVER by the request-side
  field or a separate probe. A probe that the instrument is present is
  not proof it played the work.

This script enforces P46 at the routing layer:
  1. Reads `response.model` (the model OpenRouter ACTUALLY served) on
     every call — never the request-side `model` field.
  2. ASSERTS response.model == "moonshotai/kimi-k3". If the served model
     is anything else (Gemma, Llama, etc.), the script FAILS LOUDLY with
     `SERVED_MODEL=<actual>` — it NEVER relabels a fallback as kimi-k3.
  3. Captures `response.id` (the OpenRouter generation ID) so the claim
     is externally checkable on the OpenRouter dashboard.
  4. Captures `response.provider` (the actual provider name) — never
     hardcoded.
  5. On any error (timeout, 429, network), FAILS LOUDLY with
     `SERVED_MODEL=none` — the task is marked NOT DONE BY KIMI K3.
     The CTO must then either retry, restructure the task, or honestly
     declare a different engineer model.

USAGE:
  python3 cto_loop.py selftest                    # verify Kimi K3 reachable
  python3 cto_loop.py design  <task_file.json>    # delegate a design task
  python3 cto_loop.py verify  <task_id> <impl>    # review an implementation

Every output JSON includes:
  _served_model   — the model that ACTUALLY served the response (P46)
  _generation_id  — the OpenRouter generation ID for dashboard cross-check
  _provider       — the actual provider name (e.g. "Moonshot AI")
  _latency_s      — wall-clock latency
  _served_model_verified — True iff _served_model == "moonshotai/kimi-k3"
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

EXPECTED_MODEL = "moonshotai/kimi-k3"  # the ONLY acceptable served model

GOVERNANCE_PREAMBLE = """You are KIMI K3 (moonshotai/kimi-k3), the ENGINEER.
The CTO (GLM) delegates design work to you. You DESIGN the fix — diffs,
code blocks, test additions, and verification commands. The CTO applies
and verifies. You do not claim "done" — you propose, the CTO disposes.

GOVERNANCE (binding on every design you produce):
- P35 — Gate the journey, not the component.
- P36 — Deterministic entity/owner/temporal/source gate.
- P37 — Typed lifecycle with hard admission rules.
- P38 — Deletion is final.
- P39 — No shared identity in production.
- P40 — Production reliability is a trust property.
- P41 — Single source of truth (derive, don't duplicate).
- P42 — Normalize text before structural matching.
- P43 (NEW) — Built-but-not-wired is not done. Every new function ships
  with a journey assertion proving the live path calls it.
- P44 (NEW) — Resilience is not speed. A circuit breaker is a safety net,
  not a latency fix. The latency fix is streaming + bounded time-to-first-token.
- P45 (NEW) — Local-green is a hypothesis; CI-green-on-push is the proof.
- P46 (NEW) — Verify the served instrument, not the requested one. Your
  response will be checked against response.model; if you are not
  moonshotai/kimi-k3, the task is marked NOT DONE BY KIMI K3.

FORBIDDEN ACTIONS (your design MUST NOT propose these):
1. Lowering a gate threshold to silence a red.
2. Claiming "live" without a fresh fetch.
3. Seeding synthetic data and presenting it as real.
4. Modifying governance/ files.
5. Gaming a metric by narrowing scope.
6. Accepting "exists" for "works" — trace the full path.
7. Spraying a fix before all return paths — verify on abstain/error paths.
8. Headless-browser OAuth.
9. Crediting a component gate as a product fix (P35).
10. Shipping an answer not constrained to the query's entity/owner (P36).
11. Admitting non-commitments to the active commitment surface (P37).
12. Allowing re-login after account deletion (P38).

OUTPUT CONTRACT (strict):
- Respond with ONE JSON object, no prose, no markdown fence.
- Keys: design_summary, files_to_change (list of {path, change_type,
  diff_or_block, rationale}), test_additions (list of {path, block}),
  verification_commands (list of strings the CTO will run), risks
  (list of strings), principle_citations (list of P-numbers this design
  enforces), forbidden_action_check (list of FA numbers verified
  avoided).
- Every change must cite which P-number it enforces.
- If the design would require a forbidden action, ABORT and return
  {"abort": true, "reason": "..."} instead.
"""


def _load_openrouter_key() -> str:
    env_path = Path("/home/z/my-project/.env.local")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip()
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if key:
        return key
    raise SystemExit("OPENROUTER_API_KEY not found in .env.local or env")


def _call_kimi_k3(api_key: str, system: str, user: str, timeout: int = 240) -> dict:
    """Call Kimi K3 via OpenRouter with UNFAKEABLE served-model verification (P46).

    Returns a dict with:
      _served_model   — response.model (the ACTUALLY served model)
      _generation_id  — response.id (OpenRouter generation ID for dashboard cross-check)
      _provider       — response.provider (actual provider name)
      _latency_s      — wall-clock latency
      _served_model_verified — True iff _served_model == EXPECTED_MODEL

    On ANY error (timeout, 429, network, non-JSON), returns:
      {"error": ..., "_served_model": "none", "_served_model_verified": False,
       "_generation_id": "none", "_provider": "none", "_latency_s": ...}

    NEVER relabels a fallback as kimi-k3. NEVER silently retries with a
    cheaper model. If kimi-k3 is unavailable, the task FAILS LOUDLY.
    """
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {
        "model": EXPECTED_MODEL,  # request kimi-k3
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_tokens": 8000,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://maestro.local/cto-loop",
            "X-Title": "MaestroAgent CTO-Engineer Loop",
        },
        method="POST",
    )
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        elapsed = time.monotonic() - start
        detail = e.read().decode("utf-8", "replace")[:500]
        return {
            "error": f"HTTP {e.code}",
            "detail": detail,
            "_served_model": "none",
            "_served_model_verified": False,
            "_generation_id": "none",
            "_provider": "none",
            "_latency_s": round(elapsed, 2),
            "_p46_note": "FAIL LOUDLY — no fallback. Task NOT DONE BY KIMI K3.",
        }
    except Exception as e:
        elapsed = time.monotonic() - start
        return {
            "error": f"{type(e).__name__}: {e}",
            "_served_model": "none",
            "_served_model_verified": False,
            "_generation_id": "none",
            "_provider": "none",
            "_latency_s": round(elapsed, 2),
            "_p46_note": "FAIL LOUDLY — no fallback. Task NOT DONE BY KIMI K3.",
        }
    elapsed = time.monotonic() - start

    try:
        outer = json.loads(body)
    except Exception:
        return {
            "error": "non-JSON response",
            "raw": body[:500],
            "_served_model": "none",
            "_served_model_verified": False,
            "_generation_id": "none",
            "_provider": "none",
            "_latency_s": round(elapsed, 2),
            "_p46_note": "FAIL LOUDLY — no fallback. Task NOT DONE BY KIMI K3.",
        }

    # P46: read the SERVED model from the response, NOT the request.
    served_model = outer.get("model", "unknown")
    generation_id = outer.get("id", "unknown")
    # Provider is in the generation metadata, not always top-level
    provider = "unknown"
    choices = outer.get("choices", [])
    if choices:
        provider = (choices[0].get("provider") or
                    outer.get("provider") or
                    "unknown")

    # P46 ASSERTION: served model MUST be kimi-k3. If OpenRouter silently
    # fell back to a different model (Gemma, Llama, etc.), we FAIL LOUDLY
    # and mark the task NOT DONE BY KIMI K3. We NEVER relabel.
    served_model_verified = (served_model == EXPECTED_MODEL)

    content = choices[0].get("message", {}).get("content", "") if choices else ""
    if content.startswith("```"):
        first_newline = content.find("\n")
        last_fence = content.rfind("```")
        if first_newline > 0 and last_fence > first_newline:
            content = content[first_newline + 1:last_fence].strip()

    try:
        parsed = json.loads(content) if content else {}
    except Exception:
        return {
            "error": "Kimi K3 did not return valid JSON",
            "raw": content[:1000],
            "_served_model": served_model,
            "_served_model_verified": served_model_verified,
            "_generation_id": generation_id,
            "_provider": provider,
            "_latency_s": round(elapsed, 2),
            "_p46_note": ("VERIFIED SERVED MODEL" if served_model_verified else
                          f"SERVED_MODEL={served_model} — NOT kimi-k3. FAIL LOUDLY."),
        }

    parsed["_served_model"] = served_model
    parsed["_served_model_verified"] = served_model_verified
    parsed["_generation_id"] = generation_id
    parsed["_provider"] = provider
    parsed["_latency_s"] = round(elapsed, 2)
    if served_model_verified:
        parsed["_p46_note"] = (
            f"VERIFIED: response.model={served_model}, generation_id={generation_id}. "
            f"Cross-checkable on OpenRouter dashboard."
        )
    else:
        parsed["_p46_note"] = (
            f"SERVED_MODEL={served_model} — NOT {EXPECTED_MODEL}. "
            f"FAIL LOUDLY. Task NOT DONE BY KIMI K3. "
            f"generation_id={generation_id} (cross-check on dashboard)."
        )
    return parsed


def cmd_design(task_file: str) -> int:
    api_key = _load_openrouter_key()
    task = json.loads(Path(task_file).read_text())

    user_msg = f"""TASK ID: {task['task_id']}
TITLE: {task['title']}

CONTEXT FILES (read these before designing):
{json.dumps(task.get('context_files', []), indent=2)}

PRINCIPLE REFS:
{json.dumps(task.get('principle_refs', []), indent=2)}

FORBIDDEN ACTIONS TO VERIFY AVOIDED:
{json.dumps(task.get('forbidden_actions', []), indent=2)}

SPEC (what the fix must do, with acceptance criteria):
{task['spec']}

ADDITIONAL CONTEXT:
{task.get('extra_context', '')}

Produce the design per the OUTPUT CONTRACT. Remember: ONE JSON object,
no prose, no markdown fence. If the design would require a forbidden
action, return {{"abort": true, "reason": "..."}}.
"""
    task_id = task['task_id']
    out_path = Path(f"/home/z/my-project/scripts/kimi_out/{task_id}_design.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[CTO→Kimi K3] Delegating task {task_id} design...", flush=True)
    print(f"  EXPECTED SERVED MODEL: {EXPECTED_MODEL}", flush=True)
    result = _call_kimi_k3(api_key, GOVERNANCE_PREAMBLE, user_msg, timeout=240)
    out_path.write_text(json.dumps(result, indent=2))
    print(f"[Kimi K3→CTO] Design written to {out_path}", flush=True)

    # P46: print the served-model verdict prominently
    served = result.get("_served_model", "none")
    verified = result.get("_served_model_verified", False)
    gen_id = result.get("_generation_id", "none")
    provider = result.get("_provider", "none")
    latency = result.get("_latency_s", "?")
    print(f"  _served_model: {served}", flush=True)
    print(f"  _served_model_verified: {verified}", flush=True)
    print(f"  _generation_id: {gen_id}", flush=True)
    print(f"  _provider: {provider}", flush=True)
    print(f"  _latency_s: {latency}", flush=True)

    if "error" in result:
        print(f"  ERROR: {result['error']}", flush=True)
        print(f"  P46: Task NOT DONE BY KIMI K3. CTO must retry, restructure, "
              f"or honestly declare a different engineer model.", flush=True)
        return 1
    if not verified:
        print(f"  P46 VIOLATION: served model is {served}, not {EXPECTED_MODEL}.",
              flush=True)
        print(f"  Task NOT DONE BY KIMI K3. OpenRouter silently fell back to a "
              f"different model. FAIL LOUDLY — no relabeling.", flush=True)
        return 2
    if result.get("abort"):
        print(f"  ABORT (Kimi K3 refused): {result.get('reason', '?')}", flush=True)
        return 3

    print(f"  P46 VERIFIED: response.model={served}, generation_id={gen_id}",
          flush=True)
    print(f"  Cross-check on OpenRouter dashboard: look up generation_id {gen_id}",
          flush=True)
    print(f"  design_summary: {result.get('design_summary', '?')[:200]}", flush=True)
    print(f"  files_to_change: {len(result.get('files_to_change', []))}", flush=True)
    print(f"  test_additions: {len(result.get('test_additions', []))}", flush=True)
    print(f"  principle_citations: {result.get('principle_citations', [])}", flush=True)
    return 0


def cmd_selftest() -> int:
    """Self-test: confirm Kimi K3 is reachable AND actually serves the response.

    P46: this proves the SERVED model, not just the request. The probe is
    a short prompt (so it doesn't time out), and we assert response.model
    == moonshotai/kimi-k3. The generation_id is printed for dashboard
    cross-check.
    """
    api_key = _load_openrouter_key()
    print(f"[selftest] EXPECTED_SERVED_MODEL={EXPECTED_MODEL}", flush=True)
    result = _call_kimi_k3(
        api_key,
        "You are a test echo. Respond with the exact JSON: "
        "{\"ok\": true, \"echo\": \"kimi-k3-selftest\"}",
        "Reply with the JSON object only.",
        timeout=60,
    )
    print(json.dumps(result, indent=2))
    if not result.get("_served_model_verified"):
        print(f"\nP46 FAIL: served model is {result.get('_served_model')}, "
              f"not {EXPECTED_MODEL}.", flush=True)
        return 1
    if not result.get("ok"):
        print(f"\nP46 FAIL: Kimi K3 reached but did not return expected echo.",
              flush=True)
        return 1
    print(f"\nP46 PASS: served_model={result['_served_model']}, "
          f"generation_id={result['_generation_id']}", flush=True)
    print(f"Cross-check on OpenRouter dashboard: look up generation_id "
          f"{result['_generation_id']}", flush=True)
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    if cmd == "selftest":
        return cmd_selftest()
    if cmd == "design":
        if len(sys.argv) < 3:
            print("usage: cto_loop.py design <task_file.json>")
            return 2
        return cmd_design(sys.argv[2])
    print(f"unknown command: {cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
