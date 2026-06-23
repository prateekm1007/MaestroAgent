# MaestroAgent — Browser Setup & Self-Hosting

MaestroAgent is **browser-first**. The primary interface is an installable Progressive Web App (PWA) that runs in Chrome, Firefox, Brave, and Edge. You can:

1. **Use it locally** — run the backend on your machine, open the PWA in your browser.
2. **Self-host on a VPS** — run via Docker Compose, access from anywhere.
3. **Install as a PWA** — click "Install" in your browser's address bar for a native-like app experience.

This document covers all three modes.

---

## Quick start (Docker — recommended)

The fastest way to get MaestroAgent running:

```bash
git clone https://github.com/your-org/maestroagent.git
cd maestroagent
cp .env.example .env        # edit to add API keys if you have them
./install.sh                # or: docker compose up -d --build
```

Then open **http://localhost:8765** in your browser.

To **install as a PWA**:
- **Chrome/Edge/Brave:** click the install icon (⊕) in the address bar.
- **Firefox:** click the home icon with a + in the address bar.
- The app will appear in your app launcher and open in its own window.

---

## Dev mode (no Docker)

For development, run the backend and frontend separately.

### Prerequisites

- **Python 3.11+**
- **Node.js 20+** and **pnpm 9+**
- *(optional)* **Ollama** for local LLMs

### 1. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
maestro doctor    # checks Python, deps, Ollama
maestro serve --host 127.0.0.1 --port 8765
```

### 2. Frontend (Vite dev server)

In a second terminal:

```bash
cd frontend
pnpm install
pnpm dev
```

Vite runs on **http://localhost:1420** and proxies `/api` and `/ws` to the backend on port 8765. Open **http://localhost:1420** in your browser.

The Vite config also enables the service worker in dev, so you can test PWA installability.

### 3. Generate PWA icons (one-time)

```bash
cd frontend
pip install cairosvg pillow   # if not already installed
python scripts/gen-icons.py
```

This generates `public/icons/icon-192.png`, `icon-512.png`, and `favicon.ico` from `public/icon.svg`.

---

## Self-hosting on a VPS

### Option A — Docker Compose (recommended)

```bash
# On your VPS:
git clone https://github.com/your-org/maestroagent.git
cd maestroagent
cp .env.example .env
# Edit .env: add API keys, set OLLAMA_BASE_URL if needed
nano .env

# Build and start
docker compose up -d --build

# Check it's running
curl http://localhost:8765/api/health
```

**Access from anywhere:** if your VPS has a public IP, open `http://YOUR_VPS_IP:8765`. For HTTPS, put a reverse proxy (Caddy, nginx, Traefik) in front:

```caddyfile
# Caddyfile — automatic HTTPS
maestro.yourdomain.com {
    reverse_proxy localhost:8765
}
```

```bash
caddy run --config Caddyfile
```

Now open `https://maestro.yourdomain.com` and install the PWA.

### Option B — Manual (no Docker)

```bash
# Install Python 3.11+ and Node 20+ on your VPS
git clone https://github.com/your-org/maestroagent.git
cd maestroagent

# Build the frontend
cd frontend && pnpm install && pnpm build && cd ..

# Install and run the backend (serves the built frontend)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e .
export MAESTRO_FRONTEND_DIST=/path/to/maestroagent/frontend/dist
maestro serve --host 0.0.0.0 --port 8765
```

The backend auto-detects `frontend/dist/` and serves the PWA bundle at `/`.

---

## PWA features

| Feature | Status |
|---|---|
| Installable in Chrome/Edge/Brave | ✅ |
| Installable in Firefox | ✅ |
| Offline app shell (cached) | ✅ |
| Offline API calls | ❌ (requires backend) |
| Push notifications | 🔜 v0.2 |
| Background sync | 🔜 v0.2 |
| App shortcuts (New Run, Templates) | ✅ |

### Offline behavior

The service worker caches the app shell (HTML, JS, CSS, icons). When offline:
- The app still opens and renders.
- The dashboard shows an "offline" indicator.
- API calls fail gracefully — the UI shows "engine offline".
- When connectivity returns, the UI auto-reconnects.

You cannot run agents offline (they need the backend + LLM providers), but you can browse past runs, view metrics, and edit graph templates.

---

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Ollama endpoint (host networking for Docker) |
| `OPENAI_API_KEY` | — | OpenAI provider |
| `ANTHROPIC_API_KEY` | — | Anthropic provider |
| `OPENROUTER_API_KEY` | — | OpenRouter provider |
| `XAI_API_KEY` | — | Grok provider |
| `MAESTRO_LOG` | `info` | Log level |
| `MAESTRO_FRONTEND_DIST` | `frontend/dist` | Path to built PWA bundle |
| `MAESTRO_DB_PATH` | `maestro.db` | SQLite path |
| `MAESTRO_CHROMA_PATH` | `.maestro/chroma` | Chroma vector store |
| `MAESTRO_GRAPH_PATH` | `.maestro/graph.json` | Graph memory persistence |
| `VITE_API_URL` | (auto) | Frontend override for backend URL (dev only) |

---

## Data persistence

| Docker volume | Mount | Contents |
|---|---|---|
| `maestro-data` | `/data` | SQLite DB, Chroma, graph memory |
| `maestro-workspace` | `/workspace` | Generated files (code, artifacts) |

To back up:
```bash
docker compose exec maestro tar czf - /data > maestro-backup.tar.gz
```

To reset:
```bash
docker compose down -v   # -v removes volumes
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| PWA not installable | Use Chrome/Edge/Brave; ensure HTTPS (or localhost); check `manifest.webmanifest` loads |
| "engine offline" in UI | Backend not running; check `docker compose logs maestro` |
| Ollama not reachable from Docker | Set `OLLAMA_BASE_URL=http://host.docker.internal:11434`; on Linux add `extra_hosts` (already in compose) |
| WebSocket not connecting | Ensure no proxy strips `Upgrade` headers; Caddy/nginx need `proxy_set_header Upgrade $http_upgrade` |
| 404 on /api routes | You're hitting the SPA fallback; ensure backend started before frontend requests |
| Icons missing after build | Run `python frontend/scripts/gen-icons.py` |
| Port 8765 in use | Change in `docker-compose.yml`: `"8766:8765"` and `maestro serve --port 8766` |

---

## First-run checklist

1. ✅ `docker compose up -d` succeeds
2. ✅ `curl http://localhost:8765/api/health` returns `{"status":"ok",...}`
3. ✅ Browser opens `http://localhost:8765` and shows the dashboard
4. ✅ "Install" button appears in browser address bar
5. ✅ After install, app opens in its own window
6. ✅ Templates gallery lists `build_saas_mvp`, `research_crew`, `ops_autopilot`
7. ✅ Starting the "blank" template produces events in the dashboard
8. ✅ (Optional) `ollama list` shows at least one model on the host

Once all pass, you're ready to run the flagship **Build SaaS MVP** template.
