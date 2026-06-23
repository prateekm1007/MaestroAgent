# MaestroAgent — Challenges & Solutions

This document is honest about the hard problems in agent orchestration and how MaestroAgent addresses each. It is intended for contributors and skeptical evaluators.

## Challenge 1 — Debugging complex graphs

**Problem.** A 20-node graph with conditional edges, parallel branches, and nested loops produces execution traces that are impossible to read as a flat log. When a run fails, the question "which node, on which iteration, with which inputs" is often unanswerable from logs alone.

**Solution.**

- **Per-step checkpoints.** Every node invocation writes a `STEP` row with full input/output state to SQLite. The run is fully reconstructable from the checkpoint store alone.
- **Trace tree, not trace log.** The UI renders a run as a tree: run → iteration → step → sub-step → tool call → LLM call. Each level is filterable and expandable.
- **Time-travel debugging.** Pick any past step, inspect its state, and "fork from here" — clone the run starting at that step with edited state. This turns debugging from "reproduce" into "replay."
- **Deterministic replay.** LLM calls are cached by `(provider, model, prompt, temperature)` hash. A replay with the cache hot re-runs the exact same trace without spending tokens.

**What we don't claim.** Non-deterministic providers (high temperature) will diverge on replay. We surface this in the UI with a "deterministic" badge per step.

## Challenge 2 — Token costs on long runs

**Problem.** A 30-minute "build a SaaS MVP" run can easily cost $20–$50 on a frontier model. Users get burned once and never come back.

**Solution.**

- **Per-run budgets.** Every run has a `max_cost_usd`. The LLM router refuses calls that would exceed the budget; the run escalates to HITL instead of silently overspending.
- **Per-call routing.** A supervisor picking a model for a low-stakes summarization gets a cheap model; a critic scoring a final artifact gets a frontier model. The router decides per-call, not per-run.
- **Context compaction.** Sub-agents receive *summaries* of children's transcripts, not full transcripts. A 50k-token child transcript becomes a 2k-token summary in the parent's context.
- **Prompt caching.** System prompts and tool schemas are cached per-provider where supported (Anthropic, OpenAI). Repeated structure does not re-bill.
- **Live cost dashboard.** The UI shows spend in real time, broken down by agent, model, and call type. Users see a burn rate and can pause.

**What we don't claim.** Frontier models still cost real money. We give users the knobs to spend less; we don't pretend costs are zero.

## Challenge 3 — Infinite loops and runaway agents

**Problem.** "Until tests pass" can run forever if the agent keeps making the same mistake. Budgets prevent bankruptcy but not wasted time.

**Solution.**

- **Per-loop iteration caps.** Every loop has a `max_iterations`. Hitting it triggers the `on_exceed` policy: `escalate`, `pause`, or `fail`.
- **Progress detectors.** A loop can declare a "progress signal" — e.g. `test_count must increase or pass_rate must improve by ≥ 1% per iteration`. Stagnation triggers escalation even before the cap.
- **Critic veto.** A critic agent reviews every Kth iteration. If the critic reports "no meaningful change since last review," the loop escalates.
- **Quarantine.** A sub-agent that fails N times in a row is quarantined: it cannot be re-spawned for the rest of the run, and its parent is notified.

**What we don't claim.** We can detect stagnation; we cannot detect "subtly wrong direction." The HITL pause is the final safety net.

## Challenge 4 — Sub-agent context explosion

**Problem.** A supervisor that spawns 5 sub-agents and reads all their transcripts drowns in tokens. Naive "just give the parent everything" does not scale.

**Solution.**

- **Summary-only by default.** Parents see children's summaries, not transcripts. A child can be queried for detail on demand (`SubAgent.recall(query)`).
- **Tiered recall.** A parent that needs more detail can ask the child's memory tier (vector + graph) for specific facts, retrieved by query, not by full dump.
- **TTL eviction.** Idle sub-agents are evicted after a configurable TTL. Their summaries are persisted; their contexts are released.
- **Shared vs private.** A sub-agent can mark outputs as `shared` (visible to all siblings) or `private` (visible only to parent). This prevents cross-contamination.

**What we don't claim.** Cross-agent reasoning over full transcripts is fundamentally expensive. We make the common case cheap; the rare case is still possible via explicit recall.

## Challenge 5 — Provider failures and rate limits

**Problem.** Any provider will rate-limit you, 500 you, or silently degrade. A single-provider orchestrator dies on the first outage.

**Solution.**

