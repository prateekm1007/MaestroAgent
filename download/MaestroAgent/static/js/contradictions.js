// CONTRADICTIONS — gaps between stated beliefs and observed behavior
// ═══════════════════════════════════════════════════════════════════════════
// Surface 3 of the cognitive model UI. Lists every contradiction the
// detector found (law violations, assumption violations, commitment
// integrity, bottleneck contradictions) and lets the CEO acknowledge each.
//
// Calls:
//   GET  /api/oem/contradictions
//   POST /api/oem/contradictions/{id}/acknowledge
//
// Product law: eliminates NOTICING ("we honor commitments" while 2 were
// broken) by surfacing the gap between stated beliefs and observed behavior.
// ═══════════════════════════════════════════════════════════════════════════

async function loadContradictions() {
  const listEl = document.getElementById('contradictions-list');
  if (!listEl) return;
  listEl.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Detecting contradictions…</div>';

  try {
    const data = await api.getOEM('/contradictions');
    renderContradictions(listEl, data.contradictions || []);
  } catch (e) {
    listEl.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)} <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="loadContradictions()">Retry</button></div>`;
  }
}

function renderContradictions(container, contradictions) {
  if (!contradictions.length) {
    container.innerHTML = `<div class="ds-empty">
      <div style="font-size:14px;color:var(--ds-text-primary);margin-bottom:6px;">No contradictions detected.</div>
      <div>Stated beliefs and observed behavior are aligned. Contradictions surface automatically as the OEM ingests new signals — commitment breaks, assumption invalidations, law violations, and bottleneck drift.</div>
    </div>`;
    return;
  }

  container.innerHTML = contradictions.map(c => {
    const severity = c.severity || 'medium';
    const sevClass = severity === 'high' || severity === 'critical' ? 'high' : severity === 'medium' ? 'medium' : 'low';
    const acknowledged = c.status === 'acknowledged';
    return `
      <div class="ds-card" data-contradiction-id="${escapeHtml(c.contradiction_id)}">
        <div class="ds-row-between" style="margin-bottom:10px;">
          <div class="ds-row">
            <span class="ds-tag ds-tag-${sevClass}">${escapeHtml(severity.toUpperCase())}</span>
            <span class="ds-meta">${escapeHtml(c.type || 'contradiction')}</span>
          </div>
          ${acknowledged ? `<span class="ds-tag ds-tag-validated">acknowledged</span>` : ''}
        </div>

        <div style="font-size:14px;font-weight:500;color:var(--ds-text-primary);margin-bottom:8px;">${escapeHtml(c.title || c.description || 'Contradiction detected')}</div>

        ${c.stated_belief ? `
          <div style="margin-bottom:8px;">
            <div class="ds-cascade-label">Stated belief</div>
            <div style="font-size:13px;color:var(--ds-text-secondary);">${escapeHtml(c.stated_belief)}</div>
          </div>
        ` : ''}

        ${c.observed_behavior ? `
          <div style="margin-bottom:8px;">
            <div class="ds-cascade-label">Observed behavior</div>
            <div style="font-size:13px;color:var(--ds-text-primary);">${escapeHtml(c.observed_behavior)}</div>
          </div>
        ` : ''}

        ${c.description && c.title ? `
          <div style="font-size:12.5px;color:var(--ds-text-secondary);line-height:1.55;margin-bottom:8px;">${escapeHtml(humanize(c.description))}</div>
        ` : ''}

        ${c.evidence && c.evidence.length ? `
          <div style="margin-bottom:10px;">
            <div class="ds-cascade-label">Evidence (${c.evidence.length})</div>
            <div class="ds-row" style="flex-wrap:wrap;gap:4px;">
              ${c.evidence.slice(0, 6).map(e => `<span class="source-cite">${escapeHtml(e.type || e.signal_type || 'signal')}</span>`).join('')}
              ${c.evidence.length > 6 ? `<span class="ds-meta">+${c.evidence.length - 6} more</span>` : ''}
            </div>
          </div>
        ` : ''}

        ${!acknowledged ? `
          <div class="ds-row" style="gap:6px;">
            <button class="ds-btn ds-btn-primary ds-btn-small" onclick="acknowledgeContradiction('${escapeJs(c.contradiction_id)}')">Acknowledge</button>
          </div>
        ` : ''}
      </div>
    `;
  }).join('');
}

async function acknowledgeContradiction(contradictionId) {
  try {
    await api.postOEM(`/contradictions/${contradictionId}/acknowledge`, {});
    // Reload the list to reflect the acknowledged status
    loadContradictions();
  } catch (e) {
    showError(`Failed to acknowledge: ${e.message}`);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
