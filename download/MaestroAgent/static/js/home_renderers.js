// ─── Section 8: Execution Replay (historical accuracy + calibration) ──
function renderECCReplay(learning) {
  const el = document.getElementById('ecc-replay');
  const cal = learning.calibration || {};
  const overall = cal.overall || {};
  const accuracy = learning.historical_accuracy || {};
  const evidence = learning.improvement_evidence || {};
  document.getElementById('ecc-replay-count').textContent = `${overall.total_predictions || 0} prediction${(overall.total_predictions || 0) !== 1 ? 's' : ''}`;
  const buckets = cal.buckets || [];
  const trend = accuracy.trend || [];
  el.innerHTML = `
    <div class="space-y-4">
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div class="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <div class="text-[10px] uppercase text-fg-500">Accuracy</div>
          <div class="text-lg font-bold text-brand-cyan mono">${accuracy.accuracy != null ? (accuracy.accuracy * 100).toFixed(1) + '%' : '—'}</div>
          <div class="text-[10px] text-fg-600">${accuracy.resolved || 0} resolved</div>
        </div>
        <div class="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <div class="text-[10px] uppercase text-fg-500">Brier Score</div>
          <div class="text-lg font-bold text-brand-amber mono">${(overall.brier_score || 0).toFixed(4)}</div>
          <div class="text-[10px] text-fg-600">lower = better</div>
        </div>
        <div class="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <div class="text-[10px] uppercase text-fg-500">Calibration Error</div>
          <div class="text-lg font-bold text-brand-violet mono">${(overall.mean_calibration_error || 0).toFixed(4)}</div>
          <div class="text-[10px] text-fg-600">${evidence.is_calibrated ? 'well-calibrated' : 'needs calibration'}</div>
        </div>
        <div class="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <div class="text-[10px] uppercase text-fg-500">Feedback Events</div>
          <div class="text-lg font-bold text-brand-purple mono">${evidence.feedback_count || 0}</div>
          <div class="text-[10px] text-fg-600">CEO agree/reject</div>
        </div>
      </div>
      ${buckets.length > 0 ? `
        <div>
          <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-2">Calibration Diagram (10 buckets)</div>
          <div class="space-y-1">
            ${buckets.map(b => `
              <div class="flex items-center gap-2 text-[10px]">
                <span class="mono text-fg-500 w-16">${(b.expected_rate*100).toFixed(0)}% expected</span>
                <div class="flex-1 h-3 bg-white/[0.04] rounded overflow-hidden relative">
                  <div class="h-full bg-brand-cyan/40" style="width:${b.expected_rate*100}%"></div>
                  <div class="absolute top-0 h-full bg-brand-violet/60" style="width:${b.actual_rate*100}%"></div>
                </div>
                <span class="mono text-fg-400 w-16">${b.actual_rate > 0 ? (b.actual_rate*100).toFixed(0) + '% actual' : '—'}</span>
                <span class="text-fg-600 w-8">${b.predictions}</span>
              </div>`).join('')}
          </div>
          <div class="flex items-center gap-4 mt-2 text-[9px] text-fg-600">
            <span><span class="inline-block w-2 h-2 bg-brand-cyan/40 rounded"></span> Expected</span>
            <span><span class="inline-block w-2 h-2 bg-brand-violet/60 rounded"></span> Actual</span>
          </div>
        </div>
      ` : ''}
      ${trend.length > 0 ? `
        <div>
          <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-2">Accuracy Trend (weekly)</div>
          <div class="flex items-end gap-1 h-12">
            ${trend.map(t => `<div class="flex-1 bg-brand-cyan/40 rounded-t" style="height:${t.accuracy*100}%" title="${t.week}: ${(t.accuracy*100).toFixed(0)}% (${t.predictions} predictions)"></div>`).join('')}
          </div>
        </div>
      ` : ''}
      <div class="pt-3 border-t border-white/[0.05] text-[10px] text-fg-600">
        Drift events: ${evidence.drift_events_detected || 0} · Stale domains: ${evidence.stale_domains || 0} · Decaying patterns: ${evidence.decaying_patterns || 0}
      </div>
    </div>
  `;
}

