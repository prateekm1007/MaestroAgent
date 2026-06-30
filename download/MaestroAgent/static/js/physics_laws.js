// PHYSICS (Laws) — with contradiction feedback (optimistic update)
// ═══════════════════════════════════════════════════════════════════════════

async function loadLaws(statusFilter) {
  const el = document.getElementById('physics-laws');
  loadingHTML(el, 'Loading laws…');
  try {
    const path = statusFilter ? '/laws?status=' + statusFilter : '/laws';
    const data = await api.getOEM(path);
    el.innerHTML = data.laws.length === 0
      ? '<div class="empty-state">No laws match this filter.</div>'
      : data.laws.map(l => renderLawCardDetailed(l)).join('');
  } catch (e) {
    errorHTML(el, e.message, 'loadLaws()');
  }
}

function renderLawCardDetailed(l) {
  const statusTag = l.status === 'validated' ? 'tag-cyan' : l.status === 'stressed' ? 'tag-amber' : l.status === 'invalidated' ? 'tag-rose' : l.status === 'unknown_to_leadership' ? 'tag-purple' : 'tag-gray';
  const chain = l.evidence_chain && l.evidence_chain.chain ? l.evidence_chain.chain : [];
  return `<div class="card mb-3 cursor-pointer" data-law-code="${escapeHtml(l.code)}" onclick="openDrilldown('law', '${escapeJs(l.code)}')">
    <div class="flex items-start justify-between mb-2">
      <div class="flex-1">
        <div class="flex items-center gap-2 mb-1">
          <span class="mono text-[10px] text-brand-purple">${escapeHtml(l.code)}</span>
          <span class="tag ${statusTag}">${escapeHtml(l.status)}</span>
          ${l.drift_detected ? '<span class="tag tag-rose">DRIFT</span>' : ''}
        </div>
        <div class="text-sm font-semibold text-white">${escapeHtml(l.statement)}</div>
        <div class="text-[11px] text-fg-400 mt-1"><strong>Condition:</strong> ${escapeHtml(l.condition)}</div>
        <div class="text-[11px] text-fg-300 mt-1"><strong>Outcome:</strong> ${escapeHtml(l.outcome)}</div>
      </div>
    </div>
    <div class="flex items-center gap-3 text-[10px] text-fg-500 mt-3">
      <div class="conf-bar" style="width:140px;"><div class="conf-bar-track"><div class="conf-bar-fill" style="width:${l.confidence*100}%"></div></div><span class="text-brand-cyan font-bold conf-value">${formatConfidence(l.confidence)}</span></div>
      <span>·</span><span>${l.evidence_count} evidence</span>
      <span>·</span><span>${l.validated_runtimes}/${l.validated_runtimes + l.failed_runtimes} runtimes</span>
      ${l.counter_examples ? `<span>·</span><span>${l.counter_examples} counter-examples</span>` : ''}
    </div>
    <div class="grid grid-cols-2 gap-3 mt-3 pt-3 border-t border-white/[0.05]">
      <div>
        <div class="text-[10px] uppercase text-fg-500 mb-1">Providers</div>
        <div class="flex flex-wrap gap-1">${l.providers && l.providers.length ? l.providers.map(p => `<span class="tag tag-gray">${escapeHtml(p)}</span>`).join('') : '<span class="text-[10px] text-fg-600">none</span>'}</div>
      </div>
      <div>
        <div class="text-[10px] uppercase text-fg-500 mb-1">Last Verified</div>
        <div class="text-[11px] text-fg-300">${l.last_validated ? escapeHtml(l.last_validated) : 'never'}</div>
      </div>
    </div>
    ${chain.length > 0 ? `
      <div class="mt-3 pt-3 border-t border-white/[0.05]">
        <div class="text-[10px] uppercase text-fg-500 mb-2">Evidence Chain (${chain.length} nodes)</div>
        <div class="flex flex-wrap gap-1">${chain.slice(0, 12).map(n => `<span class="evidence-node ${n.type}">${escapeHtml(n.label)}</span>`).join('')}</div>
      </div>
    ` : ''}
    <div class="mt-3 pt-3 border-t border-white/[0.05] flex items-center gap-2" onclick="event.stopPropagation()">
      <div class="text-[10px] uppercase text-fg-500 mr-2">Feedback:</div>
      <button class="btn btn-ghost text-[10px]" onclick="event.stopPropagation(); contradictLaw('${escapeJs(l.code)}', 'agree')">Agree</button>
      <button class="btn btn-ghost text-[10px]" onclick="event.stopPropagation(); contradictLaw('${escapeJs(l.code)}', 'reject')">Reject</button>
      <button class="btn btn-ghost text-[10px]" onclick="event.stopPropagation(); contradictLaw('${escapeJs(l.code)}', 'modify')">Modify</button>
      <button class="btn btn-ghost text-[10px]" onclick="event.stopPropagation(); contradictLaw('${escapeJs(l.code)}', 'ignore')">Ignore</button>
    </div>
  </div>`;
}

async function contradictLaw(lawCode, action) {
  // Optimistic update: visually mark the law as "updating"
  const card = document.querySelector(`[data-law-code="${lawCode}"]`);
  if (card) {
    card.style.opacity = '0.6';
    const confEl = card.querySelector('.conf-value');
    if (confEl) confEl.innerHTML = '<span class="spinner"></span>';
  }

  try {
    const resp = await fetch(MAESTRO_API + '/api/oem/contradict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        target_type: 'law',
        target_id: lawCode,
        action: action,
        reasoning: `UI feedback: ${action}`,
      }),
    });
    if (!resp.ok) throw new Error('Contradict failed: ' + resp.status);
    const data = await resp.json();

    // Invalidate cached laws so next nav fetches fresh state
    SWR.invalidatePrefix('oem:/laws');
    SWR.invalidatePrefix('oem:/inbox');
    SWR.invalidatePrefix('oem:/dashboard');

    // Reload physics to show updated confidence
    if (window._currentSurface === 'physics') {
      loadLaws('');
    }
  } catch (e) {
    showError(`Feedback failed for ${lawCode}: ${e.message}`);
    if (card) {
      card.style.opacity = '1';
      const confEl = card.querySelector('.conf-value');
      if (confEl) confEl.textContent = '—';
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// DEBATE
// ═══════════════════════════════════════════════════════════════════════════

async function loadDebate() {
  const el = document.getElementById('debate-laws');
  loadingHTML(el);
  try {
    const data = await api.getOEM('/inbox');
    el.innerHTML = data.dissent.length === 0
      ? '<div class="empty-state">No laws hidden from leadership. All validated laws are known.</div>'
      : data.dissent.map(l => renderLawCardDetailed(l)).join('');
  } catch (e) {
    errorHTML(el, e.message, 'loadDebate()');
  }
}

// ═══════════════════════════════════════════════════════════════════════════