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
    el.innerHTML = `<div class="calm-empty" style="text-align:center;padding:48px 20px;">
      <div style="font-size:16px;font-weight:700;color:var(--maestro-black,var(--text-primary));font-family:'Montserrat',sans-serif;">Coordination Engine</div>
      <div style="font-size:13px;color:var(--maestro-gray-mid,var(--text-muted));margin-top:4px;">Failed to load: ${escapeHtml(e.message)}</div>
    </div>`;
  }
}

function renderCoordinationSurface(el, requests) {
  let html = `<div style="max-width:700px;margin:0 auto;font-family:'Montserrat',sans-serif;">`;

  // Header
  html += `
    <div style="margin-bottom:20px;">
      <div style="font-size:18px;font-weight:800;color:var(--maestro-black,var(--text-primary));">Coordination Engine</div>
      <div style="font-size:13px;color:var(--maestro-gray-mid,var(--text-muted));margin-top:4px;">Coordinate multi-team input for decisions without scheduling a meeting.</div>
    </div>
  `;

  // Initiate form
  html += `
    <div class="maestro-card" style="margin-bottom:20px;">
      <div style="font-size:14px;font-weight:700;color:var(--maestro-black,var(--text-primary));margin-bottom:12px;">Initiate a coordination request</div>
      <input type="text" class="maestro-input" id="coord-decision-input"
             placeholder="e.g., Standardize OAuth across all services"
             onkeydown="if(event.key==='Enter') initiateCoordination()"
             style="width:100%;padding:10px 14px;background:var(--maestro-gray-light,#F5F5F5);border:1px solid var(--divider,#E5E5E5);border-radius:8px;color:var(--maestro-black,var(--text-primary));font-size:14px;font-family:'Montserrat',sans-serif;outline:none;margin-bottom:12px;" />
      <button class="maestro-btn maestro-btn-full" id="coord-initiate-btn"
              style="font-size:14px;min-height:44px;">
        Initiate coordination
      </button>
    </div>
  `;

  // Active requests
  if (requests.length > 0) {
    html += `<div style="font-size:14px;font-weight:800;color:var(--maestro-black,var(--text-primary));margin-bottom:12px;">Active requests (${requests.length})</div>`;
    requests.forEach(req => {
      const status = req.status || 'open';
      const statusColor = status === 'synthesized' ? 'var(--maestro-success,#00C853)' : 'var(--maestro-warning,#FF9800)';
      const teamCount = (req.affected_teams || []).length;
      const responseCount = (req.responses || []).length;

      html += `
        <div class="maestro-card" style="margin-bottom:12px;cursor:pointer;" data-action="viewCoordination" data-args='["${escapeJs(req.request_id)}"]'>
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">
            <div style="flex:1;">
              <div style="display:inline-block;padding:3px 10px;border-radius:999px;background:${statusColor}20;color:${statusColor};font-size:11px;font-weight:800;margin-bottom:8px;text-transform:uppercase;">${escapeHtml(status)}</div>
              <div style="font-size:15px;font-weight:700;color:var(--maestro-black,var(--text-primary));line-height:1.4;">${escapeHtml(humanize(req.decision || ''))}</div>
              <div style="display:flex;gap:12px;margin-top:6px;font-size:12px;color:var(--maestro-gray-mid,var(--text-muted));font-weight:600;">
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
      <div class="calm-empty" style="text-align:center;padding:32px 20px;">
        <div style="font-size:16px;font-weight:700;color:var(--maestro-black,var(--text-primary));font-family:'Montserrat',sans-serif;">No coordination requests yet.</div>
        <div style="font-size:13px;color:var(--maestro-gray-mid,var(--text-muted));margin-top:4px;">Initiate one above to coordinate multi-team input for a decision.</div>
      </div>
    `;
  }

  // Withdrawal path
  html += `
    <div style="margin-top:24px;padding:12px 16px;background:var(--maestro-gray-light,#F5F5F5);border-radius:8px;font-size:12px;color:var(--maestro-gray-dark,var(--text-secondary));line-height:1.5;">
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
  let html = `<div style="max-width:700px;margin:0 auto;font-family:'Montserrat',sans-serif;">`;

  // Back button
  html += `<button class="maestro-btn maestro-btn-ghost" style="font-size:13px;min-height:36px;margin-bottom:16px;" id="coord-back-btn">← Back to coordination</button>`;

  // Decision
  html += `
    <div style="margin-bottom:20px;">
      <div style="font-size:18px;font-weight:800;color:var(--maestro-black,var(--text-primary));">${escapeHtml(humanize(req.decision || ''))}</div>
      <div style="font-size:12px;color:var(--maestro-gray-mid,var(--text-muted));margin-top:4px;">Initiated by ${escapeHtml(req.initiated_by || 'CEO')} · ${escapeHtml(req.created_at || '')}</div>
    </div>
  `;

  // Affected teams
  const teams = req.affected_teams || [];
  if (teams.length > 0) {
    html += `<div style="font-size:14px;font-weight:800;margin-bottom:12px;">Affected teams (${teams.length})</div>`;
    teams.forEach(team => {
      html += `
        <div class="maestro-card" style="margin-bottom:8px;padding:10px 14px;">
          <div style="font-size:14px;font-weight:700;color:var(--maestro-black,var(--text-primary));">${escapeHtml(team.team || team)}</div>
          <div style="font-size:12px;color:var(--maestro-gray-mid,var(--text-muted));margin-top:2px;">${escapeHtml((team.domains || []).join(', '))}</div>
        </div>
      `;
    });
  }

  // Contacts
  const contacts = req.contacts || [];
  if (contacts.length > 0) {
    html += `<div style="font-size:14px;font-weight:800;margin-top:20px;margin-bottom:12px;">Contacts (${contacts.length})</div>`;
    contacts.forEach(c => {
      html += `
        <div class="maestro-card" style="margin-bottom:8px;padding:10px 14px;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <div>
              <div style="font-size:14px;font-weight:700;color:var(--maestro-black,var(--text-primary));">${escapeHtml(c.email || '')}</div>
              <div style="font-size:12px;color:var(--maestro-gray-mid,var(--text-muted));">${escapeHtml(c.team || '')} · ${escapeHtml(c.role || '')}</div>
            </div>
          </div>
        </div>
      `;
    });
  }

  // Responses
  const responses = req.responses || [];
  if (responses.length > 0) {
    html += `<div style="font-size:14px;font-weight:800;margin-top:20px;margin-bottom:12px;">Responses (${responses.length})</div>`;
    responses.forEach(r => {
      html += `
        <div class="maestro-card" style="margin-bottom:8px;padding:12px 14px;border-left:4px solid var(--maestro-yellow,#FFC629);">
          <div style="font-size:13px;font-weight:700;color:var(--maestro-black,var(--text-primary));">${escapeHtml(r.from || '')} — ${escapeHtml(r.team || '')}</div>
          <div style="font-size:13px;color:var(--maestro-gray-dark,var(--text-secondary));margin-top:4px;line-height:1.5;">${escapeHtml(humanize(r.response || ''))}</div>
        </div>
      `;
    });
  }

  // Synthesis
  if (req.synthesis) {
    html += `
      <div style="margin-top:24px;padding:16px;background:var(--maestro-yellow-light,#FFF4D1);border-radius:12px;">
        <div style="font-size:14px;font-weight:800;color:var(--maestro-yellow-dark,#F0B500);margin-bottom:8px;">Synthesized recommendation</div>
        <div style="font-size:14px;color:var(--maestro-black,var(--text-primary));line-height:1.55;">${escapeHtml(humanize(req.synthesis.recommendation || ''))}</div>
        ${req.synthesis.consensus ? `<div style="font-size:12px;color:var(--maestro-gray-mid,var(--text-muted));margin-top:8px;">Consensus: ${Math.round(req.synthesis.consensus * 100)}%</div>` : ''}
      </div>
    `;
  }

  // Response form
  html += `
    <div class="maestro-card" style="margin-top:20px;">
      <div style="font-size:14px;font-weight:700;margin-bottom:12px;">Add a response</div>
      <textarea id="coord-response-input" placeholder="Enter your team's input on this decision…"
                style="width:100%;min-height:80px;padding:10px 14px;background:var(--maestro-gray-light,#F5F5F5);border:1px solid var(--divider,#E5E5E5);border-radius:8px;color:var(--maestro-black,var(--text-primary));font-size:14px;font-family:'Montserrat',sans-serif;outline:none;margin-bottom:12px;resize:vertical;"></textarea>
      <button class="maestro-btn maestro-btn-full" id="coord-respond-btn"
              style="font-size:14px;min-height:44px;">
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
