// Round 47 — Block 1.2: Per-Teammate View.
// A per-person view: tasks, commitments, attention, trust, influence.
// This is the USER'S view OF a teammate — uses only the user's own
// organizational data. Does NOT analyze the teammate's personal life.
// Accessed by tapping a person's name, NOT a new sidebar item.

async function loadTeammate(email) {
  const el = document.getElementById('teammate-content') || document.getElementById('main-content');
  if (!el) return;
  if (!email) {
    el.innerHTML = `<div class="calm-empty" style="text-align:center;padding:48px 20px;">
      <div style="font-size:16px;font-weight:700;color:var(--maestro-black,var(--text-primary));font-family:'Montserrat',sans-serif;">No teammate selected.</div>
      <div style="font-size:13px;color:var(--maestro-gray-mid,var(--text-muted));margin-top:4px;">Tap a person's name anywhere in Maestro to see their view.</div>
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
  let html = `<div style="max-width:700px;margin:0 auto;font-family:'Montserrat',sans-serif;">`;

  // Header
  html += `
    <div style="margin-bottom:24px;">
      <div style="font-size:22px;font-weight:800;color:var(--maestro-black,var(--text-primary));">${escapeHtml(humanize(data.name))}</div>
      <div style="font-size:13px;color:var(--maestro-gray-mid,var(--text-muted));margin-top:2px;">${escapeHtml(data.email)}</div>
      <div style="display:flex;gap:16px;margin-top:12px;font-size:12px;color:var(--maestro-gray-dark,var(--text-secondary));font-weight:600;">
        <span>📊 Influence: ${data.influence}</span>
        <span>📡 Signals: ${data.signal_count}</span>
        ${data.domains.length > 0 ? `<span>🏷️ ${data.domains.length} domain${data.domains.length === 1 ? '' : 's'}</span>` : ''}
      </div>
    </div>
  `;

  // Tasks
  if (data.tasks && data.tasks.length > 0) {
    html += `
      <div style="font-size:14px;font-weight:800;color:var(--maestro-black,var(--text-primary));margin-bottom:12px;">Tasks (${data.tasks.length})</div>
    `;
    data.tasks.forEach(task => {
      const priClass = task.priority === 'high' ? 'contradiction' : task.priority === 'medium' ? 'due' : 'unknown';
      html += `
        <div class="maestro-card" style="margin-bottom:10px;">
          <div class="swipe-card-category ${priClass}" style="margin-bottom:6px;">${escapeHtml(task.priority.toUpperCase())}</div>
          <div style="font-size:14px;font-weight:700;color:var(--maestro-black,var(--text-primary));line-height:1.4;">${escapeHtml(humanize(task.description))}</div>
          <div style="display:flex;gap:12px;margin-top:6px;font-size:11px;color:var(--maestro-gray-mid,var(--text-muted));font-weight:600;">
            ${task.due_date ? `<span>📅 ${escapeHtml(task.due_date)}</span>` : ''}
            ${task.domain ? `<span>🏷️ ${escapeHtml(task.domain)}</span>` : ''}
            <span style="color:${task.status === 'done' ? 'var(--maestro-success,#00C853)' : 'var(--maestro-warning,#FF9800)'};">${escapeHtml(task.status.toUpperCase())}</span>
          </div>
        </div>
      `;
    });
  }

  // Commitments
  if (data.commitments && data.commitments.length > 0) {
    html += `
      <div style="font-size:14px;font-weight:800;color:var(--maestro-black,var(--text-primary));margin-top:24px;margin-bottom:12px;">Commitments (${data.commitments.length})</div>
    `;
    data.commitments.forEach(c => {
      html += `
        <div class="maestro-card" style="margin-bottom:10px;border-left:4px solid var(--maestro-warning,#FF9800);">
          <div style="font-size:14px;font-weight:700;color:var(--maestro-black,var(--text-primary));line-height:1.4;">${escapeHtml(humanize(c.description))}</div>
          <div style="display:flex;gap:12px;margin-top:6px;font-size:11px;color:var(--maestro-gray-mid,var(--text-muted));font-weight:600;">
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
      <div style="font-size:14px;font-weight:800;color:var(--maestro-black,var(--text-primary));margin-top:24px;margin-bottom:12px;">Attention</div>
      <div class="maestro-card" style="margin-bottom:10px;">
        <div style="font-size:13px;color:var(--maestro-gray-dark,var(--text-secondary));line-height:1.5;">${escapeHtml(humanize(data.attention.summary || 'No attention data.'))}</div>
      </div>
    `;
  }

  // Empty state
  if ((!data.tasks || data.tasks.length === 0) && (!data.commitments || data.commitments.length === 0)) {
    html += `
      <div class="calm-empty" style="text-align:center;padding:32px 20px;">
        <div style="font-size:16px;font-weight:700;color:var(--maestro-black,var(--text-primary));font-family:'Montserrat',sans-serif;">No tasks or commitments yet.</div>
        <div style="font-size:13px;color:var(--maestro-gray-mid,var(--text-muted));margin-top:4px;">As ${escapeHtml(data.name)} appears in more signals, their tasks and commitments will show here.</div>
      </div>
    `;
  }

  // Withdrawal path
  html += `
    <div style="margin-top:24px;padding:12px 16px;background:var(--maestro-gray-light,#F5F5F5);border-radius:8px;font-size:12px;color:var(--maestro-gray-dark,var(--text-secondary));line-height:1.5;">
      <strong>Withdrawal path:</strong> You can track teammates in a spreadsheet. This view saves time; without it, you are slower but functional.
    </div>
  `;

  html += `</div>`;
  el.innerHTML = html;
}
