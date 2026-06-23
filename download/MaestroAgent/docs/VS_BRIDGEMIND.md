# MaestroAgent vs Bridgemind — Explicit Differentiation

This document is a candid, feature-by-feature comparison with Bridgemind.ai, based on public information about Bridgemind's BridgeSpace, BridgeMCP, BridgeMemory, and BridgeVoice. It is written for evaluators who are deciding between the two.

## TL;DR

Bridgemind is a polished **desktop-centric** vibe-coding platform with strong agent swarm UX. MaestroAgent is an **open-source, browser-first** Agent OS that beats Bridgemind on accessibility, openness, cost, and the depth of its looping/sub-agent primitives — at the cost of less polish in v0.1.

## Feature comparison

| Dimension | MaestroAgent | Bridgemind |
|---|---|---|
| **License** | MIT (fully open) | Proprietary |
| **Pricing** | Free forever; pay only for your own LLM usage | Credit-based with usage caps |
| **Self-hosting** | ✅ Docker Compose, one command | ❌ Cloud-only |
| **Browser access** | ✅ PWA (Chrome/Firefox/Brave/Edge) | ❌ Desktop-only |
| **Install on phone/tablet** | ✅ PWA installs on mobile | ❌ |
| **Data ownership** | ✅ All data on your machine/server | ⚠️ Vendor-hosted |
| **Vendor lock-in** | ✅ None — open formats, SQLite, Chroma | ⚠️ High |
| **Desktop app (optional)** | 🔜 Tauri wrapper planned (v0.3) | ✅ Native (BridgeSpace) |
| **Multi-terminal** | ✅ Web terminal + sandbox | ✅ BridgeSpace terminals |
| **Agent swarms** | ✅ Supervisor + dynamic sub-agents | ✅ Swarm UI |
| **Hierarchical sub-agents** | ✅ Spawn/debate/vote/critic | ⚠️ Flatter |
| **Verifiable loops (until tests pass)** | ✅ First-class | ❌ Manual |
| **Cron / webhook / file-event loops** | ✅ Native | ⚠️ Limited |
| **Nested / parallel / meta loops** | ✅ Native | ❌ |
| **Memory: knowledge graph** | ✅ NetworkX (Neo4j in v0.2) | ✅ BridgeMemory |
| **Memory: vector DB** | ✅ Chroma/PGVector | ⚠️ |
| **Memory: long-term episodic** | ✅ SQLite with tags + provenance | ⚠️ |
| **Voice control** | ✅ Web Speech API (multi-language) | ✅ BridgeVoice |
| **Editor integration** | 🔜 VS Code/Cursor (v0.3, superior to MCP) | ✅ BridgeMCP |
| **Model-agnostic routing** | ✅ Per-call routing + cost optimization | ⚠️ |
| **Cost tracking + budgets** | ✅ Per-run caps, real-time spend | ⚠️ Credit-based |
| **Failure recovery + checkpoint resume** | ✅ Per-step SQLite checkpoints | ⚠️ |
| **Audit log** | ✅ Tamper-evident hash chain | ⚠️ |
| **Sandboxed tool execution** | ✅ Docker (read-only, no network) | ⚠️ |
| **Self-improving meta-agent** | 🔜 v1.0 (behind flag) | ❌ |
| **Marketplace** | 🔜 v1.0 | ❌ |
| **Templates gallery** | ✅ Built-in + community (v1.0) | ⚠️ |
| **Visual graph builder** | ✅ ReactFlow drag-drop | ⚠️ |
| **Real-time observability** | ✅ WebSocket event stream | ✅ |
| **Collaboration (multi-user)** | 🔜 v0.3 | ⚠️ |

## Where MaestroAgent wins

### 1. Accessibility — browser-first, installable anywhere

Bridgemind requires a desktop install. MaestroAgent runs in any modern browser and installs as a PWA on:
- **Desktop:** Chrome, Edge, Brave, Firefox (macOS, Windows, Linux, ChromeOS)
- **Mobile:** Chrome on Android, Safari on iOS (iOS 16.4+ supports PWA install)
- **Tablet:** iPadOS, Android tablets

You can self-host on a $5/month VPS and access MaestroAgent from any device. Bridgemind cannot match this without a fundamental architecture shift.

### 2. Openness — MIT licensed, no vendor lock-in

Bridgemind is proprietary. Your agent graphs, memory, and templates live in their cloud. If they change pricing, shut down, or pivot, your work is at risk.

MaestroAgent is MIT-licensed. Your data lives in SQLite + Chroma files you own. The templates are Python files you can read, edit, and fork. If the project dies, your data and workflows survive.

### 3. Cost — no credit caps

