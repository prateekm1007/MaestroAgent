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
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
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

      <div class="b-mt24-flex">
        ${_playbookRoles.map(r => `
          <button class="ds-btn ${r.id === role ? 'ds-btn-primary' : 'ds-btn-ghost'} ds-btn-small" onclick="loadPlaybook('${r.id}')">
            ${r.icon} ${escapeHtml(r.label.split(' — ')[0])}
          </button>
        `).join('')}
      </div>

      <div class="b-mt24">
        <input type="text" class="ask-input" id="playbook-context"
               placeholder="Context (customer name for sales, campaign for marketing, feature for product)…"
               onkeydown="if(event.key==='Enter') loadPlaybookWithContext('${role}', this.value)"
               aria-label="Playbook context" />
      </div>
    </div>
  `;

  if (data.error) {
    html += `<div class="ds-empty b-mt24">${escapeHtml(humanize(data.error))}</div>`;
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
    <div class="story-card b-mt24">
      <div class="story-narrative b-fw500-text">
        Drafted Outreach — ${escapeHtml(data.customer || 'Unknown Customer')}
      </div>
  `;

  if (outreach.body) {
    html += `
      <div class="b-p14-bg-4">
${escapeHtml(outreach.body)}
      </div>
    `;
    if (outreach.talking_points && outreach.talking_points.length > 0) {
      html += `<div class="ds-cascade-label mb-8">Talking Points</div>`;
      html += outreach.talking_points.map(tp => `
        <div class="b-p812-bg-2">
          • ${escapeHtml(humanize(tp))}
        </div>
      `).join('');
    }
  }

  html += `
    <div class="ds-meta mt-16">
      ${data.customer_signal_count || 0} customer signals · ARR at stake: $${(data.arr_at_stake || 0).toLocaleString()}
    </div>
    <div class="b-mt8-fs13-2">${escapeHtml(humanize(data.next_best_action || ''))}</div>
  `;

  // Execute button — create Gmail draft from the outreach
  if (outreach.body) {
    html += `
      <div class="mt-16">
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
    <div class="story-card b-mt24">
      <div class="story-narrative b-fw500-text">
        Marketing ROI — ${data.campaigns ? data.campaigns.length : 0} Campaigns
      </div>
  `;

  if (data.campaigns && data.campaigns.length > 0) {
    html += `
      <table class="b-w-full">
        <thead>
          <tr class="b-u-u">
            <th class="p-8">Campaign</th>
            <th class="p-8">Spend</th>
            <th class="p-8">Conversions</th>
            <th class="p-8">CPA</th>
            <th class="p-8">ROI</th>
          </tr>
        </thead>
        <tbody>
          ${data.campaigns.map(c => `
            <tr class="b-u-4300">
              <td class="b-p8-text-3">${escapeHtml(c.name)}</td>
              <td class="b-p8-text-4">$${c.spend.toLocaleString()}</td>
              <td class="b-p8-text-4">${c.conversions}</td>
              <td class="b-p8-text-4">$${c.cpa.toFixed(2)}</td>
              <td class="b-p8-text">${(c.roi * 100).toFixed(0)}%</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  }

  html += `
    <div class="ds-meta mt-12">
      Total spend: $${(data.total_spend || 0).toLocaleString()} · Total conversions: ${data.total_conversions || 0} · Overall CPA: $${(data.overall_cpa || 0).toFixed(2)}
    </div>
    <div class="b-mt8-fs13-2">${escapeHtml(humanize(data.recommendation || ''))}</div>
  `;

  html += `</div>`;
  return html;
}

function renderProductPlaybook(data) {
  let html = `
    <div class="story-card b-mt24">
      <div class="story-narrative b-fw500-text">
        PRD Outline — ${escapeHtml(data.feature || 'New Feature')}
      </div>
  `;

  if (data.prd_outline) {
    html += data.prd_outline.sections.map(s => `
      <div class="mb-16">
        <div class="ds-cascade-label mb-6">${escapeHtml(s.title)}</div>
        <div class="b-p1014-bg">
          ${escapeHtml(humanize(s.content || ''))}
        </div>
      </div>
    `).join('');
  }

  if (data.drafted_tickets && data.drafted_tickets.length > 0) {
    html += `<div class="ds-cascade-label b-mt16-mb8">Drafted Tickets (${data.drafted_tickets.length})</div>`;
    html += data.drafted_tickets.map(t => `
      <div class="b-p1012-bg-2">
        <div class="b-fs13-text-9">${escapeHtml(humanize(t.summary || ''))}</div>
        <div class="ds-meta mt-4">Priority: ${escapeHtml(t.priority || 'medium')}</div>
      </div>
    `).join('');
  }

  if (data.unresolved_concerns && data.unresolved_concerns.length > 0) {
    html += `<div class="ds-cascade-label b-mt16-mb8-2">Unresolved Concerns (${data.unresolved_concerns.length})</div>`;
    html += data.unresolved_concerns.map(c => `
      <div class="b-p1012-bg">
        <div class="subtle-text">${escapeHtml(humanize(c.concern || ''))}</div>
        <div class="ds-meta mt-4">Raised by: ${escapeHtml(c.raised_by || 'unknown')}</div>
      </div>
    `).join('');
  }

  // Execute button — create Jira tickets from drafted tickets
  if (data.drafted_tickets && data.drafted_tickets.length > 0) {
    const firstTicket = data.drafted_tickets[0];
    html += `
      <div class="mt-16">
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
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  api.getOEM(`/playbook/${role}?context=${encodeURIComponent(context)}`)
    .then(data => renderPlaybook(el, role, data))
    .catch(e => {
      el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
    });
}
