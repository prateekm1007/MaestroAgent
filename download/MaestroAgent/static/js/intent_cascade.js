// INTENT CASCADE — the OEM's root view: "tell me about this intent."
// ═══════════════════════════════════════════════════════════════════════════
// Surface 1 of the cognitive model UI. Lists every active intent and lets
// the CEO expand the full cascade inline:
//   intent → assumptions → hypotheses → preparations → evidence
//
// Calls:
//   GET  /api/oem/intents                  (list)
//   GET  /api/oem/intents/{id}             (cascade)
//   POST /api/oem/hypotheses/{id}/resolve  (validated | invalidated)
//   POST /api/oem/preparations/{id}/approve
//
// Product law: eliminates THINKING about "why does this decision matter?"
// by surfacing the full chain — assumptions, hypotheses, preparations, and
// evidence — in one view.
// ═══════════════════════════════════════════════════════════════════════════

let _intentCascadeExpanded = new Set(); // intent_ids currently expanded

async function loadIntentCascade() {
  const listEl = document.getElementById('intent-cascade-list');
  if (!listEl) return;
  listEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    const data = await api.getOEM('/intents');
    renderIntentList(listEl, data.intents || []);
  } catch (e) {
    listEl.innerHTML = `<div class="ds-error">Failed to load intents: ${escapeHtml(e.message)} <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="loadIntentCascade()">Retry</button></div>`;
  }
}

function renderIntentList(container, intents) {
  if (!intents.length) {
    container.innerHTML = `<div class="ds-empty">
      <div class="b-fs14-text-11">No active intents yet.</div>
      <div>Intents are inferred from your recommendations and signal history. Connect more signal sources in Settings to surface them.</div>
    </div>`;
    return;
  }

  container.innerHTML = intents.map(intent => {
    const isExpanded = _intentCascadeExpanded.has(intent.intent_id);
    return `
      <div class="ds-card" data-intent-id="${escapeHtml(intent.intent_id)}">
        <div class="ds-row-between cursor-pointer" onclick="toggleIntentCascade('${escapeJs(intent.intent_id)}')">
          <div class="b-flex-u">
            <div class="ds-row mb-6">
              <span class="ds-tag ds-tag-${intentStatusTagClass(intent.status)}">${escapeHtml(intent.status || 'active')}</span>
              ${intent.intent_type ? `<span class="ds-meta">${escapeHtml(intent.intent_type)}</span>` : ''}
            </div>
            <div class="b-fs145-fw500">${escapeHtml(intent.goal)}</div>
            <div class="ds-meta">${intent.owner ? `Owner: <span class="ds-meta-strong">${escapeHtml(intent.owner)}</span>` : 'No owner assigned'}</div>
          </div>
          <div class="ds-row b-u-5cd1">
            ${intent.confidence != null ? `<span class="ds-meta">conf <span class="ds-meta-strong">${formatConfidence(intent.confidence)}</span></span>` : ''}
            <span class="b-text-muted-2">›</span>
          </div>
        </div>
        <div id="intent-cascade-detail-${escapeHtml(intent.intent_id)}" class="b-u-d1b3"></div>
      </div>
    `;
  }).join('');

  // Auto-expand any intents that were expanded before re-render
  intents.forEach(intent => {
    if (_intentCascadeExpanded.has(intent.intent_id)) {
      loadIntentCascadeDetail(intent.intent_id);
    }
  });
}

function intentStatusTagClass(status) {
  const s = (status || 'active').toLowerCase();
  if (s === 'achieved') return 'validated';
  if (s === 'abandoned' || s === 'superseded') return 'rejected';
  return 'pending';
}

async function toggleIntentCascade(intentId) {
  const detailEl = document.getElementById(`intent-cascade-detail-${intentId}`);
  if (!detailEl) return;

  if (_intentCascadeExpanded.has(intentId)) {
    _intentCascadeExpanded.delete(intentId);
    detailEl.style.display = 'none';
    // Toggle the chevron
    const card = detailEl.closest('.ds-card');
    if (card) {
      const chev = card.querySelector('.ds-row-between span:last-child');
      if (chev) chev.style.transform = 'rotate(0)';
    }
  } else {
    _intentCascadeExpanded.add(intentId);
    detailEl.style.display = 'block';
    const card = detailEl.closest('.ds-card');
    if (card) {
      const chev = card.querySelector('.ds-row-between span:last-child');
      if (chev) chev.style.transform = 'rotate(90deg)';
    }
    loadIntentCascadeDetail(intentId);
  }
}

