// ASK — backend-driven autocomplete (NO hardcoded suggestions)
// ═══════════════════════════════════════════════════════════════════════════
// Round 78 Phase 4: added ESC handler + 150ms debounce.
// The auditor flagged: "Key handler in ask.js handles arrows/enter but not ESC"
// and "Per-keystroke fetch with abort; stale protection exists, but no
// debounce/throttle budget." Both are now fixed.

let autocompleteAbort = null;
let autocompleteSelectedIdx = -1;
let autocompleteSuggestions = [];  // Store full suggestion objects for rich rendering
let _askDebounceTimer = null;
const _ASK_DEBOUNCE_MS = 150;

function onAskInput(value) {
  // Debounce: don't fire on every keystroke — wait 150ms of inactivity.
  // This reduces request pressure under rapid typing (auditor's MEDIUM finding).
  clearTimeout(_askDebounceTimer);
  _askDebounceTimer = setTimeout(() => _doAskInput(value), _ASK_DEBOUNCE_MS);
}

async function _doAskInput(value) {
  const dropdown = document.getElementById('exec-autocomplete');
  const v = value.trim();
  if (!v) {
    dropdown.classList.remove('active');
    autocompleteSuggestions = [];
    return;
  }

  if (autocompleteAbort) autocompleteAbort.abort();
  autocompleteAbort = new AbortController();

  // Include the current surface as context for context-aware ranking
  const surface = window._currentSurface || '';
  const contextParam = surface ? `&surface=${encodeURIComponent(surface)}` : '';

  try {
    const resp = await fetch(
      MAESTRO_API + '/api/oem/autocomplete?q=' + encodeURIComponent(v) + '&limit=8' + contextParam,
      { signal: autocompleteAbort.signal }
    );
    if (!resp.ok) throw new Error('Autocomplete failed: ' + resp.status);
    const data = await resp.json();
    const suggestions = data.suggestions || [];
    autocompleteSuggestions = suggestions;

    if (suggestions.length === 0) {
      dropdown.innerHTML = `<div class="exec-ac-header" role="status">No matches in OEM for "${escapeHtml(v)}"</div>`;
      dropdown.classList.add('active');
      autocompleteSelectedIdx = -1;
      return;
    }

    autocompleteSelectedIdx = -1;
    // Build rich dropdown with completion, reason, confidence, citations
    dropdown.setAttribute('role', 'listbox');
    dropdown.setAttribute('aria-label', 'Organizational autocomplete suggestions');
    dropdown.innerHTML = `<div class="exec-ac-header">Semantic suggestions · from live OEM · ranked by recency, authority, outcome, feedback</div>` +
      suggestions.map((s, i) => {
        const confPct = Math.round((s.confidence || 0) * 100);
        const rankPct = Math.round((s.rank_score || 0) * 100);
        const citations = (s.citations || []).slice(0, 3).map(c => {
          const short = String(c).substring(0, 20);
          return `<span class="source-cite" title="${escapeHtml(c)}">${escapeHtml(short)}</span>`;
        }).join(' ');
        const evidenceCount = (s.evidence || []).length;
        const similarCount = (s.similar_executions || []).length;
        const sourceIcon = {
          'law': 'L', 'recommendation': 'R', 'expert': '?', 'risk': '!',
          'evidence': 'E', 'lo:bottleneck': 'B', 'lo:hidden_expert': '?',
          'lo:departure_risk': 'X', 'lo:duplicate_work': 'D', 'lo:knowledge_death': 'K',
          'lo:approval_gate': 'G', 'lo:incident_pattern': 'I', 'lo:velocity_drop': 'V',
        }[s.source_type] || '*';
        return `<div class="exec-ac-item" data-idx="${i}" data-query="${escapeHtml(s.query)}" role="option" aria-selected="false" tabindex="-1" onmouseenter="autocompleteSelectedIdx=${i}; updateAutocompleteHighlight()" onclick="selectAutocomplete(${i})">
          <div class="exec-ac-completion">
            <span class="completed">${escapeHtml(s.completion)}</span>
          </div>
          <div class="text-[10px] text-fg-400 mt-1 leading-relaxed">${escapeHtml(s.reason)}</div>
          <div class="flex items-center gap-2 mt-1.5 text-[9px] text-fg-500 flex-wrap">
            <span class="mono text-brand-purple">[${escapeHtml(s.source_type)}]</span>
            <span class="text-brand-cyan">conf ${confPct}%</span>
            <span>·</span>
            <span>rank ${rankPct}%</span>
            <span>·</span>
            <span>${evidenceCount} evidence</span>
            ${similarCount ? `<span>·</span><span>${similarCount} similar</span>` : ''}
          </div>
          ${citations ? `<div class="mt-1 flex flex-wrap gap-1">${citations}</div>` : ''}
          ${s.expected_outcome ? `<div class="text-[9px] text-fg-600 mt-1 italic">→ ${escapeHtml(s.expected_outcome.substring(0, 100))}</div>` : ''}
        </div>`;
      }).join('');
    dropdown.classList.add('active');
  } catch (e) {
    if (e.name === 'AbortError') return;
    dropdown.innerHTML = `<div class="exec-ac-header" role="alert">Autocomplete error: ${escapeHtml(e.message)}</div>`;
    dropdown.classList.add('active');
  }
}

