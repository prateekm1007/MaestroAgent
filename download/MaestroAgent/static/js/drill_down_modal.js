// DRILL-DOWN MODAL — every card/metric/insight is clickable
// Answers: Why? Where? Evidence? Timeline? People? Prediction? Simulation? Recommendation? Perspectives?
// ═══════════════════════════════════════════════════════════════════════════

let drilldownData = null;
let drilldownActiveTab = 'why';
let _drilldownPerspectivesCache = null;

async function openDrilldown(entityType, entityId) {
  const modal = document.getElementById('drilldown-modal');
  const body = document.getElementById('drilldown-body');
  const title = document.getElementById('drilldown-title');
  const typeLabel = document.getElementById('drilldown-type');

  modal.classList.remove('hidden');
  body.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  title.textContent = entityId;
  typeLabel.textContent = entityType.charAt(0).toUpperCase() + entityType.slice(1);

  try {
    const resp = await fetch(`${MAESTRO_API}/api/oem/entity/${entityType}/${encodeURIComponent(entityId)}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    drilldownData = await resp.json();
    drilldownActiveTab = 'why';
    updateDrilldownTabs();
    renderDrilldownTab('why');
  } catch (e) {
    body.innerHTML = `<div class="error-state">Failed to load: ${escapeHtml(e.message)}</div>`;
  }
}

function closeDrilldown() {
  document.getElementById('drilldown-modal').classList.add('hidden');
  drilldownData = null;
}

function switchDrilldownTab(tab) {
  drilldownActiveTab = tab;
  updateDrilldownTabs();
  renderDrilldownTab(tab);
}

function updateDrilldownTabs() {
  document.querySelectorAll('.drilldown-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === drilldownActiveTab);
  });
}

function renderDrilldownTab(tab) {
  const body = document.getElementById('drilldown-body');
  if (!drilldownData) return;

  if (tab === 'why') {
    body.innerHTML = `
      <div class="space-y-4">
        <div class="text-sm text-fg-200 leading-relaxed">${escapeHtml(drilldownData.why || 'No explanation available.')}</div>
        ${drilldownData.where ? `
          <div class="mt-4 pt-4 border-t border-white/[0.05]">
            <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-2">Context</div>
            <pre class="text-[11px] text-fg-400 bg-white/[0.02] p-3 rounded-lg overflow-x-auto">${escapeHtml(JSON.stringify(drilldownData.where, null, 2))}</pre>
          </div>
        ` : ''}
      </div>
    `;
  } else if (tab === 'where') {
    body.innerHTML = `
      <div class="space-y-3">
        <div class="text-sm text-fg-200">${drilldownData.where ? 'This entity appears in:' : 'No location data.'}</div>
        ${drilldownData.where ? `<pre class="text-[11px] text-fg-400 bg-white/[0.02] p-3 rounded-lg overflow-x-auto">${escapeHtml(JSON.stringify(drilldownData.where, null, 2))}</pre>` : ''}
      </div>
    `;
  } else if (tab === 'evidence') {
    const ev = drilldownData.evidence || [];
    body.innerHTML = ev.length === 0
      ? '<div class="empty-state">No evidence available.</div>'
      : `<div class="text-[10px] text-fg-500 mb-3">${ev.length} evidence item(s)</div>
         <div class="space-y-2">${ev.map(e => `
           <div class="drilldown-evidence-item" onclick="${e.signal_id ? `openDrilldown('signal', '${escapeJs(e.signal_id)}')` : ''}">
             <div class="flex items-center justify-between">
               <span class="text-xs font-semibold text-fg-200">${escapeHtml(e.type)}${e.signal_type ? ': ' + escapeHtml(e.signal_type) : ''}</span>
               ${e.provider ? `<span class="tag tag-gray">${escapeHtml(e.provider)}</span>` : ''}
             </div>
             ${e.actor ? `<div class="text-[10px] text-fg-500 mt-1">Actor: ${escapeHtml(e.actor)}</div>` : ''}
             ${e.artifact ? `<div class="text-[10px] text-fg-500">Artifact: ${escapeHtml(e.artifact)}</div>` : ''}
             ${e.timestamp ? `<div class="text-[10px] text-fg-600 mt-1">${formatTimestamp(e.timestamp)}</div>` : ''}
           </div>
         `).join('')}</div>`;
  } else if (tab === 'timeline') {
    const tl = drilldownData.timeline || [];
    body.innerHTML = tl.length === 0
      ? '<div class="empty-state">No timeline data.</div>'
      : `<div class="space-y-0">${tl.map(t => `
         <div class="drilldown-timeline-item">
           <div class="text-xs font-semibold text-fg-200">${escapeHtml(t.event)}</div>
           <div class="text-[10px] text-fg-500">${escapeHtml(t.detail || '')}</div>
           ${t.timestamp ? `<div class="text-[10px] text-fg-600 mt-1">${formatTimestamp(t.timestamp)}</div>` : ''}
         </div>
       `).join('')}</div>`;
  } else if (tab === 'people') {
    const ppl = drilldownData.people || [];
    body.innerHTML = ppl.length === 0
      ? '<div class="empty-state">No people data.</div>'
      : `<div class="space-y-1">${ppl.map(p => `
         <div class="drilldown-person" onclick="openDrilldown('expert', '${escapeJs(p.name)}')">
           <div class="w-8 h-8 rounded-full bg-brand-violet/20 flex items-center justify-center text-xs font-bold text-brand-violet">${escapeHtml(p.name.charAt(0).toUpperCase())}</div>
           <div class="flex-1">
             <div class="text-xs font-semibold text-fg-200">${escapeHtml(p.name)}</div>
             <div class="text-[10px] text-fg-500">${escapeHtml(p.role || '')}</div>
           </div>
           ${p.influence ? `<span class="text-[10px] text-brand-purple mono">inf ${p.influence.toFixed(2)}</span>` : ''}
         </div>
       `).join('')}</div>`;
  } else if (tab === 'prediction') {
    const pred = drilldownData.prediction;
    body.innerHTML = !pred
      ? '<div class="empty-state">No prediction available.</div>'
      : `<div class="space-y-3">
         ${pred.condition ? `<div><div class="text-[10px] uppercase text-fg-500 mb-1">Condition</div><div class="text-sm text-fg-200">${escapeHtml(humanize(pred.condition))}</div></div>` : ''}
         ${pred.outcome ? `<div><div class="text-[10px] uppercase text-fg-500 mb-1">Predicted Outcome</div><div class="text-sm text-brand-cyan">${escapeHtml(humanize(pred.outcome))}</div></div>` : ''}
         ${pred.detail ? `<div><div class="text-[10px] uppercase text-fg-500 mb-1">Detail</div><div class="text-sm text-fg-300">${escapeHtml(humanize(pred.detail))}</div></div>` : ''}
         ${pred.impact ? `<div><div class="text-[10px] uppercase text-fg-500 mb-1">Impact</div><div class="text-sm text-fg-300">${escapeHtml(humanize(pred.impact))}</div></div>` : ''}
         ${pred.confidence != null ? `<div><div class="text-[10px] uppercase text-fg-500 mb-1">Confidence</div><div class="conf-bar" class="b-w200"><div class="conf-bar-track"><div class="conf-bar-fill" class="b-wpredconfidence100p"></div></div><span class="text-brand-cyan font-bold">${formatConfidenceWithWhy(pred.confidence, { entity: 'prediction', title: pred.outcome })}</span></div></div>` : ''}
         ${pred.risk ? `<div><span class="tag tag-rose">${escapeHtml(pred.risk)}</span></div>` : ''}
       </div>`;
  } else if (tab === 'simulation') {
    const sim = drilldownData.simulation;
    body.innerHTML = !sim || !sim.available
      ? '<div class="empty-state">No simulation available for this entity.</div>'
      : `<div class="space-y-4">
         <div class="text-sm text-fg-200">${escapeHtml(sim.prompt || 'Run a what-if simulation.')}</div>
         ${sim.linked_laws && sim.linked_laws.length ? `<div class="text-[10px] text-fg-500">Linked laws: ${sim.linked_laws.map(l => `<span class="source-cite">${escapeHtml(l)}</span>`).join(' ')}</div>` : ''}
         <div>
           <div class="text-[10px] uppercase text-fg-500 mb-2">Quick Simulation</div>
           <div class="flex items-center gap-3">
             <label class="text-[11px] text-fg-400">Hire count:</label>
             <input type="range" min="0" max="10" value="2" id="drilldown-sim-hires" class="flex-1" oninput="document.getElementById('drilldown-sim-val').textContent=this.value">
             <span class="text-xs font-bold text-brand-cyan mono" id="drilldown-sim-val">2</span>
             <button class="btn btn-primary text-[11px]" onclick="runDrilldownSimulation()">Run</button>
           </div>
           <div id="drilldown-sim-result" class="mt-4"></div>
         </div>
       </div>`;
  } else if (tab === 'recommendation') {
    const rec = drilldownData.recommendation;
    body.innerHTML = !rec || !rec.available
      ? '<div class="empty-state">No recommendations linked to this entity.</div>'
      : `<div class="space-y-2">${rec.items.map(r => `
         <div class="card mb-2 cursor-pointer" onclick="navTo('simulator')">
           <div class="text-sm font-semibold text-white">${escapeHtml(humanize(r.title))}</div>
           <div class="text-[11px] text-fg-400 mt-1">${escapeHtml(r.recommendation || '')}</div>
           <div class="flex items-center gap-2 mt-2 text-[10px] text-fg-500">
             ${r.urgency ? `<span class="tag ${r.urgency === 'urgent' ? 'tag-rose' : 'tag-amber'}">${escapeHtml(r.urgency)}</span>` : ''}
             ${r.confidence != null ? `<span>conf ${formatConfidence(r.confidence)}</span>` : ''}
           </div>
         </div>
       `).join('')}</div>`;
  } else if (tab === 'perspectives') {
    // Surface 4: Perspectives — translate this event into 6 team-specific views.
    body.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
    renderPerspectivesTab(body);
  } else if (tab === 'sowhat') {
    // V3 Law 8: Everything answers 'so what?'
    body.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
    renderSoWhatTab(body);
  }
}

// ─── V3: So What? tab ──────────────────────────────────────────────────────
async function renderSoWhatTab(bodyEl) {
  if (!drilldownData) {
    bodyEl.innerHTML = '<div class="ds-empty">No entity loaded.</div>';
    return;
  }
  // Infer entity type from the drilldown data
  const entityType = drilldownData.type || drilldownData.entity_type || 'recommendation';
  const entityId = drilldownData.title || drilldownData.why || drilldownData.entity_id || '';

  try {
    const data = await api.getOEM(`/sowhat?entity_type=${encodeURIComponent(entityType)}&entity_id=${encodeURIComponent(entityId)}`);
    bodyEl.innerHTML = `
      <div class="ds-stack">
        <div>
          <div class="ds-cascade-label">If ignored</div>
          <div class="b-fs14-text-9">${escapeHtml(humanize(data.consequence_if_ignored || ''))}</div>
        </div>
        <div>
          <div class="ds-cascade-label">What to do</div>
          <div class="b-fs14-text-9">${escapeHtml(humanize(data.recommended_action || ''))}</div>
        </div>
        <div>
          <div class="ds-cascade-label">When it matters</div>
          <div class="b-fs14-text-4">${escapeHtml(humanize(data.time_horizon || ''))}</div>
        </div>
        <div>
          <div class="ds-cascade-label">How we know</div>
          <div class="subtle-text">${escapeHtml(humanize(data.confidence_in_consequence || ''))} · ${data.evidence_count || 0} signals</div>
        </div>
      </div>
    `;
  } catch (e) {
    bodyEl.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

// ─── Surface 4: Perspectives ─────────────────────────────────────────────────
// Translates the current drilldown entity into 6 team-specific perspectives:
// engineering, legal, finance, sales, support, leadership.
// The same event means different things to different teams.

async function renderPerspectivesTab(bodyEl) {
  if (!drilldownData) {
    bodyEl.innerHTML = '<div class="ds-empty">No entity loaded.</div>';
    return;
  }

  // Map the drilldown entity type to a perspective event_type.
  // The PerspectiveEngine supports ~10 event types; we infer the closest match.
  const eventType = inferPerspectiveEventType(drilldownData);
  const customer = drilldownData.where?.customer || drilldownData.customer || '';
  const arr = drilldownData.where?.arr || 0;
  const commitment = drilldownData.commitment || drilldownData.where?.commitment || '';

  if (!eventType) {
    bodyEl.innerHTML = `<div class="ds-empty">
      <div class="b-fs135-text-2">No perspectives available for this entity.</div>
      <div>The Perspective Engine supports specific event types (customer commitment broken, objection raised, etc.). This entity doesn't map to a supported event type.</div>
    </div>`;
    return;
  }

  try {
    const params = new URLSearchParams({
      event_type: eventType,
      customer: customer,
      arr: String(arr),
      commitment: commitment,
    });
    const data = await api.getOEM(`/perspectives?${params.toString()}`);
    _drilldownPerspectivesCache = data;
    renderPerspectiveGrid(bodyEl, data);
  } catch (e) {
    bodyEl.innerHTML = `<div class="ds-error">Failed to load perspectives: ${escapeHtml(e.message)}</div>`;
  }
}

function inferPerspectiveEventType(data) {
  // The PerspectiveEngine supports these event types (from /perspectives/types):
  // customer.commitment_broken, customer.objection_raised, customer.champion_departed,
  // customer.security_incident, customer.procurement_pressure, customer.legal_threat,
  // decision.deadline_slipped, decision.scope_changed, team.bottleneck_formed, team.knowledge_lost
  const type = (data.type || data.entity_type || '').toLowerCase();
  const title = (data.title || data.why || '').toLowerCase();
  const text = JSON.stringify(data).toLowerCase();

  if (type.includes('customer') || text.includes('commitment_broken')) {
    if (text.includes('objection')) return 'customer.objection_raised';
    if (text.includes('champion') && text.includes('depart')) return 'customer.champion_departed';
    if (text.includes('security')) return 'customer.security_incident';
    if (text.includes('procurement')) return 'customer.procurement_pressure';
    if (text.includes('legal')) return 'customer.legal_threat';
    return 'customer.commitment_broken';
  }
  if (text.includes('bottleneck')) return 'team.bottleneck_formed';
  if (text.includes('knowledge') && text.includes('lost')) return 'team.knowledge_lost';
  if (text.includes('deadline') && text.includes('slip')) return 'decision.deadline_slipped';
  if (text.includes('scope') && text.includes('chang')) return 'decision.scope_changed';
  // Default: treat as a customer commitment event (most common in demo data)
  if (text.includes('customer') || text.includes('initech') || text.includes('globex') || text.includes('hooli')) {
    return 'customer.commitment_broken';
  }
  return null;
}

function renderPerspectiveGrid(bodyEl, data) {
  const perspectives = data.perspectives || {};
  const teams = ['engineering', 'legal', 'finance', 'sales', 'support', 'leadership'];
  const teamLabels = {
    engineering: 'Engineering',
    legal: 'Legal',
    finance: 'Finance',
    sales: 'Sales',
    support: 'Support',
    leadership: 'Leadership',
  };

  const rows = teams.map(team => {
    const text = perspectives[team];
    if (!text) return '';
    return `
      <div class="ds-perspective-team">${teamLabels[team]}</div>
      <div class="ds-perspective-text">${escapeHtml(text)}</div>
    `;
  }).filter(Boolean).join('');

  if (!rows) {
    bodyEl.innerHTML = `<div class="ds-empty">No perspectives returned for event type <code>${escapeHtml(data.event_type)}</code>.</div>`;
    return;
  }

  bodyEl.innerHTML = `
    <div class="b-mb14">
      <div class="ds-cascade-label">Event type</div>
      <div class="b-fs125-clr">${escapeHtml(data.event_type)}</div>
    </div>
    <div class="ds-perspective-grid">${rows}</div>
    <div class="ds-meta" class="b-mt14">Same event, six implications. Each team sees a different risk surface — coordination happens before the decision, not after.</div>
  `;
}

async function runDrilldownSimulation() {
  const hires = parseInt(document.getElementById('drilldown-sim-hires').value);
  const resultEl = document.getElementById('drilldown-sim-result');
  resultEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const lawCode = drilldownData?.simulation?.linked_laws?.[0];
    const resp = await fetch(`${MAESTRO_API}/api/oem/simulate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ law_code: lawCode, inputs: { hire_count: hires } }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    resultEl.innerHTML = `
      <div class="grid grid-cols-2 gap-3 text-[11px]">
        <div class="p-3 rounded-lg bg-white/[0.02]">
          <div class="text-[10px] uppercase text-fg-500">P1 Risk</div>
          <div class="text-lg font-bold text-brand-amber mono">${formatConfidence(data.predicted.p1_cluster_risk)}</div>
          <div class="text-[10px] text-fg-600">Base: ${formatConfidence(data.base_health.p1_cluster_risk)}</div>
        </div>
        <div class="p-3 rounded-lg bg-white/[0.02]">
          <div class="text-[10px] uppercase text-fg-500">Decision Velocity</div>
          <div class="text-lg font-bold text-brand-cyan mono">${data.predicted.decision_velocity_days}d</div>
          <div class="text-[10px] text-fg-600">Base: ${data.base_health.decision_velocity_days}d</div>
        </div>
      </div>
      <div class="mt-3 text-[10px] text-fg-500">Confidence: ${formatConfidenceWithWhy(data.confidence, { entity: 'recommendation' })}</div>
    `;
  } catch (e) {
    resultEl.innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`;
  }
}

// ESC closes the drill-down modal
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    const modal = document.getElementById('drilldown-modal');
    if (modal && !modal.classList.contains('hidden')) {
      closeDrilldown();
    }
  }
});

// ═══════════════════════════════════════════════════════════════════════════