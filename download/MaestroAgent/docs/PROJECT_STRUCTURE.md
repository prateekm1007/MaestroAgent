# MaestroAgent — Complete Project Folder Structure

This document is the canonical map of the repository. Every file is listed with a one-line description of its role.

```
MaestroAgent/
├── README.md                          # Project overview, quick start, differentiators
├── LICENSE                            # MIT
├── docs/
│   ├── ARCHITECTURE.md                # Layered architecture + Mermaid diagrams
│   ├── SETUP.md                       # Full local + dev setup instructions
│   ├── ROADMAP.md                     # v0.1 → v1.0+ milestones
│   ├── DIFFERENTIATION.md             # vs CrewAI / LangGraph / Bridgemind
│   ├── CHALLENGES.md                  # Hard problems + how we solve them
│   └── PROJECT_STRUCTURE.md           # This file
│
├── backend/                           # Python orchestration core (FastAPI sidecar)
│   ├── pyproject.toml                 # Package metadata, deps, tool config
│   │
│   ├── maestro_core/                  # Stateful graph runtime
│   │   ├── __init__.py                # Public API exports
│   │   ├── state.py                   # State, StateSchema, RunStatus
│   │   ├── graph.py                   # Graph, Node, Edge, ConditionalEdge, ParallelEdges
│   │   ├── context.py                 # RunContext, RunConfig (service locator)
│   │   ├── checkpoint.py              # SQLite checkpoint store + tamper-evident audit
│   │   ├── streaming.py               # EventBus, Event, EventType (typed pub-sub)
│   │   └── engine.py                  # OrchestrationEngine (walks the graph)
│   │
│   ├── maestro_agents/                # Agent primitives
│   │   ├── __init__.py
│   │   ├── base.py                    # BaseAgent (role/goal/backstory + LLM call)
│   │   ├── supervisor.py              # Supervisor (decompose + spawn + merge + decide)
│   │   ├── subagent.py                # SubAgent (dynamic child, auto-merge, TTL, quarantine)
│   │   ├── crew.py                    # CrewAdapter (CrewAI Crew → graph node)
│   │   └── debate.py                  # Debate (positions → critiques → revise → vote)
│   │
│   ├── maestro_loops/                 # Native advanced loops
│   │   ├── __init__.py
│   │   ├── types.py                   # LoopKind, BackoffPolicy, OnExceedAction, triggers
│   │   ├── conditions.py              # TestPass, MetricThreshold, Critic, AllOf, AnyOf
│   │   ├── handler.py                 # LoopHandler (verifiable exit, budgets, stagnation)
│   │   └── nested.py                  # NestedLoop, ParallelLoop, MetaLoop
│   │
│   ├── maestro_memory/                # Multi-tier memory
│   │   ├── __init__.py
│   │   ├── short_term.py              # Bounded rolling window + auto-summarization
│   │   ├── long_term.py               # SQLite episodic store with tags + provenance
│   │   ├── vector.py                  # InMemory + Chroma vector memory backends
│   │   ├── graph.py                   # NetworkX graph memory (entity relationships)
│   │   └── manager.py                 # MemoryManager (unified write/recall, RBAC)
│   │
│   ├── maestro_verify/                # Verification & governance
│   │   ├── __init__.py
│   │   ├── critic.py                  # LLM-as-judge scorer (independent of executor)
│   │   ├── evaluator.py               # EvaluatorOptimizer (generate→eval→optimize→regen)
│   │   ├── sandbox.py                 # Docker sandboxed command execution
│   │   ├── recovery.py                # FailureRecovery + FallbackPolicy (circuit breaker)
│   │   └── registry.py                # VerifierRegistry (pytest, ruff, mypy builtins)
│   │
│   ├── maestro_llm/                   # Model-agnostic LLM router
│   │   ├── __init__.py
│   │   ├── cost.py                    # CostLedger, ModelPricing, DEFAULT_PRICING
│   │   ├── providers.py               # Ollama, OpenAI, Anthropic, OpenRouter, Grok, LMStudio
│   │   └── router.py                  # LLMRouter (per-call routing, failover, caching)
│   │
│   ├── maestro_api/                   # FastAPI HTTP/WebSocket boundary
│   │   ├── __init__.py
│   │   ├── main.py                    # create_app factory + CORS + lifespan
│   │   ├── state.py                   # AppState (shared services, run tasks, live buses)
│   │   ├── websocket.py               # /ws/{run_id} event streaming
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── health.py              # /api/health, /api/doctor
│   │       ├── runs.py                # /api/runs (start, list, get, resume, cancel, audit)
│   │       ├── live.py                # /api/runs/{id}/spawn|debate|loops|live (HITL control)
│   │       ├── agents.py              # /api/agents (list, tree)
│   │       ├── loops.py               # /api/loops/{run_id}/loops
│   │       ├── memory.py              # /api/memory (recall, promote, episodes)
│   │       ├── templates.py           # /api/templates
│   │       └── costs.py               # /api/costs (per-run + aggregate)
│   │
│   ├── maestro_plugins/               # Plugin system
│   │   ├── __init__.py
│   │   ├── registry.py                # PluginRegistry + PluginEntry
│   │   ├── loader.py                  # Filesystem + entry-point discovery
│   │   └── builtin_tools.py           # shell, git_status, file_read, file_write, http_get
│   │
│   ├── maestro_cli/                   # `maestro` command-line tool
│   │   ├── __init__.py
│   │   └── main.py                    # serve, run, resume, list, cost, config, doctor
│   │
│   ├── plugins/                       # User-dropped plugins (auto-discovered)
│   │   └── web_search.py              # Example plugin
│   │
│   ├── examples/
│   │   └── templates/
│   │       ├── build_saas_mvp.py      # Supervisor + build loop + polish (flagship demo)
│   │       └── research_crew.py       # Researcher → synthesizer → critic loop
│   │
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_core_engine.py        # Linear graph, conditional edges, checkpoints, audit
│   │   ├── test_loops.py              # Exit-on-condition, max-iters, escalate
│   │   └── test_memory.py             # Write/recall, promote, graph edges
│   │
│   ├── sandbox/                       # Docker sandbox image
│   │   ├── Dockerfile                 # Read-only root, git/docker-cli/node/python/curl
│   │   └── entrypoint.sh              # sleep infinity (long-lived container)
│   │
│   └── scripts/
│       └── build_sidecar.sh           # PyInstaller freeze for bundled desktop app
│
├── desktop/                           # Tauri 2 desktop shell
│   ├── package.json                   # React + Tauri + ReactFlow + Zustand + Tailwind
│   ├── tsconfig.json                  # TS strict config
│   ├── tsconfig.node.json             # Vite config TS
│   ├── vite.config.ts                 # Vite dev server (port 1420)
│   ├── tailwind.config.js             # Maestro brand palette
│   ├── postcss.config.js
│   ├── index.html                     # SPA entry
│   │
│   ├── src/
│   │   ├── main.tsx                   # React root
│   │   ├── App.tsx                    # Shell layout + status bar + modals
│   │   ├── store/
│   │   │   └── appStore.ts            # Zustand store (runs, events, live state, modals)
│   │   ├── hooks/
│   │   │   └── index.ts               # useTauriEvent, useTauriCommand, useVoiceInput, etc.
│   │   ├── styles/
│   │   │   └── globals.css            # Tailwind layers + ReactFlow overrides
│   │   ├── lib/                       # (reserved for utils)
│   │   └── components/
│   │       ├── Sidebar.tsx            # Nav rail (8 views)
│   │       ├── TopBar.tsx             # Status, cancel, new run
│   │       ├── Dashboard.tsx          # Run summary + event stream + quick stats
│   │       ├── RunSummaryCard.tsx     # Cost/iter/node/errors card
│   │       ├── QuickStats.tsx         # Events/sec, LLM/tool calls, errors
│   │       ├── EventStream.tsx        # Live event log with type colors
│   │       ├── GraphBuilder.tsx       # ReactFlow editor + drag palette + export/import
│   │       ├── AgentTree.tsx          # Hierarchy tree + spawn + debate selection
│   │       ├── LoopsPanel.tsx         # Loop monitor + create button + progress bars
│   │       ├── Terminal.tsx           # Console-style event log
│   │       ├── FileBrowser.tsx        # Workspace file tree
│   │       ├── Metrics.tsx            # Cost breakdown table + token usage + histograms
│   │       ├── TemplatesGallery.tsx   # One-click templates + marketplace stub
│   │       ├── StartRunModal.tsx      # Goal + voice input + budget + provider picker
│   │       ├── SpawnSubagentModal.tsx # Spawn sub-agent under a supervisor
│   │       ├── DebateModal.tsx        # Trigger debate between selected agents
│   │       └── CreateLoopModal.tsx    # Define verifiable loop (tests/metric/critic)
│   │
│   └── src-tauri/                     # Rust shell
│       ├── Cargo.toml                 # Tauri 2 + plugins + reqwest + tokio
│       ├── build.rs                   # Tauri build script
│       ├── tauri.conf.json            # Window, security CSP, bundle config
│       ├── capabilities/
│       │   └── default.json           # Tauri ACL permissions
│       ├── icons/                     # App icons (placeholder — add real PNGs)
│       └── src/
│           ├── main.rs                # Entry point (windows_subsystem)
│           ├── lib.rs                 # App builder + sidecar spawn + health check
│           └── commands.rs            # 17 Tauri commands (proxy to Python sidecar)
│
└── .github/                           # (reserved for CI/CD — not in v0.1)
    └── workflows/
```

## File count summary

| Area | Files | LOC (approx) |
|---|---|---|
| Backend core (`maestro_core`) | 7 | ~900 |
| Backend agents | 6 | ~700 |
| Backend loops | 5 | ~600 |
| Backend memory | 6 | ~600 |
| Backend verify | 6 | ~500 |
| Backend LLM | 4 | ~500 |
| Backend API | 10 | ~600 |
| Backend plugins + CLI | 5 | ~500 |
| Backend examples + tests | 6 | ~400 |
| Desktop React | 19 | ~1800 |
| Desktop Rust | 4 | ~450 |
| Docs | 6 | ~1200 |
| **Total** | **~94 files** | **~8,250 LOC** |

## Key design boundaries

1. **`maestro_core` has zero UI deps.** Pure Python, testable headlessly.
2. **`maestro_api` is the only HTTP boundary.** Everything inside it is library code.
3. **The Rust shell is a thin supervisor.** It does not interpret graph state — it ferries JSON between React and the Python sidecar.
4. **React is a consumer of the event bus**, not a special case. The WebSocket endpoint is the same interface any external client would use.
5. **Plugins are discovered, not configured.** Drop a `.py` file in `backend/plugins/` and it loads.
