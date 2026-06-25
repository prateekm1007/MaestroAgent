"""Template: ops automation — monitor, diagnose, fix, deploy.

Demonstrates event-driven loops (cron + webhook + file watch) and
HITL gating before production deployments.

Usage
-----
    maestro run examples/templates/ops_autopilot.py --goal "Monitor prod API; fix 5xx spikes"

Flow
----
    entry → monitor_loop (cron: every 5 min)
          → diagnose (if anomaly detected)
          → fix_loop (until tests pass or budget hit)
          → hitl_review (human approval before deploy)
          → deploy
          → done
"""

from __future__ import annotations

from typing import Any

from maestro_agents.base import AgentSpec, BaseAgent
from maestro_loops.conditions import (
    CallableCondition,
    ConditionResult,
    CriticCondition,
    MetricThresholdCondition,
)
from maestro_loops.handler import LoopHandler, LoopSpec
from maestro_loops.types import OnExceedAction
from maestro_core.graph import Graph, Node
from maestro_core.state import RunStatus, State


def build_graph(goal: str, **extras: Any) -> Graph:
    g = Graph()

    # --- Monitor agent: checks metrics every iteration ---
    monitor = BaseAgent(
        id="monitor",
        spec=AgentSpec(
            role="SRE Monitor",
            goal=f"Check production health metrics for: {goal}",
            backstory=(
                "Veteran SRE. Knows the difference between a blip and an incident. "
                "Reads dashboards before pagers."
            ),
            tools=["http_get", "shell"],
            llm_hint={"provider": "ollama", "model": "llama3.1:8b"},
            memory_scope="shared",
            temperature=0.1,
        ),
    )
    g.add_node(Node(id="monitor", fn=monitor, description="Cron-triggered monitor"))

    # --- Diagnose agent: root-causes anomalies ---
    diagnose = BaseAgent(
        id="diagnose",
        spec=AgentSpec(
            role="Senior Diagnostic Engineer",
            goal="Identify the root cause of the anomaly. Produce a fix plan.",
            backstory=(
                "Distributed systems expert. Writes postmortems that don't blame people."
            ),
            tools=["shell", "file_read", "git_status", "http_get"],
            llm_hint={"provider": "ollama", "model": "llama3.1:8b"},
            memory_scope="shared",
            temperature=0.2,
        ),
    )
    g.add_node(Node(id="diagnose", fn=diagnose, description="Root-cause the anomaly"))

    # --- Fix agent: implements the fix ---
    fix_agent = BaseAgent(
        id="fixer",
        spec=AgentSpec(
            role="Senior Fix Engineer",
            goal="Implement the fix described by the diagnostician.",
            backstory="Pragmatic coder. Writes tests first, ships small diffs.",
            tools=["shell", "file_read", "file_write", "git_status"],
            llm_hint={"provider": "ollama", "model": "llama3.1:8b"},
            memory_scope="shared",
        ),
    )

    async def _fix_body(state: State, ctx) -> State:
        return await fix_agent(state, ctx)

    # Loop: fix → test until tests pass OR error rate drops.
    fix_loop = LoopHandler(
        spec=LoopSpec(
            id="fix_until_green",
            body=_fix_body,
            exit_condition=MetricThresholdCondition(
                metric_key="error_rate",
                threshold=0.01,
                comparator="<=",
                name="error_rate",
            ),
            max_iterations=10,
            max_cost_usd=3.0,
            on_exceed=OnExceedAction.ESCALATE,
            stagnation_window=3,
            stagnation_min_improvement=0.02,
        )
    )
    g.add_node(Node(id="fix_loop", fn=fix_loop, description="Fix until error_rate ≤ 1%"))

    # --- HITL gate: human must approve before deploy ---
    async def _hitl(state: State, ctx) -> State:
        # Pause for human review.
        return state.with_updates(
            status=RunStatus.AWAITING_HUMAN,
            metadata={
                **state.metadata,
                "hitl_reason": "approve_deploy",
                "hitl_prompt": "Review the fix and approve deployment to production.",
            },
        )
    g.add_node(Node(id="hitl_review", fn=_hitl, description="Human approval gate"))

    # --- Deploy agent ---
    deploy = BaseAgent(
        id="deployer",
        spec=AgentSpec(
            role="Deploy Engineer",
            goal="Deploy the approved fix to production. Verify rollout.",
            backstory=(
                "Blue-green deploy specialist. Never ships on Fridays without a rollback plan."
            ),
            tools=["shell", "http_get"],
            llm_hint={"provider": "ollama", "model": "llama3.1:8b"},
            memory_scope="shared",
        ),
    )
    g.add_node(Node(id="deploy", fn=deploy, description="Deploy to production"))

    # --- Done ---
    async def _done(state: State, ctx) -> State:
        return state.with_updates(status=RunStatus.SUCCEEDED)
    g.add_node(Node(id="done", fn=_done, description="Finalize"))

    # --- Edges ---
    # monitor → diagnose only if anomaly detected (else loop back to monitor).
    g.add_conditional_edge(
        "monitor", "diagnose",
        condition=lambda s: s.metadata.get("anomaly_detected", False),
    )
    # If no anomaly, the monitor would loop back (in production via cron).
    # For this template, we just end after one pass if no anomaly.
    g.add_conditional_edge(
        "monitor", "done",
        condition=lambda s: not s.metadata.get("anomaly_detected", False),
    )
    g.add_edge("diagnose", "fix_loop")
    g.add_edge("fix_loop", "hitl_review")
    g.add_edge("hitl_review", "deploy")
    g.add_edge("deploy", "done")
    g.set_entry("monitor")

    return g
