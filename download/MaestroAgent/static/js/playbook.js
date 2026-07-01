// V8 Daily Work #6 — Role-Specific Playbooks surface.
// Accessible via command palette (Ctrl+K) — NOT in the sidebar.
// Formats the same evidence differently for sales, marketing, and product.

const _playbookRoles = [
  { id: 'sales', label: 'Sales Playbook — outreach + talking points', icon: '🎯' },
  { id: 'marketing', label: 'Marketing Playbook — ROI view', icon: '📊' },
  { id: 'product', label: 'Product Playbook — PRD + tickets', icon: '📋' },
];

function loadPlaybook(role) {
  const el = document.getElementById('playbook-content');
  if (!el) return;
  el.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Loading playbook…</div>';
  api.getOEM(`/playbook/${role}`)
    .then(data => renderPlaybook(el, role, data))
    .catch(e => {
      el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
    });
}

function renderPlaybook(el, role, data) {
  let html = `
    <div class="meta-surface">
      <div class="meta-surface greeting">${escapeHtml(role.charAt(0).toUpperCase() + role.slice(1))} Playbook</div>
      <div class="meta-surface sub-greeting">Role-specific evidence formatting — not a new engine, just the right view for your role.</div>

      <div style="margin-top:24px;display:flex;gap:8px;flex-wrap:wrap;">
        ${_playbookRoles.map(r => `
          <button class="ds-btn ${r.id === role ? 'ds-btn-primary' : 'ds-btn-ghost'} ds-btn-small" onclick="loadPlaybook('${r.id}')">
            ${r.icon} ${escapeHtml(r.label.split(' — ')[0])}
          </button>
        `).join('')}
      </div>

      <div style="margin-top:24px;">
        <input type="text" class="ask-input" id="playbook-context"
               placeholder="Context (customer name for sales, campaign for marketing, feature for product)…"
               onkeydown="if(event.key==='Enter') loadPlaybookWithContext('${role}', this.value)"
               aria-label="Playbook context" />
      </div>
    </div>
  `;

  if (data.error) {
    html += `<div class="ds-empty" style="margin-top:24px;">${escapeHtml(humanize(data.error))}</div>`;
    el.innerHTML = html;
    return;
  }

  // Role-specific rendering
  if (role === 'sales') {
    html += renderSalesPlaybook(data);
  } else if (role === 'marketing') {
    html += renderMarketingPlaybook(data);
  } else if (role === 'product') {
    html += renderProductPlaybook(data);
  }

  el.innerHTML = html;
}

function renderSalesPlaybook(data) {
  const outreach = data.drafted_outreach || {};
  let html = `
    <div class="story-card" style="margin-top:24px;">
      <div class="story-narrative" style="font-weight:500;color:var(--accent);margin-bottom:12px;">
        Drafted Outreach — ${escapeHtml(data.customer || 'Unknown Customer')}
      </div>
  `;

  if (outreach.body) {
    html += `
      <div style="padding:14px;background:var(--surface-2);border-radius:8px;font-size:13px;color:var(--text-secondary);white-space:pre-wrap;line-height:1.6;margin-bottom:16px;">
${escapeHtml(outreach.body)}
      </div>
    `;
    if (outreach.talking_points && outreach.talking_points.length > 0) {
      html += `<div class="ds-cascade-label" style="margin-bottom:8px;">Talking Points</div>`;
      html += outreach.talking_points.map(tp => `
        <div style="padding:8px 12px;background:var(--surface-2);border-radius:6px;margin-bottom:6px;font-size:13px;color:var(--text-secondary);">
          • ${escapeHtml(humanize(tp))}
        </div>
      `).join('');
    }
  }

  html += `
    <div class="ds-meta" style="margin-top:16px;">
      ${data.customer_signal_count || 0} customer signals · ARR at stake: $${(data.arr_at_stake || 0).toLocaleString()}
    </div>
    <div style="margin-top:8px;font-size:13px;color:var(--accent);">${escapeHtml(humanize(data.next_best_action || ''))}</div>
  `;

  // Execute button — create Gmail draft from the outreach
  if (outreach.body) {
    html += `
      <div style="margin-top:16px;">
        <button class="ds-btn ds-btn-primary ds-btn-small" onclick="executeWriteBack('gmail','create_draft',{to:'${escapeHtml(outreach.to || '')}',subject:'${escapeHtml(outreach.subject || '').replace(/'/g, "\\'")}',body:'${escapeHtml(outreach.body || '').replace(/'/g, "\\'").replace(/\n/g, '\\n')}'})">
          Create Gmail Draft from Outreach
        </button>
      </div>
    `;
  }

  html += `</div>`;
  return html;
}

