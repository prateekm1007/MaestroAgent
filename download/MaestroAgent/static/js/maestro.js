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
  }
});

// ═══════════════════════════════════════════════════════════════════════════