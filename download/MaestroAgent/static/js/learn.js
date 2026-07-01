// THE INVISIBLE MAESTRO — LEARN surface
// ═══════════════════════════════════════════════════════════════════════════
// LEARN is not documentation. It is organizational evolution.
//
// Stories, not metrics. "Yesterday your organization learned: Engineering
// reused Platform's work. Saved 74 hours."
// ═══════════════════════════════════════════════════════════════════════════

async function loadLearn() {
  const el = document.getElementById('learn-content');
  if (!el) return;
  el.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Recalling what your organization learned…</div>';

  try {
    const [learning, improvement, calibration, identity, evolutionTracker, dna] = await Promise.all([
      api.getOEM('/learning').catch(() => null),
      api.getOEM('/improvement').catch(() => null),
      api.getOEM('/predictions/market/calibration').catch(() => null),
      api.getOEM('/identity').catch(() => null),
      api.getOEM('/evolution-tracker').catch(() => null),
      api.getOEM('/dna').catch(() => null),
    ]);

    renderLearnStories(el, learning, improvement, calibration, identity, evolutionTracker, dna);
  } catch (e) {
    el.innerHTML = `<div class="calm-empty">
      <div>Your organization is still gathering experience.</div>
      <div style="margin-top:8px;font-size:13px;">As Maestro processes more signals, stories of organizational evolution will appear here.</div>
    </div>`;
  }
}

