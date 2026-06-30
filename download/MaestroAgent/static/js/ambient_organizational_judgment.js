// AMBIENT ORGANIZATIONAL JUDGMENT — Pulse, Feed, Narrative, Cognitive Load
// ═══════════════════════════════════════════════════════════════════════════

async function loadPulse() {
  const body = document.getElementById('pulse-body');
  const stateEl = document.getElementById('pulse-state');
  if (!body) return;
  try {
    const p = await api.getOEM('/pulse');
    stateEl.textContent = p.state;
    const stateColor = p.state === 'healthy' || p.state === 'execution_accelerating' ? 'text-green-400'
      : p.state === 'turbulent' || p.state === 'trust_falling' ? 'text-red-400'
      : p.state === 'knowledge_blocked' || p.state === 'decision_stalled' ? 'text-yellow-400'
      : 'text-fg-300';
    stateEl.className = `text-[10px] font-semibold ${stateColor}`;
    body.innerHTML = `
      <div class="grid grid-cols-2 gap-2 text-xs">
        ${[['Temperature', p.temperature], ['Momentum', p.momentum], ['Alignment', p.alignment], ['Trust', p.trust], ['Knowledge', p.knowledge_mobility], ['Decision Speed', p.decision_speed]].map(([label, val]) => {
          const color = val > 70 ? 'text-green-400' : val < 40 ? 'text-red-400' : 'text-yellow-400';
          return `<div><div class="text-[10px] text-fg-500 uppercase">${label}</div><div class="font-bold ${color}">${Math.round(val)}</div></div>`;
        }).join('')}
      </div>
      <div class="mt-3 pt-3 border-t border-white/[0.05] text-xs text-fg-300">${escapeHtml(p.narrative)}</div>
    `;
  } catch (e) {
    body.innerHTML = `<div class="empty-state">Pulse unavailable: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadNarrative() {
  const body = document.getElementById('narrative-body');
  const dateEl = document.getElementById('narrative-date');
  if (!body) return;
  try {
    const n = await api.getOEM('/narrative');
    dateEl.textContent = n.date;
    body.innerHTML = `
      <div class="text-sm font-semibold text-white mb-2">${escapeHtml(n.title)}</div>
      <div class="text-xs text-fg-300 whitespace-pre-line mb-3">${escapeHtml(n.body)}</div>
      ${n.highlights && n.highlights.length > 0 ? `
        <div class="space-y-1">
          ${n.highlights.slice(0, 5).map(h => {
            const color = h.impact === 'positive' ? 'text-green-400' : h.impact === 'negative' ? 'text-red-400' : h.impact === 'warning' ? 'text-yellow-400' : 'text-fg-400';
            return `<div class="text-[11px] ${color}">• ${escapeHtml(h.text)}</div>`;
          }).join('')}
        </div>
      ` : ''}
      ${n.watch_for && n.watch_for.length > 0 ? `
        <div class="mt-2 pt-2 border-t border-white/[0.05] text-[10px] text-amber-400">${n.watch_for.slice(0, 2).map(w => escapeHtml(w)).join(' · ')}</div>
      ` : ''}
    `;
  } catch (e) {
    body.innerHTML = `<div class="empty-state">Narrative unavailable: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadFeed() {
  const body = document.getElementById('feed-body');
  if (!body) return;
  try {
    const data = await api.getOEM('/feed?limit=15');
    if (!data.events || data.events.length === 0) {
      body.innerHTML = '<div class="empty-state">No significant events. The organization is quiet.</div>';
      return;
    }
    body.innerHTML = data.events.map(e => {
      const color = e.event_type.includes('strengthened') || e.event_type.includes('renewed') || e.event_type.includes('correct') ? 'border-l-green-400'
        : e.event_type.includes('broken') || e.event_type.includes('churned') || e.event_type.includes('invalidated') ? 'border-l-red-400'
        : e.event_type.includes('drift') || e.event_type.includes('risk') || e.event_type.includes('overloaded') ? 'border-l-yellow-400'
        : 'border-l-cyan-400';
      return `
        <div class="border-l-2 ${color} pl-3 py-1.5 mb-1.5 cursor-pointer hover:bg-white/[0.02]" onclick="openFeedEvent('${escapeJs(e.event_type)}', '${escapeJs(e.entity_id)}')">
          <div class="flex items-center justify-between">
            <div class="text-xs font-semibold text-white">${escapeHtml(e.title)}</div>
            <div class="text-[9px] text-fg-500">${formatTimestamp(e.timestamp)}</div>
          </div>
          <div class="text-[10px] text-fg-400 mt-0.5">${escapeHtml(e.why_it_matters)}</div>
          <div class="text-[10px] text-fg-500 mt-0.5">→ ${escapeHtml(e.recommended_action)}</div>
        </div>
      `;
    }).join('');
  } catch (e) {
    body.innerHTML = `<div class="empty-state">Feed unavailable: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadCognitiveLoad() {
  const body = document.getElementById('ocl-body');
  const levelEl = document.getElementById('ocl-level');
  if (!body) return;
  try {
    const ocl = await api.getOEM('/cognitive-load');
    const color = ocl.level === 'low' ? 'text-green-400' : ocl.level === 'moderate' ? 'text-yellow-400' : ocl.level === 'high' ? 'text-orange-400' : 'text-red-400';
    levelEl.textContent = `${ocl.level} (${ocl.score})`;
    levelEl.className = `text-[10px] font-semibold ${color}`;
    const topFactors = Object.entries(ocl.factors).sort((a, b) => b[1].score - a[1].score).slice(0, 4);
    body.innerHTML = `
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        ${topFactors.map(([name, f]) => {
          const fc = f.score > 60 ? 'text-red-400' : f.score > 40 ? 'text-yellow-400' : 'text-green-400';
          return `<div><div class="text-[10px] text-fg-500 uppercase">${name.replace(/_/g, ' ')}</div><div class="font-bold ${fc}">${Math.round(f.score)}</div><div class="text-[9px] text-fg-400">${escapeHtml(f.detail)}</div></div>`;
        }).join('')}
      </div>
      <div class="mt-3 pt-3 border-t border-white/[0.05] text-xs text-fg-300">${escapeHtml(ocl.narrative)}</div>
      ${ocl.recommendations && ocl.recommendations.length > 0 ? `
        <div class="mt-2 text-[10px] text-cyan-400">→ ${escapeHtml(ocl.recommendations[0].recommendation)}</div>
      ` : ''}
    `;
  } catch (e) {
    body.innerHTML = `<div class="empty-state">OCL unavailable: ${escapeHtml(e.message)}</div>`;
  }
}

function openFeedEvent(eventType, entityId) {
  // Open the time machine for this entity
  if (entityId) {
    openDrilldown('feed_event', entityId);
  }
}

// ═══════════════════════════════════════════════════════════════════════════