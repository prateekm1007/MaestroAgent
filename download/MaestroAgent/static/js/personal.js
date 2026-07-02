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
    <div style="display:flex;min-height:100vh;">
      <!-- Personal sidebar (4 items) -->
      <div style="width:200px;border-right:1px solid var(--divider);padding:20px 0;flex-shrink:0;">
        <div style="padding:0 20px 20px;font-size:11px;text-transform:uppercase;color:var(--text-muted);font-weight:600;">Personal</div>
        ${_personalSurfaces.map(s => `
          <button class="personal-nav-btn" data-surface="${s.id}"
                  style="display:flex;align-items:center;gap:10px;width:100%;padding:10px 20px;border:none;background:none;cursor:pointer;color:${_personalCurrentSurface === s.id ? 'var(--accent)' : 'var(--text-secondary)'};font-size:14px;text-align:left;font-family:inherit;"
                  onclick="navPersonalSurface('${s.id}')">
            <span>${s.icon}</span>
            <span>${escapeHtml(s.label)}</span>
          </button>
        `).join('')}
        <div style="margin-top:20px;padding:0 20px;border-top:1px solid var(--divider);padding-top:20px;">
          <button class="ds-btn ds-btn-ghost ds-btn-small" style="width:100%;" onclick="showWhatMaestroKnows()">
            What Maestro Knows
          </button>
        </div>
      </div>
      <!-- Main content -->
      <div style="flex:1;padding:24px;overflow-y:auto;" id="personal-main">
        <div class="ds-loading"><span class="spinner"></span> Loading...</div>
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
  el.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Loading your morning briefing…</div>';
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
        <div style="font-size:14px;font-weight:800;color:var(--maestro-black,var(--text-primary));margin-bottom:16px;font-family:'Montserrat',sans-serif;">Your morning</div>
        <div id="personal-swipe-deck-container" style="position:relative;min-height:400px;max-width:420px;margin:0 auto;">
        </div>
        <div id="personal-swipe-deck-progress" style="text-align:center;margin-top:16px;font-size:13px;font-weight:700;color:var(--maestro-gray-mid,var(--text-muted));font-family:'Montserrat',sans-serif;">
          ${deck.length} ${deck.length === 1 ? 'card' : 'cards'}
        </div>
        <div id="personal-swipe-deck-summary" style="display:none;text-align:center;padding:24px;">
          <div style="font-size:18px;font-weight:800;color:var(--maestro-black,var(--text-primary));font-family:'Montserrat',sans-serif;">That's your morning.</div>
        </div>
      `;
    } else {
      html += `
        <div class="calm-empty" style="text-align:center;padding:48px 20px;">
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
    <div style="padding:20px;background:var(--surface);border:1px solid var(--divider);border-radius:12px;margin-bottom:20px;">
      <div style="font-size:14px;font-weight:600;color:var(--text-primary);margin-bottom:12px;">Memory Replay</div>
      <input type="text" class="ask-input" id="memory-replay-input"
             placeholder="What did I talk about with Sarah?"
             onkeydown="if(event.key==='Enter') doMemoryReplay(this.value)"
             style="width:100%;padding:8px 12px;background:var(--surface-2);border:1px solid var(--divider);border-radius:6px;color:var(--text-primary);font-size:13px;outline:none;" />
      <div id="memory-replay-result" style="margin-top:12px;"></div>
    </div>
  `;

  html += `
    <div style="padding:20px;background:var(--surface);border:1px solid var(--divider);border-radius:12px;margin-bottom:20px;">
      <div style="font-size:14px;font-weight:600;color:var(--text-primary);margin-bottom:12px;">Personal Why?</div>
      <input type="text" class="ask-input" id="personal-why-input"
             placeholder="Why did I skip the gym 3 times this month?"
             onkeydown="if(event.key==='Enter') doPersonalWhy(this.value)"
             style="width:100%;padding:8px 12px;background:var(--surface-2);border:1px solid var(--divider);border-radius:6px;color:var(--text-primary);font-size:13px;outline:none;" />
      <div id="personal-why-result" style="margin-top:12px;"></div>
    </div>
  `;

  html += `
    <div style="padding:20px;background:var(--surface);border:1px solid var(--divider);border-radius:12px;">
      <div style="font-size:14px;font-weight:600;color:var(--text-primary);margin-bottom:12px;">Evolution Report</div>
      <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="loadEvolutionReport()">Generate quarterly report</button>
      <div id="evolution-report-result" style="margin-top:12px;"></div>
    </div>
  `;

  html += '</div>';
  el.innerHTML = html;
}

// ─── Decide: decision support + prepared decisions + intent cascade + predictions ──

async function loadPersonalDecide(el) {
  let html = '<div class="work-section">';

  html += `
    <div style="padding:20px;background:var(--surface);border:1px solid var(--divider);border-radius:12px;margin-bottom:20px;">
      <div style="font-size:14px;font-weight:600;color:var(--text-primary);margin-bottom:12px;">Decision Support</div>
      <input type="text" class="ask-input" id="decide-input"
             placeholder="Should I take this trip?"
             onkeydown="if(event.key==='Enter') doDecide(this.value)"
             style="width:100%;padding:8px 12px;background:var(--surface-2);border:1px solid var(--divider);border-radius:6px;color:var(--text-primary);font-size:13px;outline:none;" />
      <div id="decide-result" style="margin-top:12px;"></div>
    </div>
  `;

  html += `
    <div style="padding:20px;background:var(--surface);border:1px solid var(--divider);border-radius:12px;margin-bottom:20px;">
      <div style="font-size:14px;font-weight:600;color:var(--text-primary);margin-bottom:12px;">Intent Cascade</div>
      <input type="text" class="ask-input" id="intent-input"
             placeholder="improve fitness"
             onkeydown="if(event.key==='Enter') doIntentCascade(this.value)"
             style="width:100%;padding:8px 12px;background:var(--surface-2);border:1px solid var(--divider);border-radius:6px;color:var(--text-primary);font-size:13px;outline:none;" />
      <div id="intent-result" style="margin-top:12px;"></div>
    </div>
  `;

  html += `
    <div style="padding:20px;background:var(--surface);border:1px solid var(--divider);border-radius:12px;">
      <div style="font-size:14px;font-weight:600;color:var(--text-primary);margin-bottom:12px;">Prediction Market</div>
      <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="loadCalibration()">View calibration</button>
      <div id="calibration-result" style="margin-top:12px;"></div>
    </div>
  `;

  html += '</div>';
  el.innerHTML = html;
}

// ─── Reflect: self-reflection prompts + legacy builder ───────────────────

async function loadPersonalReflect(el) {
  let html = '<div class="work-section">';

  html += `
    <div style="padding:20px;background:var(--surface);border:1px solid var(--divider);border-radius:12px;margin-bottom:20px;">
      <div style="font-size:14px;font-weight:600;color:var(--text-primary);margin-bottom:12px;">Reflection Prompts</div>
      <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="loadReflectionPrompts()">Get prompts</button>
      <div id="reflection-prompts-result" style="margin-top:12px;"></div>
    </div>
  `;

  html += `
    <div style="padding:20px;background:var(--surface);border:1px solid var(--divider);border-radius:12px;">
      <div style="font-size:14px;font-weight:600;color:var(--text-primary);margin-bottom:12px;">Legacy Builder</div>
      <div style="font-size:13px;color:var(--text-secondary);margin-bottom:12px;">Document your life stories, values, and wisdom. Always private.</div>
      <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="loadLegacyPrompts()">Get writing prompts</button>
      <div id="legacy-prompts-result" style="margin-top:12px;"></div>
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
    alert('Check-in failed: ' + e.message);
  }
}

