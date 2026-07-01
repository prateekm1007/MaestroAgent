// THE INVISIBLE MAESTRO — WORK surface (Bumble-redesigned)
// ═══════════════════════════════════════════════════════════════════════════
// WORK never looks like software. Maestro follows the user into existing
// tools. The user never opens Maestro. Maestro quietly appears.
//
// Bumble design: bold cards, pill buttons, Montserrat typography.
// Each whisper and ambient integration is a maestro-card.
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
    el.innerHTML = `<div class="calm-empty" style="text-align:center;padding:48px 20px;">
      <div style="font-size:20px;font-weight:800;color:var(--maestro-black,var(--text-primary));margin-bottom:8px;font-family:'Montserrat',sans-serif;">Maestro is connecting to your tools.</div>
      <div style="font-size:14px;color:var(--maestro-gray-mid,var(--text-muted));">Configure signal sources in Settings to see ambient intelligence here.</div>
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

  // GitHub card
  const githubConnected = providers.includes('github');
  ambientCards.push({
    tool: 'GitHub',
    message: githubConnected
      ? `${metrics.signals_processed || 0} signals processed from your repositories. ${decisions.decisions.length > 0 ? `${decisions.decisions.length} ${decisions.decisions.length === 1 ? 'decision needs' : 'decisions need'} attention.` : 'No blocked PRs detected.'}`
      : 'GitHub is not connected. Configure it in Settings to see repository intelligence here.',
    action: () => navTo('eng-signals'),
  });

  // Slack card
  ambientCards.push({
    tool: 'Slack',
    message: providers.includes('slack')
      ? (Contradictions.length > 0
        ? `${Contradictions.length} ${Contradictions.length === 1 ? 'cross-team tension was' : 'cross-team tensions were'} detected in recent conversations.`
        : 'Conversations are flowing normally. No tensions detected.')
      : 'Slack is not connected. Configure it in Settings to see conversation intelligence.',
    action: () => navTo('contradictions'),
  });

  // Jira card
  ambientCards.push({
    tool: 'Jira',
    message: providers.includes('jira')
      ? `${metrics.patterns_inferred || 0} patterns inferred from issue transitions. ${metrics.patterns_validated || 0} organizational patterns validated.`
      : 'Jira is not connected. Configure it in Settings to see issue-transition intelligence.',
    action: () => navTo('eng-signals'),
  });

  // Outlook card
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

  // ─── Bumble design: bold cards, Montserrat, pill buttons ──────────
  let html = `<div style="max-width:700px;margin:0 auto;font-family:'Montserrat',sans-serif;">`;

  // Whispers — Bumble cards with amber accent
  if (whispers.length > 0) {
    html += `<div style="font-size:14px;font-weight:800;color:var(--maestro-black,var(--text-primary));margin-bottom:12px;font-family:'Montserrat',sans-serif;">Whispers</div>`;
    whispers.forEach((w, i) => {
      html += `
        <div class="maestro-card whisper" data-idx="${i}" style="margin-bottom:12px;border-left:4px solid var(--maestro-warning,#FF9800);cursor:pointer;">
          <div style="font-size:15px;font-weight:700;color:var(--maestro-black,var(--text-primary));line-height:1.4;">${escapeHtml(humanize(w.text))}</div>
          <div style="font-size:12px;font-weight:600;color:var(--maestro-gray-mid,var(--text-muted));margin-top:6px;">via ${escapeHtml(w.source)}</div>
        </div>
      `;
    });
  }

  // Ambient integrations — Bumble cards with tool badges
  html += `<div style="font-size:14px;font-weight:800;color:var(--maestro-black,var(--text-primary));margin-top:24px;margin-bottom:12px;font-family:'Montserrat',sans-serif;">In your tools</div>`;
  ambientCards.forEach((a, i) => {
    html += `
      <div class="maestro-card ambient-card" data-idx="${i}" style="margin-bottom:12px;cursor:pointer;">
        <div style="display:inline-block;padding:4px 12px;border-radius:999px;background:var(--maestro-yellow-light,#FFF4D1);color:var(--maestro-yellow-dark,#F0B500);font-size:12px;font-weight:800;margin-bottom:8px;">${escapeHtml(a.tool)}</div>
        <div style="font-size:14px;color:var(--maestro-gray-dark,var(--text-secondary));line-height:1.55;">${escapeHtml(a.message)}</div>
      </div>
    `;
  });

  // Deep capabilities — Bumble pill buttons
  html += `<div style="font-size:14px;font-weight:800;color:var(--maestro-black,var(--text-primary));margin-top:24px;margin-bottom:12px;font-family:'Montserrat',sans-serif;">Deep capabilities</div>`;
  html += `<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">`;
  deepCaps.forEach(cap => {
    const label = cap.count > 0
      ? `${escapeHtml(humanize(cap.label))} · ${cap.count}`
      : escapeHtml(humanize(cap.label));
    html += `<button class="maestro-btn maestro-btn-secondary" style="font-size:14px;min-height:44px;padding:10px 16px;" onclick="navTo('${cap.surface}')">${label}</button>`;
  });
  html += `</div>`;

  html += `</div>`;
  el.innerHTML = html;

  // Wire up whisper dismiss + ambient card clicks
  el.querySelectorAll('.whisper').forEach((wEl, i) => {
    wEl.addEventListener('click', () => {
      wEl.style.opacity = '0';
      wEl.style.transform = 'translateX(100%)';
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
