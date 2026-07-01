// THE INVISIBLE MAESTRO — TODAY surface
// ═══════════════════════════════════════════════════════════════════════════
// The morning brief. When the CEO opens Maestro they should immediately
// understand what deserves attention. Nothing else.
//
// Structure:
//   Good morning.
//   Yesterday your organization became smarter.
//
//   One decision
//   One opportunity
//   One risk
//   One thing learned overnight
//   One prediction that changed
//
// No scrolling. No charts. No KPI overload. Calm. Like Apple Weather.
// ═══════════════════════════════════════════════════════════════════════════

async function loadToday() {
  const el = document.getElementById('today-content');
  if (!el) return;
  el.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Preparing your morning brief…</div>';

  try {
    // Compose the brief from existing API endpoints — no new backend needed
    const [briefing, pulse, contradictionsResp, personality] = await Promise.all([
      api.getOEM('/ceo-briefing'),
      api.getOEM('/pulse').catch(() => null),
      api.getOEM('/contradictions').catch(() => ({ contradictions: [] })),
      api.getOEM('/personality').catch(() => null),
    ]);
    const contradictions = contradictionsResp.contradictions || [];

    // Fetch time-axis for a relevant domain. Derive the domain from the
    // actual briefing data — not a hardcoded string. The auditor (round 15)
    // found that domain='engineering' always 404s with the demo seed because
    // the demo data has <5 signals for 'engineering'. We now try domains
    // that actually exist in the data: first from knowledge traps, then
    // from overnight changes, then fall back to 'payments' (which has
    // enough signals in the demo seed).
    let timeAxis = null;
    const trapDomain = (briefing.knowledge && briefing.knowledge.traps && briefing.knowledge.traps[0])
      ? (briefing.knowledge.traps[0].domain || '') : '';
    const changeDomain = (briefing.overnight && briefing.overnight.changes && briefing.overnight.changes[0])
      ? (briefing.overnight.changes[0].domain || '') : '';
    const domainsToTry = [trapDomain, changeDomain, 'payments', 'auth'].filter(d => d);
    for (const domain of domainsToTry) {
      try {
        timeAxis = await api.getOEM(`/time-axis?domain=${encodeURIComponent(domain)}`);
        if (timeAxis) break;
      } catch (e) {
        // 404 is honest — not enough data for this domain. Try the next one.
      }
    }

    // Fetch "so what?" for the top recommendation (if one exists)
    let sowhatData = null;
    const ot = briefing.one_thing || {};
    if (ot.title) {
      try {
        sowhatData = await api.getOEM(`/sowhat?entity_type=recommendation&entity_id=${encodeURIComponent(ot.title)}`);
      } catch (e) {
        // Fallback — use the hardcoded provenance
      }
    }

    // Fetch curiosity questions (V4 Organ #2)
    let curiosity = null;
    try {
      curiosity = await api.getOEM('/curiosity');
    } catch (e) {
      // Curiosity engine may not be available
    }

    // Fetch adaptive nudges (V6 Spec #1)
    let nudges = null;
    try {
      nudges = await api.getOEM('/nudges');
    } catch (e) {
      // Nudge engine may not be available
    }

    // Fetch background loop notices (V6 Spec #3)
    let backgroundLoop = null;
    try {
      backgroundLoop = await api.getOEM('/background-loop');
    } catch (e) {
      // Background loop may not be available
    }

    // Fetch trajectory interventions (V6 Spec #4)
    let interventions = null;
    try {
      interventions = await api.getOEM('/trajectory-intervention');
    } catch (e) {
      // Trajectory intervention may not be available
    }

    renderMorningBrief(el, briefing, pulse, contradictions, personality, timeAxis, sowhatData, curiosity, nudges, backgroundLoop, interventions);
  } catch (e) {
    el.innerHTML = `<div class="calm-empty">
      <div style="font-size:18px;color:var(--text-primary);margin-bottom:8px;">Good morning.</div>
      <div>We couldn't prepare your brief right now. The organization is still learning.</div>
      <button class="ds-btn ds-btn-ghost ds-btn-small" style="margin-top:16px;" onclick="loadToday()">Try again</button>
    </div>`;
  }
}

