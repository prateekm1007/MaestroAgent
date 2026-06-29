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
  ask: 'Ask the Organization', physics: 'Organizational Physics', debate: 'Debate',
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
    const surfaces = ['home','inbox','simulator','hayek','flow','memory','ask','physics','debate'];
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
    case 'eng-signals': loadEngSignals(); break;
    case 'eng-oem': loadEngOEM(); break;
    case 'eng-audit': loadEngAudit(); break;
    case 'eng-settings': loadEngSettings(); break;
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// HOME — CEO Briefing: answers 5 questions a Fortune 100 CEO needs
// ═══════════════════════════════════════════════════════════════════════════

async function loadDashboard() {
  const overnightEl = document.getElementById('home-overnight');
  const oneThingEl = document.getElementById('home-one-thing');
  const moneyEl = document.getElementById('home-money');
  const knowledgeEl = document.getElementById('home-knowledge');
  const decisionsEl = document.getElementById('home-ceo-decisions');
  const stateEl = document.getElementById('home-oem-state');
  const providersBadge = document.getElementById('oem-providers-badge');

  // Render panels independently — don't wait for both endpoints.
  // /dashboard is fast (~200ms); /ceo-briefing runs OEM inference (~1-8s).
  // By splitting, the OEM State panel renders in ~200ms instead of waiting
  // for the full briefing.
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

  // CEO briefing panels — render as soon as the briefing is ready
  try {
    const briefing = await api.getOEM('/ceo-briefing');

    // Update timestamp
    const tsEl = document.getElementById('home-briefing-timestamp');
    if (tsEl && briefing.generated_at) {
      tsEl.textContent = `Last updated: ${formatTimestamp(briefing.generated_at)}`;
    }

    // ─── Q1: What changed overnight? ───
    const ov = briefing.overnight;
    document.getElementById('home-overnight-count').textContent = ov.summary;
    if (!ov.changes || ov.changes.length === 0) {
      emptyHTML(overnightEl, 'Nothing new. The org is stable. The OEM will surface new patterns as signals flow.');
    } else {
      overnightEl.innerHTML = `
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
              <div class="w-7 h-7 rounded-md bg-brand-${sevColor}/15 flex items-center justify-center flex-shrink-0">
                <span class="text-brand-${sevColor} text-sm font-bold">${c.type === 'hidden_expert' ? '?' : c.type === 'bottleneck' ? '!' : c.type === 'departure_risk' ? 'x' : 'v'}</span>
              </div>
              <div class="flex-1">
                <div class="text-[12px] font-semibold text-fg-100">${escapeHtml(c.title)}</div>
                <div class="text-[10px] text-fg-500 mt-0.5">${escapeHtml(c.detail)}</div>
              </div>
              <span class="tag tag-${sevColor}">${escapeHtml(c.severity)}</span>
            </div>`;
          }).join('')}
        </div>
      `;
    }

    // ─── Q2: If I only do one thing today? ───
    const ot = briefing.one_thing;
    const urgencyColor = ot.urgency === 'urgent' ? 'rose' : ot.urgency === 'normal' ? 'amber' : 'gray';
    oneThingEl.innerHTML = `
      <div class="space-y-3">
        <div>
          <div class="text-base font-bold text-white">${escapeHtml(ot.title)}</div>
          <div class="text-[11px] text-fg-400 mt-1 leading-relaxed">${escapeHtml(ot.why)}</div>
        </div>
        <div class="pt-3 border-t border-white/[0.05]">
          <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-1">Recommended action</div>
          <div class="text-sm text-brand-violet font-medium">${escapeHtml(ot.recommendation)}</div>
        </div>
        <div class="flex items-center gap-3 pt-2">
          <span class="tag tag-${urgencyColor}">${escapeHtml(ot.urgency)}</span>
          <div class="conf-bar" style="width:120px;"><div class="conf-bar-track"><div class="conf-bar-fill" style="width:${ot.confidence*100}%"></div></div><span class="text-brand-cyan font-bold">${formatConfidence(ot.confidence)}</span></div>
          <span class="text-[10px] text-fg-500">confidence</span>
        </div>
        <div class="text-[11px] text-fg-300 pt-2">${escapeHtml(ot.impact)}</div>
        ${ot.rec_id ? `<button class="btn btn-primary text-[11px] mt-2" onclick="openDrilldown('recommendation', '${escapeHtml(ot.title)}')">Investigate this →</button>` : ''}
      </div>
    `;

    // ─── Q3: Where is money being lost? ───
    const money = briefing.money;
    document.getElementById('home-money-count').textContent = money.summary;
    if (!money.losses || money.losses.length === 0) {
      emptyHTML(moneyEl, 'No obvious money drains detected. The OEM will surface bottlenecks, duplicate work, and incident costs as signals flow.');
    } else {
      moneyEl.innerHTML = `
        <div class="mb-3 p-3 rounded-lg bg-brand-rose/[0.04] border border-brand-rose/10">
          <div class="text-sm font-semibold text-white">${escapeHtml(money.headline)}</div>
          <div class="text-[11px] text-brand-rose mt-1">${escapeHtml(money.headline_cost)}</div>
        </div>
        <div class="space-y-2">
          ${money.losses.map(l => {
            const sevColor = l.severity === 'high' ? 'rose' : 'amber';
            const drillType = l.type === 'bottleneck' ? 'pattern' : l.type === 'duplicate_work' ? 'pattern' : l.type === 'incident' ? 'pattern' : 'pattern';
            return `<div class="flex items-start gap-3 p-3 rounded-lg bg-brand-${sevColor}/[0.04] border border-brand-${sevColor}/10 cursor-pointer hover:bg-brand-${sevColor}/[0.08] transition-colors" onclick="openDrilldown('${drillType}', '${escapeHtml(l.title)}')">
              <div class="w-7 h-7 rounded-md bg-brand-${sevColor}/15 flex items-center justify-center flex-shrink-0">
                <span class="text-brand-${sevColor} text-sm font-bold">$</span>
              </div>
              <div class="flex-1">
                <div class="text-[12px] font-semibold text-fg-100">${escapeHtml(l.title)}</div>
                <div class="text-[10px] text-fg-500 mt-0.5">${escapeHtml(l.estimated_cost)}</div>
                <div class="text-[10px] text-fg-600 mt-0.5">${escapeHtml(l.detail)}</div>
              </div>
              <span class="tag tag-${sevColor}">${escapeHtml(l.severity)}</span>
            </div>`;
          }).join('')}
        </div>
      `;
    }

    // ─── Q4: Where is knowledge trapped? ───
    const knowledge = briefing.knowledge;
    document.getElementById('home-knowledge-count').textContent = knowledge.summary;
    if (!knowledge.traps || knowledge.traps.length === 0) {
      emptyHTML(knowledgeEl, 'No knowledge traps detected. The OEM will surface hidden experts, concentration risks, and knowledge death as signals flow.');
    } else {
      knowledgeEl.innerHTML = `
        <div class="mb-3 p-3 rounded-lg bg-brand-amber/[0.04] border border-brand-amber/10">
          <div class="text-sm font-semibold text-white">${escapeHtml(knowledge.headline)}</div>
          <div class="text-[11px] text-brand-amber mt-1">${escapeHtml(knowledge.headline_risk)}</div>
        </div>
        <div class="space-y-2">
          ${knowledge.traps.map(t => {
            const drillType = t.type === 'hidden_expert' ? 'expert' : t.type === 'concentration_risk' ? 'risk' : 'pattern';
            const drillId = t.entity || t.domain || t.title || 'unknown';
            const icon = t.type === 'hidden_expert' ? '?' : t.type === 'concentration_risk' ? '!' : 'x';
            return `<div class="flex items-start gap-3 p-3 rounded-lg bg-brand-amber/[0.04] border border-brand-amber/10 cursor-pointer hover:bg-brand-amber/[0.08] transition-colors" onclick="openDrilldown('${drillType}', '${escapeHtml(drillId)}')">
              <div class="w-7 h-7 rounded-md bg-brand-amber/15 flex items-center justify-center flex-shrink-0">
                <span class="text-brand-amber text-sm font-bold">${icon}</span>
              </div>
              <div class="flex-1">
                <div class="text-[12px] font-semibold text-fg-100">${escapeHtml(t.entity || t.domain || t.title || 'Unknown')}</div>
                <div class="text-[10px] text-fg-500 mt-0.5">${escapeHtml(t.risk)}</div>
                ${t.influence ? `<div class="text-[10px] text-fg-600 mt-0.5">Influence: ${t.influence.toFixed(2)}</div>` : ''}
                ${t.score ? `<div class="text-[10px] text-fg-600 mt-0.5">Concentration score: ${t.score.toFixed(2)}</div>` : ''}
              </div>
            </div>`;
          }).join('')}
        </div>
      `;
    }

    // ─── Q5: What decision only I can make? ───
    const decisions = briefing.decisions;
    document.getElementById('home-decisions-count').textContent = decisions.summary;
    if (!decisions.decisions || decisions.decisions.length === 0) {
      emptyHTML(decisionsEl, 'No CEO-only decisions pending. The org is running without your intervention.');
    } else {
      decisionsEl.innerHTML = `
        <div class="mb-3 p-3 rounded-lg bg-brand-purple/[0.06] border border-brand-purple/15">
          <div class="text-sm font-semibold text-white">${escapeHtml(decisions.headline)}</div>
          <div class="text-[11px] text-brand-purple mt-1">${escapeHtml(decisions.headline_question)}</div>
        </div>
        <div class="space-y-2">
          ${decisions.decisions.map(d => {
            const drillType = d.type === 'urgent_decision' ? 'recommendation' : d.type === 'retention' ? 'pattern' : 'law';
            const drillId = d.linked_laws && d.linked_laws.length ? d.linked_laws[0] : d.title;
            return `<div class="flex items-start gap-3 p-3 rounded-lg bg-brand-purple/[0.04] border border-brand-purple/10 cursor-pointer hover:bg-brand-purple/[0.08] transition-colors" onclick="openDrilldown('${drillType}', '${escapeHtml(drillId)}')">
              <div class="w-7 h-7 rounded-md bg-brand-purple/15 flex items-center justify-center flex-shrink-0">
                <span class="text-brand-purple text-sm font-bold">!</span>
              </div>
              <div class="flex-1">
                <div class="text-[12px] font-semibold text-fg-100">${escapeHtml(d.title)}</div>
                <div class="text-[10px] text-fg-500 mt-0.5">${escapeHtml(d.question)}</div>
                <div class="text-[10px] text-brand-violet mt-1">${escapeHtml(d.recommendation)}</div>
              </div>
              <span class="text-[10px] text-fg-500">conf ${formatConfidence(d.confidence)}</span>
            </div>`;
          }).join('')}
        </div>
      `;
    }

    // OEM State panel is now rendered independently by the /dashboard fetch above
    // (no longer waits for the CEO briefing to resolve)

  } catch (e) {
    errorHTML(overnightEl, 'Failed to load briefing: ' + e.message, 'loadDashboard()');
    errorHTML(oneThingEl, e.message, 'loadDashboard()');
    errorHTML(moneyEl, e.message, 'loadDashboard()');
    errorHTML(knowledgeEl, e.message, 'loadDashboard()');
    errorHTML(decisionsEl, e.message, 'loadDashboard()');
    document.getElementById('oem-status').innerHTML = `<span class="text-brand-rose">●</span> <span>OEM unreachable: ${escapeHtml(e.message)}</span>`;
    document.getElementById('oem-status-badge').textContent = 'OEM OFFLINE';
    document.getElementById('oem-status-badge').className = 'text-[10px] font-semibold text-brand-rose';
    showError('Failed to load CEO briefing: ' + e.message);
  }
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

window.addEventListener('load', () => {
  setTimeout(checkForRunningImports, 1000);
});