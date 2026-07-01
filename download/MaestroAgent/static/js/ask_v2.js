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

// ═══════════════════════════════════════════════════════════════════════════
