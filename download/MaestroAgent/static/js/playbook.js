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

      <div class="auto-mt24-flex-gap8-u-9012">
        ${_playbookRoles.map(r => `
          <button class="ds-btn ${r.id === role ? 'ds-btn-primary' : 'ds-btn-ghost'} ds-btn-small" onclick="loadPlaybook('${r.id}')">
            ${r.icon} ${escapeHtml(r.label.split(' — ')[0])}
          </button>
        `).join('')}
      </div>

      <div class="auto-mt24">
        <input type="text" class="ask-input" id="playbook-context"
               placeholder="Context (customer name for sales, campaign for marketing, feature for product)…"
               onkeydown="if(event.key==='Enter') loadPlaybookWithContext('${role}', this.value)"
               aria-label="Playbook context" />
      </div>
    </div>
  `;

  if (data.error) {
    html += `<div class="ds-empty" class="auto-mt24">${escapeHtml(humanize(data.error))}</div>`;
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
    <div class="story-card" class="auto-mt24">
      <div class="story-narrative" class="auto-fw500-text-accent-mb12">
        Drafted Outreach — ${escapeHtml(data.customer || 'Unknown Customer')}
      </div>
  `;

  if (outreach.body) {
    html += `
      <div class="auto-p14-bg-surface-rad8-fs13-2">
${escapeHtml(outreach.body)}
      </div>
    `;
    if (outreach.talking_points && outreach.talking_points.length > 0) {
      html += `<div class="ds-cascade-label" class="auto-mb8">Talking Points</div>`;
      html += outreach.talking_points.map(tp => `
        <div class="auto-p812-bg-surface-rad6-mb6">
          • ${escapeHtml(humanize(tp))}
        </div>
      `).join('');
    }
  }

  html += `
    <div class="ds-meta" class="auto-mt16">
      ${data.customer_signal_count || 0} customer signals · ARR at stake: $${(data.arr_at_stake || 0).toLocaleString()}
    </div>
    <div class="auto-mt8-fs13-text-accent">${escapeHtml(humanize(data.next_best_action || ''))}</div>
  `;

  // Execute button — create Gmail draft from the outreach
  if (outreach.body) {
    html += `
      <div class="auto-mt16">
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
    <div class="story-card" class="auto-mt24">
      <div class="story-narrative" class="auto-fw500-text-accent-mb12">
        Marketing ROI — ${data.campaigns ? data.campaigns.length : 0} Campaigns
      </div>
  `;

  if (data.campaigns && data.campaigns.length > 0) {
    html += `
      <table class="auto-w-full-fs12-u-be09-mb16">
        <thead>
          <tr class="auto-u-4300-u-200a-text-muted">
            <th class="auto-p8">Campaign</th>
            <th class="auto-p8">Spend</th>
            <th class="auto-p8">Conversions</th>
            <th class="auto-p8">CPA</th>
            <th class="auto-p8">ROI</th>
          </tr>
        </thead>
        <tbody>
          ${data.campaigns.map(c => `
            <tr class="auto-u-4300">
              <td class="auto-p8-text-primary">${escapeHtml(c.name)}</td>
              <td class="auto-p8-text-secondary">$${c.spend.toLocaleString()}</td>
              <td class="auto-p8-text-secondary">${c.conversions}</td>
              <td class="auto-p8-text-secondary">$${c.cpa.toFixed(2)}</td>
              <td class="auto-p8-text-positive">${(c.roi * 100).toFixed(0)}%</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  }

  html += `
    <div class="ds-meta" class="auto-mt12">
      Total spend: $${(data.total_spend || 0).toLocaleString()} · Total conversions: ${data.total_conversions || 0} · Overall CPA: $${(data.overall_cpa || 0).toFixed(2)}
    </div>
    <div class="auto-mt8-fs13-text-accent">${escapeHtml(humanize(data.recommendation || ''))}</div>
  `;

  html += `</div>`;
  return html;
}

function renderProductPlaybook(data) {
  let html = `
    <div class="story-card" class="auto-mt24">
      <div class="story-narrative" class="auto-fw500-text-accent-mb12">
        PRD Outline — ${escapeHtml(data.feature || 'New Feature')}
      </div>
  `;

  if (data.prd_outline) {
    html += data.prd_outline.sections.map(s => `
      <div class="auto-mb16">
        <div class="ds-cascade-label" class="auto-mb6">${escapeHtml(s.title)}</div>
        <div class="auto-p1014-bg-surface-rad6-fs13">
          ${escapeHtml(humanize(s.content || ''))}
        </div>
      </div>
    `).join('');
  }

  if (data.drafted_tickets && data.drafted_tickets.length > 0) {
    html += `<div class="ds-cascade-label" class="auto-mt16-mb8">Drafted Tickets (${data.drafted_tickets.length})</div>`;
    html += data.drafted_tickets.map(t => `
      <div class="auto-p1012-bg-surface-rad6-mb6">
        <div class="auto-fs13-text-primary-fw500">${escapeHtml(humanize(t.summary || ''))}</div>
        <div class="ds-meta" class="auto-mt4">Priority: ${escapeHtml(t.priority || 'medium')}</div>
      </div>
    `).join('');
  }

  if (data.unresolved_concerns && data.unresolved_concerns.length > 0) {
    html += `<div class="ds-cascade-label" class="auto-mt16-mb8-text-warning">Unresolved Concerns (${data.unresolved_concerns.length})</div>`;
    html += data.unresolved_concerns.map(c => `
      <div class="auto-p1012-bg-52dd-bd-f358-rad6">
        <div class="auto-fs13-text-secondary-2">${escapeHtml(humanize(c.concern || ''))}</div>
        <div class="ds-meta" class="auto-mt4">Raised by: ${escapeHtml(c.raised_by || 'unknown')}</div>
      </div>
    `).join('');
  }

  // Execute button — create Jira tickets from drafted tickets
  if (data.drafted_tickets && data.drafted_tickets.length > 0) {
    const firstTicket = data.drafted_tickets[0];
    html += `
      <div class="auto-mt16">
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
