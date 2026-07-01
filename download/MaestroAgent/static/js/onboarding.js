// V8 Maestro × Bumble — Onboarding Flow (6 screens).
// One bold question per screen. Big yellow CTAs. Confident, not a form.
// Stores data via PersonalDataStore + ConsentStore + ModeManager + PersonalKG.

let _onboardingStep = 1;
let _onboardingData = {};

function startOnboarding() {
  _onboardingStep = 1;
  _onboardingData = {};
  showOnboardingScreen(1);
}

function showOnboardingScreen(step) {
  _onboardingStep = step;
  const el = document.getElementById('onboarding-container');
  if (!el) return;

  const screens = {
    1: renderOnboardingWelcome,
    2: renderOnboardingName,
    3: renderOnboardingAbout,
    4: renderOnboardingMode,
    5: renderOnboardingConnect,
    6: renderOnboardingDone,
  };

  el.innerHTML = screens[step]();
  updateProgressDots(step);
}

function updateProgressDots(step) {
  const dotsContainer = document.querySelector('.progress-dots');
  if (!dotsContainer) return;
  const dots = dotsContainer.querySelectorAll('.progress-dot');
  dots.forEach((dot, i) => {
    dot.classList.toggle('active', i + 1 === step);
  });
}

// ─── Screen 1: Welcome ────────────────────────────────────────────────────

function renderOnboardingWelcome() {
  return `
    <div class="onboarding-screen">
      <div class="onboarding-logo">M</div>
      <div class="text-hero" style="text-align:center;margin-bottom:var(--space-3);">Make the first move.</div>
      <div class="text-body" style="text-align:center;color:var(--maestro-gray-dark);max-width:320px;margin-bottom:var(--space-6);">
        I'm Maestro — your cognitive companion for work and life.
      </div>
      <button class="maestro-btn maestro-btn-full" onclick="showOnboardingScreen(2)">Get Started</button>
      <div class="progress-dots">
        ${[1,2,3,4,5,6].map(i => `<div class="progress-dot ${i === 1 ? 'active' : ''}"></div>`).join('')}
      </div>
    </div>
  `;
}

// ─── Screen 2: Name ───────────────────────────────────────────────────────

function renderOnboardingName() {
  return `
    <div class="onboarding-screen">
      <div class="text-title" style="margin-bottom:var(--space-5);">What's your name?</div>
      <div style="width:100%;max-width:420px;">
        <input type="text" class="maestro-input" id="onboard-name" placeholder="First name"
               oninput="document.getElementById('onboard-name-btn').disabled = !this.value.trim()"
               style="margin-bottom:var(--space-4);" autofocus />
        <div class="text-caption" style="color:var(--maestro-gray-mid);margin-bottom:var(--space-5);">
          This is how I'll greet you.
        </div>
        <button class="maestro-btn maestro-btn-full" id="onboard-name-btn" disabled
                onclick="saveOnboardingName()">Continue</button>
      </div>
      <div class="progress-dots">
        ${[1,2,3,4,5,6].map(i => `<div class="progress-dot ${i === 2 ? 'active' : ''}"></div>`).join('')}
      </div>
    </div>
  `;
}

function saveOnboardingName() {
  const name = document.getElementById('onboard-name').value.trim();
  if (!name) return;
  _onboardingData.name = name;
  // Store via API
  api.postPersonal('/kg/entity', {
    user: 'default',
    entity_type: 'person',
    name: name,
    attributes: { role: 'self' },
  }).catch(() => {});
  showOnboardingScreen(3);
}

// ─── Screen 3: About You ──────────────────────────────────────────────────

