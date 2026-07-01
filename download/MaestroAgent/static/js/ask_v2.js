// THE INVISIBLE MAESTRO — ASK surface
// ═══════════════════════════════════════════════════════════════════════════
// Replace search with intention. Never ask "Search..." — instead ask
// "What are you trying to accomplish?"
//
// The system translates intentions into organizational knowledge.
// ═══════════════════════════════════════════════════════════════════════════

const _intentionPrompts = [
  { label: 'Ship safely', text: 'Ship OAuth safely.' },
  { label: 'Reduce failures', text: 'Reduce deployment failures.' },
  { label: 'Understand tension', text: 'Understand why Legal disagrees.' },
  { label: 'Prepare meeting', text: 'Prepare tomorrow\'s board meeting.' },
  { label: 'Find bottleneck', text: 'Who is the bottleneck?' },
  { label: 'Check assumptions', text: 'What are we assuming that might be wrong?' },
  { label: 'Review predictions', text: 'What predictions have been confirmed or disproven?' },
  { label: 'Prepare customer', text: 'What does the organization know about this customer?' },
  { label: 'Imagine', text: 'What would happen if Legal disappeared?' },
  { label: 'Recall', text: 'When have we been here before?' },
];

let _askIntentionMode = true; // true = show prompts, false = show answer

function loadAskV2() {
  const el = document.getElementById('ask-v2-content');
  if (!el) return;
  renderAskIntention(el);
}

function renderAskIntention(el) {
  _askIntentionMode = true;
  el.innerHTML = `
    <div class="meta-surface">
      <div class="meta-surface greeting">What are you trying to accomplish?</div>
      <div class="meta-surface sub-greeting">Maestro will translate your intention into organizational knowledge.</div>

      <div class="intention-label">Common intentions</div>
      ${_intentionPrompts.map((p, i) => `
        <button class="intention-prompt" data-idx="${i}">
          <span style="color:var(--accent);font-weight:500;">${escapeHtml(p.label)}</span>
          <span style="color:var(--text-muted);margin-left:8px;">— ${escapeHtml(p.text)}</span>
        </button>
      `).join('')}

      <div style="margin-top:32px;">
        <input type="text" class="ask-input" id="ask-v2-input"
               placeholder="Or type your own intention…"
               onkeydown="if(event.key==='Enter') submitAskV2(this.value)"
               aria-label="Ask the organization">
      </div>

      <div id="ask-v2-answer" style="margin-top:32px;"></div>
    </div>
  `;

  // Wire up intention prompts
  el.querySelectorAll('.intention-prompt').forEach((btn, i) => {
    btn.addEventListener('click', () => {
      submitAskV2(_intentionPrompts[i].text);
    });
  });
}

async function submitAskV2(question) {
  if (!question || !question.trim()) return;
  const answerEl = document.getElementById('ask-v2-answer');
  if (!answerEl) return;

  _askIntentionMode = false;
  const qLower = question.toLowerCase();

  // V5 Spec #5 — route "what if" questions to Imagination engine
  if (qLower.includes('what if') || qLower.includes('what would happen') || qLower.includes('imagine')) {
    answerEl.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Imagining consequences…</div>';
    answerEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    try {
      const data = await api.getOEM(`/imagine?scenario=${encodeURIComponent(question)}`);
      renderImaginationAnswer(answerEl, question, data);
    } catch (e) {
      answerEl.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
    }
    return;
  }

  // V5 Spec #8 — route "when have we" questions to Recall engine
  if (qLower.includes('when have we') || qLower.includes('been here before') || qLower.includes('recall') || qLower.includes('last time')) {
    answerEl.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Searching organizational memory…</div>';
    answerEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    try {
      const data = await api.getOEM(`/recall?situation=${encodeURIComponent(question)}`);
      renderRecallAnswer(answerEl, question, data);
    } catch (e) {
      answerEl.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
    }
    return;
  }

  answerEl.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Consulting your organization\u2019s memory…</div>';

  // Scroll to answer
  answerEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

  try {
    const data = await api.getOEM(`/ask?q=${encodeURIComponent(question)}`);
    renderAskV2Answer(answerEl, question, data);
  } catch (e) {
    answerEl.innerHTML = `<div class="ds-error">Maestro couldn't answer that right now. ${escapeHtml(e.message)}</div>`;
  }
}