Bridgemind uses credit-based pricing with usage caps. Users report hitting limits quickly on heavy use. MaestroAgent charges nothing — you pay only for the LLM API calls you make, at provider rates, with full cost visibility and per-run budget caps.

Run a 30-minute "build a SaaS MVP" workflow on Ollama (local): **$0**. The same on Bridgemind would burn credits.

### 4. Looping primitives — verifiable, nested, event-driven

Bridgemind has agent swarms but no first-class loop primitive. "Until tests pass" is a hand-rolled `while` hidden inside a node. MaestroAgent has:

- `LoopHandler` with verifiable exit conditions (tests, metrics, critic)
- Per-loop budgets (iterations, cost, wall-clock)
- Stagnation detection (auto-escalate if no progress)
- Nested loops, parallel loops, meta-loops
- Event-driven triggers (cron, webhook, file events)

This is the single biggest reliability win. A Bridgemind swarm that dies after 4 minutes becomes a MaestroAgent loop that runs for 4 hours, unattended, and resumes after a reboot.

### 5. Dynamic hierarchical sub-agents — not just flat swarms

Bridgemind's swarms are relatively flat. MaestroAgent supervisors spawn hierarchical sub-agents at runtime, with:
- Isolated contexts (children's transcripts don't bloat the parent)
- Auto-merge with conflict detection
- Debate / vote / critic primitives
- TTL eviction + quarantine for failing sub-agents

This is required for open-ended goals ("build a SaaS MVP") that cannot be planned in full up front.

### 6. Model-agnostic routing with cost optimization

Bridgemind picks a model at config time. MaestroAgent routes per-call based on capability, latency, and cost:
- A supervisor picking a model for low-stakes summarization → cheap model
- A critic scoring a final artifact → frontier model
- Per-call failover chain (claude-sonnet → gpt-4o → llama3.1:70b)
- Circuit breaker (failed providers taken out of rotation)
- Real-time cost tracking with per-run budget caps

### 7. Production reliability — checkpoints, audit, sandbox

- **Per-step SQLite checkpoints** — resume after crash, time-travel debug
- **Tamper-evident audit log** — hash-chained, verifiable
- **Docker sandbox** — read-only root, no network, resource limits
- **Model fallback** — automatic failover on provider failure
- **HITL gates** — pause before high-stakes tool calls

Bridgemind has some of these but not all, and not open.

## Where Bridgemind wins (honestly)

### 1. Polish

Bridgemind's BridgeSpace is a mature, polished native desktop ADE. MaestroAgent v0.1 is alpha-quality. The UI works but is less refined.

### 2. Editor integration

BridgeMCP connects Cursor, Claude Code, and other editors today. MaestroAgent's editor integration is v0.3.

### 3. Out-of-the-box experience

Bridgemind is a product you pay for and use immediately. MaestroAgent requires self-hosting setup (though `./install.sh` makes it one command).

### 4. Shared agent context UX

Bridgemind's BridgeSpace has thoughtful UX around shared agent context and file ownership to avoid conflicts. MaestroAgent has the primitives (memory scopes, RBAC) but less polished UX.

## The strategic bet

Bridgemind will keep iterating on desktop polish. MaestroAgent bets on:

1. **Open source** — community contributions outpace any single vendor.
2. **Browser-first** — accessibility beats polish for the long tail of users.
3. **Reliability primitives** — loops + sub-agents + verification are what make agents trustworthy for unattended work. Polish can be added; reliability cannot be retrofitted.
4. **No vendor lock-in** — users stay because the product is good, not because their data is held hostage.

## When to choose which

**Choose Bridgemind if:**
- You want a polished desktop ADE today.
- You're OK with credit-based pricing and cloud hosting.
- You don't need to self-host or customize the orchestrator.
- You primarily use Cursor/Claude Code and want tight editor integration now.

**Choose MaestroAgent if:**
- You want to own your data and workflows.
- You need browser/mobile access.
- You're building long-running, unattended agent workflows.
- You want to customize or extend the orchestrator (plugins, templates).
- You're cost-sensitive (run on local Ollama for $0).
- You're a developer who wants to read, fork, and contribute to the codebase.

## Migration path (from Bridgemind to MaestroAgent)

1. **Export your agent definitions** from Bridgemind (if export is available).
2. **Recreate them as MaestroAgent `AgentSpec` objects** (role/goal/backstory map directly).
3. **Recreate your workflows as templates** — Python files in `examples/templates/`.
4. **Import your knowledge graph** — MaestroAgent's `GraphMemory` accepts any NetworkX-compatible graph.
5. **Point MaestroAgent at your LLM providers** — set API keys in `.env`.

The agent definitions and workflows are the valuable part; the orchestrator is the commodity. MaestroAgent gives you a better orchestrator for free.
