// LIVE MEETING — real OEM-driven meeting intelligence (NO hardcoded script)
// ═══════════════════════════════════════════════════════════════════════════

let liveTimer = null;

// Clean up Live Meeting timers when navigating away
function teardownLive() {
  if (liveTimer) { clearTimeout(liveTimer); liveTimer = null; }
}

async function startLiveMeeting() {
  if (liveTimer) { clearTimeout(liveTimer); liveTimer = null; }
  document.getElementById('transcript-area').innerHTML = '';
  document.getElementById('live-obj-count').textContent = '0';
  document.getElementById('live-ai-count').textContent = '0';
  document.getElementById('live-law-count').textContent = '0';
  document.getElementById('live-objections').innerHTML = 'No objections yet.';
  document.getElementById('live-actions').innerHTML = 'No action items yet.';
  document.getElementById('live-laws').innerHTML = 'No laws triggered yet.';
  document.getElementById('live-start-btn').textContent = 'Replay Meeting';

  const transcriptArea = document.getElementById('transcript-area');
  transcriptArea.innerHTML = '<div class="text-[11px] text-fg-500 italic">Paste a transcript below and click "Analyze with OEM" — the OEM will detect objections, laws triggered, and action items in real time.</div>';

  const inputArea = document.getElementById('live-transcript-input');
  if (inputArea) inputArea.style.display = 'block';
}