function renderMorningBrief(el, briefing, pulse, contradictions, personality, timeAxis, sowhatData, curiosity, nudges, backgroundLoop, interventions) {
  const ot = briefing.one_thing || {};
  const overnight = briefing.overnight || {};
  const changes = overnight.changes || [];
  const money = briefing.money || {};
  const knowledge = briefing.knowledge || {};

  // Pick one decision, one opportunity, one risk, one learning, one prediction
  // Each item answers the Constitution's implicit questions:
  //   Why now? Why me? What happens if ignored? How do we know?
  const decision = ot.title ? {
    label: 'One decision',
    title: ot.title,
    context: ot.why || ot.recommendation || '',
    provenance: ot.rec_id ? `Why now: ${ot.urgency || 'this pattern is active'}. Why you: only the CEO can unblock this. If ignored: the pattern will repeat. How we know: ${ot.impact || 'organizational memory'}.` : '',
    sowhat: sowhatData ? sowhatData.consequence_if_ignored : '',
    action: () => { if (ot.title) openDrilldown('recommendation', ot.title); },
  } : null;

  const opportunity = (money.losses && money.losses.length) ? {
    label: 'One opportunity',
    title: money.losses[0].title,
    context: money.losses[0].detail || '',
    provenance: money.losses[0].estimated_cost ? `So what: ${humanize(money.losses[0].estimated_cost)}. If addressed: the pattern won't repeat.` : '',
    action: () => { navTo('home'); },
  } : null;

  const risk = changes.find(c => c.severity === 'urgent' || c.severity === 'warning') || changes[0];
  const riskItem = risk ? {
    label: risk.severity === 'urgent' ? 'One risk' : 'One thing changed overnight',
    title: risk.title || risk.detail || '',
    context: risk.detail || '',
    provenance: risk.entity || risk.domain ? `Where: ${humanize(risk.entity || risk.domain || '')}. So what: this shifted the organizational pattern.` : '',
    action: () => { navTo('home'); },
  } : null;

  const learning = (knowledge.traps && knowledge.traps.length) ? {
    label: 'One thing learned',
    title: knowledge.traps[0].title || knowledge.traps[0].risk || '',
    context: knowledge.traps[0].detail || '',
    provenance: timeAxis && timeAxis.future ? `Trajectory: ${humanize(timeAxis.future.prediction)}` : 'From organizational patterns',
    action: () => { navTo('assumptions'); },
  } : (timeAxis ? {
    label: 'One thing learned',
    title: timeAxis.present ? timeAxis.present.state : 'Organizational pattern detected',
    context: timeAxis.past ? timeAxis.past.summary : '',
    provenance: timeAxis.future ? `Trajectory: ${humanize(timeAxis.future.prediction)}` : '',
    action: () => { navTo('physics'); },
  } : null);

  // Prediction that changed — from the learning report
  const predictionChanged = briefing.improvement || null;
  const predictionItem = predictionChanged ? {
    label: 'One prediction that changed',
    title: predictionChanged.summary || predictionChanged.evidence || '',
    context: '',
    provenance: '',
    action: () => { navTo('predictions'); },
  } : null;

  const items = [decision, opportunity, riskItem, learning, predictionItem].filter(Boolean);

  // Determine the organizational dot color
  const dotColor = determineDotColor(briefing, contradictions);
  updateOrgDot(dotColor);

  // Determine the weather forecast
  const weather = determineWeather(pulse, briefing);

  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning.' : hour < 18 ? 'Good afternoon.' : 'Good evening.';

  let html = `
    <div class="meta-surface">
      <div class="meta-surface greeting">${greeting}</div>
      <div class="meta-surface sub-greeting">
        <span class="org-heartbeat"></span>
        ${items.length > 0 ? `${items.length} ${items.length === 1 ? 'thing' : 'things'} deserve attention.` : 'Everything is calm. Your organization is working well.'}
      </div>
  `;

  // Organizational personality one-liner (V3 Law 6)
  if (personality && personality.summary) {
    html += `
      <div style="padding:12px 16px;border-radius:8px;background:var(--surface);border:1px solid var(--divider);margin-bottom:20px;font-size:13px;color:var(--text-secondary);line-height:1.5;">
        ${escapeHtml(humanize(personality.summary))}
      </div>
    `;
  }

  // Organizational weather
  if (weather) {
    html += `
      <div class="weather-card">
        <div class="weather-forecast">${weather.forecast}</div>
        ${weather.detail ? `<div class="weather-detail">${weather.detail}</div>` : ''}
      </div>
    `;
  }

  // Brief items
  if (items.length === 0) {
    html += `<div class="calm-empty">
      <div>Nothing requires your attention right now.</div>
      <div style="margin-top:8px;font-size:13px;">Maestro is watching. You'll know when something matters.</div>
    </div>`;
  } else {
    items.forEach((item, i) => {
      const prepareBtn = item.label === 'One decision' ? `<button class="ds-btn ds-btn-primary ds-btn-small" style="margin-top:10px;" onclick="prepareExecution('${escapeJs(item.title)}')">Prepare</button>` : '';
      html += `
        <div class="brief-item" data-idx="${i}">
          <div class="brief-label">${escapeHtml(item.label)}</div>
          <div class="brief-title">${escapeHtml(humanize(item.title))}</div>
          ${item.context ? `<div class="brief-context">${escapeHtml(humanize(item.context))}</div>` : ''}
          ${item.provenance ? `<div class="brief-provenance">${escapeHtml(humanize(item.provenance))}</div>` : ''}
          ${item.sowhat ? `<div class="brief-context" style="margin-top:8px;color:var(--accent);font-weight:500;">So what: ${escapeHtml(humanize(item.sowhat))}</div>` : ''}
          ${prepareBtn}
        </div>
      `;
    });
  }

  // V6 Spec #3 — Background Loop: "Maestro noticed this while you were away"
  if (backgroundLoop && backgroundLoop.notices && backgroundLoop.notices.length > 0) {
    html += `
      <div style="margin-top:24px;padding:20px;border-radius:12px;background:var(--surface);border:1px solid var(--divider);">
        <div class="brief-label" style="color:var(--text-muted);">While you were away</div>
        <div style="font-size:14px;color:var(--text-secondary);margin-bottom:12px;">${escapeHtml(humanize(backgroundLoop.summary || ''))}</div>
        ${backgroundLoop.notices.slice(0, 3).map(n => {
          const color = n.urgency === 'high' ? 'var(--risk)' : n.urgency === 'medium' ? 'var(--warning)' : 'var(--text-secondary)';
          return `<div style="padding:8px 0;border-bottom:1px solid var(--divider);">
            <div style="font-size:13px;color:${color};">${escapeHtml(humanize(n.message || ''))}</div>
            ${n.detail ? `<div class="ds-meta" style="margin-top:2px;">${escapeHtml(humanize(n.detail))}</div>` : ''}
          </div>`;
        }).join('')}
      </div>
    `;
  }

  // V6 Spec #4 — Trajectory Intervention: declining trajectories that need action
  if (interventions && interventions.interventions && interventions.interventions.length > 0) {
    html += `
      <div style="margin-top:24px;padding:20px;border-radius:12px;background:var(--surface);border:1px solid rgba(239,68,68,0.2);">
        <div class="brief-label" style="color:var(--risk);">Needs attention</div>
        <div style="font-size:14px;color:var(--text-secondary);margin-bottom:12px;">${escapeHtml(humanize(interventions.summary || ''))}</div>
        ${interventions.interventions.slice(0, 2).map(iv => `
          <div style="padding:10px 0;border-bottom:1px solid var(--divider);">
            <div style="font-size:14px;color:var(--text-primary);font-weight:500;">${escapeHtml(humanize(iv.intervention || ''))}</div>
            <div class="ds-meta" style="margin-top:4px;">Time to impact: ${escapeHtml(iv.time_to_failure || '')} · Urgency: ${escapeHtml(iv.urgency || '')}</div>
          </div>
        `).join('')}
      </div>
    `;
  }

  // V6 Spec #1 — Adaptive Nudges: actionable restructuring suggestions
  if (nudges && nudges.nudges && nudges.nudges.length > 0) {
    html += `
      <div style="margin-top:32px;padding:20px;border-radius:12px;background:var(--surface);border:1px solid var(--accent-border);">
        <div class="brief-label" style="color:var(--accent);">Maestro suggests a change</div>
        <div style="font-size:14px;color:var(--text-secondary);margin-bottom:16px;">${escapeHtml(humanize(nudges.summary || ''))}</div>
        ${nudges.nudges.slice(0, 2).map((n, i) => `
          <div class="brief-item" data-nudge-idx="${i}" style="border-bottom:1px solid var(--divider);">
            <div style="font-size:14px;color:var(--text-primary);font-weight:500;margin-bottom:4px;">${escapeHtml(humanize(n.intervention || ''))}</div>
            <div class="brief-context" style="font-size:12px;">${escapeHtml(humanize(n.evidence || ''))}</div>
            <div class="ds-row" style="gap:6px;margin-top:8px;">
              <button class="ds-btn ds-btn-positive ds-btn-small" onclick="this.closest('.brief-item').style.opacity='0.5';this.textContent='Accepted'">Accept</button>
              <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="this.closest('.brief-item').style.display='none'">Dismiss</button>
            </div>
          </div>
        `).join('')}
      </div>
    `;
  }

  // V4 Organ #2 — Curiosity: questions the org has never asked
  if (curiosity && curiosity.questions && curiosity.questions.length > 0) {
    html += `
      <div style="margin-top:32px;padding:20px;border-radius:12px;background:var(--surface);border:1px solid var(--divider);">
        <div class="brief-label" style="color:var(--accent);">Maestro is curious</div>
        <div style="font-size:14px;color:var(--text-secondary);margin-bottom:16px;">${escapeHtml(humanize(curiosity.summary))}</div>
        ${curiosity.questions.slice(0, 3).map((q, i) => `
          <div class="brief-item" data-curiosity-idx="${i}" style="border-bottom:1px solid var(--divider);">
            <div class="brief-context" style="color:var(--text-primary);font-weight:500;">${escapeHtml(humanize(q.question))}</div>
            <div class="brief-provenance">${escapeHtml(humanize(q.evidence))}</div>
          </div>
        `).join('')}
      </div>
    `;
  }

  html += `</div>`;
  el.innerHTML = html;

  // Wire up click handlers
  items.forEach((item, i) => {
    const itemEl = el.querySelector(`.brief-item[data-idx="${i}"]`);
    if (itemEl && item.action) {
      itemEl.addEventListener('click', item.action);
    }
  });
}

