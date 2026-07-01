// MAESTRO — Pure Renderer Frontend
// ═══════════════════════════════════════════════════════════════════════════
// The UI is a pure renderer. The OEM is the single source of truth.
// Every metric, recommendation, law, discovery, autocomplete suggestion,
// and dashboard number comes from a live OEM API call.
//
// Features:
//   - SWR-style caching (stale-while-revalidate)
//   - Loading states with skeletons
//   - Retry with exponential backoff
//   - Offline mode (serves cached data when network fails)
//   - Optimistic updates (contradiction feedback)
//   - Error recovery (global error boundary + per-surface retry)
//   - Request cancellation (AbortController per fetch)
// ═══════════════════════════════════════════════════════════════════════════

// ─── Configuration ───────────────────────────────────────────────────────────
const MAESTRO_API = window.MAESTRO_API || '';

// ─── Navigation map (the only hardcoded data — labels, not insights) ────────
const pageNames = {
  // Constitution v2 — 4 meta-surfaces
  today: 'Today', work: 'Work', 'ask-v2': 'Ask', learn: 'Learn',
  evolution: 'Evolution Report',
  cognition: 'Cognitive Organs',
  autobiography: "Your Organization's Story",
  // Deep capabilities (existing surfaces)
  home: 'Home', inbox: 'Inbox', simulator: 'Decision Simulator',
  hayek: 'Hayek Lens', flow: 'Knowledge Flow', memory: 'Memory Replay',
  ask: 'Ask the Organization', customer: 'Customer Judgment',
  physics: 'Organizational Physics', debate: 'Debate',
  live: 'Live Meeting',
  intents: 'Intent Cascade',
  contradictions: 'Contradictions',
  predictions: 'Prediction Market',
  assumptions: 'Dangerous Assumptions',
  'eng-signals': 'Signals', 'eng-oem': 'OEM Builder',
  'eng-audit': 'Audit Log', 'eng-settings': 'Settings',
};

function navTo(surface) {
  // Teardown: clean up timers/WS when leaving a surface
  if (window._currentSurface === 'live' && surface !== 'live') {
    teardownLive();
  }
  window._currentSurface = surface;
  if (window.location.hash !== '#' + surface) {
    history.replaceState(null, '', '#' + surface);
  }
  document.querySelectorAll('.surface').forEach(s => s.classList.remove('active'));
  const target = document.getElementById('surface-' + surface);
  if (target) {
    target.classList.add('active');
    void target.offsetWidth;
  }
  document.querySelectorAll('.sidebar-link').forEach(l => l.classList.remove('active'));
  const link = document.querySelector('.sidebar-link[data-surface="' + surface + '"]');
  if (link) link.classList.add('active');
  document.getElementById('bc-page').textContent = pageNames[surface] || surface;
  document.getElementById('bc-detail').textContent = '';
  document.getElementById('main-scroll').scrollTop = 0;
  closeMobileSidebar();

  // WCAG 2.1: Move focus to main content for screen reader users
  const mainContent = document.getElementById('main-content');
  if (mainContent) {
    mainContent.setAttribute('tabindex', '-1');
    mainContent.focus({ preventScroll: true });
  }

  loadSurfaceData(surface);
}

document.querySelectorAll('.sidebar-link[data-surface]').forEach(link => {
  link.addEventListener('click', () => navTo(link.dataset.surface));
  link.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navTo(link.dataset.surface); }
  });
});

function toggleMobileSidebar() {
  document.getElementById('sidebar').classList.toggle('mobile-open');
}
function closeMobileSidebar() {
  document.getElementById('sidebar').classList.remove('mobile-open');
}

window.addEventListener('hashchange', () => {
  const hash = window.location.hash.slice(1);
  if (hash && document.getElementById('surface-' + hash)) navTo(hash);
});
window.addEventListener('DOMContentLoaded', () => {
  const hash = window.location.hash.slice(1);
  // Constitution v2: default to TODAY (the morning brief)
  const validHash = hash && document.getElementById('surface-' + hash);
  navTo(validHash ? hash : 'today');
  // Initialize the Organizational Dot
  initOrgDot();
});

