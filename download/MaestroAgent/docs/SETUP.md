# MaestroAgent — Setup, Install, Run

This document covers local install, dev mode, packaging, and troubleshooting.

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

## 2. Clone & bootstrap

```bash
git clone https://github.com/your-org/maestroagent.git
cd maestroagent
```

## 3. Backend setup

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
maestro config set openrouter.api_key $OPENROUTER_API_KEY   # or use keyring
maestro config set anthropic.api_key $ANTHROPIC_API_KEY
maestro config set default_provider ollama
maestro config set default_model llama3.1:8b
```

Secrets are stored in the OS keychain by default. To force env-var mode, set `MAESTRO_SECRETS_BACKEND=env`.

### Smoke test

```bash
maestro --version
maestro doctor
```

`maestro doctor` checks Python version, optional dependencies (Docker, Ollama), DB writability, and provider connectivity.

## 4. Desktop app — dev mode

```bash
cd desktop
pnpm install
pnpm tauri dev
```

The first run builds the Rust shell (1–3 min) and starts the Vite dev server. The Rust sidecar host will:

1. Locate the Python venv (set `MAESTRO_PYTHON` to override).
2. Spawn `maestro serve --port 8765`.
3. Stream its stdout into the UI's **Logs** panel.
4. Restart it on crash with exponential backoff.

## 5. Running workflows

### From the CLI

```bash
maestro run examples/build_saas_mvp.py --goal "Build a notes SaaS with auth + Stripe"
maestro run examples/research_crew.py --goal "Survey of retrieval-augmented generation, 2024"
```

### From the desktop UI

1. Open the app.
2. **Templates** → pick a workflow.
3. Set the goal, budget, and provider.
4. **Run**. Watch the dashboard stream traces, the agent tree grow, and the loop progress bar advance.

### Resuming after a crash

```bash
maestro resume <run_id>
```

All state is checkpointed per step, so resume is exact.

## 6. Running headless (server-only)

If you do not want the desktop app:

```bash
maestro serve --host 0.0.0.0 --port 8765
```

Then point any HTTP/WebSocket client at it. The OpenAPI schema is at `http://localhost:8765/docs`.

## 7. Production packaging

```bash
cd desktop
pnpm tauri build
```

Produces installers in `desktop/src-tauri/target/release/bundle/`. The Python sidecar is bundled as a PyInstaller-frozen executable in `desktop/src-tauri/binaries/` (see `scripts/build_sidecar.sh`).

## 8. Dev workflow

- Backend tests: `cd backend && pytest`
- Frontend lint: `cd desktop && pnpm lint`
- Type-check: `cd desktop && pnpm tsc --noEmit`
- Format: `black backend && ruff check backend && pnpm format`

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `maestro` not found after install | Ensure the venv is activated; or `pip install --user -e ./backend` |
| Tauri build fails on Linux | Install webkit2gtk and libgtk deps (see Tauri prereqs) |
| Ollama models not listed | `ollama pull llama3.1:8b` then `maestro doctor` |
| Port 8765 in use | `maestro serve --port 8766` and update `desktop/src-tauri/tauri.conf.json` |
| Sidecar won't start | Check Logs panel; set `MAESTRO_LOG=debug` for verbose output |

## 10. Docker compose (optional, for sandboxed tools)

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

The sandbox image ships git, docker-cli, node, python, and curl — nothing else. The core dispatches tool calls into this container via a small gRPC protocol.