function renderLearnStories(el, learning, improvement, calibration, identity, evolutionTracker, dna) {
  const stories = [];

  // Story 1: "Your organization became smarter" (from improvement report)
  if (improvement && improvement.summary) {
    const s = improvement.summary;
    if (s.resolved > 0) {
      stories.push({
        narrative: `Your organization resolved ${s.resolved} ${s.resolved === 1 ? 'prediction' : 'predictions'} and learned from the outcome.`,
        evidence: s.correct > 0 ? `${s.correct} ${s.correct === 1 ? 'was' : 'were'} correct. ${s.incorrect} ${s.incorrect === 1 ? 'was' : 'were'} incorrect.` : 'All predictions were resolved.',
        action: () => navTo('predictions'),
      });
    }
  }

  // Story 2: Calibration story (from prediction market)
  if (calibration && calibration.predictors && calibration.predictors.length > 0) {
    const best = calibration.predictors[0];
    const brier = best.avg_brier_score;
    let quality = 'still calibrating';
    if (brier < 0.1) quality = 'exceptionally well-calibrated';
    else if (brier < 0.2) quality = 'well-calibrated';
    else if (brier < 0.3) quality = 'moderately calibrated';

    stories.push({
      narrative: `${best.email.split('@')[0]} is ${quality} in their predictions. Their judgment is becoming a trusted signal.`,
      evidence: `Based on ${best.resolved_predictions} resolved ${best.resolved_predictions === 1 ? 'prediction' : 'predictions'}.`,
      action: () => navTo('predictions'),
    });
  }

  // Story 3: Law evolution (from learning report)
  if (learning && learning.law_evolution && learning.law_evolution.length > 0) {
    const evo = learning.law_evolution[0];
    stories.push({
      narrative: `Your organization consistently succeeds when ${evo.detail || 'following established patterns'}.`,
      evidence: `This pattern has been reinforced ${evo.evidence_delta > 0 ? 'with new evidence' : 'over time'}.`,
      action: () => navTo('physics'),
    });
  }

  // Story 4: Drift detection
  if (learning && learning.drift_events && learning.drift_events.length > 0) {
    const drift = learning.drift_events[0];
    stories.push({
      narrative: `Something changed: ${drift.description || 'organizational behavior shifted'}.`,
      evidence: `Severity: ${drift.severity}. The organization may need to adapt.`,
      action: () => navTo('home'),
    });
  }

  // Story 5: Knowledge freshness
  if (learning && learning.freshness) {
    const fresh = learning.freshness;
    if (fresh.fresh_domains && fresh.fresh_domains.length > 0) {
      stories.push({
        narrative: `Knowledge in ${fresh.fresh_domains.slice(0, 2).join(' and ')} is current and actively growing.`,
        evidence: `${fresh.total_signals || 'Multiple'} signals processed recently.`,
        action: () => navTo('flow'),
      });
    }
  }

  let html = `<div class="meta-surface">`;

  // Organizational heartbeat
  html += `<div class="meta-surface greeting"><span class="org-heartbeat"></span>Your organization is evolving.</div>`;

  if (stories.length === 0) {
    html += `<div class="calm-empty">
      <div>Your organization is still gathering experience.</div>
      <div style="margin-top:8px;font-size:13px;">As predictions are resolved and patterns are validated, stories of organizational evolution will appear here.</div>
    </div>`;
  } else {
    html += `<div class="meta-surface sub-greeting">${stories.length} ${stories.length === 1 ? 'story' : 'stories'} from recent organizational learning.</div>`;

    stories.forEach((s, i) => {
      html += `
        <div class="story-card" data-idx="${i}">
          <div class="story-narrative">${escapeHtml(humanize(s.narrative))}</div>
          <div class="story-evidence">${escapeHtml(humanize(s.evidence))}</div>
        </div>
      `;
    });
  }

  // Deep capabilities
  // V4 Organ #1 — Identity: does the org know itself?
  if (identity && identity.beliefs && identity.beliefs.length > 0) {
    html += `
      <div style="margin-top:32px;padding:20px;border-radius:12px;background:var(--surface);border:1px solid var(--divider);">
        <div class="intention-label" style="margin:0 0 12px 0;color:var(--accent);">Who your organization is</div>
        <div style="font-size:15px;color:var(--text-primary);line-height:1.6;margin-bottom:16px;">${escapeHtml(humanize(identity.summary))}</div>
        <div style="font-size:13px;color:var(--text-secondary);margin-bottom:8px;">
          <strong>Strongest alignment:</strong> ${escapeHtml(humanize(identity.strongest_alignment || ''))}
        </div>
        <div style="font-size:13px;color:var(--text-secondary);">
          <strong>Largest gap:</strong> ${escapeHtml(humanize(identity.largest_gap || ''))}
        </div>
      </div>
    `;
  }

  // V6 Spec #5 — Organizational DNA: "Who your organization has become"
  if (dna && dna.chromosomes) {
    html += `
      <div style="margin-top:32px;padding:20px;border-radius:12px;background:var(--surface);border:1px solid var(--divider);">
        <div class="intention-label" style="color:var(--accent);margin:0 0 12px 0;">Who your organization has become</div>
        <div style="font-size:15px;color:var(--text-primary);margin-bottom:16px;">${escapeHtml(humanize(dna.summary || ''))}</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
          ${Object.entries(dna.chromosomes).map(([name, chr]) => `
            <div style="padding:10px;border-radius:8px;background:var(--surface-2);">
              <div style="font-size:12px;font-weight:500;color:var(--text-primary);text-transform:capitalize;">${escapeHtml(name.replace(/_/g, ' '))}</div>
              <div style="font-size:11px;color:var(--text-secondary);">${escapeHtml(humanize(chr.label || ''))}</div>
              <div style="font-size:10px;color:var(--text-muted);margin-top:2px;">${escapeHtml(humanize(chr.basis || ''))}</div>
            </div>
          `).join('')}
        </div>
      </div>
    `;
  }

  // V6 Spec #2 — Evolution Tracker: "Mistakes your organization no longer makes"
  if (evolutionTracker && evolutionTracker.failure_modes && evolutionTracker.failure_modes.length > 0) {
    html += `
      <div style="margin-top:32px;padding:20px;border-radius:12px;background:var(--surface);border:1px solid var(--divider);">
        <div class="intention-label" style="color:var(--accent);margin:0 0 12px 0;">Mistakes your organization no longer makes</div>
        <div style="font-size:14px;color:var(--text-secondary);margin-bottom:16px;">${escapeHtml(humanize(evolutionTracker.summary || ''))}</div>
        ${evolutionTracker.failure_modes.slice(0, 4).map(m => {
          const status = m.current_status || 'active';
          const color = status === 'eliminated' ? 'var(--positive)' : status === 'resolving' ? 'var(--warning)' : 'var(--risk)';
          const label = status === 'eliminated' ? '✓ eliminated' : status === 'resolving' ? 'resolving' : 'active';
          return `<div style="padding:10px 0;border-bottom:1px solid var(--divider);">
            <div class="ds-row" style="gap:8px;">
              <span style="color:${color};font-size:12px;font-weight:500;">${label}</span>
              <span style="font-size:13px;color:var(--text-primary);">${escapeHtml(humanize(m.failure_mode || ''))}</span>
            </div>
            <div style="font-size:12px;color:var(--text-muted);margin-top:4px;">${escapeHtml(humanize(m.narrative || ''))}</div>
          </div>`;
        }).join('')}
      </div>
    `;
  }

  html += `<div class="intention-label" style="margin-top:32px;">Explore deeper</div>`;
  html += `<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">`;
  html += `<button class="intention-prompt" onclick="navTo('predictions')">Prediction calibration</button>`;
  html += `<button class="intention-prompt" onclick="navTo('assumptions')">Assumption accuracy</button>`;
  html += `<button class="intention-prompt" onclick="navTo('physics')">Organizational patterns</button>`;
  html += `<button class="intention-prompt" onclick="navTo('memory')">Memory replay</button>`;
  html += `</div>`;

  html += `</div>`;
  el.innerHTML = html;

  // Wire up story card clicks
  el.querySelectorAll('.story-card').forEach((card, i) => {
    if (stories[i] && stories[i].action) {
      card.style.cursor = 'pointer';
      card.addEventListener('click', stories[i].action);
    }
  });
}

// ═══════════════════════════════════════════════════════════════════════════
