// EVOLUTION — Quarterly Evolution Report (V3 Law 10)
// ═══════════════════════════════════════════════════════════════════════════
// "How has our organization changed?"
// Shows 5 dimensions with delta + direction + narrative.
// The V3 end-state metric — is the organization becoming smarter?
// ═══════════════════════════════════════════════════════════════════════════

async function loadEvolution() {
  const el = document.getElementById('evolution-content');
  if (!el) return;
  el.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Measuring how your organization has evolved…</div>';

  try {
    const data = await api.getOEM('/evolution?window=90d');
    renderEvolutionReport(el, data);
  } catch (e) {
    el.innerHTML = `<div class="calm-empty">
      <div>Your organization is still gathering the history needed to measure evolution.</div>
      <div style="margin-top:8px;font-size:13px;">After 90 days of signals, Maestro will show how decision quality, knowledge mobility, and prediction accuracy have changed.</div>
    </div>`;
  }
}

function renderEvolutionReport(el, data) {
  const dims = data.dimensions || {};
  const overall = data.overall || 'Your organization is evolving.';
  const caveats = data.caveats || '';

  let html = `<div class="meta-surface">`;
  html += `<div class="meta-surface greeting"><span class="org-heartbeat"></span>Your organization has evolved.</div>`;
  html += `<div class="meta-surface sub-greeting">${escapeHtml(humanize(overall))}</div>`;

  // Render each dimension as a story card
  for (const [name, dim] of Object.entries(dims)) {
    const direction = dim.direction || 'stable';
    const delta = dim.delta || 0;
    const narrative = dim.narrative || '';
    const evidence = dim.evidence_count || 0;

    const arrow = direction === 'improving' ? '↑' : direction === 'declining' ? '↓' : '→';
    const color = direction === 'improving' ? 'var(--positive)' : direction === 'declining' ? 'var(--risk)' : 'var(--text-muted)';

    // Humanize the dimension name
    const humanName = name.replace(/_/g, ' ');

    html += `
      <div class="story-card">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
          <span style="font-size:20px;color:${color};">${arrow}</span>
          <span style="font-size:15px;font-weight:500;color:var(--text-primary);text-transform:capitalize;">${escapeHtml(humanName)}</span>
          <span style="margin-left:auto;font-size:13px;color:${color};font-family:var(--font-mono);">${delta > 0 ? '+' : ''}${(delta * 100).toFixed(0)}%</span>
        </div>
        <div class="story-narrative">${escapeHtml(humanize(narrative))}</div>
        <div class="story-evidence">Based on ${evidence} ${evidence === 1 ? 'signal' : 'signals'}</div>
      </div>
    `;
  }

  // Caveats
  if (caveats) {
    html += `<div style="margin-top:24px;padding:16px;border-radius:8px;background:var(--surface-2);border:1px solid var(--divider);font-size:12px;color:var(--text-muted);line-height:1.6;">${escapeHtml(caveats)}</div>`;
  }

  html += `</div>`;
  el.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════════════════════
