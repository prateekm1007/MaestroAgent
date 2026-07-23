#!/usr/bin/env python3
"""Run k3 deep-reasoning forensic sweep over the actual codebase.

This is the MISSING HALF: k3 actually reads the code and produces
independent findings. The static+live findings are separate; k3's
findings are labeled as k3-produced.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx

OPS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(OPS_DIR))

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
MODEL = "moonshotai/kimi-k3"
CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"

# The codebase root
REPO_ROOT = Path(__file__).resolve().parents[2]  # download/MaestroAgent/

# Per-team forensic prompts — each reads its domain's code
TEAM_PROMPTS = {
    "Connector": """You are a forensic code auditor reviewing the Maestro connector subsystem.
Read these files and find bugs, security holes, dead code, silent assumptions, and error-handling gaps:

FILES TO REVIEW:
- connectors.py (ConnectorStore: encryption, token storage, ingest)
- routers/connectors.py (connect endpoint, OAuth callbacks, work_email IMAP)
- gmail_connector.py (OAuth flow, token refresh)
- calendar_connector.py (OAuth config, Calendar API)
- connector_framework/adapters/outlook.py (IMAP adapter)

For each finding, provide:
1. FINDING ID (K3-CONN-NNN)
2. SEVERITY (P0/P1/P2/P3)
3. TITLE (one line)
4. EVIDENCE (file:line + exact code snippet)
5. REPRODUCTION (exact command or API call to confirm)
6. ROOT CAUSE (the mechanism)
7. FIX (recommended change)
8. STATUS (CONFIRMED-LIVE if you can verify from the code, STATIC-HYPOTHESIS if inferred)

Focus on: credential storage security, OAuth flow correctness, IMAP error handling, token refresh bugs, cross-user data leakage.""",

    "Backend": """You are a forensic code auditor reviewing the Maestro backend.
Read these files and find bugs, security holes, dead code, silent assumptions, and error-handling gaps:

FILES TO REVIEW:
- routers/auth.py (login, register, token minting, demo path)
- routers/ask.py (Ask endpoint, evidence retrieval, entity resolution, abstention)
- routers/admin.py (health endpoint, purge endpoint)
- shell.py (filter_evidence, PersonalShell)
- retrieval_ensemble.py (_load_all_signals, specialist retrievers)

For each finding, provide:
1. FINDING ID (K3-BE-NNN)
2. SEVERITY (P0/P1/P2/P3)
3. TITLE (one line)
4. EVIDENCE (file:line + exact code snippet)
5. REPRODUCTION (exact command or API call to confirm)
6. ROOT CAUSE (the mechanism)
7. FIX (recommended change)
8. STATUS (CONFIRMED-LIVE if you can verify from the code, STATIC-HYPOTHESIS if inferred)

Focus on: auth bypass, IDOR (cross-user access), evidence isolation, abstention correctness, rate limiting, secret exposure in logs/responses.""",

    "UI": """You are a forensic code auditor reviewing the Maestro frontend.
Read these files and find bugs, UX issues, security holes, and rendering gaps:

FILES TO REVIEW:
- app/page.tsx (SSR shell, hydration)
- components/maestro/AppShell.tsx (shell skeleton)
- components/maestro/Login.tsx (login form, demo path removal)
- components/maestro/Connectors.tsx (connector cards, work email form, IMAP auto-detect)
- components/maestro/Ask.tsx (evidence panel, evidence_refs rendering)
- lib/maestro-api.ts (maestroFetch, error handling, 401→400)

For each finding, provide:
1. FINDING ID (K3-UI-NNN)
2. SEVERITY (P0/P1/P2/P3)
3. TITLE (one line)
4. EVIDENCE (file:line + exact code snippet)
5. REPRODUCTION (exact UI step or curl to confirm)
6. ROOT CAUSE (the mechanism)
7. FIX (recommended change)
8. STATUS (CONFIRMED-LIVE if you can verify from the code, STATIC-HYPOTHESIS if inferred)

Focus on: XSS, credential handling in the browser, SSR vs hydration mismatches, error display correctness, evidence panel rendering.""",

    "Infra": """You are a forensic code auditor reviewing the Maestro infrastructure.
