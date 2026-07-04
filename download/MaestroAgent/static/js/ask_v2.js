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

// Round 3 fix: Generate a session_id for multi-turn conversation.
// This enables pronoun resolution ("What did we promise?" after "Prepare me
// for Globex" resolves "we" → Globex). Persisted for the page session.
// P11: without this, the AskPipeline's conversation-state path is unreachable
// from the UI — the engine works in tests but the user never benefits.
let _askSessionId = null;
function getAskSessionId() {
  if (!_askSessionId) {
    try {
      _askSessionId = crypto.randomUUID();
    } catch (e) {
      // Fallback for browsers without crypto.randomUUID
      _askSessionId = 'sess-' + Date.now() + '-' + Math.random().toString(36).slice(2, 11);
    }
  }
  return _askSessionId;
}

function loadAskV2() {
  const el = document.getElementById('ask-v2-content');
  if (!el) return;
  // CEO Vision: Ask must be situational before the executive types
  loadAskContext(el);
}

async function loadAskContext(el) {
  // Fetch preparation + whispers to determine context
  let prep = null;
  let whispers = null;
  try {
    const [prepResp, whisperResp] = await Promise.all([
      fetch((MAESTRO_API || '') + '/api/oem/preparation/tomorrow').then(r => r.ok ? r.json() : null).catch(() => null),
      fetch((MAESTRO_API || '') + '/api/oem/whisper?context=meeting').then(r => r.ok ? r.json() : null).catch(() => null),
    ]);
    prep = prepResp;
    whispers = whisperResp;
  } catch (e) {
    // Non-fatal — fall back to default prompts
  }

  // Determine context
  let header = 'What do you need?';
  let subheader = '';
  let prompts = [
    'Prepare me',
    'Remind me',
    'Explain this',
    'Find who knows',
    "What am I missing?",
  ];

  // If there are upcoming meetings, show ALL meetings and prioritize the risky one
  if (prep && prep.meetings && prep.meetings.length > 0) {
    // Find the riskiest meeting (most concerns + objections + commitments)
    const meetingsWithRisk = prep.meetings.map(m => {
      const p = m.preparation || {};
      const riskScore = (p.customer_concerns || []).length + (p.previous_objections || []).length + (p.relevant_commitments || []).length;
      return { ...m, riskScore };
    });
    meetingsWithRisk.sort((a, b) => b.riskScore - a.riskScore);
    const riskyMeeting = meetingsWithRisk[0];

    if (prep.meetings.length === 1) {
      header = `You have ${riskyMeeting.title} coming up.`;
    } else {
      header = `You have ${prep.meetings.length} meetings coming up. ${riskyMeeting.title} is the risky one.`;
      const concerns = (riskyMeeting.preparation || {}).customer_concerns || [];
      if (concerns.length > 0) {
        header += ` (${concerns.length} unresolved concern${concerns.length === 1 ? '' : 's'})`;
      }
    }
    subheader = 'I can prepare you, explain what changed, or find previous decisions.';
    prompts = [
      `Prepare me for ${riskyMeeting.title}`,
      'What am I likely to be asked?',
      "What hasn't been resolved?",
      'What should I remember?',
    ];
  }

  // If there are high-priority whispers, show them
  let whisperNote = '';
  if (whispers && whispers.whispers) {
    const highPriority = whispers.whispers.filter(w => w.priority === 'high');
    if (highPriority.length > 0) {
      whisperNote = `${highPriority.length} ${highPriority.length === 1 ? 'thing' : 'things'} deserve your attention.`;
    }
  }

  el.innerHTML = `
    <div class="meta-surface">
      <div class="ask-contextual-header">${escapeHtml(header)}</div>
      ${subheader ? `<div class="ask-contextual-subheader">${escapeHtml(subheader)}</div>` : ''}
      ${whisperNote ? `<div class="ask-contextual-whisper-note">${escapeHtml(whisperNote)}</div>` : ''}

      <div class="ask-contextual-prompts">
        ${prompts.map(p => `
          <button class="ask-contextual-prompt" onclick="askSubmit('${escapeJs(p)}')">${escapeHtml(p)}</button>
        `).join('')}
      </div>

      <div class="pos-relative ask-input-container">
        <input type="text" class="ask-input" id="ask-v2-input"
               placeholder="Or ask anything about your organization..."
               onkeydown="if(event.key==='Enter') askSubmit(this.value)"
               aria-label="Ask Maestro" />
      </div>
    </div>
  `;
  if (typeof lucide !== 'undefined') lucide.createIcons();
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
          <span class="b-text-accent">${escapeHtml(p.label)}</span>
          <span class="b-text-muted-6">— ${escapeHtml(p.text)}</span>
        </button>
      `).join('')}

      <div class="b-mt32">
        <input type="text" class="maestro-input b-mt32" id="ask-v2-input"
               placeholder="Ask me anything…"
               onkeydown="if(event.key==='Enter') submitAskV2(this.value)"
               aria-label="Ask the organization"
               class="b-fs16-fw600" />
      </div>

      <div id="ask-v2-answer"></div>
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

  // V8 Upgrade #1 — route "why" questions to the Explanation engine.
  // A "why" question is one that starts with "why" or contains "why" as a
  // standalone word, OR starts with "explain why". These get a multi-step
  // causal chain rendered as a visual sequence.
  const trimmedLower = qLower.trim();
  const isWhyQuestion = (
    trimmedLower.startsWith('why') ||
    trimmedLower.startsWith('explain why') ||
    /\bwhy\b/.test(trimmedLower)
  );
  if (isWhyQuestion) {
    answerEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
    answerEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    try {
      const data = await api.getOEM(`/explain?q=${encodeURIComponent(question)}`);
      renderExplanationAnswer(answerEl, question, data);
    } catch (e) {
      answerEl.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
    }
    return;
  }

  // V5 Spec #5 — route "what if" questions to Imagination engine
  if (qLower.includes('what if') || qLower.includes('what would happen') || qLower.includes('imagine')) {
    answerEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
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
    answerEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
    answerEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    try {
      const data = await api.getOEM(`/recall?situation=${encodeURIComponent(question)}`);
      renderRecallAnswer(answerEl, question, data);
    } catch (e) {
      answerEl.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
    }
    return;
  }

  answerEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  // Scroll to answer
  answerEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

  try {
    // Round 3 fix: Use POST /ask/conversation (AskPipeline) instead of
    // GET /ask?q= (old TF-IDF DecisionEngine). This activates:
    //   - 9 intent types (WISDOM, WHAT_IF, SIMULATE, RECALL, PREPARE, etc.)
    //   - Conversation state (pronoun resolution via session_id)
    //   - Evidence-grounded narration with inline citations [1][2]
    // P11: the AskPipeline was built (commit 78aa7d7) but the UI never called
    // it. Same disease as CRITICAL-01, one layer up.
    const resp = await fetch((MAESTRO_API || '') + '/api/oem/ask/conversation', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: question,
        history: [],
        session_id: getAskSessionId(),  // enables pronoun resolution
      }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    renderAskV2Answer(answerEl, question, data);
  } catch (e) {
    answerEl.innerHTML = `<div class="ds-error">Maestro couldn't answer that right now. ${escapeHtml(e.message)}</div>`;
  }
}