// ─── Section 9: Executive Autocomplete (live preview) ──
function renderECCAutocomplete() {
  const el = document.getElementById('ecc-autocomplete');
  el.innerHTML = `
    <div class="space-y-3">
      <div class="text-[11px] text-fg-400">Type below to see real-time semantic suggestions from the OEM. Every suggestion includes completion, reason, confidence, evidence, citations, and expected outcome.</div>
      <div class="relative">
        <input type="text" class="ask-input w-full" placeholder="Try: we should, bottleneck, who knows, risk..." id="ecc-ac-input" oninput="onECCAutocompleteInput(this.value)" aria-label="Executive autocomplete">
        <div id="ecc-ac-dropdown" class="exec-autocomplete"></div>
      </div>
      <div id="ecc-ac-results" class="space-y-2"></div>
    </div>
  `;
}

let eccAcAbort = null;
let _eccAcDebounceTimer = null;
let _eccAcSelectedIdx = -1;

function onECCAutocompleteInput(value) {
  // Round 78 Phase 4: debounce + ESC support.
  clearTimeout(_eccAcDebounceTimer);
  _eccAcDebounceTimer = setTimeout(() => _doECCAutocompleteInput(value), 150);
}

async function _doECCAutocompleteInput(value) {
  const dropdown = document.getElementById('ecc-ac-dropdown');
  const resultsEl = document.getElementById('ecc-ac-results');
  const v = value.trim();
  if (!v) { dropdown.classList.remove('active'); resultsEl.innerHTML = ''; return; }
  if (eccAcAbort) eccAcAbort.abort();
  eccAcAbort = new AbortController();
  try {
    const resp = await fetch(MAESTRO_API + '/api/oem/autocomplete?q=' + encodeURIComponent(v) + '&limit=5', {signal: eccAcAbort.signal});
    if (!resp.ok) return;
    const data = await resp.json();
    const suggestions = data.suggestions || [];
    if (suggestions.length === 0) {
      dropdown.classList.remove('active');
      resultsEl.innerHTML = '<div class="empty-state">No matches in OEM for "' + escapeHtml(v) + '"</div>';
      return;
    }
    dropdown.classList.remove('active');
    resultsEl.innerHTML = suggestions.map(s => `
      <div class="card mb-2 cursor-pointer" role="button" tabindex="0" onclick="openDrilldown('${s.source_type.split(':')[0]}', '${escapeJs(s.source_id)}')">
        <div class="text-sm font-semibold text-white">${escapeHtml(s.completion)}</div>
        <div class="text-[10px] text-fg-400 mt-1">${escapeHtml(s.reason)}</div>
        <div class="flex items-center gap-2 mt-2 text-[10px] text-fg-500 flex-wrap">
          <span class="mono text-brand-purple">[${escapeHtml(s.source_type)}]</span>
          <span class="text-brand-cyan">conf ${(s.confidence*100).toFixed(0)}%</span>
          <span>·</span><span>rank ${(s.rank_score*100).toFixed(0)}%</span>
          <span>·</span><span>${s.evidence.length} evidence</span>
          <span>·</span><span>${s.citations.length} citations</span>
        </div>
        ${s.expected_outcome ? `<div class="text-[10px] text-fg-600 mt-1 italic">→ ${escapeHtml(s.expected_outcome.substring(0, 100))}</div>` : ''}
        <div class="text-[10px] text-brand-violet mt-1">Click for full drill-down →</div>
      </div>
    `).join('');
  } catch(e) { if (e.name !== 'AbortError') {} }
}