- **Per-provider health.** The router tracks rolling latency and error rates per provider. A degraded provider is deprioritized, not removed.
- **Failover chains.** Each call specifies a failover chain (`[claude-sonnet, gpt-4o, llama3.1:70b-via-openrouter]`). The router tries them in order with backoff.
- **Idempotent retries.** Tool and LLM calls carry an idempotency key. A retried call after a timeout does not double-charge or double-execute.
- **Circuit breakers.** A provider that fails N times in M seconds is circuit-broken for a cooldown. The router pretends it does not exist during cooldown.

**What we don't claim.** A total internet outage will stop your run. We resume from the last checkpoint when connectivity returns.

## Challenge 6 — Sandboxing untrusted tool execution

**Problem.** An agent with shell access is one prompt injection away from `rm -rf` or exfiltration.

**Solution.**

- **Default deny.** Tools run inside a Docker container with a read-only root, no network by default, and a per-run workspace volume.
- **Egress allowlist.** Network access, when granted, is to a per-run allowlist of domains. The allowlist is part of the template, not the agent.
- **Role-tagged tools.** Tools declare required roles; agents declare their roles. The engine refuses mismatches.
- **Audit every call.** Every tool invocation is logged with agent, role, tool, args, result, and duration. The log is append-only and hash-chained.
- **HITL gates.** Templates can mark specific tools (e.g. `cloud.deploy`, `db.drop`) as HITL-gated: the run pauses and waits for human approval before each call.

**What we don't claim.** Docker is not a security boundary against a determined attacker with a kernel exploit. For high-stakes deployments, run the sandbox on a separate VM.

## Challenge 7 — Reproducibility across machines

**Problem.** A workflow that works on your laptop fails on your colleague's because of a different Python version, a missing model, or a different Docker version.

**Solution.**

- **Pinned template manifests.** Every template carries a manifest: Python version, plugin versions, model IDs, sandbox image digest. The engine refuses to run if the environment does not match.
- **`maestro doctor`.** Verifies the environment against the manifest before the run starts. Missing pieces are reported with install instructions.
- **Frozen sidecar.** The desktop app bundles a PyInstaller-frozen Python sidecar so the user's system Python is irrelevant.
- **Model pinning.** Models are referenced by ID + digest where supported (Ollama). A different machine pulling the same ID gets the same weights.

**What we don't claim.** Closed-weights providers (OpenAI, Anthropic) can change model behavior without notice. We pin the model ID but cannot pin the weights.

## Challenge 8 — Observability without a paid SaaS

**Problem.** LangSmith is great but paid and hosted. Local-first users need the same insight without the cloud dependency.

**Solution.**

- **Unified event bus.** Every layer emits typed events (`StepStarted`, `LLMCallCompleted`, `ToolCallFailed`, `LoopIterationCompleted`, etc.) onto an in-process `asyncio` bus.
- **SQLite trace store.** Events are persisted to SQLite with a stable schema. The UI is just a consumer.
- **WebSocket streaming.** The FastAPI server republishes events over WebSocket. Any client (desktop UI, CLI, external hook) can subscribe.
- **OpenTelemetry export.** For users who already have observability stacks, an OTel exporter is a one-line config.

**What we don't claim.** We do not provide cross-run analytics comparable to a hosted product out of the box; that is a v1.0 feature.

## Challenge 9 — Plugin safety

**Problem.** A plugin ecosystem without safety is a supply-chain nightmare.

**Solution.**

- **Sandboxed plugin mode (v0.2).** Untrusted plugins run out-of-process with a capability-restricted RPC surface. They cannot touch the filesystem or network except through declared capabilities.
- **Signed manifests.** Plugins declare their capabilities in a signed manifest. The registry verifies signatures before listing.
- **Per-run isolation.** Each run loads its own plugin set; plugins cannot mutate global engine state.
- **Audit.** Plugin calls are logged identically to tool calls.

**What we don't claim.** v0.1 plugins run in-process for performance. Treat v0.1 plugins as trusted code. The sandboxed mode is the v0.2 priority.

## Challenge 10 — The "agent that optimizes itself" risk

**Problem.** A self-improving meta-agent that rewrites core code is a fascinating demo and a terrifying production feature.

**Solution.**

- **Behind a flag.** `--self-improve` is off by default and will remain so until v1.0 at the earliest.
- **Scope-limited.** When on, the meta-agent can only modify *template* code and *plugin* code, never the engine core.
- **Review-required.** Every proposed change is queued for human review before being applied. The meta-agent drafts; the human merges.
- **Rollback.** Every applied change is a git commit on a `meta-agent` branch. `git revert` undoes any change.

**What we don't claim.** We do not claim self-improvement is safe. We claim it is *possible* to do responsibly, and we are building the guardrails before the feature.
