/* Phase 2.2 — Trajectory Panel shared utility.
 *
 * Used by: today.js (commitment cards), personal.js (work_context card).
 *
 * Fetches /api/oem/loop1.5/timeline/{entity} and renders the Day-1 → Day-60
 * projection + recommendation DERIVED server-side by CommitmentTimelineSimulator
 * from the CommitmentMutationTracker's history (P13 — the UI never supplies
 * the rate, pattern, risk, or recommendation; it only renders what the server
 * derived).
 *
 * The panel renders into a container element with id `containerId`. If the
 * container already has content, the call toggles it off (same UX as
 * showInlineWhy in today.js).
 *
 * Dependencies (must be loaded before this script runs):
 *   - api.getOEM()  (from swr_cache.js)
 *   - escapeHtml()  (from swr_cache.js)
 *   - humanize()    (from humanize.js)
 */
function showTrajectoryPanel(containerId, entity) {
  const el = document.getElementById(containerId);
  if (!el) return;
  // Toggle off if already shown
  if (el.innerHTML.trim()) {
    el.innerHTML = '';
    return;
  }
  if (!entity) {
    el.innerHTML = `<div class="ds-meta fs-11">No customer entity on this commitment.</div>`;
    return;
  }
  // Skeleton while fetching
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  // Async IIFE — fetch + render
  (async () => {
    try {
      const data = await api.getOEM(`/loop1.5/timeline/${encodeURIComponent(entity)}`);
      if (!data || !data.pattern_type) {
        el.innerHTML = `<div class="ds-meta fs-11">No trajectory data available for ${escapeHtml(entity)}.</div>`;
        return;
      }
      const risk = data.risk_level || 'unknown';
      const riskClass = risk === 'high' ? 'b-text-risk' : (risk === 'medium' ? 'b-text-accent' : 'b-text-primary-2');
      const patternLabel = data.pattern_type.replace(/_/g, ' ');
      const horizon = data.projected_mutations_by_day_60;
      const rate = (data.mutation_rate_per_30d || 0).toFixed(2);
      // Trajectory chips
      let trajHtml = '';
      if (Array.isArray(data.baseline_trajectory) && data.baseline_trajectory.length > 0) {
        trajHtml = '<div class="b-flex-gap4 b-mt4-u">';
        for (const cp of data.baseline_trajectory) {
          const day = cp.day;
          const state = cp.projected_state || 'unknown';
          const stateClass = state === 'on_track' ? 'b-text-primary-2'
            : state === 'at_risk' ? 'b-text-accent'
            : state === 'renegotiated' ? 'b-text-accent-3'
            : state === 'broken' ? 'b-text-risk'
            : 'b-text-primary-2';
          const stateLabel = state.replace(/_/g, ' ');
          trajHtml += `
            <div class="b-p612-bg" style="min-width:88px">
              <div class="ds-meta fs-11">Day ${day}</div>
              <div class="${stateClass} fs-11" style="font-weight:600">${escapeHtml(stateLabel)}</div>
            </div>
          `;
        }
        trajHtml += '</div>';
      }
      // Recommendation (derived server-side)
      const recHtml = data.recommendation
        ? `<div class="b-fs12-text-14 b-mt4-u">${escapeHtml(humanize(data.recommendation))}</div>`
        : '';
      // Evidence summary (transparency — P13: shows the user what the projection was derived from)
      let evHtml = '';
      if (data.evidence_summary) {
        const ev = data.evidence_summary;
        const breakdown = ev.mutation_breakdown || {};
        const breakdownParts = Object.keys(breakdown).map(k => `${escapeHtml(k.replace(/_/g, ' '))}: ${breakdown[k]}`);
        evHtml = `
          <div class="ds-meta fs-11 b-mt4-u" style="opacity:0.8">
            Derived from ${ev.history_count || 0} commitment${ev.history_count === 1 ? '' : 's'} ·
            ${ev.mutation_count || 0} mutation${ev.mutation_count === 1 ? '' : 's'} ·
            ${ev.history_span_days || 0}-day span
            ${breakdownParts.length > 0 ? ` · ${breakdownParts.join(' · ')}` : ''}
          </div>
        `;
      }
      el.innerHTML = `
        <div class="b-p812-bg b-mt4-u" style="border-left:3px solid var(--accent)">
          <div class="b-flex-gap4 b-flex-space-between">
            <div class="ds-meta fs-11">Trajectory</div>
            <div class="${riskClass} fs-11" style="font-weight:600">${escapeHtml(risk.toUpperCase())} RISK</div>
          </div>
          <div class="b-fs12-text-14 b-mt2-u">
            <span style="font-weight:600">${escapeHtml(patternLabel)}</span>
            · rate ${rate}/30d · ~${horizon} mutation${horizon === 1 ? '' : 's'} by Day 60
          </div>
          ${trajHtml}
          ${recHtml}
          ${evHtml}
          <button class="ds-btn ds-btn-ghost ds-btn-small fs-11 b-mt4-u" onclick="document.getElementById('${containerId}').innerHTML=''">Close</button>
        </div>
      `;
    } catch (e) {
      el.innerHTML = `<div class="ds-error fs-11">Failed: ${escapeHtml(e.message)}</div>`;
    }
  })();
}