Read these files and find bugs, deployment issues, and monitoring gaps:

FILES TO REVIEW:
- Dockerfile (build process, env vars, module list)
- .github/workflows/deploy.yml (deploy pipeline, S0 assertion)
- .github/workflows/benchmark.yml (CI gate, scorer proof)
- audit/deploy_ops.py (drift detection, deploy trigger, S0 check)
- audit/run_benchmark.py (scorer, isolation_assertion)

For each finding, provide:
1. FINDING ID (K3-INFRA-NNN)
2. SEVERITY (P0/P1/P2/P3)
3. TITLE (one line)
4. EVIDENCE (file:line + exact code snippet)
5. REPRODUCTION (exact command to confirm)
6. ROOT CAUSE (the mechanism)
7. FIX (recommended change)
8. STATUS (CONFIRMED-LIVE if you can verify from the code, STATIC-HYPOTHESIS if inferred)

Focus on: deploy drift, build failures, S0 false-positives, CI gate bypasses, env var misconfiguration.""",

    "Data": """You are a forensic code auditor reviewing the Maestro data layer.
Read these files and find bugs, provenance issues, and data integrity gaps:

FILES TO REVIEW:
- api.py (demo seeding, DB init, signal storage)
- demo_seeder.py (demo data, seeding gate)
- entity_resolver.py (possessive resolution, entity filtering)
- commitment_ledger.py (correction propagation, state transitions)
- ops/governance_enforcer.py (forbidden actions, secret scan)
- ops/case_memory.py (FTS5, seeded cases)

For each finding, provide:
1. FINDING ID (K3-DATA-NNN)
2. SEVERITY (P0/P1/P2/P3)
3. TITLE (one line)
4. EVIDENCE (file:line + exact code snippet)
5. REPRODUCTION (exact command to confirm)
6. ROOT CAUSE (the mechanism)
7. FIX (recommended change)
8. STATUS (CONFIRMED-LIVE if you can verify from the code, STATIC-HYPOTHESIS if inferred)

