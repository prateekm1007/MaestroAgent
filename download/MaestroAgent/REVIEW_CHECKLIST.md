# MaestroAgent — Browser Review Checklist

This document lists every major feature with exact steps to test it in the browser. Use this to verify a deployment is fully functional.

## Prerequisites

Before testing, ensure the backend is running:

```bash
# Option A: dev mode (fastest)
./dev.sh

# Option B: Docker
./install.sh
```

Then open **http://localhost:1420** (dev) or **http://localhost:8765** (Docker) in Chrome, Firefox, or Brave.

---

## 1. Backend Health

**What**: The FastAPI backend is running and reachable.

**Test steps**:
1. Open **http://localhost:8765/api/health** in your browser.
2. ✅ You should see JSON: `{"status":"ok","version":"1.0.0","providers":[...],...}`
3. Open **http://localhost:8765/status** for a visual dashboard.
4. Open **http://localhost:8765/docs** for the interactive API docs.

**If failing**: Check `docker compose logs maestro` or the dev.sh terminal output.

---

## 2. PWA Installation

**What**: MaestroAgent is installable as a Progressive Web App.

**Test steps**:
1. Open **http://localhost:8765** (or :1420 in dev) in Chrome/Brave.
2. Look at the address bar — you should see an **install icon** (⊕ or a monitor with a down arrow).
3. Click it → click **Install**.
4. ✅ MaestroAgent opens in its own window (not a browser tab).
5. ✅ It appears in your OS app launcher.
6. Close the browser — the app still opens independently.

**If failing**: 
- Use Chrome/Edge/Brave (Firefox PWA support varies).
- Ensure you're on `http://localhost` or HTTPS (PWA requires secure context).
- Check the browser console for service worker errors.

---

## 3. Dashboard + Live Event Stream

**What**: The dashboard shows a live event stream when a run is active.

**Test steps**:
1. Click **Templates** in the left sidebar.
2. Select the **blank** template.
3. Click **Configure & Run**.
4. In the modal: goal = "test", click **Launch Run**.
5. ✅ You're redirected to the Dashboard.
6. ✅ The **Live Event Stream** panel shows events appearing in real time (color-coded: purple=run, blue=step, amber=loop, green=LLM).
7. ✅ The **Run Summary Card** shows cost, iteration, current node.
8. ✅ The **Quick Stats** panel shows events/sec, LLM calls, tool calls.

**If failing**: Check the status bar at the bottom — does it say "engine online"? If not, the backend isn't reachable from the browser.

---

## 4. Command Palette (⌘K)

**What**: A Linear/Notion-style command palette for keyboard navigation.

**Test steps**:
1. Press **⌘K** (Mac) or **Ctrl+K** (Windows/Linux) anywhere in the app.
2. ✅ A modal appears with a search input + grouped commands.
3. Type "dashboard" — the list filters.
4. Press **↓** to navigate, **Enter** to select.
5. ✅ The view switches to the Dashboard.
6. Press **⌘N** — the Start Run modal opens.
7. Press **⌘2** — Graph Builder opens. **⌘3** → Agents. **⌘4** → Loops. Etc.
8. Press **Esc** — any open modal closes.

**If failing**: Make sure the browser window has focus (click on the app first).

---

## 5. Graph Builder (ReactFlow)

**What**: Drag-and-drop visual workflow editor.

**Test steps**:
1. Press **⌘2** or click **Graph Builder** in the sidebar.
2. ✅ You see a canvas with a sample SaaS MVP graph (supervisor → agents → loop → HITL → done).
3. ✅ A **Palette** on the left shows 7 node types: Agent, Supervisor, Loop, Gate, HITL, Tool, Terminal.
4. **Drag** a "Loop" node from the palette onto the canvas.
5. ✅ A new loop node appears at the drop position.
6. Click a node — it gets a purple ring (selected).
7. Click **Delete Selected** in the Actions panel — the node disappears.
8. Click **Export JSON** — a `maestro-graph-*.json` file downloads.
9. Click **Import JSON** — select the file you just downloaded — the graph reloads.
10. ✅ The **Stats** panel shows node/agent/loop/edge counts.
11. Use the **MiniMap** (bottom right) to navigate. Use **Controls** to zoom/fit.

**If failing**: Check the browser console for ReactFlow errors. The canvas needs a fixed-height container.

---

## 6. Loops Panel — Create + Monitor

**What**: Create verifiable loops (simple/nested/parallel/meta) and monitor them live.

**Test steps**:
1. Press **⌘4** or click **Loops** in the sidebar.
2. ✅ You see a summary (Total / Active / Completed / Escalated) and a loop monitor.
3. If no run is active, the panel says "No loops yet".
4. Start a run (see section 3), then come back to Loops.
5. ✅ As the run progresses, loop cards appear with:
   - Spinning icon (amber) while active
   - Progress bar showing iterations / max
   - Live score (if the loop has a critic/metric condition)
   - Outcome badge when complete (condition met / stagnant / max iterations)
