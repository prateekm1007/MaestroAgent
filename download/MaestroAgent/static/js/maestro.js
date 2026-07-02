
// Round 78: Toast notification system (replaces alert/confirm)
function showToast(message, type) {
  type = type || 'info';
  var toast = document.createElement('div');
  toast.className = 'toast ' + type;
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(function() {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.3s';
    setTimeout(function() { toast.remove(); }, 300);
  }, 3000);
}
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
  // Round 46 — 4 unified meta-surfaces
  today: 'Today', memory: 'Memory', 'ask-v2': 'Ask', more: 'More',
  // Legacy meta-surfaces (accessible via Ctrl+K)
  work: 'Work', learn: 'Learn',
  evolution: 'Evolution Report',
  cognition: 'Cognitive Organs',
  autobiography: "Your Organization's Story",
  playbook: 'Role Playbooks',
  personal: 'Personal Mode',
  // Deep capabilities (existing surfaces)
  home: 'Home', inbox: 'Inbox', simulator: 'Decision Simulator',
  hayek: 'Hayek Lens', flow: 'Knowledge Flow',
  ask: 'Ask the Organization', customer: 'Customer Judgment',
  physics: 'Organizational Physics', debate: 'Debate',
  live: 'Meeting Analyzer',
  intents: 'Intent Cascade',
  contradictions: 'Contradictions',
  predictions: 'Prediction Market',
  assumptions: 'Dangerous Assumptions',
  'eng-signals': 'Signals', 'eng-oem': 'OEM Builder',
  'eng-audit': 'Audit Log', 'eng-settings': 'Settings',
  // Round 47 — Block 1
  canvas: 'Decision Canvas', coordination: 'Coordination Engine',
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
  // Round 78 Phase 3: check if demo seed is active and watermark the UI.
  // The auditor flagged "demo data conflated with production" — this adds
  // a visible "DEMO DATA" badge so users always know when they're looking
  // at synthetic data vs real tenant data.
  fetch((MAESTRO_API || '') + '/api/health').then(r => r.json()).then(data => {
    if (data.demo_seed) {
      const badge = document.createElement('div');
      badge.id = 'demo-watermark';
      badge.style.cssText = 'position:fixed;top:0;right:0;z-index:99999;background:#f59e0b;color:#000;font-size:11px;font-weight:700;padding:4px 12px;border-radius:0 0 0 8px;letter-spacing:0.5px;box-shadow:0 2px 8px rgba(0,0,0,0.3)';
      badge.textContent = 'DEMO DATA';
      badge.title = 'This instance is running with synthetic demo data (MAESTRO_DEMO_SEED=true). All insights, signals, and learning objects are fictional.';
      document.body.appendChild(badge);
    }
  }).catch(() => {});
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
  { id: 'live', label: 'Meeting Analyzer — transcript intelligence', group: 'CEO Product' },
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
  { id: 'playbook', label: 'Role Playbooks — Sales, Marketing, Product', group: 'Daily Work' },
  { id: 'personal', label: 'Personal Mode — your life, your memory, your decisions', group: 'Personal' },
  // Round 47 — Block 1: Canvas + Per-Teammate (command-palette only, NOT sidebar)
  { id: 'canvas', label: 'Canvas — visual decision mapping', group: 'Round 47' },
  { id: 'coordination', label: 'Coordination Engine — multi-team decision input', group: 'Round 59' },
];

function openCommandPalette() {
  let palette = document.getElementById('command-palette');
  if (!palette) {
    palette = document.createElement('div');
    palette.id = 'command-palette';
    palette.className = 'fixed inset-0 z-50';
    palette.style.cssText = 'display:flex;align-items:flex-start;justify-content:center;padding-top:120px;background:rgba(0,0,0,0.5);';
    palette.innerHTML = `
      <div class="b-bg-surface">
        <input type="text" id="command-palette-input" placeholder="Search surfaces…"
               class="b-w-full-7"
               aria-label="Search surfaces"
               oninput="filterCommandPalette(this.value)"
               onkeydown="handlePaletteKeydown(event)">
        <div id="command-palette-results" class="b-flex-u-2"></div>
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
    results.innerHTML = '<div class="b-p20-text">No surfaces found</div>';
    return;
  }
  let currentGroup = '';
  results.innerHTML = surfaces.map(s => {
    const groupHeader = s.group !== currentGroup ? `<div class="b-p8164-fs10">${escapeHtml(s.group)}</div>` : '';
    currentGroup = s.group;
    return groupHeader + `<div class="palette-result" class="b-p1016-cursor" onmouseenter="this.style.background='var(--surface-2)'" onmouseleave="this.style.background='transparent'" onclick="navTo('${escapeJs(s.id)}');closeCommandPalette();">${escapeHtml(s.label)}</div>`;
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