/*
 * Maestro Ambient Overlay — bookmarklet that surfaces organizational
 * judgment without opening Maestro.
 *
 * The auditor's core finding: "The coder built the intelligence layer
 * but not the ambient delivery mechanism." This is that mechanism.
 *
 * How it works:
 *   1. User drags the bookmarklet to their bookmarks bar.
 *   2. On any page (Gmail, Calendar, GitHub, Jira, Slack, Zoom), they
 *      click the bookmarklet.
 *   3. The overlay detects the current context (which app, calendar
 *      title, URL domain) and calls /api/oem/ambient.
 *   4. If Maestro has something to whisper (intent-relevant knowledge,
 *      interrupt-worthy events), a small non-intrusive panel appears
 *      in the corner.
 *   5. The panel disappears after 10 seconds or when clicked away.
 *
 * Privacy by design:
 *   - The bookmarklet only reads the URL domain and page title — never
 *     page content, never keystrokes, never email bodies.
 *   - It calls the Maestro API with only: active_app, url_domain,
 *     page_title (which maps to calendar_title).
 *   - The user explicitly clicks the bookmarklet — Maestro never
 *     auto-activates.
 *
 * Installation:
 *   1. Create a new bookmark.
 *   2. Name it "Maestro Whisper".
 *   3. Set the URL to: javascript:(function(){...code below...})();
 *
 * Or serve this file from the Maestro backend and have users drag the
 * link from the settings page.
 */

// ─── Detect context from the current page ─────────────────────────────────

function detectContext() {
  const url = window.location.href;
  const domain = window.location.hostname;
  const title = document.title;

  let activeApp = 'browser';
  let calendarTitle = '';
  let urlContext = domain;

  // Gmail
  if (domain.includes('mail.google')) {
    activeApp = 'email';
  }
  // Google Calendar
  else if (domain.includes('calendar.google')) {
    activeApp = 'calendar';
    // Calendar page title often includes the event title
    calendarTitle = title.replace(' - Google Calendar', '').trim();
  }
  // GitHub
  else if (domain.includes('github.com')) {
    activeApp = 'github';
  }
  // Jira / Atlassian
  else if (domain.includes('atlassian') || domain.includes('jira')) {
    activeApp = 'jira';
  }
  // Slack
  else if (domain.includes('slack.com')) {
    activeApp = 'slack';
  }
  // Zoom
  else if (domain.includes('zoom')) {
    activeApp = 'zoom';
  }
  // Salesforce / HubSpot
  else if (domain.includes('salesforce') || domain.includes('hubspot')) {
    activeApp = 'crm';
  }
  // Google Docs
  else if (domain.includes('docs.google')) {
    activeApp = 'docs';
  }

  return { activeApp, calendarTitle, urlContext };
}

// ─── Fetch ambient state from Maestro ─────────────────────────────────────

async function fetchAmbientState(maestroHost) {
  const ctx = detectContext();
  const params = new URLSearchParams({
    active_app: ctx.activeApp,
    calendar_title: ctx.calendarTitle,
    url_context: ctx.urlContext,
  });

  try {
    const resp = await fetch(`${maestroHost}/api/oem/ambient?${params}`);
    if (!resp.ok) return null;
    return await resp.json();
  } catch (e) {
    console.error('[Maestro] Ambient fetch failed:', e);
    return null;
  }
}

// ─── Render the overlay panel ─────────────────────────────────────────────