function determineDotColor(briefing, contradictionsOrPulse) {
  // Red: urgent decision needed
  if (briefing.one_thing && briefing.one_thing.urgency === 'urgent') return 'red';
  // Orange: cross-functional impact (contradictions detected)
  // The contradictions parameter can be an array (from /contradictions API)
  // or an object with a .contradictions array (from the briefing)
  let contradictions = [];
  if (Array.isArray(contradictionsOrPulse)) {
    contradictions = contradictionsOrPulse;
  } else if (contradictionsOrPulse && contradictionsOrPulse.contradictions) {
    contradictions = contradictionsOrPulse.contradictions;
  }
  if (contradictions.length > 0) return 'orange';
  // Yellow: opportunity or overnight change
  if (briefing.overnight && briefing.overnight.changes && briefing.overnight.changes.length > 0) return 'yellow';
  // Green: nothing requires attention
  return 'green';
}

function determineWeather(pulse, briefing) {
  if (!pulse) return null;

  const temp = pulse.temperature || 'neutral';
  const momentum = pulse.momentum || 'stable';

  // Map pulse metrics to weather metaphors
  if (temp === 'hot' || temp === 'tension') {
    return {
      forecast: 'Decision Storm — organizational tension is high.',
      detail: momentum === 'accelerating' ? 'Pressure is building. Decisions made now will propagate fast.' : 'Tension is stable but present.',
    };
  }
  if (temp === 'cold' || temp === 'calm') {
    return {
      forecast: 'Calm Execution Window.',
      detail: 'Low tension. Good time for long-term work.',
    };
  }
  if (momentum === 'accelerating') {
    return {
      forecast: 'Knowledge Front moving through the organization.',
      detail: 'New patterns are forming. Decisions will be easier soon.',
    };
  }
  if (momentum === 'decelerating') {
    return {
      forecast: 'Heavy Review Traffic expected.',
      detail: 'Decisions are slowing. Consider unblocking bottlenecks.',
    };
  }
  return {
    forecast: 'Stable conditions.',
    detail: 'The organization is operating normally.',
  };
}

