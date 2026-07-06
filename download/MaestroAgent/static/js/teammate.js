// Round 47 — Block 1.2: Per-Teammate View.
// A per-person view: tasks, commitments, attention, trust, influence.
// This is the USER'S view OF a teammate — uses only the user's own
// organizational data. Does NOT analyze the teammate's personal life.
// Accessed by tapping a person's name, NOT a new sidebar item.
//
// Typography: font-family: 'Montserrat', sans-serif (Bumble design system)

async function loadTeammate(email) {
  const el = document.getElementById('teammate-content') || document.getElementById('main-content');
  if (!el) return;
  if (!email) {
    el.innerHTML = `<div class="calm-empty b-text-center-9">
      <div class="b-fs16-fw700-2">No teammate selected.</div>
      <div class="caption-text">Tap a person's name anywhere in Maestro to see their view.</div>
    </div>`;
    return;
  }
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    const data = await api.getOEM(`/teammate/${encodeURIComponent(email)}`);
    renderTeammate(el, data);
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed to load teammate: ${escapeHtml(e.message)}</div>`;
  }
}

function renderTeammate(el, data) {
  let html = `<div class="b-mw700-m0auto">`;

  // Header
  html += `
    <div class="b-mb24">
      <div class="b-fs22-fw800">${escapeHtml(humanize(data.name))}</div>
      <div class="b-fs13-text-4">${escapeHtml(data.email)}</div>
      <div class="b-flex-gap16-2">
        <span>📊 Influence: ${data.influence}</span>
        <span>📡 Signals: ${data.signal_count}</span>
        ${data.domains.length > 0 ? `<span>🏷️ ${data.domains.length} domain${data.domains.length === 1 ? '' : 's'}</span>` : ''}
      </div>
    </div>
  `;

  // Tasks
  if (data.tasks && data.tasks.length > 0) {
    html += `
      <div class="b-fs14-fw800-4">Tasks (${data.tasks.length})</div>
    `;
    data.tasks.forEach(task => {
      const priClass = task.priority === 'high' ? 'contradiction' : task.priority === 'medium' ? 'due' : 'unknown';
      html += `
        <div class="maestro-card mb-10">
          <div class="swipe-card-category ${priClass} mb-6">${escapeHtml(task.priority.toUpperCase())}</div>
          <div class="b-fs14-fw700-3">${escapeHtml(humanize(task.description))}</div>
          <div class="b-flex-gap12">
            ${task.due_date ? `<span>📅 ${escapeHtml(task.due_date)}</span>` : ''}
            ${task.domain ? `<span>🏷️ ${escapeHtml(task.domain)}</span>` : ''}
            <span class="text-positive">${escapeHtml(task.status.toUpperCase())}</span>
          </div>
        </div>
      `;
    });
  }

  // Commitments
  if (data.commitments && data.commitments.length > 0) {
    html += `
      <div class="b-fs14-fw800-8">Commitments (${data.commitments.length})</div>
    `;
    data.commitments.forEach(c => {
      html += `
        <div class="maestro-card b-mb10-u">
          <div class="b-fs14-fw700-3">${escapeHtml(humanize(c.description))}</div>
          <div class="b-flex-gap12">
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
      <div class="b-fs14-fw800-8">Attention</div>
      <div class="maestro-card mb-10">
        <div class="b-fs13-text-17">${escapeHtml(humanize(data.attention.summary || 'No attention data.'))}</div>
      </div>
    `;
  }

  // Empty state
  if ((!data.tasks || data.tasks.length === 0) && (!data.commitments || data.commitments.length === 0)) {
    html += `
      <div class="calm-empty b-text-center-8">
        <div class="b-fs16-fw700-2">No tasks or commitments yet.</div>
        <div class="caption-text">As ${escapeHtml(data.name)} appears in more signals, their tasks and commitments will show here.</div>
      </div>
    `;
  }

  // Withdrawal path
  html += `
    <div class="b-mt24-p1216">
      <strong>Withdrawal path:</strong> You can track teammates in a spreadsheet. This view saves time; without it, you are slower but functional.
    </div>
  `;

  html += `</div>`;
  el.innerHTML = html;
}