function renderRecCard(r) {
  const urgencyTag = r.urgency === 'urgent' ? 'tag-rose' : r.urgency === 'normal' ? 'tag-amber' : 'tag-gray';
  const provChain = (r.provenance || []).slice(0, 3).map(p => {
    const key = p.oem_change || p.gate || p.entity || p.domain || 'evidence';
    return `<span class="prov-node">${escapeHtml(key)}</span>`;
  }).join('<span class="prov-arrow">→</span>');
  return `<div class="card ${r.urgency === 'urgent' ? 'urgent' : ''} mb-3 cursor-pointer" role="button" tabindex="0" onclick="openDrilldown('recommendation', '${escapeJs(r.title)}')">
    <div class="flex items-start justify-between mb-2">
      <div class="flex-1">
        <div class="text-sm font-semibold text-white mb-1">${escapeHtml(humanize(r.title))}</div>
        <div class="text-[11px] text-fg-400 leading-relaxed">${escapeHtml(humanize(r.description))}</div>
      </div>
      <span class="tag ${urgencyTag} ml-3">${escapeHtml(r.urgency)}</span>
    </div>
    ${provChain ? `<div class="prov-chain mt-2 mb-2">${provChain}</div>` : ''}
    <div class="flex items-center gap-3 text-[10px] text-fg-500 mt-2">
      <div class="conf-bar" style="width:120px;"><div class="conf-bar-track"><div class="conf-bar-fill" style="width:${r.confidence*100}%"></div></div><span class="text-brand-cyan font-bold">${formatConfidenceWithWhy(r.confidence, { entity: 'recommendation', title: r.title })}</span></div>
      <span>·</span>
      <span>${r.evidence_count || 0} evidence</span>
      ${r.linked_laws && r.linked_laws.length ? `<span>·</span><span>Laws: ${r.linked_laws.join(', ')}</span>` : ''}
    </div>
    <div class="mt-2 text-[11px] text-fg-300">${escapeHtml(humanize(r.impact))}</div>
  </div>`;
}

// ═══════════════════════════════════════════════════════════════════════════
// INBOX
// ═══════════════════════════════════════════════════════════════════════════

async function loadInbox() {
  const owedEl = document.getElementById('inbox-owed');
  const driftEl = document.getElementById('inbox-drift');
  const dissentEl = document.getElementById('inbox-dissent');
  const summaryEl = document.getElementById('inbox-summary');

  loadingHTML(owedEl); loadingHTML(driftEl); loadingHTML(dissentEl);
  summaryEl.textContent = 'Loading…';

  try {
    const data = await api.getOEM('/inbox');
    const c = data.counts;
    summaryEl.textContent = `${c.owed} decisions you owe · ${c.drift} showing drift · ${c.dissent} unknown to leadership`;

    owedEl.innerHTML = c.owed === 0
      ? '<div class="empty-state">No urgent decisions owed.</div>'
      : data.decisions_owed.map(r => renderRecCard(r)).join('');

    driftEl.innerHTML = c.drift === 0
      ? '<div class="empty-state">No drift detected. All laws are stable.</div>'
      : data.drift.map(l => renderLawCard(l)).join('');

    dissentEl.innerHTML = c.dissent === 0
      ? '<div class="empty-state">No hidden disagreements. All validated laws are known to leadership.</div>'
      : data.dissent.map(l => renderLawCard(l)).join('');
  } catch (e) {
    errorHTML(owedEl, e.message, 'loadInbox()');
    errorHTML(driftEl, e.message, 'loadInbox()');
    errorHTML(dissentEl, e.message, 'loadInbox()');
    summaryEl.textContent = 'Failed to load inbox.';
    showError('Inbox load failed: ' + e.message);
  }
}

