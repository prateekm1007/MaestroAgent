'use strict';

// ═══════════════════════════════════════════════════════════════════════════
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
  home: 'Home', inbox: 'Inbox', simulator: 'Decision Simulator',
  hayek: 'Hayek Lens', flow: 'Knowledge Flow', memory: 'Memory Replay',
  ask: 'Ask the Organization', customer: 'Customer Judgment',
  physics: 'Organizational Physics', debate: 'Debate',
  live: 'Live Meeting',
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
  navTo(hash && document.getElementById('surface-' + hash) ? hash : 'home');
});

document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  if ((e.metaKey || e.ctrlKey) && e.key >= '1' && e.key <= '9') {
    e.preventDefault();
    const surfaces = ['home','inbox','simulator','hayek','flow','memory','ask','customer','physics','debate'];
    const idx = parseInt(e.key) - 1;
    if (surfaces[idx]) navTo(surfaces[idx]);
  }
  if (e.key === 'Escape') {
    document.getElementById('exec-autocomplete').classList.remove('active');
  }
});

// ═══════════════════════════════════════════════════════════════════════════
// SWR CACHE — Stale-While-Revalidate with retry, offline, cancellation
// ═══════════════════════════════════════════════════════════════════════════

const SWR = {
  // Cache: key → { data, timestamp, promise, abort, error, url }
  _cache: new Map(),
  _subscribers: new Map(),
  _online: navigator.onLine,
  DEDUP_MS: 2000,
  STALE_MS: 30000,
  MAX_RETRIES: 3,
  RETRY_DELAYS: [1000, 2000, 4000],

  init() {
    window.addEventListener('online', () => {
      this._online = true;
      this.revalidateAll();
      hideOfflineBanner();
    });
    window.addEventListener('offline', () => {
      this._online = false;
      showOfflineBanner();
    });
  },

  on(key, callback) {
    if (!this._subscribers.has(key)) this._subscribers.set(key, new Set());
    this._subscribers.get(key).add(callback);
    const entry = this._cache.get(key);
    if (entry) {
      callback({ data: entry.data, error: entry.error, loading: false, fromCache: true });
    }
    return () => this._subscribers.get(key)?.delete(callback);
  },

  _notify(key, state) {
    const subs = this._subscribers.get(key);
    if (subs) subs.forEach(cb => { try { cb(state); } catch (e) { console.warn(e); } });
  },

  async fetch(key, url, options = {}) {
    const now = Date.now();
    const entry = this._cache.get(key);

    // Dedup: if a fetch is in-flight, return its promise
    if (entry?.promise && now - entry.timestamp < this.DEDUP_MS) {
      return entry.promise;
    }

    // Cancel any previous in-flight request for this key
    if (entry?.abort) {
      try { entry.abort.abort(); } catch (e) {}
    }

    const abort = new AbortController();
    const fetchPromise = this._doFetch(key, url, { ...options, signal: abort.signal });

    this._cache.set(key, {
      data: entry?.data,
      timestamp: now,
      promise: fetchPromise,
      abort,
      error: null,
      url,
    });

    // If we have stale data, notify immediately (stale-while-revalidate)
    if (entry?.data) {
      this._notify(key, { data: entry.data, error: null, loading: true, fromCache: true });
    } else {
      this._notify(key, { data: null, error: null, loading: true, fromCache: false });
    }

    return fetchPromise;
  },

  async _doFetch(key, url, options, retryCount = 0) {
    try {
      const resp = await fetch(MAESTRO_API + url, options);
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
      }
      const data = await resp.json();
      const entry = this._cache.get(key);
      this._cache.set(key, {
        ...entry,
        data,
        timestamp: Date.now(),
        promise: null,
        abort: null,
        error: null,
        url,
      });
      this._notify(key, { data, error: null, loading: false, fromCache: false });
      return data;
    } catch (err) {
      if (err.name === 'AbortError') {
        return null;
      }

      // Retry with exponential backoff
      if (retryCount < this.MAX_RETRIES && this._online) {
        const delay = this.RETRY_DELAYS[retryCount] || 4000;
        await new Promise(r => setTimeout(r, delay));
        return this._doFetch(key, url, options, retryCount + 1);
      }

      // Final failure — serve cached data if available, else error
      const entry = this._cache.get(key);
      const cachedData = entry?.data;
      this._cache.set(key, {
        ...entry,
        promise: null,
        abort: null,
        error: err,
      });
      if (cachedData) {
        this._notify(key, { data: cachedData, error: err, loading: false, fromCache: true, offline: !this._online });
        return cachedData;
      } else {
        this._notify(key, { data: null, error: err, loading: false, fromCache: false });
        throw err;
      }
    }
  },

  mutate(key, updater) {
    const entry = this._cache.get(key);
    if (!entry) return;
    const newData = typeof updater === 'function' ? updater(entry.data) : updater;
    this._cache.set(key, { ...entry, data: newData });
    this._notify(key, { data: newData, error: null, loading: false, fromCache: true, optimistic: true });
  },

  invalidate(key) {
    const entry = this._cache.get(key);
    if (!entry?.url) return;
    this.fetch(key, entry.url);
  },

  invalidatePrefix(prefix) {
    for (const [key, entry] of this._cache.entries()) {
      if (key.startsWith(prefix) && entry?.url) {
        this.fetch(key, entry.url);
      }
    }
  },

  revalidateAll() {
    for (const [key, entry] of this._cache.entries()) {
      if (entry?.url && !entry.promise) {
        this.fetch(key, entry.url);
      }
    }
  },

  get(key) {
    return this._cache.get(key)?.data;
  },
};

SWR.init();

// ═══════════════════════════════════════════════════════════════════════════
// API HELPERS — typed wrappers around SWR.fetch
// ═══════════════════════════════════════════════════════════════════════════

