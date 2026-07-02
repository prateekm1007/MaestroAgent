// HOME — Executive Cognition Center (9 sections, all from OEM)
// ═══════════════════════════════════════════════════════════════════════════

async function loadDashboard() {
  const stateEl = document.getElementById('home-oem-state');
  const providersBadge = document.getElementById('oem-providers-badge');

  // ── Ambient layers: Pulse, Narrative, Feed, Cognitive Load ──
  loadPulse();
  loadNarrative();
  loadFeed();
  loadCognitiveLoad();

  // ── Cognitive-model surface: Prepared Decisions (renders into #ecc-prepared) ──
  // Sits ABOVE Today's Attention. Calls /api/oem/preparations directly.
  loadPreparedDecisions();

  // OEM State (reference) — fetch independently (fast)
  api.getOEM('/dashboard').then(data => {
    const m = data.metrics;
    stateEl.innerHTML = `
      <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
        <div class="metric metric-clickable" onclick="openDrilldown('metric', 'signals_processed')"><div class="metric-value">${m.signals_processed}</div><div class="metric-label">Signals</div></div>
        <div class="metric metric-clickable" onclick="openDrilldown('metric', 'learning_objects')"><div class="metric-value">${m.learning_objects}</div><div class="metric-label">Learning Objects</div></div>
        <div class="metric metric-clickable" onclick="openDrilldown('metric', 'laws_inferred')"><div class="metric-value">${m.laws_inferred}</div><div class="metric-label">Laws</div></div>
        <div class="metric metric-clickable" onclick="openDrilldown('metric', 'validated_laws')"><div class="metric-value">${m.validated_laws}</div><div class="metric-label">Validated</div></div>
        <div class="metric metric-clickable" onclick="openDrilldown('metric', 'recommendations_active')"><div class="metric-value">${m.recommendations_active}</div><div class="metric-label">Recommendations</div></div>
        <div class="metric metric-clickable" onclick="openDrilldown('metric', 'p1_cluster_risk')"><div class="metric-value">${formatConfidence(m.p1_cluster_risk)}</div><div class="metric-label">P1 Risk</div></div>
      </div>
      <div class="mt-4 pt-4 border-t border-white/[0.05] flex flex-wrap gap-2">
        ${data.providers_connected.map(p => `<span class="tag tag-cyan">${escapeHtml(p)}</span>`).join('')}
      </div>
    `;
    providersBadge.textContent = data.providers_connected.length + ' providers';
    document.getElementById('oem-status').innerHTML = `<span class="text-brand-cyan">●</span> <span>OEM connected · ${m.signals_processed} signals · ${m.laws_inferred} laws</span>`;
    document.getElementById('oem-status-badge').textContent = 'OEM ONLINE';
    document.getElementById('oem-status-badge').className = 'text-[10px] font-semibold text-brand-cyan';
  }).catch(e => {
    errorHTML(stateEl, 'Failed to load OEM state: ' + e.message, 'loadDashboard()');
    document.getElementById('oem-status').innerHTML = `<span class="text-brand-rose">●</span> <span>OEM unreachable: ${escapeHtml(e.message)}</span>`;
    document.getElementById('oem-status-badge').textContent = 'OEM OFFLINE';
    document.getElementById('oem-status-badge').className = 'text-[10px] font-semibold text-brand-rose';
  });

  // CEO Briefing — powers sections 1 + 2
  try {
    const briefing = await api.getOEM('/ceo-briefing');
    const tsEl = document.getElementById('home-briefing-timestamp');
    if (tsEl && briefing.generated_at) tsEl.textContent = `Last updated: ${formatTimestamp(briefing.generated_at)}`;

    // ── Section 1: Today's Attention (one thing + CEO-only decisions) ──
    renderECCAttention(briefing);

    // ── Section 2: What Changed Overnight ──
    renderECCOvernight(briefing);
  } catch (e) {
    document.getElementById('ecc-attention').innerHTML = `<div class="error-state">Failed: ${escapeHtml(e.message)} <button onclick="loadDashboard()" class="btn btn-ghost text-[10px] ml-2">Retry</button></div>`;
    document.getElementById('ecc-overnight').innerHTML = `<div class="error-state">Failed: ${escapeHtml(e.message)}</div>`;
  }

  // ── Section 3: Hayek Lens ──
  try {
    const knowledge = await api.getOEM('/knowledge');
    renderECCHayek(knowledge);
  } catch (e) {
    document.getElementById('ecc-hayek').innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`;
  }

  // ── Section 4: Knowledge Flow ──
  try {
    const knowledge = SWR.get('oem:/knowledge') || await api.getOEM('/knowledge');
    renderECCFlow(knowledge);
  } catch (e) {
    document.getElementById('ecc-flow').innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`;
  }

  // ── Section 5: Hidden Experts ──
  try {
    const knowledge = SWR.get('oem:/knowledge') || await api.getOEM('/knowledge');
    renderECCExperts(knowledge);
  } catch (e) {
    document.getElementById('ecc-experts').innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`;
  }

  // ── Section 6: Decision Simulator ──
  try {
    const sim = await api.getOEM('/simulator');
    renderECCSimulator(sim);
  } catch (e) {
    document.getElementById('ecc-simulator').innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`;
  }

  // ── Section 7: Ask the Organization ──
  renderECCAsk();

  // ── Section 8: Execution Replay ──
  try {
    const learning = await api.getOEM('/learning');
    renderECCReplay(learning);
  } catch (e) {
    document.getElementById('ecc-replay').innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`;
  }

  // ── Section 9: Executive Autocomplete ──
  renderECCAutocomplete();

  // ── Section 10: Digital Twin ──
  try {
    const twinState = await api.getOEM('/twin/state');
    renderECCTwin(twinState);
  } catch (e) {
    document.getElementById('ecc-twin').innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`;
  }
}

