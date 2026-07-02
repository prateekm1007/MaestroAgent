// V8 Personal Mode — Frontend Surface.
// 4-item sidebar: Today / Memory / Decide / Reflect.
// Tier 2 features (relationship vault, ambient context, crossover) surface contextually.
// "What Maestro Knows" reachable in one click from every surface (Guideline P8).
// Incognito toggle with visible indicator (Guideline P6).

// ═══════════════════════════════════════════════════════════════════════════
// PERSONAL MODE — state + navigation
// ═══════════════════════════════════════════════════════════════════════════

const _personalSurfaces = [
  { id: 'personal-today', label: 'Today', icon: '☀️' },
  { id: 'personal-memory', label: 'Memory', icon: '🧠' },
  { id: 'personal-decide', label: 'Decide', icon: '⚖️' },
  { id: 'personal-reflect', label: 'Reflect', icon: '📝' },
];

let _personalCurrentSurface = 'personal-today';
let _incognitoActive = false;

// ═══════════════════════════════════════════════════════════════════════════
// LOAD PERSONAL MODE
// ═══════════════════════════════════════════════════════════════════════════

function loadPersonalMode() {
  // Check incognito status
  api.getPersonal('/incognito/status').then(data => {
    _incognitoActive = data.incognito;
  }).catch(() => {});

  // Round 51 H16 fix: render into a dedicated personal-content container,
  // NOT #main-content. The old code fell back to main-content when
  // personal-content didn't exist, which destroyed the navigation DOM
  // and broke hashchange navigation after visiting Personal Mode.
  // Now we create the container if it doesn't exist, and always render
  // into it — never overwriting main-content.
  let el = document.getElementById('personal-content');
  if (!el) {
    el = document.createElement('div');
    el.id = 'personal-content';
    const mainContent = document.getElementById('main-content');
    if (mainContent) {
      mainContent.appendChild(el);
    } else {
      // If main-content doesn't exist, fall back to body (shouldn't happen)
      document.body.appendChild(el);
    }
  }
  if (!el) return;

  el.innerHTML = `
    <div class="b-flex-minh100vh">
      <!-- Personal sidebar (4 items) -->
      <div class="b-w200-u">
        <div class="b-p02020-fs11">Personal</div>
        ${_personalSurfaces.map(s => `
          <button class="personal-nav-btn" data-surface="${s.id}"
                  class="b-flex-u-4"
                  onclick="navPersonalSurface('${s.id}')">
            <span>${s.icon}</span>
            <span>${escapeHtml(s.label)}</span>
          </button>
        `).join('')}
        <div class="b-mt20-p020">
          <button class="ds-btn ds-btn-ghost ds-btn-small" class="w-full" onclick="showWhatMaestroKnows()">
            What Maestro Knows
          </button>
        </div>
      </div>
      <!-- Main content -->
      <div class="b-flex-p24" id="personal-main">
        <div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>
      </div>
    </div>
  `;

  // Update nav button styles
  updatePersonalNavStyles();
  // Load the current surface
  loadPersonalSurface(_personalCurrentSurface);
}

function navPersonalSurface(surfaceId) {
  _personalCurrentSurface = surfaceId;
  updatePersonalNavStyles();
  loadPersonalSurface(surfaceId);
}

