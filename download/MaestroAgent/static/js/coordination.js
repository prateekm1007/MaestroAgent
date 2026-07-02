// Round 59 — Coordination Engine UI surface.
// Lets the CEO initiate a coordination request, see affected teams,
// collect responses, and view the synthesized recommendation.
// Accessed via the command palette (Ctrl+K), NOT a sidebar item (V5 litmus).

async function loadCoordination() {
  const el = document.getElementById('coordination-content') || document.getElementById('main-content');
  if (!el) return;
  el.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Loading coordination requests…</div>';

  try {
    const [active, all] = await Promise.all([
      api.getOEM('/coordinate').catch(() => ({ requests: [] })),
      api.getOEM('/coordinate').catch(() => ({ requests: [] })),
    ]);

    const requests = (all.requests || []);
    renderCoordinationSurface(el, requests);
  } catch (e) {
    el.innerHTML = `<div class="calm-empty" class="auto-text-center-p4820">
      <div class="auto-fs16-fw700-text-primary-2">Coordination Engine</div>
      <div class="auto-fs13-text-muted-mt4">Failed to load: ${escapeHtml(e.message)}</div>
    </div>`;
  }
}

function renderCoordinationSurface(el, requests) {
  let html = `<div class="auto-mw700-m0auto">`;

  // Header
  html += `
    <div class="auto-mb20">
      <div class="auto-fs18-fw800-text-primary">Coordination Engine</div>
      <div class="auto-fs13-text-muted-mt4">Coordinate multi-team input for decisions without scheduling a meeting.</div>
    </div>
  `;

  // Initiate form
  html += `
    <div class="maestro-card" class="auto-mb20">
      <div class="auto-fs14-fw700-text-primary-mb12">Initiate a coordination request</div>
      <input type="text" class="maestro-input" id="coord-decision-input"
             placeholder="e.g., Standardize OAuth across all services"
             onkeydown="if(event.key==='Enter') initiateCoordination()"
             class="auto-w-full-p1014-bg-muted-border-default" />
      <button class="maestro-btn maestro-btn-full" id="coord-initiate-btn"
              class="auto-fs14-minh44">
        Initiate coordination
      </button>
    </div>
  `;

  // Active requests
  if (requests.length > 0) {
    html += `<div class="auto-fs14-fw800-text-primary-mb12">Active requests (${requests.length})</div>`;
    requests.forEach(req => {
      const status = req.status || 'open';
      const statusColor = status === 'synthesized' ? 'var(--maestro-success,#00C853)' : 'var(--maestro-warning,#FF9800)';
      const teamCount = (req.affected_teams || []).length;
      const responseCount = (req.responses || []).length;

      html += `
        <div class="maestro-card" class="auto-mb12-cursor-pointer" data-action="viewCoordination" data-args='["${escapeJs(req.request_id)}"]'>
          <div class="auto-flex-u-daae-u-b505-gap12">
            <div class="auto-flex-1">
              <div class="auto-inline-block-p310-rad999-bg-98ab">${escapeHtml(status)}</div>
              <div class="auto-fs15-fw700-text-primary-lh14">${escapeHtml(humanize(req.decision || ''))}</div>
              <div class="auto-flex-gap12-mt6-fs12">
                <span>👥 ${teamCount} team${teamCount === 1 ? '' : 's'}</span>
                <span>💬 ${responseCount} response${responseCount === 1 ? '' : 's'}</span>
              </div>
            </div>
          </div>
        </div>
      `;
    });
  } else {
    html += `
      <div class="calm-empty" class="auto-text-center-p3220">
        <div class="auto-fs16-fw700-text-primary-2">No coordination requests yet.</div>
        <div class="auto-fs13-text-muted-mt4">Initiate one above to coordinate multi-team input for a decision.</div>
      </div>
    `;
  }

  // Withdrawal path
  html += `
    <div class="auto-mt24-p1216-bg-muted-rad8">
      <strong>Withdrawal path:</strong> You can make decisions without coordination — schedule a meeting instead. This tool saves time; without it, you are slower but functional.
    </div>
  `;

  html += `</div>`;
  el.innerHTML = html;

  // Wire the initiate button via addEventListener (CSP-safe)
  const btn = document.getElementById('coord-initiate-btn');
  if (btn) {
    btn.addEventListener('click', initiateCoordination);
  }
}

async function initiateCoordination() {
  const input = document.getElementById('coord-decision-input');
  if (!input || !input.value.trim()) return;
  const decision = input.value.trim();

  try {
    const result = await api.postOEM('/coordinate', {
      decision: decision,
      initiated_by: 'ceo@acme.com',
    });
    // Reload to show the new request
    loadCoordination();
  } catch (e) {
    alert('Failed to initiate coordination: ' + e.message);
  }
}

