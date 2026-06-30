// CUSTOMER JUDGMENT ENGINE — another OEM surface
// ═══════════════════════════════════════════════════════════════════════════

async function loadCustomerJudgment() {
  loadCustomerMorning();
  loadCustomerList();
  loadCustomerTwinScenarios();
}

async function loadCustomerMorning() {
  const el = document.getElementById('customer-morning');
  const summaryEl = document.getElementById('customer-morning-summary');
  try {
    const data = await api.getOEM('/customer/morning');
    summaryEl.textContent = data.summary || '';
    if (!data.relationships || data.relationships.length === 0) {
      el.innerHTML = '<div class="empty-state">No customer relationships in the OEM yet.</div>';
      return;
    }
    el.innerHTML = data.relationships.map(r => `
      <div class="border border-white/[0.05] rounded-lg p-3 mb-2 cursor-pointer hover:bg-white/[0.02]" onclick="selectCustomer('${escapeJs(r.customer)}')">
        <div class="flex items-center justify-between mb-1">
          <div class="font-semibold text-white">${escapeHtml(r.customer)}</div>
          <div class="flex gap-2">
            <span class="tag ${r.urgency === 'urgent' ? 'tag-red' : r.urgency === 'normal' ? 'tag-yellow' : 'tag-green'}">${escapeHtml(r.urgency)}</span>
            <span class="tag tag-cyan">${formatConfidence(r.confidence)}</span>
          </div>
        </div>
        <div class="text-xs text-fg-400 mb-1">${escapeHtml(r.why)}</div>
        <div class="text-xs text-fg-300"><strong>Recommendation:</strong> ${escapeHtml(r.recommendation)}</div>
        <div class="text-[10px] text-fg-500 mt-1">Expected value: ${escapeHtml(r.expected_value)} · Risk: ${formatConfidence(r.escalation_risk)} · Champion: ${escapeHtml(r.champion_health)}</div>
        <div class="flex gap-1.5 mt-2">
          <button class="tag tag-gray cursor-pointer text-[10px] hover:bg-white/[0.05]" onclick="event.stopPropagation(); selectCustomer('${escapeJs(r.customer)}')" aria-label="Open full brief for ${escapeHtml(r.customer)}">Open brief</button>
          <button class="tag tag-gray cursor-pointer text-[10px] hover:bg-white/[0.05]" onclick="event.stopPropagation(); quickCustomerAsk('${escapeJs(r.customer)}')" aria-label="Ask about ${escapeHtml(r.customer)}">Ask</button>
          <button class="tag tag-gray cursor-pointer text-[10px] hover:bg-white/[0.05]" onclick="event.stopPropagation(); runDefaultTwinScenario('${escapeJs(r.customer)}', '${escapeJs(r.champion_health)}')" aria-label="Simulate ${escapeHtml(r.customer)}">Simulate</button>
        </div>
      </div>
    `).join('');
  } catch (e) {
    el.innerHTML = `<div class="empty-state">Failed to load: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadCustomerList() {
  const el = document.getElementById('customer-list');
  try {
    const data = await api.getOEM('/customer/list');
    if (!data.customers || data.customers.length === 0) {
      el.innerHTML = '<div class="empty-state">No customers found. Connect the Customer provider or enable the demo seed.</div>';
      return;
    }
    el.innerHTML = `
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
        ${data.customers.map(c => `
          <div class="border border-white/[0.05] rounded-lg p-3 cursor-pointer hover:bg-white/[0.02]" onclick="selectCustomer('${escapeJs(c.name)}')">
            <div class="flex items-center justify-between mb-2">
              <div class="font-semibold text-white">${escapeHtml(c.name)}</div>
              <span class="tag ${c.state === 'negative' ? 'tag-red' : c.state === 'positive' ? 'tag-green' : 'tag-gray'}">${escapeHtml(c.state)}</span>
            </div>
            <div class="text-lg font-bold text-cyan-400">$${(c.arr_at_stake / 1000000).toFixed(1)}M</div>
            <div class="text-[10px] text-fg-500">ARR at stake</div>
            <div class="text-[10px] text-fg-400 mt-2">Risk: ${formatConfidence(c.escalation_risk)} · Champion: ${escapeHtml(c.champion_health)}</div>
          </div>
        `).join('')}
      </div>
    `;
  } catch (e) {
    el.innerHTML = `<div class="empty-state">Failed to load: ${escapeHtml(e.message)}</div>`;
  }
}

async function selectCustomer(name) {
  // Show the panels
  document.getElementById('customer-brief-panel').style.display = '';
  document.getElementById('customer-committee-panel').style.display = '';
  document.getElementById('customer-drift-panel').style.display = '';
  document.getElementById('customer-brief-title').textContent = `Executive Brief — ${name}`;

  loadCustomerBrief(name);
  loadCustomerCommittee(name);
  loadCustomerDrift(name);
}

async function loadCustomerBrief(name) {
  const body = document.getElementById('customer-brief-body');
  const confEl = document.getElementById('customer-brief-confidence');
  body.innerHTML = '<div class="loading-state"><span class="spinner"></span>Loading brief…</div>';
  try {
    const b = await api.getOEM(`/customer/brief/${encodeURIComponent(name)}`);
    confEl.textContent = `confidence ${formatConfidence(b.confidence)}`;
    body.innerHTML = `
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div><div class="text-[10px] text-fg-500 uppercase">State</div><div class="text-sm font-semibold ${b.relationship_state === 'healthy' || b.relationship_state === 'renewed' ? 'text-green-400' : b.relationship_state === 'at_risk' ? 'text-yellow-400' : b.relationship_state === 'churned' ? 'text-red-400' : 'text-fg-300'}">${escapeHtml(b.relationship_state)}</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">ARR at stake</div><div class="text-sm font-semibold text-cyan-400">$${(b.arr_at_stake / 1000000).toFixed(2)}M</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">Urgency</div><div class="text-sm font-semibold">${escapeHtml(b.urgency)}</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">Business impact</div><div class="text-xs text-fg-300">${escapeHtml(b.business_impact)}</div></div>
      </div>
      <div class="border-t border-white/[0.05] pt-3">
        <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-2">Recommended outcome</div>
        <div class="text-sm text-fg-200">${escapeHtml(b.recommended_outcome)}</div>
      </div>
      <div class="border-t border-white/[0.05] pt-3">
        <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-2">Outstanding risks</div>
        <div class="text-xs text-fg-300 space-y-1">
          <div>Broken commitments: <strong>${b.outstanding_risks.broken_commitments}</strong></div>
          <div>Objections: <strong>${b.outstanding_risks.objections}</strong> (${escapeHtml((b.outstanding_risks.objection_types || []).join(', ') || 'none')})</div>
          <div>Drift signals: <strong>${b.outstanding_risks.drift_signals}</strong></div>
        </div>
      </div>
      ${b.things_not_to_say && b.things_not_to_say.length > 0 ? `
      <div class="border-t border-white/[0.05] pt-3">
        <div class="text-[10px] uppercase tracking-wider text-red-400 font-semibold mb-2">Things not to say</div>
        <ul class="text-xs text-fg-300 space-y-1">
          ${b.things_not_to_say.map(t => `<li>• ${escapeHtml(t)}</li>`).join('')}
        </ul>
      </div>` : ''}
      <div class="border-t border-white/[0.05] pt-3">
        <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-2">Evidence</div>
        <div class="text-xs text-fg-400">${escapeHtml(b.confidence_explanation)}</div>
        <div class="text-xs text-fg-400 mt-1">${b.evidence.learning_objects} LOs · ${b.evidence.laws.length} laws · ${b.evidence.signals} signals</div>
      </div>
    `;
  } catch (e) {
    body.innerHTML = `<div class="empty-state">Failed to load brief: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadCustomerCommittee(name) {
  const body = document.getElementById('customer-committee-body');
  const meta = document.getElementById('customer-committee-meta');
  body.innerHTML = '<div class="loading-state"><span class="spinner"></span>Loading committee…</div>';
  try {
    const c = await api.getOEM(`/customer/committee/${encodeURIComponent(name)}`);
    meta.textContent = `${c.total_members} members · ${c.decision_radius} decision radius`;
    body.innerHTML = `
      <div class="grid grid-cols-1 md:grid-cols-2 gap-2 mb-3">
        ${c.members.map(m => `
          <div class="border border-white/[0.05] rounded p-2">
            <div class="flex items-center justify-between">
              <div class="text-xs font-semibold text-white">${escapeHtml(m.contact)}</div>
              <span class="tag ${m.support_level === 'strong' ? 'tag-green' : m.support_level === 'moderate' ? 'tag-yellow' : m.support_level === 'weak' ? 'tag-gray' : 'tag-red'}">${escapeHtml(m.support_level)}</span>
            </div>
            <div class="text-[10px] text-fg-400 mt-1">Roles: ${escapeHtml(m.roles.join(', ') || 'unknown')}</div>
            <div class="text-[10px] text-fg-500">Influence: ${m.influence} · Interactions: ${m.interactions} · conf ${formatConfidence(m.confidence)}</div>
          </div>
        `).join('')}
      </div>
      <div class="text-[10px] text-fg-500">Roles filled: ${escapeHtml(c.roles_filled.join(', '))}</div>
      ${c.roles_missing.length > 0 ? `<div class="text-[10px] text-amber-400">Roles missing: ${escapeHtml(c.roles_missing.join(', '))}</div>` : ''}
    `;
  } catch (e) {
    body.innerHTML = `<div class="empty-state">Failed to load: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadCustomerDrift(name) {
  const body = document.getElementById('customer-drift-body');
  body.innerHTML = '<div class="loading-state"><span class="spinner"></span>Loading drift…</div>';
  try {
    const d = await api.getOEM(`/customer/drift/${encodeURIComponent(name)}`);
    body.innerHTML = `
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div><div class="text-[10px] text-fg-500 uppercase">Momentum</div><div class="text-sm font-semibold ${d.momentum === 'positive' ? 'text-green-400' : d.momentum === 'negative' ? 'text-red-400' : 'text-fg-300'}">${escapeHtml(d.momentum)}</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">Trust</div><div class="text-sm font-semibold">${formatConfidence(d.trust)}</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">Champion health</div><div class="text-sm font-semibold ${d.champion_health === 'active' ? 'text-green-400' : d.champion_health === 'quiet' ? 'text-red-400' : 'text-fg-300'}">${escapeHtml(d.champion_health)}</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">Escalation risk</div><div class="text-sm font-semibold ${d.escalation_risk > 0.5 ? 'text-red-400' : d.escalation_risk > 0.2 ? 'text-yellow-400' : 'text-green-400'}">${formatConfidence(d.escalation_risk)}</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">Decision readiness</div><div class="text-sm">${escapeHtml(d.decision_readiness)}</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">Exec engagement</div><div class="text-sm">${escapeHtml(d.executive_engagement)}</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">Response latency</div><div class="text-sm">${d.response_latency_days !== null ? d.response_latency_days + 'd' : '—'}</div></div>
        <div><div class="text-[10px] text-fg-500 uppercase">Buying velocity</div><div class="text-sm">${d.buying_velocity}/mo</div></div>
      </div>
    `;
  } catch (e) {
    body.innerHTML = `<div class="empty-state">Failed to load: ${escapeHtml(e.message)}</div>`;
  }
}

async function submitCustomerAsk(q) {
  const answerEl = document.getElementById('customer-ask-answer');
  const textEl = document.getElementById('customer-ask-text');
  const evEl = document.getElementById('customer-ask-evidence');
  const unEl = document.getElementById('customer-ask-unknowns');
  const confEl = document.getElementById('customer-ask-confidence');
  answerEl.style.display = '';
  textEl.textContent = 'Thinking…';
  evEl.textContent = '';
  unEl.textContent = '';
  confEl.textContent = '';
  try {
    const data = await api.getOEM(`/customer/ask?q=${encodeURIComponent(q)}`);
    textEl.textContent = data.answer;
    evEl.innerHTML = `<strong>Evidence:</strong> ${JSON.stringify(data.evidence)}`;
    if (data.unknowns && data.unknowns.length > 0) {
      unEl.innerHTML = `<strong>Unknowns:</strong> ${data.unknowns.map(u => escapeHtml(u)).join('; ')}`;
    }
    if (data.counter_evidence && data.counter_evidence.length > 0) {
      unEl.innerHTML = (unEl.innerHTML ? unEl.innerHTML + '<br>' : '') +
        `<strong>Counter-evidence:</strong> ${data.counter_evidence.map(c => escapeHtml(c.detail || JSON.stringify(c))).join('; ')}`;
    }
    confEl.textContent = `Confidence ${formatConfidence(data.confidence)} — ${escapeHtml(data.confidence_explanation || '')}`;
  } catch (e) {
    textEl.textContent = `Error: ${e.message}`;
  }
}

async function loadCustomerTwinScenarios() {
  const el = document.getElementById('customer-twin-scenarios');
  try {
    const data = await api.getOEM('/customer/twin/scenarios');
    el.innerHTML = data.scenarios.map(s => `
      <button class="tag tag-gray cursor-pointer text-left p-2 hover:bg-white/[0.05]" onclick="loadCustomerTwinForm('${escapeJs(s.type)}', ${JSON.stringify(s.example).replace(/"/g, '&quot;')})">
        <div class="text-xs font-semibold">${escapeHtml(s.title)}</div>
        <div class="text-[10px] text-fg-500">${escapeHtml(s.type)}</div>
      </button>
    `).join('');
  } catch (e) {
    el.innerHTML = `<div class="empty-state">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadCustomerTwinForm(type, example) {
  const formEl = document.getElementById('customer-twin-form');
  const resultEl = document.getElementById('customer-twin-result');
  formEl.style.display = '';
  resultEl.style.display = 'none';
  // Use the example as the payload — in production this would render a form
  // based on the scenario's params, but for the demo the examples are complete.
  formEl.innerHTML = `
    <div class="text-xs text-fg-300">Scenario: <strong>${escapeHtml(type)}</strong></div>
    <div class="text-[10px] text-fg-500">Payload: <code>${escapeHtml(JSON.stringify(example, null, 2))}</code></div>
    <button class="btn btn-primary text-xs" onclick="runCustomerTwin(${JSON.stringify(example).replace(/"/g, '&quot;')})">Run simulation</button>
  `;
}

async function runCustomerTwin(payload) {
  const resultEl = document.getElementById('customer-twin-result');
  resultEl.style.display = '';
  resultEl.innerHTML = '<div class="loading-state"><span class="spinner"></span>Simulating…</div>';
  try {
    const data = await api.postOEM('/customer/twin/simulate', payload);
    const riskColor = data.risk_level === 'critical' ? 'text-red-400' : data.risk_level === 'high' ? 'text-orange-400' : data.risk_level === 'medium' ? 'text-yellow-400' : 'text-green-400';
    resultEl.innerHTML = `
      <div class="border border-white/[0.05] rounded-lg p-3 space-y-3">
        <div class="flex items-center justify-between">
          <div class="text-sm font-semibold text-white">Expected outcome: <span class="text-cyan-400">${escapeHtml(data.expected_outcome)}</span></div>
          <div class="flex gap-2">
            <span class="tag ${riskColor}">${escapeHtml(data.risk_level)} risk</span>
            <span class="tag tag-cyan">${formatConfidence(data.confidence)}</span>
          </div>
        </div>
        <div class="text-xs text-fg-300">${escapeHtml(data.description)}</div>
        <div class="border-t border-white/[0.05] pt-2">
          <div class="text-[10px] uppercase text-fg-500 font-semibold mb-1">Business impact</div>
          <div class="text-xs text-fg-300">${Object.entries(data.business_impact).map(([k,v]) => `${escapeHtml(k)}: ${escapeHtml(String(v))}`).join(' · ')}</div>
        </div>
        <div class="border-t border-white/[0.05] pt-2">
          <div class="text-[10px] uppercase text-fg-500 font-semibold mb-1">Supporting evidence</div>
          <ul class="text-xs text-fg-300 space-y-1">${data.supporting_evidence.map(e => `<li>• ${escapeHtml(e.detail)}</li>`).join('')}</ul>
        </div>
        <div class="border-t border-white/[0.05] pt-2">
          <div class="text-[10px] uppercase text-amber-400 font-semibold mb-1">Counter-evidence</div>
          <ul class="text-xs text-fg-400 space-y-1">${data.counter_evidence.map(e => `<li>• ${escapeHtml(e.detail)}</li>`).join('')}</ul>
        </div>
        <div class="border-t border-white/[0.05] pt-2">
          <div class="text-[10px] uppercase text-fg-500 font-semibold mb-1">Alternative actions</div>
          <ul class="text-xs text-fg-300 space-y-1">${data.alternative_actions.map(a => `<li>• <strong>${escapeHtml(a.action)}</strong> — ${escapeHtml(a.rationale)}</li>`).join('')}</ul>
        </div>
      </div>
    `;
  } catch (e) {
    resultEl.innerHTML = `<div class="empty-state">Simulation failed: ${escapeHtml(e.message)}</div>`;
  }
}

// ─── One-click actions from the morning brief ─────────────────────────────

async function quickCustomerAsk(customer) {
  // Navigate to customer surface, populate the ask input, and submit
  navTo('customer');
  await new Promise(r => setTimeout(r, 300)); // Let the surface load
  const input = document.getElementById('customer-ask-input');
  if (input) {
    const q = `What should I know about ${customer} right now?`;
    input.value = q;
    submitCustomerAsk(q);
  }
}

async function runDefaultTwinScenario(customer, championHealth) {
  // Pick a scenario based on the customer's state
  navTo('customer');
  await new Promise(r => setTimeout(r, 300));
  // If champion is quiet, simulate champion_leaves (highest urgency)
  // Otherwise simulate pricing (most common question)
  const scenario = championHealth === 'quiet'
    ? { type: 'champion_leaves', customer }
    : { type: 'pricing', customer, increase_pct: 10 };
  runCustomerTwin(scenario);
}
