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
    const [skepticism, wisdom, metacognition, principles, compression, consciousness, attention, trajectories, causal, forgetting] = await Promise.all([
      api.getOEM('/skepticism').catch(() => null),
      api.getOEM('/wisdom').catch(() => null),
      api.getOEM('/metacognition').catch(() => null),
      api.getOEM('/principles').catch(() => null),
      api.getOEM('/compression').catch(() => null),
      api.getOEM('/consciousness').catch(() => null),
      api.getOEM('/attention').catch(() => null),
      api.getOEM('/trajectories').catch(() => null),
      api.getOEM('/causal').catch(() => null),
      api.getOEM('/forgetting').catch(() => null),
    ]);

    renderCognition(el, skepticism, wisdom, metacognition, principles, compression, consciousness, attention, trajectories, causal, forgetting);
  } catch (e) {
    el.innerHTML = `<div class="calm-empty">
      <div>The cognitive organs are still calibrating.</div>
      <div class="auto-mt8-fs13">As Maestro processes more signals, the organs will engage.</div>
    </div>`;
  }
}

function renderCognition(el, skepticism, wisdom, metacognition, principles, compression, consciousness, attention, trajectories, causal, forgetting) {
  let html = `<div class="meta-surface">`;
  html += `<div class="meta-surface greeting">How your organization thinks</div>`;
  html += `<div class="meta-surface sub-greeting">What it knows, what it questions, and how it judges.</div>`;

  // V5 Spec #3 — Attention Allocation (replaces weather as the first card)
  if (attention) {
    html += renderAttention(attention);
  }

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

  // V5 Spec #7 — Temporal Trajectories
  if (trajectories && trajectories.trajectories) {
    html += renderTrajectories(trajectories);
  }

  // V5 Spec #6 — Causal Cognition
  if (causal && causal.chains) {
    html += renderCausal(causal);
  }

  // V5 Spec #4 — Forgetting Engine
  if (forgetting && forgetting.candidates) {
    html += renderForgetting(forgetting);
  }

  html += `</div>`;
  el.innerHTML = html;
}

function renderAttention(a) {
  let html = `
    <div class="story-card" class="auto-mb16">
      <div class="intention-label" class="auto-text-accent-mb8">Where your attention should be</div>
      <div class="auto-fs14-text-secondary-mb16">${escapeHtml(humanize(a.summary || ''))}</div>
  `;
  if (a.attention_thieves && a.attention_thieves.length) {
    html += `<div class="auto-fs12-text-risk-mb8">Stealing focus:</div>`;
    for (const t of a.attention_thieves) {
      html += `<div class="auto-fs13-text-secondary-p40">${escapeHtml(humanize(t.domain || ''))}: ${t.percentage}% — ${escapeHtml(humanize(t.reason || ''))}</div>`;
    }
  }
  if (a.should_ignore && a.should_ignore.length) {
    html += `<div class="auto-fs12-text-muted-mt8-mb8">Can deprioritize:</div>`;
    for (const ign of a.should_ignore) {
      html += `<div class="auto-fs13-text-muted-p40">${escapeHtml(humanize(ign.domain || ''))} — ${escapeHtml(humanize(ign.reason || ''))}</div>`;
    }
  }
  html += `</div>`;
  return html;
}

function renderTrajectories(t) {
  const trajs = t.trajectories || {};
  let html = `
    <div class="story-card" class="auto-mb16">
      <div class="intention-label" class="auto-text-accent-mb8">Where things are heading</div>
      <div class="auto-fs14-text-secondary-mb16">${escapeHtml(humanize(t.summary || ''))}</div>
  `;
  for (const [name, traj] of Object.entries(trajs)) {
    const trend = traj.trend || 'stable';
    const arrow = trend === 'improving' ? '↑' : trend === 'declining' ? '↓' : '→';
    const color = trend === 'improving' ? 'var(--positive)' : trend === 'declining' ? 'var(--risk)' : 'var(--text-muted)';
    html += `
      <div class="auto-p100-u-4300">
        <div class="ds-row" class="auto-gap8">
          <span class="auto-clr-6419-fs16">${arrow}</span>
          <span class="auto-fs13-fw500-text-primary-tt-capitalize">${escapeHtml(name.replace(/_/g, ' '))}</span>
          <span class="auto-mlauto-fs11-text-muted">${escapeHtml(traj.slope || '')} · ${escapeHtml(traj.duration || '')}</span>
        </div>
        <div class="auto-fs12-text-secondary-mt4">${escapeHtml(humanize(traj.narrative || ''))}</div>
      </div>
    `;
  }
  html += `</div>`;
  return html;
}

