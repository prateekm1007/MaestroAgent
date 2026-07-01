// V4 COGNITIVE ORGANS — frontend surface
// ═══════════════════════════════════════════════════════════════════════════
// Skepticism, Wisdom, Metacognition, Principles, Memory Compression,
// Consciousness — all 6 remaining V4 organs rendered in one surface.
//
// This surface is accessible via the command palette (NOT the sidebar).
// The sidebar stays at 5 items. The V4 organs live behind Ctrl+K.
// ═══════════════════════════════════════════════════════════════════════════

async function loadCognition() {
  const el = document.getElementById('cognition-content');
  if (!el) return;
  el.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Engaging cognitive organs…</div>';

  try {
    const [skepticism, wisdom, metacognition, principles, compression, consciousness] = await Promise.all([
      api.getOEM('/skepticism').catch(() => null),
      api.getOEM('/wisdom').catch(() => null),
      api.getOEM('/metacognition').catch(() => null),
      api.getOEM('/principles').catch(() => null),
      api.getOEM('/compression').catch(() => null),
      api.getOEM('/consciousness').catch(() => null),
    ]);

    renderCognition(el, skepticism, wisdom, metacognition, principles, compression, consciousness);
  } catch (e) {
    el.innerHTML = `<div class="calm-empty">
      <div>The cognitive organs are still calibrating.</div>
      <div style="margin-top:8px;font-size:13px;">As Maestro processes more signals, the organs will engage.</div>
    </div>`;
  }
}

function renderCognition(el, skepticism, wisdom, metacognition, principles, compression, consciousness) {
  let html = `<div class="meta-surface">`;
  html += `<div class="meta-surface greeting">Organizational Cognition</div>`;
  html += `<div class="meta-surface sub-greeting">The organization's cognitive organs — how it perceives, questions, judges, and knows itself.</div>`;

  // Organ #8 — Consciousness (state vector)
  if (consciousness) {
    html += renderConsciousness(consciousness);
  }

  // Organ #3 — Skepticism
  if (skepticism) {
    html += renderSkepticism(skepticism);
  }

  // Organ #4 — Wisdom
  if (wisdom) {
    html += renderWisdom(wisdom);
  }

  // Organ #5 — Metacognition
  if (metacognition) {
    html += renderMetacognition(metacognition);
  }

  // Organ #6 — Principles
  if (principles) {
    html += renderPrinciples(principles);
  }

  // Organ #7 — Memory Compression
  if (compression) {
    html += renderCompression(compression);
  }

  html += `</div>`;
  el.innerHTML = html;
}

function renderConsciousness(c) {
  const dims = c.dimensions || {};
  let html = `
    <div class="story-card" style="margin-bottom:16px;">
      <div class="intention-label" style="color:var(--accent);margin-bottom:12px;">Consciousness — state vector</div>
      <div style="font-size:15px;color:var(--text-primary);margin-bottom:16px;">${escapeHtml(humanize(c.summary || ''))}</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
  `;
  for (const [name, dim] of Object.entries(dims)) {
    const score = dim.score || 0;
    const pct = Math.round(score * 100);
    const color = score > 0.6 ? 'var(--positive)' : score > 0.3 ? 'var(--warning)' : 'var(--risk)';
    html += `
      <div style="padding:12px;border-radius:8px;background:var(--surface-2);">
        <div style="font-size:13px;font-weight:500;color:var(--text-primary);text-transform:capitalize;">${escapeHtml(name.replace(/_/g, ' '))}</div>
        <div style="font-size:11px;color:var(--text-muted);margin-bottom:6px;">${escapeHtml(humanize(dim.label || ''))} — ${escapeHtml(humanize(dim.basis || ''))}</div>
        <div style="height:3px;background:var(--divider);border-radius:2px;overflow:hidden;">
          <div style="height:100%;width:${pct}%;background:${color};border-radius:2px;"></div>
        </div>
      </div>
    `;
  }
  html += `</div></div>`;
  return html;
}

function renderSkepticism(s) {
  if (!s.challenges || s.challenges.length === 0) return '';
  let html = `
    <div class="story-card" style="margin-bottom:16px;">
      <div class="intention-label" style="color:var(--accent);margin-bottom:8px;">Skepticism — challenged beliefs</div>
      <div style="font-size:14px;color:var(--text-secondary);margin-bottom:16px;">${escapeHtml(humanize(s.summary || ''))}</div>
  `;
  for (const c of s.challenges.slice(0, 3)) {
    html += `
      <div style="padding:12px 0;border-bottom:1px solid var(--divider);">
        <div style="font-size:14px;color:var(--text-primary);font-weight:500;">${escapeHtml(humanize(c.challenge || ''))}</div>
        <div class="ds-meta" style="margin-top:4px;">Risk: ${Math.round((c.fossilization_risk || 0) * 100)}% · ${escapeHtml(humanize(c.evidence || ''))}</div>
      </div>
    `;
  }
  html += `</div>`;
  return html;
}