document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  if ((e.metaKey || e.ctrlKey) && e.key >= '1' && e.key <= '9') {
    e.preventDefault();
    // Constitution v2: Ctrl+1-4 = meta-surfaces, Ctrl+5-9 = deep capabilities
    const surfaces = ['today','work','ask-v2','learn','home','inbox','simulator','customer','physics'];
    const idx = parseInt(e.key) - 1;
    if (surfaces[idx]) navTo(surfaces[idx]);
  }
  if (e.key === 'Escape') {
    document.getElementById('exec-autocomplete').classList.remove('active');
    const palette = document.getElementById('command-palette');
    if (palette) palette.classList.add('hidden');
  }
  // Ctrl+K opens command palette
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault();
    openCommandPalette();
  }
});

// ═══════════════════════════════════════════════════════════════════════════
// COMMAND PALETTE — access to the 22 deep surfaces without sidebar clutter
// ═══════════════════════════════════════════════════════════════════════════

const _hiddenSurfaces = [
  { id: 'home', label: 'Home — live dashboard', group: 'CEO Product' },
  { id: 'inbox', label: 'Inbox — decisions I owe', group: 'CEO Product' },
  { id: 'simulator', label: 'Decision Simulator', group: 'CEO Product' },
  { id: 'hayek', label: 'Hayek Lens — influence graph', group: 'CEO Product' },
  { id: 'flow', label: 'Knowledge Flow', group: 'CEO Product' },
  { id: 'memory', label: 'Memory Replay', group: 'CEO Product' },
  { id: 'ask', label: 'Ask the Organization (legacy)', group: 'CEO Product' },
  { id: 'customer', label: 'Customer Judgment', group: 'CEO Product' },
  { id: 'physics', label: 'Organizational Physics — patterns', group: 'CEO Product' },
  { id: 'debate', label: 'Debate — laws unknown to leadership', group: 'CEO Product' },
  { id: 'live', label: 'Live Meeting intelligence', group: 'CEO Product' },
  { id: 'intents', label: 'Intent Cascade', group: 'Cognitive Model' },
  { id: 'contradictions', label: 'Contradictions', group: 'Cognitive Model' },
  { id: 'predictions', label: 'Prediction Market — calibration', group: 'Cognitive Model' },
  { id: 'assumptions', label: 'Dangerous Assumptions', group: 'Cognitive Model' },
  { id: 'eng-signals', label: 'Signals — connected sources', group: 'Engineering' },
  { id: 'eng-oem', label: 'OEM Builder — inference pipeline', group: 'Engineering' },
  { id: 'eng-audit', label: 'Audit Log — signal history', group: 'Engineering' },
  { id: 'eng-settings', label: 'Settings — configuration', group: 'Engineering' },
  { id: 'evolution', label: 'Evolution Report — how has the organization changed?', group: 'Constitution v3' },
  { id: 'cognition', label: 'Cognitive Organs — skepticism, wisdom, metacognition, principles, consciousness', group: 'Constitution v4' },
  { id: 'autobiography', label: 'Your Organization\u2019s Story — the autobiography', group: 'Constitution v6' },
];