function renderLawCard(l) {
  const statusTag = l.status === 'validated' ? 'tag-cyan' : l.status === 'stressed' ? 'tag-amber' : l.status === 'invalidated' ? 'tag-rose' : l.status === 'unknown_to_leadership' ? 'tag-purple' : 'tag-gray';
  return `<div class="card mb-3 cursor-pointer" role="button" tabindex="0" onclick="openDrilldown('law', '${escapeJs(l.code)}')">
    <div class="flex items-start justify-between mb-2">
      <div class="flex-1">
        <div class="flex items-center gap-2 mb-1">
          <span class="mono text-[10px] text-brand-purple">${escapeHtml(l.code)}</span>
          <span class="tag ${statusTag}">${escapeHtml(l.status)}</span>
        </div>
        <div class="text-sm font-semibold text-white">${escapeHtml(humanize(l.statement))}</div>
        <div class="text-[11px] text-fg-400 mt-1">If: ${escapeHtml(humanize(l.condition))}</div>
        <div class="text-[11px] text-fg-300 mt-1">Then: ${escapeHtml(humanize(l.outcome))}</div>
      </div>
    </div>
    <div class="flex items-center gap-3 text-[10px] text-fg-500 mt-2">
      <div class="conf-bar" style="width:120px;"><div class="conf-bar-track"><div class="conf-bar-fill" style="width:${l.confidence*100}%"></div></div><span class="text-brand-cyan font-bold">${formatConfidenceWithWhy(l.confidence, { entity: 'law', title: l.statement })}</span></div>
      <span>·</span>
      <span>${l.evidence_count} evidence</span>
      <span>·</span>
      <span>${l.validated_runtimes}/${l.validated_runtimes + l.failed_runtimes} runtimes</span>
      ${l.providers && l.providers.length ? `<span>·</span><span>${l.providers.join(', ')}</span>` : ''}
    </div>
    ${l.last_validated ? `<div class="mt-2 text-[10px] text-fg-500">Last verified: ${escapeHtml(l.last_validated)}</div>` : ''}
  </div>`;
}

// ═══════════════════════════════════════════════════════════════════════════
// SIMULATOR
// ═══════════════════════════════════════════════════════════════════════════

let simulatorAbort = null;

async function loadSimulator() {
  const el = document.getElementById('simulator-scenario');
  loadingHTML(el, 'Loading scenario…');
  try {
    const data = await api.getOEM('/simulator');
    const s = data.scenario;
    el.innerHTML = `
      <div class="space-y-3">
        <div>
          <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-1">Scenario</div>
          <div class="text-sm font-semibold text-white">${escapeHtml(humanize(s.title))}</div>
          <div class="text-[11px] text-fg-400 mt-1">${escapeHtml(humanize(s.description))}</div>
        </div>
        <div class="grid grid-cols-2 gap-4 pt-3 border-t border-white/[0.05]">
          <div>
            <div class="text-[10px] uppercase text-fg-500">Recommendation</div>
            <div class="text-sm text-brand-cyan mt-1">${escapeHtml(humanize(s.recommendation))}</div>
          </div>
          <div>
            <div class="text-[10px] uppercase text-fg-500">Confidence</div>
            <div class="conf-bar mt-1"><div class="conf-bar-track"><div class="conf-bar-fill" style="width:${s.confidence*100}%"></div></div><span class="text-brand-cyan font-bold">${formatConfidence(s.confidence)}</span></div>
          </div>
        </div>
        <div class="pt-3 border-t border-white/[0.05]">
          <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-1">Decision Question</div>
          <div class="text-[11px] text-fg-300">${escapeHtml(s.decision_question)}</div>
        </div>
        <div class="pt-3 border-t border-white/[0.05]">
          <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-1">Current Health</div>
          <div class="grid grid-cols-2 gap-2 text-[11px]">
            <div>P1 Cluster Risk: <span class="mono text-brand-amber">${formatConfidence(data.current_health.p1_cluster_risk)}</span></div>
            <div>Incident Rate: <span class="mono text-brand-amber">${data.current_health.incident_rate}</span></div>
            <div>Decision Velocity: <span class="mono text-brand-cyan">${data.current_health.decision_velocity_days.toFixed(1)}d</span></div>
            <div>Release Frequency: <span class="mono text-brand-cyan">${data.current_health.release_frequency.toFixed(1)}/wk</span></div>
          </div>
        </div>
      </div>
    `;
  } catch (e) {
    errorHTML(el, e.message, 'loadSimulator()');
  }
}