async function dismissContradiction(key) {
  try {
    await api.postPersonal('/contradictions/dismiss', { dismiss_key: key });
    loadPersonalSurface('personal-today'); // reload
  } catch (e) {
    alert('Dismiss failed: ' + e.message);
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
    alert('Incognito toggle failed: ' + e.message);
  }
}

async function doMemoryReplay(query) {
  const el = document.getElementById('memory-replay-result');
  if (!el || !query) return;
  el.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Searching memories…</div>';
  try {
    const data = await api.postPersonal('/memory/replay', { query });
    let html = '<div style="padding:12px;background:var(--surface-2);border-radius:8px;">';
    html += `<div style="font-size:13px;color:var(--text-primary);white-space:pre-wrap;">${escapeHtml(humanize(data.summary || ''))}</div>`;
    if (data.third_party_warning) {
      html += `<div style="margin-top:8px;font-size:12px;color:var(--warning);">${escapeHtml(humanize(data.third_party_warning))}</div>`;
    }
    html += '</div>';

    // Round 47 Block 2.2 — Follow-up question chips for memory conversation.
    // After a memory replay answer, show 2-3 follow-up question chips
    // (Bumble pill style). Tapping a chip asks the next question.
    // Chips are derived from the memory graph, not generated by an LLM.
    const followUps = _generateMemoryFollowUps(query, data);
    if (followUps.length > 0) {
      html += '<div style="margin-top:12px;">';
      html += '<div style="font-size:11px;font-weight:700;color:var(--text-muted);margin-bottom:6px;text-transform:uppercase;letter-spacing:0.05em;">Follow up</div>';
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
  el.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Analyzing…</div>';
  try {
    const data = await api.postPersonal('/why', { question });
    let html = '<div style="padding:12px;background:var(--surface-2);border-radius:8px;">';
    if (data.third_party_redirected) {
      html += `<div style="font-size:13px;color:var(--warning);">${escapeHtml(humanize(data.explanation_chain[0].narrative || ''))}</div>`;
    } else {
      data.explanation_chain.forEach(step => {
        html += `<div style="padding:6px 0;border-bottom:1px solid var(--divider);">
          <div style="font-size:13px;font-weight:500;color:var(--text-primary);">${escapeHtml(humanize(step.label || ''))}</div>
          <div style="font-size:12px;color:var(--text-secondary);">${escapeHtml(humanize(step.narrative || ''))}</div>
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
  el.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Analyzing…</div>';
  try {
    const data = await api.postPersonal('/decide', { question });
    let html = '<div style="padding:12px;background:var(--surface-2);border-radius:8px;">';
    html += `<div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;">${escapeHtml(data.label || '')}</div>`;
    html += `<div style="font-size:13px;color:var(--text-primary);margin-bottom:8px;">${escapeHtml(humanize(data.recommendation || ''))}</div>`;
    html += `<div style="display:flex;gap:16px;font-size:12px;"><div><strong>Pros:</strong> ${data.pros.map(p => escapeHtml(p)).join('; ')}</div></div>`;
    html += `<div style="font-size:12px;margin-top:4px;"><strong>Cons:</strong> ${data.cons.map(c => escapeHtml(c)).join('; ')}</div>`;
    html += `<div style="font-size:12px;color:var(--accent);margin-top:8px;">Confidence: ${(data.confidence * 100).toFixed(0)}%</div>`;
    html += '</div>';
    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function doIntentCascade(intent) {
  const el = document.getElementById('intent-result');
  if (!el || !intent) return;
  el.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Breaking down…</div>';
  try {
    const data = await api.postPersonal('/intent-cascade', { intent });
    let html = '<div style="padding:12px;background:var(--surface-2);border-radius:8px;">';
    const sections = [
      ['Assumptions', data.assumptions],
      ['Hypotheses', data.hypotheses],
      ['Preparations', data.preparations],
      ['Evidence Plan', data.evidence_plan],
    ];
    sections.forEach(([label, items]) => {
      html += `<div style="margin-bottom:10px;"><div style="font-size:12px;font-weight:600;color:var(--accent);margin-bottom:4px;">${label}</div>`;
      items.forEach(item => {
        html += `<div style="font-size:12px;color:var(--text-secondary);padding:2px 0;">• ${escapeHtml(humanize(item.text || ''))}</div>`;
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
    el.innerHTML = `<div style="padding:12px;background:var(--surface-2);border-radius:8px;font-size:13px;color:var(--text-primary);">${escapeHtml(data.message || 'No data yet.')}</div>`;
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadReflectionPrompts() {
  const el = document.getElementById('reflection-prompts-result');
  if (!el) return;
  el.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Generating prompts…</div>';
  try {
    const data = await api.getPersonal('/reflection-prompts');
    let html = '<div style="padding:12px;background:var(--surface-2);border-radius:8px;">';
    data.prompts.forEach(p => {
      html += `<div style="padding:8px 0;border-bottom:1px solid var(--divider);">
        <div style="font-size:13px;color:var(--text-primary);">${escapeHtml(humanize(p.prompt || ''))}</div>
        <div class="ds-meta" style="margin-top:2px;">${escapeHtml(p.type || '')}</div>
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
    let html = '<div style="padding:12px;background:var(--surface-2);border-radius:8px;">';
    html += '<div style="font-size:13px;color:var(--text-secondary);margin-bottom:8px;">Writing prompts for your legacy:</div>';
    data.prompts.forEach(p => {
      html += `<div style="font-size:13px;color:var(--text-primary);padding:4px 0;">• ${escapeHtml(p)}</div>`;
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
  el.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Generating report…</div>';
  try {
    const data = await api.getPersonal('/evolution-report');
    el.innerHTML = `<div style="padding:12px;background:var(--surface-2);border-radius:8px;font-size:13px;color:var(--text-primary);white-space:pre-wrap;">${escapeHtml(humanize(data.narrative || ''))}</div>`;
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
  el.innerHTML = '<div class="ds-loading"><span class="spinner"></span> Loading everything Maestro knows about you…</div>';
  try {
    const data = await api.getPersonal('/dashboard');
    let html = '<div class="work-section">';
    html += `<div style="padding:20px;background:var(--surface);border:1px solid var(--divider);border-radius:12px;">`;
    html += `<div style="font-size:16px;font-weight:600;color:var(--text-primary);margin-bottom:8px;">What Maestro Knows About You</div>`;
    html += `<div style="font-size:13px;color:var(--text-secondary);margin-bottom:16px;">${escapeHtml(data.message || '')}</div>`;
    html += `<div class="ds-meta" class="mb-16">${data.total_sources} source(s) · ${data.total_items} item(s)</div>`;

    if (data.sources && data.sources.length > 0) {
      data.sources.forEach(src => {
        html += `<div style="padding:12px 0;border-bottom:1px solid var(--divider);">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <div>
              <div style="font-size:13px;font-weight:500;color:var(--text-primary);">${escapeHtml(src.source)}</div>
              <div class="ds-meta">${src.item_count} item(s) · Consent: ${src.consent_active ? 'active' : 'revoked'}</div>
            </div>
            <button class="ds-btn ds-btn-ghost ds-btn-small" style="font-size:11px;color:var(--risk);"
                    onclick="revokePersonalSource('${escapeHtml(src.source)}')">Revoke</button>
          </div>
        </div>`;
      });
    } else {
      html += '<div style="font-size:13px;color:var(--text-muted);">No data sources connected yet.</div>';
    }

    html += '</div></div>';
    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = `<div class="ds-error">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function revokePersonalSource(source) {
  if (!confirm(`Revoke consent for '${source}' and delete ALL data from this source? This cannot be undone.`)) return;
  try {
    await api.postPersonal('/dashboard/revoke', { source });
    showWhatMaestroKnows(); // reload
  } catch (e) {
    alert('Revoke failed: ' + e.message);
  }
}
