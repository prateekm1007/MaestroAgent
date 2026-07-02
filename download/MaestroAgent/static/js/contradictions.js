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
  listEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

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
      <div class="b-fs14-text-11">No contradictions detected.</div>
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
        <div class="ds-row-between" class="mb-10">
          <div class="ds-row">
            <span class="ds-tag ds-tag-${sevClass}">${escapeHtml(severity.toUpperCase())}</span>
            <span class="ds-meta">${escapeHtml(c.type || 'contradiction')}</span>
          </div>
          ${acknowledged ? `<span class="ds-tag ds-tag-validated">acknowledged</span>` : ''}
        </div>

        <div class="b-fs14-fw500-4">${escapeHtml(c.title || c.description || 'Contradiction detected')}</div>

        ${c.stated_belief ? `
          <div class="mb-8">
            <div class="ds-cascade-label">Stated belief</div>
            <div class="b-fs13-text-16">${escapeHtml(c.stated_belief)}</div>
          </div>
        ` : ''}

        ${c.observed_behavior ? `
          <div class="mb-8">
            <div class="ds-cascade-label">Observed behavior</div>
            <div class="b-fs13-text-7">${escapeHtml(c.observed_behavior)}</div>
          </div>
        ` : ''}

        ${c.description && c.title ? `
          <div class="b-fs125-text-2">${escapeHtml(humanize(c.description))}</div>
        ` : ''}

        ${c.evidence && c.evidence.length ? `
          <div class="mb-10">
            <div class="ds-cascade-label">Evidence (${c.evidence.length})</div>
            <div class="ds-row" class="b-u-gap4">
              ${c.evidence.slice(0, 6).map(e => `<span class="source-cite">${escapeHtml(e.type || e.signal_type || 'signal')}</span>`).join('')}
              ${c.evidence.length > 6 ? `<span class="ds-meta">+${c.evidence.length - 6} more</span>` : ''}
            </div>
          </div>
        ` : ''}

        ${!acknowledged ? `
          <div class="ds-row" class="b-gap6">
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
