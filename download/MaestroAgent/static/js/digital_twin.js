// DIGITAL TWIN — "What happens if...?"
// ═══════════════════════════════════════════════════════════════════════════

function renderECCTwin(twinState) {
  const el = document.getElementById('ecc-twin');
  const summary = twinState.summary || {};
  const people = twinState.people || [];
  const domains = twinState.domains || [];

  el.innerHTML = `
    <div class="space-y-4">
      <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div class="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <div class="text-[10px] uppercase text-fg-500">People</div>
          <div class="text-lg font-bold text-white mono">${summary.people || 0}</div>
        </div>
        <div class="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <div class="text-[10px] uppercase text-fg-500">Domains</div>
          <div class="text-lg font-bold text-white mono">${summary.domains || 0}</div>
        </div>
        <div class="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <div class="text-[10px] uppercase text-fg-500">Bottlenecks</div>
          <div class="text-lg font-bold text-brand-rose mono">${summary.bottlenecks || 0}</div>
        </div>
        <div class="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <div class="text-[10px] uppercase text-fg-500">At-Risk Domains</div>
          <div class="text-lg font-bold text-brand-amber mono">${summary.at_risk_domains || 0}</div>
        </div>
        <div class="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <div class="text-[10px] uppercase text-fg-500">Avg Workload</div>
          <div class="text-lg font-bold text-brand-cyan mono">${(summary.avg_workload || 0).toFixed(1)}</div>
        </div>
      </div>

      <div class="pt-3 border-t border-white/[0.05]">
        <div class="text-[10px] uppercase tracking-wider text-fg-500 font-semibold mb-2">Run a What-If Scenario</div>
        <div class="space-y-3">
          <!-- Person leaves -->
          <div class="flex items-center gap-2">
            <select id="twin-person" class="ask-input flex-1 text-[11px]">
              ${people.map(p => `<option value="${escapeHtml(p.email)}">${escapeHtml(p.email)} (wl: ${p.workload}, inf: ${p.influence})</option>`).join('')}
            </select>
            <button class="btn btn-ghost text-[10px]" onclick="runTwinScenario({'type':'person_leaves','person':document.getElementById('twin-person').value})">What if they leave?</button>
          </div>
          <!-- Cut meetings -->
          <div class="flex items-center gap-2">
            <label class="text-[11px] text-fg-400">Cut meetings by:</label>
            <input type="range" min="10" max="80" value="30" id="twin-meeting-cut" class="flex-1" oninput="document.getElementById('twin-meeting-val').textContent=this.value+'%'">
            <span class="text-xs font-bold text-brand-cyan mono" id="twin-meeting-val">30%</span>
            <button class="btn btn-ghost text-[10px]" onclick="runTwinScenario({'type':'cut_meetings','reduction_pct':parseInt(document.getElementById('twin-meeting-cut').value)})">Simulate</button>
          </div>
          <!-- Add hires -->
          <div class="flex items-center gap-2">
            <select id="twin-hire-domain" class="ask-input flex-1 text-[11px]">
              ${domains.map(d => `<option value="${escapeHtml(d.name)}">${escapeHtml(d.name)} (${d.people.length} people)</option>`).join('')}
            </select>
            <input type="number" min="1" max="20" value="3" id="twin-hire-count" class="w-16 ask-input text-[11px] text-center">
            <button class="btn btn-ghost text-[10px]" onclick="runTwinScenario({'type':'add_hires','domain':document.getElementById('twin-hire-domain').value,'count':parseInt(document.getElementById('twin-hire-count').value)})">Add hires</button>
          </div>
        </div>
      </div>

      <div id="twin-result" class="mt-3"></div>
    </div>
  `;
}

async function runTwinScenario(scenario) {
  const resultEl = document.getElementById('twin-result');
  if (!resultEl) return;
  resultEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const resp = await fetch(MAESTRO_API + '/api/oem/twin/simulate', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(scenario),
    });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const report = await resp.json();
    renderTwinReport(report);
  } catch(e) {
    resultEl.innerHTML = `<div class="error-state">${escapeHtml(e.message)}</div>`;
  }
}