function updatePersonalNavStyles() {
  document.querySelectorAll('.personal-nav-btn').forEach(btn => {
    const isActive = btn.dataset.surface === _personalCurrentSurface;
    btn.style.color = isActive ? 'var(--accent)' : 'var(--text-secondary)';
    btn.style.fontWeight = isActive ? '600' : '400';
    btn.style.background = isActive ? 'var(--surface-2)' : 'transparent';
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// SURFACE LOADERS
// ═══════════════════════════════════════════════════════════════════════════

async function loadPersonalSurface(surfaceId) {
  const el = document.getElementById('personal-main');
  if (!el) return;

  if (surfaceId === 'personal-today') {
    await loadPersonalToday(el);
  } else if (surfaceId === 'personal-memory') {
    await loadPersonalMemory(el);
  } else if (surfaceId === 'personal-decide') {
    await loadPersonalDecide(el);
  } else if (surfaceId === 'personal-reflect') {
    await loadPersonalReflect(el);
  }
}

// ─── Today: briefing + habits + contradictions (Round 47 Block 2.1: swipe cards) ──

async function loadPersonalToday(el) {
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line" class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line" class="skeleton skeleton-line skeleton-line-w70"></div><div class="skeleton skeleton-line" class="skeleton skeleton-line skeleton-line-w50"></div></div>';
  try {
    const [briefing, habits, contradictions] = await Promise.all([
      api.getPersonal('/briefing').catch(() => null),
      api.getPersonal('/habits/streaks').catch(() => null),
      api.getPersonal('/contradictions').catch(() => null),
    ]);

    let html = '<div class="work-section">';

    // Round 47 Block 2.1 — Personal briefing as swipe cards.
    // Same Bumble pattern as the enterprise briefing. Max 7 cards.
    // Card types: HABIT (green), CONTRADICTION (red, NOTICED not FAILED),
    // MEMORY (yellow), REMINDER (amber). Summary card at the end.
    const personalDeckCards = [];

    // Habits → HABIT cards
    if (habits && habits.streaks) {
      habits.streaks.slice(0, 3).forEach(h => {
        personalDeckCards.push({
          category: 'HABIT',
          categoryClass: 'habit',
          title: h.name || 'Your habit',
          evidence: `Streak: ${h.current_streak || 0} day${(h.current_streak || 0) === 1 ? '' : 's'}`,
          rightLabel: 'CHECK IN',
          leftLabel: 'SKIP',
          _type: 'habit',
          _habitId: h.habit_id,
        });
      });
    }

    // Contradictions → NOTICED cards (Round 47 Block 2.3)
    if (contradictions && contradictions.contradictions) {
      contradictions.contradictions.slice(0, 3).forEach(c => {
        personalDeckCards.push({
          category: 'NOTICED',
          categoryClass: 'noticed',
          title: c.description || 'A pattern was noticed',
          evidence: c.evidence || '',
          rightLabel: 'REFLECT',
          leftLabel: 'DISMISS 30D',
          _type: 'contradiction',
          _dismissKey: c.dismiss_key,
        });
      });
    }

    // Briefing items → REMINDER cards
    if (briefing && briefing.items) {
      briefing.items.slice(0, 3).forEach(item => {
        personalDeckCards.push({
          category: 'REMINDER',
          categoryClass: 'due',
          title: (item.content || '').slice(0, 100),
          evidence: `From ${item.source || 'your calendar'}`,
          rightLabel: 'ACKNOWLEDGE',
          leftLabel: 'DEFER',
          _type: 'reminder',
        });
      });
    }

    // Work context card (if integration toggle is on)
    if (briefing && briefing.work_context && briefing.work_context.enabled) {
      const wc = briefing.work_context;
      const wcParts = [];
      if (wc.deadlines_today && wc.deadlines_today.length > 0) {
        wcParts.push(`${wc.deadlines_today.length} work deadline${wc.deadlines_today.length !== 1 ? 's' : ''}`);
      }
      if (wc.meetings_into_personal_time && wc.meetings_into_personal_time.length > 0) {
        wcParts.push(`${wc.meetings_into_personal_time.length} meeting${wc.meetings_into_personal_time.length !== 1 ? 's' : ''} into personal time`);
      }
      if (wcParts.length > 0) {
        personalDeckCards.push({
          category: 'WORK CONTEXT',
          categoryClass: 'decision',
          title: wcParts.join(' · '),
          evidence: wc.commitments_summary || '',
          rightLabel: 'ACKNOWLEDGE',
          leftLabel: 'DEFER',
          _type: 'work_context',
        });
      }
    }

    // Render the swipe deck (max 7 cards)
    const deck = personalDeckCards.slice(0, 7);

    if (deck.length > 0) {
      html += `
        <div class="b-fs14-fw800-6">Your morning</div>
        <div id="personal-swipe-deck-container" class="b-pos-relative">
        </div>
        <div id="personal-swipe-deck-progress" class="b-text-center-5">
          ${deck.length} ${deck.length === 1 ? 'card' : 'cards'}
        </div>
        <div id="personal-swipe-deck-summary" class="b-hidden-text">
          <div class="b-fs18-fw800-2">That's your morning.</div>
        </div>
      `;
    } else {
      html += `
        <div class="calm-empty" class="b-text-center-9">
          <div class="calm-empty-icon">☀️</div>
          <div class="calm-empty-title">Good morning.</div>
          <div class="calm-empty-body">Connect a source and I'll brief you tomorrow. I work either way.</div>
        </div>
      `;
    }

    html += '</div>';
    el.innerHTML = html;

    // Initialize the personal swipe deck
    if (deck.length > 0) {
      _initPersonalSwipeDeck(deck);
    }
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

function _initPersonalSwipeDeck(deck) {
  window._personalDeck = deck;
  window._personalDeckIdx = 0;
  window._personalDeckActed = 0;
  window._personalDeckDeferred = 0;
  _renderPersonalSwipeCard();
}

function _renderPersonalSwipeCard() {
  const container = document.getElementById('personal-swipe-deck-container');
  if (!container || !window._personalDeck) return;

  const idx = window._personalDeckIdx || 0;
  const deck = window._personalDeck;

  if (idx >= deck.length) {
    _showPersonalDeckSummary();
    return;
  }

  const cardData = deck[idx];
  container.innerHTML = '';

  if (typeof createSwipeCard !== 'function') return;

  const card = createSwipeCard({
    category: cardData.category,
    category_class: cardData.categoryClass,
    judgment: cardData.title,
    evidence: cardData.evidence,
    right_label: cardData.rightLabel,
    left_label: cardData.leftLabel,
    why_link: false,
  });

  card.style.position = 'relative';
  container.appendChild(card);

  if (typeof SwipeCard !== 'undefined') {
    const handler = new SwipeCard(card,
      // Swipe right
      () => {
        window._personalDeckActed++;
        _handlePersonalCardAction(cardData, true);
        _advancePersonalDeck();
      },
      // Swipe left
      () => {
        window._personalDeckDeferred++;
        _handlePersonalCardAction(cardData, false);
        _advancePersonalDeck();
      }
    );
  }

  _updatePersonalDeckProgress();
}

function _handlePersonalCardAction(cardData, swipedRight) {
  // Handle the action based on card type
  if (cardData._type === 'habit' && swipedRight && cardData._habitId) {
    // Check in the habit
    api.postPersonal('/habits/checkin', { habit_id: cardData._habitId }).catch(() => {});
  } else if (cardData._type === 'contradiction') {
    if (swipedRight) {
      // Reflect — could open a journaling prompt (future)
    } else if (cardData._dismissKey) {
      // Dismiss for 30 days
      api.postPersonal('/contradictions/dismiss', { dismiss_key: cardData._dismissKey }).catch(() => {});
    }
  }
}

function _advancePersonalDeck() {
  window._personalDeckIdx = (window._personalDeckIdx || 0) + 1;
  setTimeout(() => _renderPersonalSwipeCard(), 350);
}

function _updatePersonalDeckProgress() {
  const progress = document.getElementById('personal-swipe-deck-progress');
  if (!progress) return;
  const deck = window._personalDeck || [];
  const idx = window._personalDeckIdx || 0;
  const remaining = deck.length - idx;
  progress.textContent = `${remaining} ${remaining === 1 ? 'card' : 'cards'} left`;
}

function _showPersonalDeckSummary() {
  const container = document.getElementById('personal-swipe-deck-container');
  const progress = document.getElementById('personal-swipe-deck-progress');
  const summary = document.getElementById('personal-swipe-deck-summary');
  if (container) container.style.display = 'none';
  if (progress) progress.style.display = 'none';
  if (summary) summary.style.display = 'block';
}

// ─── Memory: knowledge graph + memory replay + evolution report ──────────

async function loadPersonalMemory(el) {
  let html = '<div class="work-section">';

  html += `
    <div class="b-p20-bg-2">
      <div class="section-title">Memory Replay</div>
      <input type="text" class="ask-input" id="memory-replay-input"
             placeholder="What did I talk about with Sarah?"
             onkeydown="if(event.key==='Enter') doMemoryReplay(this.value)"
             class="b-w-full-8" />
      <div id="memory-replay-result" class="mt-12"></div>
    </div>
  `;

  html += `
    <div class="b-p20-bg-2">
      <div class="section-title">Personal Why?</div>
      <input type="text" class="ask-input" id="personal-why-input"
             placeholder="Why did I skip the gym 3 times this month?"
             onkeydown="if(event.key==='Enter') doPersonalWhy(this.value)"
             class="b-w-full-8" />
      <div id="personal-why-result" class="mt-12"></div>
    </div>
  `;

  html += `
    <div class="b-p20-bg">
      <div class="section-title">Evolution Report</div>
      <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="loadEvolutionReport()">Generate quarterly report</button>
      <div id="evolution-report-result" class="mt-12"></div>
    </div>
  `;

  html += '</div>';
  el.innerHTML = html;
}

// ─── Decide: decision support + prepared decisions + intent cascade + predictions ──

async function loadPersonalDecide(el) {
  let html = '<div class="work-section">';

  html += `
    <div class="b-p20-bg-2">
      <div class="section-title">Decision Support</div>
      <input type="text" class="ask-input" id="decide-input"
             placeholder="Should I take this trip?"
             onkeydown="if(event.key==='Enter') doDecide(this.value)"
             class="b-w-full-8" />
      <div id="decide-result" class="mt-12"></div>
    </div>
  `;

  html += `
    <div class="b-p20-bg-2">
      <div class="section-title">Intent Cascade</div>
      <input type="text" class="ask-input" id="intent-input"
             placeholder="improve fitness"
             onkeydown="if(event.key==='Enter') doIntentCascade(this.value)"
             class="b-w-full-8" />
      <div id="intent-result" class="mt-12"></div>
    </div>
  `;

  html += `
    <div class="b-p20-bg">
      <div class="section-title">Prediction Market</div>
      <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="loadCalibration()">View calibration</button>
      <div id="calibration-result" class="mt-12"></div>
    </div>
  `;

  html += '</div>';
  el.innerHTML = html;
}

// ─── Reflect: self-reflection prompts + legacy builder ───────────────────

async function loadPersonalReflect(el) {
  let html = '<div class="work-section">';

  html += `
    <div class="b-p20-bg-2">
      <div class="section-title">Reflection Prompts</div>
      <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="loadReflectionPrompts()">Get prompts</button>
      <div id="reflection-prompts-result" class="mt-12"></div>
    </div>
  `;

  html += `
    <div class="b-p20-bg">
      <div class="section-title">Legacy Builder</div>
      <div class="b-fs13-text-19">Document your life stories, values, and wisdom. Always private.</div>
      <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="loadLegacyPrompts()">Get writing prompts</button>
      <div id="legacy-prompts-result" class="mt-12"></div>
    </div>
  `;

  html += '</div>';
  el.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════════════════════
// ACTION HANDLERS
// ═══════════════════════════════════════════════════════════════════════════

async function checkInHabit(habitId) {
  try {
    await api.postPersonal('/habits/checkin', { habit_id: habitId });
    loadPersonalSurface('personal-today'); // reload
  } catch (e) {
    showToast('Check-in failed: ' + e.message, 'error');
  }
}

async function dismissContradiction(key) {
  try {
    await api.postPersonal('/contradictions/dismiss', { dismiss_key: key });
    loadPersonalSurface('personal-today'); // reload
  } catch (e) {
    showToast('Dismiss failed: ' + e.message, 'error');
  }
}

async function toggleIncognito() {
  try {
    if (_incognitoActive) {
      await api.postPersonal('/incognito/end');
      _incognitoActive = false;
    } else {
      await api.postPersonal('/incognito/start');
      _incognitoActive = true;
    }
    loadPersonalSurface('personal-today'); // reload
  } catch (e) {
    showToast('Incognito toggle failed: ' + e.message, 'error');
  }
}

async function doMemoryReplay(query) {
  const el = document.getElementById('memory-replay-result');
  if (!el || !query) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line" class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line" class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const data = await api.postPersonal('/memory/replay', { query });
    let html = '<div class="b-p12-bg">';
    html += `<div class="b-fs13-text-15">${escapeHtml(humanize(data.summary || ''))}</div>`;
    if (data.third_party_warning) {
      html += `<div class="b-mt8-fs12">${escapeHtml(humanize(data.third_party_warning))}</div>`;
    }
    html += '</div>';

    // Round 47 Block 2.2 — Follow-up question chips for memory conversation.
    // After a memory replay answer, show 2-3 follow-up question chips
    // (Bumble pill style). Tapping a chip asks the next question.
    // Chips are derived from the memory graph, not generated by an LLM.
    const followUps = _generateMemoryFollowUps(query, data);
    if (followUps.length > 0) {
      html += '<div class="mt-12">';
      html += '<div class="b-fs11-fw700">Follow up</div>';
      followUps.forEach(fq => {
        html += `<button class="follow-up-chip" onclick="doMemoryReplay('${escapeJs(fq).replace(/'/g,"\\'")}')">${escapeHtml(fq)}</button>`;
      });
      html += '</div>';
    }

    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

function _generateMemoryFollowUps(originalQuery, data) {
  // Round 47 Block 2.2 — derive follow-up questions from the memory graph.
  // Not LLM-generated — these are structural follow-ups based on the query
  // and the entities/time windows in the replay result.
  const followUps = [];
  const q = (originalQuery || '').toLowerCase();

  // If the query mentions a person, offer "Show more about {person}"
  const personMatch = originalQuery && originalQuery.match(/(?:about|with|from)\s+([A-Z][a-z]+)/);
  if (personMatch) {
    followUps.push(`Show more about ${personMatch[1]}`);
  }

  // Always offer a time-based follow-up
  followUps.push('What else happened that week?');

  // If the replay returned moments, offer a decision-based follow-up
  if (data && data.moments && data.moments.length > 0) {
    followUps.push('What did I decide then?');
  }

  // If the replay found memories, offer a "related" follow-up
  if (data && data.summary && !data.novel) {
    followUps.push('What else is related?');
  }

  return followUps.slice(0, 3);  // max 3 chips
}

async function doPersonalWhy(question) {
  const el = document.getElementById('personal-why-result');
  if (!el || !question) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line" class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line" class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const data = await api.postPersonal('/why', { question });
    let html = '<div class="b-p12-bg">';
    if (data.third_party_redirected) {
      html += `<div class="b-fs13-text-25">${escapeHtml(humanize(data.explanation_chain[0].narrative || ''))}</div>`;
    } else {
      data.explanation_chain.forEach(step => {
        html += `<div class="b-p60-u">
          <div class="b-fs13-fw500">${escapeHtml(humanize(step.label || ''))}</div>
          <div class="b-fs12-text-16">${escapeHtml(humanize(step.narrative || ''))}</div>
        </div>`;
      });
    }
    html += '</div>';
    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function doDecide(question) {
  const el = document.getElementById('decide-result');
  if (!el || !question) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line" class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line" class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const data = await api.postPersonal('/decide', { question });
    let html = '<div class="b-p12-bg">';
    html += `<div class="b-fs12-text-5">${escapeHtml(data.label || '')}</div>`;
    html += `<div class="b-fs13-text-12">${escapeHtml(humanize(data.recommendation || ''))}</div>`;
    html += `<div class="b-flex-gap16"><div><strong>Pros:</strong> ${data.pros.map(p => escapeHtml(p)).join('; ')}</div></div>`;
    html += `<div class="b-fs12-mt4"><strong>Cons:</strong> ${data.cons.map(c => escapeHtml(c)).join('; ')}</div>`;
    html += `<div class="b-fs12-text">Confidence: ${(data.confidence * 100).toFixed(0)}%</div>`;
    html += '</div>';
    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function doIntentCascade(intent) {
  const el = document.getElementById('intent-result');
  if (!el || !intent) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line" class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line" class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const data = await api.postPersonal('/intent-cascade', { intent });
    let html = '<div class="b-p12-bg">';
    const sections = [
      ['Assumptions', data.assumptions],
      ['Hypotheses', data.hypotheses],
      ['Preparations', data.preparations],
      ['Evidence Plan', data.evidence_plan],
    ];
    sections.forEach(([label, items]) => {
      html += `<div class="mb-10"><div class="b-fs12-fw600">${label}</div>`;
      items.forEach(item => {
        html += `<div class="b-fs12-text-18">• ${escapeHtml(humanize(item.text || ''))}</div>`;
      });
      html += '</div>';
    });
    html += '</div>';
    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadCalibration() {
  const el = document.getElementById('calibration-result');
  if (!el) return;
  try {
    const data = await api.getPersonal('/predictions/calibration');
    el.innerHTML = `<div class="b-p12-bg-2">${escapeHtml(data.message || 'No data yet.')}</div>`;
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadReflectionPrompts() {
  const el = document.getElementById('reflection-prompts-result');
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const data = await api.getPersonal('/reflection-prompts');
    let html = '<div class="b-p12-bg">';
    data.prompts.forEach(p => {
      html += `<div class="b-p80-u">
        <div class="b-fs13-text-8">${escapeHtml(humanize(p.prompt || ''))}</div>
        <div class="ds-meta" class="mt-2">${escapeHtml(p.type || '')}</div>
      </div>`;
    });
    html += '</div>';
    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadLegacyPrompts() {
  const el = document.getElementById('legacy-prompts-result');
  if (!el) return;
  try {
    const data = await api.getPersonal('/legacy/prompts');
    let html = '<div class="b-p12-bg">';
    html += '<div class="b-fs13-text-21">Writing prompts for your legacy:</div>';
    data.prompts.forEach(p => {
      html += `<div class="b-fs13-text-14">• ${escapeHtml(p)}</div>`;
    });
    html += '</div>';
    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadEvolutionReport() {
  const el = document.getElementById('evolution-report-result');
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const data = await api.getPersonal('/evolution-report');
    el.innerHTML = `<div class="b-p12-bg-3">${escapeHtml(humanize(data.narrative || ''))}</div>`;
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// "WHAT MAESTRO KNOWS" DASHBOARD (Guideline P8 — one-click from anywhere)
// ═══════════════════════════════════════════════════════════════════════════

async function showWhatMaestroKnows() {
  const el = document.getElementById('personal-main');
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const data = await api.getPersonal('/dashboard');
    let html = '<div class="work-section">';
    html += `<div class="b-p20-bg">`;
    html += `<div class="b-fs16-fw600-2">What Maestro Knows About You</div>`;
    html += `<div class="b-fs13-text-20">${escapeHtml(data.message || '')}</div>`;
    html += `<div class="ds-meta" class="mb-16">${data.total_sources} source(s) · ${data.total_items} item(s)</div>`;

    if (data.sources && data.sources.length > 0) {
      data.sources.forEach(src => {
        html += `<div class="b-p120-u">
          <div class="b-flex-u-7">
            <div>
              <div class="b-fs13-fw500">${escapeHtml(src.source)}</div>
              <div class="ds-meta">${src.item_count} item(s) · Consent: ${src.consent_active ? 'active' : 'revoked'}</div>
            </div>
            <button class="ds-btn ds-btn-ghost ds-btn-small" class="b-fs11-text-5"
                    onclick="revokePersonalSource('${escapeHtml(src.source)}')">Revoke</button>
          </div>
        </div>`;
      });
    } else {
      html += '<div class="empty-state"><div class="empty-state-icon"><svg width="48" height="48" viewBox="0 0 48 48" fill="none"><path d="M24 8 C16 8 12 14 12 20 C12 26 16 30 16 30 L16 36 L32 36 L32 30 C32 30 36 26 36 20 C36 14 32 8 24 8 Z" stroke="#FFC629" stroke-width="2" fill="#FFF4D1"/></svg></div><div class="empty-state-title">No data sources connected.</div><div class="empty-state-body">Connect your work tools in Settings to start receiving signals.</div></div>';
    }

    html += '</div></div>';
    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function revokePersonalSource(source) {
  if (!await showConfirm(`Revoke consent for '${source}' and delete ALL data from this source? This cannot be undone.`)) return;
  try {
    await api.postPersonal('/dashboard/revoke', { source });
    showWhatMaestroKnows(); // reload
  } catch (e) {
    showToast('Revoke failed: ' + e.message, 'error');
  }
}