// ─── Enriched Recommendation Card (evidence, confidence, provenance, impact, accuracy, drill-down) ──
function renderEnrichedRec(r, opts = {}) {
  const urgencyTag = r.urgency === 'urgent' ? 'tag-rose' : r.urgency === 'normal' ? 'tag-amber' : 'tag-gray';
  const provChain = (r.provenance || []).slice(0, 3).map(p => {
    const key = p.oem_change || p.gate || p.entity || p.domain || 'evidence';
    return `<span class="prov-node">${escapeHtml(key)}</span>`;
  }).join('<span class="prov-arrow">→</span>');
  const evidenceCount = r.evidence_count || (r.provenance || []).length || 0;
  const linkedLaws = r.linked_laws || [];
  const compact = opts.compact;
  return `<div class="card ${r.urgency === 'urgent' ? 'urgent' : ''} mb-3 cursor-pointer" onclick="openDrilldown('recommendation', '${escapeJs(r.title)}')">
    <div class="flex items-start justify-between mb-2">
      <div class="flex-1">
        <div class="text-sm font-semibold text-white mb-1">${escapeHtml(humanize(r.title))}</div>
        ${!compact ? `<div class="text-[11px] text-fg-400 leading-relaxed">${escapeHtml(humanize(r.description || ''))}</div>` : ''}
      </div>
      <span class="tag ${urgencyTag} ml-3">${escapeHtml(r.urgency || 'normal')}</span>
    </div>
    ${provChain ? `<div class="prov-chain mt-2 mb-2">${provChain}</div>` : ''}
    <div class="flex items-center gap-3 text-[10px] text-fg-500 mt-2 flex-wrap">
      <span>${evidenceCount} signals</span>
      ${linkedLaws.length ? `<span>·</span><span>${linkedLaws.length} ${linkedLaws.length === 1 ? 'pattern' : 'patterns'}</span>` : ''}
    </div>
    ${!compact && r.impact ? `<div class="mt-2 text-[11px] text-fg-300"><strong>Expected impact:</strong> ${escapeHtml(humanize(r.impact))}</div>` : ''}
    ${!compact ? `<div class="mt-2 pt-2 border-t border-white/[0.05] flex items-center gap-3 text-[10px] text-fg-600">
      <span>Based on ${evidenceCount} signals</span>
      ${r.evidence_strength ? `<span>·</span><span>Strength: ${r.evidence_strength}</span>` : ''}
      <span>·</span>
      <span class="text-brand-violet cursor-pointer hover:text-brand-cyan">Drill-down →</span>
    </div>` : ''}
  </div>`;
}

