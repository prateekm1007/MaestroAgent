// THE INVISIBLE MAESTRO — WORK surface
// ═══════════════════════════════════════════════════════════════════════════
// WORK never looks like software. Maestro follows the user into existing
// tools. The user never opens Maestro. Maestro quietly appears.
//
// This surface shows:
//   1. Ambient integrations — what Maestro sees in your tools
//   2. Contextual whispers — max 2 sentences, disappear after ack
//   3. Compressed access to deep capabilities (inbox, simulator, etc.)
// ═══════════════════════════════════════════════════════════════════════════

async function loadWork() {
  const el = document.getElementById('work-content');
  if (!el) return;
  el.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Listening to your tools…</div>';

  try {
    const [briefing, contradictions, dashboard] = await Promise.all([
      api.getOEM('/ceo-briefing'),
      api.getOEM('/contradictions').catch(() => ({ contradictions: [] })),
      api.getOEM('/dashboard').catch(() => null),
    ]);

    renderWorkSurface(el, briefing, contradictions, dashboard);
  } catch (e) {
    el.innerHTML = `<div class="calm-empty">
      <div>Maestro is connecting to your tools.</div>
      <div style="margin-top:8px;font-size:13px;">Configure signal sources in Settings to see ambient intelligence here.</div>
    </div>`;
  }
}

function renderWorkSurface(el, briefing, contradictions, dashboard) {
  const decisions = briefing.decisions || { decisions: [] };
  const overnight = briefing.overnight || { changes: [] };
  const Contradictions = contradictions.contradictions || [];
  const metrics = dashboard ? dashboard.metrics || {} : {};
  const providers = dashboard ? dashboard.providers_connected || [] : [];

  // Generate whispers from contradictions and overnight changes
  const whispers = [];

  Contradictions.slice(0, 3).forEach(c => {
    whispers.push({
      text: c.title || c.description || 'A contradiction was detected in your organization.',
      source: c.type || 'organizational pattern',
      action: () => navTo('contradictions'),
    });
  });

  overnight.changes.slice(0, 2).forEach(c => {
    whispers.push({
      text: `${c.title}: ${c.detail}`.substring(0, 120),
      source: c.entity || c.domain || 'overnight signal',
      action: () => navTo('home'),
    });
  });

  // Generate ambient integration cards from REAL data (not hardcoded)
  const ambientCards = [];

  // GitHub card — uses real signal count from dashboard
  const githubConnected = providers.includes('github');
  ambientCards.push({
    tool: 'GitHub',
    message: githubConnected
      ? `${metrics.signals_processed || 0} signals processed from your repositories. ${decisions.decisions.length > 0 ? `${decisions.decisions.length} ${decisions.decisions.length === 1 ? 'decision needs' : 'decisions need'} attention.` : 'No blocked PRs detected.'}`
      : 'GitHub is not connected. Configure it in Settings to see repository intelligence here.',
    action: () => navTo('eng-signals'),
  });

  // Slack card — uses real contradiction count
  ambientCards.push({
    tool: 'Slack',
    message: providers.includes('slack')
      ? (Contradictions.length > 0
        ? `${Contradictions.length} ${Contradictions.length === 1 ? 'cross-team tension was' : 'cross-team tensions were'} detected in recent conversations.`
        : 'Conversations are flowing normally. No tensions detected.')
      : 'Slack is not connected. Configure it in Settings to see conversation intelligence.',
    action: () => navTo('contradictions'),
  });

  // Jira card — uses real signal count
  ambientCards.push({
    tool: 'Jira',
    message: providers.includes('jira')
      ? `${metrics.patterns_inferred || 0} patterns inferred from issue transitions. ${metrics.patterns_validated || 0} organizational patterns validated.`
      : 'Jira is not connected. Configure it in Settings to see issue-transition intelligence.',
    action: () => navTo('eng-signals'),
  });

  // Outlook card — bookmarklet prompt
  ambientCards.push({
    tool: 'Outlook',
    message: 'Install the Maestro bookmarklet to see organizational context inside your email.',
    action: () => navTo('eng-settings'),
  });

  // Deep capabilities (compressed)
  const deepCaps = [
    { label: 'Decisions I owe', surface: 'inbox', count: decisions.decisions.length },
    { label: 'What changed overnight', surface: 'home', count: overnight.changes.length },
    { label: 'Customer relationships', surface: 'customer', count: 0 },
    { label: 'Live meeting intelligence', surface: 'live', count: 0 },
  ];

  let html = `<div class="meta-surface">`;

  // Whispers
  if (whispers.length > 0) {
    html += `<div class="intention-label">Whispers</div>`;
    whispers.forEach((w, i) => {
      html += `
        <div class="whisper" data-idx="${i}">
          ${escapeHtml(humanize(w.text))}
          <div class="whisper-source">via ${escapeHtml(w.source)}</div>
        </div>
      `;
    });
  }

  // Ambient integrations
  html += `<div class="intention-label" style="margin-top:32px;">In your tools</div>`;
  ambientCards.forEach((a, i) => {
    html += `
      <div class="ambient-card" data-idx="${i}">
        <div class="ambient-tool">${escapeHtml(a.tool)}</div>
        <div class="ambient-message">${escapeHtml(a.message)}</div>
      </div>
    `;
  });

  // Deep capabilities
  html += `<div class="intention-label" style="margin-top:32px;">Deep capabilities</div>`;
  html += `<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">`;
  deepCaps.forEach(cap => {
    if (cap.count > 0) {
      html += `<button class="intention-prompt" onclick="navTo('${cap.surface}')">${escapeHtml(humanize(cap.label))} · ${cap.count}</button>`;
    } else {
      html += `<button class="intention-prompt" onclick="navTo('${cap.surface}')">${escapeHtml(humanize(cap.label))}</button>`;
    }
  });
  html += `</div>`;

  html += `</div>`;
  el.innerHTML = html;

  // Wire up whisper dismiss + ambient card clicks
  el.querySelectorAll('.whisper').forEach((wEl, i) => {
    wEl.addEventListener('click', () => {
      wEl.classList.add('dismissed');
      setTimeout(() => wEl.remove(), 300);
      if (whispers[i] && whispers[i].action) whispers[i].action();
    });
  });

  el.querySelectorAll('.ambient-card').forEach((aEl, i) => {
    aEl.addEventListener('click', () => {
      if (ambientCards[i] && ambientCards[i].action) ambientCards[i].action();
    });
  });
}

// ═══════════════════════════════════════════════════════════════════════════