function updateAutocompleteHighlight() {
  document.querySelectorAll('.exec-ac-item').forEach((el, i) => {
    const selected = i === autocompleteSelectedIdx;
    el.classList.toggle('selected', selected);
    el.setAttribute('aria-selected', selected ? 'true' : 'false');
  });
  // Scroll the selected item into view
  if (autocompleteSelectedIdx >= 0) {
    const sel = document.querySelector(`.exec-ac-item[data-idx="${autocompleteSelectedIdx}"]`);
    if (sel) sel.scrollIntoView({ block: 'nearest' });
  }
}

function selectAutocomplete(idx) {
  const item = document.querySelector(`.exec-ac-item[data-idx="${idx}"]`);
  if (!item) return;
  const query = item.dataset.query;
  // Fill the input with the completion text (not the query) for a natural feel
  const suggestion = autocompleteSuggestions[idx];
  if (suggestion && suggestion.completion) {
    document.getElementById('ask-input').value = suggestion.completion;
  } else {
    document.getElementById('ask-input').value = query;
  }
  document.getElementById('exec-autocomplete').classList.remove('active');
  submitAsk(query);
}

document.addEventListener('keydown', (e) => {
  const dropdown = document.getElementById('exec-autocomplete');
  if (!dropdown || !dropdown.classList.contains('active')) return;
  const items = dropdown.querySelectorAll('.exec-ac-item');
  if (items.length === 0) return;

  if (e.key === 'ArrowDown') {
    e.preventDefault();
    autocompleteSelectedIdx = (autocompleteSelectedIdx + 1) % items.length;
    updateAutocompleteHighlight();
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    autocompleteSelectedIdx = (autocompleteSelectedIdx - 1 + items.length) % items.length;
    updateAutocompleteHighlight();
  } else if (e.key === 'Enter' && autocompleteSelectedIdx >= 0) {
    e.preventDefault();
    selectAutocomplete(autocompleteSelectedIdx);
  } else if (e.key === 'Escape') {
    // Round 78 Phase 4: ESC closes the dropdown and returns focus to the input.
    // The auditor flagged: "Key handler handles arrows/enter but not ESC."
    e.preventDefault();
    dropdown.classList.remove('active');
    autocompleteSelectedIdx = -1;
    document.getElementById('ask-input').focus();
  }
});

async function submitAsk(query) {
  const q = query.trim();
  if (!q) return;
  document.getElementById('ask-input').value = '';
  document.getElementById('exec-autocomplete').classList.remove('active');
  document.getElementById('ask-suggestions').style.display = 'none';
  const answerDiv = document.getElementById('ask-answer');
  answerDiv.style.display = 'block';
  document.getElementById('ask-answer-text').innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  document.getElementById('ask-citations').innerHTML = '';
  document.getElementById('ask-path').textContent = '';
  document.getElementById('ask-confidence').textContent = '';
  answerDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  try {
    // Phase 2.2: Migrate from GET /ask (old, cross-customer) to POST /ask/conversation (AskPipeline)
    if (!window._askSessionId) {
      try { window._askSessionId = crypto.randomUUID(); }
      catch(e) { window._askSessionId = 'sess-' + Date.now() + '-' + Math.random().toString(36).slice(2,11); }
    }
    const resp = await MaestroAPI.post('/ask/conversation', { query: q, history: [], session_id: window._askSessionId });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    document.getElementById('ask-answer-text').innerHTML = escapeHtml(humanize(data.answer || '')).replace(/\n/g, '<br>');
    const sources = data.sources || (data.evidence || []).map(e => e.source || 'unknown');
    document.getElementById('ask-citations').innerHTML = sources.length === 0
      ? '<span class="text-[11px] text-fg-500">No sources cited (insufficient evidence).</span>'
      : sources.map(s => `<span class="source-cite">${escapeHtml(s)}</span>`).join('');
    const path = data.evidence_path || data.evidence || [];
    document.getElementById('ask-path').textContent = path.length === 0
      ? 'No evidence path available.'
      : path.map(p => (p.source || p.type || '') + (p.text ? ': ' + p.text.substring(0,40) : '')).join(' → ');
    // CEO directive: confidence removed from /ask responses
    document.getElementById('ask-confidence').textContent = `${sources.length} sources`;
  } catch (e) {
    document.getElementById('ask-answer-text').innerHTML = `<span class="text-brand-rose">Error: ${escapeHtml(e.message)}</span>`;
    showError('Ask failed: ' + e.message);
  }
}

// ═══════════════════════════════════════════════════════════════════════════