// ─── Section 1: Today's Attention ──
function renderECCAttention(briefing) {
  const el = document.getElementById('ecc-attention');
  const ot = briefing.one_thing;
  const decisions = briefing.decisions;
  document.getElementById('ecc-attention-count').textContent = `${decisions.decisions.length} decision${decisions.decisions.length !== 1 ? 's' : ''}`;
  const urgencyColor = ot.urgency === 'urgent' ? 'rose' : ot.urgency === 'normal' ? 'amber' : 'gray';
  el.innerHTML = `
    <div class="space-y-4">
      <div class="p-3 rounded-lg bg-brand-violet/[0.06] border border-brand-violet/15">
        <div class="text-[10px] uppercase tracking-wider text-brand-violet font-semibold mb-1">If you do one thing today</div>
        <div class="text-base font-bold text-white">${escapeHtml(humanize(ot.title))}</div>
        <div class="text-[11px] text-fg-400 mt-1">${escapeHtml(humanize(ot.why))}</div>
        <div class="text-sm text-brand-violet font-medium mt-2">${escapeHtml(humanize(ot.recommendation))}</div>
        <div class="flex items-center gap-3 pt-2">
          <span class="tag tag-${urgencyColor}">${escapeHtml(ot.urgency)}</span>
        </div>
        <div class="text-[11px] text-fg-300 mt-2">${escapeHtml(humanize(ot.impact))}</div>
        ${ot.rec_id ? `<button class="btn btn-primary text-[11px] mt-2" onclick="event.stopPropagation(); openDrilldown('recommendation', '${escapeJs(ot.title)}')">Investigate →</button>` : ''}
      </div>
      ${decisions.decisions.length > 0 ? `
        <div>
          <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-2">CEO-only decisions</div>
          <div class="space-y-2">
            ${decisions.decisions.map(d => {
              const drillType = d.type === 'urgent_decision' ? 'recommendation' : d.type === 'retention' ? 'pattern' : 'law';
              const drillId = d.linked_laws && d.linked_laws.length ? d.linked_laws[0] : d.title;
              return `<div class="flex items-start gap-3 p-3 rounded-lg bg-brand-purple/[0.04] border border-brand-purple/10 cursor-pointer hover:bg-brand-purple/[0.08] transition-colors" onclick="openDrilldown('${drillType}', '${escapeJs(drillId)}')">
                <div class="w-7 h-7 rounded-md bg-brand-purple/15 flex items-center justify-center flex-shrink-0"><span class="text-brand-purple text-sm font-bold">!</span></div>
                <div class="flex-1">
                  <div class="text-[12px] font-semibold text-fg-100">${escapeHtml(d.title)}</div>
                  <div class="text-[10px] text-fg-500 mt-0.5">${escapeHtml(d.question)}</div>
                  <div class="text-[10px] text-brand-violet mt-1">${escapeHtml(d.recommendation)}</div>
                </div>
                <span class="text-[10px] text-fg-500">${d.evidence_count || 0} signals</span>
              </div>`;
            }).join('')}
          </div>
        </div>
      ` : ''}
    </div>
  `;
}

