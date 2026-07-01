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
    const [briefing, pulse, contradictionsResp] = await Promise.all([
      api.getOEM('/ceo-briefing'),
      api.getOEM('/pulse').catch(() => null),
      api.getOEM('/contradictions').catch(() => ({ contradictions: [] })),
    ]);
    const contradictions = contradictionsResp.contradictions || [];

    renderMorningBrief(el, briefing, pulse, contradictions);
  } catch (e) {
    el.innerHTML = `<div class="calm-empty">
      <div style="font-size:18px;color:var(--text-primary);margin-bottom:8px;">Good morning.</div>
      <div>We couldn't prepare your brief right now. The organization is still learning.</div>
      <button class="ds-btn ds-btn-ghost ds-btn-small" style="margin-top:16px;" onclick="loadToday()">Try again</button>
    </div>`;
  }
}

function renderMorningBrief(el, briefing, pulse, contradictions) {
  const ot = briefing.one_thing || {};
  const overnight = briefing.overnight || {};
  const changes = overnight.changes || [];
  const money = briefing.money || {};
  const knowledge = briefing.knowledge || {};

  // Pick one decision, one opportunity, one risk, one learning, one prediction
  const decision = ot.title ? {
    label: 'One decision',
    title: ot.title,
    context: ot.why || ot.recommendation || '',
    provenance: ot.rec_id ? `Based on organizational patterns` : '',
    action: () => { if (ot.title) openDrilldown('recommendation', ot.title); },
  } : null;

  const opportunity = (money.losses && money.losses.length) ? {
    label: 'One opportunity',
    title: money.losses[0].title,
    context: money.losses[0].detail || '',
    provenance: money.losses[0].estimated_cost || '',
    action: () => { navTo('home'); },
  } : null;

  const risk = changes.find(c => c.severity === 'urgent' || c.severity === 'warning') || changes[0];
  const riskItem = risk ? {
    label: risk.severity === 'urgent' ? 'One risk' : 'One thing changed overnight',
    title: risk.title || risk.detail || '',
    context: risk.detail || '',
    provenance: risk.entity || risk.domain || '',
    action: () => { navTo('home'); },
  } : null;

  const learning = (knowledge.traps && knowledge.traps.length) ? {
    label: 'One thing learned',
    title: knowledge.traps[0].title || knowledge.traps[0].risk || '',
    context: knowledge.traps[0].detail || '',
    provenance: 'From organizational patterns',
    action: () => { navTo('assumptions'); },
  } : null;

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
      html += `
        <div class="brief-item" data-idx="${i}">
          <div class="brief-label">${escapeHtml(item.label)}</div>
          <div class="brief-title">${escapeHtml(item.title)}</div>
          ${item.context ? `<div class="brief-context">${escapeHtml(item.context)}</div>` : ''}
          ${item.provenance ? `<div class="brief-provenance">${escapeHtml(item.provenance)}</div>` : ''}
        </div>
      `;
    });
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

// ═══════════════════════════════════════════════════════════════════════════