function renderCausal(c) {
  if (!c.chains || c.chains.length === 0) return '';
  let html = `
    <div class="story-card" class="auto-mb16">
      <div class="intention-label" class="auto-text-accent-mb8">What causes what</div>
      <div class="auto-fs14-text-secondary-mb16">${escapeHtml(humanize(c.summary || ''))}</div>
  `;
  for (const chain of c.chains.slice(0, 3)) {
    html += `
      <div class="auto-p120-u-4300">
        <div class="auto-fs13-text-primary-2"><strong>When:</strong> ${escapeHtml(humanize(chain.cause || ''))}</div>
        <div class="auto-fs13-text-primary-mt4"><strong>Then:</strong> ${escapeHtml(humanize(chain.effect || ''))}</div>
        <div class="ds-meta" class="auto-mt4">Observed ${chain.sequence_count} times · ${escapeHtml(chain.confidence || '')} confidence</div>
        <div class="auto-fs12-text-secondary-mt4">${escapeHtml(humanize(chain.narrative || ''))}</div>
      </div>
    `;
  }
  html += `</div>`;
  return html;
}

function renderForgetting(f) {
  if (!f.candidates || f.candidates.length === 0) return '';
  let html = `
    <div class="story-card" class="auto-mb16">
      <div class="intention-label" class="auto-text-accent-mb8">What to stop tracking</div>
      <div class="auto-fs14-text-secondary-mb16">${escapeHtml(humanize(f.summary || ''))}</div>
  `;
  for (const c of f.candidates.slice(0, 3)) {
    html += `
      <div class="auto-p100-u-4300">
        <div class="auto-fs13-text-primary-2">${escapeHtml(humanize(c.entity_id || ''))}</div>
        <div class="auto-fs12-text-muted-mt4-2">${escapeHtml(humanize(c.narrative || ''))}</div>
      </div>
    `;
  }
  html += `</div>`;
  return html;
}