6. Click **New Loop** — the Create Loop modal opens.
7. ✅ You see a **Loop kind** selector: Simple / Nested / Parallel / Meta.
8. Select **Parallel** — the "Body agent" field changes to "Child agents (comma-separated)".
9. Fill in: Loop ID = `test_parallel`, child agents = `agent_a, agent_b`, exit kind = `critic`, rubric = "test", threshold = 0.8.
10. Click **Create Loop** — the modal closes and the loop appears in the panel.

**If failing**: Loops require an active run. Start a run first.

---

## 7. Agent Tree — Spawn + Debate

**What**: View the live agent hierarchy, spawn sub-agents, trigger debates.

**Test steps**:
1. Press **⌘3** or click **Agents** in the sidebar.
2. If a run with a supervisor is active, you see a tree of agents.
3. ✅ Each agent row shows: id, role, scope badge (private/shared/crew), status badge, child count.
4. **Hover** over an agent — a **+** button appears on the right.
5. Click **+** — the Spawn Sub-Agent modal opens.
6. Fill in: sub-goal = "implement auth", role = "Backend Engineer", select a tool (shell), click **Spawn Sub-Agent**.
7. ✅ The new sub-agent appears in the tree under the parent.
8. **Click** on an agent to select it (purple ring).
9. **Ctrl+Click** or click another agent to multi-select.
10. ✅ When 2+ agents are selected, a **Debate** button appears in the header.
11. Click **Debate** — the Debate Modal opens.
12. Fill in: topic = "Should we use Postgres or MySQL?", click **Start Debate**.
13. ✅ A debate event appears in the event stream.

**If failing**: The agent tree is empty until a supervisor spawns sub-agents. Run the `build_saas_mvp` template.

---

## 8. Terminal

**What**: Console-style live event log.

**Test steps**:
1. Press **⌘5** or click **Terminal** in the sidebar.
2. Start a run (or have one active).
3. ✅ Events stream in as monospace text: `[HH:MM:SS.mmm] event.type  key=value key=value`
4. ✅ The terminal auto-scrolls to the bottom.
5. ✅ The header shows line count.

---

## 9. File Browser

**What**: Browse the workspace produced by a run.

**Test steps**:
1. Press **⌘6** or click **Files** in the sidebar.
2. ✅ You see a tree view of `/workspace` with folders (src, tests) and files.
3. Click a folder — it expands/collapses.
4. Click a file — it's selected (path shown at the bottom).
5. ✅ File sizes are shown in B/KB/MB.

---

## 10. Metrics + Cost Tracking + Meta-Agent

**What**: Real-time cost tracking, token usage, and meta-agent recommendations.

**Test steps**:
1. Press **⌘7** or click **Metrics** in the sidebar.
2. Start a run that makes LLM calls.
3. ✅ The **Total Cost** card updates in real time (every 5s).
4. ✅ The **LLM Calls** / **Tool Calls** / **Errors** cards reflect the event stream.
5. ✅ The **Token Usage** panel shows prompt vs completion tokens with a bar chart.
6. ✅ The **Cost Breakdown by Provider** table shows per-provider: prompt tokens, completion tokens, calls, cost, and a share bar.
7. Scroll down to **Meta-Agent Recommendations**.
8. Click **Refresh** — the meta-agent analyzes recent runs.
9. ✅ Recommendations appear with severity badges (info/warn/critical), expected savings, and confidence.
10. Scroll to **Export Project** — click **Export JSON** — a full run bundle downloads.

**If failing**: Cost data requires LLM calls. If you're using Ollama (local), cost is $0 but token counts still appear.

---

## 11. Templates Gallery

**What**: One-click workflow templates.

**Test steps**:
1. Press **⌘8** or click **Templates** in the sidebar.
2. ✅ You see a grid of template cards (build_saas_mvp, research_crew, ops_autopilot, hybrid_crew).
3. Type in the **search box** — the grid filters.
4. Click a card — it's selected (purple ring).
5. Click **Configure & Run** at the bottom — the Start Run modal opens pre-filled with the template.
6. ✅ Scroll down to see the **Marketplace** stub (v1.0) and **Featured Swarms**.

---

## 12. Voice Input (Start Run Modal)

**What**: Speech-to-text for goal entry.

**Test steps**:
1. Open Templates → click a template → **Configure & Run**.
2. ✅ In the Goal field, you see a **microphone icon** (top right of the textarea).
3. Click the mic — it turns red and pulses.
4. ✅ A "Listening..." indicator appears.
5. Speak: "Build a notes SaaS with authentication".
6. ✅ Your speech appears in the goal field.
7. Click the mic again to stop.

**If failing**: Voice input requires Chrome/Edge/Brave (Chromium-based). Safari/Firefox may not support it. The mic icon won't appear if unsupported.

---

## 13. Offline Mode (PWA)

**What**: The app shell works offline; past runs are cached.

