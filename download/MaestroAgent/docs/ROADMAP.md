# MaestroAgent — Roadmap

This roadmap is deliberately conservative. Each milestone has a single reliability theme; features slip before reliability slips.

## v0.1 — Alpha (this release)

**Theme: the reliability core.**

- Stateful graph runtime with per-step checkpoints
- Native loops: recursive-until-verifiable, cron, webhook, file-event, nested, parallel
- Dynamic hierarchical sub-agents (supervisor + spawn + auto-merge)
- Multi-tier memory: short-term, semantic (Chroma), graph (NetworkX), long-term (SQLite)
- LLM router: Ollama, OpenAI, Anthropic, OpenRouter, Grok, LM Studio; cost tracking + budgets
- Verification: critic agent, evaluator-optimizer, Docker sandbox runner, failure recovery + model fallback
- FastAPI server with REST + WebSocket streaming
- Tauri desktop shell: dashboard, agent tree, loop progress, terminal, file browser, metrics
- CLI: `serve`, `run`, `resume`, `template`, `cost`, `doctor`
- Example workflows: build SaaS MVP, research crew, ops automation
- MIT license, full docs

**Exit criteria:** runs a 30-minute unattended "build a SaaS MVP" workflow end-to-end with crash-resume verified.

## v0.2 — Visual authoring

**Theme: make the graph builder as good as the engine.**

- Drag-and-drop visual graph builder with live code view sync
- Node palette: agent, supervisor, loop, gate, HITL, tool call, memory write, etc.
- Template gallery (in-app, local)
- Plugin marketplace scaffolding (registry API, signing, install flow)
- Evaluator-optimizer loop UI (iterate on a rubric)
- One-click "fork this run" — clone a finished run as an editable template

## v0.3 — Collaboration & burst

**Theme: teams and scale.**

- Multi-user real-time collaboration (CRDT-backed graph edits)
- Git-like workflow versioning: branch, merge, PR for agents/loops/templates
- Cloud burst: run sub-graphs on remote workers (Beam/Fargate) with results streamed back
- Voice + multimodal input (speech-to-agent, vision for screenshots/UI)
- Deep editor integration: VS Code, Cursor, JetBrains — superior protocol to MCP (typed, streaming, bidirectional)

## v0.4 — Verifiable autonomy

**Theme: trust the agent more, safely.**

- Formal verifier for graph invariants (no infinite loops, budget always honored)
- Provenance graph for every output (which agent, which tool, which model, which inputs)
- Compliance pack: SOC2-style audit export, PII redaction in logs
- Simulation mode: dry-run a workflow against synthetic LLM responses for CI

## v1.0 — General availability

**Theme: the ecosystem.**

- Self-improving meta-agent (behind an explicit `--self-improve` flag; never on by default)
- Marketplace for sharing agents/loops/templates (with ratings, cost stats, sandboxed trial)
- One-click deploy of built artifacts (web/mobile) via integrated deploy tools
- Analytics dashboard: cross-run insights, agent performance, cost trends
- Hardened sandbox: seccomp profiles, network policies, signed tool images
- Stable public API and plugin ABI

## Beyond v1.0 (research directions, not promised)

- Hierarchical reinforcement learning for supervisor policies
- On-device fine-tuning of specialist sub-agents from run traces
- Cross-machine agent mobility (agents that move to where data lives)
- Formal verification of generated artifacts (proof-carrying code for security-sensitive outputs)

## What we will NOT ship

- A closed-source "enterprise" edition that withholds core features. MaestroAgent is and will remain MIT.
- Telemetry that phones home. All analytics are local; the marketplace is the only networked feature and it is opt-in.
- A hosted SaaS that competes with users. The cloud burst feature lets users bring their own cloud.