// ─── Section 2: What Changed Overnight ──
function renderECCOvernight(briefing) {
  const el = document.getElementById('ecc-overnight');
  const ov = briefing.overnight;
  document.getElementById('ecc-overnight-count').textContent = ov.summary;
  if (!ov.changes || ov.changes.length === 0) {
    emptyHTML(el, 'Nothing new. The org is stable. The OEM will surface new patterns as signals flow.');
    return;
  }
  el.innerHTML = `
    <div class="mb-3 p-3 rounded-lg bg-brand-cyan/[0.04] border border-brand-cyan/10">
      <div class="text-sm font-semibold text-white">${escapeHtml(ov.headline)}</div>
      <div class="text-[11px] text-fg-500 mt-1">${escapeHtml(ov.headline_detail)}</div>
    </div>
    <div class="space-y-2">
      ${ov.changes.map(c => {
        const sevColor = c.severity === 'urgent' ? 'rose' : c.severity === 'warning' ? 'amber' : 'cyan';
        const drillType = c.type === 'hidden_expert' ? 'expert' : c.type === 'bottleneck' ? 'pattern' : c.type === 'concentration_risk' ? 'risk' : 'pattern';
        const drillId = c.entity || c.domain || c.title || c.detail;
        return `<div class="flex items-start gap-3 p-3 rounded-lg bg-brand-${sevColor}/[0.04] border border-brand-${sevColor}/10 cursor-pointer hover:bg-brand-${sevColor}/[0.08] transition-colors" onclick="openDrilldown('${drillType}', '${escapeJs(drillId)}')">
          <div class="w-7 h-7 rounded-md bg-brand-${sevColor}/15 flex items-center justify-center flex-shrink-0"><span class="text-brand-${sevColor} text-sm font-bold">${c.type === 'hidden_expert' ? '?' : c.type === 'bottleneck' ? '!' : c.type === 'departure_risk' ? 'x' : 'v'}</span></div>
          <div class="flex-1"><div class="text-[12px] font-semibold text-fg-100">${escapeHtml(c.title)}</div><div class="text-[10px] text-fg-500 mt-0.5">${escapeHtml(c.detail)}</div></div>
          <span class="tag tag-${sevColor}">${escapeHtml(c.severity)}</span>
        </div>`;
      }).join('')}
    </div>
  `;
}

// ─── Section 3: Hayek Lens ──
function renderECCHayek(knowledge) {
  const el = document.getElementById('ecc-hayek');
  const risks = knowledge.concentration_risks || [];
  document.getElementById('ecc-hayek-count').textContent = `${risks.length} risk${risks.length !== 1 ? 's' : ''}`;
  if (risks.length === 0) { emptyHTML(el, 'No concentration risks detected.'); return; }
  el.innerHTML = `<div class="space-y-2">${risks.map(r => `
    <div class="card mb-2 cursor-pointer hover:bg-white/[0.02]" onclick="openDrilldown('risk', '${escapeJs(r.domain)}')">
      <div class="text-sm font-semibold text-white">${escapeHtml(r.domain)}</div>
      <div class="text-[11px] text-fg-400 mt-1">Concentration: <span class="mono text-brand-rose">${r.score.toFixed(2)}</span></div>
      <div class="conf-bar mt-2"><div class="conf-bar-track"><div class="conf-bar-fill" class="auto-wmathminrscore10100p-bg-58b7"></div></div></div>
      <div class="text-[10px] text-fg-600 mt-1">Click for evidence, people, prediction →</div>
    </div>`).join('')}</div>`;
}

