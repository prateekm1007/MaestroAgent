// THE INVISIBLE MAESTRO — Organizational Dot + Heartbeat
// ═══════════════════════════════════════════════════════════════════════════
// One tiny colored dot. Universal presence indicator.
//   Green  — Nothing requires attention.
//   Yellow — Opportunity.
//   Orange — Cross-functional impact.
//   Red    — Do not continue.
//
// Clicking opens context. Never a dashboard.
// ═══════════════════════════════════════════════════════════════════════════

let _orgDotColor = 'green';
let _orgDotPollTimer = null;

function initOrgDot() {
  // Render the dot in the topbar
  const topbar = document.querySelector('.topbar');
  if (!topbar) return;

  // Check if dot already exists
  if (document.getElementById('org-dot-container')) return;

  // Create the dot container
  const dotContainer = document.createElement('div');
  dotContainer.id = 'org-dot-container';
  dotContainer.style.cssText = 'display:flex;align-items:center;gap:8px;cursor:pointer;padding:4px 12px;border-radius:8px;transition:all var(--ease);';
  dotContainer.innerHTML = `
    <span class="org-dot org-dot-green" id="org-dot" aria-label="Organizational status"></span>
    <span class="b-fs13-fw500-5" id="org-dot-label">All clear</span>
  `;
  dotContainer.addEventListener('click', () => {
    // Clicking the dot navigates to TODAY (the morning brief)
    navTo('today');
  });
  dotContainer.addEventListener('mouseenter', () => {
    dotContainer.style.background = 'var(--surface-2)';
  });
  dotContainer.addEventListener('mouseleave', () => {
    dotContainer.style.background = 'transparent';
  });

  // Insert before the OEM status badge
  const oemBadge = topbar.querySelector('#oem-pulse')?.parentElement;
  if (oemBadge) {
    topbar.insertBefore(dotContainer, oemBadge);
  } else {
    topbar.appendChild(dotContainer);
  }

  // Start polling for org status (every 60 seconds)
  pollOrgDotStatus();
  if (_orgDotPollTimer) clearInterval(_orgDotPollTimer);
  _orgDotPollTimer = setInterval(pollOrgDotStatus, 60000);
}

async function pollOrgDotStatus() {
  try {
    const [briefing, contradictionsResp] = await Promise.all([
      api.getOEM('/ceo-briefing'),
      api.getOEM('/contradictions').catch(() => ({ contradictions: [] })),
    ]);
    const contradictions = contradictionsResp.contradictions || [];
    const color = determineDotColor(briefing, contradictions);
    updateOrgDot(color);
  } catch (e) {
    // Keep the current dot state if the API fails
  }
}

function updateOrgDot(color) {
  _orgDotColor = color;
  const dot = document.getElementById('org-dot');
  const label = document.getElementById('org-dot-label');
  if (!dot || !label) return;

  // Remove all color classes
  dot.className = 'org-dot';
  dot.classList.add(`org-dot-${color}`);

  const labels = {
    green: 'All clear',
    yellow: 'Opportunity',
    orange: 'Cross-functional impact',
    red: 'Attention needed',
  };
  label.textContent = labels[color] || 'All clear';

  // Update the title attribute for accessibility
  dot.setAttribute('title', labels[color] || 'All clear');
  dot.setAttribute('aria-label', `Organizational status: ${labels[color] || 'all clear'}`);
}

// ═══════════════════════════════════════════════════════════════════════════