function renderWisdom(w) {
  let html = `
    <div class="story-card" style="margin-bottom:16px;">
      <div class="intention-label" style="color:var(--accent);margin-bottom:8px;">Wisdom — competing values synthesized</div>
      <div style="font-size:14px;color:var(--text-primary);margin-bottom:12px;">${escapeHtml(humanize(w.wisdom || ''))}</div>
  `;
  if (w.competing_values && w.competing_values.length) {
    html += `<div style="font-size:12px;color:var(--text-muted);margin-bottom:12px;">Competing values: ${w.competing_values.map(v => escapeHtml(humanize(v))).join(' · ')}</div>`;
  }
  if (w.recommendation) {
    html += `<div style="font-size:14px;color:var(--accent);font-weight:500;">${escapeHtml(humanize(w.recommendation))}</div>`;
  }
  html += `</div>`;
  return html;
}

function renderMetacognition(m) {
  let html = `
    <div class="story-card" style="margin-bottom:16px;">
      <div class="intention-label" style="color:var(--accent);margin-bottom:8px;">Metacognition — thinking about thinking</div>
      <div style="font-size:15px;color:var(--text-primary);margin-bottom:12px;">${escapeHtml(humanize(m.diagnosis || ''))}</div>
      <div style="font-size:13px;color:var(--text-secondary);margin-bottom:8px;">Meta-gap: ${m.meta_gap} (negative = teams smarter than org)</div>
  `;
  if (m.team_quality && m.team_quality.length) {
    html += `<div style="font-size:12px;color:var(--text-muted);margin-top:8px;">Team quality:</div>`;
    for (const t of m.team_quality.slice(0, 3)) {
      html += `<div style="font-size:12px;color:var(--text-secondary);padding:4px 0;">${escapeHtml(t.domain)}: ${escapeHtml(t.quality_label)} (${t.signal_count} signals)</div>`;
    }
  }
  html += `<div style="font-size:14px;color:var(--accent);margin-top:12px;font-weight:500;">${escapeHtml(humanize(m.recommendation || ''))}</div>`;
  html += `</div>`;
  return html;
}

function renderPrinciples(p) {
  let html = `
    <div class="story-card" style="margin-bottom:16px;">
      <div class="intention-label" style="color:var(--accent);margin-bottom:8px;">Principles — graduated wisdom</div>
      <div style="font-size:14px;color:var(--text-secondary);margin-bottom:16px;">${escapeHtml(humanize(p.summary || ''))}</div>
  `;
  if (p.principles && p.principles.length) {
    for (const principle of p.principles) {
      html += `
        <div style="padding:12px 0;border-bottom:1px solid var(--divider);">
          <div style="font-size:14px;color:var(--text-primary);font-weight:500;">${escapeHtml(humanize(principle.statement || ''))}</div>
          <div class="ds-meta" style="margin-top:4px;">${escapeHtml(humanize(principle.narrative || ''))}</div>
        </div>
      `;
    }
  }
  if (p.candidates && p.candidates.length) {
    html += `<div style="font-size:12px;color:var(--text-muted);margin-top:12px;">Approaching graduation:</div>`;
    for (const c of p.candidates.slice(0, 2)) {
      html += `<div style="font-size:12px;color:var(--text-secondary);padding:4px 0;">${escapeHtml(humanize(c.narrative || ''))}</div>`;
    }
  }
  html += `</div>`;
  return html;
}

function renderCompression(c) {
  let html = `
    <div class="story-card" style="margin-bottom:16px;">
      <div class="intention-label" style="color:var(--accent);margin-bottom:8px;">Memory Compression</div>
      <div style="font-size:14px;color:var(--text-secondary);margin-bottom:16px;">${escapeHtml(humanize(c.summary || ''))}</div>
  `;
  if (c.truths && c.truths.length) {
    html += `<div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:6px;">TRUTHS</div>`;
    for (const t of c.truths) {
      html += `<div style="font-size:13px;color:var(--text-primary);padding:4px 0;">${escapeHtml(humanize(t.truth || ''))}</div>`;
    }
  }
  if (c.habits && c.habits.length) {
    html += `<div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-top:12px;margin-bottom:6px;">HABITS</div>`;
    for (const h of c.habits.slice(0, 3)) {
      html += `<div style="font-size:13px;color:var(--text-secondary);padding:4px 0;">${escapeHtml(humanize(h.habit || ''))} — ${escapeHtml(humanize(h.assessment || ''))}</div>`;
    }
  }
  if (c.mistakes && c.mistakes.length) {
    html += `<div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-top:12px;margin-bottom:6px;">MISTAKES</div>`;
    for (const m of c.mistakes.slice(0, 2)) {
      html += `<div style="font-size:13px;color:var(--text-secondary);padding:4px 0;">${escapeHtml(humanize(m.mistake || ''))}</div>`;
    }
  }
  html += `</div>`;
  return html;
}

// ═══════════════════════════════════════════════════════════════════════════