function renderOverlay(state, maestroHost) {
  // Remove any existing overlay
  const existing = document.getElementById('maestro-ambient-overlay');
  if (existing) existing.remove();

  if (!state || !state.should_show) {
    // Show a "nothing to whisper" toast for 2 seconds
    const toast = document.createElement('div');
    toast.id = 'maestro-ambient-overlay';
    toast.style.cssText = `
      position: fixed; bottom: 20px; right: 20px; z-index: 999999;
      background: #1a1a2e; color: #9a9aa3; font-family: -apple-system, sans-serif;
      font-size: 12px; padding: 10px 14px; border-radius: 8px;
      border: 1px solid rgba(255,255,255,0.1); max-width: 320px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    `;
    toast.innerHTML = `
      <div style="display:flex;align-items:center;gap:6px;">
        <span style="color:#7c5cff;font-weight:700;">M</span>
        <span>Maestro has nothing to add right now.</span>
      </div>
    `;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 2000);
    return;
  }

  const overlay = document.createElement('div');
  overlay.id = 'maestro-ambient-overlay';
  overlay.style.cssText = `
    position: fixed; bottom: 20px; right: 20px; z-index: 999999;
    background: #0d0d1a; color: #eaeaef; font-family: -apple-system, sans-serif;
    font-size: 12px; padding: 0; border-radius: 10px;
    border: 1px solid rgba(124,92,255,0.3); max-width: 360px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.4); overflow: hidden;
  `;

  const intent = state.intent || {};
  const whisper = state.whisper || {};
  const pulse = state.pulse || {};
  const interrupts = state.interrupts || [];

  let html = `
    <div style="background:rgba(124,92,255,0.1);padding:8px 12px;display:flex;align-items:center;justify-content:space-between;">
      <div style="display:flex;align-items:center;gap:6px;">
        <span style="color:#7c5cff;font-weight:700;font-size:14px;">M</span>
        <span style="font-weight:600;color:#fff;">Maestro Whisper</span>
      </div>
      <span style="color:#9a9aa3;font-size:10px;text-transform:uppercase;">${intent.label || ''}</span>
    </div>
  `;

  // Whisper (the main thing to surface)
  if (whisper.text) {
    html += `
      <div style="padding:10px 12px;border-bottom:1px solid rgba(255,255,255,0.05);">
        <div style="color:#eaeaef;line-height:1.4;">${whisper.text}</div>
        ${whisper.action ? `<div style="color:#7c5cff;font-size:11px;margin-top:6px;cursor:pointer;" onclick="window.open('${maestroHost}${whisper.endpoint || ''}','_blank')">${whisper.action} →</div>` : ''}
      </div>
    `;
  }

  // Interrupt-worthy events
  if (interrupts.length > 0) {
    html += `<div style="padding:8px 12px;border-bottom:1px solid rgba(255,255,255,0.05);"><div style="color:#9a9aa3;font-size:10px;text-transform:uppercase;margin-bottom:4px;">Needs attention</div>`;
    for (const ev of interrupts.slice(0, 3)) {
      const priorityColor = ev.interrupt_decision?.priority === 'escalate' ? '#ef4444'
        : ev.interrupt_decision?.priority === 'interrupt' ? '#ef4444'
        : ev.interrupt_decision?.priority === 'recommend' ? '#f59e0b'
        : '#9a9aa3';
      html += `
        <div style="margin-bottom:4px;padding-left:8px;border-left:2px solid ${priorityColor};">
          <div style="color:#eaeaef;">${ev.title || ''}</div>
          <div style="color:#9a9aa3;font-size:10px;">${ev.why_it_matters || ''}</div>
        </div>
      `;
    }
    html += `</div>`;
  }

  // Pulse (org state)
  if (pulse.state) {
    const pulseColor = pulse.state === 'healthy' || pulse.state === 'execution_accelerating' ? '#22c55e'
      : pulse.state === 'turbulent' || pulse.state === 'trust_falling' ? '#ef4444'
      : '#f59e0b';
    html += `
      <div style="padding:6px 12px;display:flex;align-items:center;gap:6px;">
        <span style="color:${pulseColor};font-size:10px;">●</span>
        <span style="color:#9a9aa3;font-size:10px;">${pulse.narrative || pulse.state}</span>
      </div>
    `;
  }

  // Close button
  html += `
    <div style="padding:4px 12px;display:flex;justify-content:space-between;align-items:center;">
      <span style="color:#6b7280;font-size:9px;">Confidence: ${Math.round((intent.confidence || 0) * 100)}%</span>
      <span style="color:#6b7280;font-size:11px;cursor:pointer;" onclick="this.closest('#maestro-ambient-overlay').remove()">✕</span>
    </div>
  `;

  overlay.innerHTML = html;
  document.body.appendChild(overlay);

  // Auto-dismiss after 15 seconds (unless hovered)
  let dismissTimer = setTimeout(() => overlay.remove(), 15000);
  overlay.addEventListener('mouseenter', () => clearTimeout(dismissTimer));
  overlay.addEventListener('mouseleave', () => {
    dismissTimer = setTimeout(() => overlay.remove(), 5000);
  });
}

// ─── Main entry point ─────────────────────────────────────────────────────

(function() {
  // Try to detect the Maestro host from the current page's known patterns
  // or use a default. In production, this would be configured per-deployment.
  const MAESTRO_HOST = window.__MAESTRO_HOST__ || 'http://localhost:8000';

  fetchAmbientState(MAESTRO_HOST).then(state => {
    renderOverlay(state, MAESTRO_HOST);
  });
})();