// ─── Section 4: Knowledge Flow ──
function renderECCFlow(knowledge) {
  const el = document.getElementById('ecc-flow');
  const dups = knowledge.duplicate_work || [];
  const deaths = knowledge.knowledge_death || [];
  document.getElementById('ecc-flow-count').textContent = `${dups.length + deaths.length} issue${(dups.length + deaths.length) !== 1 ? 's' : ''}`;
  if (dups.length === 0 && deaths.length === 0) { emptyHTML(el, 'No duplicate work or knowledge death detected.'); return; }
  el.innerHTML = `
    ${dups.length > 0 ? `<div class="mb-3"><div class="text-[10px] uppercase text-fg-500 mb-2">Duplicate Work (${dups.length})</div>${dups.map(d => `
      <div class="card mb-2 cursor-pointer hover:bg-white/[0.02]" onclick="openDrilldown('pattern', '${escapeJs(d.title || d.description)}')">
        <div class="text-sm font-semibold text-white">${escapeHtml(d.title)}</div>
        <div class="text-[11px] text-fg-400 mt-1">${escapeHtml(d.description)}</div>
        <div class="text-[10px] text-fg-600 mt-1">Domain: ${escapeHtml(d.domain)} · ${d.providers.join(', ')}</div>
      </div>`).join('')}</div>` : ''}
    ${deaths.length > 0 ? `<div><div class="text-[10px] uppercase text-fg-500 mb-2">Knowledge Death (${deaths.length})</div>${deaths.map(k => `
      <div class="card mb-2 cursor-pointer hover:bg-white/[0.02]" onclick="openDrilldown('pattern', '${escapeJs(k.title || k.description)}')">
        <div class="text-sm font-semibold text-white">${escapeHtml(k.title)}</div>
        <div class="text-[11px] text-fg-400 mt-1">${escapeHtml(k.description)}</div>
        <div class="text-[10px] text-fg-600 mt-1">Boundary: ${escapeHtml(k.boundary)} · conf ${formatConfidence(k.confidence)}</div>
      </div>`).join('')}</div>` : ''}
  `;
}

// ─── Section 5: Hidden Experts ──
function renderECCExperts(knowledge) {
  const el = document.getElementById('ecc-experts');
  const experts = knowledge.hidden_experts || [];
  document.getElementById('ecc-experts-count').textContent = `${experts.length} expert${experts.length !== 1 ? 's' : ''}`;
  if (experts.length === 0) { emptyHTML(el, 'No hidden experts detected.'); return; }
  el.innerHTML = `<div class="space-y-2">${experts.map(e => `
    <div class="card mb-2 cursor-pointer hover:bg-white/[0.02]" onclick="openDrilldown('expert', '${escapeJs(e.entity)}')">
      <div class="flex items-center gap-3">
        <div class="w-8 h-8 rounded-full bg-brand-purple/20 flex items-center justify-center text-xs font-bold text-brand-purple">${escapeHtml(e.entity.charAt(0).toUpperCase())}</div>
        <div class="flex-1">
          <div class="text-sm font-semibold text-white">${escapeHtml(e.entity)}</div>
          <div class="text-[11px] text-fg-400">Influence: <span class="mono text-brand-purple">${e.influence.toFixed(2)}</span> · ${e.domains ? e.domains.length : 0} domains</div>
        </div>
        ${e.domains && e.domains.length ? `<div class="flex flex-wrap gap-1">${e.domains.map(d => `<span class="tag tag-gray">${escapeHtml(d)}</span>`).join('')}</div>` : ''}
      </div>
      <div class="text-[10px] text-fg-600 mt-1">Click for evidence, timeline, prediction →</div>
    </div>`).join('')}</div>`;
}