// V5 Spec #2 — Executive Function: Prepare an execution plan
async function prepareExecution(title) {
  // Open the drill-down modal with the execution plan
  openDrilldown('recommendation', title);
  // Switch to the So What? tab first (which has the consequence),
  // then the user can click "Prepare" to see the full plan
  setTimeout(async () => {
    const body = document.getElementById('drilldown-body');
    if (!body) return;
    body.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Preparing execution plan…</div>';
    try {
      const plan = await api.getOEM(`/execute?recommendation_id=${encodeURIComponent(title)}`);
      body.innerHTML = `
        <div class="ds-stack">
          <div>
            <div class="ds-cascade-label">Execution plan</div>
            <div style="font-size:15px;color:var(--text-primary);margin-bottom:16px;">${escapeHtml(humanize(plan.summary || ''))}</div>
          </div>
          ${plan.steps ? plan.steps.map(s => `
            <div class="ds-card" style="padding:14px;">
              <div class="ds-row-between" style="margin-bottom:6px;">
                <span class="ds-tag ds-tag-pending">Step ${s.step}</span>
                <span class="ds-meta">${escapeHtml(s.estimated_time || '')}</span>
              </div>
              <div style="font-size:14px;font-weight:500;color:var(--text-primary);margin-bottom:4px;">${escapeHtml(humanize(s.title || ''))}</div>
              <div style="font-size:13px;color:var(--text-secondary);">${escapeHtml(humanize(s.detail || ''))}</div>
              <div class="ds-meta" style="margin-top:6px;">Owner: ${escapeHtml(humanize(s.owner || ''))}${s.prerequisite ? ' · After: ' + escapeHtml(humanize(s.prerequisite)) : ''}</div>
            </div>
          `).join('') : ''}
          <div>
            <div class="ds-cascade-label">Drafted briefing</div>
            <div style="padding:14px;background:var(--surface-2);border-radius:8px;font-size:13px;color:var(--text-secondary);white-space:pre-wrap;line-height:1.6;">${escapeHtml(humanize(plan.drafted_briefing || ''))}</div>
          </div>
          <div>
            <div class="ds-cascade-label">Follow-through</div>
            <div style="font-size:13px;color:var(--text-secondary);">
              Check-in: ${escapeHtml(plan.follow_through?.check_in_date || '')}<br>
              Success: ${escapeHtml(humanize(plan.follow_through?.success_metric || ''))}
            </div>
          </div>
        </div>
      `;
    } catch (e) {
      body.innerHTML = `<div class="ds-error">Failed to prepare: ${escapeHtml(e.message)}</div>`;
    }
  }, 500);
}

// ═══════════════════════════════════════════════════════════════════════════
