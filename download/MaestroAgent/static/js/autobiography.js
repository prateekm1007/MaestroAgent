// V6 Spec #6 — Evolution Narrative: the organization's autobiography.
// Accessible via command palette ONLY (NOT in sidebar — sidebar stays at 4).
// ═══════════════════════════════════════════════════════════════════════════

async function loadAutobiography() {
  const el = document.getElementById('autobiography-content');
  if (!el) return;
  el.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Writing your organization\u2019s story…</div>';

  try {
    const data = await api.getOEM('/autobiography');
    renderAutobiography(el, data);
  } catch (e) {
    el.innerHTML = `<div class="calm-empty">
      <div>Your organization's story is still being written.</div>
      <div style="margin-top:8px;font-size:13px;">As Maestro gathers more history, the chapters will fill in.</div>
    </div>`;
  }
}

function renderAutobiography(el, data) {
  const chapters = data.chapters || [];
  let html = `<div class="meta-surface">`;
  html += `<div class="meta-surface greeting">Your organization's story</div>`;
  html += `<div class="meta-surface sub-greeting">${escapeHtml(humanize(data.summary || data.narrative || ''))}</div>`;

  for (const ch of chapters) {
    html += `
      <div class="story-card" style="margin-bottom:16px;">
        <div class="intention-label" style="color:var(--accent);margin-bottom:8px;">${escapeHtml(humanize(ch.title || ''))}</div>
        <div class="story-narrative">${escapeHtml(humanize(ch.narrative || ''))}</div>
        ${ch.lessons && ch.lessons.length ? `<div class="story-evidence" style="margin-top:8px;">${ch.lessons.map(l => escapeHtml(humanize(l))).join(' · ')}</div>` : ''}
      </div>
    `;
  }

  html += `</div>`;
  el.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════════════════════
