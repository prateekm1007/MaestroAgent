// V8 Maestro × Bumble — Onboarding Flow (Round 46 — 6 screens, no mode choice).
// One bold question per screen. Big yellow CTAs. Confident, not a form.
// Stores data via PersonalDataStore + ConsentStore + ModeManager + PersonalKG.
//
// Round 46: Screen 4 (the mode choice) is REMOVED. The user is never
// asked to choose Work, Personal, or Both. Instead:
//   Screen 4: "Connect your work tools" (optional — Jira, Slack, GitHub, Gmail, Calendar).
//   Screen 5: "Connect your personal tools" (optional — personal calendar, personal email, photos).
//   Screen 6: "You're in."
// The user connects what they want, and Maestro figures out the rest.
// The "mode" is inferred from the data. The filter pill lets them focus.

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
    4: renderOnboardingWorkTools,    // Round 46 — was renderOnboardingMode
    5: renderOnboardingPersonalTools, // Round 46 — was renderOnboardingConnect
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
               oninput="document.getElementById('onboard-name-btn').disabled = !this.value.trim"
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
  if (_onboardingData.role) {
    api.postPersonal('/kg/entity', {
      user: 'default', entity_type: 'interest',
      name: _onboardingData.role,
      attributes: { company: _onboardingData.company },
    }).catch(() => {});
  }
  showOnboardingScreen(4);
}

// ─── Screen 4: Connect Work Tools (Round 46 — replaces the mode choice) ───
// The user is NOT asked to choose a mode. They connect work tools (all
// OFF by default). Maestro infers "work context" from the data.

let _workToolToggles = { jira: false, slack: false, github: false, gmail: false, calendar: false };

function renderOnboardingWorkTools() {
  const tools = [
    { id: 'jira', icon: '📋', label: 'Jira', desc: 'Issue tracking & project management' },
    { id: 'slack', icon: '💬', label: 'Slack', desc: 'Team conversations & cross-team signals' },
    { id: 'github', icon: '🐙', label: 'GitHub', desc: 'Code, PRs, & engineering signals' },
    { id: 'gmail', icon: '✉️', label: 'Gmail', desc: 'Work email (read-only)' },
    { id: 'calendar', icon: '📅', label: 'Work Calendar', desc: 'Meetings & commitments' },
  ];

  return `
    <div class="onboarding-screen">
      <div class="text-title" style="margin-bottom:var(--space-2);">Connect your work tools.</div>
      <div class="text-body" style="color:var(--maestro-gray-mid);margin-bottom:var(--space-5);max-width:380px;text-align:center;">
        Optional — skip if you want. I work either way.
      </div>
      <div style="width:100%;max-width:420px;">
        <div class="onboarding-card" style="margin-bottom:var(--space-4);">
          ${tools.map(s => `
            <div class="onboarding-toggle-row">
              <div style="display:flex;align-items:center;gap:var(--space-3);">
                <span style="font-size:24px;">${s.icon}</span>
                <div>
                  <div class="text-label">${escapeHtml(s.label)}</div>
                  <div class="text-caption" style="color:var(--maestro-gray-mid);">${escapeHtml(s.desc)}</div>
                </div>
              </div>
              <div class="maestro-toggle" id="work-toggle-${s.id}" onclick="toggleWorkTool('${s.id}')"></div>
            </div>
          `).join('')}
        </div>
        <div style="display:flex;gap:var(--space-3);">
          <button class="maestro-btn maestro-btn-ghost maestro-btn-full" onclick="showOnboardingScreen(5)">Skip for now</button>
          <button class="maestro-btn maestro-btn-full" onclick="saveOnboardingWorkTools()">Continue</button>
        </div>
      </div>
      <div class="progress-dots">
        ${[1,2,3,4,5,6].map(i => `<div class="progress-dot ${i === 4 ? 'active' : ''}"></div>`).join('')}
      </div>
    </div>
  `;
}

function toggleWorkTool(toolId) {
  _workToolToggles[toolId] = !_workToolToggles[toolId];
  const toggle = document.getElementById(`work-toggle-${toolId}`);
  if (toggle) {
    toggle.classList.toggle('on', _workToolToggles[toolId]);
  }
  // Grant consent if ON. These are work sources — stored under the work
  // namespace in PersonalDataStore. The user can revoke later via
  // "What Maestro Knows."
  if (_workToolToggles[toolId]) {
    api.postPersonal('/consent/grant', {
      user: 'default', source: `work_${toolId}`, purpose: 'store',
    }).catch(() => {});
    api.postPersonal('/consent/grant', {
      user: 'default', source: `work_${toolId}`, purpose: 'retrieve',
    }).catch(() => {});
  }
}

