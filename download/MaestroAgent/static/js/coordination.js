// Round 59 — Coordination Engine UI surface.
// Lets the CEO initiate a coordination request, see affected teams,
// collect responses, and view the synthesized recommendation.
// Accessed via the command palette (Ctrl+K), NOT a sidebar item (V5 litmus).

async function loadCoordination() {
  const el = document.getElementById('coordination-content') || document.getElementById('main-content');
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    const [active, all] = await Promise.all([
      api.getOEM('/coordinate').catch(() => ({ requests: [] })),
      api.getOEM('/coordinate').catch(() => ({ requests: [] })),
    ]);

    const requests = (all.requests || []);
    renderCoordinationSurface(el, requests);
  } catch (e) {
    el.innerHTML = `<div class="calm-empty b-text-center-9">
      <div class="b-fs16-fw700-2">Coordination Engine</div>
      <div class="caption-text">Failed to load: ${escapeHtml(e.message)}</div>
    </div>`;
  }
}

function renderCoordinationSurface(el, requests) {
  let html = `<div class="b-mw700-m0auto">`;

  // Header
  html += `
    <div class="b-mb20">
      <div class="b-fs18-fw800">Coordination Engine</div>
      <div class="caption-text">Coordinate multi-team input for decisions without scheduling a meeting.</div>
    </div>
  `;

  // Initiate form
  html += `
    <div class="maestro-card b-mb20">
      <div class="b-fs14-fw700-4">Initiate a coordination request</div>
      <input type="text" class="maestro-input" id="coord-decision-input"
             placeholder="e.g., Standardize OAuth across all services"
             onkeydown="if(event.key==='Enter') initiateCoordination()"
             class="b-w-full-6" />
      <button class="maestro-btn maestro-btn-full" id="coord-initiate-btn"
              class="b-fs14-minh44">
        Initiate coordination
      </button>
    </div>
  `;

  // Active requests
  if (requests.length > 0) {
    html += `<div class="b-fs14-fw800-4">Active requests (${requests.length})</div>`;
    requests.forEach(req => {
      const status = req.status || 'open';
      const statusColor = status === 'synthesized' ? 'var(--maestro-success,#00C853)' : 'var(--maestro-warning,#FF9800)';
      const teamCount = (req.affected_teams || []).length;
      const responseCount = (req.responses || []).length;

      html += `
        <div class="maestro-card b-mb12-cursor" data-action="viewCoordination" data-args='["${escapeJs(req.request_id)}"]'>
          <div class="b-flex-u-9">
            <div class="flex-1">
              <div class="b-inline-block-3">${escapeHtml(status)}</div>
              <div class="b-fs15-fw700">${escapeHtml(humanize(req.decision || ''))}</div>
              <div class="b-flex-gap12-2">
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
      <div class="calm-empty b-text-center-8">
        <div class="b-fs16-fw700-2">No coordination requests yet.</div>
        <div class="caption-text">Initiate one above to coordinate multi-team input for a decision.</div>
      </div>
    `;
  }

  // Withdrawal path
  html += `
    <div class="b-mt24-p1216">
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
    showToast('Failed to initiate coordination: ' + e.message, 'error');
  }
}

async function viewCoordination(requestId) {
  const el = document.getElementById('coordination-content') || document.getElementById('main-content');
  if (!el || !requestId) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    const req = await api.getOEM(`/coordinate/${encodeURIComponent(requestId)}`);
    renderCoordinationDetail(el, req);
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

function renderCoordinationDetail(el, req) {
  let html = `<div class="b-mw700-m0auto">`;

  // Back button
  html += `<button class="maestro-btn maestro-btn-ghost b-fs13-minh36" id="coord-back-btn">← Back to coordination</button>`;

  // Decision
  html += `
    <div class="b-mb20">
      <div class="b-fs18-fw800">${escapeHtml(humanize(req.decision || ''))}</div>
      <div class="b-fs12-text-9">Initiated by ${escapeHtml(req.initiated_by || 'CEO')} · ${escapeHtml(req.created_at || '')}</div>
    </div>
  `;

  // Affected teams
  const teams = req.affected_teams || [];
  if (teams.length > 0) {
    html += `<div class="b-fs14-fw800">Affected teams (${teams.length})</div>`;
    teams.forEach(team => {
      html += `
        <div class="maestro-card b-mb8-p1014">
          <div class="b-fs14-fw700-2">${escapeHtml(team.team || team)}</div>
          <div class="b-fs12-text-7">${escapeHtml((team.domains || []).join(', '))}</div>
        </div>
      `;
    });
  }

  // Contacts
  const contacts = req.contacts || [];
  if (contacts.length > 0) {
    html += `<div class="b-fs14-fw800-2">Contacts (${contacts.length})</div>`;
    contacts.forEach(c => {
      html += `
        <div class="maestro-card b-mb8-p1014">
          <div class="b-flex-u-7">
            <div>
              <div class="b-fs14-fw700-2">${escapeHtml(c.email || '')}</div>
              <div class="tag-text">${escapeHtml(c.team || '')} · ${escapeHtml(c.role || '')}</div>
            </div>
          </div>
        </div>
      `;
    });
  }

  // Responses
  const responses = req.responses || [];
  if (responses.length > 0) {
    html += `<div class="b-fs14-fw800-2">Responses (${responses.length})</div>`;
    responses.forEach(r => {
      html += `
        <div class="maestro-card b-mb8-p1214">
          <div class="b-fs13-fw700">${escapeHtml(r.from || '')} — ${escapeHtml(r.team || '')}</div>
          <div class="b-fs13-text-23">${escapeHtml(humanize(r.response || ''))}</div>
        </div>
      `;
    });
  }

  // Synthesis
  if (req.synthesis) {
    html += `
      <div class="b-mt24-p16">
        <div class="b-fs14-fw800-3">Synthesized recommendation</div>
        <div class="b-fs14-text-7">${escapeHtml(humanize(req.synthesis.recommendation || ''))}</div>
        ${req.synthesis.consensus ? `<div class="b-fs12-text-11">Consensus: ${Math.round(req.synthesis.consensus * 100)}%</div>` : ''}
      </div>
    `;
  }

  // Response form
  html += `
    <div class="maestro-card b-mt20">
      <div class="b-fs14-fw700">Add a response</div>
      <textarea id="coord-response-input" placeholder="Enter your team's input on this decision…"
                class="b-w-full-4"></textarea>
      <button class="maestro-btn maestro-btn-full" id="coord-respond-btn"
              class="b-fs14-minh44">
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
        showToast('Failed to submit response: ' + e.message, 'error');
      }
    });
  }
}