// ─── Section 6: Decision Simulator ──
function renderECCSimulator(sim) {
  const el = document.getElementById('ecc-simulator');
  const s = sim.scenario;
  el.innerHTML = `
    <div class="space-y-3">
      <div>
        <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-1">Current Scenario</div>
        <div class="text-sm font-semibold text-white">${escapeHtml(s.title)}</div>
        <div class="text-[11px] text-fg-400 mt-1">${escapeHtml(s.description)}</div>
      </div>
      <div class="grid grid-cols-2 gap-4 pt-3 border-t border-white/[0.05]">
        <div><div class="text-[10px] uppercase text-fg-500">Recommendation</div><div class="text-sm text-brand-cyan mt-1">${escapeHtml(s.recommendation)}</div></div>
        <div><div class="text-[10px] uppercase text-fg-500">Confidence</div><div class="conf-bar mt-1"><div class="conf-bar-track"><div class="conf-bar-fill" class="auto-wsconfidence100p"></div></div><span class="text-brand-cyan font-bold">${formatConfidence(s.confidence)}</span></div></div>
      </div>
      <div class="pt-3 border-t border-white/[0.05]">
        <div class="text-[10px] uppercase text-fg-500 font-semibold mb-1">Current Health</div>
        <div class="grid grid-cols-2 gap-2 text-[11px]">
          <div>P1 Risk: <span class="mono text-brand-amber">${formatConfidence(sim.current_health.p1_cluster_risk)}</span></div>
          <div>Incident Rate: <span class="mono text-brand-amber">${sim.current_health.incident_rate}</span></div>
          <div>Decision Velocity: <span class="mono text-brand-cyan">${sim.current_health.decision_velocity_days.toFixed(1)}d</span></div>
          <div>Release Frequency: <span class="mono text-brand-cyan">${sim.current_health.release_frequency.toFixed(1)}/wk</span></div>
        </div>
      </div>
      <div class="pt-3 border-t border-white/[0.05]">
        <div class="text-[10px] uppercase text-fg-500 font-semibold mb-1">Run What-If</div>
        <div class="flex items-center gap-3">
          <label class="text-[11px] text-fg-400">Hire count:</label>
          <input type="range" min="0" max="10" value="2" id="ecc-sim-hires" class="flex-1" oninput="document.getElementById('ecc-sim-val').textContent=this.value">
          <span class="text-xs font-bold text-brand-cyan mono" id="ecc-sim-val">2</span>
          <button class="btn btn-primary text-[11px]" onclick="runECCSimulation()">Run</button>
        </div>
        <div id="ecc-sim-result" class="mt-3"></div>
      </div>
    </div>
  `;
}