function renderOnboardingAbout() {
  return `
    <div class="onboarding-screen">
      <div class="text-title" style="margin-bottom:var(--space-5);">Tell me about you.</div>
      <div style="width:100%;max-width:420px;">
        <div class="onboarding-card" style="margin-bottom:var(--space-3);">
          <div class="text-label" style="margin-bottom:var(--space-2);">How old are you?</div>
          <input type="number" class="maestro-input" id="onboard-age" placeholder="Age" min="18" max="120" />
        </div>
        <div class="onboarding-card" style="margin-bottom:var(--space-3);">
          <div class="text-label" style="margin-bottom:var(--space-2);">What do you do?</div>
          <input type="text" class="maestro-input" id="onboard-role" placeholder="Role (e.g. Engineer, Student)" style="margin-bottom:var(--space-2);" />
          <input type="text" class="maestro-input" id="onboard-company" placeholder="Company (optional)" />
        </div>
        <div class="text-caption" style="color:var(--maestro-gray-mid);margin-bottom:var(--space-4);">
          This stays on your device. Never shared.
        </div>
        <button class="maestro-btn maestro-btn-full" onclick="saveOnboardingAbout()">Continue</button>
      </div>
      <div class="progress-dots">
        ${[1,2,3,4,5,6].map(i => `<div class="progress-dot ${i === 3 ? 'active' : ''}"></div>`).join('')}
      </div>
    </div>
  `;
}

function saveOnboardingAbout() {
  _onboardingData.age = document.getElementById('onboard-age')?.value || '';
  _onboardingData.role = document.getElementById('onboard-role')?.value || '';
  _onboardingData.company = document.getElementById('onboard-company')?.value || '';
  // Store as KG entities
  if (_onboardingData.role) {
    api.postPersonal('/kg/entity', {
      user: 'default', entity_type: 'interest',
      name: _onboardingData.role,
      attributes: { company: _onboardingData.company },
    }).catch(() => {});
  }
  showOnboardingScreen(4);
}

// ─── Screen 4: Mode Choice ────────────────────────────────────────────────

let _selectedMode = '';

function renderOnboardingMode() {
  return `
    <div class="onboarding-screen">
      <div class="text-title" style="margin-bottom:var(--space-5);">What's this for?</div>
      <div style="width:100%;max-width:420px;">
        <div class="onboarding-card onboarding-mode-card" id="mode-card-work" onclick="selectOnboardingMode('work')">
          <div class="checkmark">✓</div>
          <div style="font-size:28px;margin-bottom:var(--space-2);">💼</div>
          <div class="text-title" style="margin-bottom:var(--space-1);">Work</div>
          <div class="text-body" style="color:var(--maestro-gray-mid);">Organizational judgment, enterprise tools</div>
        </div>
        <div class="onboarding-card onboarding-mode-card" id="mode-card-personal" onclick="selectOnboardingMode('personal')">
          <div class="checkmark">✓</div>
          <div style="font-size:28px;margin-bottom:var(--space-2);">🌱</div>
          <div class="text-title" style="margin-bottom:var(--space-1);">Personal</div>
          <div class="text-body" style="color:var(--maestro-gray-mid);">Life, relationships, self-growth</div>
        </div>
        <div class="onboarding-card onboarding-mode-card" id="mode-card-both" onclick="selectOnboardingMode('both')">
          <div class="checkmark">✓</div>
          <div style="font-size:28px;margin-bottom:var(--space-2);">⚡</div>
          <div class="text-title" style="margin-bottom:var(--space-1);">Both</div>
          <div class="text-body" style="color:var(--maestro-gray-mid);">Seamless switching, shared memory</div>
        </div>
        <button class="maestro-btn maestro-btn-full" id="onboard-mode-btn" disabled
                style="margin-top:var(--space-4);" onclick="saveOnboardingMode()">Continue</button>
      </div>
      <div class="progress-dots">
        ${[1,2,3,4,5,6].map(i => `<div class="progress-dot ${i === 4 ? 'active' : ''}"></div>`).join('')}
      </div>
    </div>
  `;
}

function selectOnboardingMode(mode) {
  _selectedMode = mode;
  // Remove all selections
  document.querySelectorAll('.onboarding-mode-card').forEach(c => {
    c.classList.remove('selected-work', 'selected-personal', 'selected-both');
  });
  // Add selection
  document.getElementById(`mode-card-${mode}`).classList.add(`selected-${mode}`);
  // Enable button
  document.getElementById('onboard-mode-btn').disabled = false;
}