function renderTwinReport(report) {
  const resultEl = document.getElementById('twin-result');
  const riskColor = report.risk_level === 'critical' ? 'rose' : report.risk_level === 'high' ? 'amber' : report.risk_level === 'medium' ? 'amber' : 'green';
  resultEl.innerHTML = `
    <div class="space-y-4">
      <div class="p-3 rounded-lg bg-brand-${riskColor}/[0.06] border border-brand-${riskColor}/15">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-sm font-semibold text-white">${escapeHtml(humanize(report.description))}</div>
            <div class="text-[10px] text-fg-500 mt-1">Scenario: ${escapeHtml(report.scenario_type)} · ${escapeHtml(report.timestamp)}</div>
          </div>
          <div class="text-right">
            <span class="tag tag-${riskColor}">${escapeHtml(report.risk_level)}</span>
            <div class="text-[10px] text-fg-600 mt-1">risk score: ${report.risk_score.toFixed(2)}</div>
          </div>
        </div>
      </div>

      ${report.overloaded_people.length > 0 ? `
        <div>
          <div class="text-[10px] uppercase text-fg-500 font-semibold mb-2">Overloaded People (${report.overloaded_people.length})</div>
          ${report.overloaded_people.map(p => `
            <div class="flex items-center gap-2 p-2 rounded-lg bg-brand-rose/[0.04] border border-brand-rose/10 mb-1 cursor-pointer" onclick="openDrilldown('expert', '${escapeJs(p.person)}')">
              <span class="text-xs font-semibold text-fg-200">${escapeHtml(p.person)}</span>
              <span class="text-[10px] text-brand-rose">+${p.workload_increase} workload</span>
              <span class="text-[10px] text-fg-600">${p.domains.join(', ')}</span>
            </div>`).join('')}
        </div>` : ''}

      ${report.knowledge_loss.length > 0 ? `
        <div>
          <div class="text-[10px] uppercase text-fg-500 font-semibold mb-2">Knowledge Loss (${report.knowledge_loss.length})</div>
          ${report.knowledge_loss.map(kl => `
            <div class="p-2 rounded-lg bg-brand-amber/[0.04] border border-brand-amber/10 mb-1 cursor-pointer" onclick="openDrilldown('risk', '${escapeJs(kl.domain)}')">
              <span class="text-xs font-semibold text-fg-200">${escapeHtml(kl.domain)}</span>
              <span class="text-[10px] text-brand-amber ml-2">${kl.people_before} → ${kl.people_after} people</span>
              <div class="text-[10px] text-fg-600">${escapeHtml(humanize(kl.description))}</div>
            </div>`).join('')}
        </div>` : ''}

      ${report.new_bottlenecks.length > 0 ? `
        <div>
          <div class="text-[10px] uppercase text-fg-500 font-semibold mb-2">New Bottlenecks (${report.new_bottlenecks.length})</div>
          ${report.new_bottlenecks.map(nb => `
            <div class="p-2 rounded-lg bg-brand-purple/[0.04] border border-brand-purple/10 mb-1">
              <span class="text-xs font-semibold text-fg-200">${escapeHtml(nb.person || nb.description)}</span>
              <div class="text-[10px] text-fg-600">${escapeHtml(humanize(nb.description))}</div>
            </div>`).join('')}
        </div>` : ''}

      ${report.law_violations.length > 0 ? `
        <div>
          <div class="text-[10px] uppercase text-fg-500 font-semibold mb-2">Law Violations (${report.law_violations.length})</div>
          ${report.law_violations.map(lv => `
            <div class="p-2 rounded-lg bg-brand-rose/[0.04] border border-brand-rose/10 mb-1 cursor-pointer" onclick="openDrilldown('law', '${escapeJs(lv.law_code)}')">
              <span class="text-xs font-semibold text-fg-200">${escapeHtml(lv.law_code)}</span>
              <span class="text-[10px] text-fg-600 ml-2">${escapeHtml(humanize(lv.description))}</span>
            </div>`).join('')}
        </div>` : ''}

      ${Object.keys(report.velocity_change).length > 0 ? `
        <div class="grid grid-cols-2 gap-3">
          <div class="p-3 rounded-lg bg-white/[0.02]">
            <div class="text-[10px] uppercase text-fg-500">Velocity</div>
            <div class="text-sm font-bold ${report.velocity_change.velocity_direction === 'improved' ? 'text-brand-cyan' : 'text-brand-rose'} mono">${report.velocity_change.velocity_before}d → ${report.velocity_change.velocity_after}d</div>
          </div>
          <div class="p-3 rounded-lg bg-white/[0.02]">
            <div class="text-[10px] uppercase text-fg-500">P1 Risk</div>
            <div class="text-sm font-bold mono">${report.velocity_change.p1_risk_before} → ${report.velocity_change.p1_risk_after}</div>
          </div>
        </div>` : ''}

      <div>
        <div class="text-[10px] uppercase text-fg-500 font-semibold mb-2">Recommendations</div>
        ${report.recommendations.map(r => `
          <div class="p-2 rounded-lg bg-white/[0.02] border border-white/[0.04] mb-1">
            <div class="flex items-center gap-2">
              <span class="tag ${r.priority === 'urgent' ? 'tag-rose' : r.priority === 'high' ? 'tag-amber' : 'tag-gray'}">${escapeHtml(r.priority)}</span>
              <span class="text-xs font-semibold text-fg-200">${escapeHtml(r.action)}</span>
            </div>
            <div class="text-[10px] text-fg-600 mt-1">${escapeHtml(r.reason)}</div>
          </div>`).join('')}
      </div>
    </div>
  `;
}

window.addEventListener('load', () => {
  setTimeout(checkForRunningImports, 1000);
  checkDemoMode();
});

// ─── Demo-mode banner ─────────────────────────────────────────────────────
// Check if the OEM is running with demo seed data and show a prominent
// banner if so. This makes demo mode unmistakable — not just a flag in
// settings that a careful reader could find.
async function checkDemoMode() {
  try {
    const data = await api.getOEM('/dashboard');
    // The dashboard response includes the connected providers. If the demo
    // seed is active, the OEM has signals from the demo providers (github,
    // jira, slack, confluence, gmail, customer) but no real OAuth connections.
    // We check /api/oauth/status to see if ANY provider is really connected.
    const oauthResp = await fetch((MAESTRO_API || '') + '/api/oauth/status');
    const oauthData = await oauthResp.json();
    const providers = oauthData.providers || [];
    const anyConnected = providers.some(p => p.connected);
    // If no real OAuth connection exists AND the OEM has signals, the data
    // must be from the demo seed.
    const hasSignals = data.metrics && data.metrics.signals_processed > 0;
    if (hasSignals && !anyConnected) {
      const banner = document.getElementById('demo-banner');
      if (banner) banner.style.display = 'block';
    }
  } catch (e) {
    // If the check fails, don't show the banner — fail open (the app still works).
  }
}
// ═══════════════════════════════════════════════════════════════════════════