const api = {
  getOEM: (path) => SWR.fetch('oem:' + path, '/api/oem' + path),
  postOEM: (path, body) =>
    SWR.fetch('oem:' + path, '/api/oem' + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  getImports: () => SWR.fetch('imports:list', '/api/imports'),
  getOAuthStatus: () => SWR.fetch('oauth:status', '/api/oauth/status'),
};

// ═══════════════════════════════════════════════════════════════════════════
// ERROR BOUNDARY — global error toast + offline banner
// ═══════════════════════════════════════════════════════════════════════════

function showError(message, duration = 5000) {
  let toast = document.getElementById('error-toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'error-toast';
    toast.className = 'fixed top-4 right-4 bg-brand-rose/20 border border-brand-rose/40 text-brand-rose px-4 py-3 rounded-lg shadow-2xl text-sm z-50 max-w-md';
    document.body.appendChild(toast);
  }
  toast.innerHTML = `<div class="flex items-start gap-2">
    <span class="text-brand-rose font-bold">!</span>
    <div class="flex-1">${escapeHtml(message)}</div>
    <button onclick="this.parentElement.parentElement.remove()" class="text-brand-rose/60 hover:text-brand-rose">x</button>
  </div>`;
  toast.style.display = 'block';
  clearTimeout(toast._timeout);
  toast._timeout = setTimeout(() => { toast.style.display = 'none'; }, duration);
}

function showOfflineBanner() {
  let banner = document.getElementById('offline-banner');
  if (!banner) {
    banner = document.createElement('div');
    banner.id = 'offline-banner';
    banner.className = 'fixed top-0 left-0 right-0 bg-brand-amber/20 border-b border-brand-amber/40 text-brand-amber text-center py-1.5 text-xs z-50';
    banner.innerHTML = 'Offline — showing cached data. Changes may not persist.';
    document.body.appendChild(banner);
  }
  banner.style.display = 'block';
}

function hideOfflineBanner() {
  const banner = document.getElementById('offline-banner');
  if (banner) banner.style.display = 'none';
}

// ═══════════════════════════════════════════════════════════════════════════
// RENDER HELPERS
// ═══════════════════════════════════════════════════════════════════════════

function escapeHtml(s) {
  if (s == null) return '';
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// ═══════════════════════════════════════════════════════════════════════════
// VIRTUALIZATION — render only visible items for large lists
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Render a large list with windowing — only visible items are in the DOM.
 * Uses IntersectionObserver for infinite scroll.
 *
 * @param {HTMLElement} container - The scroll container
 * @param {Array} items - All items
 * @param {Function} renderFn - (item, index) => HTML string
 * @param {number} pageSize - Items per page (default 50)
 */
function renderVirtualized(container, items, renderFn, pageSize = 50) {
  let visibleCount = Math.min(pageSize, items.length);
  let offset = 0;

  function renderPage() {
    const page = items.slice(0, visibleCount);
    container.innerHTML = page.map((item, i) => renderFn(item, i)).join('');

    // Add "Load more" sentinel if there are more items
    if (visibleCount < items.length) {
      const sentinel = document.createElement('div');
      sentinel.id = 'virtualized-sentinel';
      sentinel.className = 'text-center py-3 text-[11px] text-fg-500 cursor-pointer hover:text-fg-300';
      sentinel.textContent = `Load more (${items.length - visibleCount} remaining)`;
      sentinel.onclick = () => {
        visibleCount = Math.min(visibleCount + pageSize, items.length);
        renderPage();
      };
      container.appendChild(sentinel);
    }
  }

  renderPage();
}

function formatConfidence(c) {
  if (c == null) return '—';
  return Number(c).toFixed(2);
}

function formatTimestamp(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return escapeHtml(ts);
    return d.toLocaleString();
  } catch (e) {
    return escapeHtml(ts);
  }
}

function loadingHTML(el, msg) {
  el.innerHTML = `<div class="loading-state"><span class="spinner"></span> ${msg || 'Loading…'}</div>`;
}
function errorHTML(el, msg, retryFn) {
  const retryBtn = retryFn ? `<button onclick="${retryFn}" class="btn btn-ghost text-[10px] ml-2">Retry</button>` : '';
  el.innerHTML = `<div class="error-state">${escapeHtml(msg)}${retryBtn}</div>`;
}
function emptyHTML(el, msg) {
  el.innerHTML = `<div class="empty-state">${escapeHtml(msg)}</div>`;
}

// ═══════════════════════════════════════════════════════════════════════════
// SURFACE LOADER DISPATCH
// ═══════════════════════════════════════════════════════════════════════════

function loadSurfaceData(surface) {
  switch (surface) {
    case 'home': loadDashboard(); break;
    case 'inbox': loadInbox(); break;
    case 'simulator': loadSimulator(); break;
    case 'hayek': loadHayek(); break;
    case 'flow': loadKnowledge(); break;
    case 'memory': loadMemory(); break;
    case 'physics': loadLaws(''); break;
    case 'debate': loadDebate(); break;
    case 'customer': loadCustomerJudgment(); break;
    case 'eng-signals': loadEngSignals(); break;
    case 'eng-oem': loadEngOEM(); break;
    case 'eng-audit': loadEngAudit(); break;
    case 'eng-settings': loadEngSettings(); break;
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// AMBIENT ORGANIZATIONAL JUDGMENT — Pulse, Feed, Narrative, Cognitive Load
// ═══════════════════════════════════════════════════════════════════════════

async function loadPulse() {
  const body = document.getElementById('pulse-body');
  const stateEl = document.getElementById('pulse-state');
  if (!body) return;
  try {
    const p = await api.getOEM('/pulse');
    stateEl.textContent = p.state;
    const stateColor = p.state === 'healthy' || p.state === 'execution_accelerating' ? 'text-green-400'
      : p.state === 'turbulent' || p.state === 'trust_falling' ? 'text-red-400'
      : p.state === 'knowledge_blocked' || p.state === 'decision_stalled' ? 'text-yellow-400'
      : 'text-fg-300';
    stateEl.className = `text-[10px] font-semibold ${stateColor}`;
    body.innerHTML = `
      <div class="grid grid-cols-2 gap-2 text-xs">
        ${[['Temperature', p.temperature], ['Momentum', p.momentum], ['Alignment', p.alignment], ['Trust', p.trust], ['Knowledge', p.knowledge_mobility], ['Decision Speed', p.decision_speed]].map(([label, val]) => {
          const color = val > 70 ? 'text-green-400' : val < 40 ? 'text-red-400' : 'text-yellow-400';
          return `<div><div class="text-[10px] text-fg-500 uppercase">${label}</div><div class="font-bold ${color}">${Math.round(val)}</div></div>`;
        }).join('')}
      </div>
      <div class="mt-3 pt-3 border-t border-white/[0.05] text-xs text-fg-300">${escapeHtml(p.narrative)}</div>
    `;
  } catch (e) {
    body.innerHTML = `<div class="empty-state">Pulse unavailable: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadNarrative() {
  const body = document.getElementById('narrative-body');
  const dateEl = document.getElementById('narrative-date');
  if (!body) return;
  try {
    const n = await api.getOEM('/narrative');
    dateEl.textContent = n.date;
    body.innerHTML = `
      <div class="text-sm font-semibold text-white mb-2">${escapeHtml(n.title)}</div>
      <div class="text-xs text-fg-300 whitespace-pre-line mb-3">${escapeHtml(n.body)}</div>
      ${n.highlights && n.highlights.length > 0 ? `
        <div class="space-y-1">
          ${n.highlights.slice(0, 5).map(h => {
            const color = h.impact === 'positive' ? 'text-green-400' : h.impact === 'negative' ? 'text-red-400' : h.impact === 'warning' ? 'text-yellow-400' : 'text-fg-400';
            return `<div class="text-[11px] ${color}">• ${escapeHtml(h.text)}</div>`;
          }).join('')}
        </div>
      ` : ''}
      ${n.watch_for && n.watch_for.length > 0 ? `
        <div class="mt-2 pt-2 border-t border-white/[0.05] text-[10px] text-amber-400">${n.watch_for.slice(0, 2).map(w => escapeHtml(w)).join(' · ')}</div>
      ` : ''}
    `;
  } catch (e) {
    body.innerHTML = `<div class="empty-state">Narrative unavailable: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadFeed() {
  const body = document.getElementById('feed-body');
  if (!body) return;
  try {
    const data = await api.getOEM('/feed?limit=15');
    if (!data.events || data.events.length === 0) {
      body.innerHTML = '<div class="empty-state">No significant events. The organization is quiet.</div>';
      return;
    }
    body.innerHTML = data.events.map(e => {
      const color = e.event_type.includes('strengthened') || e.event_type.includes('renewed') || e.event_type.includes('correct') ? 'border-l-green-400'
        : e.event_type.includes('broken') || e.event_type.includes('churned') || e.event_type.includes('invalidated') ? 'border-l-red-400'
        : e.event_type.includes('drift') || e.event_type.includes('risk') || e.event_type.includes('overloaded') ? 'border-l-yellow-400'
        : 'border-l-cyan-400';
      return `
        <div class="border-l-2 ${color} pl-3 py-1.5 mb-1.5 cursor-pointer hover:bg-white/[0.02]" onclick="openFeedEvent('${escapeHtml(e.event_type)}', '${escapeHtml(e.entity_id)}')">
          <div class="flex items-center justify-between">
            <div class="text-xs font-semibold text-white">${escapeHtml(e.title)}</div>
            <div class="text-[9px] text-fg-500">${formatTimestamp(e.timestamp)}</div>
          </div>
          <div class="text-[10px] text-fg-400 mt-0.5">${escapeHtml(e.why_it_matters)}</div>
          <div class="text-[10px] text-fg-500 mt-0.5">→ ${escapeHtml(e.recommended_action)}</div>
        </div>
      `;
    }).join('');
  } catch (e) {
    body.innerHTML = `<div class="empty-state">Feed unavailable: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadCognitiveLoad() {
  const body = document.getElementById('ocl-body');
  const levelEl = document.getElementById('ocl-level');
  if (!body) return;
  try {
    const ocl = await api.getOEM('/cognitive-load');
    const color = ocl.level === 'low' ? 'text-green-400' : ocl.level === 'moderate' ? 'text-yellow-400' : ocl.level === 'high' ? 'text-orange-400' : 'text-red-400';
    levelEl.textContent = `${ocl.level} (${ocl.score})`;
    levelEl.className = `text-[10px] font-semibold ${color}`;
    const topFactors = Object.entries(ocl.factors).sort((a, b) => b[1].score - a[1].score).slice(0, 4);
    body.innerHTML = `
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        ${topFactors.map(([name, f]) => {
          const fc = f.score > 60 ? 'text-red-400' : f.score > 40 ? 'text-yellow-400' : 'text-green-400';
          return `<div><div class="text-[10px] text-fg-500 uppercase">${name.replace(/_/g, ' ')}</div><div class="font-bold ${fc}">${Math.round(f.score)}</div><div class="text-[9px] text-fg-400">${escapeHtml(f.detail)}</div></div>`;
        }).join('')}
      </div>
      <div class="mt-3 pt-3 border-t border-white/[0.05] text-xs text-fg-300">${escapeHtml(ocl.narrative)}</div>
      ${ocl.recommendations && ocl.recommendations.length > 0 ? `
        <div class="mt-2 text-[10px] text-cyan-400">→ ${escapeHtml(ocl.recommendations[0].recommendation)}</div>
      ` : ''}
    `;
  } catch (e) {
    body.innerHTML = `<div class="empty-state">OCL unavailable: ${escapeHtml(e.message)}</div>`;
  }
}

function openFeedEvent(eventType, entityId) {
  // Open the time machine for this entity
  if (entityId) {
    openDrilldown('feed_event', entityId);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// HOME — Executive Cognition Center (9 sections, all from OEM)
// ═══════════════════════════════════════════════════════════════════════════

async function loadDashboard() {
  const stateEl = document.getElementById('home-oem-state');
  const providersBadge = document.getElementById('oem-providers-badge');

  // ── Ambient layers: Pulse, Narrative, Feed, Cognitive Load ──
  loadPulse();
  loadNarrative();
  loadFeed();
  loadCognitiveLoad();

  // OEM State (reference) — fetch independently (fast)
  api.getOEM('/dashboard').then(data => {
    const m = data.metrics;
    stateEl.innerHTML = `
      <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
        <div class="metric metric-clickable" onclick="openDrilldown('metric', 'signals_processed')"><div class="metric-value">${m.signals_processed}</div><div class="metric-label">Signals</div></div>
        <div class="metric metric-clickable" onclick="openDrilldown('metric', 'learning_objects')"><div class="metric-value">${m.learning_objects}</div><div class="metric-label">Learning Objects</div></div>
        <div class="metric metric-clickable" onclick="openDrilldown('metric', 'laws_inferred')"><div class="metric-value">${m.laws_inferred}</div><div class="metric-label">Laws</div></div>
        <div class="metric metric-clickable" onclick="openDrilldown('metric', 'validated_laws')"><div class="metric-value">${m.validated_laws}</div><div class="metric-label">Validated</div></div>
        <div class="metric metric-clickable" onclick="openDrilldown('metric', 'recommendations_active')"><div class="metric-value">${m.recommendations_active}</div><div class="metric-label">Recommendations</div></div>
        <div class="metric metric-clickable" onclick="openDrilldown('metric', 'p1_cluster_risk')"><div class="metric-value">${formatConfidence(m.p1_cluster_risk)}</div><div class="metric-label">P1 Risk</div></div>
      </div>
      <div class="mt-4 pt-4 border-t border-white/[0.05] flex flex-wrap gap-2">
        ${data.providers_connected.map(p => `<span class="tag tag-cyan">${escapeHtml(p)}</span>`).join('')}
      </div>
    `;
    providersBadge.textContent = data.providers_connected.length + ' providers';
    document.getElementById('oem-status').innerHTML = `<span class="text-brand-cyan">●</span> <span>OEM connected · ${m.signals_processed} signals · ${m.laws_inferred} laws</span>`;
    document.getElementById('oem-status-badge').textContent = 'OEM ONLINE';
    document.getElementById('oem-status-badge').className = 'text-[10px] font-semibold text-brand-cyan';
  }).catch(e => {
    errorHTML(stateEl, 'Failed to load OEM state: ' + e.message, 'loadDashboard()');
    document.getElementById('oem-status').innerHTML = `<span class="text-brand-rose">●</span> <span>OEM unreachable: ${escapeHtml(e.message)}</span>`;
    document.getElementById('oem-status-badge').textContent = 'OEM OFFLINE';
    document.getElementById('oem-status-badge').className = 'text-[10px] font-semibold text-brand-rose';
  });

  // CEO Briefing — powers sections 1 + 2
  try {
    const briefing = await api.getOEM('/ceo-briefing');
    const tsEl = document.getElementById('home-briefing-timestamp');
    if (tsEl && briefing.generated_at) tsEl.textContent = `Last updated: ${formatTimestamp(briefing.generated_at)}`;

    // ── Section 1: Today's Attention (one thing + CEO-only decisions) ──
    renderECCAttention(briefing);

    // ── Section 2: What Changed Overnight ──
    renderECCOvernight(briefing);
  } catch (e) {
    document.getElementById('ecc-attention').innerHTML = `<div class="error-state">Failed: ${escapeHtml(e.message)} <button onclick="loadDashboard()" class="btn btn-ghost text-[10px] ml-2">Retry</button></div>`;
    document.getElementById('ecc-overnight').innerHTML = `<div class="error-state">Failed: ${escapeHtml(e.message)}</div>`;
  }

  // ── Section 3: Hayek Lens ──
  try {
    const knowledge = await api.getOEM('/knowledge');
    renderECCHayek(knowledge);
  } catch (e) {
    document.getElementById('ecc-hayek').innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`;
  }

  // ── Section 4: Knowledge Flow ──
  try {
    const knowledge = SWR.get('oem:/knowledge') || await api.getOEM('/knowledge');
    renderECCFlow(knowledge);
  } catch (e) {
    document.getElementById('ecc-flow').innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`;
  }

  // ── Section 5: Hidden Experts ──
  try {
    const knowledge = SWR.get('oem:/knowledge') || await api.getOEM('/knowledge');
    renderECCExperts(knowledge);
  } catch (e) {
    document.getElementById('ecc-experts').innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`;
  }

  // ── Section 6: Decision Simulator ──
  try {
    const sim = await api.getOEM('/simulator');
    renderECCSimulator(sim);
  } catch (e) {
    document.getElementById('ecc-simulator').innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`;
  }

  // ── Section 7: Ask the Organization ──
  renderECCAsk();

  // ── Section 8: Execution Replay ──
  try {
    const learning = await api.getOEM('/learning');
    renderECCReplay(learning);
  } catch (e) {
    document.getElementById('ecc-replay').innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`;
  }

  // ── Section 9: Executive Autocomplete ──
  renderECCAutocomplete();

  // ── Section 10: Digital Twin ──
  try {
    const twinState = await api.getOEM('/twin/state');
    renderECCTwin(twinState);
  } catch (e) {
    document.getElementById('ecc-twin').innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`;
  }
}

// ─── Enriched Recommendation Card (evidence, confidence, provenance, impact, accuracy, drill-down) ──
function renderEnrichedRec(r, opts = {}) {
  const urgencyTag = r.urgency === 'urgent' ? 'tag-rose' : r.urgency === 'normal' ? 'tag-amber' : 'tag-gray';
  const provChain = (r.provenance || []).slice(0, 3).map(p => {
    const key = p.oem_change || p.gate || p.entity || p.domain || 'evidence';
    return `<span class="prov-node">${escapeHtml(key)}</span>`;
  }).join('<span class="prov-arrow">→</span>');
  const evidenceCount = r.evidence_count || (r.provenance || []).length || 0;
  const linkedLaws = r.linked_laws || [];
  const compact = opts.compact;
  return `<div class="card ${r.urgency === 'urgent' ? 'urgent' : ''} mb-3 cursor-pointer" onclick="openDrilldown('recommendation', '${escapeHtml(r.title)}')">
    <div class="flex items-start justify-between mb-2">
      <div class="flex-1">
        <div class="text-sm font-semibold text-white mb-1">${escapeHtml(r.title)}</div>
        ${!compact ? `<div class="text-[11px] text-fg-400 leading-relaxed">${escapeHtml(r.description || '')}</div>` : ''}
      </div>
      <span class="tag ${urgencyTag} ml-3">${escapeHtml(r.urgency || 'normal')}</span>
    </div>
    ${provChain ? `<div class="prov-chain mt-2 mb-2">${provChain}</div>` : ''}
    <div class="flex items-center gap-3 text-[10px] text-fg-500 mt-2 flex-wrap">
      <div class="conf-bar" style="width:120px;"><div class="conf-bar-track"><div class="conf-bar-fill" style="width:${(r.confidence||0)*100}%"></div></div><span class="text-brand-cyan font-bold">${formatConfidence(r.confidence)}</span></div>
      <span>·</span><span>${evidenceCount} evidence</span>
      ${linkedLaws.length ? `<span>·</span><span>Laws: ${linkedLaws.join(', ')}</span>` : ''}
    </div>
    ${!compact && r.impact ? `<div class="mt-2 text-[11px] text-fg-300"><strong>Expected impact:</strong> ${escapeHtml(r.impact)}</div>` : ''}
    ${!compact ? `<div class="mt-2 pt-2 border-t border-white/[0.05] flex items-center gap-3 text-[10px] text-fg-600">
      <span>Provenance: ${evidenceCount} signals</span>
      <span>·</span>
      <span>Confidence: ${formatConfidence(r.confidence)}</span>
      ${r.evidence_strength ? `<span>·</span><span>Strength: ${r.evidence_strength}</span>` : ''}
      <span>·</span>
      <span class="text-brand-violet cursor-pointer hover:text-brand-cyan">Drill-down →</span>
    </div>` : ''}
  </div>`;
}

// ─── Section 1: Today's Attention ──
function renderECCAttention(briefing) {
  const el = document.getElementById('ecc-attention');
  const ot = briefing.one_thing;
  const decisions = briefing.decisions;
  document.getElementById('ecc-attention-count').textContent = `${decisions.decisions.length} decision${decisions.decisions.length !== 1 ? 's' : ''}`;
  const urgencyColor = ot.urgency === 'urgent' ? 'rose' : ot.urgency === 'normal' ? 'amber' : 'gray';
  el.innerHTML = `
    <div class="space-y-4">
      <div class="p-3 rounded-lg bg-brand-violet/[0.06] border border-brand-violet/15">
        <div class="text-[10px] uppercase tracking-wider text-brand-violet font-semibold mb-1">If you do one thing today</div>
        <div class="text-base font-bold text-white">${escapeHtml(ot.title)}</div>
        <div class="text-[11px] text-fg-400 mt-1">${escapeHtml(ot.why)}</div>
        <div class="text-sm text-brand-violet font-medium mt-2">${escapeHtml(ot.recommendation)}</div>
        <div class="flex items-center gap-3 pt-2">
          <span class="tag tag-${urgencyColor}">${escapeHtml(ot.urgency)}</span>
          <div class="conf-bar" style="width:100px;"><div class="conf-bar-track"><div class="conf-bar-fill" style="width:${ot.confidence*100}%"></div></div><span class="text-brand-cyan font-bold">${formatConfidence(ot.confidence)}</span></div>
          <span class="text-[10px] text-fg-500">confidence</span>
        </div>
        <div class="text-[11px] text-fg-300 mt-2">${escapeHtml(ot.impact)}</div>
        ${ot.rec_id ? `<button class="btn btn-primary text-[11px] mt-2" onclick="event.stopPropagation(); openDrilldown('recommendation', '${escapeHtml(ot.title)}')">Investigate →</button>` : ''}
      </div>
      ${decisions.decisions.length > 0 ? `
        <div>
          <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-2">CEO-only decisions</div>
          <div class="space-y-2">
            ${decisions.decisions.map(d => {
              const drillType = d.type === 'urgent_decision' ? 'recommendation' : d.type === 'retention' ? 'pattern' : 'law';
              const drillId = d.linked_laws && d.linked_laws.length ? d.linked_laws[0] : d.title;
              return `<div class="flex items-start gap-3 p-3 rounded-lg bg-brand-purple/[0.04] border border-brand-purple/10 cursor-pointer hover:bg-brand-purple/[0.08] transition-colors" onclick="openDrilldown('${drillType}', '${escapeHtml(drillId)}')">
                <div class="w-7 h-7 rounded-md bg-brand-purple/15 flex items-center justify-center flex-shrink-0"><span class="text-brand-purple text-sm font-bold">!</span></div>
                <div class="flex-1">
                  <div class="text-[12px] font-semibold text-fg-100">${escapeHtml(d.title)}</div>
                  <div class="text-[10px] text-fg-500 mt-0.5">${escapeHtml(d.question)}</div>
                  <div class="text-[10px] text-brand-violet mt-1">${escapeHtml(d.recommendation)}</div>
                </div>
                <span class="text-[10px] text-fg-500">conf ${formatConfidence(d.confidence)}</span>
              </div>`;
            }).join('')}
          </div>
        </div>
      ` : ''}
    </div>
  `;
}

// ─── Section 2: What Changed Overnight ──
function renderECCOvernight(briefing) {
  const el = document.getElementById('ecc-overnight');
  const ov = briefing.overnight;
  document.getElementById('ecc-overnight-count').textContent = ov.summary;
  if (!ov.changes || ov.changes.length === 0) {
    emptyHTML(el, 'Nothing new. The org is stable. The OEM will surface new patterns as signals flow.');
    return;
  }
  el.innerHTML = `
    <div class="mb-3 p-3 rounded-lg bg-brand-cyan/[0.04] border border-brand-cyan/10">
      <div class="text-sm font-semibold text-white">${escapeHtml(ov.headline)}</div>
      <div class="text-[11px] text-fg-500 mt-1">${escapeHtml(ov.headline_detail)}</div>
    </div>
    <div class="space-y-2">
      ${ov.changes.map(c => {
        const sevColor = c.severity === 'urgent' ? 'rose' : c.severity === 'warning' ? 'amber' : 'cyan';
        const drillType = c.type === 'hidden_expert' ? 'expert' : c.type === 'bottleneck' ? 'pattern' : c.type === 'concentration_risk' ? 'risk' : 'pattern';
        const drillId = c.entity || c.domain || c.title || c.detail;
        return `<div class="flex items-start gap-3 p-3 rounded-lg bg-brand-${sevColor}/[0.04] border border-brand-${sevColor}/10 cursor-pointer hover:bg-brand-${sevColor}/[0.08] transition-colors" onclick="openDrilldown('${drillType}', '${escapeHtml(drillId)}')">
          <div class="w-7 h-7 rounded-md bg-brand-${sevColor}/15 flex items-center justify-center flex-shrink-0"><span class="text-brand-${sevColor} text-sm font-bold">${c.type === 'hidden_expert' ? '?' : c.type === 'bottleneck' ? '!' : c.type === 'departure_risk' ? 'x' : 'v'}</span></div>
          <div class="flex-1"><div class="text-[12px] font-semibold text-fg-100">${escapeHtml(c.title)}</div><div class="text-[10px] text-fg-500 mt-0.5">${escapeHtml(c.detail)}</div></div>
          <span class="tag tag-${sevColor}">${escapeHtml(c.severity)}</span>
        </div>`;
      }).join('')}
    </div>
  `;
}

// ─── Section 3: Hayek Lens ──
function renderECCHayek(knowledge) {
  const el = document.getElementById('ecc-hayek');
  const risks = knowledge.concentration_risks || [];
  document.getElementById('ecc-hayek-count').textContent = `${risks.length} risk${risks.length !== 1 ? 's' : ''}`;
  if (risks.length === 0) { emptyHTML(el, 'No concentration risks detected.'); return; }
  el.innerHTML = `<div class="space-y-2">${risks.map(r => `
    <div class="card mb-2 cursor-pointer hover:bg-white/[0.02]" onclick="openDrilldown('risk', '${escapeHtml(r.domain)}')">
      <div class="text-sm font-semibold text-white">${escapeHtml(r.domain)}</div>
      <div class="text-[11px] text-fg-400 mt-1">Concentration: <span class="mono text-brand-rose">${r.score.toFixed(2)}</span></div>
      <div class="conf-bar mt-2"><div class="conf-bar-track"><div class="conf-bar-fill" style="width:${Math.min(r.score*10,100)}%;background:#ff5577;"></div></div></div>
      <div class="text-[10px] text-fg-600 mt-1">Click for evidence, people, prediction →</div>
    </div>`).join('')}</div>`;
}

// ─── Section 4: Knowledge Flow ──
function renderECCFlow(knowledge) {
  const el = document.getElementById('ecc-flow');
  const dups = knowledge.duplicate_work || [];
  const deaths = knowledge.knowledge_death || [];
  document.getElementById('ecc-flow-count').textContent = `${dups.length + deaths.length} issue${(dups.length + deaths.length) !== 1 ? 's' : ''}`;
  if (dups.length === 0 && deaths.length === 0) { emptyHTML(el, 'No duplicate work or knowledge death detected.'); return; }
  el.innerHTML = `
    ${dups.length > 0 ? `<div class="mb-3"><div class="text-[10px] uppercase text-fg-500 mb-2">Duplicate Work (${dups.length})</div>${dups.map(d => `
      <div class="card mb-2 cursor-pointer hover:bg-white/[0.02]" onclick="openDrilldown('pattern', '${escapeHtml(d.title || d.description)}')">
        <div class="text-sm font-semibold text-white">${escapeHtml(d.title)}</div>
        <div class="text-[11px] text-fg-400 mt-1">${escapeHtml(d.description)}</div>
        <div class="text-[10px] text-fg-600 mt-1">Domain: ${escapeHtml(d.domain)} · ${d.providers.join(', ')}</div>
      </div>`).join('')}</div>` : ''}
    ${deaths.length > 0 ? `<div><div class="text-[10px] uppercase text-fg-500 mb-2">Knowledge Death (${deaths.length})</div>${deaths.map(k => `
      <div class="card mb-2 cursor-pointer hover:bg-white/[0.02]" onclick="openDrilldown('pattern', '${escapeHtml(k.title || k.description)}')">
        <div class="text-sm font-semibold text-white">${escapeHtml(k.title)}</div>
        <div class="text-[11px] text-fg-400 mt-1">${escapeHtml(k.description)}</div>
        <div class="text-[10px] text-fg-600 mt-1">Boundary: ${escapeHtml(k.boundary)} · conf ${formatConfidence(k.confidence)}</div>
      </div>`).join('')}</div>` : ''}
  `;
}

// ─── Section 5: Hidden Experts ──
function renderECCExperts(knowledge) {
  const el = document.getElementById('ecc-experts');
  const experts = knowledge.hidden_experts || [];
  document.getElementById('ecc-experts-count').textContent = `${experts.length} expert${experts.length !== 1 ? 's' : ''}`;
  if (experts.length === 0) { emptyHTML(el, 'No hidden experts detected.'); return; }
  el.innerHTML = `<div class="space-y-2">${experts.map(e => `
    <div class="card mb-2 cursor-pointer hover:bg-white/[0.02]" onclick="openDrilldown('expert', '${escapeHtml(e.entity)}')">
      <div class="flex items-center gap-3">
        <div class="w-8 h-8 rounded-full bg-brand-purple/20 flex items-center justify-center text-xs font-bold text-brand-purple">${escapeHtml(e.entity.charAt(0).toUpperCase())}</div>
        <div class="flex-1">
          <div class="text-sm font-semibold text-white">${escapeHtml(e.entity)}</div>
          <div class="text-[11px] text-fg-400">Influence: <span class="mono text-brand-purple">${e.influence.toFixed(2)}</span> · ${e.domains ? e.domains.length : 0} domains</div>
        </div>
        ${e.domains && e.domains.length ? `<div class="flex flex-wrap gap-1">${e.domains.map(d => `<span class="tag tag-gray">${escapeHtml(d)}</span>`).join('')}</div>` : ''}
      </div>
      <div class="text-[10px] text-fg-600 mt-1">Click for evidence, timeline, prediction →</div>
    </div>`).join('')}</div>`;
}

// ─── Section 6: Decision Simulator ──
function renderECCSimulator(sim) {
  const el = document.getElementById('ecc-simulator');
  const s = sim.scenario;
  el.innerHTML = `
    <div class="space-y-3">
      <div>
        <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-1">Current Scenario</div>
        <div class="text-sm font-semibold text-white">${escapeHtml(s.title)}</div>
        <div class="text-[11px] text-fg-400 mt-1">${escapeHtml(s.description)}</div>
      </div>
      <div class="grid grid-cols-2 gap-4 pt-3 border-t border-white/[0.05]">
        <div><div class="text-[10px] uppercase text-fg-500">Recommendation</div><div class="text-sm text-brand-cyan mt-1">${escapeHtml(s.recommendation)}</div></div>
        <div><div class="text-[10px] uppercase text-fg-500">Confidence</div><div class="conf-bar mt-1"><div class="conf-bar-track"><div class="conf-bar-fill" style="width:${s.confidence*100}%"></div></div><span class="text-brand-cyan font-bold">${formatConfidence(s.confidence)}</span></div></div>
      </div>
      <div class="pt-3 border-t border-white/[0.05]">
        <div class="text-[10px] uppercase text-fg-500 font-semibold mb-1">Current Health</div>
        <div class="grid grid-cols-2 gap-2 text-[11px]">
          <div>P1 Risk: <span class="mono text-brand-amber">${formatConfidence(sim.current_health.p1_cluster_risk)}</span></div>
          <div>Incident Rate: <span class="mono text-brand-amber">${sim.current_health.incident_rate}</span></div>
          <div>Decision Velocity: <span class="mono text-brand-cyan">${sim.current_health.decision_velocity_days.toFixed(1)}d</span></div>
          <div>Release Frequency: <span class="mono text-brand-cyan">${sim.current_health.release_frequency.toFixed(1)}/wk</span></div>
        </div>
      </div>
      <div class="pt-3 border-t border-white/[0.05]">
        <div class="text-[10px] uppercase text-fg-500 font-semibold mb-1">Run What-If</div>
        <div class="flex items-center gap-3">
          <label class="text-[11px] text-fg-400">Hire count:</label>
          <input type="range" min="0" max="10" value="2" id="ecc-sim-hires" class="flex-1" oninput="document.getElementById('ecc-sim-val').textContent=this.value">
          <span class="text-xs font-bold text-brand-cyan mono" id="ecc-sim-val">2</span>
          <button class="btn btn-primary text-[11px]" onclick="runECCSimulation()">Run</button>
        </div>
        <div id="ecc-sim-result" class="mt-3"></div>
      </div>
    </div>
  `;
}

async function runECCSimulation() {
  const hires = parseInt(document.getElementById('ecc-sim-hires').value);
  const resultEl = document.getElementById('ecc-sim-result');
  resultEl.innerHTML = '<div class="loading-state"><span class="spinner"></span> Running...</div>';
  try {
    const resp = await fetch(MAESTRO_API + '/api/oem/simulate', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({inputs: {hire_count: hires}}),
    });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    resultEl.innerHTML = `
      <div class="grid grid-cols-2 gap-3 text-[11px]">
        <div class="p-3 rounded-lg bg-white/[0.02]">
          <div class="text-[10px] uppercase text-fg-500">Predicted P1 Risk</div>
          <div class="text-lg font-bold text-brand-amber mono">${formatConfidence(data.predicted.p1_cluster_risk)}</div>
          <div class="text-[10px] text-fg-600">Base: ${formatConfidence(data.base_health.p1_cluster_risk)}</div>
        </div>
        <div class="p-3 rounded-lg bg-white/[0.02]">
          <div class="text-[10px] uppercase text-fg-500">Predicted Velocity</div>
          <div class="text-lg font-bold text-brand-cyan mono">${data.predicted.decision_velocity_days}d</div>
          <div class="text-[10px] text-fg-600">Base: ${data.base_health.decision_velocity_days}d</div>
        </div>
      </div>
      <div class="mt-3 text-[10px] text-fg-500">Confidence: ${formatConfidence(data.confidence)} · Linked laws: ${data.linked_laws.join(', ') || 'none'}</div>
    `;
  } catch (e) { resultEl.innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`; }
}

// ─── Section 7: Ask the Organization ──
function renderECCAsk() {
  const el = document.getElementById('ecc-ask');
  el.innerHTML = `
    <div class="space-y-3">
      <div class="relative">
        <input type="text" class="ask-input w-full" placeholder="Ask anything about your organization..." id="ecc-ask-input" oninput="onECCAskInput(this.value)" onkeydown="if(event.key==='Enter'){submitECCAsk()}" aria-label="Ask the organization">
        <div id="ecc-ask-autocomplete" class="exec-autocomplete"></div>
      </div>
      <div id="ecc-ask-answer" style="display:none;" class="space-y-3">
        <div class="text-[11px] text-fg-400" id="ecc-ask-answer-text"></div>
        <div id="ecc-ask-citations" class="flex flex-wrap gap-1"></div>
        <div id="ecc-ask-path" class="text-[10px] text-fg-600"></div>
        <div id="ecc-ask-confidence" class="text-[10px] text-brand-cyan"></div>
      </div>
    </div>
  `;
}

let eccAskAbort = null;
async function onECCAskInput(value) {
  const dropdown = document.getElementById('ecc-ask-autocomplete');
  const v = value.trim();
  if (!v) { dropdown.classList.remove('active'); return; }
  if (eccAskAbort) eccAskAbort.abort();
  eccAskAbort = new AbortController();
  try {
    const resp = await fetch(MAESTRO_API + '/api/oem/autocomplete?q=' + encodeURIComponent(v) + '&limit=5', {signal: eccAskAbort.signal});
    if (!resp.ok) return;
    const data = await resp.json();
    const suggestions = data.suggestions || [];
    if (suggestions.length === 0) { dropdown.innerHTML = '<div class="exec-ac-header">No matches in OEM</div>'; dropdown.classList.add('active'); return; }
    dropdown.innerHTML = '<div class="exec-ac-header">From live OEM · ranked by recency, authority, outcome, feedback</div>' +
      suggestions.map((s, i) => `<div class="exec-ac-item" onclick="document.getElementById('ecc-ask-input').value='${escapeHtml(s.query)}'; document.getElementById('ecc-ask-autocomplete').classList.remove('active'); submitECCAsk('${escapeHtml(s.query)}')">
        <div class="exec-ac-completion"><span class="completed">${escapeHtml(s.completion)}</span></div>
        <div class="text-[9px] text-fg-600 mt-0.5">${escapeHtml(s.source_type)} · conf ${(s.confidence*100).toFixed(0)}% · ${s.citations.length} citations</div>
      </div>`).join('');
    dropdown.classList.add('active');
  } catch(e) { if (e.name !== 'AbortError') {} }
}

async function submitECCAsk(query) {
  const q = (query || document.getElementById('ecc-ask-input').value).trim();
  if (!q) return;
  document.getElementById('ecc-ask-input').value = '';
  document.getElementById('ecc-ask-autocomplete').classList.remove('active');
  const ans = document.getElementById('ecc-ask-answer');
  ans.style.display = 'block';
  document.getElementById('ecc-ask-answer-text').innerHTML = '<span class="spinner"></span> Asking the OEM...';
  try {
    const data = await api.getOEM('/ask?q=' + encodeURIComponent(q));
    document.getElementById('ecc-ask-answer-text').innerHTML = escapeHtml(data.answer).replace(/\n/g, '<br>');
    const sources = data.sources || [];
    document.getElementById('ecc-ask-citations').innerHTML = sources.length === 0 ? '<span class="text-[11px] text-fg-500">No sources cited.</span>' : sources.map(s => `<span class="source-cite">${escapeHtml(s)}</span>`).join('');
    document.getElementById('ecc-ask-confidence').textContent = `Confidence ${formatConfidence(data.confidence)} · ${sources.length} sources`;
  } catch(e) {
    document.getElementById('ecc-ask-answer-text').innerHTML = `<span class="text-brand-rose">Error: ${escapeHtml(e.message)}</span>`;
  }
}

// ─── Section 8: Execution Replay (historical accuracy + calibration) ──
function renderECCReplay(learning) {
  const el = document.getElementById('ecc-replay');
  const cal = learning.calibration || {};
  const overall = cal.overall || {};
  const accuracy = learning.historical_accuracy || {};
  const evidence = learning.improvement_evidence || {};
  document.getElementById('ecc-replay-count').textContent = `${overall.total_predictions || 0} prediction${(overall.total_predictions || 0) !== 1 ? 's' : ''}`;
  const buckets = cal.buckets || [];
  const trend = accuracy.trend || [];
  el.innerHTML = `
    <div class="space-y-4">
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div class="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <div class="text-[10px] uppercase text-fg-500">Accuracy</div>
          <div class="text-lg font-bold text-brand-cyan mono">${accuracy.accuracy != null ? (accuracy.accuracy * 100).toFixed(1) + '%' : '—'}</div>
          <div class="text-[10px] text-fg-600">${accuracy.resolved || 0} resolved</div>
        </div>
        <div class="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <div class="text-[10px] uppercase text-fg-500">Brier Score</div>
          <div class="text-lg font-bold text-brand-amber mono">${(overall.brier_score || 0).toFixed(4)}</div>
          <div class="text-[10px] text-fg-600">lower = better</div>
        </div>
        <div class="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <div class="text-[10px] uppercase text-fg-500">Calibration Error</div>
          <div class="text-lg font-bold text-brand-violet mono">${(overall.mean_calibration_error || 0).toFixed(4)}</div>
          <div class="text-[10px] text-fg-600">${evidence.is_calibrated ? 'well-calibrated' : 'needs calibration'}</div>
        </div>
        <div class="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <div class="text-[10px] uppercase text-fg-500">Feedback Events</div>
          <div class="text-lg font-bold text-brand-purple mono">${evidence.feedback_count || 0}</div>
          <div class="text-[10px] text-fg-600">CEO agree/reject</div>
        </div>
      </div>
      ${buckets.length > 0 ? `
        <div>
          <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-2">Calibration Diagram (10 buckets)</div>
          <div class="space-y-1">
            ${buckets.map(b => `
              <div class="flex items-center gap-2 text-[10px]">
                <span class="mono text-fg-500 w-16">${(b.expected_rate*100).toFixed(0)}% expected</span>
                <div class="flex-1 h-3 bg-white/[0.04] rounded overflow-hidden relative">
                  <div class="h-full bg-brand-cyan/40" style="width:${b.expected_rate*100}%"></div>
                  <div class="absolute top-0 h-full bg-brand-violet/60" style="width:${b.actual_rate*100}%"></div>
                </div>
                <span class="mono text-fg-400 w-16">${b.actual_rate > 0 ? (b.actual_rate*100).toFixed(0) + '% actual' : '—'}</span>
                <span class="text-fg-600 w-8">${b.predictions}</span>
              </div>`).join('')}
          </div>
          <div class="flex items-center gap-4 mt-2 text-[9px] text-fg-600">
            <span><span class="inline-block w-2 h-2 bg-brand-cyan/40 rounded"></span> Expected</span>
            <span><span class="inline-block w-2 h-2 bg-brand-violet/60 rounded"></span> Actual</span>
          </div>
        </div>
      ` : ''}
      ${trend.length > 0 ? `
        <div>
          <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-2">Accuracy Trend (weekly)</div>
          <div class="flex items-end gap-1 h-12">
            ${trend.map(t => `<div class="flex-1 bg-brand-cyan/40 rounded-t" style="height:${t.accuracy*100}%" title="${t.week}: ${(t.accuracy*100).toFixed(0)}% (${t.predictions} predictions)"></div>`).join('')}
          </div>
        </div>
      ` : ''}
      <div class="pt-3 border-t border-white/[0.05] text-[10px] text-fg-600">
        Drift events: ${evidence.drift_events_detected || 0} · Stale domains: ${evidence.stale_domains || 0} · Decaying patterns: ${evidence.decaying_patterns || 0}
      </div>
    </div>
  `;
}

// ─── Section 9: Executive Autocomplete (live preview) ──
function renderECCAutocomplete() {
  const el = document.getElementById('ecc-autocomplete');
  el.innerHTML = `
    <div class="space-y-3">
      <div class="text-[11px] text-fg-400">Type below to see real-time semantic suggestions from the OEM. Every suggestion includes completion, reason, confidence, evidence, citations, and expected outcome.</div>
      <div class="relative">
        <input type="text" class="ask-input w-full" placeholder="Try: we should, bottleneck, who knows, risk..." id="ecc-ac-input" oninput="onECCAutocompleteInput(this.value)" aria-label="Executive autocomplete">
        <div id="ecc-ac-dropdown" class="exec-autocomplete"></div>
      </div>
      <div id="ecc-ac-results" class="space-y-2"></div>
    </div>
  `;
}

let eccAcAbort = null;
async function onECCAutocompleteInput(value) {
  const dropdown = document.getElementById('ecc-ac-dropdown');
  const resultsEl = document.getElementById('ecc-ac-results');
  const v = value.trim();
  if (!v) { dropdown.classList.remove('active'); resultsEl.innerHTML = ''; return; }
  if (eccAcAbort) eccAcAbort.abort();
  eccAcAbort = new AbortController();
  try {
    const resp = await fetch(MAESTRO_API + '/api/oem/autocomplete?q=' + encodeURIComponent(v) + '&limit=5', {signal: eccAcAbort.signal});
    if (!resp.ok) return;
    const data = await resp.json();
    const suggestions = data.suggestions || [];
    if (suggestions.length === 0) {
      dropdown.classList.remove('active');
      resultsEl.innerHTML = '<div class="empty-state">No matches in OEM for "' + escapeHtml(v) + '"</div>';
      return;
    }
    dropdown.classList.remove('active');
    resultsEl.innerHTML = suggestions.map(s => `
      <div class="card mb-2 cursor-pointer" onclick="openDrilldown('${s.source_type.split(':')[0]}', '${escapeHtml(s.source_id)}')">
        <div class="text-sm font-semibold text-white">${escapeHtml(s.completion)}</div>
        <div class="text-[10px] text-fg-400 mt-1">${escapeHtml(s.reason)}</div>
        <div class="flex items-center gap-2 mt-2 text-[10px] text-fg-500 flex-wrap">
          <span class="mono text-brand-purple">[${escapeHtml(s.source_type)}]</span>
          <span class="text-brand-cyan">conf ${(s.confidence*100).toFixed(0)}%</span>
          <span>·</span><span>rank ${(s.rank_score*100).toFixed(0)}%</span>
          <span>·</span><span>${s.evidence.length} evidence</span>
          <span>·</span><span>${s.citations.length} citations</span>
        </div>
        ${s.expected_outcome ? `<div class="text-[10px] text-fg-600 mt-1 italic">→ ${escapeHtml(s.expected_outcome.substring(0, 100))}</div>` : ''}
        <div class="text-[10px] text-brand-violet mt-1">Click for full drill-down →</div>
      </div>
    `).join('');
  } catch(e) { if (e.name !== 'AbortError') {} }
}

function renderRecCard(r) {
  const urgencyTag = r.urgency === 'urgent' ? 'tag-rose' : r.urgency === 'normal' ? 'tag-amber' : 'tag-gray';
  const provChain = (r.provenance || []).slice(0, 3).map(p => {
    const key = p.oem_change || p.gate || p.entity || p.domain || 'evidence';
    return `<span class="prov-node">${escapeHtml(key)}</span>`;
  }).join('<span class="prov-arrow">→</span>');
  return `<div class="card ${r.urgency === 'urgent' ? 'urgent' : ''} mb-3 cursor-pointer" onclick="openDrilldown('recommendation', '${escapeHtml(r.title)}')">
    <div class="flex items-start justify-between mb-2">
      <div class="flex-1">
        <div class="text-sm font-semibold text-white mb-1">${escapeHtml(r.title)}</div>
        <div class="text-[11px] text-fg-400 leading-relaxed">${escapeHtml(r.description)}</div>
      </div>
      <span class="tag ${urgencyTag} ml-3">${escapeHtml(r.urgency)}</span>
    </div>
    ${provChain ? `<div class="prov-chain mt-2 mb-2">${provChain}</div>` : ''}
    <div class="flex items-center gap-3 text-[10px] text-fg-500 mt-2">
      <div class="conf-bar" style="width:120px;"><div class="conf-bar-track"><div class="conf-bar-fill" style="width:${r.confidence*100}%"></div></div><span class="text-brand-cyan font-bold">${formatConfidence(r.confidence)}</span></div>
      <span>·</span>
      <span>${r.evidence_count || 0} evidence</span>
      ${r.linked_laws && r.linked_laws.length ? `<span>·</span><span>Laws: ${r.linked_laws.join(', ')}</span>` : ''}
    </div>
    <div class="mt-2 text-[11px] text-fg-300">${escapeHtml(r.impact)}</div>
  </div>`;
}

// ═══════════════════════════════════════════════════════════════════════════
// INBOX
// ═══════════════════════════════════════════════════════════════════════════

async function loadInbox() {
  const owedEl = document.getElementById('inbox-owed');
  const driftEl = document.getElementById('inbox-drift');
  const dissentEl = document.getElementById('inbox-dissent');
  const summaryEl = document.getElementById('inbox-summary');

  loadingHTML(owedEl); loadingHTML(driftEl); loadingHTML(dissentEl);
  summaryEl.textContent = 'Loading…';

  try {
    const data = await api.getOEM('/inbox');
    const c = data.counts;
    summaryEl.textContent = `${c.owed} decisions you owe · ${c.drift} showing drift · ${c.dissent} unknown to leadership`;

    owedEl.innerHTML = c.owed === 0
      ? '<div class="empty-state">No urgent decisions owed.</div>'
      : data.decisions_owed.map(r => renderRecCard(r)).join('');

    driftEl.innerHTML = c.drift === 0
      ? '<div class="empty-state">No drift detected. All laws are stable.</div>'
      : data.drift.map(l => renderLawCard(l)).join('');

    dissentEl.innerHTML = c.dissent === 0
      ? '<div class="empty-state">No hidden disagreements. All validated laws are known to leadership.</div>'
      : data.dissent.map(l => renderLawCard(l)).join('');
  } catch (e) {
    errorHTML(owedEl, e.message, 'loadInbox()');
    errorHTML(driftEl, e.message, 'loadInbox()');
    errorHTML(dissentEl, e.message, 'loadInbox()');
    summaryEl.textContent = 'Failed to load inbox.';
    showError('Inbox load failed: ' + e.message);
  }
}

function renderLawCard(l) {
  const statusTag = l.status === 'validated' ? 'tag-cyan' : l.status === 'stressed' ? 'tag-amber' : l.status === 'invalidated' ? 'tag-rose' : l.status === 'unknown_to_leadership' ? 'tag-purple' : 'tag-gray';
  return `<div class="card mb-3 cursor-pointer" onclick="openDrilldown('law', '${escapeHtml(l.code)}')">
    <div class="flex items-start justify-between mb-2">
      <div class="flex-1">
        <div class="flex items-center gap-2 mb-1">
          <span class="mono text-[10px] text-brand-purple">${escapeHtml(l.code)}</span>
          <span class="tag ${statusTag}">${escapeHtml(l.status)}</span>
        </div>
        <div class="text-sm font-semibold text-white">${escapeHtml(l.statement)}</div>
        <div class="text-[11px] text-fg-400 mt-1">If: ${escapeHtml(l.condition)}</div>
        <div class="text-[11px] text-fg-300 mt-1">Then: ${escapeHtml(l.outcome)}</div>
      </div>
    </div>
    <div class="flex items-center gap-3 text-[10px] text-fg-500 mt-2">
      <div class="conf-bar" style="width:120px;"><div class="conf-bar-track"><div class="conf-bar-fill" style="width:${l.confidence*100}%"></div></div><span class="text-brand-cyan font-bold">${formatConfidence(l.confidence)}</span></div>
      <span>·</span>
      <span>${l.evidence_count} evidence</span>
      <span>·</span>
      <span>${l.validated_runtimes}/${l.validated_runtimes + l.failed_runtimes} runtimes</span>
      ${l.providers && l.providers.length ? `<span>·</span><span>${l.providers.join(', ')}</span>` : ''}
    </div>
    ${l.last_validated ? `<div class="mt-2 text-[10px] text-fg-500">Last verified: ${escapeHtml(l.last_validated)}</div>` : ''}
  </div>`;
}

// ═══════════════════════════════════════════════════════════════════════════
// SIMULATOR
// ═══════════════════════════════════════════════════════════════════════════

let simulatorAbort = null;

async function loadSimulator() {
  const el = document.getElementById('simulator-scenario');
  loadingHTML(el, 'Loading scenario…');
  try {
    const data = await api.getOEM('/simulator');
    const s = data.scenario;
    el.innerHTML = `
      <div class="space-y-3">
        <div>
          <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-1">Scenario</div>
          <div class="text-sm font-semibold text-white">${escapeHtml(s.title)}</div>
          <div class="text-[11px] text-fg-400 mt-1">${escapeHtml(s.description)}</div>
        </div>
        <div class="grid grid-cols-2 gap-4 pt-3 border-t border-white/[0.05]">
          <div>
            <div class="text-[10px] uppercase text-fg-500">Recommendation</div>
            <div class="text-sm text-brand-cyan mt-1">${escapeHtml(s.recommendation)}</div>
          </div>
          <div>
            <div class="text-[10px] uppercase text-fg-500">Confidence</div>
            <div class="conf-bar mt-1"><div class="conf-bar-track"><div class="conf-bar-fill" style="width:${s.confidence*100}%"></div></div><span class="text-brand-cyan font-bold">${formatConfidence(s.confidence)}</span></div>
          </div>
        </div>
        <div class="pt-3 border-t border-white/[0.05]">
          <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-1">Decision Question</div>
          <div class="text-[11px] text-fg-300">${escapeHtml(s.decision_question)}</div>
        </div>
        <div class="pt-3 border-t border-white/[0.05]">
          <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-1">Current Health</div>
          <div class="grid grid-cols-2 gap-2 text-[11px]">
            <div>P1 Cluster Risk: <span class="mono text-brand-amber">${formatConfidence(data.current_health.p1_cluster_risk)}</span></div>
            <div>Incident Rate: <span class="mono text-brand-amber">${data.current_health.incident_rate}</span></div>
            <div>Decision Velocity: <span class="mono text-brand-cyan">${data.current_health.decision_velocity_days.toFixed(1)}d</span></div>
            <div>Release Frequency: <span class="mono text-brand-cyan">${data.current_health.release_frequency.toFixed(1)}/wk</span></div>
          </div>
        </div>
      </div>
    `;
  } catch (e) {
    errorHTML(el, e.message, 'loadSimulator()');
  }
}

async function runSimulator() {
  const hires = parseInt(document.getElementById('sim-hires').value);
  const panel = document.getElementById('simulator-result-panel');
  const result = document.getElementById('simulator-result');
  panel.style.display = 'block';
  loadingHTML(result, 'Running simulation…');

  if (simulatorAbort) simulatorAbort.abort();
  simulatorAbort = new AbortController();

  try {
    const resp = await fetch(MAESTRO_API + '/api/oem/simulator', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({inputs: {hire_count: hires}}),
      signal: simulatorAbort.signal,
    });
    if (!resp.ok) throw new Error('Simulator returned ' + resp.status);
    const data = await resp.json();
    const p = data.predicted;
    result.innerHTML = `
      <div class="space-y-3">
        <div class="grid grid-cols-2 gap-4">
          <div>
            <div class="text-[10px] uppercase text-fg-500">Predicted P1 Risk</div>
            <div class="text-xl font-bold text-brand-amber mono">${formatConfidence(p.p1_cluster_risk)}</div>
            <div class="text-[10px] text-fg-500">Base: ${formatConfidence(data.base_health.p1_cluster_risk)}</div>
          </div>
          <div>
            <div class="text-[10px] uppercase text-fg-500">Confidence</div>
            <div class="conf-bar mt-1"><div class="conf-bar-track"><div class="conf-bar-fill" style="width:${data.confidence*100}%"></div></div><span class="text-brand-cyan font-bold">${formatConfidence(data.confidence)}</span></div>
          </div>
        </div>
        ${data.linked_laws && data.linked_laws.length ? `<div class="pt-3 border-t border-white/[0.05]"><div class="text-[10px] uppercase text-fg-500 mb-1">Linked Laws</div><div class="flex flex-wrap gap-1">${data.linked_laws.map(l => `<span class="prov-node">${escapeHtml(l)}</span>`).join('')}</div></div>` : ''}
      </div>
    `;
  } catch (e) {
    if (e.name === 'AbortError') return;
    errorHTML(result, e.message, 'runSimulator()');
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// HAYEK
// ═══════════════════════════════════════════════════════════════════════════

async function loadHayek() {
  const risksEl = document.getElementById('hayek-risks');
  const knowEl = document.getElementById('hayek-knowledge');
  loadingHTML(risksEl); loadingHTML(knowEl);
  try {
    const data = await api.getOEM('/knowledge');
    risksEl.innerHTML = data.concentration_risks.length === 0
      ? '<div class="empty-state">No concentration risks detected.</div>'
      : data.concentration_risks.map(r => `
        <div class="card mb-2 cursor-pointer hover:bg-white/[0.02]" onclick="openDrilldown('risk', '${escapeHtml(r.domain)}')">
          <div class="text-sm font-semibold text-white">${escapeHtml(r.domain)}</div>
          <div class="text-[11px] text-fg-400 mt-1">Influence concentration: <span class="mono text-brand-rose">${r.score.toFixed(2)}</span></div>
          <div class="conf-bar mt-2"><div class="conf-bar-track"><div class="conf-bar-fill" style="width:${Math.min(r.score*10,100)}%;background:#ff5577;"></div></div></div>
        </div>
      `).join('');
    knowEl.innerHTML = data.hidden_experts.length === 0
      ? '<div class="empty-state">No hidden experts detected.</div>'
      : data.hidden_experts.map(e => `
        <div class="card mb-2 cursor-pointer hover:bg-white/[0.02]" onclick="openDrilldown('expert', '${escapeHtml(e.entity)}')">
          <div class="text-sm font-semibold text-white">${escapeHtml(e.entity)}</div>
          <div class="text-[11px] text-fg-400 mt-1">Influence: <span class="mono text-brand-purple">${e.influence.toFixed(2)}</span> · ${e.domains ? e.domains.length : 0} domains</div>
          ${e.domains && e.domains.length ? `<div class="mt-2 flex flex-wrap gap-1">${e.domains.map(d => `<span class="tag tag-gray">${escapeHtml(d)}</span>`).join('')}</div>` : ''}
        </div>
      `).join('');
  } catch (e) {
    errorHTML(risksEl, e.message, 'loadHayek()');
    errorHTML(knowEl, e.message, 'loadHayek()');
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// KNOWLEDGE FLOW
// ═══════════════════════════════════════════════════════════════════════════

async function loadKnowledge() {
  const expertsEl = document.getElementById('flow-experts');
  const deathEl = document.getElementById('flow-death');
  const dupEl = document.getElementById('flow-duplicates');
  loadingHTML(expertsEl); loadingHTML(deathEl); loadingHTML(dupEl);
  try {
    const data = await api.getOEM('/knowledge');
    expertsEl.innerHTML = data.hidden_experts.length === 0
      ? '<div class="empty-state">No hidden experts detected.</div>'
      : data.hidden_experts.map(e => `
        <div class="card mb-2 cursor-pointer hover:bg-white/[0.02]" onclick="openDrilldown('expert', '${escapeHtml(e.entity)}')">
          <div class="text-sm font-semibold text-white">${escapeHtml(e.entity)}</div>
          <div class="text-[11px] text-fg-400 mt-1">Influence ${e.influence.toFixed(2)} · ${e.domains ? e.domains.length : 0} domains</div>
        </div>
      `).join('');
    deathEl.innerHTML = data.knowledge_death.length === 0
      ? '<div class="empty-state">No knowledge death detected.</div>'
      : data.knowledge_death.map(k => `
        <div class="card mb-2 cursor-pointer hover:bg-white/[0.02]" onclick="openDrilldown('pattern', '${escapeHtml(k.title || k.description || 'knowledge_death')}')">
          <div class="text-sm font-semibold text-white">${escapeHtml(k.title)}</div>
          <div class="text-[11px] text-fg-400 mt-1">${escapeHtml(k.description)}</div>
          <div class="text-[10px] text-fg-500 mt-1">Boundary: ${escapeHtml(k.boundary)} · Confidence ${formatConfidence(k.confidence)}</div>
        </div>
      `).join('');
    dupEl.innerHTML = data.duplicate_work.length === 0
      ? '<div class="empty-state">No duplicate work detected.</div>'
      : data.duplicate_work.map(d => `
        <div class="card mb-2 cursor-pointer hover:bg-white/[0.02]" onclick="openDrilldown('pattern', '${escapeHtml(d.title || d.description || 'duplicate_work')}')">
          <div class="text-sm font-semibold text-white">${escapeHtml(d.title)}</div>
          <div class="text-[11px] text-fg-400 mt-1">${escapeHtml(d.description)}</div>
          <div class="text-[10px] text-fg-500 mt-1">Domain: ${escapeHtml(d.domain)} · ${d.providers.join(', ')}</div>
        </div>
      `).join('');
  } catch (e) {
    errorHTML(expertsEl, e.message, 'loadKnowledge()');
    errorHTML(deathEl, e.message, 'loadKnowledge()');
    errorHTML(dupEl, e.message, 'loadKnowledge()');
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// MEMORY
// ═══════════════════════════════════════════════════════════════════════════

async function loadMemory() {
  const el = document.getElementById('memory-laws');
  loadingHTML(el);
  try {
    const data = await api.getOEM('/laws');
    el.innerHTML = data.laws.length === 0
      ? '<div class="empty-state">No laws inferred yet.</div>'
      : data.laws.map(l => renderLawCard(l)).join('');
  } catch (e) {
    errorHTML(el, e.message, 'loadMemory()');
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// ASK — backend-driven autocomplete (NO hardcoded suggestions)
// ═══════════════════════════════════════════════════════════════════════════

let autocompleteAbort = null;
let autocompleteSelectedIdx = -1;
let autocompleteSuggestions = [];  // Store full suggestion objects for rich rendering

async function onAskInput(value) {
  const dropdown = document.getElementById('exec-autocomplete');
  const v = value.trim();
  if (!v) {
    dropdown.classList.remove('active');
    autocompleteSuggestions = [];
    return;
  }

  if (autocompleteAbort) autocompleteAbort.abort();
  autocompleteAbort = new AbortController();

  // Include the current surface as context for context-aware ranking
  const surface = window._currentSurface || '';
  const contextParam = surface ? `&surface=${encodeURIComponent(surface)}` : '';

  try {
    const resp = await fetch(
      MAESTRO_API + '/api/oem/autocomplete?q=' + encodeURIComponent(v) + '&limit=8' + contextParam,
      { signal: autocompleteAbort.signal }
    );
    if (!resp.ok) throw new Error('Autocomplete failed: ' + resp.status);
    const data = await resp.json();
    const suggestions = data.suggestions || [];
    autocompleteSuggestions = suggestions;

    if (suggestions.length === 0) {
      dropdown.innerHTML = `<div class="exec-ac-header" role="status">No matches in OEM for "${escapeHtml(v)}"</div>`;
      dropdown.classList.add('active');
      autocompleteSelectedIdx = -1;
      return;
    }

    autocompleteSelectedIdx = -1;
    // Build rich dropdown with completion, reason, confidence, citations
    dropdown.setAttribute('role', 'listbox');
    dropdown.setAttribute('aria-label', 'Organizational autocomplete suggestions');
    dropdown.innerHTML = `<div class="exec-ac-header">Semantic suggestions · from live OEM · ranked by recency, authority, outcome, feedback</div>` +
      suggestions.map((s, i) => {
        const confPct = Math.round((s.confidence || 0) * 100);
        const rankPct = Math.round((s.rank_score || 0) * 100);
        const citations = (s.citations || []).slice(0, 3).map(c => {
          const short = String(c).substring(0, 20);
          return `<span class="source-cite" title="${escapeHtml(c)}">${escapeHtml(short)}</span>`;
        }).join(' ');
        const evidenceCount = (s.evidence || []).length;
        const similarCount = (s.similar_executions || []).length;
        const sourceIcon = {
          'law': 'L', 'recommendation': 'R', 'expert': '?', 'risk': '!',
          'evidence': 'E', 'lo:bottleneck': 'B', 'lo:hidden_expert': '?',
          'lo:departure_risk': 'X', 'lo:duplicate_work': 'D', 'lo:knowledge_death': 'K',
          'lo:approval_gate': 'G', 'lo:incident_pattern': 'I', 'lo:velocity_drop': 'V',
        }[s.source_type] || '*';
        return `<div class="exec-ac-item" data-idx="${i}" data-query="${escapeHtml(s.query)}" role="option" aria-selected="false" tabindex="-1" onmouseenter="autocompleteSelectedIdx=${i}; updateAutocompleteHighlight()" onclick="selectAutocomplete(${i})">
          <div class="exec-ac-completion">
            <span class="completed">${escapeHtml(s.completion)}</span>
          </div>
          <div class="text-[10px] text-fg-400 mt-1 leading-relaxed">${escapeHtml(s.reason)}</div>
          <div class="flex items-center gap-2 mt-1.5 text-[9px] text-fg-500 flex-wrap">
            <span class="mono text-brand-purple">[${escapeHtml(s.source_type)}]</span>
            <span class="text-brand-cyan">conf ${confPct}%</span>
            <span>·</span>
            <span>rank ${rankPct}%</span>
            <span>·</span>
            <span>${evidenceCount} evidence</span>
            ${similarCount ? `<span>·</span><span>${similarCount} similar</span>` : ''}
          </div>
          ${citations ? `<div class="mt-1 flex flex-wrap gap-1">${citations}</div>` : ''}
          ${s.expected_outcome ? `<div class="text-[9px] text-fg-600 mt-1 italic">→ ${escapeHtml(s.expected_outcome.substring(0, 100))}</div>` : ''}
        </div>`;
      }).join('');
    dropdown.classList.add('active');
  } catch (e) {
    if (e.name === 'AbortError') return;
    dropdown.innerHTML = `<div class="exec-ac-header" role="alert">Autocomplete error: ${escapeHtml(e.message)}</div>`;
    dropdown.classList.add('active');
  }
}

function updateAutocompleteHighlight() {
  document.querySelectorAll('.exec-ac-item').forEach((el, i) => {
    const selected = i === autocompleteSelectedIdx;
    el.classList.toggle('selected', selected);
    el.setAttribute('aria-selected', selected ? 'true' : 'false');
  });
  // Scroll the selected item into view
  if (autocompleteSelectedIdx >= 0) {
    const sel = document.querySelector(`.exec-ac-item[data-idx="${autocompleteSelectedIdx}"]`);
    if (sel) sel.scrollIntoView({ block: 'nearest' });
  }
}

function selectAutocomplete(idx) {
  const item = document.querySelector(`.exec-ac-item[data-idx="${idx}"]`);
  if (!item) return;
  const query = item.dataset.query;
  // Fill the input with the completion text (not the query) for a natural feel
  const suggestion = autocompleteSuggestions[idx];
  if (suggestion && suggestion.completion) {
    document.getElementById('ask-input').value = suggestion.completion;
  } else {
    document.getElementById('ask-input').value = query;
  }
  document.getElementById('exec-autocomplete').classList.remove('active');
  submitAsk(query);
}

document.addEventListener('keydown', (e) => {
  const dropdown = document.getElementById('exec-autocomplete');
  if (!dropdown || !dropdown.classList.contains('active')) return;
  const items = dropdown.querySelectorAll('.exec-ac-item');
  if (items.length === 0) return;

  if (e.key === 'ArrowDown') {
    e.preventDefault();
    autocompleteSelectedIdx = (autocompleteSelectedIdx + 1) % items.length;
    updateAutocompleteHighlight();
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    autocompleteSelectedIdx = (autocompleteSelectedIdx - 1 + items.length) % items.length;
    updateAutocompleteHighlight();
  } else if (e.key === 'Enter' && autocompleteSelectedIdx >= 0) {
    e.preventDefault();
    selectAutocomplete(autocompleteSelectedIdx);
  }
});

async function submitAsk(query) {
  const q = query.trim();
  if (!q) return;
  document.getElementById('ask-input').value = '';
  document.getElementById('exec-autocomplete').classList.remove('active');
  document.getElementById('ask-suggestions').style.display = 'none';
  const answerDiv = document.getElementById('ask-answer');
  answerDiv.style.display = 'block';
  document.getElementById('ask-answer-text').innerHTML = '<span class="spinner"></span> Asking the OEM…';
  document.getElementById('ask-citations').innerHTML = '';
  document.getElementById('ask-path').textContent = '';
  document.getElementById('ask-confidence').textContent = '';
  answerDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  try {
    const data = await api.getOEM('/ask?q=' + encodeURIComponent(q));
    document.getElementById('ask-answer-text').innerHTML = escapeHtml(data.answer).replace(/\n/g, '<br>');
    const sources = data.sources || [];
    document.getElementById('ask-citations').innerHTML = sources.length === 0
      ? '<span class="text-[11px] text-fg-500">No sources cited (insufficient evidence).</span>'
      : sources.map(s => `<span class="source-cite">${escapeHtml(s)}</span>`).join('');
    const path = data.evidence_path || [];
    document.getElementById('ask-path').textContent = path.length === 0
      ? 'No evidence path available.'
      : path.map(p => p.type + (p.code ? ':' + p.code : p.entity ? ':' + p.entity : p.gate ? ':' + p.gate : '')).join(' → ');
    document.getElementById('ask-confidence').textContent = `Confidence ${formatConfidence(data.confidence)} · ${sources.length} sources`;
  } catch (e) {
    document.getElementById('ask-answer-text').innerHTML = `<span class="text-brand-rose">Error: ${escapeHtml(e.message)}</span>`;
    showError('Ask failed: ' + e.message);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// PHYSICS (Laws) — with contradiction feedback (optimistic update)
// ═══════════════════════════════════════════════════════════════════════════

async function loadLaws(statusFilter) {
  const el = document.getElementById('physics-laws');
  loadingHTML(el, 'Loading laws…');
  try {
    const path = statusFilter ? '/laws?status=' + statusFilter : '/laws';
    const data = await api.getOEM(path);
    el.innerHTML = data.laws.length === 0
      ? '<div class="empty-state">No laws match this filter.</div>'
      : data.laws.map(l => renderLawCardDetailed(l)).join('');
  } catch (e) {
    errorHTML(el, e.message, 'loadLaws()');
  }
}

function renderLawCardDetailed(l) {
  const statusTag = l.status === 'validated' ? 'tag-cyan' : l.status === 'stressed' ? 'tag-amber' : l.status === 'invalidated' ? 'tag-rose' : l.status === 'unknown_to_leadership' ? 'tag-purple' : 'tag-gray';
  const chain = l.evidence_chain && l.evidence_chain.chain ? l.evidence_chain.chain : [];
  return `<div class="card mb-3 cursor-pointer" data-law-code="${escapeHtml(l.code)}" onclick="openDrilldown('law', '${escapeHtml(l.code)}')">
    <div class="flex items-start justify-between mb-2">
      <div class="flex-1">
        <div class="flex items-center gap-2 mb-1">
          <span class="mono text-[10px] text-brand-purple">${escapeHtml(l.code)}</span>
          <span class="tag ${statusTag}">${escapeHtml(l.status)}</span>
          ${l.drift_detected ? '<span class="tag tag-rose">DRIFT</span>' : ''}
        </div>
        <div class="text-sm font-semibold text-white">${escapeHtml(l.statement)}</div>
        <div class="text-[11px] text-fg-400 mt-1"><strong>Condition:</strong> ${escapeHtml(l.condition)}</div>
        <div class="text-[11px] text-fg-300 mt-1"><strong>Outcome:</strong> ${escapeHtml(l.outcome)}</div>
      </div>
    </div>
    <div class="flex items-center gap-3 text-[10px] text-fg-500 mt-3">
      <div class="conf-bar" style="width:140px;"><div class="conf-bar-track"><div class="conf-bar-fill" style="width:${l.confidence*100}%"></div></div><span class="text-brand-cyan font-bold conf-value">${formatConfidence(l.confidence)}</span></div>
      <span>·</span><span>${l.evidence_count} evidence</span>
      <span>·</span><span>${l.validated_runtimes}/${l.validated_runtimes + l.failed_runtimes} runtimes</span>
      ${l.counter_examples ? `<span>·</span><span>${l.counter_examples} counter-examples</span>` : ''}
    </div>
    <div class="grid grid-cols-2 gap-3 mt-3 pt-3 border-t border-white/[0.05]">
      <div>
        <div class="text-[10px] uppercase text-fg-500 mb-1">Providers</div>
        <div class="flex flex-wrap gap-1">${l.providers && l.providers.length ? l.providers.map(p => `<span class="tag tag-gray">${escapeHtml(p)}</span>`).join('') : '<span class="text-[10px] text-fg-600">none</span>'}</div>
      </div>
      <div>
        <div class="text-[10px] uppercase text-fg-500 mb-1">Last Verified</div>
        <div class="text-[11px] text-fg-300">${l.last_validated ? escapeHtml(l.last_validated) : 'never'}</div>
      </div>
    </div>
    ${chain.length > 0 ? `
      <div class="mt-3 pt-3 border-t border-white/[0.05]">
        <div class="text-[10px] uppercase text-fg-500 mb-2">Evidence Chain (${chain.length} nodes)</div>
        <div class="flex flex-wrap gap-1">${chain.slice(0, 12).map(n => `<span class="evidence-node ${n.type}">${escapeHtml(n.label)}</span>`).join('')}</div>
      </div>
    ` : ''}
    <div class="mt-3 pt-3 border-t border-white/[0.05] flex items-center gap-2" onclick="event.stopPropagation()">
      <div class="text-[10px] uppercase text-fg-500 mr-2">Feedback:</div>
      <button class="btn btn-ghost text-[10px]" onclick="event.stopPropagation(); contradictLaw('${escapeHtml(l.code)}', 'agree')">Agree</button>
      <button class="btn btn-ghost text-[10px]" onclick="event.stopPropagation(); contradictLaw('${escapeHtml(l.code)}', 'reject')">Reject</button>
      <button class="btn btn-ghost text-[10px]" onclick="event.stopPropagation(); contradictLaw('${escapeHtml(l.code)}', 'modify')">Modify</button>
      <button class="btn btn-ghost text-[10px]" onclick="event.stopPropagation(); contradictLaw('${escapeHtml(l.code)}', 'ignore')">Ignore</button>
    </div>
  </div>`;
}

async function contradictLaw(lawCode, action) {
  // Optimistic update: visually mark the law as "updating"
  const card = document.querySelector(`[data-law-code="${lawCode}"]`);
  if (card) {
    card.style.opacity = '0.6';
    const confEl = card.querySelector('.conf-value');
    if (confEl) confEl.innerHTML = '<span class="spinner"></span>';
  }

  try {
    const resp = await fetch(MAESTRO_API + '/api/oem/contradict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        target_type: 'law',
        target_id: lawCode,
        action: action,
        reasoning: `UI feedback: ${action}`,
      }),
    });
    if (!resp.ok) throw new Error('Contradict failed: ' + resp.status);
    const data = await resp.json();

    // Invalidate cached laws so next nav fetches fresh state
    SWR.invalidatePrefix('oem:/laws');
    SWR.invalidatePrefix('oem:/inbox');
    SWR.invalidatePrefix('oem:/dashboard');

    // Reload physics to show updated confidence
    if (window._currentSurface === 'physics') {
      loadLaws('');
    }
  } catch (e) {
    showError(`Feedback failed for ${lawCode}: ${e.message}`);
    if (card) {
      card.style.opacity = '1';
      const confEl = card.querySelector('.conf-value');
      if (confEl) confEl.textContent = '—';
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// DEBATE
// ═══════════════════════════════════════════════════════════════════════════

async function loadDebate() {
  const el = document.getElementById('debate-laws');
  loadingHTML(el);
  try {
    const data = await api.getOEM('/inbox');
    el.innerHTML = data.dissent.length === 0
      ? '<div class="empty-state">No laws hidden from leadership. All validated laws are known.</div>'
      : data.dissent.map(l => renderLawCardDetailed(l)).join('');
  } catch (e) {
    errorHTML(el, e.message, 'loadDebate()');
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// LIVE MEETING — real OEM-driven meeting intelligence (NO hardcoded script)
// ═══════════════════════════════════════════════════════════════════════════

let liveTimer = null;

// Clean up Live Meeting timers when navigating away
function teardownLive() {
  if (liveTimer) { clearTimeout(liveTimer); liveTimer = null; }
}

async function startLiveMeeting() {
  if (liveTimer) { clearTimeout(liveTimer); liveTimer = null; }
  document.getElementById('transcript-area').innerHTML = '';
  document.getElementById('live-obj-count').textContent = '0';
  document.getElementById('live-ai-count').textContent = '0';
  document.getElementById('live-law-count').textContent = '0';
  document.getElementById('live-objections').innerHTML = 'No objections yet.';
  document.getElementById('live-actions').innerHTML = 'No action items yet.';
  document.getElementById('live-laws').innerHTML = 'No laws triggered yet.';
  document.getElementById('live-start-btn').textContent = 'Replay Meeting';

  const transcriptArea = document.getElementById('transcript-area');
  transcriptArea.innerHTML = '<div class="text-[11px] text-fg-500 italic">Paste a transcript below and click "Analyze with OEM" — the OEM will detect objections, laws triggered, and action items in real time.</div>';

  const inputArea = document.getElementById('live-transcript-input');
  if (inputArea) inputArea.style.display = 'block';
}

async function analyzeTranscript() {
  const input = document.getElementById('live-transcript-textarea');
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;

  // Parse the textarea into a transcript (one line per turn, "Speaker: text")
  const lines = text.split('\n').filter(l => l.trim());
  const transcript = lines.map(line => {
    const idx = line.indexOf(':');
    if (idx > 0) {
      return { speaker: line.slice(0, idx).trim(), text: line.slice(idx + 1).trim() };
    }
    return { speaker: 'Unknown', text: line };
  });

  const transcriptArea = document.getElementById('transcript-area');

  // Build the entire transcript HTML in one string, then assign once.
  // This is O(n) instead of O(n²) — the old `innerHTML +=` re-parsed
  // the entire DOM on each line append.
  const transcriptHtml = transcript.map((line, i) => `<div class="flex gap-3 p-2 rounded-md bg-white/[0.02] mb-1">
      <span class="text-[10px] text-fg-500 mono w-12">${String(i+1).padStart(2,'0')}</span>
      <span class="text-xs font-semibold text-brand-cyan w-20">${escapeHtml(line.speaker)}</span>
      <span class="text-xs text-fg-200 flex-1">${escapeHtml(line.text)}</span>
    </div>`).join('');
  transcriptArea.innerHTML = transcriptHtml;

  // Analyze via OEM
  document.getElementById('live-objections').innerHTML = '<span class="spinner"></span> Analyzing…';
  document.getElementById('live-actions').innerHTML = '<span class="spinner"></span> Analyzing…';
  document.getElementById('live-laws').innerHTML = '<span class="spinner"></span> Analyzing…';

  try {
    const resp = await fetch(MAESTRO_API + '/api/oem/meetings/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ transcript }),
    });
    if (!resp.ok) throw new Error('Analyze failed: ' + resp.status);
    const data = await resp.json();

    document.getElementById('live-obj-count').textContent = data.summary.objection_count;
    document.getElementById('live-ai-count').textContent = data.summary.action_count;
    document.getElementById('live-law-count').textContent = data.summary.law_count;

    document.getElementById('live-objections').innerHTML = data.objections.length === 0
      ? '<div class="text-[11px] text-fg-500">No objections detected.</div>'
      : data.objections.map(o => `
        <div class="p-2 rounded-md bg-brand-rose/[0.06] border-l-2 border-brand-rose mb-1">
          <div class="text-brand-rose font-semibold text-[11px]">${escapeHtml(o.speaker)} dissents</div>
          <div class="text-[10px] text-fg-500">${escapeHtml(o.text)}</div>
          ${o.law_code ? `<div class="text-[10px] text-fg-600 mt-1">Linked: <span class="source-cite">${escapeHtml(o.law_code)}</span></div>` : ''}
        </div>
      `).join('');

    document.getElementById('live-actions').innerHTML = data.actions.length === 0
      ? '<div class="text-[11px] text-fg-500">No action items detected.</div>'
      : data.actions.map(a => `
        <div class="flex items-center gap-2 text-[11px] py-1">
          <div class="w-3 h-3 border border-white/20 rounded-sm"></div>
          <span class="text-fg-200 flex-1">${escapeHtml(a.text)}</span>
          <span class="text-fg-500">@${escapeHtml(a.owner)}</span>
        </div>
      `).join('');

    document.getElementById('live-laws').innerHTML = data.laws_triggered.length === 0
      ? '<div class="text-[11px] text-fg-500">No laws triggered.</div>'
      : data.laws_triggered.map(l => `
        <div class="flex items-center gap-2 text-[11px] py-1">
          <span class="source-cite">${escapeHtml(l.code)}</span>
          <span class="text-fg-400">${escapeHtml(l.statement.substring(0, 60))}…</span>
        </div>
      `).join('');
  } catch (e) {
    document.getElementById('live-objections').innerHTML = `<div class="text-[11px] text-brand-rose">Error: ${escapeHtml(e.message)}</div>`;
    document.getElementById('live-actions').innerHTML = '';
    document.getElementById('live-laws').innerHTML = '';
    showError('Meeting analysis failed: ' + e.message);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// ENG: SIGNALS
// ═══════════════════════════════════════════════════════════════════════════

async function loadEngSignals() {
  const el = document.getElementById('eng-signals-list');
  loadingHTML(el);
  try {
    const data = await api.getOEM('/state');
    el.innerHTML = `
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        ${data.providers.map(p => `
          <div class="card">
            <div class="flex items-center justify-between mb-2">
              <div class="text-sm font-semibold text-white">${escapeHtml(p.label)}</div>
              <span class="tag tag-cyan">connected</span>
            </div>
            <div class="text-[11px] text-fg-400">${escapeHtml(p.provider)}</div>
            <div class="text-[10px] text-fg-500 mt-2">${p.signal_count} signals processed</div>
            <div class="text-[10px] text-fg-500">Tracks: ${escapeHtml(p.artifact_label)}</div>
          </div>
        `).join('')}
      </div>
      <div class="mt-4 pt-4 border-t border-white/[0.05] grid grid-cols-2 md:grid-cols-4 gap-4">
        <div class="metric"><div class="metric-value">${data.summary.signals_processed}</div><div class="metric-label">Total Signals</div></div>
        <div class="metric"><div class="metric-value">${data.summary.learning_objects}</div><div class="metric-label">Learning Objects</div></div>
        <div class="metric"><div class="metric-value">${data.summary.patterns_detected}</div><div class="metric-label">Patterns</div></div>
        <div class="metric"><div class="metric-value">${data.summary.laws_inferred}</div><div class="metric-label">Laws</div></div>
      </div>
    `;
  } catch (e) {
    errorHTML(el, e.message, 'loadEngSignals()');
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// ENG: OEM BUILDER
// ═══════════════════════════════════════════════════════════════════════════

async function loadEngOEM() {
  const el = document.getElementById('eng-oem-pipeline');
  loadingHTML(el);
  try {
    const data = await api.getOEM('/state');
    const s = data.summary;
    el.innerHTML = `
      <div class="space-y-3">
        <div class="flex items-center gap-3 text-[11px]"><span class="w-2 h-2 rounded-full bg-brand-cyan"></span><span class="text-fg-200 flex-1">Ingesting signals from ${s.providers_connected.length} sources</span><span class="mono text-brand-cyan">${s.signals_processed}</span></div>
        <div class="flex items-center gap-3 text-[11px]"><span class="w-2 h-2 rounded-full bg-brand-amber"></span><span class="text-fg-200 flex-1">Learning objects inferred</span><span class="mono text-brand-amber">${s.learning_objects}</span></div>
        <div class="flex items-center gap-3 text-[11px]"><span class="w-2 h-2 rounded-full bg-brand-purple"></span><span class="text-fg-200 flex-1">Patterns detected</span><span class="mono text-brand-purple">${s.patterns_detected}</span></div>
        <div class="flex items-center gap-3 text-[11px]"><span class="w-2 h-2 rounded-full bg-brand-rose"></span><span class="text-fg-200 flex-1">Laws inferred</span><span class="mono text-brand-rose">${s.laws_inferred}</span></div>
        <div class="flex items-center gap-3 text-[11px]"><span class="w-2 h-2 rounded-full bg-brand-cyan"></span><span class="text-fg-200 flex-1">Validated laws</span><span class="mono text-brand-cyan">${s.validated_laws}</span></div>
        <div class="flex items-center gap-3 text-[11px]"><span class="w-2 h-2 rounded-full bg-brand-sky"></span><span class="text-fg-200 flex-1">Hidden experts</span><span class="mono text-brand-sky">${s.hidden_experts}</span></div>
        <div class="flex items-center gap-3 text-[11px]"><span class="w-2 h-2 rounded-full bg-brand-amber"></span><span class="text-fg-200 flex-1">Bottlenecks</span><span class="mono text-brand-amber">${s.bottlenecks}</span></div>
        <div class="flex items-center gap-3 text-[11px]"><span class="w-2 h-2 rounded-full bg-brand-rose"></span><span class="text-fg-200 flex-1">Departure risks</span><span class="mono text-brand-rose">${s.departure_risks}</span></div>
      </div>
      <div class="mt-4 pt-4 border-t border-white/[0.05] text-[10px] text-fg-500">Last updated: ${escapeHtml(data.last_updated || 'unknown')}</div>
    `;
  } catch (e) {
    errorHTML(el, e.message, 'loadEngOEM()');
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// ENG: AUDIT — structured receipts (NO JSON.stringify)
// ═══════════════════════════════════════════════════════════════════════════

async function loadEngAudit() {
  const el = document.getElementById('eng-audit-list');
  loadingHTML(el, 'Loading receipts…');
  try {
    const data = await api.getOEM('/receipts?limit=100');
    if (data.receipts.length === 0) {
      emptyHTML(el, 'No receipts recorded yet. Receipts appear as signals flow into the OEM.');
      return;
    }
    el.innerHTML = `
      <div class="text-[10px] text-fg-500 mb-3">${data.total} receipts · showing latest ${data.receipts.length}</div>
      <div class="space-y-1">
        ${data.receipts.map(r => `
          <div class="text-[11px] p-2 rounded bg-white/[0.02] border border-white/[0.04] grid grid-cols-12 gap-2 items-center hover:bg-white/[0.04] cursor-pointer" onclick="openDrilldown('signal', '${escapeHtml(r.receipt_id)}')">
            <span class="mono text-brand-purple col-span-2" title="${escapeHtml(r.receipt_id)}">${escapeHtml(r.receipt_id.substring(0, 8))}</span>
            <span class="text-fg-500 col-span-2">${formatTimestamp(r.timestamp)}</span>
            <span class="tag tag-gray col-span-1">${escapeHtml(r.provider)}</span>
            <span class="text-fg-300 col-span-2">${escapeHtml(r.signal_type)}</span>
            <span class="text-fg-200 col-span-2 truncate" title="${escapeHtml(r.actor)}">${escapeHtml(r.actor)}</span>
            <span class="text-fg-400 col-span-2 truncate" title="${escapeHtml(r.artifact)}">${escapeHtml(r.artifact)}</span>
            <span class="text-fg-500 col-span-1">${r.law_code ? `<span class="source-cite">${escapeHtml(r.law_code)}</span>` : ''}</span>
          </div>
        `).join('')}
      </div>
    `;
  } catch (e) {
    errorHTML(el, e.message, 'loadEngAudit()');
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// ENG: SETTINGS
// ═══════════════════════════════════════════════════════════════════════════

async function loadEngSettings() {
  document.getElementById('settings-api-url').value = MAESTRO_API || '(same origin)';
  const statusEl = document.getElementById('settings-oem-status');
  try {
    const data = await api.getOEM('/state');
    statusEl.innerHTML = `<span class="text-brand-cyan">●</span> Connected — ${data.summary.signals_processed} signals, ${data.summary.laws_inferred} laws`;
  } catch (e) {
    statusEl.innerHTML = `<span class="text-brand-rose">●</span> Unreachable: ${escapeHtml(e.message)}`;
  }
  await loadProviderStatus();
  await loadImportJobs();
}

// ─── Signal provider connection UI ─────────────────────────────────────────

const PROVIDER_META = {
  github:     { name: 'GitHub',     icon: 'G', description: 'Code execution, PR reviews, and repository management' },
  jira:       { name: 'Jira',       icon: 'J', description: 'Issue tracking, sprint velocity, approval bottlenecks' },
  slack:      { name: 'Slack',      icon: 'S', description: 'Messages, threads, hidden experts, departure signals' },
  confluence: { name: 'Confluence', icon: 'C', description: 'Knowledge pages, version history, expertise graph' },
  gmail:      { name: 'Gmail',      icon: 'M', description: 'Email patterns, decision trails, cross-team signals' },
};

async function loadProviderStatus() {
  const listEl = document.getElementById('signal-providers-list');
  if (!listEl) return;
  try {
    const data = await api.getOAuthStatus();
    listEl.innerHTML = data.providers.map(p => {
      const meta = PROVIDER_META[p.provider] || { name: p.provider, icon: 'O', description: '' };
      const statusBadge = p.connected
        ? `<span class="tag tag-cyan">Connected</span>`
        : p.configured
          ? `<span class="tag tag-gray">Not connected</span>`
          : `<span class="tag tag-amber" title="Set MAESTRO_OAUTH_${p.provider.toUpperCase()}_CLIENT_ID and _SECRET env vars">Not configured</span>`;
      const actionButton = p.connected
        ? `<button class="btn btn-ghost text-[11px]" onclick="disconnectProvider('${p.provider}')">Disconnect</button>`
        : `<button class="btn btn-primary text-[11px]" ${p.configured ? '' : 'disabled'} onclick="connectProvider('${p.provider}')">Connect</button>`;
      return `
        <div class="flex items-center justify-between p-3 rounded-lg bg-ink-800/60 border border-ink-700">
          <div class="flex items-center gap-3">
            <div class="text-xl">${meta.icon}</div>
            <div>
              <div class="text-sm font-semibold text-white">${meta.name}</div>
              <div class="text-[10px] text-fg-500">${escapeHtml(meta.description)}</div>
            </div>
          </div>
          <div class="flex items-center gap-3">
            ${statusBadge}
            ${actionButton}
          </div>
        </div>`;
    }).join('');
  } catch (e) {
    listEl.innerHTML = `<div class="text-xs text-brand-rose">Failed to load provider status: ${escapeHtml(e.message)}</div>`;
  }
}

async function connectProvider(provider) {
  try {
    const resp = await fetch(`${MAESTRO_API}/api/oauth/${provider}/start`);
    if (!resp.ok) {
      const err = await resp.json();
      showError(`Failed to start OAuth: ${err.detail || 'Unknown error'}`);
      return;
    }
    const { auth_url } = await resp.json();
    window.location.href = auth_url;
  } catch (e) {
    showError(`Connection failed: ${e.message}`);
  }
}

async function disconnectProvider(provider) {
  if (!confirm(`Disconnect ${provider}? Already-ingested history is preserved.`)) return;
  try {
    await fetch(`${MAESTRO_API}/api/oauth/${provider}/disconnect`, { method: 'POST' });
    SWR.invalidate('oauth:status');
    await loadProviderStatus();
  } catch (e) {
    showError(`Disconnect failed: ${e.message}`);
  }
}

async function loadImportJobs() {
  const listEl = document.getElementById('import-jobs-list');
  if (!listEl) return;
  try {
    const data = await api.getImports();
    if (!data.jobs || data.jobs.length === 0) {
      listEl.innerHTML = '<div class="text-xs text-fg-500">No import jobs yet. Connect a provider to start.</div>';
      return;
    }
    listEl.innerHTML = data.jobs.slice(0, 10).map(job => {
      const statusColor = job.status === 'completed' ? 'cyan' : job.status === 'failed' ? 'rose' : job.status === 'running' ? 'violet' : 'gray';
      return `
        <div class="flex items-center justify-between p-2 rounded-lg bg-ink-800/60 border border-ink-700 text-xs">
          <div>
            <div class="font-semibold text-white">${job.providers.join(', ')}</div>
            <div class="text-fg-500">${job.total_signals || 0} signals · ${job.started_at ? new Date(job.started_at).toLocaleString() : ''}</div>
          </div>
          <div class="flex items-center gap-2">
            <span class="tag tag-${statusColor}">${job.status}</span>
            ${job.status === 'running' ? `<button class="btn btn-ghost text-[10px]" onclick="cancelImport('${job.job_id}')">Cancel</button>` : ''}
          </div>
        </div>`;
    }).join('');
  } catch (e) {
    listEl.innerHTML = `<div class="text-xs text-brand-rose">Failed to load jobs: ${escapeHtml(e.message)}</div>`;
  }
}

async function cancelImport(jobId) {
  if (!jobId) {
    const banner = document.getElementById('import-banner');
    jobId = banner.dataset.jobId;
  }
  if (!jobId) return;
  try {
    await fetch(`${MAESTRO_API}/api/imports/${jobId}/cancel`, { method: 'POST' });
  } catch (e) {
    console.warn('Cancel failed:', e);
  }
}

// ─── Live import progress banner (WebSocket) ────────────────────────────────

let importWs = null;
let importPollInterval = null;

async function checkForRunningImports() {
  try {
    const data = await api.getImports();
    const running = (data.jobs || []).find(j => j.status === 'running');
    if (running) {
      subscribeToImport(running.job_id);
    }
  } catch (e) {
    // Silently fail — banner is non-critical
  }
}

function subscribeToImport(jobId) {
  if (importWs) {
    try { importWs.close(); } catch (e) {}
  }
  const wsBase = MAESTRO_API.replace(/^http/, 'ws') || (window.location.origin.replace(/^http/, 'ws'));
  importWs = new WebSocket(`${wsBase}/api/imports/${jobId}/stream`);
  importWs.onmessage = (e) => {
    try {
      const snap = JSON.parse(e.data);
      if (snap.type === 'ping') return;
      updateImportBanner(jobId, snap);
    } catch (err) {}
  };
  importWs.onerror = (e) => {
    console.warn('Import WS error:', e);
    // Don't silently fall back to polling — surface the error
    showError('Import monitoring connection lost. Will retry.');
  };
  importWs.onclose = () => {
    if (importPollInterval) clearInterval(importPollInterval);
    let pollStartedAt = Date.now(), pollErrors = 0;
    importPollInterval = setInterval(async () => {
      // Max poll duration: 1 hour
      if (Date.now() - pollStartedAt > 60 * 60 * 1000) {
        clearInterval(importPollInterval);
        importPollInterval = null;
        showError('Import monitoring timed out after 1 hour.');
        hideImportBanner();
        return;
      }
      try {
        const resp = await fetch(`${MAESTRO_API}/api/imports/${jobId}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const job = await resp.json();
        pollErrors = 0;
        if (job.status === 'running' || (job.providers_progress && Object.values(job.providers_progress).some(p => p.status === 'running'))) {
          updateImportBanner(jobId, job);
        } else {
          hideImportBanner();
          clearInterval(importPollInterval);
          importPollInterval = null;
        }
      } catch (e) {
        if (++pollErrors > 5) {
          clearInterval(importPollInterval);
          importPollInterval = null;
          hideImportBanner();
          showError('Import monitoring lost after 5 consecutive errors.');
        }
      }
    }, 5000);
  };
}

function updateImportBanner(jobId, snap) {
  const banner = document.getElementById('import-banner');
  banner.classList.remove('hidden');
  banner.dataset.jobId = jobId;

  const providers = snap.providers_progress || {};
  const providerNames = Object.keys(providers);
  const totalEvents = snap.total_events || 0;
  const runningProvider = providerNames.find(p => providers[p].status === 'running');
  const totalEstimated = runningProvider ? providers[runningProvider].total_estimated : 0;
  const etaSeconds = runningProvider ? providers[runningProvider].eta_seconds : 0;

  const titleEl = document.getElementById('import-banner-title');
  const subtitleEl = document.getElementById('import-banner-subtitle');
  if (runningProvider) {
    const meta = PROVIDER_META[runningProvider] || { name: runningProvider };
    titleEl.textContent = `Importing ${meta.name}…`;
    const etaMin = Math.ceil(etaSeconds / 60);
    subtitleEl.textContent = `${totalEvents.toLocaleString()} events processed · ETA ${etaMin}m`;
  } else if (snap.status === 'completed') {
    titleEl.textContent = `Import complete`;
    subtitleEl.textContent = `${totalEvents.toLocaleString()} events imported`;
    setTimeout(hideImportBanner, 5000);
  } else if (snap.status === 'failed') {
    titleEl.textContent = `Import failed`;
    subtitleEl.textContent = snap.error || 'Unknown error';
    setTimeout(hideImportBanner, 10000);
  }

  const oem = snap.oem || {};
  document.getElementById('import-banner-patterns').textContent = oem.patterns_detected || 0;
  document.getElementById('import-banner-laws').textContent = oem.laws_inferred || 0;
  document.getElementById('import-banner-recs').textContent = oem.recommendations || 0;

  const progressPct = totalEstimated > 0 ? Math.min(100, (totalEvents / totalEstimated) * 100) : 0;
  document.getElementById('import-banner-progress').style.width = `${progressPct}%`;

  // Only refresh dashboard on completion (not on every progress tick).
  // The old code re-fetched /ceo-briefing + /dashboard every 2s during
  // imports — hundreds of unnecessary backend inference calls.
  if (snap.phase === 'completed' && window._currentSurface === 'home') {
    SWR.invalidatePrefix('oem:');  // Invalidate cache; next render fetches fresh
    loadDashboard();
  }
}

function hideImportBanner() {
  document.getElementById('import-banner').classList.add('hidden');
  // Full teardown: close WS and clear polling interval
  if (importWs) { try { importWs.close(); } catch (e) {} importWs = null; }
  if (importPollInterval) { clearInterval(importPollInterval); importPollInterval = null; }
}

// Page lifecycle: clean up all resources on page hide
window.addEventListener('pagehide', () => {
  teardownLive();
  if (importWs) { try { importWs.close(); } catch (e) {} importWs = null; }
  if (importPollInterval) { clearInterval(importPollInterval); importPollInterval = null; }
});

// Visibility change: pause SWR revalidation when tab is backgrounded
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    // Tab backgrounded — SWR will stop revalidating naturally
    // (no active timers to pause since SWR is event-driven)
  } else {
    // Tab foregrounded — revalidate stale cache
    SWR.revalidateAll();
  }
});

// ═══════════════════════════════════════════════════════════════════════════
// DRILL-DOWN MODAL — every card/metric/insight is clickable
// Answers: Why? Where? Evidence? Timeline? People? Prediction? Simulation? Recommendation?
// ═══════════════════════════════════════════════════════════════════════════

let drilldownData = null;
let drilldownActiveTab = 'why';

async function openDrilldown(entityType, entityId) {
  const modal = document.getElementById('drilldown-modal');
  const body = document.getElementById('drilldown-body');
  const title = document.getElementById('drilldown-title');
  const typeLabel = document.getElementById('drilldown-type');

  modal.classList.remove('hidden');
  body.innerHTML = '<div class="loading-state"><span class="spinner"></span> Loading drill-down…</div>';
  title.textContent = entityId;
  typeLabel.textContent = entityType.charAt(0).toUpperCase() + entityType.slice(1);

  try {
    const resp = await fetch(`${MAESTRO_API}/api/oem/entity/${entityType}/${encodeURIComponent(entityId)}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    drilldownData = await resp.json();
    drilldownActiveTab = 'why';
    updateDrilldownTabs();
    renderDrilldownTab('why');
  } catch (e) {
    body.innerHTML = `<div class="error-state">Failed to load: ${escapeHtml(e.message)}</div>`;
  }
}

function closeDrilldown() {
  document.getElementById('drilldown-modal').classList.add('hidden');
  drilldownData = null;
}

function switchDrilldownTab(tab) {
  drilldownActiveTab = tab;
  updateDrilldownTabs();
  renderDrilldownTab(tab);
}

function updateDrilldownTabs() {
  document.querySelectorAll('.drilldown-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === drilldownActiveTab);
  });
}

function renderDrilldownTab(tab) {
  const body = document.getElementById('drilldown-body');
  if (!drilldownData) return;

  if (tab === 'why') {
    body.innerHTML = `
      <div class="space-y-4">
        <div class="text-sm text-fg-200 leading-relaxed">${escapeHtml(drilldownData.why || 'No explanation available.')}</div>
        ${drilldownData.where ? `
          <div class="mt-4 pt-4 border-t border-white/[0.05]">
            <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-2">Context</div>
            <pre class="text-[11px] text-fg-400 bg-white/[0.02] p-3 rounded-lg overflow-x-auto">${escapeHtml(JSON.stringify(drilldownData.where, null, 2))}</pre>
          </div>
        ` : ''}
      </div>
    `;
  } else if (tab === 'where') {
    body.innerHTML = `
      <div class="space-y-3">
        <div class="text-sm text-fg-200">${drilldownData.where ? 'This entity appears in:' : 'No location data.'}</div>
        ${drilldownData.where ? `<pre class="text-[11px] text-fg-400 bg-white/[0.02] p-3 rounded-lg overflow-x-auto">${escapeHtml(JSON.stringify(drilldownData.where, null, 2))}</pre>` : ''}
      </div>
    `;
  } else if (tab === 'evidence') {
    const ev = drilldownData.evidence || [];
    body.innerHTML = ev.length === 0
      ? '<div class="empty-state">No evidence available.</div>'
      : `<div class="text-[10px] text-fg-500 mb-3">${ev.length} evidence item(s)</div>
         <div class="space-y-2">${ev.map(e => `
           <div class="drilldown-evidence-item" onclick="${e.signal_id ? `openDrilldown('signal', '${escapeHtml(e.signal_id)}')` : ''}">
             <div class="flex items-center justify-between">
               <span class="text-xs font-semibold text-fg-200">${escapeHtml(e.type)}${e.signal_type ? ': ' + escapeHtml(e.signal_type) : ''}</span>
               ${e.provider ? `<span class="tag tag-gray">${escapeHtml(e.provider)}</span>` : ''}
             </div>
             ${e.actor ? `<div class="text-[10px] text-fg-500 mt-1">Actor: ${escapeHtml(e.actor)}</div>` : ''}
             ${e.artifact ? `<div class="text-[10px] text-fg-500">Artifact: ${escapeHtml(e.artifact)}</div>` : ''}
             ${e.timestamp ? `<div class="text-[10px] text-fg-600 mt-1">${formatTimestamp(e.timestamp)}</div>` : ''}
           </div>
         `).join('')}</div>`;
  } else if (tab === 'timeline') {
    const tl = drilldownData.timeline || [];
    body.innerHTML = tl.length === 0
      ? '<div class="empty-state">No timeline data.</div>'
      : `<div class="space-y-0">${tl.map(t => `
         <div class="drilldown-timeline-item">
           <div class="text-xs font-semibold text-fg-200">${escapeHtml(t.event)}</div>
           <div class="text-[10px] text-fg-500">${escapeHtml(t.detail || '')}</div>
           ${t.timestamp ? `<div class="text-[10px] text-fg-600 mt-1">${formatTimestamp(t.timestamp)}</div>` : ''}
         </div>
       `).join('')}</div>`;
  } else if (tab === 'people') {
    const ppl = drilldownData.people || [];
    body.innerHTML = ppl.length === 0
      ? '<div class="empty-state">No people data.</div>'
      : `<div class="space-y-1">${ppl.map(p => `
         <div class="drilldown-person" onclick="openDrilldown('expert', '${escapeHtml(p.name)}')">
           <div class="w-8 h-8 rounded-full bg-brand-violet/20 flex items-center justify-center text-xs font-bold text-brand-violet">${escapeHtml(p.name.charAt(0).toUpperCase())}</div>
           <div class="flex-1">
             <div class="text-xs font-semibold text-fg-200">${escapeHtml(p.name)}</div>
             <div class="text-[10px] text-fg-500">${escapeHtml(p.role || '')}</div>
           </div>
           ${p.influence ? `<span class="text-[10px] text-brand-purple mono">inf ${p.influence.toFixed(2)}</span>` : ''}
         </div>
       `).join('')}</div>`;
  } else if (tab === 'prediction') {
    const pred = drilldownData.prediction;
    body.innerHTML = !pred
      ? '<div class="empty-state">No prediction available.</div>'
      : `<div class="space-y-3">
         ${pred.condition ? `<div><div class="text-[10px] uppercase text-fg-500 mb-1">Condition</div><div class="text-sm text-fg-200">${escapeHtml(pred.condition)}</div></div>` : ''}
         ${pred.outcome ? `<div><div class="text-[10px] uppercase text-fg-500 mb-1">Predicted Outcome</div><div class="text-sm text-brand-cyan">${escapeHtml(pred.outcome)}</div></div>` : ''}
         ${pred.detail ? `<div><div class="text-[10px] uppercase text-fg-500 mb-1">Detail</div><div class="text-sm text-fg-300">${escapeHtml(pred.detail)}</div></div>` : ''}
         ${pred.impact ? `<div><div class="text-[10px] uppercase text-fg-500 mb-1">Impact</div><div class="text-sm text-fg-300">${escapeHtml(pred.impact)}</div></div>` : ''}
         ${pred.confidence != null ? `<div><div class="text-[10px] uppercase text-fg-500 mb-1">Confidence</div><div class="conf-bar" style="width:200px;"><div class="conf-bar-track"><div class="conf-bar-fill" style="width:${pred.confidence*100}%"></div></div><span class="text-brand-cyan font-bold">${formatConfidence(pred.confidence)}</span></div></div>` : ''}
         ${pred.risk ? `<div><span class="tag tag-rose">${escapeHtml(pred.risk)}</span></div>` : ''}
       </div>`;
  } else if (tab === 'simulation') {
    const sim = drilldownData.simulation;
    body.innerHTML = !sim || !sim.available
      ? '<div class="empty-state">No simulation available for this entity.</div>'
      : `<div class="space-y-4">
         <div class="text-sm text-fg-200">${escapeHtml(sim.prompt || 'Run a what-if simulation.')}</div>
         ${sim.linked_laws && sim.linked_laws.length ? `<div class="text-[10px] text-fg-500">Linked laws: ${sim.linked_laws.map(l => `<span class="source-cite">${escapeHtml(l)}</span>`).join(' ')}</div>` : ''}
         <div>
           <div class="text-[10px] uppercase text-fg-500 mb-2">Quick Simulation</div>
           <div class="flex items-center gap-3">
             <label class="text-[11px] text-fg-400">Hire count:</label>
             <input type="range" min="0" max="10" value="2" id="drilldown-sim-hires" class="flex-1" oninput="document.getElementById('drilldown-sim-val').textContent=this.value">
             <span class="text-xs font-bold text-brand-cyan mono" id="drilldown-sim-val">2</span>
             <button class="btn btn-primary text-[11px]" onclick="runDrilldownSimulation()">Run</button>
           </div>
           <div id="drilldown-sim-result" class="mt-4"></div>
         </div>
       </div>`;
  } else if (tab === 'recommendation') {
    const rec = drilldownData.recommendation;
    body.innerHTML = !rec || !rec.available
      ? '<div class="empty-state">No recommendations linked to this entity.</div>'
      : `<div class="space-y-2">${rec.items.map(r => `
         <div class="card mb-2 cursor-pointer" onclick="navTo('simulator')">
           <div class="text-sm font-semibold text-white">${escapeHtml(r.title)}</div>
           <div class="text-[11px] text-fg-400 mt-1">${escapeHtml(r.recommendation || '')}</div>
           <div class="flex items-center gap-2 mt-2 text-[10px] text-fg-500">
             ${r.urgency ? `<span class="tag ${r.urgency === 'urgent' ? 'tag-rose' : 'tag-amber'}">${escapeHtml(r.urgency)}</span>` : ''}
             ${r.confidence != null ? `<span>conf ${formatConfidence(r.confidence)}</span>` : ''}
           </div>
         </div>
       `).join('')}</div>`;
  }
}

async function runDrilldownSimulation() {
  const hires = parseInt(document.getElementById('drilldown-sim-hires').value);
  const resultEl = document.getElementById('drilldown-sim-result');
  resultEl.innerHTML = '<div class="loading-state"><span class="spinner"></span> Running…</div>';
  try {
    const lawCode = drilldownData?.simulation?.linked_laws?.[0];
    const resp = await fetch(`${MAESTRO_API}/api/oem/simulate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ law_code: lawCode, inputs: { hire_count: hires } }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    resultEl.innerHTML = `
      <div class="grid grid-cols-2 gap-3 text-[11px]">
        <div class="p-3 rounded-lg bg-white/[0.02]">
          <div class="text-[10px] uppercase text-fg-500">P1 Risk</div>
          <div class="text-lg font-bold text-brand-amber mono">${formatConfidence(data.predicted.p1_cluster_risk)}</div>
          <div class="text-[10px] text-fg-600">Base: ${formatConfidence(data.base_health.p1_cluster_risk)}</div>
        </div>
        <div class="p-3 rounded-lg bg-white/[0.02]">
          <div class="text-[10px] uppercase text-fg-500">Decision Velocity</div>
          <div class="text-lg font-bold text-brand-cyan mono">${data.predicted.decision_velocity_days}d</div>
          <div class="text-[10px] text-fg-600">Base: ${data.base_health.decision_velocity_days}d</div>
        </div>
      </div>
      <div class="mt-3 text-[10px] text-fg-500">Confidence: ${formatConfidence(data.confidence)}</div>
    `;
  } catch (e) {
    resultEl.innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`;
  }
}

// ESC closes the drill-down modal
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    const modal = document.getElementById('drilldown-modal');
    if (modal && !modal.classList.contains('hidden')) {
      closeDrilldown();
    }
  }
});

// ═══════════════════════════════════════════════════════════════════════════
// DIGITAL TWIN — "What happens if...?"
// ═══════════════════════════════════════════════════════════════════════════

function renderECCTwin(twinState) {
  const el = document.getElementById('ecc-twin');
  const summary = twinState.summary || {};
  const people = twinState.people || [];
  const domains = twinState.domains || [];

  el.innerHTML = `
    <div class="space-y-4">
      <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div class="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <div class="text-[10px] uppercase text-fg-500">People</div>
          <div class="text-lg font-bold text-white mono">${summary.people || 0}</div>
        </div>
        <div class="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <div class="text-[10px] uppercase text-fg-500">Domains</div>
          <div class="text-lg font-bold text-white mono">${summary.domains || 0}</div>
        </div>
        <div class="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <div class="text-[10px] uppercase text-fg-500">Bottlenecks</div>
          <div class="text-lg font-bold text-brand-rose mono">${summary.bottlenecks || 0}</div>
        </div>
        <div class="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <div class="text-[10px] uppercase text-fg-500">At-Risk Domains</div>
          <div class="text-lg font-bold text-brand-amber mono">${summary.at_risk_domains || 0}</div>
        </div>
        <div class="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <div class="text-[10px] uppercase text-fg-500">Avg Workload</div>
          <div class="text-lg font-bold text-brand-cyan mono">${(summary.avg_workload || 0).toFixed(1)}</div>
        </div>
      </div>

      <div class="pt-3 border-t border-white/[0.05]">
        <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-2">Run a What-If Scenario</div>
        <div class="space-y-3">
          <!-- Person leaves -->
          <div class="flex items-center gap-2">
            <select id="twin-person" class="ask-input flex-1 text-[11px]">
              ${people.map(p => `<option value="${escapeHtml(p.email)}">${escapeHtml(p.email)} (wl: ${p.workload}, inf: ${p.influence})</option>`).join('')}
            </select>
            <button class="btn btn-ghost text-[10px]" onclick="runTwinScenario({'type':'person_leaves','person':document.getElementById('twin-person').value})">What if they leave?</button>
          </div>
          <!-- Cut meetings -->
          <div class="flex items-center gap-2">
            <label class="text-[11px] text-fg-400">Cut meetings by:</label>
            <input type="range" min="10" max="80" value="30" id="twin-meeting-cut" class="flex-1" oninput="document.getElementById('twin-meeting-val').textContent=this.value+'%'">
            <span class="text-xs font-bold text-brand-cyan mono" id="twin-meeting-val">30%</span>
            <button class="btn btn-ghost text-[10px]" onclick="runTwinScenario({'type':'cut_meetings','reduction_pct':parseInt(document.getElementById('twin-meeting-cut').value)})">Simulate</button>
          </div>
          <!-- Add hires -->
          <div class="flex items-center gap-2">
            <select id="twin-hire-domain" class="ask-input flex-1 text-[11px]">
              ${domains.map(d => `<option value="${escapeHtml(d.name)}">${escapeHtml(d.name)} (${d.people.length} people)</option>`).join('')}
            </select>
            <input type="number" min="1" max="20" value="3" id="twin-hire-count" class="w-16 ask-input text-[11px] text-center">
            <button class="btn btn-ghost text-[10px]" onclick="runTwinScenario({'type':'add_hires','domain':document.getElementById('twin-hire-domain').value,'count':parseInt(document.getElementById('twin-hire-count').value)})">Add hires</button>
          </div>
        </div>
      </div>

      <div id="twin-result" class="mt-3"></div>
    </div>
  `;
}

async function runTwinScenario(scenario) {
  const resultEl = document.getElementById('twin-result');
  if (!resultEl) return;
  resultEl.innerHTML = '<div class="loading-state"><span class="spinner"></span> Running simulation...</div>';
  try {
    const resp = await fetch(MAESTRO_API + '/api/oem/twin/simulate', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(scenario),
    });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const report = await resp.json();
    renderTwinReport(report);
  } catch(e) {
    resultEl.innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`;
  }
}

function renderTwinReport(report) {
  const resultEl = document.getElementById('twin-result');
  const riskColor = report.risk_level === 'critical' ? 'rose' : report.risk_level === 'high' ? 'amber' : report.risk_level === 'medium' ? 'amber' : 'green';
  resultEl.innerHTML = `
    <div class="space-y-4">
      <div class="p-3 rounded-lg bg-brand-${riskColor}/[0.06] border border-brand-${riskColor}/15">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-sm font-semibold text-white">${escapeHtml(report.description)}</div>
            <div class="text-[10px] text-fg-500 mt-1">Scenario: ${escapeHtml(report.scenario_type)} · ${escapeHtml(report.timestamp)}</div>
          </div>
          <div class="text-right">
            <span class="tag tag-${riskColor}">${escapeHtml(report.risk_level)}</span>
            <div class="text-[10px] text-fg-600 mt-1">risk score: ${report.risk_score.toFixed(2)}</div>
          </div>
        </div>
      </div>

      ${report.overloaded_people.length > 0 ? `
        <div>
          <div class="text-[10px] uppercase text-fg-500 font-semibold mb-2">Overloaded People (${report.overloaded_people.length})</div>
          ${report.overloaded_people.map(p => `
            <div class="flex items-center gap-2 p-2 rounded-lg bg-brand-rose/[0.04] border border-brand-rose/10 mb-1 cursor-pointer" onclick="openDrilldown('expert', '${escapeHtml(p.person)}')">
              <span class="text-xs font-semibold text-fg-200">${escapeHtml(p.person)}</span>
              <span class="text-[10px] text-brand-rose">+${p.workload_increase} workload</span>
              <span class="text-[10px] text-fg-600">${p.domains.join(', ')}</span>
            </div>`).join('')}
        </div>` : ''}

      ${report.knowledge_loss.length > 0 ? `
        <div>
          <div class="text-[10px] uppercase text-fg-500 font-semibold mb-2">Knowledge Loss (${report.knowledge_loss.length})</div>
          ${report.knowledge_loss.map(kl => `
            <div class="p-2 rounded-lg bg-brand-amber/[0.04] border border-brand-amber/10 mb-1 cursor-pointer" onclick="openDrilldown('risk', '${escapeHtml(kl.domain)}')">
              <span class="text-xs font-semibold text-fg-200">${escapeHtml(kl.domain)}</span>
              <span class="text-[10px] text-brand-amber ml-2">${kl.people_before} → ${kl.people_after} people</span>
              <div class="text-[10px] text-fg-600">${escapeHtml(kl.description)}</div>
            </div>`).join('')}
        </div>` : ''}

      ${report.new_bottlenecks.length > 0 ? `
        <div>
          <div class="text-[10px] uppercase text-fg-500 font-semibold mb-2">New Bottlenecks (${report.new_bottlenecks.length})</div>
          ${report.new_bottlenecks.map(nb => `
            <div class="p-2 rounded-lg bg-brand-purple/[0.04] border border-brand-purple/10 mb-1">
              <span class="text-xs font-semibold text-fg-200">${escapeHtml(nb.person || nb.description)}</span>
              <div class="text-[10px] text-fg-600">${escapeHtml(nb.description)}</div>
            </div>`).join('')}
        </div>` : ''}

      ${report.law_violations.length > 0 ? `
        <div>
          <div class="text-[10px] uppercase text-fg-500 font-semibold mb-2">Law Violations (${report.law_violations.length})</div>
          ${report.law_violations.map(lv => `
            <div class="p-2 rounded-lg bg-brand-rose/[0.04] border border-brand-rose/10 mb-1 cursor-pointer" onclick="openDrilldown('law', '${escapeHtml(lv.law_code)}')">
              <span class="text-xs font-semibold text-fg-200">${escapeHtml(lv.law_code)}</span>
              <span class="text-[10px] text-fg-600 ml-2">${escapeHtml(lv.description)}</span>
            </div>`).join('')}
        </div>` : ''}

      ${Object.keys(report.velocity_change).length > 0 ? `
        <div class="grid grid-cols-2 gap-3">
          <div class="p-3 rounded-lg bg-white/[0.02]">
            <div class="text-[10px] uppercase text-fg-500">Velocity</div>
            <div class="text-sm font-bold ${report.velocity_change.velocity_direction === 'improved' ? 'text-brand-cyan' : 'text-brand-rose'} mono">${report.velocity_change.velocity_before}d → ${report.velocity_change.velocity_after}d</div>
          </div>
          <div class="p-3 rounded-lg bg-white/[0.02]">
            <div class="text-[10px] uppercase text-fg-500">P1 Risk</div>
            <div class="text-sm font-bold mono">${report.velocity_change.p1_risk_before} → ${report.velocity_change.p1_risk_after}</div>
          </div>
        </div>` : ''}

      <div>
        <div class="text-[10px] uppercase text-fg-500 font-semibold mb-2">Recommendations</div>
        ${report.recommendations.map(r => `
          <div class="p-2 rounded-lg bg-white/[0.02] border border-white/[0.04] mb-1">
            <div class="flex items-center gap-2">
              <span class="tag ${r.priority === 'urgent' ? 'tag-rose' : r.priority === 'high' ? 'tag-amber' : 'tag-gray'}">${escapeHtml(r.priority)}</span>
              <span class="text-xs font-semibold text-fg-200">${escapeHtml(r.action)}</span>
            </div>
            <div class="text-[10px] text-fg-600 mt-1">${escapeHtml(r.reason)}</div>
          </div>`).join('')}
      </div>
    </div>
  `;
}

window.addEventListener('load', () => {
  setTimeout(checkForRunningImports, 1000);
  checkDemoMode();
});

// ─── Demo-mode banner ─────────────────────────────────────────────────────
// Check if the OEM is running with demo seed data and show a prominent
// banner if so. This makes demo mode unmistakable — not just a flag in
// settings that a careful reader could find.
async function checkDemoMode() {
  try {
    const data = await api.getOEM('/dashboard');
    // The dashboard response includes the connected providers. If the demo
    // seed is active, the OEM has signals from the demo providers (github,
    // jira, slack, confluence, gmail, customer) but no real OAuth connections.
    // We check /api/oauth/status to see if ANY provider is really connected.
    const oauthResp = await fetch((MAESTRO_API || '') + '/api/oauth/status');
    const oauthData = await oauthResp.json();
    const providers = oauthData.providers || [];
    const anyConnected = providers.some(p => p.connected);
    // If no real OAuth connection exists AND the OEM has signals, the data
    // must be from the demo seed.
    const hasSignals = data.metrics && data.metrics.signals_processed > 0;
    if (hasSignals && !anyConnected) {
      const banner = document.getElementById('demo-banner');
      if (banner) banner.style.display = 'block';
    }
  } catch (e) {
    // If the check fails, don't show the banner — fail open (the app still works).
  }
}
// ═══════════════════════════════════════════════════════════════════════════
// CUSTOMER JUDGMENT ENGINE — another OEM surface
// ═══════════════════════════════════════════════════════════════════════════

async function loadCustomerJudgment() {
  loadCustomerMorning();
  loadCustomerList();
  loadCustomerTwinScenarios();
}

async function loadCustomerMorning() {
  const el = document.getElementById('customer-morning');
  const summaryEl = document.getElementById('customer-morning-summary');
  try {
    const data = await api.getOEM('/customer/morning');
    summaryEl.textContent = data.summary || '';
    if (!data.relationships || data.relationships.length === 0) {
      el.innerHTML = '<div class="empty-state">No customer relationships in the OEM yet.</div>';
      return;
    }
    el.innerHTML = data.relationships.map(r => `
      <div class="border border-white/[0.05] rounded-lg p-3 mb-2 cursor-pointer hover:bg-white/[0.02]" onclick="selectCustomer('${escapeHtml(r.customer)}')">
        <div class="flex items-center justify-between mb-1">
          <div class="font-semibold text-white">${escapeHtml(r.customer)}</div>
          <div class="flex gap-2">
            <span class="tag ${r.urgency === 'urgent' ? 'tag-red' : r.urgency === 'normal' ? 'tag-yellow' : 'tag-green'}">${escapeHtml(r.urgency)}</span>
            <span class="tag tag-cyan">${formatConfidence(r.confidence)}</span>
          </div>
        </div>
        <div class="text-xs text-fg-400 mb-1">${escapeHtml(r.why)}</div>
        <div class="text-xs text-fg-300"><strong>Recommendation:</strong> ${escapeHtml(r.recommendation)}</div>
        <div class="text-[10px] text-fg-500 mt-1">Expected value: ${escapeHtml(r.expected_value)} · Risk: ${formatConfidence(r.escalation_risk)} · Champion: ${escapeHtml(r.champion_health)}</div>
        <div class="flex gap-1.5 mt-2">
          <button class="tag tag-gray cursor-pointer text-[10px] hover:bg-white/[0.05]" onclick="event.stopPropagation(); selectCustomer('${escapeHtml(r.customer)}')" aria-label="Open full brief for ${escapeHtml(r.customer)}">Open brief</button>
          <button class="tag tag-gray cursor-pointer text-[10px] hover:bg-white/[0.05]" onclick="event.stopPropagation(); quickCustomerAsk('${escapeHtml(r.customer)}')" aria-label="Ask about ${escapeHtml(r.customer)}">Ask</button>
          <button class="tag tag-gray cursor-pointer text-[10px] hover:bg-white/[0.05]" onclick="event.stopPropagation(); runDefaultTwinScenario('${escapeHtml(r.customer)}', '${escapeHtml(r.champion_health)}')" aria-label="Simulate ${escapeHtml(r.customer)}">Simulate</button>
        </div>
      </div>
    `).join('');
  } catch (e) {
    el.innerHTML = `<div class="empty-state">Failed to load: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadCustomerList() {
  const el = document.getElementById('customer-list');
  try {
    const data = await api.getOEM('/customer/list');
    if (!data.customers || data.customers.length === 0) {
      el.innerHTML = '<div class="empty-state">No customers found. Connect the Customer provider or enable the demo seed.</div>';
      return;
    }
    el.innerHTML = `
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
        ${data.customers.map(c => `
          <div class="border border-white/[0.05] rounded-lg p-3 cursor-pointer hover:bg-white/[0.02]" onclick="selectCustomer('${escapeHtml(c.name)}')">
            <div class="flex items-center justify-between mb-2">
              <div class="font-semibold text-white">${escapeHtml(c.name)}</div>
              <span class="tag ${c.state === 'negative' ? 'tag-red' : c.state === 'positive' ? 'tag-green' : 'tag-gray'}">${escapeHtml(c.state)}</span>
            </div>
            <div class="text-lg font-bold text-cyan-400">$${(c.arr_at_stake / 1000000).toFixed(1)}M</div>
            <div class="text-[10px] text-fg-500">ARR at stake</div>
            <div class="text-[10px] text-fg-400 mt-2">Risk: ${formatConfidence(c.escalation_risk)} · Champion: ${escapeHtml(c.champion_health)}</div>
          </div>
        `).join('')}
      </div>
    `;
  } catch (e) {
    el.innerHTML = `<div class="empty-state">Failed to load: ${escapeHtml(e.message)}</div>`;
  }
}

async function selectCustomer(name) {
  // Show the panels
  document.getElementById('customer-brief-panel').style.display = '';
  document.getElementById('customer-committee-panel').style.display = '';
  document.getElementById('customer-drift-panel').style.display = '';
  document.getElementById('customer-brief-title').textContent = `Executive Brief — ${name}`;

  loadCustomerBrief(name);
  loadCustomerCommittee(name);
  loadCustomerDrift(name);
}

async function loadCustomerBrief(name) {
  const body = document.getElementById('customer-brief-body');
  const confEl = document.getElementById('customer-brief-confidence');
  body.innerHTML = '<div class="loading-state"><span class="spinner"></span>Loading brief…</div>';
  try {
    const b = await api.getOEM(`/customer/brief/${encodeURIComponent(name)}`);
    confEl.textContent = `confidence ${formatConfidence(b.confidence)}`;
    body.innerHTML = `
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div><div class="text-[10px] text-fg-500 uppercase">State</div><div class="text-sm font-semibold ${b.relationship_state === 'healthy' || b.relationship_state === 'renewed' ? 'text-green-400' : b.relationship_state === 'at_risk' ? 'text-yellow-400' : b.relationship_state === 'churned' ? 'text-red-400' : 'text-fg-300'}">${escapeHtml(b.relationship_state)}</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">ARR at stake</div><div class="text-sm font-semibold text-cyan-400">$${(b.arr_at_stake / 1000000).toFixed(2)}M</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">Urgency</div><div class="text-sm font-semibold">${escapeHtml(b.urgency)}</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">Business impact</div><div class="text-xs text-fg-300">${escapeHtml(b.business_impact)}</div></div>
      </div>
      <div class="border-t border-white/[0.05] pt-3">
        <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-2">Recommended outcome</div>
        <div class="text-sm text-fg-200">${escapeHtml(b.recommended_outcome)}</div>
      </div>
      <div class="border-t border-white/[0.05] pt-3">
        <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-2">Outstanding risks</div>
        <div class="text-xs text-fg-300 space-y-1">
          <div>Broken commitments: <strong>${b.outstanding_risks.broken_commitments}</strong></div>
          <div>Objections: <strong>${b.outstanding_risks.objections}</strong> (${escapeHtml((b.outstanding_risks.objection_types || []).join(', ') || 'none')})</div>
          <div>Drift signals: <strong>${b.outstanding_risks.drift_signals}</strong></div>
        </div>
      </div>
      ${b.things_not_to_say && b.things_not_to_say.length > 0 ? `
      <div class="border-t border-white/[0.05] pt-3">
        <div class="text-[10px] uppercase tracking-wider text-red-400 font-semibold mb-2">Things not to say</div>
        <ul class="text-xs text-fg-300 space-y-1">
          ${b.things_not_to_say.map(t => `<li>• ${escapeHtml(t)}</li>`).join('')}
        </ul>
      </div>` : ''}
      <div class="border-t border-white/[0.05] pt-3">
        <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-2">Evidence</div>
        <div class="text-xs text-fg-400">${escapeHtml(b.confidence_explanation)}</div>
        <div class="text-xs text-fg-400 mt-1">${b.evidence.learning_objects} LOs · ${b.evidence.laws.length} laws · ${b.evidence.signals} signals</div>
      </div>
    `;
  } catch (e) {
    body.innerHTML = `<div class="empty-state">Failed to load brief: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadCustomerCommittee(name) {
  const body = document.getElementById('customer-committee-body');
  const meta = document.getElementById('customer-committee-meta');
  body.innerHTML = '<div class="loading-state"><span class="spinner"></span>Loading committee…</div>';
  try {
    const c = await api.getOEM(`/customer/committee/${encodeURIComponent(name)}`);
    meta.textContent = `${c.total_members} members · ${c.decision_radius} decision radius`;
    body.innerHTML = `
      <div class="grid grid-cols-1 md:grid-cols-2 gap-2 mb-3">
        ${c.members.map(m => `
          <div class="border border-white/[0.05] rounded p-2">
            <div class="flex items-center justify-between">
              <div class="text-xs font-semibold text-white">${escapeHtml(m.contact)}</div>
              <span class="tag ${m.support_level === 'strong' ? 'tag-green' : m.support_level === 'moderate' ? 'tag-yellow' : m.support_level === 'weak' ? 'tag-gray' : 'tag-red'}">${escapeHtml(m.support_level)}</span>
            </div>
            <div class="text-[10px] text-fg-400 mt-1">Roles: ${escapeHtml(m.roles.join(', ') || 'unknown')}</div>
            <div class="text-[10px] text-fg-500">Influence: ${m.influence} · Interactions: ${m.interactions} · conf ${formatConfidence(m.confidence)}</div>
          </div>
        `).join('')}
      </div>
      <div class="text-[10px] text-fg-500">Roles filled: ${escapeHtml(c.roles_filled.join(', '))}</div>
      ${c.roles_missing.length > 0 ? `<div class="text-[10px] text-amber-400">Roles missing: ${escapeHtml(c.roles_missing.join(', '))}</div>` : ''}
    `;
  } catch (e) {
    body.innerHTML = `<div class="empty-state">Failed to load: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadCustomerDrift(name) {
  const body = document.getElementById('customer-drift-body');
  body.innerHTML = '<div class="loading-state"><span class="spinner"></span>Loading drift…</div>';
  try {
    const d = await api.getOEM(`/customer/drift/${encodeURIComponent(name)}`);
    body.innerHTML = `
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div><div class="text-[10px] text-fg-500 uppercase">Momentum</div><div class="text-sm font-semibold ${d.momentum === 'positive' ? 'text-green-400' : d.momentum === 'negative' ? 'text-red-400' : 'text-fg-300'}">${escapeHtml(d.momentum)}</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">Trust</div><div class="text-sm font-semibold">${formatConfidence(d.trust)}</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">Champion health</div><div class="text-sm font-semibold ${d.champion_health === 'active' ? 'text-green-400' : d.champion_health === 'quiet' ? 'text-red-400' : 'text-fg-300'}">${escapeHtml(d.champion_health)}</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">Escalation risk</div><div class="text-sm font-semibold ${d.escalation_risk > 0.5 ? 'text-red-400' : d.escalation_risk > 0.2 ? 'text-yellow-400' : 'text-green-400'}">${formatConfidence(d.escalation_risk)}</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">Decision readiness</div><div class="text-sm">${escapeHtml(d.decision_readiness)}</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">Exec engagement</div><div class="text-sm">${escapeHtml(d.executive_engagement)}</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">Response latency</div><div class="text-sm">${d.response_latency_days !== null ? d.response_latency_days + 'd' : '—'}</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">Buying velocity</div><div class="text-sm">${d.buying_velocity}/mo</div></div>
      </div>
    `;
  } catch (e) {
    body.innerHTML = `<div class="empty-state">Failed to load: ${escapeHtml(e.message)}</div>`;
  }
}

async function submitCustomerAsk(q) {
  const answerEl = document.getElementById('customer-ask-answer');
  const textEl = document.getElementById('customer-ask-text');
  const evEl = document.getElementById('customer-ask-evidence');
  const unEl = document.getElementById('customer-ask-unknowns');
  const confEl = document.getElementById('customer-ask-confidence');
  answerEl.style.display = '';
  textEl.textContent = 'Thinking…';
  evEl.textContent = '';
  unEl.textContent = '';
  confEl.textContent = '';
  try {
    const data = await api.getOEM(`/customer/ask?q=${encodeURIComponent(q)}`);
    textEl.textContent = data.answer;
    evEl.innerHTML = `<strong>Evidence:</strong> ${JSON.stringify(data.evidence)}`;
    if (data.unknowns && data.unknowns.length > 0) {
      unEl.innerHTML = `<strong>Unknowns:</strong> ${data.unknowns.map(u => escapeHtml(u)).join('; ')}`;
    }
    if (data.counter_evidence && data.counter_evidence.length > 0) {
      unEl.innerHTML = (unEl.innerHTML ? unEl.innerHTML + '<br>' : '') +
        `<strong>Counter-evidence:</strong> ${data.counter_evidence.map(c => escapeHtml(c.detail || JSON.stringify(c))).join('; ')}`;
    }
    confEl.textContent = `Confidence ${formatConfidence(data.confidence)} — ${escapeHtml(data.confidence_explanation || '')}`;
  } catch (e) {
    textEl.textContent = `Error: ${e.message}`;
  }
}

async function loadCustomerTwinScenarios() {
  const el = document.getElementById('customer-twin-scenarios');
  try {
    const data = await api.getOEM('/customer/twin/scenarios');
    el.innerHTML = data.scenarios.map(s => `
      <button class="tag tag-gray cursor-pointer text-left p-2 hover:bg-white/[0.05]" onclick="loadCustomerTwinForm('${s.type}', ${JSON.stringify(s.example).replace(/"/g, '&quot;')})">
        <div class="text-xs font-semibold">${escapeHtml(s.title)}</div>
        <div class="text-[10px] text-fg-500">${escapeHtml(s.type)}</div>
      </button>
    `).join('');
  } catch (e) {
    el.innerHTML = `<div class="empty-state">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadCustomerTwinForm(type, example) {
  const formEl = document.getElementById('customer-twin-form');
  const resultEl = document.getElementById('customer-twin-result');
  formEl.style.display = '';
  resultEl.style.display = 'none';
  // Use the example as the payload — in production this would render a form
  // based on the scenario's params, but for the demo the examples are complete.
  formEl.innerHTML = `
    <div class="text-xs text-fg-300">Scenario: <strong>${escapeHtml(type)}</strong></div>
    <div class="text-[10px] text-fg-500">Payload: <code>${escapeHtml(JSON.stringify(example, null, 2))}</code></div>
    <button class="btn btn-primary text-xs" onclick="runCustomerTwin(${JSON.stringify(example).replace(/"/g, '&quot;')})">Run simulation</button>
  `;
}

async function runCustomerTwin(payload) {
  const resultEl = document.getElementById('customer-twin-result');
  resultEl.style.display = '';
  resultEl.innerHTML = '<div class="loading-state"><span class="spinner"></span>Simulating…</div>';
  try {
    const data = await api.postOEM('/customer/twin/simulate', payload);
    const riskColor = data.risk_level === 'critical' ? 'text-red-400' : data.risk_level === 'high' ? 'text-orange-400' : data.risk_level === 'medium' ? 'text-yellow-400' : 'text-green-400';
    resultEl.innerHTML = `
      <div class="border border-white/[0.05] rounded-lg p-3 space-y-3">
        <div class="flex items-center justify-between">
          <div class="text-sm font-semibold text-white">Expected outcome: <span class="text-cyan-400">${escapeHtml(data.expected_outcome)}</span></div>
          <div class="flex gap-2">
            <span class="tag ${riskColor}">${escapeHtml(data.risk_level)} risk</span>
            <span class="tag tag-cyan">${formatConfidence(data.confidence)}</span>
          </div>
        </div>
        <div class="text-xs text-fg-300">${escapeHtml(data.description)}</div>
        <div class="border-t border-white/[0.05] pt-2">
          <div class="text-[10px] uppercase text-fg-500 font-semibold mb-1">Business impact</div>
          <div class="text-xs text-fg-300">${Object.entries(data.business_impact).map(([k,v]) => `${escapeHtml(k)}: ${escapeHtml(String(v))}`).join(' · ')}</div>
        </div>
        <div class="border-t border-white/[0.05] pt-2">
          <div class="text-[10px] uppercase text-fg-500 font-semibold mb-1">Supporting evidence</div>
          <ul class="text-xs text-fg-300 space-y-1">${data.supporting_evidence.map(e => `<li>• ${escapeHtml(e.detail)}</li>`).join('')}</ul>
        </div>
        <div class="border-t border-white/[0.05] pt-2">
          <div class="text-[10px] uppercase text-amber-400 font-semibold mb-1">Counter-evidence</div>
          <ul class="text-xs text-fg-400 space-y-1">${data.counter_evidence.map(e => `<li>• ${escapeHtml(e.detail)}</li>`).join('')}</ul>
        </div>
        <div class="border-t border-white/[0.05] pt-2">
          <div class="text-[10px] uppercase text-fg-500 font-semibold mb-1">Alternative actions</div>
          <ul class="text-xs text-fg-300 space-y-1">${data.alternative_actions.map(a => `<li>• <strong>${escapeHtml(a.action)}</strong> — ${escapeHtml(a.rationale)}</li>`).join('')}</ul>
        </div>
      </div>
    `;
  } catch (e) {
    resultEl.innerHTML = `<div class="empty-state">Simulation failed: ${escapeHtml(e.message)}</div>`;
  }
}

// ─── One-click actions from the morning brief ─────────────────────────────

async function quickCustomerAsk(customer) {
  // Navigate to customer surface, populate the ask input, and submit
  navTo('customer');
  await new Promise(r => setTimeout(r, 300)); // Let the surface load
  const input = document.getElementById('customer-ask-input');
  if (input) {
    const q = `What should I know about ${customer} right now?`;
    input.value = q;
    submitCustomerAsk(q);
  }
}

async function runDefaultTwinScenario(customer, championHealth) {
  // Pick a scenario based on the customer's state
  navTo('customer');
  await new Promise(r => setTimeout(r, 300));
  // If champion is quiet, simulate champion_leaves (highest urgency)
  // Otherwise simulate pricing (most common question)
  const scenario = championHealth === 'quiet'
    ? { type: 'champion_leaves', customer }
    : { type: 'pricing', customer, increase_pct: 10 };
  runCustomerTwin(scenario);
}