async function runSimulator() {
  const hires = parseInt(document.getElementById('sim-hires').value);
  const panel = document.getElementById('simulator-result-panel');
  const result = document.getElementById('simulator-result');
  panel.style.display = 'block';
  loadingHTML(result, 'Running simulation…');

  if (simulatorAbort) simulatorAbort.abort();
  simulatorAbort = new AbortController();

  try {
    const resp = await fetch(MAESTRO_API + '/api/oem/simulator', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({inputs: {hire_count: hires}}),
      signal: simulatorAbort.signal,
    });
    if (!resp.ok) throw new Error('Simulator returned ' + resp.status);
    const data = await resp.json();
    const p = data.predicted;
    result.innerHTML = `
      <div class="space-y-3">
        <div class="grid grid-cols-2 gap-4">
          <div>
            <div class="text-[10px] uppercase text-fg-500">Predicted P1 Risk</div>
            <div class="text-xl font-bold text-brand-amber mono">${formatConfidence(p.p1_cluster_risk)}</div>
            <div class="text-[10px] text-fg-500">Base: ${formatConfidence(data.base_health.p1_cluster_risk)}</div>
          </div>
          <div>
            <div class="text-[10px] uppercase text-fg-500">Confidence</div>
            <div class="conf-bar mt-1"><div class="conf-bar-track"><div class="conf-bar-fill" style="width:${data.confidence*100}%"></div></div><span class="text-brand-cyan font-bold">${formatConfidence(data.confidence)}</span></div>
          </div>
        </div>
        ${data.linked_laws && data.linked_laws.length ? `<div class="pt-3 border-t border-white/[0.05]"><div class="text-[10px] uppercase text-fg-500 mb-1">Linked Laws</div><div class="flex flex-wrap gap-1">${data.linked_laws.map(l => `<span class="prov-node">${escapeHtml(l)}</span>`).join('')}</div></div>` : ''}
      </div>
    `;
  } catch (e) {
    if (e.name === 'AbortError') return;
    errorHTML(result, e.message, 'runSimulator()');
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// HAYEK
// ═══════════════════════════════════════════════════════════════════════════

async function loadHayek() {
  const risksEl = document.getElementById('hayek-risks');
  const knowEl = document.getElementById('hayek-knowledge');
  loadingHTML(risksEl); loadingHTML(knowEl);
  try {
    const data = await api.getOEM('/knowledge');
    risksEl.innerHTML = data.concentration_risks.length === 0
      ? '<div class="empty-state">No concentration risks detected.</div>'
      : data.concentration_risks.map(r => `
        <div class="card mb-2 cursor-pointer hover:bg-white/[0.02]" role="button" tabindex="0" onclick="openDrilldown('risk', '${escapeJs(r.domain)}')">
          <div class="text-sm font-semibold text-white">${escapeHtml(r.domain)}</div>
          <div class="text-[11px] text-fg-400 mt-1">Influence concentration: <span class="mono text-brand-rose">${r.score.toFixed(2)}</span></div>
          <div class="conf-bar mt-2"><div class="conf-bar-track"><div class="conf-bar-fill" style="width:${Math.min(r.score*10,100)}%;background:#ff5577;"></div></div></div>
        </div>
      `).join('');
    knowEl.innerHTML = data.hidden_experts.length === 0
      ? '<div class="empty-state">No hidden experts detected.</div>'
      : data.hidden_experts.map(e => `
        <div class="card mb-2 cursor-pointer hover:bg-white/[0.02]" role="button" tabindex="0" onclick="openDrilldown('expert', '${escapeJs(e.entity)}')">
          <div class="text-sm font-semibold text-white">${escapeHtml(e.entity)}</div>
          <div class="text-[11px] text-fg-400 mt-1">Influence: <span class="mono text-brand-purple">${e.influence.toFixed(2)}</span> · ${e.domains ? e.domains.length : 0} domains</div>
          ${e.domains && e.domains.length ? `<div class="mt-2 flex flex-wrap gap-1">${e.domains.map(d => `<span class="tag tag-gray">${escapeHtml(d)}</span>`).join('')}</div>` : ''}
        </div>
      `).join('');
  } catch (e) {
    errorHTML(risksEl, e.message, 'loadHayek()');
    errorHTML(knowEl, e.message, 'loadHayek()');
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// KNOWLEDGE FLOW
// ═══════════════════════════════════════════════════════════════════════════

async function loadKnowledge() {
  const expertsEl = document.getElementById('flow-experts');
  const deathEl = document.getElementById('flow-death');
  const dupEl = document.getElementById('flow-duplicates');
  loadingHTML(expertsEl); loadingHTML(deathEl); loadingHTML(dupEl);
  try {
    const data = await api.getOEM('/knowledge');
    expertsEl.innerHTML = data.hidden_experts.length === 0
      ? '<div class="empty-state">No hidden experts detected.</div>'
      : data.hidden_experts.map(e => `
        <div class="card mb-2 cursor-pointer hover:bg-white/[0.02]" role="button" tabindex="0" onclick="openDrilldown('expert', '${escapeJs(e.entity)}')">
          <div class="text-sm font-semibold text-white">${escapeHtml(e.entity)}</div>
          <div class="text-[11px] text-fg-400 mt-1">Influence ${e.influence.toFixed(2)} · ${e.domains ? e.domains.length : 0} domains</div>
        </div>
      `).join('');
    deathEl.innerHTML = data.knowledge_death.length === 0
      ? '<div class="empty-state">No knowledge death detected.</div>'
      : data.knowledge_death.map(k => `
        <div class="card mb-2 cursor-pointer hover:bg-white/[0.02]" role="button" tabindex="0" onclick="openDrilldown('pattern', '${escapeJs(k.title || k.description || 'knowledge_death')}')">
          <div class="text-sm font-semibold text-white">${escapeHtml(humanize(k.title))}</div>
          <div class="text-[11px] text-fg-400 mt-1">${escapeHtml(humanize(k.description))}</div>
          <div class="text-[10px] text-fg-500 mt-1">Boundary: ${escapeHtml(k.boundary)} · Confidence ${formatConfidence(k.confidence)}</div>
        </div>
      `).join('');
    dupEl.innerHTML = data.duplicate_work.length === 0
      ? '<div class="empty-state">No duplicate work detected.</div>'
      : data.duplicate_work.map(d => `
        <div class="card mb-2 cursor-pointer hover:bg-white/[0.02]" role="button" tabindex="0" onclick="openDrilldown('pattern', '${escapeJs(d.title || d.description || 'duplicate_work')}')">
          <div class="text-sm font-semibold text-white">${escapeHtml(humanize(d.title))}</div>
          <div class="text-[11px] text-fg-400 mt-1">${escapeHtml(humanize(d.description))}</div>
          <div class="text-[10px] text-fg-500 mt-1">Domain: ${escapeHtml(d.domain)} · ${d.providers.join(', ')}</div>
        </div>
      `).join('');
  } catch (e) {
    errorHTML(expertsEl, e.message, 'loadKnowledge()');
    errorHTML(deathEl, e.message, 'loadKnowledge()');
    errorHTML(dupEl, e.message, 'loadKnowledge()');
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// MEMORY
// ═══════════════════════════════════════════════════════════════════════════

async function loadMemory() {
  const el = document.getElementById('memory-laws');
  loadingHTML(el);
  try {
    const data = await api.getOEM('/laws');
    el.innerHTML = data.laws.length === 0
      ? '<div class="empty-state">No laws inferred yet.</div>'
      : data.laws.map(l => renderLawCard(l)).join('');
  } catch (e) {
    errorHTML(el, e.message, 'loadMemory()');
  }
}

// ═══════════════════════════════════════════════════════════════════════════

// Round 78 Phase 6: keyboard accessibility for div-as-button elements.
// Any element with role="button" and tabindex="0" should activate on
// Enter or Space — this is the WAI-ARIA pattern for interactive divs.
document.addEventListener('keydown', function(e) {
  if (e.target && e.target.getAttribute && e.target.getAttribute('role') === 'button') {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      e.target.click();
    }
  }
});