function renderAskV2Answer(el, question, data) {
  // Translate the OEM response into a human narrative using the shared
  // humanize() utility — no internal vocabulary, no law codes, no confidence numbers.
  const answer = data.answer || data.summary || 'Maestro is still learning about this.';
  const evidence = data.evidence || [];
  const confidence = data.confidence;

  const humanAnswer = humanize(answer);

  let html = `
    <div class="story-card">
      <div class="story-narrative">${escapeHtml(humanAnswer)}</div>
  `;

  // Provenance — "How do we know?" without exposing internal vocabulary
  if (evidence.length > 0) {
    html += `<div class="story-evidence">Based on ${evidence.length} ${evidence.length === 1 ? 'signal' : 'signals'} from your organization.</div>`;
  }

  // Confidence as a story, not a percentage
  if (confidence != null) {
    if (confidence > 0.8) {
      html += `<div class="story-evidence">We've seen this pattern consistently.</div>`;
    } else if (confidence > 0.5) {
      html += `<div class="story-evidence">This pattern appears frequently, but not always.</div>`;
    } else {
      html += `<div class="story-evidence">This is a emerging pattern — still forming.</div>`;
    }
  }

  html += `</div>`;

  // "Ask another question" prompt
  html += `<button class="intention-prompt" onclick="loadAskV2()" style="margin-top:16px;">Ask another question</button>`;

  el.innerHTML = html;
}

function renderImaginationAnswer(el, question, data) {
  let html = `<div class="story-card">
    <div class="story-narrative" style="font-weight:500;color:var(--accent);margin-bottom:12px;">${escapeHtml(humanize(data.scenario || question))}</div>
  `;
  if (data.consequences && data.consequences.length) {
    for (const c of data.consequences) {
      html += `<div style="padding:10px 0;border-bottom:1px solid var(--divider);">
        <div style="font-size:14px;color:var(--text-primary);">${escapeHtml(humanize(c.effect || ''))}</div>
        <div class="ds-meta" style="margin-top:4px;">Because: ${escapeHtml(humanize(c.cause || ''))}</div>
        <div class="ds-meta">Confidence: ${escapeHtml(humanize(c.confidence || ''))}</div>
      </div>`;
    }
  }
  if (data.historical_analogue) {
    html += `<div style="margin-top:12px;padding:12px;background:var(--surface-2);border-radius:8px;font-size:13px;color:var(--text-secondary);"><strong>Last time something similar happened:</strong> ${escapeHtml(humanize(data.historical_analogue))}</div>`;
  }
  if (data.recommendation) {
    html += `<div style="margin-top:8px;font-size:14px;color:var(--accent);font-weight:500;">${escapeHtml(humanize(data.recommendation))}</div>`;
  }
  html += `</div>`;
  html += `<button class="intention-prompt" onclick="loadAskV2()" style="margin-top:16px;">Ask another question</button>`;
  el.innerHTML = html;
}

function renderRecallAnswer(el, question, data) {
  if (data.novel || !data.moments || data.moments.length === 0) {
    el.innerHTML = `<div class="story-card">
      <div class="story-narrative">${escapeHtml(humanize(data.summary || 'No similar past moments found.'))}</div>
      <div class="story-evidence" style="margin-top:8px;">This may be a novel situation for the organization.</div>
    </div>
    <button class="intention-prompt" onclick="loadAskV2()" style="margin-top:16px;">Ask another question</button>`;
    return;
  }
  let html = `<div class="story-card">
    <div class="story-narrative" style="font-weight:500;color:var(--accent);margin-bottom:12px;">${escapeHtml(humanize(data.summary || ''))}</div>
  `;
  for (const m of data.moments) {
    html += `<div style="padding:12px 0;border-bottom:1px solid var(--divider);">
      <div class="ds-meta" style="margin-bottom:4px;">${escapeHtml(humanize(m.when || ''))}</div>
      <div style="font-size:14px;color:var(--text-primary);">${escapeHtml(humanize(m.situation || ''))}</div>
      <div style="font-size:13px;color:var(--text-secondary);margin-top:4px;">What we did: ${escapeHtml(humanize(m.what_we_did || ''))}</div>
      <div style="font-size:13px;color:var(--text-secondary);">What we learned: ${escapeHtml(humanize(m.what_we_learned || ''))}</div>
    </div>`;
  }
  html += `</div>`;
  html += `<button class="intention-prompt" onclick="loadAskV2()" style="margin-top:16px;">Ask another question</button>`;
  el.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════════════════════
