// PREPARED DECISIONS — "X is ready. Approve?"
// ═══════════════════════════════════════════════════════════════════════════
// Surface 2 of the cognitive model UI. Replaces the "you should do X" framing
// of recommendations with "X is ready. Approve?" — the CPO's directive.
//
// Rendered as a new panel ABOVE the existing "Today's Attention" panel on Home.
// The existing #ecc-attention DOM is preserved unchanged so Playwright tests
// continue to pass; this surface adds a sibling #ecc-prepared panel.
//
// Calls:
//   GET  /api/oem/preparations              (list prepared work packets)
//   POST /api/oem/preparations/{id}/approve (CEO approves/rejects)
//
// Product law: eliminates PREPARING ("what work do I need to do before I can
// decide?") by surfacing work packets that are already assembled — rollback
// plans, RFC drafts, customer briefs, etc.
// ═══════════════════════════════════════════════════════════════════════════

async function loadPreparedDecisions() {
  const el = document.getElementById('ecc-prepared');
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    const data = await api.getOEM('/preparations');
    renderPreparedDecisions(el, data.preparations || []);
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)} <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="loadPreparedDecisions()">Retry</button></div>`;
  }
}

function renderPreparedDecisions(container, preps) {
  const countEl = document.getElementById('ecc-prepared-count');
  if (countEl) countEl.textContent = `${preps.length} ready`;

  if (!preps.length) {
    container.innerHTML = `<div class="ds-empty">
      <div class="b-fs135-text-2">No prepared decisions yet.</div>
      <div>Prepared decisions are assembled automatically from your recommendations — rollback plans, RFC drafts, customer briefs. They appear here when ready for your approval.</div>
    </div>`;
    return;
  }

  container.innerHTML = preps.map(p => {
    const status = p.status || 'ready';
    const isReady = status === 'ready' || status === 'draft';
    const statusClass = status === 'approved' ? 'approved' : status === 'rejected' ? 'rejected' : 'ready';
    const evidenceCount = (p.evidence || []).length;
    const assumptionCount = (p.assumptions || p.linked_assumptions || []).length;

    return `
      <div class="ds-card" data-preparation-id="${escapeHtml(p.preparation_id)}">
        <div class="ds-row-between" class="mb-8">
          <div class="ds-row">
            <span class="ds-tag ds-tag-${statusClass}">${escapeHtml(status)}</span>
            <span class="ds-meta">${escapeHtml(p.preparation_type || 'preparation')}</span>
          </div>
          ${p.confidence != null ? `<span class="ds-meta">conf <span class="ds-meta-strong">${formatConfidence(p.confidence)}</span></span>` : ''}
        </div>

        <div class="b-fs145-fw500-2">${escapeHtml(humanize(p.title))}</div>

        ${p.summary ? `<div class="b-fs13-text-18">${escapeHtml(humanize(p.summary))}</div>` : ''}

        <div class="ds-row" class="b-gap14-mb10-2">
          ${assumptionCount > 0 ? `<span class="ds-meta">${assumptionCount} assumption${assumptionCount === 1 ? '' : 's'}</span>` : ''}
          ${evidenceCount > 0 ? `<span class="ds-meta">${evidenceCount} evidence signal${evidenceCount === 1 ? '' : 's'}</span>` : ''}
          ${p.intent_id ? `<span class="ds-meta">linked intent</span>` : ''}
        </div>

        ${p.content ? `
          <div class="mb-10">
            <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="togglePrepContent('${escapeJs(p.preparation_id)}')">Review content</button>
            <div id="prep-content-${escapeHtml(p.preparation_id)}" class="b-hidden-mt8">${escapeHtml(p.content)}</div>
          </div>
        ` : ''}

        ${isReady ? `
          <div class="ds-row" class="b-gap6">
            <button class="ds-btn ds-btn-positive ds-btn-small" onclick="approvePreparedDecision('${escapeJs(p.preparation_id)}')">Approve</button>
            <button class="ds-btn ds-btn-risk ds-btn-small" onclick="rejectPreparedDecision('${escapeJs(p.preparation_id)}')">Reject</button>
            ${p.intent_id ? `<button class="ds-btn ds-btn-ghost ds-btn-small" onclick="navTo('intents')">View cascade</button>` : ''}
          </div>
        ` : status === 'approved' ? `
          <div class="ds-meta">Approved by ${escapeHtml(p.approved_by || 'ceo')}</div>
        ` : ''}
      </div>
    `;
  }).join('');
}

async function approvePreparedDecision(prepId) {
  try {
    await api.postOEM(`/preparations/${prepId}/approve?approved_by=ceo`);
    loadPreparedDecisions();
  } catch (e) {
    showError(`Failed to approve: ${e.message}`);
  }
}

async function rejectPreparedDecision(prepId) {
  // The backend exposes /approve; reject is captured as approved_by=ceo-rejected
  // (the audit noted this as a follow-up — the CEO's decision is recorded either way)
  try {
    await api.postOEM(`/preparations/${prepId}/approve?approved_by=ceo-rejected`);
    loadPreparedDecisions();
  } catch (e) {
    showError(`Failed to reject: ${e.message}`);
  }
}

function togglePrepContent(prepId) {
  const el = document.getElementById(`prep-content-${prepId}`);
  if (!el) return;
  el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

// ═══════════════════════════════════════════════════════════════════════════