function renderMarketingPlaybook(data) {
  let html = `
    <div class="story-card" style="margin-top:24px;">
      <div class="story-narrative" style="font-weight:500;color:var(--accent);margin-bottom:12px;">
        Marketing ROI — ${data.campaigns ? data.campaigns.length : 0} Campaigns
      </div>
  `;

  if (data.campaigns && data.campaigns.length > 0) {
    html += `
      <table style="width:100%;font-size:12px;border-collapse:collapse;margin-bottom:16px;">
        <thead>
          <tr style="border-bottom:1px solid var(--divider);text-align:left;color:var(--text-muted);">
            <th style="padding:8px;">Campaign</th>
            <th style="padding:8px;">Spend</th>
            <th style="padding:8px;">Conversions</th>
            <th style="padding:8px;">CPA</th>
            <th style="padding:8px;">ROI</th>
          </tr>
        </thead>
        <tbody>
          ${data.campaigns.map(c => `
            <tr style="border-bottom:1px solid var(--divider);">
              <td style="padding:8px;color:var(--text-primary);">${escapeHtml(c.name)}</td>
              <td style="padding:8px;color:var(--text-secondary);">$${c.spend.toLocaleString()}</td>
              <td style="padding:8px;color:var(--text-secondary);">${c.conversions}</td>
              <td style="padding:8px;color:var(--text-secondary);">$${c.cpa.toFixed(2)}</td>
              <td style="padding:8px;color:${c.roi >= 0 ? 'var(--positive,#16A34A)' : 'var(--risk,#DC2626)'};">${(c.roi * 100).toFixed(0)}%</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  }

  html += `
    <div class="ds-meta" style="margin-top:12px;">
      Total spend: $${(data.total_spend || 0).toLocaleString()} · Total conversions: ${data.total_conversions || 0} · Overall CPA: $${(data.overall_cpa || 0).toFixed(2)}
    </div>
    <div style="margin-top:8px;font-size:13px;color:var(--accent);">${escapeHtml(humanize(data.recommendation || ''))}</div>
  `;

  html += `</div>`;
  return html;
}

function renderProductPlaybook(data) {
  let html = `
    <div class="story-card" style="margin-top:24px;">
      <div class="story-narrative" style="font-weight:500;color:var(--accent);margin-bottom:12px;">
        PRD Outline — ${escapeHtml(data.feature || 'New Feature')}
      </div>
  `;

  if (data.prd_outline) {
    html += data.prd_outline.sections.map(s => `
      <div style="margin-bottom:16px;">
        <div class="ds-cascade-label" style="margin-bottom:6px;">${escapeHtml(s.title)}</div>
        <div style="padding:10px 14px;background:var(--surface-2);border-radius:6px;font-size:13px;color:var(--text-secondary);white-space:pre-wrap;line-height:1.5;">
          ${escapeHtml(humanize(s.content || ''))}
        </div>
      </div>
    `).join('');
  }

  if (data.drafted_tickets && data.drafted_tickets.length > 0) {
    html += `<div class="ds-cascade-label" style="margin-top:16px;margin-bottom:8px;">Drafted Tickets (${data.drafted_tickets.length})</div>`;
    html += data.drafted_tickets.map(t => `
      <div style="padding:10px 12px;background:var(--surface-2);border-radius:6px;margin-bottom:6px;">
        <div style="font-size:13px;color:var(--text-primary);font-weight:500;">${escapeHtml(humanize(t.summary || ''))}</div>
        <div class="ds-meta" style="margin-top:4px;">Priority: ${escapeHtml(t.priority || 'medium')}</div>
      </div>
    `).join('');
  }

  if (data.unresolved_concerns && data.unresolved_concerns.length > 0) {
    html += `<div class="ds-cascade-label" style="margin-top:16px;margin-bottom:8px;color:var(--warning,#D97706);">Unresolved Concerns (${data.unresolved_concerns.length})</div>`;
    html += data.unresolved_concerns.map(c => `
      <div style="padding:10px 12px;background:rgba(217,119,6,0.05);border:1px solid rgba(217,119,6,0.18);border-radius:6px;margin-bottom:6px;">
        <div style="font-size:13px;color:var(--text-secondary);">${escapeHtml(humanize(c.concern || ''))}</div>
        <div class="ds-meta" style="margin-top:4px;">Raised by: ${escapeHtml(c.raised_by || 'unknown')}</div>
      </div>
    `).join('');
  }

  // Execute button — create Jira tickets from drafted tickets
  if (data.drafted_tickets && data.drafted_tickets.length > 0) {
    const firstTicket = data.drafted_tickets[0];
    html += `
      <div style="margin-top:16px;">
        <button class="ds-btn ds-btn-primary ds-btn-small" onclick="executeWriteBack('jira','create_issue',{project:'PROD',summary:'${escapeHtml(firstTicket.summary || '').replace(/'/g, "\\'")}',description:'${escapeHtml(firstTicket.description || '').replace(/'/g, "\\'")}',issue_type:'Task'})">
          Create Jira Ticket from First Draft
        </button>
      </div>
    `;
  }

  html += `</div>`;
  return html;
}

function loadPlaybookWithContext(role, context) {
  const el = document.getElementById('playbook-content');
  if (!el) return;
  el.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Loading playbook…</div>';
  api.getOEM(`/playbook/${role}?context=${encodeURIComponent(context)}`)
    .then(data => renderPlaybook(el, role, data))
    .catch(e => {
      el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
    });
}
