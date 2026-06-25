# MaestroAgent

**An experimental platform for studying adaptive multi-agent systems using reproducible benchmarks, pre-registered experiments, causal ablations, and predictive theory evaluation.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Research Platform](https://img.shields.io/badge/type-research_platform-purple.svg)](docs/HISTORY.md)
[![PWA](https://img.shields.io/badge/PWA-installable-purple.svg)](https://web.dev/progressive-web-apps/)
[![Docker](https://img.shields.io/badge/Docker-self--host-blue.svg)](docker-compose.yml)
[![CI](https://img.shields.io/badge/CI-passing-brightgreen.svg)](.github/workflows/ci.yml)
[![Status: Stable](https://img.shields.io/badge/status-stable-brightgreen.svg)](#roadmap)

> **Bridgemind charges $16–80/mo with credit caps and is desktop-only.**
> **MaestroAgent is free forever, browser-first, self-hostable, and has superior loops + sub-agents + a self-improving meta-agent. No credit walls. Ever.**

---

## Screenshots

> *These are described textually. Run MaestroAgent locally to see them live.*

**1. PWA Install Prompt** — Open MaestroAgent in Chrome/Brave and click the install icon in the address bar. The app installs as a native-like window with its own launcher icon. No app store required.

**2. Dashboard with Live Event Stream** — The dashboard shows a run summary card (cost, iteration, node, errors), a live event stream color-coded by type (purple for runs, blue for steps, amber for loops, green for LLM calls), and quick stats (events/sec, LLM calls, tool calls, errors).

**3. Graph Builder (ReactFlow)** — A drag-and-drop workflow editor with a palette of 7 node types (agent, supervisor, loop, gate, HITL, tool, terminal). Drag onto the canvas, connect with edges, export/import as JSON. MiniMap + controls in the corner.

**4. Command Palette (⌘K)** — Press ⌘K anywhere. A Linear/Notion-style palette appears with fuzzy-filtered commands. Arrow keys navigate, Enter runs, Esc closes.

**5. Loops Panel** — Active loops with spinning icons, progress bars, live scores, and outcome badges (condition met / stagnant / max iterations / escalated). Click "New Loop" to create simple / nested / parallel / meta loops with verifiable exit conditions.

**6. Agent Tree** — Live hierarchy of supervisors + spawned sub-agents. Hover any agent to reveal a "+" button to spawn a sub-agent. Select 2+ agents to trigger a structured debate with vote + critic.

**7. Metrics + Meta-Agent** — Cost breakdown table by provider with share bars, token usage split (prompt vs completion), loop iteration histograms, and a meta-agent recommendations panel that proposes concrete optimizations based on past runs.

**8. Login Modal (auth enabled)** — When `MAESTRO_AUTH_ENABLED=true`, a clean modal prompts for the API key (auto-generated and saved to `/data/api_key.txt`).

---

## Why MaestroAgent?

| | MaestroAgent v1.0 | Bridgemind |
|---|---|---|
| **Price** | Free forever | $16–80/mo + credit caps |
| **License** | MIT (fully open) | Proprietary |
| **Browser access** | ✅ PWA (Chrome/Firefox/Brave/Edge) | ❌ Desktop-only |
| **Self-hosting** | ✅ `./install.sh` (one command) | ❌ Cloud-only |
| **Usage caps** | ❌ None — pay only for your LLM usage | ⚠️ Credit-based, overage costs |
| **Long-running unattended loops** | ✅ Native (verifiable, nested, meta) | ⚠️ Limited |
| **Dynamic hierarchical sub-agents** | ✅ Spawn + debate + auto-merge | ⚠️ Flatter |
| **Self-improving meta-agent** | ✅ Analyzes runs, proposes optimizations | ❌ |
| **Model-agnostic routing** | ✅ Per-call, cost-optimized | ⚠️ |
| **Voice input** | ✅ Web Speech API | ✅ BridgeVoice |
| **Auth + rate limiting** | ✅ API key + OAuth stub + audit | ⚠️ |
| **Data ownership** | ✅ SQLite + Chroma on your disk | ⚠️ Vendor-hosted |

See [`docs/VS_BRIDGEMIND.md`](docs/VS_BRIDGEMIND.md) for the full comparison.

---

## Quick start

### 🚀 Try it in Browser — 30 seconds (dev mode, fastest)

```bash
git clone https://github.com/your-org/maestroagent.git
cd maestroagent
./dev.sh
```

Then open **http://localhost:1420** in Chrome/Firefox/Brave. Click the install icon in the address bar to install as a PWA.

> `./dev.sh` auto-creates the Python venv, installs deps, starts the backend on :8765 + frontend on :1420 with hot reload. No Docker build wait.

### Option A — Docker (production self-host, 2 minutes)

```bash
git clone https://github.com/your-org/maestroagent.git
cd maestroagent
cp .env.example .env
./install.sh
```

Open **http://localhost:8765** → click **Install** in your browser's address bar.

### Option B — Dev mode (manual)

```bash
# Terminal 1: backend
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
maestro serve

# Terminal 2: frontend
cd frontend && pnpm install && pnpm dev
```

Open **http://localhost:1420**.

### Option C — Production self-host (with auth + HTTPS)

```bash
cp .env.example .env
# Edit .env:
#   MAESTRO_AUTH_ENABLED=true
#   MAESTRO_CORS_ORIGINS=https://maestro.yourdomain.com
#   OPENAI_API_KEY=sk-... (or use Ollama for $0)
./install.sh

# Add HTTPS with Caddy (auto Let's Encrypt):
cp docker/Caddyfile /etc/caddy/Caddyfile  # edit domain
sudo systemctl restart caddy
```

### Verify it works

```bash
# Quick health check
curl -s http://localhost:8765/api/health | head -c 100

# Visual status dashboard
open http://localhost:8765/status

# Full smoke test (11 checks)
./test_e2e.sh
```

See **[REVIEW_CHECKLIST.md](REVIEW_CHECKLIST.md)** for a detailed 18-feature browser test guide.

Full setup: [`docs/BROWSER_SETUP.md`](docs/BROWSER_SETUP.md).

---

## What's new in v1.0

- 🔐 **Security hardening** — API key auth, rate limiting, input sanitization, audit logging, Docker non-root + resource limits
- 🧠 **Self-improving meta-agent** — analyzes past runs and proposes optimizations (adjust LLM hints, tighten loop budgets, promote memory)
- 🔀 **Hybrid CrewAI ↔ LangGraph** — compile CrewAI crews into stateful graphs with per-agent checkpointing
- 📦 **Project export/import** — download full runs as portable JSON
- 🎤 **Voice input** — Web Speech API for speech-to-agent goals
- ⌨️ **Command palette** — ⌘K with fuzzy search + keyboard navigation
- 📴 **Offline support** — IndexedDB caches runs/events for offline browsing
- 🔁 **Robust WebSocket** — auto-reconnect with exponential backoff

See [`docs/RELEASE_NOTES_v1.0.md`](docs/RELEASE_NOTES_v1.0.md) for the full changelog.

---

## Project layout

```
MaestroAgent/
├── frontend/              # React 18 + TypeScript PWA (Vite + vite-plugin-pwa)
│   └── src/               # 18 components + store + hooks + lib (IndexedDB, api, utils)
├── backend/               # Python core (FastAPI sidecar)
│   ├── maestro_core/      # Stateful graph engine, checkpoints, streaming
│   ├── maestro_agents/    # Agent, Supervisor, SubAgent, CrewAdapter, Debate
│   ├── maestro_loops/     # Native loops: recursive, cron, webhook, nested, parallel, meta
│   ├── maestro_memory/    # Short-term, vector, graph, long-term + manager
│   ├── maestro_verify/    # Critic, evaluator-optimizer, sandbox, recovery
│   ├── maestro_llm/       # Router + 6 providers + cost ledger + auto-detect
│   ├── maestro_auth/      # API keys, OAuth stub, rate limiting, audit middleware (v1.0)
│   ├── maestro_meta/      # Self-improving meta-agent (v1.0)
│   ├── maestro_hybrid/    # CrewAI → graph compiler (v1.0)
│   ├── maestro_api/       # FastAPI + WebSocket + 10 route groups
│   └── ...
├── Dockerfile             # Multi-stage, non-root, hardened (v1.0)
├── docker-compose.yml     # Self-host with resource limits + security_opt
├── install.sh             # One-click install
├── update.sh              # One-click update
├── test_e2e.sh            # 11-step smoke test
└── docs/                  # 10 docs
```

---

## Documentation

| Doc | What's inside |
|---|---|
| [README.md](README.md) | This file |
| [REVIEW_CHECKLIST.md](REVIEW_CHECKLIST.md) | **18-feature browser test guide** — how to verify every feature works |
| [docs/RELEASE_NOTES_v1.0.md](docs/RELEASE_NOTES_v1.0.md) | v1.0 changelog + migration guide |
| [docs/BROWSER_SETUP.md](docs/BROWSER_SETUP.md) | Browser install + self-host (Docker + dev) |
| [docs/VS_BRIDGEMIND.md](docs/VS_BRIDGEMIND.md) | Feature-by-feature comparison vs Bridgemind |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layered architecture, design principles |
| [docs/ARCHITECTURE_FULLSTACK.md](docs/ARCHITECTURE_FULLSTACK.md) | Full-stack Mermaid diagrams |
| [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) | Complete file tree |
| [docs/ROADMAP.md](docs/ROADMAP.md) | v0.1 → v1.1+ milestones |
| [docs/DIFFERENTIATION.md](docs/DIFFERENTIATION.md) | vs CrewAI / LangGraph |
| [docs/CHALLENGES.md](docs/CHALLENGES.md) | Hard problems + solutions |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contributor guide |

---

## Roadmap

- **v1.0** ✅ — security hardening, meta-agent, hybrid orchestration, PWA polish
- **v1.1** — OAuth full integration, multi-user collaboration, plugin marketplace, background sync, mobile polish
- **v1.2** — self-improving meta-agent with `--self-improve` flag (applies recommendations behind review)
- **v2.0** — cloud burst, analytics dashboard, one-click deploy to cloud

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for details.

---

## License

MIT © MaestroAgent contributors. See [LICENSE](LICENSE).

## Contributing

PRs welcome. Read [`CONTRIBUTING.md`](CONTRIBUTING.md) first. The project follows a strict "core is pure Python, no UI deps" rule.