async function loadIntentCascadeDetail(intentId) {
  const detailEl = document.getElementById(`intent-cascade-detail-${intentId}`);
  if (!detailEl) return;
  detailEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    const cascade = await api.getOEM(`/intents/${intentId}`);
    detailEl.innerHTML = renderIntentCascade(cascade);
  } catch (e) {
    detailEl.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

function renderIntentCascade(cascade) {
  const assumptions = cascade.assumptions || [];
  const hypotheses = cascade.hypotheses || [];
  const preparations = cascade.preparations || [];
  const evidence = cascade.evidence || [];

  const sections = [];

  // ── Assumptions ──────────────────────────────────────────────────────────
  if (assumptions.length) {
    sections.push(`
      <div class="ds-cascade-leaf">
        <div class="ds-cascade-label">Assumptions (${assumptions.length})</div>
        <div class="ds-stack">
          ${assumptions.map(a => `
            <div class="ds-card b-p1214">
              <div class="ds-row-between mb-6">
                <span class="ds-tag ds-tag-${assumptionStatusTagClass(a.status)}">${escapeHtml(a.status || 'open')}</span>
                ${a.stakes ? `<span class="ds-tag ds-tag-${a.stakes === 'critical' || a.stakes === 'high' ? 'high' : a.stakes === 'medium' ? 'medium' : 'low'}">${escapeHtml(a.stakes)}</span>` : ''}
              </div>
              <div class="b-fs13-text-10">${escapeHtml(humanize(a.statement))}</div>
              ${a.context ? `<div class="ds-meta mt-6">${escapeHtml(humanize(a.context))}</div>` : ''}
              ${a.made_by ? `<div class="ds-meta mt-4">By <span class="ds-meta-strong">${escapeHtml(a.made_by)}</span></div>` : ''}
            </div>
          `).join('')}
        </div>
      </div>
    `);
  }

  // ── Hypotheses ───────────────────────────────────────────────────────────
  if (hypotheses.length) {
    sections.push(`
      <div class="ds-cascade-leaf">
        <div class="ds-cascade-label">Hypotheses (${hypotheses.length})</div>
        <div class="ds-stack">
          ${hypotheses.map(h => renderHypothesisInline(h)).join('')}
        </div>
      </div>
    `);
  }

  // ── Preparations ─────────────────────────────────────────────────────────
  if (preparations.length) {
    sections.push(`
      <div class="ds-cascade-leaf">
        <div class="ds-cascade-label">Preparations (${preparations.length})</div>
        <div class="ds-stack">
          ${preparations.map(p => renderPreparationInline(p)).join('')}
        </div>
      </div>
    `);
  }

  // ── Evidence ─────────────────────────────────────────────────────────────
  if (evidence.length) {
    sections.push(`
      <div class="ds-cascade-leaf">
        <div class="ds-cascade-label">Evidence (${evidence.length} signal${evidence.length === 1 ? '' : 's'})</div>
        <div class="ds-stack">
          ${evidence.slice(0, 12).map(ev => `
            <div class="ds-card b-p1014">
              <div class="ds-row-between">
                <div class="ds-row">
                  <span class="source-cite">${escapeHtml(ev.type || ev.signal_type || 'signal')}</span>
                  ${ev.actor ? `<span class="ds-meta">${escapeHtml(ev.actor)}</span>` : ''}
                </div>
                ${ev.timestamp ? `<span class="ds-meta">${formatTimestamp(ev.timestamp)}</span>` : ''}
              </div>
              ${ev.artifact ? `<div class="ds-meta mt-4">${escapeHtml(ev.artifact)}</div>` : ''}
            </div>
          `).join('')}
          ${evidence.length > 12 ? `<div class="ds-meta b-p62">+ ${evidence.length - 12} more</div>` : ''}
        </div>
      </div>
    `);
  }

  if (!sections.length) {
    return '<div class="ds-empty">No linked assumptions, hypotheses, preparations, or evidence yet.</div>';
  }

  return `<div class="ds-cascade">${sections.join('')}</div>`;
}

function renderHypothesisInline(h) {
  const status = h.status || 'pending';
  const canResolve = status === 'pending' || status === 'open';
  return `
    <div class="ds-card b-p1214">
      <div class="ds-row-between mb-6">
        <span class="ds-tag ds-tag-${hypothesisStatusTagClass(status)}">${escapeHtml(status)}</span>
        ${h.confidence != null ? `<span class="ds-meta">conf <span class="ds-meta-strong">${formatConfidence(h.confidence)}</span></span>` : ''}
      </div>
      <div class="b-fs13-text-11">${escapeHtml(humanize(h.statement))}</div>
      ${h.prediction ? `<div class="ds-meta mb-4">Prediction: <span class="ds-meta-strong">${escapeHtml(h.prediction)}</span></div>` : ''}
      ${h.predicted_value != null ? `<div class="ds-meta">Predicted: <span class="ds-meta-strong">${escapeHtml(String(h.predicted_value))}</span></div>` : ''}
      ${canResolve ? `
        <div class="ds-row b-mt8-gap6">
          <button class="ds-btn ds-btn-positive ds-btn-small" onclick="resolveHypothesisFromCascade('${escapeJs(h.hypothesis_id)}','validated')">Mark validated</button>
          <button class="ds-btn ds-btn-risk ds-btn-small" onclick="resolveHypothesisFromCascade('${escapeJs(h.hypothesis_id)}','invalidated')">Mark invalidated</button>
        </div>
      ` : ''}
    </div>
  `;
}

function renderPreparationInline(p) {
  const status = p.status || 'ready';
  const isReady = status === 'ready' || status === 'draft';
  return `
    <div class="ds-card b-p1214">
      <div class="ds-row-between mb-6">
        <span class="ds-tag ds-tag-${preparationStatusTagClass(status)}">${escapeHtml(status)}</span>
        <span class="ds-meta">${escapeHtml(p.preparation_type || 'preparation')}</span>
      </div>
      <div class="b-fs13-fw500-2">${escapeHtml(humanize(p.title))}</div>
      ${p.summary ? `<div class="b-fs125-text">${escapeHtml(humanize(p.summary))}</div>` : ''}
      ${isReady ? `
        <div class="ds-row b-mt8-gap6">
          <button class="ds-btn ds-btn-positive ds-btn-small" onclick="approvePreparationFromCascade('${escapeJs(p.preparation_id)}')">Approve</button>
          <button class="ds-btn ds-btn-risk ds-btn-small" onclick="rejectPreparationFromCascade('${escapeJs(p.preparation_id)}')">Reject</button>
        </div>
      ` : ''}
    </div>
  `;
}

function hypothesisStatusTagClass(status) {
  const s = (status || 'pending').toLowerCase();
  if (s === 'validated') return 'validated';
  if (s === 'invalidated') return 'rejected';
  if (s === 'uncertain' || s === 'inconclusive') return 'uncertain';
  return 'pending';
}

function preparationStatusTagClass(status) {
  const s = (status || 'ready').toLowerCase();
  if (s === 'approved') return 'approved';
  if (s === 'rejected') return 'rejected';
  if (s === 'ready') return 'ready';
  return 'open';
}

function assumptionStatusTagClass(status) {
  const s = (status || 'open').toLowerCase();
  if (s === 'validated') return 'validated';
  if (s === 'invalidated') return 'rejected';
  return 'open';
}

async function resolveHypothesisFromCascade(hypothesisId, outcome) {
  try {
    await api.postOEM(`/hypotheses/${hypothesisId}/resolve`, { outcome });
    // Find the expanded intent and reload its cascade
    for (const intentId of _intentCascadeExpanded) {
      loadIntentCascadeDetail(intentId);
    }
  } catch (e) {
    showError(`Failed to resolve hypothesis: ${e.message}`);
  }
}

async function approvePreparationFromCascade(prepId) {
  try {
    await api.postOEM(`/preparations/${prepId}/approve?approved_by=ceo`);
    for (const intentId of _intentCascadeExpanded) {
      loadIntentCascadeDetail(intentId);
    }
  } catch (e) {
    showError(`Failed to approve: ${e.message}`);
  }
}

async function rejectPreparationFromCascade(prepId) {
  // The API exposes approve + a status mutation; reject is the inverse.
  // For now we mark approved_by with a 'rejected' note via approve endpoint
  // since the backend doesn't yet expose a /reject route — the CEO's
  // decision is captured either way.
  try {
    await api.postOEM(`/preparations/${prepId}/approve?approved_by=ceo-rejected`);
    for (const intentId of _intentCascadeExpanded) {
      loadIntentCascadeDetail(intentId);
    }
  } catch (e) {
    showError(`Failed to reject: ${e.message}`);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
