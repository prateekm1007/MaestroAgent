// V8 Maestro × Bumble — Filter Pill + Bottom Nav (Round 46).
// Round 46: The mode tabs (Work/Personal/BOTH switcher) are REMOVED from
// the default experience. The user does not "switch modes." The user
// opens Maestro and sees their whole life. The "mode" is a FILTER, not
// a switch.
//
// The filter pill is a subtle Bumble pill in the top-right of the Today
// surface: [ All | Work | Personal ]. Default is "All." The user can
// tap "Work" to filter to work cards only, or "Personal" to filter to
// personal cards only. This is a VIEW filter — the underlying data does
// not change.
//
// The bottom nav is UNIFIED — always the same 4 items regardless of
// filter: Today / Memory / Ask / More. (Phase 2 will wire this fully;
// for now the bottom nav stays at 4 items and does not switch based on
// mode.)

// ─── Filter state (Round 46) ───────────────────────────────────────────────
// The filter is a VIEW parameter. Default: 'all'. It is NOT stored as
// user state — it is a transient UI filter that resets to 'all' on page
// load. The user can change it for the current session.
let _currentFilter = 'all';  // 'all' | 'work' | 'personal'

function getCurrentFilter() {
  return _currentFilter;
}

function setCurrentFilter(filter) {
  const valid = ['all', 'work', 'personal'];
  const newFilter = valid.includes(filter) ? filter : 'all';
  if (newFilter === _currentFilter) return;  // no change, no-op
  _currentFilter = newFilter;
  // Persist for the session (not as user state — just UI convenience)
  try { sessionStorage.setItem('maestro-filter', _currentFilter); } catch (e) {}

  // Round 47 Block 2.4 — OPTIMISTIC filter application.
  // Immediately hide/show cards based on their _mode dot, WITHOUT
  // waiting for a refetch. The deck filters instantly (no spinner).
  // The background refetch (loadToday) updates silently if different.
  _optimisticFilterApply();

  // Record filter usage for pilot metrics (privacy-preserving — count only)
  try {
    api.postOEM('/pilot/metrics/filter', { filter: _currentFilter }).catch(() => {});
  } catch (e) { /* non-fatal */ }

  // Re-render the filter pill to reflect the new active state
  renderFilterPill();

  // Background refetch — updates silently if the data is different.
  // No loading spinner — the optimistic filter already applied.
  if (window._currentSurface === 'today' && typeof loadToday === 'function') {
    loadToday();
  }
}

function _optimisticFilterApply() {
  // Round 47 Block 2.4 — instantly hide/show cards based on the filter.
  // This runs BEFORE the refetch, so the user sees instant feedback.
  const cards = document.querySelectorAll('.brief-item, .swipe-card, [data-mode]');
  cards.forEach(card => {
    const mode = card.dataset.mode || card.getAttribute('data-mode') || '';
    if (_currentFilter === 'all') {
      card.style.display = '';
    } else if (_currentFilter === 'work' && mode === 'personal') {
      card.style.display = 'none';
    } else if (_currentFilter === 'personal' && mode === 'work') {
      card.style.display = 'none';
    } else {
      card.style.display = '';
    }
  });
}

function _loadInitialFilter() {
  try {
    const saved = sessionStorage.getItem('maestro-filter');
    if (saved && ['all', 'work', 'personal'].includes(saved)) {
      _currentFilter = saved;
    }
  } catch (e) { /* default to 'all' */ }
}

// ─── Filter Pill renderer (Round 46) ──────────────────────────────────────
// The filter pill is a subtle Bumble pill with 3 options. The active
// option gets the Bumble yellow background; inactive options are ghost.
// It renders in the top-right of the Today surface (or wherever the
// caller injects it).

function renderFilterPill(containerId) {
  // If a container ID is provided, render into it. Otherwise, find or
  // create the pill in the today-content header.
  let container = containerId ? document.getElementById(containerId) : null;
  if (!container) {
    // Try to find an existing filter-pill-container in the today surface
    container = document.getElementById('filter-pill-container');
  }
  if (!container) return;  // no container — the pill is not rendered

  const options = [
    { value: 'all', label: 'All' },
    { value: 'work', label: 'Work' },
    { value: 'personal', label: 'Personal' },
  ];

  container.innerHTML = `
    <div class="b-flex-gap4">
      ${options.map(opt => `
        <button class="maestro-btn ${_currentFilter === opt.value ? '' : 'maestro-btn-ghost'}"
                class="b-fs12-minh30"
                onclick="setCurrentFilter('${opt.value}')"
                aria-pressed="${_currentFilter === opt.value}">
          ${escapeHtml(opt.label)}
        </button>
      `).join('')}
    </div>
  `;
}

// ─── Mode Tab Switcher — evolved into Filter Pill (Round 46 → Round 78) ───
// The original Bumble mode tabs (Work/Personal/BOTH) evolved into the
// filter pill (All/Work/Personal). This IS the Bumble pattern — pill
// buttons, yellow active state, Montserrat font. The filter pill is
// rendered by renderFilterPill() above.
//
// renderModeTabs() is kept as a backward-compat shim that delegates to
// the filter pill. Callers that used the old API still work.

function renderModeTabs(currentMode) {
  // Delegate to the filter pill — the Bumble evolution of mode tabs.
  // Callers that still invoke this get the pill rendered.
  renderFilterPill(null);
  return '';
}

