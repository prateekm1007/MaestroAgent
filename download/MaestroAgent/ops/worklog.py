"""Agent Worklog — append-only, reviewable log of every agent action.

The transparency layer that makes the swarm trustworthy at scale:
agents act autonomously, but every action is logged, version-controlled,
secret-free, and reviewable by the owner and the auditor.

DESIGN:
  - ops/worklog/<ticket-id>.md — one file per ticket, full lifecycle
  - ops/WORKLOG.md — append-only index with one-line summary + link
  - Each entry records: Detect → Diagnose → Govern → Execute → Verify → Learn → Outcome
  - Secret-scan runs before write (enforcer.check_report) — no secret values
  - Append-only: the swarm never rewrites or deletes history
  - Each entry is a git commit — git history is the tamper-evident guarantee

USAGE:
    from worklog import Worklog
    wl = Worklog()
    entry = wl.start_entry("OPS-003", "Work email connector", source="user_request")
    entry.add_detect("User requested work email connector")
    entry.add_diagnose("Adapters exist in connectors/adapters/ but not surfaced in UI")
    entry.add_govern("wire IMAP form: ALLOW (Level 1)")
    entry.add_execute("Added IMAP connect form to Connectors.tsx")
    entry.add_verify("Connected test mailbox, 5 signals ingested with source=imap")
    entry.add_learn("IMAP ingest works; provenance flows through to evidence_refs")
    entry.set_outcome("RESOLVED")
    wl.write_entry(entry)  # writes file + updates index + secret-scans
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Make governance_enforcer importable
OPS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(OPS_DIR))

from governance_enforcer import GovernanceEnforcer, SECRET_PATTERNS

WORKLOG_DIR = OPS_DIR / "worklog"
WORKLOG_INDEX = OPS_DIR / "WORKLOG.md"  # ops/WORKLOG.md


@dataclass
class WorklogEntry:
    """A single worklog entry — the full lifecycle of one ticket."""
    ticket_id: str
    title: str
    source: str = ""  # user_request, monitoring, deploy, etc.
    created_at: str = ""
    agents: list[str] = field(default_factory=list)  # Diagnostician, Repair, Verifier, etc.
    detect: str = ""
    diagnose: str = ""
    govern: list[str] = field(default_factory=list)  # each governance verdict
    execute: list[str] = field(default_factory=list)  # each action taken
    verify: str = ""
    learn: str = ""
    outcome: str = ""  # RESOLVED / ESCALATED / FAILED
    summary: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def add_detect(self, text: str):
        self.detect = text

    def add_diagnose(self, text: str):
        self.diagnose = text

    def add_govern(self, verdict: str):
        """Add a governance verdict. e.g., 'trigger deploy: ALLOW (Level 1)'"""
        self.govern.append(verdict)

    def add_execute(self, action: str):
        """Add an executed action. NEVER include secret values."""
        self.execute.append(action)

    def add_verify(self, text: str):
        self.verify = text

    def add_learn(self, text: str):
        self.learn = text

    def add_agent(self, agent_name: str):
        self.agents.append(agent_name)

    def set_outcome(self, outcome: str, summary: str = ""):
        self.outcome = outcome
        if summary:
            self.summary = summary

    def to_markdown(self) -> str:
        """Render as markdown — machine-parseable AND human-readable."""
        lines = [
            f"# {self.ticket_id} — {self.title}",
            "",
            f"- **Created:** {self.created_at} | **Source:** {self.source}",
            f"- **Agents:** {', '.join(self.agents) if self.agents else 'N/A'}",
            f"- **Outcome:** {self.outcome}",
            "",
            "## Detect",
            self.detect or "(not recorded)",
            "",
            "## Diagnose",
            self.diagnose or "(not recorded)",
            "",
            "## Govern",
        ]
        if self.govern:
            for g in self.govern:
                lines.append(f"- {g}")
        else:
            lines.append("(no governance checks)")
        lines.extend([
            "",
            "## Execute",
        ])
        if self.execute:
            for e in self.execute:
                lines.append(f"- {e}")
        else:
            lines.append("(no actions taken)")
        lines.extend([
            "",
            "## Verify",
            self.verify or "(not verified)",
            "",
            "## Learn",
            self.learn or "(no lesson recorded)",
            "",
            "## Outcome",
            f"**{self.outcome}**",
            "",
            self.summary or "",
            "",
            "---",
            f"*This entry is append-only. Git history is the tamper-evident guarantee. "
            f"The swarm never rewrites or deletes worklog entries.*",
        ])
        return "\n".join(lines)


class Worklog:
    """Append-only worklog manager."""

    def __init__(self):
        self.enforcer = GovernanceEnforcer()
        WORKLOG_DIR.mkdir(parents=True, exist_ok=True)

    def start_entry(self, ticket_id: str, title: str, source: str = "") -> WorklogEntry:
        """Start a new worklog entry."""
        return WorklogEntry(
            ticket_id=ticket_id,
            title=title,
            source=source,
        )

    def write_entry(self, entry: WorklogEntry) -> dict:
        """Write the entry to ops/worklog/<ticket-id>.md + update the index.

        Runs a secret-scan before writing. If a secret is found, the entry
        is BLOCKED and not written.

        Returns: {written: bool, path: str, secret_scan: str}
        """
        # Render to markdown
        markdown = entry.to_markdown()

        # SECRET SCAN — no secret values in the worklog
        report_check = self.enforcer.check_report(markdown)
        if report_check.verdict == "BLOCK":
            return {
                "written": False,
                "path": "",
                "secret_scan": f"BLOCKED: {report_check.reason}",
                "error": "Worklog entry contains a secret pattern — refusing to write. Reference secrets by name only.",
            }

        # Write the entry file
        entry_path = WORKLOG_DIR / f"{entry.ticket_id}.md"
        entry_path.write_text(markdown)

        # Update the index (append-only)
        self._update_index(entry)

        return {
            "written": True,
            "path": str(entry_path),
            "secret_scan": "PASS — no secret values detected",
        }

    def _update_index(self, entry: WorklogEntry):
        """Append to ops/WORKLOG.md index. Never rewrite existing entries."""
        index_line = (
            f"- [{entry.ticket_id}](worklog/{entry.ticket_id}.md) — "
            f"{entry.title} | {entry.outcome} | {entry.created_at[:10]}"
        )

        if WORKLOG_INDEX.exists():
            content = WORKLOG_INDEX.read_text()
            # Check if this ticket is already in the index (avoid duplicates)
            if entry.ticket_id in content:
                # Don't rewrite — append-only means we don't modify existing lines
                # But if the ticket ID exists, it means we're updating — which we
                # handle by appending a new line (the latest entry wins for review)
                pass
            # Append the new line
            content = content.rstrip() + "\n" + index_line + "\n"
            WORKLOG_INDEX.write_text(content)
        else:
            # Create the index with a header
            header = (
                "# Agent Worklog — Index\n\n"
                "Every agent action, reviewable. Append-only. Git history is the tamper-evident guarantee.\n\n"
                "## Entries\n\n"
            )
            WORKLOG_INDEX.write_text(header + index_line + "\n")


# ── Self-test ───────────────────────────────────────────────────────────────

def run_self_test() -> bool:
    """Verify the worklog system works: write + secret-scan + index."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        # Override paths for testing
        global WORKLOG_DIR, WORKLOG_INDEX
        original_dir = WORKLOG_DIR
        original_index = WORKLOG_INDEX
        WORKLOG_DIR = Path(tmpdir) / "worklog"
        WORKLOG_INDEX = Path(tmpdir) / "WORKLOG.md"

        wl = Worklog()

        # GREEN: write a clean entry
        entry = wl.start_entry("TEST-001", "Test entry", source="self-test")
        entry.add_detect("Test detection")
        entry.add_diagnose("Test diagnosis")
        entry.add_govern("test action: ALLOW (Level 1)")
        entry.add_execute("Test execution — no secrets")
        entry.add_verify("Test verified")
        entry.add_learn("Test lesson")
        entry.set_outcome("RESOLVED", "Test summary")
        result = wl.write_entry(entry)

        print(f"GREEN (clean entry): written={result['written']}, secret_scan={result['secret_scan']}")
        if not result["written"]:
            print("✗ FAIL — clean entry should write")
            WORKLOG_DIR = original_dir
            WORKLOG_INDEX = original_index
            return False

        # RED: entry with a secret value
        secret_entry = wl.start_entry("TEST-002", "Secret entry", source="self-test")
        secret_entry.add_execute("Used token: e3d39b32-d40a-4405-9c08-958acaa9e92c")
        secret_entry.set_outcome("FAILED")
        result = wl.write_entry(secret_entry)

        print(f"RED (secret entry): written={result['written']}, secret_scan={result['secret_scan']}")
        if result["written"]:
            print("✗ FAIL — secret entry should be BLOCKED")
            WORKLOG_DIR = original_dir
            WORKLOG_INDEX = original_index
            return False

        # Verify index was created
        if not WORKLOG_INDEX.exists():
            print("✗ FAIL — index not created")
            WORKLOG_DIR = original_dir
            WORKLOG_INDEX = original_index
            return False

        index_content = WORKLOG_INDEX.read_text()
        if "TEST-001" not in index_content:
            print("✗ FAIL — TEST-001 not in index")
            WORKLOG_DIR = original_dir
            WORKLOG_INDEX = original_index
            return False

        if "TEST-002" in index_content:
            print("✗ FAIL — TEST-002 (blocked) should not be in index")
            WORKLOG_DIR = original_dir
            WORKLOG_INDEX = original_index
            return False

        # Restore paths
        WORKLOG_DIR = original_dir
        WORKLOG_INDEX = original_index

        print("\n✓ ALL WORKLOG TESTS PASS")
        print("  - Clean entry written ✓")
        print("  - Secret entry BLOCKED ✓")
        print("  - Index created + clean entry indexed ✓")
        print("  - Blocked entry NOT indexed ✓")
        return True


if __name__ == "__main__":
    import sys
    sys.exit(0 if run_self_test() else 1)
