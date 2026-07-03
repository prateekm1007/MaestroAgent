// ═══════════════════════════════════════════════════════════════════════════
// Maestro Ambient Whisper — Content Script v2.0
// ═══════════════════════════════════════════════════════════════════════════
//
// CEO's Ambient Layer spec (2026-07-03):
//   - Every card has 4 parts: Situation → Insight → Evidence → Action
//   - Golden Rule: Never interrupt. Only arrive when intelligence changes a decision.
//   - 5-second auto-dismiss (unless hovered)
//   - Only high-priority whispers auto-show
//   - Bumble theme (via styles.css — zero inline styles)
//
// Delivery surfaces: Gmail, Calendar, GitHub, Zoom, Slack, Jira, Salesforce,
//   Notion, Figma
// ═══════════════════════════════════════════════════════════════════════════

(function() {
  'use strict';

  // ─── Configuration ────────────────────────────────────────────────────
  const MAESTRO_URL = localStorage.getItem('maestro_url') || 'http://127.0.0.1:8765';
  const CHECK_INTERVAL_MS = 30000;  // Check every 30 seconds
  const AUTO_DISMISS_MS = 5000;     // 5-second auto-dismiss (CEO's spec)
  const COOLDOWN_MS = 60000;        // Don't show the same insight twice in 60s

  let panel = null;
  let dismissTimer = null;
  let lastInsight = '';

  // ─── Context detection ────────────────────────────────────────────────
  function detectContext() {
    const url = window.location.href;
    const title = document.title || '';

    // Gmail
    if (url.includes('mail.google.com')) {
      const senderEl = document.querySelector('[email]') || document.querySelector('.gD');
      const sender = senderEl ? (senderEl.getAttribute('email') || senderEl.textContent.trim()) : '';
      return { app: 'gmail', context: 'email', entity: sender, topic: title };
    }

    // GitHub PR
    if (url.includes('github.com') && url.includes('/pull/')) {
      const repo = url.split('github.com/')[1] ? url.split('github.com/')[1].split('/pull/')[0] : '';
      return { app: 'github', context: 'review', entity: repo, topic: 'code_review' };
    }

    // GitHub issue
    if (url.includes('github.com') && url.includes('/issues/')) {
      const repo = url.split('github.com/')[1] ? url.split('github.com/')[1].split('/issues/')[0] : '';
      return { app: 'github', context: 'ticket', entity: repo, topic: title };
    }

    // Jira
    if (url.includes('atlassian.net') && url.includes('/browse/')) {
      const ticketId = url.split('/browse/')[1] ? url.split('/browse/')[1].split('?')[0] : '';
      return { app: 'jira', context: 'ticket', entity: ticketId, topic: title };
    }

    // Salesforce
    if (url.includes('lightning.force.com')) {
      return { app: 'salesforce', context: 'customer', entity: title, topic: 'crm' };
    }

    // Notion
    if (url.includes('notion.so')) {
      return { app: 'notion', context: 'document', entity: '', topic: title };
    }

    // Figma
    if (url.includes('figma.com')) {
      return { app: 'figma', context: 'design', entity: '', topic: title };
    }

    // Zoom
    if (url.includes('zoom.us')) {
      return { app: 'zoom', context: 'meeting', entity: '', topic: title };
    }

    // Slack
    if (url.includes('app.slack.com')) {
      const channelEl = document.querySelector('[data-qa="channel_name"]');
      const channel = channelEl ? channelEl.textContent.trim() : '';
      return { app: 'slack', context: 'message', entity: channel, topic: title };
    }

    // Calendar
    if (url.includes('calendar.google.com')) {
      return { app: 'calendar', context: 'meeting', entity: '', topic: title };
    }

    return null;
  }

  // ─── API call ─────────────────────────────────────────────────────────
  async function fetchWhisper(ctx) {
    try {
      const params = new URLSearchParams({
        context: ctx.context,
        entity: ctx.entity || '',
        topic: ctx.topic || '',
      });
      const resp = await fetch(`${MAESTRO_URL}/api/oem/whisper?${params}`, {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
      });
      if (!resp.ok) return null;
      return await resp.json();
    } catch (e) {
      // Network error — Maestro may not be running. Silent (golden rule).
      return null;
    }
  }

  // ─── Golden Rule: should we show? ─────────────────────────────────────
  function shouldShow(whispers) {
    // Golden Rule: Never interrupt. Only arrive when intelligence changes a decision.
    if (!whispers || whispers.length === 0) return false;

    // Only high-priority whispers auto-show
    const highPriority = whispers.filter(w => w.priority === 'high');
    if (highPriority.length === 0) return false;

    // Don't show the same insight twice in one session
    const currentInsight = highPriority[0].insight;
    if (currentInsight === lastInsight) return false;

    // Respect cooldown
    const lastShown = parseInt(localStorage.getItem('maestro_last_shown') || '0', 10);
    if (Date.now() - lastShown < COOLDOWN_MS) return false;

    lastInsight = currentInsight;
    localStorage.setItem('maestro_last_shown', String(Date.now()));
    return true;
  }

  // ─── Render ────────────────────────────────────────────────────────────
  function esc(s) {
    if (!s) return '';
    return String(s).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  }

  function createCard(w) {
    const evidenceHtml = (w.evidence || []).map(e => `
      <div class="maestro-ambient-evidence-item">
        <span class="maestro-ambient-evidence-source">${esc(e.source)}</span>
        <span class="maestro-ambient-evidence-date">${esc(e.date)}</span>
        <span class="maestro-ambient-evidence-text">${esc(e.text)}</span>
      </div>
    `).join('');

    // CEO Directive: confidence % removed — replaced with why_surfaced (evidence-based)
    const priorityClass = `priority-${w.priority || 'medium'}`;
    const priorityBadge = w.priority === 'high'
      ? `<span class="maestro-ambient-priority-badge high">High Priority</span>` : '';

    const actionPayload = encodeURIComponent(JSON.stringify(w.action ? w.action.payload : {}));
    const actionType = w.action ? w.action.type : 'open_in_maestro';
    const actionLabel = w.action ? w.action.label : 'Open in Maestro';

    return `
      <div class="maestro-ambient-card ${priorityClass}">
        <div class="maestro-ambient-situation">
          <span class="maestro-ambient-label">Situation</span>
          <span class="maestro-ambient-situation-text">${esc(w.situation)}${priorityBadge}</span>
        </div>
        <div class="maestro-ambient-insight">
          <span class="maestro-ambient-label">Insight</span>
          <span class="maestro-ambient-insight-text">${esc(w.insight)}</span>
        </div>
        ${evidenceHtml ? `
        <div class="maestro-ambient-evidence">
          <span class="maestro-ambient-label">Evidence</span>
          <div class="maestro-ambient-evidence-list">${evidenceHtml}</div>
        </div>` : ''}
        ${w.counterfactuals ? `
        <div class="maestro-ambient-counterfactuals">
          <span class="maestro-ambient-label">What If</span>
          ${w.counterfactuals.map(cf => `
            <div class="maestro-ambient-counterfactual">
              <span class="cf-scenario">${esc(cf.scenario)}</span>
              <span class="cf-assessment">${esc(cf.assessment)}</span>
            </div>
            ${cf.evidence ? `<div class="cf-evidence">${esc(cf.evidence)}</div>` : ''}
          `).join('')}
        </div>` : ''}
        ${w.collaboration ? `
        <div class="maestro-ambient-collaboration">
          <span class="maestro-ambient-label">Team</span>
          ${Object.entries(w.collaboration).map(([team, status]) => `
            <span class="collab-team collab-${status.status}">${esc(team)} ${esc(status.status)}</span>
          `).join('')}
        </div>` : ''}
        ${w.memory && w.memory.times_shown > 0 ? `
        <div class="maestro-ambient-memory">
          ${w.memory.ignored_count > 0
            ? `<span class="memory-escalated">Ignored ${w.memory.ignored_count}× — risk increasing</span>`
            : `<span class="memory-shown">Shown ${w.memory.times_shown}×</span>`}
        </div>` : ''}
        ${w.urgency ? `
        <div class="maestro-ambient-urgency">
          <span class="urgency-text">${esc(w.urgency)}</span>
        </div>` : ''}
        <button class="maestro-ambient-action"
                data-action="${esc(actionType)}"
                data-payload="${actionPayload}"
                data-whisper-id="${esc(w.whisper_id)}"
                data-insight="${esc(w.insight)}">
          ${esc(actionLabel)} ↓
        </button>
        ${w.why_surfaced ? `
        <div class="maestro-ambient-why">
          <span class="maestro-ambient-label">Why Maestro surfaced this</span>
          <span class="maestro-ambient-why-text">${esc(w.why_surfaced)}</span>
        </div>` : ''}
      </div>
    `;
  }

  function showPanel(whispers) {
    if (!panel) createPanel();
    const cards = whispers.map(createCard).join('');
    const header = `
      <div class="maestro-ambient-panel-header">
        <span class="maestro-ambient-panel-title">⚡ Maestro</span>
        <button class="maestro-ambient-panel-close" id="maestro-close-btn">×</button>
      </div>
    `;
    panel.innerHTML = header + cards;
    panel.classList.add('visible');

    // Bind close button
    const closeBtn = panel.querySelector('#maestro-close-btn');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => dismissPanel('closed'));
    }

    // Bind action buttons
    panel.querySelectorAll('.maestro-ambient-action').forEach(btn => {
      btn.addEventListener('click', () => handleAction(btn));
    });

    // CEO Directive: confidence bar removed — replaced with why_surfaced text

    // Auto-dismiss after 5 seconds (CEO's spec: "Less than five seconds")
    clearTimeout(dismissTimer);
    dismissTimer = setTimeout(() => dismissPanel('timeout'), AUTO_DISMISS_MS);

    // Hover pauses auto-dismiss
    panel.addEventListener('mouseenter', () => clearTimeout(dismissTimer));
    panel.addEventListener('mouseleave', () => {
      clearTimeout(dismissTimer);
      dismissTimer = setTimeout(() => dismissPanel('timeout'), AUTO_DISMISS_MS);
    });
  }

  function dismissPanel(reason) {
    if (!panel) return;
    panel.classList.remove('visible');
    // Record outcome (ignored) if auto-dismissed
    if (reason === 'timeout') {
      const firstCard = panel.querySelector('.maestro-ambient-action');
      if (firstCard) {
        recordOutcome(firstCard.dataset.whisperId, 'ignored', firstCard.dataset.insight);
      }
    }
    clearTimeout(dismissTimer);
  }

  function createPanel() {
    panel = document.createElement('div');
    panel.className = 'maestro-ambient-panel';
    document.body.appendChild(panel);
  }

  // ─── Action handling ──────────────────────────────────────────────────
  function handleAction(btn) {
    const actionType = btn.dataset.action;
    const payload = JSON.parse(decodeURIComponent(btn.dataset.payload) || '{}');
    const whisperId = btn.dataset.whisperId;
    const insight = btn.dataset.insight;

    switch (actionType) {
      case 'insert_text':
        // Insert into the active text field (Gmail compose, Slack input, etc.)
        const activeField = document.activeElement;
        if (activeField && (activeField.tagName === 'TEXTAREA' || activeField.contentEditable === 'true')) {
          if (activeField.contentEditable === 'true') {
            activeField.innerHTML += payload.text || '';
          } else {
            activeField.value += payload.text || '';
          }
        }
        recordOutcome(whisperId, 'acted', insight);
        dismissPanel('acted');
        break;

      case 'prepare_email':
        // Open Maestro with the prepared email draft
        window.open(`${MAESTRO_URL}/#prepare-email:${encodeURIComponent(JSON.stringify(payload))}`, '_blank');
        recordOutcome(whisperId, 'acted', insight);
        dismissPanel('acted');
        break;

      case 'open_in_maestro':
        // Open a Maestro surface
        const surface = payload.surface || 'home';
        window.open(`${MAESTRO_URL}/#${surface}`, '_blank');
        recordOutcome(whisperId, 'acted', insight);
        dismissPanel('acted');
        break;

      case 'approve_anyway':
        // Record the override
        recordOutcome(whisperId, 'overrode', insight);
        dismissPanel('overrode');
        break;

      default:
        window.open(MAESTRO_URL, '_blank');
        recordOutcome(whisperId, 'acted', insight);
        dismissPanel('acted');
    }
  }

  // ─── Outcome tracking (closes the feedback loop) ──────────────────────
  function recordOutcome(whisperId, action, insight) {
    try {
      fetch(`${MAESTRO_URL}/api/oem/whisper/outcome`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ whisper_id: whisperId, action: action, insight: insight }),
      });
    } catch (e) {
      // Silent — outcome tracking is best-effort
    }
  }

  // ─── Main loop ─────────────────────────────────────────────────────────
  async function check() {
    const ctx = detectContext();
    if (!ctx) return;

    const data = await fetchWhisper(ctx);
    if (!data || !data.whispers) return;

    if (shouldShow(data.whispers)) {
      const highPriority = data.whispers.filter(w => w.priority === 'high');
      showPanel(highPriority);
    }
  }

  // ─── Init ──────────────────────────────────────────────────────────────
  // Wait 3 seconds after page load before first check (don't interrupt immediately)
  setTimeout(() => {
    check();
    setInterval(check, CHECK_INTERVAL_MS);
  }, 3000);

})();
