// Round 47 — Block 1.2: Per-Teammate View.
// A per-person view: tasks, commitments, attention, trust, influence.
// This is the USER'S view OF a teammate — uses only the user's own
// organizational data. Does NOT analyze the teammate's personal life.
// Accessed by tapping a person's name, NOT a new sidebar item.

async function loadTeammate(email) {
  const el = document.getElementById('teammate-content') || document.getElementById('main-content');
  if (!el) return;
  if (!email) {
    el.innerHTML = `<div class="calm-empty" class="auto-text-center-p4820">
      <div class="auto-fs16-fw700-text-primary-2">No teammate selected.</div>
      <div class="auto-fs13-text-muted-mt4">Tap a person's name anywhere in Maestro to see their view.</div>
    </div>`;
    return;
  }
  el.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Loading teammate view…</div>';

  try {
    const data = await api.getOEM(`/teammate/${encodeURIComponent(email)}`);
    renderTeammate(el, data);
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed to load teammate: ${escapeHtml(e.message)}</div>`;
  }
}

function renderTeammate(el, data) {
  let html = `<div class="auto-mw700-m0auto">`;

  // Header
  html += `
    <div class="auto-mb24">
      <div class="auto-fs22-fw800-text-primary">${escapeHtml(humanize(data.name))}</div>
      <div class="auto-fs13-text-muted-mt2">${escapeHtml(data.email)}</div>
      <div class="auto-flex-gap16-mt12-fs12">
        <span>📊 Influence: ${data.influence}</span>
        <span>📡 Signals: ${data.signal_count}</span>
        ${data.domains.length > 0 ? `<span>🏷️ ${data.domains.length} domain${data.domains.length === 1 ? '' : 's'}</span>` : ''}
      </div>
    </div>
  `;

  // Tasks
  if (data.tasks && data.tasks.length > 0) {
    html += `
      <div class="auto-fs14-fw800-text-primary-mb12">Tasks (${data.tasks.length})</div>
    `;
    data.tasks.forEach(task => {
      const priClass = task.priority === 'high' ? 'contradiction' : task.priority === 'medium' ? 'due' : 'unknown';
      html += `
        <div class="maestro-card" class="auto-mb10">
          <div class="swipe-card-category ${priClass}" class="auto-mb6">${escapeHtml(task.priority.toUpperCase())}</div>
          <div class="auto-fs14-fw700-text-primary-lh14">${escapeHtml(humanize(task.description))}</div>
          <div class="auto-flex-gap12-mt6-fs11">
            ${task.due_date ? `<span>📅 ${escapeHtml(task.due_date)}</span>` : ''}
            ${task.domain ? `<span>🏷️ ${escapeHtml(task.domain)}</span>` : ''}
            <span class="auto-text-positive">${escapeHtml(task.status.toUpperCase())}</span>
          </div>
        </div>
      `;
    });
  }

  // Commitments
  if (data.commitments && data.commitments.length > 0) {
    html += `
      <div class="auto-fs14-fw800-text-primary-mt24">Commitments (${data.commitments.length})</div>
    `;
    data.commitments.forEach(c => {
      html += `
        <div class="maestro-card" class="auto-mb10-u-24f4">
          <div class="auto-fs14-fw700-text-primary-lh14">${escapeHtml(humanize(c.description))}</div>
          <div class="auto-flex-gap12-mt6-fs11">
            ${c.to_whom ? `<span>→ ${escapeHtml(c.to_whom)}</span>` : ''}
            ${c.due_date ? `<span>📅 ${escapeHtml(c.due_date)}</span>` : ''}
          </div>
        </div>
      `;
    });
  }

  // Attention
  if (data.attention && data.attention.total_signals > 0) {
    html += `
      <div class="auto-fs14-fw800-text-primary-mt24">Attention</div>
      <div class="maestro-card" class="auto-mb10">
        <div class="auto-fs13-text-secondary-lh15">${escapeHtml(humanize(data.attention.summary || 'No attention data.'))}</div>
      </div>
    `;
  }

  // Empty state
  if ((!data.tasks || data.tasks.length === 0) && (!data.commitments || data.commitments.length === 0)) {
    html += `
      <div class="calm-empty" class="auto-text-center-p3220">
        <div class="auto-fs16-fw700-text-primary-2">No tasks or commitments yet.</div>
        <div class="auto-fs13-text-muted-mt4">As ${escapeHtml(data.name)} appears in more signals, their tasks and commitments will show here.</div>
      </div>
    `;
  }

  // Withdrawal path
  html += `
    <div class="auto-mt24-p1216-bg-muted-rad8">
      <strong>Withdrawal path:</strong> You can track teammates in a spreadsheet. This view saves time; without it, you are slower but functional.
    </div>
  `;

  html += `</div>`;
  el.innerHTML = html;
}
