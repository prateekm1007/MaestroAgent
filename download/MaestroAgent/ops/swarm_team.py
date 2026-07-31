"""Swarm Team — Team Leader + bounded multiplication + team members.

Each Team Leader is a coordinator agent that:
  - Receives a domain mandate
  - Breaks it into sub-tasks and assigns each to a team member
  - Coordinates members' work and aggregates results
  - Communicates with other Team Leaders via the message bus
  - Reports results to the Orchestrator
  - Records everything in the worklog
  - Never bypasses governance

Bounded multiplication: max N sub-agents per leader (default 5).
"""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from governance_enforcer import Action, GovernanceEnforcer, Verdict
from case_memory import CaseMemory
from swarm_message_bus import MessageBus, LeaderMessage

logger = logging.getLogger(__name__)

MAX_SUB_AGENTS = 5  # bounded multiplication


@dataclass
class SubTask:
    """A sub-task assigned to a team member."""
    id: str
    description: str
    assigned_to: str = ""  # agent name
    status: str = "pending"  # pending, in_progress, done, blocked, escalated
    result: str = ""
    governance_verdict: str = ""


@dataclass
class TeamMember:
    """A specialist agent within a team."""
    name: str
    specialty: str
    leader: str
    current_task: SubTask | None = None

    def execute(self, task: SubTask, context: dict) -> SubTask:
        """Execute a sub-task. Returns the updated task."""
        task.status = "in_progress"
        task.assigned_to = self.name
        print(f"    🔧 {self.name} executing: {task.description[:60]}...")

        # Look up the handler from the context's handler registry
        handlers = context.get("handlers", {})
        handler = handlers.get(task.id)

        if handler:
            try:
                result = handler(task, context)
                task.result = result or "completed"
                task.status = "done"
            except Exception as e:
                task.result = f"error: {e}"
                task.status = "blocked"
        else:
            task.result = "no handler assigned"
            task.status = "blocked"

        print(f"    {'✓' if task.status == 'done' else '⚠'} {self.name}: {task.result[:80]}")
        return task


class TeamLeader:
    """A Team Leader coordinates a swarm team.

    Receives a mandate → breaks into sub-tasks → assigns to members →
    coordinates → aggregates → reports → logs.
    """

    def __init__(
        self,
        name: str,
        domain: str,
        enforcer: GovernanceEnforcer,
        case_memory: CaseMemory,
        message_bus: MessageBus,
        max_members: int = MAX_SUB_AGENTS,
    ):
        self.name = name
        self.domain = domain
        self.enforcer = enforcer
        self.case_memory = case_memory
        self.message_bus = message_bus
        self.max_members = max_members
        self.members: list[TeamMember] = []
        self.sub_tasks: list[SubTask] = []
        self.mandate: str = ""
        self.results: dict[str, str] = {}

    def add_member(self, name: str, specialty: str) -> TeamMember:
        """Add a team member (bounded multiplication)."""
        if len(self.members) >= self.max_members:
            raise ValueError(f"Max members ({self.max_members}) reached for {self.name}")
        member = TeamMember(name=name, specialty=specialty, leader=self.name)
        self.members.append(member)
        print(f"  👤 {self.name}: added member {name} ({specialty})")
        return member

    def receive_mandate(self, mandate: str) -> list[SubTask]:
        """Receive a domain mandate and break it into sub-tasks."""
        self.mandate = mandate
        print(f"\n{'='*60}")
        print(f"TEAM LEADER: {self.name} ({self.domain})")
        print(f"{'='*60}")
        print(f"  Mandate: {mandate[:80]}...")

        # Search case memory for relevant past incidents
        matches = self.case_memory.search(mandate, limit=3)
        if matches:
            print(f"  Case memory: {len(matches)} match(es)")
            for m in matches:
                print(f"    - [{m.id}] {m.symptom[:60]}...")

        # Break into sub-tasks (domain-specific — overridden by subclasses)
        self.sub_tasks = self._break_down_mandate(mandate)
        print(f"  Sub-tasks: {len(self.sub_tasks)}")
        for t in self.sub_tasks:
            print(f"    - {t.id}: {t.description[:60]}...")

        return self.sub_tasks

    def _break_down_mandate(self, mandate: str) -> list[SubTask]:
        """Break the mandate into sub-tasks. Overridden by subclasses."""
        return []

    def execute(self, context: dict | None = None) -> dict:
        """Execute all sub-tasks by assigning them to team members."""
        context = context or {}
        context["enforcer"] = self.enforcer
        context["case_memory"] = self.case_memory
        context["message_bus"] = self.message_bus
        context["leader"] = self.name

        print(f"\n  {self.name}: executing {len(self.sub_tasks)} sub-task(s)...")

        for task in self.sub_tasks:
            # Assign to the most relevant member
            member = self._assign_task(task)
            if member:
                # Governance check on the task
                action = Action(
                    name=task.id,
                    description=task.description,
                    level=1,  # default Level-1 (reversible)
                    writes_to=[],
                )
                result = self.enforcer.check(action)
                task.governance_verdict = f"{result.verdict.value}: {result.reason}"

                if result.verdict == Verdict.BLOCK:
                    task.status = "blocked"
                    print(f"    ✗ {task.id} BLOCKED: {result.reason[:60]}")
                    continue
                if result.verdict == Verdict.ESCALATE:
                    task.status = "escalated"
                    print(f"    ⚠ {task.id} ESCALATED: {result.reason[:60]}")
                    continue

                # Execute
                member.execute(task, context)
            else:
                task.status = "blocked"
                task.result = "no available member"
                print(f"    ✗ {task.id}: no available member")

            self.results[task.id] = f"{task.status}: {task.result}"

        # Check for messages from other leaders
        messages = self.message_bus.receive(self.name)
        for msg in messages:
            print(f"  📨 Received from {msg.from_leader}: {msg.subject}")

        return self.results

    def _assign_task(self, task: SubTask) -> TeamMember | None:
        """Assign a task to the most relevant member."""
        if not self.members:
            return None
        # Simple: round-robin (subclass can override)
        return self.members[len(self.sub_tasks) % len(self.members)]

    def send_to_leader(self, to_leader: str, subject: str, body: str, ticket_id: str = ""):
        """Send a message to another Team Leader."""
        self.message_bus.send(self.name, to_leader, subject, body, ticket_id)

    def report(self) -> dict:
        """Generate a team report."""
        resolved = sum(1 for t in self.sub_tasks if t.status == "done")
        blocked = sum(1 for t in self.sub_tasks if t.status == "blocked")
        escalated = sum(1 for t in self.sub_tasks if t.status == "escalated")
        return {
            "team": self.name,
            "domain": self.domain,
            "mandate": self.mandate[:100],
            "sub_tasks": len(self.sub_tasks),
            "resolved": resolved,
            "blocked": blocked,
            "escalated": escalated,
            "results": self.results,
        }