Focus on: demo data leakage, provenance correctness, correction feedback, entity resolution bugs, governance enforcement gaps.""",
}


def read_file_for_prompt(filepath: str, max_lines: int = 200) -> str:
    """Read a file and return its content (truncated for prompt size)."""
    full_path = REPO_ROOT / filepath
    if not full_path.exists():
        return f"(file not found: {filepath})"
    try:
        content = full_path.read_text()
        lines = content.split("\n")
        if len(lines) > max_lines:
            return "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines truncated)"
        return content
    except Exception as e:
        return f"(error reading {filepath}: {e})"


def build_team_prompt(team: str, prompt_template: str) -> str:
    """Build the full prompt for a team — template + actual file contents."""
    # Map team to the files it should read
    file_map = {
        "Connector": [
            "maestro-personal/src/maestro_personal_shell/connectors.py",
            "maestro-personal/src/maestro_personal_shell/routers/connectors.py",
            "maestro-personal/src/maestro_personal_shell/gmail_connector.py",
            "maestro-personal/src/maestro_personal_shell/calendar_connector.py",
        ],
        "Backend": [
            "maestro-personal/src/maestro_personal_shell/routers/auth.py",
            "maestro-personal/src/maestro_personal_shell/routers/admin.py",
            "maestro-personal/src/maestro_personal_shell/shell.py",
            "maestro-personal/src/maestro_personal_shell/retrieval_ensemble.py",
        ],
        "UI": [
            "maestro-personal/web/src/app/page.tsx",
            "maestro-personal/web/src/components/maestro/AppShell.tsx",
            "maestro-personal/web/src/components/maestro/Login.tsx",
            "maestro-personal/web/src/components/maestro/Connectors.tsx",
            "maestro-personal/web/src/lib/maestro-api.ts",
        ],
        "Infra": [
            "Dockerfile",
            ".github/workflows/deploy.yml",
            "maestro-personal/audit/deploy_ops.py",
            "maestro-personal/audit/run_benchmark.py",
        ],
        "Data": [
            "maestro-personal/src/maestro_personal_shell/api.py",
            "maestro-personal/src/maestro_personal_shell/demo_seeder.py",
            "maestro-personal/src/maestro_personal_shell/entity_resolver.py",
            "maestro-personal/src/maestro_personal_shell/commitment_ledger.py",
        ],
    }

    files_to_read = file_map.get(team, [])
    code_content = "\n\n".join(
        f"=== FILE: {f} ===\n{read_file_for_prompt(f, max_lines=150)}"
        for f in files_to_read
    )

    return f"{prompt_template}\n\n=== CODEBASE (actual source code) ===\n\n{code_content}\n\n=== END CODEBASE ===\n\nNow produce your forensic findings. Be specific — cite exact file:line and code snippets. Mark each finding CONFIRMED-LIVE or STATIC-HYPOTHESIS. Do NOT produce findings about things you cannot verify from the code above."


def call_k3(prompt: str, max_retries: int = 3) -> str:
    """Call k3 with retry+backoff for 429s."""
    if not OPENROUTER_API_KEY:
        return "K3_UNAVAILABLE: OPENROUTER_API_KEY not set"

    for attempt in range(max_retries):
        try:
            resp = httpx.post(
                CHAT_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": "You are a forensic code auditor. Be precise, cite evidence, and never overstate a hypothesis as confirmed. Output findings in the exact format requested."},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 3000,
                    "temperature": 0.2,
                },
                timeout=300,
            )
            if resp.status_code == 429:
                delay = 5 * (2 ** attempt)
                print(f"    ⚠ 429 — retrying in {delay}s (attempt {attempt+1}/{max_retries})")
                time.sleep(delay)
                continue
            if resp.status_code == 200:
                return resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                return f"K3_ERROR: {resp.status_code} — {resp.text[:200]}"
        except httpx.TimeoutException:
            print(f"    ⚠ Timeout (attempt {attempt+1}/{max_retries})")
            time.sleep(5)
        except Exception as e:
            return f"K3_ERROR: {e}"

    return "K3_EXHAUSTED: max retries (429)"


def main():
    print("=" * 72)
    print("k3 DEEP-REASONING FORENSIC SWEEP")
    print(f"Model: {MODEL}")
    print(f"API Key: {'available' if OPENROUTER_API_KEY else 'NOT SET'}")
    print("=" * 72)

    all_k3_findings = {}

    for team, prompt_template in TEAM_PROMPTS.items():
        print(f"\n{'='*60}")
        print(f"TEAM: {team}")
        print(f"{'='*60}")

        # Build the prompt with actual code
        print(f"  Building prompt with codebase content...")
        full_prompt = build_team_prompt(team, prompt_template)
        prompt_size = len(full_prompt)
        print(f"  Prompt size: {prompt_size:,} chars (~{prompt_size//4:,} tokens)")

        # Call k3
        print(f"  Calling k3 (may take 1-5 min)...")
        start = time.time()
        result = call_k3(full_prompt)
        elapsed = time.time() - start

        if result.startswith("K3_"):
            print(f"  ✗ k3 call failed: {result[:100]}")
            all_k3_findings[team] = f"FAILED: {result}"
        else:
            print(f"  ✓ k3 responded in {elapsed:.0f}s ({len(result)} chars)")
            all_k3_findings[team] = result

            # Print the findings
            print(f"\n  --- k3 FINDINGS ({team}) ---")
            print(result[:2000])
            if len(result) > 2000:
                print(f"  ... ({len(result) - 2000} more chars)")

    # Save all k3 findings
    print(f"\n{'='*72}")
    print("k3 FORENSIC SWEEP COMPLETE")
    print(f"{'='*72}")

    output = {
        "model": MODEL,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "teams": all_k3_findings,
    }

    output_path = OPS_DIR / "k3_forensic_findings.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nFindings saved to: {output_path}")

    # Also print the full findings for relay
    print(f"\n{'='*72}")
    print("FULL k3 FINDINGS (for relay)")
    print(f"{'='*72}")
    for team, findings in all_k3_findings.items():
        print(f"\n## TEAM: {team}")
        print(findings)


if __name__ == "__main__":
    main()