function renderConsciousness(c) {
  const dims = c.dimensions || {};
  let html = `
    <div class="story-card" class="auto-mb16">
      <div class="intention-label" class="auto-text-accent-mb12">Right now</div>
      <div class="auto-fs15-text-primary-mb16">${escapeHtml(humanize(c.summary || ''))}</div>
      <div class="auto-u-998b-u-f764-gap12">
  `;
  for (const [name, dim] of Object.entries(dims)) {
    const score = dim.score || 0;
    const pct = Math.round(score * 100);
    const color = score > 0.6 ? 'var(--positive)' : score > 0.3 ? 'var(--warning)' : 'var(--risk)';
    html += `
      <div class="auto-p12-rad8-bg-surface">
        <div class="auto-fs13-fw500-text-primary-tt-capitalize">${escapeHtml(name.replace(/_/g, ' '))}</div>
        <div class="auto-fs11-text-muted-mb6">${escapeHtml(humanize(dim.label || ''))} — ${escapeHtml(humanize(dim.basis || ''))}</div>
        <div class="auto-h3-bg-08c2-rad2-overflow-hidden">
          <div class="auto-h100-wpctp-bg-6419-rad2"></div>
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
    <div class="story-card" class="auto-mb16">
      <div class="intention-label" class="auto-text-accent-mb8">Beliefs worth questioning</div>
      <div class="auto-fs14-text-secondary-mb16">${escapeHtml(humanize(s.summary || ''))}</div>
  `;
  for (const c of s.challenges.slice(0, 3)) {
    html += `
      <div class="auto-p120-u-4300">
        <div class="auto-fs14-text-primary-fw500">${escapeHtml(humanize(c.challenge || ''))}</div>
        <div class="ds-meta" class="auto-mt4">${escapeHtml(humanize(c.evidence || ''))}</div>
      </div>
    `;
  }
  html += `</div>`;
  return html;
}

function renderWisdom(w) {
  let html = `
    <div class="story-card" class="auto-mb16">
      <div class="intention-label" class="auto-text-accent-mb8">When values compete</div>
      <div class="auto-fs14-text-primary-mb12">${escapeHtml(humanize(w.wisdom || ''))}</div>
  `;
  if (w.competing_values && w.competing_values.length) {
    html += `<div class="auto-fs12-text-muted-mb12">${w.competing_values.map(v => escapeHtml(humanize(v))).join(' · ')}</div>`;
  }
  if (w.recommendation) {
    html += `<div class="auto-fs14-text-accent-fw500">${escapeHtml(humanize(w.recommendation))}</div>`;
  }
  html += `</div>`;
  return html;
}

function renderMetacognition(m) {
  let html = `
    <div class="story-card" class="auto-mb16">
      <div class="intention-label" class="auto-text-accent-mb8">How well the parts work together</div>
      <div class="auto-fs15-text-primary-mb12">${escapeHtml(humanize(m.diagnosis || ''))}</div>
      <div class="auto-fs13-text-secondary-mb8">Team quality vs. organization quality: ${m.meta_gap > 0 ? 'organization is stronger' : m.meta_gap < -0.1 ? 'teams are stronger than the whole' : 'balanced'}</div>
  `;
  if (m.team_quality && m.team_quality.length) {
    html += `<div class="auto-fs12-text-muted-mt8-2">Team quality:</div>`;
    for (const t of m.team_quality.slice(0, 3)) {
      html += `<div class="auto-fs12-text-secondary-p40">${escapeHtml(t.domain)}: ${escapeHtml(t.quality_label)} (${t.signal_count} signals)</div>`;
    }
  }
  html += `<div class="auto-fs14-text-accent-mt12-fw500">${escapeHtml(humanize(m.recommendation || ''))}</div>`;
  html += `</div>`;
  return html;
}

function renderPrinciples(p) {
  let html = `
    <div class="story-card" class="auto-mb16">
      <div class="intention-label" class="auto-text-accent-mb8">What your organization has earned the right to trust</div>
      <div class="auto-fs14-text-secondary-mb16">${escapeHtml(humanize(p.summary || ''))}</div>
  `;
  if (p.principles && p.principles.length) {
    for (const principle of p.principles) {
      html += `
        <div class="auto-p120-u-4300">
          <div class="auto-fs14-text-primary-fw500">${escapeHtml(humanize(principle.statement || ''))}</div>
          <div class="ds-meta" class="auto-mt4">${escapeHtml(humanize(principle.narrative || ''))}</div>
        </div>
      `;
    }
  }
  if (p.candidates && p.candidates.length) {
    html += `<div class="auto-fs12-text-muted-mt12">Almost there:</div>`;
    for (const c of p.candidates.slice(0, 2)) {
      html += `<div class="auto-fs12-text-secondary-p40">${escapeHtml(humanize(c.narrative || ''))}</div>`;
    }
  }
  html += `</div>`;
  return html;
}

function renderCompression(c) {
  let html = `
    <div class="story-card" class="auto-mb16">
      <div class="intention-label" class="auto-text-accent-mb8">What it all comes down to</div>
      <div class="auto-fs14-text-secondary-mb16">${escapeHtml(humanize(c.summary || ''))}</div>
  `;
  if (c.truths && c.truths.length) {
    html += `<div class="auto-fs12-fw600-text-muted-mb6">TRUTHS</div>`;
    for (const t of c.truths) {
      html += `<div class="auto-fs13-text-primary-p40">${escapeHtml(humanize(t.truth || ''))}</div>`;
    }
  }
  if (c.habits && c.habits.length) {
    html += `<div class="auto-fs12-fw600-text-muted-mt12">HABITS</div>`;
    for (const h of c.habits.slice(0, 3)) {
      html += `<div class="auto-fs13-text-secondary-p40">${escapeHtml(humanize(h.habit || ''))} — ${escapeHtml(humanize(h.assessment || ''))}</div>`;
    }
  }
  if (c.mistakes && c.mistakes.length) {
    html += `<div class="auto-fs12-fw600-text-muted-mt12">MISTAKES</div>`;
    for (const m of c.mistakes.slice(0, 2)) {
      html += `<div class="auto-fs13-text-secondary-p40">${escapeHtml(humanize(m.mistake || ''))}</div>`;
    }
  }
  html += `</div>`;
  return html;
}

// ═══════════════════════════════════════════════════════════════════════════