async function runECCSimulation() {
  const hires = parseInt(document.getElementById('ecc-sim-hires').value);
  const resultEl = document.getElementById('ecc-sim-result');
  resultEl.innerHTML = '<div class="loading-state"><span class="spinner"></span> Running...</div>';
  try {
    const resp = await fetch(MAESTRO_API + '/api/oem/simulate', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({inputs: {hire_count: hires}}),
    });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    resultEl.innerHTML = `
      <div class="grid grid-cols-2 gap-3 text-[11px]">
        <div class="p-3 rounded-lg bg-white/[0.02]">
          <div class="text-[10px] uppercase text-fg-500">Predicted P1 Risk</div>
          <div class="text-lg font-bold text-brand-amber mono">${formatConfidence(data.predicted.p1_cluster_risk)}</div>
          <div class="text-[10px] text-fg-600">Base: ${formatConfidence(data.base_health.p1_cluster_risk)}</div>
        </div>
        <div class="p-3 rounded-lg bg-white/[0.02]">
          <div class="text-[10px] uppercase text-fg-500">Predicted Velocity</div>
          <div class="text-lg font-bold text-brand-cyan mono">${data.predicted.decision_velocity_days}d</div>
          <div class="text-[10px] text-fg-600">Base: ${data.base_health.decision_velocity_days}d</div>
        </div>
      </div>
      <div class="mt-3 text-[10px] text-fg-500">Based on ${data.linked_laws ? data.linked_laws.length : 0} ${data.linked_laws && data.linked_laws.length === 1 ? 'pattern' : 'patterns'} from organizational memory</div>
    `;
  } catch (e) { resultEl.innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`; }
}

// ─── Section 7: Ask the Organization ──
function renderECCAsk() {
  const el = document.getElementById('ecc-ask');
  el.innerHTML = `
    <div class="space-y-3">
      <div class="relative">
        <input type="text" class="ask-input w-full" placeholder="Ask anything about your organization..." id="ecc-ask-input" oninput="onECCAskInput(this.value)" onkeydown="if(event.key==='Enter'){submitECCAsk()}" aria-label="Ask the organization">
        <div id="ecc-ask-autocomplete" class="exec-autocomplete"></div>
      </div>
      <div id="ecc-ask-answer" class="auto-hidden" class="space-y-3">
        <div class="text-[11px] text-fg-400" id="ecc-ask-answer-text"></div>
        <div id="ecc-ask-citations" class="flex flex-wrap gap-1"></div>
        <div id="ecc-ask-path" class="text-[10px] text-fg-600"></div>
        <div id="ecc-ask-confidence" class="text-[10px] text-brand-cyan"></div>
      </div>
    </div>
  `;
}

let eccAskAbort = null;
async function onECCAskInput(value) {
  const dropdown = document.getElementById('ecc-ask-autocomplete');
  const v = value.trim();
  if (!v) { dropdown.classList.remove('active'); return; }
  if (eccAskAbort) eccAskAbort.abort();
  eccAskAbort = new AbortController();
  try {
    const resp = await fetch(MAESTRO_API + '/api/oem/autocomplete?q=' + encodeURIComponent(v) + '&limit=5', {signal: eccAskAbort.signal});
    if (!resp.ok) return;
    const data = await resp.json();
    const suggestions = data.suggestions || [];
    if (suggestions.length === 0) { dropdown.innerHTML = '<div class="exec-ac-header">No matches in OEM</div>'; dropdown.classList.add('active'); return; }
    dropdown.innerHTML = '<div class="exec-ac-header">From live OEM · ranked by recency, authority, outcome, feedback</div>' +
      suggestions.map((s, i) => `<div class="exec-ac-item" onclick="document.getElementById('ecc-ask-input').value='${escapeJs(s.query)}'; document.getElementById('ecc-ask-autocomplete').classList.remove('active'); submitECCAsk('${escapeJs(s.query)}')">
        <div class="exec-ac-completion"><span class="completed">${escapeHtml(s.completion)}</span></div>
        <div class="text-[9px] text-fg-600 mt-0.5">${escapeHtml(s.source_type)} · conf ${(s.confidence*100).toFixed(0)}% · ${s.citations.length} citations</div>
      </div>`).join('');
    dropdown.classList.add('active');
  } catch(e) { if (e.name !== 'AbortError') {} }
}

async function submitECCAsk(query) {
  const q = (query || document.getElementById('ecc-ask-input').value).trim();
  if (!q) return;
  document.getElementById('ecc-ask-input').value = '';
  document.getElementById('ecc-ask-autocomplete').classList.remove('active');
  const ans = document.getElementById('ecc-ask-answer');
  ans.style.display = 'block';
  document.getElementById('ecc-ask-answer-text').innerHTML = '<span class="spinner"></span> Asking the OEM...';
  try {
    const data = await api.getOEM('/ask?q=' + encodeURIComponent(q));
    document.getElementById('ecc-ask-answer-text').innerHTML = escapeHtml(data.answer).replace(/\n/g, '<br>');
    const sources = data.sources || [];
    document.getElementById('ecc-ask-citations').innerHTML = sources.length === 0 ? '<span class="text-[11px] text-fg-500">No sources cited.</span>' : sources.map(s => `<span class="source-cite">${escapeHtml(s)}</span>`).join('');
    document.getElementById('ecc-ask-confidence').textContent = `Confidence ${formatConfidence(data.confidence)} · ${sources.length} sources`;
  } catch(e) {
    document.getElementById('ecc-ask-answer-text').innerHTML = `<span class="text-brand-rose">Error: ${escapeHtml(e.message)}</span>`;
  }
}

// ─── Section 8: Execution Replay (historical accuracy + calibration) ──
// (renderECCReplay is in home_renderers.js)

