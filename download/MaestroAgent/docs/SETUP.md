# MaestroAgent — Setup, Install, Run

This document covers local install, dev mode, packaging, and troubleshooting for the **full stack**: Python backend, Tauri Rust shell, and React frontend.

## 1. Prerequisites

| Tool | Version | Why |
|---|---|---|
| Python | 3.11+ | Backend core |
| Node.js | 20+ | Frontend build |
| pnpm | 9+ | Frontend package manager (npm also works) |
| Rust | stable (1.75+) | Tauri shell + sidecar host |
| Tauri 2 system deps | see [Tauri prereqs](https://v2.tauri.app/start/prerequisites/) | Desktop windowing / webview |
| SQLite | bundled | Default storage |
| *(optional)* Ollama | any recent | Local LLMs |
| *(optional)* LM Studio | any recent | Local LLMs |
| *(optional)* Docker | any recent | Sandboxed tool execution |

### Quick check

```bash
python3 --version    # 3.11+
node --version       # v20+
pnpm --version       # 9+
rustc --version      # 1.75+
```

## 2. Clone & bootstrap

```bash
git clone https://github.com/your-org/maestroagent.git
cd maestroagent
```

## 3. Backend (Python core) setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -e ".[dev]"
```

This installs the `maestro` CLI plus all core dependencies (`fastapi`, `langgraph`, `crewai`, `chromadb`, `networkx`, `pydantic`, `httpx`, `tenacity`, etc.).

### Configure providers

```bash
maestro config set ollama.base_url http://localhost:11434
maestro config set openrouter.api_key $OPENROUTER_API_KEY   # or use env var
maestro config set anthropic.api_key $ANTHROPIC_API_KEY
maestro config set default_provider ollama
maestro config set default_model llama3.1:8b
```

Secrets are stored in the OS keychain by default (`keyring`). To force env-var mode, set `MAESTRO_SECRETS_BACKEND=env`.

### Smoke test

```bash
maestro --version
maestro doctor
```

`maestro doctor` checks Python version, optional dependencies (Docker, Ollama), DB writability, and provider connectivity.

### Build the sandbox image (optional but recommended)

```bash
docker build -t maestroagent/sandbox:latest backend/sandbox/
```

This gives you isolated tool execution (Git, Docker, shell, tests). Without it, the engine falls back to local execution with a warning.

## 4. Frontend (Tauri + React) setup

```bash
cd desktop
pnpm install
```

This installs React, ReactFlow, Zustand, Tailwind, Tauri plugins, and all UI dependencies.

### Configure the sidecar URL

The frontend talks to the Python backend at `http://localhost:8765` by default. To change it, edit `desktop/src/store/appStore.ts`:

```typescript
sidecarUrl: "http://localhost:8765",
```

Or set the `MAESTRO_SIDECAR_URL` env var before `pnpm tauri dev`.

## 5. Running in dev mode

### Option A — Run backend + frontend separately (recommended for dev)

Terminal 1 (backend):
```bash
cd backend
source .venv/bin/activate
maestro serve --host 127.0.0.1 --port 8765
```

Terminal 2 (frontend):
```bash
cd desktop
pnpm tauri dev
```

The Tauri dev server runs Vite on port 1420 and opens the desktop window. The Rust shell will try to spawn the Python sidecar automatically — if you already started it in Terminal 1, the shell will detect it's already running and skip spawning.

### Option B — Let Tauri manage everything

```bash
cd desktop
pnpm tauri dev
```

The Rust shell will:
1. Locate the Python venv (or `python3` on PATH).
2. Spawn `python -m maestro_cli.main serve --port 8765`.
3. Pipe its stdout/stderr into the UI's Logs panel.
4. Restart it on crash with exponential backoff.

To force a specific Python interpreter: `export MAESTRO_PYTHON=/path/to/python` before `pnpm tauri dev`.

## 6. Running workflows

### From the CLI

```bash
maestro run examples/templates/build_saas_mvp.py --goal "Build a notes SaaS with auth + Stripe"
maestro run examples/templates/research_crew.py --goal "Survey of retrieval-augmented generation, 2024"
maestro run examples/templates/ops_autopilot.py --goal "Monitor prod API; fix 5xx spikes"
```

### From the desktop UI

1. Open the app.
2. **Templates** (left sidebar) → pick a workflow card.
3. Click **Configure & Run**.
4. In the modal: set the goal (or use 🎤 voice input), budget, provider.
5. **Launch Run**.
6. Watch the **Dashboard** stream live events.
7. Open **Agents** to see the supervisor spawn sub-agents.
8. Open **Loops** to watch verifiable cycles progress.
9. Open **Metrics** for cost + token breakdowns.

### Live control during a run

- **Spawn a sub-agent:** Agents panel → hover a supervisor → click **+**.
- **Trigger a debate:** Agents panel → select 2+ agents → click **Debate**.
- **Create a loop:** Loops panel → **New Loop** → pick body agent + exit condition.
- **Pause / cancel:** Top bar → **Cancel**.

### Resuming after a crash

```bash
maestro resume <run_id>
```

All state is checkpointed per step, so resume is exact. From the UI, the run will appear in the dashboard with a "paused" status and a **Resume** button.

## 7. Running headless (server-only, no desktop)

If you do not want the desktop app:

```bash
maestro serve --host 0.0.0.0 --port 8765
```

Then point any HTTP/WebSocket client at it. The OpenAPI schema is at `http://localhost:8765/docs`.

Example: start a run via curl:

```bash
curl -X POST http://localhost:8765/api/runs \
  -H "Content-Type: application/json" \
  -d '{"template": "build_saas_mvp", "goal": "Build a notes SaaS", "max_cost_usd": 5.0}'
```

Stream events via WebSocket:

```bash
# Requires websocat: cargo install websocat
websocat ws://localhost:8765/ws/<run_id>
```

## 8. Production packaging

### Build the Python sidecar (frozen binary)

```bash
./backend/scripts/build_sidecar.sh
```

This uses PyInstaller to produce a self-contained `maestro-sidecar` binary in `desktop/src-tauri/binaries/`. End users won't need Python installed.

### Build the desktop installer

```bash
cd desktop
pnpm tauri build
```

Produces installers in `desktop/src-tauri/target/release/bundle/`:
- **macOS:** `.dmg` and `.app`
- **Linux:** `.deb`, `.AppImage`, `.rpm`
- **Windows:** `.msi` and `.exe`

## 9. Dev workflow

| Task | Command |
|---|---|
| Backend tests | `cd backend && pytest` |
| Backend format | `cd backend && black . && ruff check .` |
| Backend type-check | `cd backend && mypy maestro_core maestro_agents` |
| Frontend lint | `cd desktop && pnpm lint` |
| Frontend type-check | `cd desktop && pnpm tsc --noEmit` |
| Frontend format | `cd desktop && pnpm format` |
| Build sandbox image | `docker build -t maestroagent/sandbox:latest backend/sandbox/` |

## 10. Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `MAESTRO_PYTHON` | (auto) | Python interpreter for sidecar |
| `MAESTRO_SIDECAR_URL` | `http://localhost:8765` | Sidecar URL for frontend |
| `MAESTRO_LOG` | `info` | Log level (`debug`, `info`, `warning`, `error`) |
| `MAESTRO_SECRETS_BACKEND` | `keyring` | `keyring` or `env` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `OPENAI_API_KEY` | — | OpenAI provider |
| `ANTHROPIC_API_KEY` | — | Anthropic provider |
| `OPENROUTER_API_KEY` | — | OpenRouter provider |
| `XAI_API_KEY` | — | Grok provider |

## 11. Docker compose (sandbox + sidecar)

```yaml
# docker-compose.yml
services:
  maestro-sandbox:
    image: maestroagent/sandbox:latest
    build: ./backend/sandbox
    privileged: false
    read_only: true
    network_mode: none
    volumes:
      - ./workspace:/workspace
```

```bash
docker compose up -d
maestro serve
```

The sandbox image ships git, docker-cli, node, python, curl, pytest, ruff, mypy — nothing else. The core dispatches tool calls into this container.

## 12. Troubleshooting

| Symptom | Fix |
|---|---|
| `maestro` not found after install | Ensure the venv is activated; or `pip install --user -e ./backend` |
| Tauri build fails on Linux | Install webkit2gtk and libgtk deps (see Tauri prereqs) |
| Tauri build fails on macOS | `xcode-select --install`; ensure Rust target matches |
| Ollama models not listed | `ollama pull llama3.1:8b` then `maestro doctor` |
| Port 8765 in use | `maestro serve --port 8766` and update `desktop/src/store/appStore.ts` |
| Sidecar won't start | Check Logs panel; set `MAESTRO_LOG=debug` for verbose output |
| WebSocket not connecting | Check the sidecar URL matches; ensure CSP allows `ws://localhost:8765` |
| Chroma errors on startup | `rm -rf .maestro/chroma` to reset; or use `InMemoryVectorMemory` (auto-fallback) |
| Voice input not working | Use a Chromium-based browser/webview; Safari/WebKit may not support SpeechRecognition |
| `spawn_subagent` 404 | Ensure the run is live (check `currentRun` in the dashboard); the sidecar must be running |

## 13. First-run checklist

1. ✅ `maestro doctor` passes (Python, deps, DB writable)
2. ✅ `ollama list` shows at least one model (or set an API key)
3. ✅ `maestro serve` starts without errors
4. ✅ Desktop app opens and shows "engine online" in the top bar
5. ✅ Templates gallery lists `build_saas_mvp` and `research_crew`
6. ✅ Starting the "blank" template produces events in the dashboard
7. ✅ (Optional) `docker build -t maestroagent/sandbox:latest backend/sandbox/` succeeds

Once all of the above pass, you're ready to run the flagship **Build SaaS MVP** template.