function renderAskV2Answer(el, question, data) {
  // V8 P0-4 + Bumble — Synthesized answer as a bold card with swipe-to-rate.
  const synthesized = data.synthesized_answer || data.answer || 'Maestro is still learning about this.';
  const evidenceDetail = data.evidence_detail || '';
  const confidence = data.confidence;

  const humanAnswer = humanize(synthesized);

  let html = `
    <div class="maestro-card b-mw420-m0auto">
      <div class="swipe-card-category answer mb-12">Answer</div>
      <div class="b-fs18-fw800-3">
        ${escapeHtml(humanAnswer)}
      </div>
  `;

  // Collapsible evidence detail (Apple's progressive disclosure)
  if (evidenceDetail) {
    html += `<details class="b-mt8-mb12">
      <summary class="b-cursor-pointer">Show evidence</summary>
      <div class="b-mt8-p12">${escapeHtml(humanize(evidenceDetail))}</div>
    </details>`;
  }

  // Round 3 fix: Render citations from the AskPipeline.
  // The new response format includes `citations` (list of {number, source,
  // text, date}) and `evidence` (list of evidence items). These are the
  // inline [1][2] citations that link the answer to the Evidence Spine.
  if (data.citations && data.citations.length > 0) {
    html += `<details class="b-mt8-mb12">
      <summary class="b-cursor-pointer">Sources (${data.citations.length})</summary>
      <div class="b-mt8-p12">`;
    for (const cite of data.citations) {
      const citeText = cite.text || '';
      const citeSource = cite.source || 'unknown';
      const citeDate = cite.date || '';
      html += `<div class="b-mb8">
        <span class="b-fw600">[${cite.number}]</span>
        <span class="text-muted">${escapeHtml(citeSource)}</span>
        ${citeDate ? `<span class="text-muted"> · ${escapeHtml(citeDate)}</span>` : ''}
        <div class="b-fs13-text-muted">${escapeHtml(humanize(citeText))}</div>
      </div>`;
    }
    html += `</div></details>`;
  }

  // Also render the intent + entities (transparency — proves the pipeline ran)
  if (data.intent || (data.entities && data.entities.length > 0)) {
    html += `<div class="b-mt8 b-fs12 text-muted">`;
    if (data.intent) html += `Intent: ${escapeHtml(data.intent)}`;
    if (data.entities && data.entities.length > 0) {
      html += ` · Entities: ${escapeHtml(data.entities.join(', '))}`;
    }
    html += `</div>`;
  }

  // P0-4: Bold confidence labels — VERIFIED / CONFIDENT / EXPLORING
  if (confidence != null) {
    // Check if the law is human-verified (Rule D2)
    const isVerified = data.laws && data.laws.length > 0 && data.laws[0].verified_by;
    let confLabel = 'EXPLORING';
    let confColor = 'var(--maestro-gray-mid,#999999)';
    if (isVerified) {
      confLabel = 'VERIFIED';
      confColor = 'var(--maestro-success,#00C853)';
    } else if (confidence >= 0.8) {
      confLabel = 'CONFIDENT';
      confColor = 'var(--maestro-success,#00C853)';
    } else if (confidence >= 0.5) {
      confLabel = 'CONFIDENT';
      confColor = 'var(--maestro-warning,#FF9800)';
    }
    html += `<div class="b-inline-block-5">${confLabel}</div>`;
  }

  // Swipe-to-rate hint (feeds attention signals P1-5)
  html += `
    <div class="swipe-card-hint b-mtauto">
      <span class="text-muted">← Not useful</span>
      <span class="b-text-positive">Useful →</span>
    </div>
    <div class="b-flex-gap8-3">
      <button class="maestro-btn maestro-btn-secondary b-flex-fs13" onclick="rateAskAnswer(false)">Not useful</button>
      <button class="maestro-btn b-flex-fs13" onclick="rateAskAnswer(true)">Useful</button>
    </div>
  `;

  html += `</div>`;

  // "Ask another question" — Bumble pill style
  html += `<button class="maestro-btn maestro-btn-ghost maestro-btn-full b-mt16-mw420" onclick="loadAskV2()">Ask another question</button>`;

  el.innerHTML = html;
}

