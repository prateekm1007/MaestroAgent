// V8 Maestro × Bumble — Mode Tab Switcher + Bottom Nav.
// Bumble's Date/BFF/Bizz pattern adapted for Work/Personal/Both.
// The mode tabs reconfigure the entire experience instantly.

// ─── Mode Tab Switcher ─────────────────────────────────────────────────────

function renderModeTabs(currentMode) {
  // Only show in "both" mode
  if (currentMode !== 'both') return '';

  return `
    <div class="mode-tabs" id="mode-tabs">
      <button class="mode-tab ${currentMode === 'work' ? 'active' : ''}" onclick="switchMode('work')">
        Work
      </button>
      <button class="mode-tab ${currentMode === 'personal' ? 'active' : ''}" onclick="switchMode('personal')">
        Personal
      </button>
    </div>
  `;
}

async function switchMode(mode) {
  try {
    await fetch('/api/personal/mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: mode, user: 'default' }),
    });
  } catch (e) {
    // Non-fatal — mode switch is optimistic
  }

  // Update tab styles
  document.querySelectorAll('.mode-tab').forEach(tab => {
    tab.classList.remove('active');
  });
  const activeTab = document.querySelector(`.mode-tab[onclick*="${mode}"]`);
  if (activeTab) activeTab.classList.add('active');

  // Reconfigure nav
  renderBottomNav(mode);

  // Reload current surface
  if (mode === 'work') {
    if (typeof loadToday === 'function') loadToday();
  } else if (mode === 'personal') {
    if (typeof loadPersonalMode === 'function') loadPersonalMode();
  }
}

// ─── Bottom Nav ────────────────────────────────────────────────────────────

const _workNavItems = [
  { id: 'today', label: 'Today', icon: '☀️' },
  { id: 'work', label: 'Work', icon: '💼' },
  { id: 'ask-v2', label: 'Ask', icon: '💬' },
  { id: 'more', label: 'More', icon: '⋯' },
];

const _personalNavItems = [
  { id: 'personal-today', label: 'Today', icon: '☀️' },
  { id: 'personal-memory', label: 'Memory', icon: '🧠' },
  { id: 'personal-decide', label: 'Decide', icon: '⚖️' },
  { id: 'personal-reflect', label: 'Reflect', icon: '📝' },
];

function renderBottomNav(mode) {
  let existing = document.querySelector('.bottom-nav');
  if (existing) existing.remove();

  const items = mode === 'personal' ? _personalNavItems : _workNavItems;
  const nav = document.createElement('nav');
  nav.className = 'bottom-nav';

  items.forEach(item => {
    const btn = document.createElement('button');
    btn.className = 'nav-item';
    btn.innerHTML = `<span class="icon">${item.icon}</span><span>${escapeHtml(item.label)}</span>`;
    btn.onclick = () => {
      if (item.id === 'more') {
        openMoreMenu(mode);
      } else if (item.id.startsWith('personal-')) {
        navPersonalSurface(item.id);
      } else {
        navTo(item.id);
      }
    };
    nav.appendChild(btn);
  });

  document.body.appendChild(nav);
}

function openMoreMenu(mode) {
  const actions = mode === 'personal' ? [
    { label: 'What Maestro Knows', onclick: 'showWhatMaestroKnows()', style: '' },
    { label: 'Incognito Toggle', onclick: 'toggleIncognito()', style: 'maestro-btn-secondary' },
  ] : [
    { label: 'Role Playbooks', onclick: "navTo('playbook')", style: '' },
    { label: 'Cognitive Organs', onclick: "navTo('cognition')", style: 'maestro-btn-secondary' },
    { label: 'Organizational Story', onclick: "navTo('autobiography')", style: 'maestro-btn-secondary' },
    { label: 'Personal Mode', onclick: "navTo('personal')", style: 'maestro-btn-secondary' },
  ];
  openActionSheet('More', actions);
}

// ─── Initialize on page load ───────────────────────────────────────────────

function initBumbleNav() {
  // Check current mode
  fetch('/api/personal/mode?user=default')
    .then(r => r.json())
    .then(data => {
      const mode = data.mode || 'work';
      renderBottomNav(mode);
    })
    .catch(() => {
      renderBottomNav('work'); // default
    });
}

// Auto-init on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initBumbleNav);
} else {
  initBumbleNav();
}