function saveOnboardingWorkTools() {
  _onboardingData.workTools = { ..._workToolToggles };
  showOnboardingScreen(5);
}

// ─── Screen 5: Connect Personal Tools (Round 46 — separate from work) ─────
// Personal tools are on a SEPARATE screen with SEPARATE consent toggles.
// This enforces the consent boundary — work and personal are never
// conflated during onboarding.

let _personalToolToggles = { personal_calendar: false, personal_email: false, photos: false };

function renderOnboardingPersonalTools() {
  const tools = [
    { id: 'personal_calendar', icon: '📆', label: 'Personal Calendar', desc: 'Your life events, appointments' },
    { id: 'personal_email', icon: '📧', label: 'Personal Email', desc: 'Personal correspondence (read-only)' },
    { id: 'photos', icon: '📷', label: 'Photos', desc: 'So I can help you remember' },
  ];

  return `
    <div class="onboarding-screen">
      <div class="text-title" style="margin-bottom:var(--space-2);">Connect your personal tools.</div>
      <div class="text-body" style="color:var(--maestro-gray-mid);margin-bottom:var(--space-5);max-width:380px;text-align:center;">
        Also optional. Personal data stays separate from work by default.
      </div>
      <div style="width:100%;max-width:420px;">
        <div class="onboarding-card" style="margin-bottom:var(--space-4);">
          ${tools.map(s => `
            <div class="onboarding-toggle-row">
              <div style="display:flex;align-items:center;gap:var(--space-3);">
                <span style="font-size:24px;">${s.icon}</span>
                <div>
                  <div class="text-label">${escapeHtml(s.label)}</div>
                  <div class="text-caption" style="color:var(--maestro-gray-mid);">${escapeHtml(s.desc)}</div>
                </div>
              </div>
              <div class="maestro-toggle" id="personal-toggle-${s.id}" onclick="togglePersonalTool('${s.id}')"></div>
            </div>
          `).join('')}
        </div>
        <div style="display:flex;gap:var(--space-3);">
          <button class="maestro-btn maestro-btn-ghost maestro-btn-full" onclick="showOnboardingScreen(6)">Skip for now</button>
          <button class="maestro-btn maestro-btn-full" onclick="saveOnboardingPersonalTools()">Connect</button>
        </div>
      </div>
      <div class="progress-dots">
        ${[1,2,3,4,5,6].map(i => `<div class="progress-dot ${i === 5 ? 'active' : ''}"></div>`).join('')}
      </div>
    </div>
  `;
}

function togglePersonalTool(toolId) {
  _personalToolToggles[toolId] = !_personalToolToggles[toolId];
  const toggle = document.getElementById(`personal-toggle-${toolId}`);
  if (toggle) {
    toggle.classList.toggle('on', _personalToolToggles[toolId]);
  }
  // Grant consent if ON. These are personal sources. The Work/Personal
  // integration toggle (Round 44) still defaults to OFF — connecting
  // personal tools does NOT auto-enable cross-context intelligence.
  if (_personalToolToggles[toolId]) {
    api.postPersonal('/consent/grant', {
      user: 'default', source: toolId, purpose: 'store',
    }).catch(() => {});
    api.postPersonal('/consent/grant', {
      user: 'default', source: toolId, purpose: 'retrieve',
    }).catch(() => {});
  }
}

function saveOnboardingPersonalTools() {
  _onboardingData.personalTools = { ..._personalToolToggles };
  showOnboardingScreen(6);
}

// ─── Screen 6: You're In ──────────────────────────────────────────────────

function renderOnboardingDone() {
  return `
    <div class="onboarding-screen yellow-bg">
      <div class="text-hero" style="text-align:center;margin-bottom:var(--space-5);">You're in.</div>
      <div style="font-size:80px;font-weight:900;margin-bottom:var(--space-5);">✓</div>
      <div class="text-label" style="text-align:center;max-width:300px;margin-bottom:var(--space-6);">
        I'll learn what matters as you use me. You'll get a briefing tomorrow morning.
      </div>
      <button class="maestro-btn maestro-btn-inverted maestro-btn-full" onclick="finishOnboarding()">
        Open Maestro
      </button>
    </div>
  `;
}

function finishOnboarding() {
  window.location.href = '/app.html';
}