// V8 P1-5 — Rate the answer (feeds attention signals).
async function rateAskAnswer(useful) {
  try {
    await api.postOEM('/attention/record', { item_type: 'ask_answer', item_id: useful ? 'useful' : 'not_useful' });
  } catch (e) {
    // Non-fatal — rating is best-effort
  }
}

function renderImaginationAnswer(el, question, data) {
  let html = `<div class="story-card">
    <div class="story-narrative b-fw500-text">${escapeHtml(humanize(data.scenario || question))}</div>
  `;
  if (data.consequences && data.consequences.length) {
    for (const c of data.consequences) {
      html += `<div class="b-p100-u">
        <div class="b-fs14-text-4">${escapeHtml(humanize(c.effect || ''))}</div>
        <div class="ds-meta mt-4">Because: ${escapeHtml(humanize(c.cause || ''))}</div>
        <div class="ds-meta">Confidence: ${escapeHtml(humanize(c.confidence || ''))}</div>
      </div>`;
    }
  }
  if (data.historical_analogue) {
    html += `<div class="b-mt12-p12"><strong>Last time something similar happened:</strong> ${escapeHtml(humanize(data.historical_analogue))}</div>`;
  }
  if (data.recommendation) {
    html += `<div class="b-mt8-fs14">${escapeHtml(humanize(data.recommendation))}</div>`;
  }
  html += `</div>`;
  html += `<button class="intention-prompt mt-16" onclick="loadAskV2()">Ask another question</button>`;
  el.innerHTML = html;
}