async function analyzeTranscript() {
  const input = document.getElementById('live-transcript-textarea');
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;

  // Parse the textarea into a transcript (one line per turn, "Speaker: text")
  const lines = text.split('\n').filter(l => l.trim());
  const transcript = lines.map(line => {
    const idx = line.indexOf(':');
    if (idx > 0) {
      return { speaker: line.slice(0, idx).trim(), text: line.slice(idx + 1).trim() };
    }
    return { speaker: 'Unknown', text: line };
  });

  const transcriptArea = document.getElementById('transcript-area');

  // Build the entire transcript HTML in one string, then assign once.
  // This is O(n) instead of O(n²) — the old `innerHTML +=` re-parsed
  // the entire DOM on each line append.
  const transcriptHtml = transcript.map((line, i) => `<div class="flex gap-3 p-2 rounded-md bg-white/[0.02] mb-1">
      <span class="text-[10px] text-fg-500 mono w-12">${String(i+1).padStart(2,'0')}</span>
      <span class="text-xs font-semibold text-brand-cyan w-20">${escapeHtml(line.speaker)}</span>
      <span class="text-xs text-fg-200 flex-1">${escapeHtml(humanize(line.text))}</span>
    </div>`).join('');
  transcriptArea.innerHTML = transcriptHtml;

  // Analyze via OEM
  document.getElementById('live-objections').innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  document.getElementById('live-actions').innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  document.getElementById('live-laws').innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    const resp = await fetch(MAESTRO_API + '/api/oem/meetings/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ transcript }),
    });
    if (!resp.ok) throw new Error('Analyze failed: ' + resp.status);
    const data = await resp.json();

    document.getElementById('live-obj-count').textContent = data.summary.objection_count;
    document.getElementById('live-ai-count').textContent = data.summary.action_count;
    document.getElementById('live-law-count').textContent = data.summary.law_count;

    document.getElementById('live-objections').innerHTML = data.objections.length === 0
      ? '<div class="text-[11px] text-fg-500">No objections detected.</div>'
      : data.objections.map(o => `
        <div class="p-2 rounded-md bg-brand-rose/[0.06] border-l-2 border-brand-rose mb-1">
          <div class="text-brand-rose font-semibold text-[11px]">${escapeHtml(o.speaker)} dissents</div>
          <div class="text-[10px] text-fg-500">${escapeHtml(humanize(o.text))}</div>
          ${o.law_code ? `<div class="text-[10px] text-fg-600 mt-1">Linked: <span class="source-cite">${escapeHtml(o.law_code)}</span></div>` : ''}
        </div>
      `).join('');

    document.getElementById('live-actions').innerHTML = data.actions.length === 0
      ? '<div class="text-[11px] text-fg-500">No action items detected.</div>'
      : data.actions.map(a => `
        <div class="flex items-center gap-2 text-[11px] py-1">
          <div class="w-3 h-3 border border-white/20 rounded-sm"></div>
          <span class="text-fg-200 flex-1">${escapeHtml(humanize(a.text))}</span>
          <span class="text-fg-500">@${escapeHtml(a.owner)}</span>
        </div>
      `).join('');

    document.getElementById('live-laws').innerHTML = data.laws_triggered.length === 0
      ? '<div class="text-[11px] text-fg-500">No laws triggered.</div>'
      : data.laws_triggered.map(l => `
        <div class="flex items-center gap-2 text-[11px] py-1">
          <span class="source-cite">${escapeHtml(l.code)}</span>
          <span class="text-fg-400">${escapeHtml(l.statement.substring(0, 60))}…</span>
        </div>
      `).join('');
  } catch (e) {
    document.getElementById('live-objections').innerHTML = `<div class="text-[11px] text-brand-rose">Error: ${escapeHtml(e.message)}</div>`;
    document.getElementById('live-actions').innerHTML = '';
    document.getElementById('live-laws').innerHTML = '';
    showError('Meeting analysis failed: ' + e.message);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// ENG: SIGNALS
// ═══════════════════════════════════════════════════════════════════════════

async function loadEngSignals() {
  const el = document.getElementById('eng-signals-list');
  loadingHTML(el);
  try {
    const data = await api.getOEM('/state');
    el.innerHTML = `
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        ${data.providers.map(p => `
          <div class="card">
            <div class="flex items-center justify-between mb-2">
              <div class="text-sm font-semibold text-white">${escapeHtml(humanize(p.label))}</div>
              <span class="tag tag-cyan">connected</span>
            </div>
            <div class="text-[11px] text-fg-400">${escapeHtml(p.provider)}</div>
            <div class="text-[10px] text-fg-500 mt-2">${p.signal_count} signals processed</div>
            <div class="text-[10px] text-fg-500">Tracks: ${escapeHtml(p.artifact_label)}</div>
          </div>
        `).join('')}
      </div>
      <div class="mt-4 pt-4 border-t border-white/[0.05] grid grid-cols-2 md:grid-cols-4 gap-4">
        <div class="metric"><div class="metric-value">${data.summary.signals_processed}</div><div class="metric-label">Total Signals</div></div>
        <div class="metric"><div class="metric-value">${data.summary.learning_objects}</div><div class="metric-label">Learning Objects</div></div>
        <div class="metric"><div class="metric-value">${data.summary.patterns_detected}</div><div class="metric-label">Patterns</div></div>
        <div class="metric"><div class="metric-value">${data.summary.laws_inferred}</div><div class="metric-label">Laws</div></div>
      </div>
    `;
  } catch (e) {
    errorHTML(el, e.message, 'loadEngSignals()');
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// ENG: OEM BUILDER
// ═══════════════════════════════════════════════════════════════════════════

async function loadEngOEM() {
  const el = document.getElementById('eng-oem-pipeline');
  loadingHTML(el);
  try {
    const data = await api.getOEM('/state');
    const s = data.summary;
    el.innerHTML = `
      <div class="space-y-3">
        <div class="flex items-center gap-3 text-[11px]"><span class="w-2 h-2 rounded-full bg-brand-cyan"></span><span class="text-fg-200 flex-1">Ingesting signals from ${s.providers_connected.length} sources</span><span class="mono text-brand-cyan">${s.signals_processed}</span></div>
        <div class="flex items-center gap-3 text-[11px]"><span class="w-2 h-2 rounded-full bg-brand-amber"></span><span class="text-fg-200 flex-1">Learning objects inferred</span><span class="mono text-brand-amber">${s.learning_objects}</span></div>
        <div class="flex items-center gap-3 text-[11px]"><span class="w-2 h-2 rounded-full bg-brand-purple"></span><span class="text-fg-200 flex-1">Patterns detected</span><span class="mono text-brand-purple">${s.patterns_detected}</span></div>
        <div class="flex items-center gap-3 text-[11px]"><span class="w-2 h-2 rounded-full bg-brand-rose"></span><span class="text-fg-200 flex-1">Laws inferred</span><span class="mono text-brand-rose">${s.laws_inferred}</span></div>
        <div class="flex items-center gap-3 text-[11px]"><span class="w-2 h-2 rounded-full bg-brand-cyan"></span><span class="text-fg-200 flex-1">Validated laws</span><span class="mono text-brand-cyan">${s.validated_laws}</span></div>
        <div class="flex items-center gap-3 text-[11px]"><span class="w-2 h-2 rounded-full bg-brand-sky"></span><span class="text-fg-200 flex-1">Hidden experts</span><span class="mono text-brand-sky">${s.hidden_experts}</span></div>
        <div class="flex items-center gap-3 text-[11px]"><span class="w-2 h-2 rounded-full bg-brand-amber"></span><span class="text-fg-200 flex-1">Bottlenecks</span><span class="mono text-brand-amber">${s.bottlenecks}</span></div>
        <div class="flex items-center gap-3 text-[11px]"><span class="w-2 h-2 rounded-full bg-brand-rose"></span><span class="text-fg-200 flex-1">Departure risks</span><span class="mono text-brand-rose">${s.departure_risks}</span></div>
      </div>
      <div class="mt-4 pt-4 border-t border-white/[0.05] text-[10px] text-fg-500">Last updated: ${escapeHtml(data.last_updated || 'unknown')}</div>
    `;
  } catch (e) {
    errorHTML(el, e.message, 'loadEngOEM()');
  }
}

// ═══════════════════════════════════════════════════════════════════════════