**Test steps**:
1. Open the app and run a workflow.
2. **Disconnect** your network (turn off Wi-Fi, or stop the backend with `docker compose down`).
3. Refresh the page.
4. ✅ The app still loads (service worker cached the shell).
5. ✅ The status bar shows "offline" and "engine offline".
6. ✅ The Dashboard shows cached events from the last run (from IndexedDB).
7. ✅ You can browse Templates, Graph Builder, and edit graphs offline.
8. ❌ Starting a new run fails (needs the backend).
9. Reconnect — the app auto-reconnects (WS status → "open").

**If failing**: The service worker must be registered. Check `chrome://inspect/#service-workers` or the browser console.

---

## 14. WebSocket Auto-Reconnect

**What**: If the WS drops, the app reconnects automatically.

**Test steps**:
1. Start a run and watch the event stream.
2. Stop the backend: `docker compose down` (or Ctrl+C in dev mode).
3. ✅ The status bar WS indicator changes from "ws live" → "ws error" → "ws retry 1" → "ws retry 2" (with increasing delay).
4. Restart the backend: `docker compose up -d`.
5. ✅ Within ~30s, the WS reconnects ("ws live") and events resume.

---

## 15. Auth (if enabled)

**What**: API key authentication.

**Test steps**:
1. Set `MAESTRO_AUTH_ENABLED=true` in `.env`, restart: `./update.sh`.
2. Open the app.
3. ✅ A **Login Modal** appears, asking for an API key.
4. Get the key: `docker compose exec maestro cat /data/api_key.txt`.
5. Paste the key → click **Unlock**.
6. ✅ The modal closes and the app works normally.
7. ✅ The status bar shows "engine online".
8. Open browser DevTools → Application → Local Storage — you see `maestro_api_key`.

**If failing**: Check that `MAESTRO_AUTH_ENABLED=true` is in the `.env` file and the container was restarted.

---

## 16. Hybrid CrewAI Template

**What**: CrewAI crews compiled to MaestroAgent graphs.

**Test steps**:
1. Open Templates → select **hybrid_crew**.
2. Click **Configure & Run**.
3. Goal: "Write a blog post about local-first AI".
4. Click **Launch Run**.
5. ✅ The Dashboard shows events from a 3-agent crew: researcher → writer → editor.
6. ✅ Each agent's LLM call is a separate event (not a black-box crew).
7. ✅ The Agent Tree shows the crew's agents.

**If failing**: This template requires CrewAI installed (`pip install crewai`). If not installed, it falls back to BaseAgent nodes.

---

## 17. Status Dashboard

**What**: Quick HTML health check at /status.

**Test steps**:
1. Open **http://localhost:8765/status**.
2. ✅ You see a styled HTML page (not the PWA) showing:
   - Engine status (✅ Running)
   - Auth status (🔒 Enabled or 🔓 Disabled)
   - Default provider + model
   - Provider health table
   - Templates / verifiers / plugins lists
   - Quick links to PWA, API docs, health JSON

---

## 18. E2E Smoke Test

**What**: Automated 11-step smoke test.

**Test steps**:
1. With the backend running, execute:
   ```bash
   ./test_e2e.sh
   ```
2. ✅ All 11 checks pass:
   - Health check
   - Doctor diagnostics
   - Templates list
   - Models list
   - Start a blank run
   - Wait for completion
   - Run history
   - Audit log
   - Cost breakdown
   - PWA bundle served at /
   - PWA manifest

**If failing**: The script shows which step failed. Check `docker compose logs maestro` for backend errors.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| "engine offline" in status bar | Backend not running. Start with `./dev.sh` or `docker compose up -d` |
| PWA not installable | Use Chrome/Brave; ensure `http://localhost` or HTTPS; check manifest at `/manifest.webmanifest` |
| WebSocket not connecting | Check browser console for WS errors; ensure no proxy strips `Upgrade` headers |
| "No providers" in status | Start Ollama (`ollama serve`) or set an API key in `.env` |
| Templates gallery empty | Backend can't find `examples/templates/`. Ensure the Docker image built correctly |
| Voice input missing | Use Chromium-based browser; Safari/Firefox may not support SpeechRecognition |
| Auth login fails | Verify the key in `/data/api_key.txt` matches what you pasted |
| Cost always $0 | You're using Ollama (local, free). That's correct — token counts still appear |
| Graph builder blank | The canvas needs a fixed-height container. Try resizing the window |

---

## Quick Deployment Verification

For a 30-second verification:

```bash
# 1. Start
./install.sh   # or: ./dev.sh

# 2. Verify backend
curl -s http://localhost:8765/api/health | head -c 100

# 3. Verify status page
open http://localhost:8765/status    # macOS
xdg-open http://localhost:8765/status  # Linux

# 4. Verify PWA
open http://localhost:8765            # macOS
xdg-open http://localhost:8765        # Linux

# 5. Run smoke tests
./test_e2e.sh
```

If all 5 steps succeed, MaestroAgent is ready for browser review.