function openCommandPalette() {
  let palette = document.getElementById('command-palette');
  if (!palette) {
    palette = document.createElement('div');
    palette.id = 'command-palette';
    palette.className = 'fixed inset-0 z-50';
    palette.style.cssText = 'display:flex;align-items:flex-start;justify-content:center;padding-top:120px;background:rgba(0,0,0,0.5);';
    palette.innerHTML = `
      <div style="background:var(--surface);border:1px solid var(--divider);border-radius:12px;width:480px;max-height:400px;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 20px 60px rgba(0,0,0,0.5);">
        <input type="text" id="command-palette-input" placeholder="Search surfaces…"
               style="width:100%;padding:16px 20px;background:transparent;border:none;border-bottom:1px solid var(--divider);color:var(--text-primary);font-size:15px;outline:none;font-family:var(--font-sans);"
               aria-label="Search surfaces"
               oninput="filterCommandPalette(this.value)"
               onkeydown="handlePaletteKeydown(event)">
        <div id="command-palette-results" style="flex:1;overflow-y:auto;padding:8px;"></div>
      </div>
    `;
    palette.addEventListener('click', (e) => {
      if (e.target === palette) closeCommandPalette();
    });
    document.body.appendChild(palette);
  }
  palette.classList.remove('hidden');
  palette.style.display = 'flex';
  renderPaletteResults(_hiddenSurfaces);
  setTimeout(() => {
    const input = document.getElementById('command-palette-input');
    if (input) input.focus();
  }, 50);
}

function closeCommandPalette() {
  const palette = document.getElementById('command-palette');
  if (palette) palette.style.display = 'none';
}

function renderPaletteResults(surfaces) {
  const results = document.getElementById('command-palette-results');
  if (!results) return;
  if (surfaces.length === 0) {
    results.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted);font-size:14px;">No surfaces found</div>';
    return;
  }
  let currentGroup = '';
  results.innerHTML = surfaces.map(s => {
    const groupHeader = s.group !== currentGroup ? `<div style="padding:8px 16px 4px;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;color:var(--text-muted);">${escapeHtml(s.group)}</div>` : '';
    currentGroup = s.group;
    return groupHeader + `<div class="palette-result" style="padding:10px 16px;cursor:pointer;border-radius:6px;font-size:14px;color:var(--text-primary);transition:background 150ms;" onmouseenter="this.style.background='var(--surface-2)'" onmouseleave="this.style.background='transparent'" onclick="navTo('${escapeJs(s.id)}');closeCommandPalette();">${escapeHtml(s.label)}</div>`;
  }).join('');
}

function selectFirstPaletteResult() {
  const first = document.querySelector('.palette-result');
  if (first) first.click();
}

// Arrow-key navigation for the command palette (Linear/Raycast-style)
let _paletteSelectedIdx = -1;

function handlePaletteKeydown(event) {
  const results = document.querySelectorAll('.palette-result');
  if (results.length === 0) return;

  if (event.key === 'Escape') {
    closeCommandPalette();
    return;
  }
  if (event.key === 'Enter') {
    if (_paletteSelectedIdx >= 0 && results[_paletteSelectedIdx]) {
      results[_paletteSelectedIdx].click();
    } else if (results[0]) {
      results[0].click();
    }
    return;
  }
  if (event.key === 'ArrowDown') {
    event.preventDefault();
    _paletteSelectedIdx = Math.min(_paletteSelectedIdx + 1, results.length - 1);
    updatePaletteSelection(results);
  }
  if (event.key === 'ArrowUp') {
    event.preventDefault();
    _paletteSelectedIdx = Math.max(_paletteSelectedIdx - 1, 0);
    updatePaletteSelection(results);
  }
}

function updatePaletteSelection(results) {
  results.forEach((r, i) => {
    if (i === _paletteSelectedIdx) {
      r.style.background = 'var(--accent-soft)';
      r.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    } else {
      r.style.background = 'transparent';
    }
  });
}

// Reset selection when filtering
function filterCommandPalette(query) {
  _paletteSelectedIdx = -1;
  const q = query.toLowerCase().trim();
  if (!q) {
    renderPaletteResults(_hiddenSurfaces);
    return;
  }
  const filtered = _hiddenSurfaces.filter(s =>
    s.label.toLowerCase().includes(q) || s.id.toLowerCase().includes(q)
  );
  renderPaletteResults(filtered);
}

// ═══════════════════════════════════════════════════════════════════════════