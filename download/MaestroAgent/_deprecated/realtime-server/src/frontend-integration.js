// === REAL BACKEND INTEGRATION ===
// Replaces all mock task-flow logic with real /api/runs + WebSocket streaming.
// Every character of "AI output" the user sees comes from a real LLM call.

// Backend base URL — same origin in production, configurable for dev.
const MAESTRO_API = window.MAESTRO_API || '';
const MAESTRO_WS = window.MAESTRO_WS || (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host;

// Track the active run + WS connection so the user can navigate away and back.
let activeRun = { id: null, ws: null, agentBuffers: {}, agentsSeen: new Set(), artifacts: [] };

// Sanitize text for safe innerHTML insertion (XSS protection).
function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// Render markdown-ish text to HTML (very lightweight: code blocks, bold, headings).
function renderMarkdown(text) {
  let html = escapeHtml(text);
  // Fenced code blocks
  html = html.replace(/```(\w+)?\n([\s\S]*?)```/g, (_, lang, code) => {
    return '<pre class="md-code"><code data-lang="' + (lang || '') + '">' + code + '</code></pre>';
  });
  // Headings
  html = html.replace(/^### (.+)$/gm, '<h4 class="md-h4">$1</h4>');
  html = html.replace(/^## (.+)$/gm, '<h3 class="md-h3">$1</h3>');
  html = html.replace(/^# (.+)$/gm, '<h2 class="md-h2">$1</h2>');
  // Bold
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code class="md-inline">$1</code>');
  // Line breaks
  html = html.replace(/\n/g, '<br>');
  return html;
}

// Entry point: user typed a goal and hit Start.
async function startTaskFlow() {
  const input = document.getElementById('mission-input');
  const goal = input ? input.value.trim() : '';
  if (!goal) {
    if (input) input.focus();
    return;
  }

  // Tear down any previous run.
  if (activeRun.ws) { try { activeRun.ws.close(); } catch {} }
  activeRun = { id: null, ws: null, agentBuffers: {}, agentsSeen: new Set(), artifacts: [] };

  // Hide mission control, show work stream.
  const mc = document.querySelector('.mission-control');
  const ws = document.getElementById('work-stream');
  if (mc) mc.style.display = 'none';
  if (ws) {
    ws.classList.add('active');
    ws.textContent = '';
  }

  // User's message bubble.
  addWorkStreamMessage('user', goal);

  // Maestro acknowledges — typing indicator first.
  await sleep(300);
  addMaestroMessage("On it. Let me assemble the right specialists and get to work.", true);

  // === REAL BACKEND CALL ===
  try {
    const resp = await fetch(MAESTRO_API + '/api/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ goal }),
    });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    activeRun.id = data.run_id;

    // Progress bar — will be updated as agents complete.
    addWorkProgress('Starting run...');

    // Connect WebSocket for live streaming.
    connectRunWebSocket(data.run_id);
  } catch (err) {
    addMaestroMessage("⚠️ Couldn't reach the Maestro backend. Is the realtime server running on port 8765? Error: " + escapeHtml(err.message), false);
  }
}

// Open the WebSocket and wire every event type to a UI update.
function connectRunWebSocket(runId) {
  const url = MAESTRO_WS + '/ws/' + runId;
  const ws = new WebSocket(url);
  activeRun.ws = ws;

  ws.onopen = () => {
    console.log('[maestro] WS connected to run', runId);
  };

  ws.onmessage = (e) => {
    let ev;
    try { ev = JSON.parse(e.data); } catch { return; }
    handleRunEvent(ev);
  };

  ws.onerror = (e) => {
    console.error('[maestro] WS error', e);
  };

  ws.onclose = () => {
    console.log('[maestro] WS closed for run', runId);
  };
}

// Dispatch a single event to the right UI handler.
function handleRunEvent(ev) {
  const p = ev.payload || {};
  switch (ev.type) {
    case 'connected':
      // First message from server — ack only.
      break;

    case 'run.started':
      updateWorkProgress(5, 'Team assembled · starting work');
      addMaestroMessage("I've put together a team of " + (p.team?.length || 0) + " specialists. They'll work in sequence — you'll see each one's output stream in real time.", false);
      // Add the deliverables panel up front so it's ready to fill in.
      ensureDeliverablesPanel();
      break;

    case 'agent.joined':
      addSpecialistJoin({ icon: p.icon, name: p.name, role: p.role });
      break;

    case 'agent.thinking':
      // Start a new agent message bubble that we'll stream tokens into.
      startAgentStream(p.agent_id, p.name, p.icon, p.step, p.total_steps);
      // Update progress: each agent gets a proportional slice.
      const pct = 10 + Math.floor(((p.step - 1) / p.total_steps) * 80);
      updateWorkProgress(pct, p.name + ' is working (step ' + p.step + '/' + p.total_steps + ')');
      break;

    case 'agent.token':
      // Stream the token into the current agent's bubble.
      appendTokenToAgentStream(p.agent_id, p.delta);
      break;

    case 'agent.completed':
      // Finalize the agent's bubble with the full rendered text.
      finalizeAgentStream(p.agent_id, p.text, p.artifact, p.bytes);
      // Add to deliverables panel.
      addDeliverableCard({
        agent_id: p.agent_id,
        agent_name: p.name,
        filename: p.artifact,
        bytes: p.bytes,
        preview: (p.text || '').slice(0, 240),
      });
      // Bump progress.
      const done = p.step / p.total_steps;
      updateWorkProgress(10 + Math.floor(done * 80), p.name + ' done · ' + Math.floor(done * 100) + '% complete');
      break;

    case 'run.completed':
      updateWorkProgress(100, 'Done · ' + (p.duration_ms / 1000).toFixed(1) + 's');
      // Highlight the final deliverable.
      if (p.final_artifact) {
        markFinalDeliverable(p.final_artifact);
      }
      addMaestroMessage("All done. " + (p.artifacts?.length || 0) + " artifacts produced. Scroll down to download them, or start a new task.", false);
      // Show "start new" CTA.
      addStartNewCTA();
      break;

    case 'run.failed':
      updateWorkProgress(100, 'Failed');
      addMaestroMessage("⚠️ Run failed: " + escapeHtml(p.error || 'unknown error'), false);
      break;
  }
}

// === Work-stream UI helpers ===
// All of these operate on the #work-stream container.

function addWorkStreamMessage(type, text) {
  const ws = document.getElementById('work-stream');
  if (!ws) return;
  const el = document.createElement('div');
  el.className = type === 'user' ? 'user-msg' : 'maestro-msg';
  if (type === 'user') {
    el.innerHTML = '<div class="user-msg-text"></div>';
    el.querySelector('.user-msg-text').textContent = text;
  } else {
    el.innerHTML = '<span class="maestro-msg-avatar">M</span><span class="maestro-msg-text"></span>';
    el.querySelector('.maestro-msg-text').innerHTML = text;
  }
  ws.appendChild(el);
  el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function addMaestroMessage(text, withTyping) {
  const ws = document.getElementById('work-stream');
  if (!ws) return;
  if (withTyping) {
    const typing = document.createElement('div');
    typing.className = 'maestro-msg';
    typing.innerHTML = '<span class="maestro-msg-avatar">M</span><span class="typing-dots"><span></span><span></span><span></span></span>';
    ws.appendChild(typing);
    typing.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    setTimeout(() => {
      typing.innerHTML = '<span class="maestro-msg-avatar">M</span><span class="maestro-msg-text"></span>';
      typing.querySelector('.maestro-msg-text').innerHTML = text;
    }, 700);
  } else {
    addWorkStreamMessage('maestro', text);
  }
}

function addWorkProgress(label) {
  const ws = document.getElementById('work-stream');
  if (!ws) return;
  // Remove any existing progress bar.
  const existing = document.getElementById('work-progress-bar');
  if (existing) existing.remove();
  const el = document.createElement('div');
  el.className = 'work-progress';
  el.id = 'work-progress-bar';
  el.innerHTML = '<div style="font-size:12px;color:#8888a0;">' + escapeHtml(label) + '</div><div class="work-progress-bar"><div class="work-progress-fill" style="width:0%"></div></div>';
  ws.appendChild(el);
  el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function updateWorkProgress(percent, label) {
  const prog = document.getElementById('work-progress-bar');
  if (!prog) return;
  const fill = prog.querySelector('.work-progress-fill');
  const labelEl = prog.querySelector('div');
  if (fill) fill.style.width = Math.max(0, Math.min(100, percent)) + '%';
  if (labelEl && label) labelEl.textContent = label;
}

function addSpecialistJoin(agent) {
  const ws = document.getElementById('work-stream');
  if (!ws) return;
  const el = document.createElement('div');
  el.className = 'specialist-join';
  el.innerHTML = '<div class="specialist-join-avatar">' + escapeHtml(agent.icon) + '</div>' +
    '<div><div class="specialist-join-name"></div><div class="specialist-join-role"></div></div>' +
    '<div class="specialist-join-badge">✓ joined</div>';
  el.querySelector('.specialist-join-name').textContent = agent.name;
  el.querySelector('.specialist-join-role').textContent = agent.role;
  ws.appendChild(el);
  el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Start a streaming bubble for an agent. The bubble has a header
// (icon + name + step) and a body that we append tokens to.
function startAgentStream(agentId, name, icon, step, totalSteps) {
  const ws = document.getElementById('work-stream');
  if (!ws) return;
  const el = document.createElement('div');
  el.className = 'agent-stream-msg';
  el.id = 'agent-stream-' + agentId;
  el.innerHTML =
    '<div class="agent-stream-header">' +
      '<div class="specialist-join-avatar">' + escapeHtml(icon) + '</div>' +
      '<div class="agent-stream-name">' + escapeHtml(name) + '</div>' +
      '<div class="agent-stream-step">step ' + step + ' / ' + totalSteps + '</div>' +
      '<div class="typing-dots"><span></span><span></span><span></span></div>' +
    '</div>' +
    '<div class="agent-stream-body"></div>';
  ws.appendChild(el);
  activeRun.agentBuffers[agentId] = '';
  el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Append a real LLM token to the agent's streaming bubble.
function appendTokenToAgentStream(agentId, delta) {
  const el = document.getElementById('agent-stream-' + agentId);
  if (!el) return;
  activeRun.agentBuffers[agentId] = (activeRun.agentBuffers[agentId] || '') + delta;
  const body = el.querySelector('.agent-stream-body');
  if (body) {
    // Render the accumulated text as markdown on each token.
    // Cheap enough for typical agent outputs (a few KB).
    body.innerHTML = renderMarkdown(activeRun.agentBuffers[agentId]);
    // Auto-scroll only if user is near the bottom.
    const ws = document.getElementById('work-stream');
    if (ws) {
      const nearBottom = ws.scrollHeight - ws.scrollTop - ws.clientHeight < 200;
      if (nearBottom) ws.scrollTop = ws.scrollHeight;
    }
  }
}

// Finalize the agent's bubble: remove typing dots, add the artifact badge.
function finalizeAgentStream(agentId, fullText, artifact, bytes) {
  const el = document.getElementById('agent-stream-' + agentId);
  if (!el) return;
  // Remove typing dots.
  el.querySelectorAll('.typing-dots').forEach(d => d.remove());
  // Replace step badge with "done" + artifact link.
  const step = el.querySelector('.agent-stream-step');
  if (step) {
    step.innerHTML = '✓ done · <a href="' + MAESTRO_API + '/api/runs/' + activeRun.id + '/artifacts/' + encodeURIComponent(artifact) + '" target="_blank" class="agent-artifact-link">' + escapeHtml(artifact) + '</a> (' + bytes + ' bytes)';
  }
  // Final render with full text.
  const body = el.querySelector('.agent-stream-body');
  if (body && fullText) {
    body.innerHTML = renderMarkdown(fullText);
  }
}

// === Deliverables panel ===
// A dedicated section at the bottom of the work-stream showing every
// artifact produced, with download links.

function ensureDeliverablesPanel() {
  if (document.getElementById('deliverables-panel')) return;
  const ws = document.getElementById('work-stream');
  if (!ws) return;
  const panel = document.createElement('div');
  panel.id = 'deliverables-panel';
  panel.className = 'deliverables-panel';
  panel.innerHTML =
    '<div class="deliverables-header">' +
      '<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>' +
      '<span>Deliverables</span>' +
      '<span class="deliverables-count" id="deliverables-count">0 files</span>' +
    '</div>' +
    '<div class="deliverables-list" id="deliverables-list"></div>';
  ws.appendChild(panel);
}

function addDeliverableCard(artifact) {
  ensureDeliverablesPanel();
  const list = document.getElementById('deliverables-list');
  if (!list) return;
  activeRun.artifacts.push(artifact);

  const card = document.createElement('div');
  card.className = 'deliverable-card';
  card.id = 'deliverable-' + artifact.filename;
  const url = MAESTRO_API + '/api/runs/' + activeRun.id + '/artifacts/' + encodeURIComponent(artifact.filename);
  card.innerHTML =
    '<div class="deliverable-card-icon">' + escapeHtml(artifact.filename.split('.').pop().toUpperCase()) + '</div>' +
    '<div class="deliverable-card-body">' +
      '<div class="deliverable-card-name">' + escapeHtml(artifact.filename) + '</div>' +
      '<div class="deliverable-card-meta">' + escapeHtml(artifact.agent_name) + ' · ' + artifact.bytes + ' bytes</div>' +
      '<div class="deliverable-card-preview">' + escapeHtml(artifact.preview) + (artifact.preview.length >= 240 ? '…' : '') + '</div>' +
    '</div>' +
    '<a href="' + url + '" target="_blank" download class="btn btn-cyan deliverable-download">Download</a>';
  list.appendChild(card);

  // Update count.
  const count = document.getElementById('deliverables-count');
  if (count) count.textContent = list.children.length + ' file' + (list.children.length === 1 ? '' : 's');
}

function markFinalDeliverable(filename) {
  const card = document.getElementById('deliverable-' + filename);
  if (card) card.classList.add('final');
}

function addStartNewCTA() {
  const ws = document.getElementById('work-stream');
  if (!ws) return;
  const el = document.createElement('div');
  el.className = 'start-new-cta';
  el.innerHTML =
    '<button class="btn btn-primary" onclick="resetHome()">Start a new task</button>' +
    ' &nbsp; ' +
    '<a href="' + MAESTRO_API + '/api/runs/' + (activeRun.id || '') + '" target="_blank" class="btn btn-ghost">View run JSON</a>';
  ws.appendChild(el);
}

function resetHome() {
  // Close any active WS.
  if (activeRun.ws) { try { activeRun.ws.close(); } catch {} }
  activeRun = { id: null, ws: null, agentBuffers: {}, agentsSeen: new Set(), artifacts: [] };
  const mc = document.querySelector('.mission-control');
  const ws = document.getElementById('work-stream');
  if (mc) mc.style.display = '';
  if (ws) { ws.classList.remove('active'); ws.textContent = ''; }
  const input = document.getElementById('mission-input');
  if (input) { input.value = ''; input.focus(); }
}

// === Task flow modal (still used by the "templates" page) ===
// We keep the modal UI but make it actually start a real run.

function openTaskFlow(type, presetGoal) {
  const config = taskFlowConfig[type] || taskFlowConfig['build'];
  document.getElementById('task-flow-title').textContent = config.title;
  document.getElementById('task-flow-subtitle').textContent = config.subtitle;
  if (presetGoal) {
    const goalInput = document.getElementById('tf-goal-input');
    if (goalInput) goalInput.value = presetGoal;
  }
  document.querySelectorAll('.task-flow-step').forEach(s => s.classList.remove('active'));
  document.getElementById('tf-step-goal').classList.add('active');
  toggleModal('taskFlowModal');
}

function nextTaskFlowStep(step) {
  document.querySelectorAll('.task-flow-step').forEach(s => s.classList.remove('active'));
  const target = document.getElementById('tf-step-' + step);
  if (target) target.classList.add('active');
  if (step === 'team') autoGenerateTeam();
}

function prevTaskFlowStep(step) {
  document.querySelectorAll('.task-flow-step').forEach(s => s.classList.remove('active'));
  const target = document.getElementById('tf-step-' + step);
  if (target) target.classList.add('active');
}

// Used by the modal — kicks off a real run with the goal typed in the modal.
async function autoGenerateTeam() {
  const goal = (document.getElementById('tf-goal-input') || {}).value || 'your task';
  const narration = document.getElementById('tf-narration');
  const desc = document.getElementById('tf-team-description');
  const list = document.getElementById('tf-team-list');
  if (list) list.textContent = '';
  if (narration) { narration.textContent = 'Thinking about who should work on this...'; narration.classList.add('text-brand-cyan'); narration.classList.remove('text-brand-purple'); }
  if (desc) desc.textContent = 'Asking the backend to assemble the right specialists for "' + goal.substring(0, 50) + (goal.length > 50 ? '...' : '') + '":';

  // Start a real run.
  try {
    const resp = await fetch(MAESTRO_API + '/api/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ goal }),
    });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    activeRun.id = data.run_id;
    activeRun.agentBuffers = {};
    activeRun.artifacts = [];

    // Connect WS just to drive the modal's team list — close it when done.
    const url = MAESTRO_WS + '/ws/' + data.run_id;
    const ws = new WebSocket(url);
    activeRun.ws = ws;
    ws.onmessage = (e) => {
      let ev; try { ev = JSON.parse(e.data); } catch { return; }
      if (ev.type === 'agent.joined') {
        const p = ev.payload;
        if (narration) narration.textContent = p.name + ' joined the team';
        if (list) {
          const el = document.createElement('div');
          el.className = 'auto-team-agent';
          el.innerHTML = '<div class="w-8 h-8 rounded-md bg-brand-purple/15 flex items-center justify-center text-sm">' + escapeHtml(p.icon) + '</div>' +
            '<div class="flex-1"><div class="text-[12px] font-semibold text-fg-100">' + escapeHtml(p.name) + '</div>' +
            '<div class="text-[10px] text-fg-500">' + escapeHtml(p.role) + '</div></div>' +
            '<span class="tag tag-cyan">joined</span>';
          list.appendChild(el);
        }
      } else if (ev.type === 'run.completed' || ev.type === 'run.failed') {
        if (narration) {
          narration.textContent = ev.type === 'run.completed' ? 'Team ready. Starting work...' : 'Run failed';
          narration.classList.remove('text-brand-cyan');
          narration.classList.add('text-brand-purple');
        }
        // After a beat, close the modal and show the work stream.
        setTimeout(() => {
          toggleModal('taskFlowModal');
          // Reset home + start the same run again in the work stream UI.
          // But the run already started — we just need to subscribe again
          // and replay events.
          if (mc) mc.style.display = 'none';
          const wsEl = document.getElementById('work-stream');
          if (wsEl) { wsEl.classList.add('active'); wsEl.textContent = ''; }
          addWorkStreamMessage('user', goal);
          addMaestroMessage('Loaded run ' + data.run_id.slice(0, 8) + ' — replaying events...', false);
          ensureDeliverablesPanel();
          // Fetch all past events and replay them, then re-subscribe.
          replayRunEvents(data.run_id);
        }, 1200);
      }
    };
  } catch (err) {
    if (narration) narration.textContent = 'Error: ' + err.message;
  }
}

// Fetch all events for a run and replay them through handleRunEvent,
// then open a fresh WS for any remaining events.
async function replayRunEvents(runId) {
  try {
    const resp = await fetch(MAESTRO_API + '/api/runs/' + runId + '/events');
    if (!resp.ok) return;
    const events = await resp.json();
    for (const ev of events) handleRunEvent(ev);
    // If run is still active, re-connect WS for live tail.
    const runResp = await fetch(MAESTRO_API + '/api/runs/' + runId);
    if (runResp.ok) {
      const run = await runResp.json();
      if (run.status === 'running' || run.status === 'pending') {
        connectRunWebSocket(runId);
      }
    }
  } catch (err) {
    console.error('[maestro] replay failed', err);
  }
}

// Tiny sleep helper.
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// On page load, check the backend health and update the UI accordingly.
(async function checkBackendHealth() {
  try {
    const resp = await fetch(MAESTRO_API + '/api/health');
    if (resp.ok) {
      const data = await resp.json();
      console.log('[maestro] backend healthy:', data);
      // If there are recent runs, populate the "Recent" list with real ones.
      const runsResp = await fetch(MAESTRO_API + '/api/runs');
      if (runsResp.ok) {
        const runs = await runsResp.json();
        if (runs.length > 0) updateRecentWork(runs);
      }
    }
  } catch (err) {
    console.warn('[maestro] backend not reachable:', err.message);
  }
})();

// Replace the hardcoded "Recent" list with real runs from the backend.
function updateRecentWork(runs) {
  const container = document.querySelector('.mission-control .mt-10');
  if (!container) return;
  const items = runs.slice(0, 5).map(r => {
    const ago = relativeTime(r.startedAt);
    const statusTag = r.status === 'completed' ? '<span class="tag tag-sky">Done</span>'
      : r.status === 'running' ? '<span class="tag tag-cyan">Working</span>'
      : r.status === 'failed' ? '<span class="tag tag-rose">Failed</span>'
      : '<span class="tag tag-gray">' + r.status + '</span>';
    return '<div class="recent-work-item" onclick="openRunDetail(\'' + r.id + '\')">' +
      '<div class="recent-work-icon" style="background: rgba(124,92,255,0.12);">📄</div>' +
      '<div class="flex-1"><div class="recent-work-title">' + escapeHtml(r.goal) + '</div>' +
      '<div class="recent-work-meta">' + (r.teamSize || 0) + ' specialists · ' + ago + '</div></div>' +
      statusTag + '</div>';
  }).join('');
  // Preserve the heading, replace items.
  const heading = container.querySelector('h3');
  container.innerHTML = '';
  if (heading) container.appendChild(heading);
  const wrap = document.createElement('div');
  wrap.innerHTML = items;
  while (wrap.firstChild) container.appendChild(wrap.firstChild);
}

function openRunDetail(runId) {
  // Navigate to work stream and replay.
  const mc = document.querySelector('.mission-control');
  const ws = document.getElementById('work-stream');
  if (mc) mc.style.display = 'none';
  if (ws) { ws.classList.add('active'); ws.textContent = ''; }
  activeRun = { id: runId, ws: null, agentBuffers: {}, agentsSeen: new Set(), artifacts: [] };
  // Fetch run info to display the goal as the user message.
  fetch(MAESTRO_API + '/api/runs/' + runId).then(r => r.json()).then(run => {
    addWorkStreamMessage('user', run.goal);
    addMaestroMessage('Replaying run <code>' + runId.slice(0, 8) + '</code> — ' + run.status + '.', false);
    ensureDeliverablesPanel();
    // Pre-populate deliverables from run state.
    (run.artifacts || []).forEach(a => {
      addDeliverableCard({
        agent_id: a.agent_id,
        agent_name: a.agent_name,
        filename: a.filename,
        bytes: a.bytes,
        preview: a.preview || '',
      });
      if (a.isFinal) markFinalDeliverable(a.filename);
    });
    replayRunEvents(runId);
  });
}

function relativeTime(iso) {
  if (!iso) return 'just now';
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  return Math.floor(diff / 86400) + 'd ago';
}