function renderRecallAnswer(el, question, data) {
  if (data.novel || !data.moments || data.moments.length === 0) {
    el.innerHTML = `<div class="story-card">
      <div class="story-narrative">${escapeHtml(humanize(data.summary || 'No similar past moments found.'))}</div>
      <div class="story-evidence mt-8">This may be a novel situation for the organization.</div>
    </div>
    <button class="intention-prompt mt-16" onclick="loadAskV2()">Ask another question</button>`;
    return;
  }
  let html = `<div class="story-card">
    <div class="story-narrative b-fw500-text">${escapeHtml(humanize(data.summary || ''))}</div>
  `;
  for (const m of data.moments) {
    html += `<div class="b-p120-u">
      <div class="ds-meta mb-4">${escapeHtml(humanize(m.when || ''))}</div>
      <div class="b-fs14-text-4">${escapeHtml(humanize(m.situation || ''))}</div>
      <div class="b-fs13-text-22">What we did: ${escapeHtml(humanize(m.what_we_did || ''))}</div>
      <div class="subtle-text">What we learned: ${escapeHtml(humanize(m.what_we_learned || ''))}</div>
    </div>`;
  }
  html += `</div>`;
  html += `<button class="intention-prompt mt-16" onclick="loadAskV2()">Ask another question</button>`;
  el.innerHTML = html;
}

// V8 Upgrade #1 — render an Explanation as a visual causal chain.
// Each step is a card with: step number, label, narrative, evidence count,
// confidence bar, and source-entity references. Steps are connected by a
// vertical line so the chain is visible.
function renderExplanationAnswer(el, question, data) {
  // Empty / honest-limitation case
  if (!data.steps || data.steps.length === 0) {
    el.innerHTML = `<div class="story-card">
      <div class="story-narrative">${escapeHtml(humanize(data.honest_limitation || data.summary || 'Maestro cannot explain this yet.'))}</div>
      <div class="story-evidence mt-8">Connect more providers (GitHub, Jira, Slack, Confluence) so Maestro can observe the pattern and compose a causal chain.</div>
    </div>
    <button class="intention-prompt mt-16" onclick="loadAskV2()">Ask another question</button>`;
    return;
  }

  // Header — the question + overall confidence + total evidence
  const overallPct = Math.round((data.overall_confidence || 0) * 100);
  let html = `<div class="story-card">
    <div class="story-narrative b-fw500-text-2">${escapeHtml(humanize(question))}</div>
    <div class="ds-meta mb-16">
      ${data.step_count} step${data.step_count === 1 ? '' : 's'} · ${data.total_evidence} evidence signals · overall confidence ${overallPct}%
    </div>
    <div class="explanation-chain">`;

  // Steps — each is a card connected by a vertical line
  for (let i = 0; i < data.steps.length; i++) {
    const step = data.steps[i];
    const isLast = i === data.steps.length - 1;
    const confPct = Math.round((step.confidence || 0) * 100);
    // Confidence color: high (>=70%) = accent, medium (40-69%) = secondary, low (<40%) = muted
    const confColor = confPct >= 70 ? 'var(--accent)' : confPct >= 40 ? 'var(--secondary)' : 'var(--text-muted)';
    html += `
      <div class="explanation-step${isLast ? ' explanation-step-last' : ''}">
        <div class="explanation-step-marker">${step.step}</div>
        <div class="explanation-step-body">
          <div class="explanation-step-label">${escapeHtml(humanize(step.label || ''))}</div>
          <div class="explanation-step-narrative">${escapeHtml(humanize(step.narrative || ''))}</div>
          <div class="explanation-step-meta">
            <span class="ds-meta">${step.evidence_count} evidence</span>
            <span class="ds-meta b-ml12">confidence ${confPct}%</span>
          </div>
          <div class="explanation-conf-bar b-bg-08c2">
            <div class="b-bg-41cc"></div>
          </div>
          ${step.sources && step.sources.length > 0 ? `
            <details class="explanation-sources">
              <summary class="ds-meta b-cursor-pointer-2">${step.sources.length} source${step.sources.length === 1 ? '' : 's'}</summary>
              <div class="mt-6">
                ${step.sources.map(s => `<div class="ds-meta p-20">${escapeHtml(s)}</div>`).join('')}
              </div>
            </details>
          ` : ''}
        </div>
      </div>
    `;
  }

  html += `</div>`;

  // Honest limitation (if any) — shown as a footnote
  if (data.honest_limitation) {
    html += `<div class="story-evidence b-mt16-u">${escapeHtml(humanize(data.honest_limitation))}</div>`;
  }

  html += `</div>`;
  html += `<button class="intention-prompt mt-16" onclick="loadAskV2()">Ask another question</button>`;
  el.innerHTML = html;
}