async function switchMode(mode) {
  // switchMode delegates to setCurrentFilter — same concept, new name.
  // Maps old mode values to new filter values
  const filterMap = { work: 'work', personal: 'personal', both: 'all' };
  const filter = filterMap[mode] || 'all';
  setCurrentFilter(filter);
}

// ─── Bottom Nav (UNIFIED — Round 46) ──────────────────────────────────────
// The bottom nav is ALWAYS the same 4 items regardless of filter:
// Today / Memory / Ask / More. It does NOT switch based on mode.

const _unifiedNavItems = [
  { id: 'today', label: 'Today', icon: '☀️' },
  { id: 'memory', label: 'Memory', icon: '🧠' },
  { id: 'ask-v2', label: 'Ask', icon: '💬' },
  { id: 'more', label: 'More', icon: '⋯' },
];

function renderBottomNav(mode) {
  // Round 46: the 'mode' parameter is IGNORED. The bottom nav is always
  // the same 4 unified items.
  let existing = document.querySelector('.bottom-nav');
  if (existing) existing.remove();

  const items = _unifiedNavItems;
  const nav = document.createElement('nav');
  nav.className = 'bottom-nav';

  items.forEach(item => {
    const btn = document.createElement('button');
    btn.className = 'nav-item';
    btn.innerHTML = `<span class="icon">${item.icon}</span><span>${escapeHtml(item.label)}</span>`;
    btn.onclick = () => {
      if (item.id === 'more') {
        openMoreMenu();
      } else {
        navTo(item.id);
      }
    };
    nav.appendChild(btn);
  });

  document.body.appendChild(nav);
}

function openMoreMenu(mode) {
  // Round 46: the 'mode' parameter is IGNORED. The More menu is unified.
  const actions = [
    { label: 'What Maestro Knows', onclick: 'showWhatMaestroKnows()', style: '' },
    { label: 'Incognito Toggle', onclick: 'toggleIncognito()', style: 'maestro-btn-secondary' },
    { label: 'Personal Context in Work', onclick: 'showIntegrationToggle()', style: 'maestro-btn-secondary' },
    { label: 'Role Playbooks', onclick: "navTo('playbook')", style: 'maestro-btn-secondary' },
    { label: 'Cognitive Organs', onclick: "navTo('cognition')", style: 'maestro-btn-secondary' },
    { label: "Organizational Story", onclick: "navTo('autobiography')", style: 'maestro-btn-secondary' },
  ];
  openActionSheet('More', actions);
}

// Round 46 — the integration toggle is reachable from the More menu.
function showIntegrationToggle() {
  const el = document.getElementById('main-content') || document.getElementById('personal-main');
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  // Round 78 CRITICAL 4: use _getCurrentUser() instead of hardcoded 'default'
  if (typeof _getCurrentUser === 'function') {
    _getCurrentUser().then(user => {
      if (!user) { el.innerHTML = '<div class="ds-error">Could not determine user identity.</div>'; return; }
      _loadIntegrationSettings(el, user);
    });
  } else {
    // Fallback if onboarding.js hasn't loaded yet
    _loadIntegrationSettings(el, 'local-dev-user');
  }
}

function _loadIntegrationSettings(el, user) {
  api.getPersonal('/settings/personal-context-in-work?user=' + encodeURIComponent(user)).then(data => {
    const enabled = data.personal_context_in_work;
    el.innerHTML = `
      <div class="b-mw500-m40p24">
        <div class="b-fs20-fw800">Personal Context in Work</div>
        <div class="b-fs14-text-13">
          When enabled, your own personal state (sleep, energy, calendar conflicts) appears in Work Mode.
          Maestro never surfaces intelligence about a third party. You can disable this at any time.
        </div>
        <div class="b-p16-bg">
          <div class="b-fs13-fw700-2">Current state: ${enabled ? 'ON' : 'OFF (default)'}</div>
          <button class="maestro-btn ${enabled ? 'maestro-btn-ghost' : ''} b-w-full-2" onclick="toggleIntegration(${!enabled})">
            ${enabled ? 'Disable' : 'Enable'}
          </button>
        </div>
        <button class="maestro-btn maestro-btn-ghost maestro-btn-full fs-13" onclick="navTo('today')">Back to Today</button>
      </div>
    `;
  }).catch(() => {
    el.innerHTML = '<div class="ds-error">Failed to load integration settings.</div>';
  });
}

async function toggleIntegration(enable) {
  try {
    const user = (typeof _getCurrentUser === 'function') ? (await _getCurrentUser()) : 'local-dev-user';
    if (!user) { showToast('Could not determine user identity.', 'error'); return; }
    await api.postPersonal('/settings/personal-context-in-work', { enabled: enable, user: user });
    showIntegrationToggle(); // reload
  } catch (e) {
    showToast('Toggle failed: ' + e.message, 'error');
  }
}

// ─── Initialize on page load ───────────────────────────────────────────────

function initBumbleNav() {
  // Round 46: load the initial filter from sessionStorage (default 'all').
  _loadInitialFilter();
  // The bottom nav is unified — always the same 4 items.
  renderBottomNav('all');  // the 'all' arg is ignored (kept for compat)
}

// Auto-init on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initBumbleNav);
} else {
  initBumbleNav();
}
