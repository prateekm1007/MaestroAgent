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
    const [learning, improvement, calibration] = await Promise.all([
      api.getOEM('/learning').catch(() => null),
      api.getOEM('/improvement').catch(() => null),
      api.getOEM('/predictions/market/calibration').catch(() => null),
    ]);

    renderLearnStories(el, learning, improvement, calibration);
  } catch (e) {
    el.innerHTML = `<div class="calm-empty">
      <div>Your organization is still gathering experience.</div>
      <div style="margin-top:8px;font-size:13px;">As Maestro processes more signals, stories of organizational evolution will appear here.</div>
    </div>`;
  }
}

function renderLearnStories(el, learning, improvement, calibration) {
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