function saveOnboardingMode() {
  if (!_selectedMode) return;
  _onboardingData.mode = _selectedMode;
  api.postPersonal('/mode', { mode: _selectedMode, user: 'default' }).catch(() => {});
  showOnboardingScreen(5);
}

// ─── Screen 5: Connect Sources ────────────────────────────────────────────

let _sourceToggles = { calendar: false, email: false, photos: false };

function renderOnboardingConnect() {
  const sources = [
    { id: 'calendar', icon: '📅', label: 'Calendar', desc: 'So I can brief you on your day' },
    { id: 'email', icon: '✉️', label: 'Email', desc: 'So I can surface what matters' },
    { id: 'photos', icon: '📷', label: 'Photos', desc: 'So I can help you remember' },
  ];

  return `
    <div class="onboarding-screen">
      <div class="text-title" style="margin-bottom:var(--space-2);">Let's connect some things.</div>
      <div class="text-body" style="color:var(--maestro-gray-mid);margin-bottom:var(--space-5);max-width:380px;text-align:center;">
        Skip if you want — I work either way.
      </div>
      <div style="width:100%;max-width:420px;">
        <div class="onboarding-card" style="margin-bottom:var(--space-4);">
          ${sources.map(s => `
            <div class="onboarding-toggle-row">
              <div style="display:flex;align-items:center;gap:var(--space-3);">
                <span style="font-size:24px;">${s.icon}</span>
                <div>
                  <div class="text-label">${escapeHtml(s.label)}</div>
                  <div class="text-caption" style="color:var(--maestro-gray-mid);">${escapeHtml(s.desc)}</div>
                </div>
              </div>
              <div class="maestro-toggle" id="toggle-${s.id}" onclick="toggleSource('${s.id}')"></div>
            </div>
          `).join('')}
        </div>
        <div style="display:flex;gap:var(--space-3);">
          <button class="maestro-btn maestro-btn-ghost maestro-btn-full" onclick="showOnboardingScreen(6)">Skip for now</button>
          <button class="maestro-btn maestro-btn-full" onclick="saveOnboardingConnect()">Connect</button>
        </div>
      </div>
      <div class="progress-dots">
        ${[1,2,3,4,5,6].map(i => `<div class="progress-dot ${i === 5 ? 'active' : ''}"></div>`).join('')}
      </div>
    </div>
  `;
}

function toggleSource(sourceId) {
  _sourceToggles[sourceId] = !_sourceToggles[sourceId];
  const toggle = document.getElementById(`toggle-${sourceId}`);
  if (toggle) {
    toggle.classList.toggle('on', _sourceToggles[sourceId]);
  }
  // Grant consent if ON, do nothing if OFF (no revoke needed during onboarding)
  if (_sourceToggles[sourceId]) {
    api.postPersonal('/consent/grant', {
      user: 'default', source: sourceId, purpose: 'store',
    }).catch(() => {});
    api.postPersonal('/consent/grant', {
      user: 'default', source: sourceId, purpose: 'retrieve',
    }).catch(() => {});
  }
}

function saveOnboardingConnect() {
  _onboardingData.sources = { ..._sourceToggles };
  showOnboardingScreen(6);
}

// ─── Screen 6: You're In ──────────────────────────────────────────────────

function renderOnboardingDone() {
  return `
    <div class="onboarding-screen yellow-bg">
      <div class="text-hero" style="text-align:center;margin-bottom:var(--space-5);">You're in.</div>
      <div style="font-size:80px;font-weight:900;margin-bottom:var(--space-5);">✓</div>
      <div class="text-label" style="text-align:center;max-width:300px;margin-bottom:var(--space-6);">
        I'll make the first move. You'll get a briefing tomorrow morning.
      </div>
      <button class="maestro-btn maestro-btn-inverted maestro-btn-full" onclick="finishOnboarding()">
        Open Maestro
      </button>
    </div>
  `;
}

function finishOnboarding() {
  // Redirect to main app
  window.location.href = '/app.html';
}