async function viewCoordination(requestId) {
  const el = document.getElementById('coordination-content') || document.getElementById('main-content');
  if (!el || !requestId) return;
  el.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Loading coordination request…</div>';

  try {
    const req = await api.getOEM(`/coordinate/${encodeURIComponent(requestId)}`);
    renderCoordinationDetail(el, req);
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

function renderCoordinationDetail(el, req) {
  let html = `<div class="auto-mw700-m0auto">`;

  // Back button
  html += `<button class="maestro-btn maestro-btn-ghost" class="auto-fs13-minh36-mb16" id="coord-back-btn">← Back to coordination</button>`;

  // Decision
  html += `
    <div class="auto-mb20">
      <div class="auto-fs18-fw800-text-primary">${escapeHtml(humanize(req.decision || ''))}</div>
      <div class="auto-fs12-text-muted-mt4">Initiated by ${escapeHtml(req.initiated_by || 'CEO')} · ${escapeHtml(req.created_at || '')}</div>
    </div>
  `;

  // Affected teams
  const teams = req.affected_teams || [];
  if (teams.length > 0) {
    html += `<div class="auto-fs14-fw800-mb12">Affected teams (${teams.length})</div>`;
    teams.forEach(team => {
      html += `
        <div class="maestro-card" class="auto-mb8-p1014">
          <div class="auto-fs14-fw700-text-primary">${escapeHtml(team.team || team)}</div>
          <div class="auto-fs12-text-muted-mt2">${escapeHtml((team.domains || []).join(', '))}</div>
        </div>
      `;
    });
  }

  // Contacts
  const contacts = req.contacts || [];
  if (contacts.length > 0) {
    html += `<div class="auto-fs14-fw800-mt20-mb12">Contacts (${contacts.length})</div>`;
    contacts.forEach(c => {
      html += `
        <div class="maestro-card" class="auto-mb8-p1014">
          <div class="auto-flex-u-daae-u-1e2c">
            <div>
              <div class="auto-fs14-fw700-text-primary">${escapeHtml(c.email || '')}</div>
              <div class="auto-fs12-text-muted">${escapeHtml(c.team || '')} · ${escapeHtml(c.role || '')}</div>
            </div>
          </div>
        </div>
      `;
    });
  }

  // Responses
  const responses = req.responses || [];
  if (responses.length > 0) {
    html += `<div class="auto-fs14-fw800-mt20-mb12">Responses (${responses.length})</div>`;
    responses.forEach(r => {
      html += `
        <div class="maestro-card" class="auto-mb8-p1214-u-61ed">
          <div class="auto-fs13-fw700-text-primary">${escapeHtml(r.from || '')} — ${escapeHtml(r.team || '')}</div>
          <div class="auto-fs13-text-secondary-mt4-lh15">${escapeHtml(humanize(r.response || ''))}</div>
        </div>
      `;
    });
  }

  // Synthesis
  if (req.synthesis) {
    html += `
      <div class="auto-mt24-p16-bg-accent-rad12">
        <div class="auto-fs14-fw800-text-accent-mb8">Synthesized recommendation</div>
        <div class="auto-fs14-text-primary-lh155">${escapeHtml(humanize(req.synthesis.recommendation || ''))}</div>
        ${req.synthesis.consensus ? `<div class="auto-fs12-text-muted-mt8">Consensus: ${Math.round(req.synthesis.consensus * 100)}%</div>` : ''}
      </div>
    `;
  }

  // Response form
  html += `
    <div class="maestro-card" class="auto-mt20">
      <div class="auto-fs14-fw700-mb12">Add a response</div>
      <textarea id="coord-response-input" placeholder="Enter your team's input on this decision…"
                class="auto-w-full-minh80-p1014-bg-muted"></textarea>
      <button class="maestro-btn maestro-btn-full" id="coord-respond-btn"
              class="auto-fs14-minh44">
        Submit response
      </button>
    </div>
  `;

  html += `</div>`;
  el.innerHTML = html;

  // Wire buttons
  const backBtn = document.getElementById('coord-back-btn');
  if (backBtn) backBtn.addEventListener('click', loadCoordination);
  const respondBtn = document.getElementById('coord-respond-btn');
  if (respondBtn) {
    respondBtn.addEventListener('click', async () => {
      const input = document.getElementById('coord-response-input');
      if (!input || !input.value.trim()) return;
      try {
        await api.postOEM(`/coordinate/${encodeURIComponent(req.request_id)}/respond`, {
          from: 'ceo@acme.com',
          team: 'leadership',
          response: input.value.trim(),
        });
        viewCoordination(req.request_id); // reload
      } catch (e) {
        alert('Failed to submit response: ' + e.message);
      }
    });
  }
}
