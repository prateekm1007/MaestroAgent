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
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div><div class="skeleton skeleton-line skeleton-line-w50"></div></div>';

  try {
    // Compose the brief from existing API endpoints — no new backend needed
    const [briefing, pulse, contradictionsResp, personality] = await Promise.all([
      api.getOEM('/ceo-briefing'),
      api.getOEM('/pulse').catch(() => null),
      api.getOEM('/contradictions').catch(() => ({ contradictions: [] })),
      api.getOEM('/personality').catch(() => null),
    ]);
    const contradictions = contradictionsResp.contradictions || [];

    // ─── Round 44 Phase 6 / Round 46: Always fetch personal data ─────
    // Round 46: The Today surface is ALWAYS the unified deck. The user
    // does not switch modes. We always fetch the personal briefing so
    // we can interleave work + personal cards. The filter pill (All/
    // Work/Personal) narrows the view — it does NOT change what we fetch.
    let currentFilter = 'all';
    let personalBriefing = null;
    let personalContradsList = [];
    try {
      currentFilter = (typeof getCurrentFilter === 'function') ? getCurrentFilter() : 'all';
    } catch (e) { /* default to 'all' */ }

    // Always fetch personal data (Round 46 — the default is 'all', so we
    // always need personal cards available for the unified deck). The
    // filter is applied at RENDER time, not fetch time.
    try {
      const [pb, pc] = await Promise.all([
        api.getPersonal('/briefing').catch(() => null),
        api.getPersonal('/contradictions').catch(() => ({ contradictions: [] })),
      ]);
      personalBriefing = pb;
      personalContradsList = (pc && pc.contradictions) || [];
    } catch (e) { /* personal mode unavailable — work-only deck */ }
    const currentMode = 'all';  // Round 46 — always 'all' (the filter is separate)

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

    // Fetch 4-level unknowns (V8 Upgrade #2)
    let unknowns = null;
    try {
      unknowns = await api.getOEM('/unknowns?levels=all');
    } catch (e) {
      // Unknowns engine may not be available
    }

    // Fetch tasks (V8 Daily Work #2)
    let tasks = null;
    try {
      tasks = await api.getOEM('/tasks?status=open');
    } catch (e) {
      // Task extraction may not be available
    }

    renderMorningBrief(el, briefing, pulse, contradictions, personality, timeAxis, sowhatData, curiosity, nudges, backgroundLoop, interventions, unknowns, tasks, currentMode, personalBriefing, personalContradsList, currentFilter);
  } catch (e) {
    el.innerHTML = `<div class="calm-empty">
      <div class="b-fs18-text">Good morning.</div>
      <div>We couldn't prepare your brief right now. The organization is still learning.</div>
      <button class="ds-btn ds-btn-ghost ds-btn-small space-4" onclick="loadToday()">Try again</button>
    </div>`;
  }
}

function renderMorningBrief(el, briefing, pulse, contradictions, personality, timeAxis, sowhatData, curiosity, nudges, backgroundLoop, interventions, unknowns, tasks, currentMode, personalBriefing, personalContradsList, currentFilter) {
  // Round 44 Phase 6 — Both Mode handling.
  // If currentMode === 'both', interleave work and personal cards by
  // priority in a single unified swipe deck. Each card has a subtle
  // mode indicator dot (blue for Work, coral for Personal). The unified
  // deck NEVER mixes third-party intelligence — work cards contain only
  // work data, personal cards contain only the user's own personal data.
  //
  // Round 46 — currentMode is always 'all'. The filter pill (currentFilter)
  // narrows the view at RENDER time. 'all' shows everything, 'work' shows
  // only blue-dot cards, 'personal' shows only coral-dot cards.
  currentMode = currentMode || 'all';
  currentFilter = currentFilter || 'all';
  personalBriefing = personalBriefing || null;
  personalContradsList = personalContradsList || [];

  const ot = briefing.one_thing || {};
  const overnight = briefing.overnight || {};
  const changes = overnight.changes || [];
  const money = briefing.money || {};
  const knowledge = briefing.knowledge || {};
  const commitments = briefing.commitments || {};

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

  // Round 46 — apply the filter to work items. If the filter is
  // 'personal', exclude work items (the deck shows only personal cards).
  const filteredItems = currentFilter === 'personal' ? [] : items;

  // ─── Round 44 Phase 6 / Round 46: Build personal cards (always) ────
  // Round 46: Always build personal cards (the default is 'all'). The
  // filter is applied at deck-building time — 'work' excludes personal
  // cards, 'personal' excludes work cards, 'all' includes both.
  // Personal cards contain ONLY the user's own data. Never third-party
  // intelligence. Each card is tagged with _mode='personal' so the
  // renderer can add the coral indicator dot.
  let personalCards = [];
  if (currentFilter !== 'work' && personalBriefing) {
    // Personal calendar items (only the user's own)
    if (personalBriefing.items && personalBriefing.items.length > 0) {
      personalBriefing.items.slice(0, 3).forEach(item => {
        personalCards.push({
          label: 'Personal',
          title: (item.content || '').slice(0, 100),
          context: `From ${item.source || 'your calendar'}`,
          provenance: '',
          sowhat: '',
          action: () => { navTo('personal'); },
          _mode: 'personal',  // coral dot
        });
      });
    }
    // Personal contradictions (only the user's own patterns)
    personalContradsList.slice(0, 2).forEach(c => {
      personalCards.push({
        label: 'Personal pattern',
        title: (c.description || '').slice(0, 100),
        context: c.evidence || '',
        provenance: '',
        sowhat: '',
        action: () => { navTo('personal'); },
        _mode: 'personal',
      });
    });
    // Work Context card from the personal briefing (bidirectional)
    if (personalBriefing.work_context && personalBriefing.work_context.enabled) {
      const wc = personalBriefing.work_context;
      const wcParts = [];
      if (wc.deadlines_today && wc.deadlines_today.length > 0) {
        wcParts.push(`${wc.deadlines_today.length} work deadline${wc.deadlines_today.length !== 1 ? 's' : ''} today`);
      }
      if (wc.meetings_into_personal_time && wc.meetings_into_personal_time.length > 0) {
        wcParts.push(`${wc.meetings_into_personal_time.length} meeting${wc.meetings_into_personal_time.length !== 1 ? 's' : ''} into personal time`);
      }
      if (wcParts.length > 0) {
        personalCards.push({
          label: 'Work context',
          title: wcParts.join(' · '),
          context: wc.commitments_summary || '',
          provenance: '',
          sowhat: '',
          action: () => { navTo('personal'); },
          _mode: 'personal',
        });
      }
    }
  }

  // Tag work items with _mode='work' for the indicator dot
  // Round 46: use filteredItems (respects the filter pill)
  filteredItems.forEach(it => { it._mode = 'work'; });

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
        ${filteredItems.length + personalCards.length > 0 ? `${filteredItems.length + personalCards.length} ${filteredItems.length + personalCards.length === 1 ? 'thing' : 'things'} deserve attention.` : 'Everything is calm. Your organization is working well.'}
      </div>
  `;

  // Round 46 — render the filter pill in the top-right of the Today surface.
  // The pill has 3 options (All/Work/Personal). Default is 'all'.
  html += `<div id="filter-pill-container" class="b-pos-absolute-2"></div>`;

  // Organizational personality one-liner (V3 Law 6)
  if (personality && personality.summary) {
    html += `
      <div class="b-p1216-rad8">
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

  // Brief items — Bumble true swipe-card deck (P0-1 through P0-4).
  // One card at a time. Swipe right to act, left to defer.
  // Withdrawal path: user can switch to scrollable list via "See all."
  //
  // Round 44 Phase 6: In "both" mode, personal cards are interleaved
  // by priority with work cards. Each card carries a _mode tag
  // ('work' = blue dot, 'personal' = coral dot) so the renderer can
  // show a subtle mode indicator. Personal cards NEVER contain
  // third-party intelligence — only the user's own data.
  const totalCardCount = filteredItems.length + personalCards.length;
  if (totalCardCount === 0) {
    html += `<div class="calm-empty b-text-center-9">
      <div class="empty-state"><div class="empty-state-icon"><svg width="64" height="64" viewBox="0 0 64 64" fill="none"><circle cx="32" cy="36" r="12" stroke="#FFC629" stroke-width="2.5" fill="#FFF4D1"/><path d="M12 48 L52 48" stroke="#999999" stroke-width="2" stroke-linecap="round"/><path d="M20 42 L20 48 M32 38 L32 48 M44 42 L44 48" stroke="#FFC629" stroke-width="2" stroke-linecap="round"/></svg></div><div class="empty-state-title">You're all caught up.</div><div class="empty-state-body">No decisions need you right now. We'll surface them here the moment they arrive.</div></div>
      <div class="meta-text">Maestro is watching. You'll know when something matters.</div>
    </div>`;
  } else {
    // P0-3: Build the swipe deck — max 7 cards, prioritized.
    // Priority: commitments due → contradictions → decisions → unknowns → everything else.
    // Round 44: in "both" mode, personal cards interleave by priority:
    //   commitments (work+personal) → contradictions (work+personal) →
    //   decisions (work) → unknowns (work) → habits/personal (personal).
    const categoryColors = {
      'One decision': 'decision',
      'One opportunity': 'decision',
      'One risk': 'due',
      'One thing changed overnight': 'unknown',
      'One thing learned': 'habit',
      'One prediction': 'unknown',
      'Personal': 'habit',
      'Personal pattern': 'habit',
      'Work context': 'due',
    };

    // P0-3: Collect all card data from the briefing sections.
    const deckCards = [];

    // Add commitments as cards (highest priority) — work mode
    if (commitments && commitments.commitments) {
      commitments.commitments.forEach(c => {
        deckCards.push({
          category: 'COMMITMENT',
          categoryClass: 'due',
          judgment: c.description || c.who_committed + ' committed to something',
          evidence: `Due: ${c.due_date || 'today'}${c.is_overdue ? ' — OVERDUE' : ''}`,
          rightLabel: 'REMIND',
          leftLabel: 'DEFER',
          swipeRightAction: () => sendCommitmentReminder(deckCards.indexOf(c)),
          isCommitment: true,
          commitmentIdx: commitments.commitments.indexOf(c),
          _mode: 'work',  // Round 44 — blue dot
        });
      });
    }

    // Add brief items as cards — work mode (Round 46: use filteredItems)
    filteredItems.forEach((item, i) => {
      const categoryClass = categoryColors[item.label] || 'decision';
      const canAct = item.label === 'One decision' || item.label === 'One opportunity';
      deckCards.push({
        category: item.label.toUpperCase(),
        categoryClass: categoryClass,
        judgment: item.title,
        evidence: item.context || item.provenance || '',
        sowhat: item.sowhat || '',
        rightLabel: canAct ? 'ACT NOW' : 'ACKNOWLEDGE',
        leftLabel: 'DEFER',
        swipeRightAction: canAct ? () => {
          openActionSheet('Take action', [
            { label: 'Create ticket', onclick: `quickWriteBack('jira','create_issue',{project:'ENG',summary:'${escapeJs(item.title).replace(/'/g,"\\'")}',description:'${escapeJs(item.context || '').replace(/'/g,"\\'")}',issue_type:'Task'},${i})` },
            { label: 'Send message', onclick: `quickWriteBack('slack','post_message',{channel:'general',text:'${escapeJs(item.title).replace(/'/g,"\\'")}'},${i})` },
          ]);
        } : () => { /* acknowledge — no action needed */ },
        whyCallback: `showInlineWhy('${escapeJs(item.title)}', ${i})`,
        itemIdx: i,
        canAct: canAct,
        _mode: 'work',  // Round 44 — blue dot
      });
    });

    // Round 44 Phase 6: Add personal cards (lowest priority, last in deck).
    // Personal cards contain ONLY the user's own data. Each card has
    // _mode='personal' so the renderer adds the coral indicator dot.
    personalCards.forEach(item => {
      deckCards.push({
        category: item.label.toUpperCase(),
        categoryClass: categoryColors[item.label] || 'habit',
        judgment: item.title,
        evidence: item.context || '',
        sowhat: '',
        rightLabel: 'ACKNOWLEDGE',
        leftLabel: 'DEFER',
        swipeRightAction: () => { /* acknowledge — no action needed */ },
        itemIdx: -1,
        canAct: false,
        _mode: 'personal',  // Round 44 — coral dot
      });
    });

    // Limit to 7 cards (P0-3 constraint)
    const deck = deckCards.slice(0, 7);
    const remaining = deck.length;

    // Render the swipe deck container
    html += `
      <div id="swipe-deck-container" class="b-pos-relative-2">
      </div>
      <div id="swipe-deck-progress" class="b-text-center-5">
        ${remaining} ${remaining === 1 ? 'card' : 'cards'}
      </div>
      <div class="b-text-center-6">
        <button class="maestro-btn maestro-btn-ghost b-fs13-minh36-2" onclick="toggleSwipeDeckView()">See all</button>
      </div>
      <div id="swipe-deck-summary" class="b-hidden-text">
        <div class="b-fs18-fw800-2">That's your morning.</div>
        <div id="swipe-deck-counts" class="b-fs14-text-3"></div>
      </div>
    `;

    // Also render the scrollable fallback (hidden by default)
    // Round 46: use filteredItems (respects the filter pill)
    html += `<div id="swipe-deck-list" class="d-none">`;
    filteredItems.forEach((item, i) => {
      const prepareBtn = item.label === 'One decision' ? `<button class="maestro-btn maestro-btn-full b-mt12-fs14" onclick="prepareExecution('${escapeJs(item.title)}')">Prepare</button>` : '';
      const whyLink = `<a class="why-link b-fs13-text-2" onclick="showInlineWhy('${escapeJs(item.title)}', ${i})">Why?</a>`;
      const actionBtns = item.label === 'One decision' || item.label === 'One opportunity'
        ? `<div class="b-flex-gap8-2">
             <button class="maestro-btn maestro-btn-secondary b-flex-fs13-2" onclick="quickWriteBack('jira','create_issue',{project:'ENG',summary:'${escapeJs(item.title).replace(/'/g,"\\'")}',description:'${escapeJs(item.context || '').replace(/'/g,"\\'")}',issue_type:'Task'},${i})">Create ticket</button>
             <button class="maestro-btn maestro-btn-secondary b-flex-fs13-2" onclick="quickWriteBack('slack','post_message',{channel:'general',text:'${escapeJs(item.title).replace(/'/g,"\\'")}'},${i})">Send message</button>
           </div>`
        : '';
      const categoryClass = categoryColors[item.label] || 'decision';
      // P0-4: Bold confidence labels
      const confLabel = item.confidence != null
        ? (item.confidence >= 0.8 ? 'VERIFIED' : item.confidence >= 0.5 ? 'CONFIDENT' : 'EXPLORING')
        : null;
      const confColor = confLabel === 'VERIFIED' ? 'var(--maestro-success,#00C853)'
                      : confLabel === 'CONFIDENT' ? 'var(--maestro-warning,#FF9800)'
                      : 'var(--maestro-gray-mid,#999999)';
      html += `
        <div class="maestro-card brief-item mb-16" data-idx="${i}">
          <div class="swipe-card-category ${categoryClass} mb-12">${escapeHtml(item.label.toUpperCase())}</div>
          <div class="brief-card-title">${escapeHtml(humanize(item.title))}</div>
          ${item.context ? `<div class="b-fs14-text-14">${escapeHtml(humanize(item.context))}</div>` : ''}
          ${item.provenance ? `<div class="b-fs12-text-4">${escapeHtml(humanize(item.provenance))}</div>` : ''}
          ${confLabel ? `<div class="b-inline-block-6">${confLabel}</div>` : ''}
          ${item.sowhat ? `<div class="b-mt8-p1014">So what: ${escapeHtml(humanize(item.sowhat))}</div>` : ''}
          ${prepareBtn}
          ${actionBtns}
          ${whyLink}
          <div id="inline-why-${i}" class="mt-8"></div>
          <div id="quick-wb-${i}" class="mt-8"></div>
        </div>
      `;
    });
    // Round 44 Phase 6: also render personal cards in the list view,
    // each with a coral mode indicator dot.
    personalCards.forEach((item, i) => {
      const categoryClass = categoryColors[item.label] || 'habit';
      html += `
        <div class="maestro-card brief-item b-mb16-pos" data-idx="p${i}">
          <div class="b-pos-absolute-3" title="Personal" aria-label="Mode: Personal"></div>
          <div class="swipe-card-category ${categoryClass} mb-12">${escapeHtml(item.label.toUpperCase())}</div>
          <div class="brief-card-title">${escapeHtml(humanize(item.title))}</div>
          ${item.context ? `<div class="b-fs14-text-14">${escapeHtml(humanize(item.context))}</div>` : ''}
        </div>
      `;
    });
    html += `</div>`;

    // Store deck state for the swipe handlers
    window._swipeDeck = deck;
    window._swipeDeckIdx = 0;
    window._swipeDeckActed = 0;
    window._swipeDeckDeferred = 0;
  }

  // V6 Spec #3 — Background Loop: "Maestro noticed this while you were away"
  if (backgroundLoop && backgroundLoop.notices && backgroundLoop.notices.length > 0) {
    html += `
      <div class="b-mt24-p20-2">
        <div class="brief-label b-text-muted">While you were away</div>
        <div class="b-fs14-text-16">${escapeHtml(humanize(backgroundLoop.summary || ''))}</div>
        ${backgroundLoop.notices.slice(0, 3).map(n => {
          const color = n.urgency === 'high' ? 'var(--risk)' : n.urgency === 'medium' ? 'var(--warning)' : 'var(--text-secondary)';
          return `<div class="b-p80-u">
            <div class="b-fs13-clr">${escapeHtml(humanize(n.message || ''))}</div>
            ${n.detail ? `<div class="ds-meta mt-2">${escapeHtml(humanize(n.detail))}</div>` : ''}
          </div>`;
        }).join('')}
      </div>
    `;
  }

  // V6 Spec #4 — Trajectory Intervention: declining trajectories that need action
  if (interventions && interventions.interventions && interventions.interventions.length > 0) {
    html += `
      <div class="b-mt24-p20">
        <div class="brief-label b-text-risk">Needs attention</div>
        <div class="b-fs14-text-16">${escapeHtml(humanize(interventions.summary || ''))}</div>
        ${interventions.interventions.slice(0, 2).map(iv => `
          <div class="b-p100-u">
            <div class="b-fs14-text-5">${escapeHtml(humanize(iv.intervention || ''))}</div>
            <div class="ds-meta mt-4">Time to impact: ${escapeHtml(iv.time_to_failure || '')} · Urgency: ${escapeHtml(iv.urgency || '')}</div>
          </div>
        `).join('')}
      </div>
    `;
  }

  // V6 Spec #1 — Adaptive Nudges: actionable restructuring suggestions
  if (nudges && nudges.nudges && nudges.nudges.length > 0) {
    html += `
      <div class="b-mt32-p20">
        <div class="brief-label text-accent">Maestro suggests a change</div>
        <div class="body-text">${escapeHtml(humanize(nudges.summary || ''))}</div>
        ${nudges.nudges.slice(0, 2).map((n, i) => `
          <div class="brief-item b-u-4300" data-nudge-idx="${i}">
            <div class="b-fs14-text-6">${escapeHtml(humanize(n.intervention || ''))}</div>
            <div class="brief-context fs-12">${escapeHtml(humanize(n.evidence || ''))}</div>
            <div class="ds-row b-gap6-mt8">
              <button class="ds-btn ds-btn-positive ds-btn-small" onclick="this.closest('.brief-item').style.opacity='0.5';this.textContent='Accepted'">Accept</button>
              <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="this.closest('.brief-item').style.display='none'">Dismiss</button>
            </div>
          </div>
        `).join('')}
      </div>
    `;
  }

  // V8 P0-1 — Commitments Due Today.
  // The Bond lesson: commitments find the CEO, not vice versa.
  if (commitments && commitments.commitments && commitments.commitments.length > 0) {
    window._currentBriefingCommitments = commitments.commitments;
    html += `
      <div class="maestro-card b-mt16-u-2">
        <div class="swipe-card-category ${commitments.overdue_count > 0 ? 'contradiction' : 'due'} mb-12">Commitments due today</div>
        <div class="b-fs14-text-15">${escapeHtml(humanize(commitments.summary || ''))}</div>
        ${commitments.commitments.map((c, i) => `
          <div class="brief-item b-u-p100">
            <div class="b-flex-u-6">
              <div class="flex-1">
                <div class="brief-context b-text-primary">${escapeHtml(humanize(c.description || ''))}</div>
                <div class="ds-meta mt-4">
                  ${c.who_committed ? `By: ${escapeHtml(c.who_committed)}` : ''}
                  ${c.to_whom ? ` → ${escapeHtml(c.to_whom)}` : ''}
                  ${c.due_date ? ` · Due: ${escapeHtml(c.due_date)}` : ''}
                  ${c.is_overdue ? ' · <span class="b-text-risk">OVERDUE</span>' : ''}
                </div>
              </div>
              <button class="ds-btn ds-btn-ghost ds-btn-small b-fs11-ws"
                      onclick="sendCommitmentReminder(${i})">Remind</button>
            </div>
            <div id="commitment-reminder-${i}" class="mt-8"></div>
          </div>
        `).join('')}
      </div>
    `;
  }

  // V4 Organ #2 → V8 Upgrade #3 — Conversational Curiosity.
  // Maestro asks a question, the user answers, Maestro asks a context-aware
  // follow-up, the user answers again, and after at most 3 turns Maestro
  // says "Thank you. Understanding updated." The answer becomes a
  // human_context signal that feeds into the model.
  if (curiosity && curiosity.questions && curiosity.questions.length > 0) {
    html += `
      <div class="brief-section">
        <div class="brief-label text-accent">Maestro has questions</div>
        <div class="body-text">${escapeHtml(humanize(curiosity.summary))}</div>
        ${curiosity.questions.slice(0, 3).map((q, i) => `
          <div class="curiosity-conversation b-u-p120" data-curiosity-idx="${i}">
            <div class="curiosity-question b-text-primary-2">${escapeHtml(humanize(q.question))}</div>
            <div class="curiosity-evidence ds-meta mb-8">${escapeHtml(humanize(q.evidence))}</div>
            <div class="curiosity-conversation-area" id="curiosity-conv-${i}" data-question-id="${escapeHtml(q.question_id || '')}" data-question-type="${escapeHtml(q.type || '')}" data-domain="${escapeHtml(q.domain || '')}" data-original-question="${escapeHtml(q.question || '')}" data-turn="1">
              <input type="text" class="curiosity-answer-input" id="curiosity-input-${i}"
                     placeholder="Type your answer…"
                     class="b-w-full-8"
                     onkeydown="if(event.key==='Enter') submitCuriosityAnswer(${i})"
                     aria-label="Answer Maestro's question" />
              <button class="ds-btn ds-btn-ghost ds-btn-small mt-6" onclick="submitCuriosityAnswer(${i})">Answer</button>
            </div>
          </div>
        `).join('')}
      </div>
    `;
  }

  // V8 Daily Work #2 — Task & Action-Item Intelligence.
  // Shows tasks b-extracted from signal text during ingestion.
  // Each task has: description, assignee, due_date, priority, status.
  if (tasks && tasks.tasks && tasks.tasks.length > 0) {
    const priorityColor = { high: 'var(--risk,#DC2626)', medium: 'var(--warning,#D97706)', low: 'var(--text-muted)' };
    html += `
      <div class="brief-section">
        <div class="brief-label text-accent">Your tasks</div>
        <div class="body-text">${tasks.total} open task${tasks.total === 1 ? '' : 's'} b-extracted from your organization's signals.</div>
        ${tasks.tasks.slice(0, 5).map(t => `
          <div class="brief-item b-u-p100">
            <div class="b-flex-u-6">
              <div class="flex-1">
                <div class="brief-context b-text-primary">${escapeHtml(humanize(t.description || ''))}</div>
                <div class="ds-meta mt-4">
                  ${t.assignee ? `Assignee: ${escapeHtml(t.assignee)}` : 'Unassigned'}
                  ${t.due_date ? ` · Due: ${escapeHtml(t.due_date)}` : ''}
                  ${t.domain ? ` · Domain: ${escapeHtml(t.domain)}` : ''}
                </div>
              </div>
              <span class="tag b-bg-3ca4">
                ${escapeHtml(t.priority || 'medium')}
              </span>
            </div>
          </div>
        `).join('')}
      </div>
    `;
  }

  // V8 Upgrade #2 — Four-Level Unknowns: what Maestro doesn't know yet.
  // 4 epistemic levels, each with different visual treatment:
  //   Known (green check) — measured thoroughly
  //   Known Unknowns (amber) — the org knows it's under-measuring
  //   Unknown Unknowns (red) — blind spots
  //   Emerging Unknowns (purple pulse) — new and uncategorized
  if (unknowns && (unknowns.known || unknowns.known_unknowns || unknowns.unknown_unknowns || unknowns.emerging_unknowns)) {
    const totalCount = (unknowns.level_counts?.known || 0) + (unknowns.level_counts?.known_unknowns || 0) +
                       (unknowns.level_counts?.unknown_unknowns || 0) + (unknowns.level_counts?.emerging_unknowns || 0);
    if (totalCount > 0) {
      html += `
        <div class="brief-section">
          <div class="brief-label b-text-muted">What Maestro doesn't know yet</div>
          <div class="body-text">${escapeHtml(humanize(unknowns.summary || ''))}</div>
      `;

      // Level 1: Known — green, collapsed by default (it's the "good news")
      if (unknowns.known && unknowns.known.length > 0) {
        html += `
          <details class="unknowns-level unknowns-known mb-12">
            <summary class="brief-card-action">
              <span class="b-text-positive-2">✓</span>
              <strong>Known</strong> — ${unknowns.known.length} area${unknowns.known.length === 1 ? '' : 's'} measured thoroughly
            </summary>
            <div class="brief-item-indent">
              ${unknowns.known.slice(0, 5).map(a => `
                <div class="b-p60-u">
                  <div class="text-body">${escapeHtml(a.area)}</div>
                  <div class="ds-meta mt-2">${a.signal_count} signals · ${Math.round((a.coverage || 0) * 100)}% coverage</div>
                </div>
              `).join('')}
            </div>
          </details>
        `;
      }

      // Level 2: Known Unknowns — amber, expanded (actionable: instrument them)
      if (unknowns.known_unknowns && unknowns.known_unknowns.length > 0) {
        html += `
          <details class="unknowns-level unknowns-known-unknowns" open class="mb-12">
            <summary class="brief-card-action">
              <span class="text-warning">!</span>
              <strong>Known Unknowns</strong> — ${unknowns.known_unknowns.length} area${unknowns.known_unknowns.length === 1 ? '' : 's'} the org knows it's under-measuring
            </summary>
            <div class="brief-item-indent">
              ${unknowns.known_unknowns.slice(0, 5).map(a => `
                <div class="b-p60-u">
                  <div class="text-body">${escapeHtml(a.area)}</div>
                  <div class="ds-meta mt-2">${a.signal_count} signal${a.signal_count === 1 ? '' : 's'} · ${Math.round((a.coverage || 0) * 100)}% coverage</div>
                  <div class="b-fs12-text-8">${escapeHtml(humanize(a.reason || ''))}</div>
                </div>
              `).join('')}
            </div>
          </details>
        `;
      }

      // Level 3: Unknown Unknowns — red, expanded (risky: blind spots)
      if (unknowns.unknown_unknowns && unknowns.unknown_unknowns.length > 0) {
        html += `
          <details class="unknowns-level unknowns-unknown-unknowns" open class="mb-12">
            <summary class="brief-card-action">
              <span class="b-text-risk-2">?</span>
              <strong>Unknown Unknowns</strong> — ${unknowns.unknown_unknowns.length} blind spot${unknowns.unknown_unknowns.length === 1 ? '' : 's'} (the org doesn't know it doesn't know)
            </summary>
            <div class="brief-item-indent">
              ${unknowns.unknown_unknowns.slice(0, 5).map(a => `
                <div class="b-p60-u">
                  <div class="text-body">${escapeHtml(a.area)}</div>
                  <div class="ds-meta mt-2">${a.signal_count} signal${a.signal_count === 1 ? '' : 's'} · ${Math.round((a.coverage || 0) * 100)}% coverage</div>
                  <div class="b-fs12-text-8">${escapeHtml(humanize(a.reason || ''))}</div>
                </div>
              `).join('')}
            </div>
          </details>
        `;
      }

      // Level 4: Emerging Unknowns — purple pulse, expanded (opportunities: investigate)
      if (unknowns.emerging_unknowns && unknowns.emerging_unknowns.length > 0) {
        html += `
          <details class="unknowns-level unknowns-emerging" open class="mb-12">
            <summary class="brief-card-action">
              <span class="text-accent">✦</span>
              <strong>Emerging Unknowns</strong> — ${unknowns.emerging_unknowns.length} new pattern${unknowns.emerging_unknowns.length === 1 ? '' : 's'} in the last 7 days
            </summary>
            <div class="brief-item-indent">
              ${unknowns.emerging_unknowns.slice(0, 5).map(a => `
                <div class="b-p60-u">
                  <div class="text-body">${escapeHtml(a.area)}</div>
                  <div class="ds-meta mt-2">${a.signal_count} new signal${a.signal_count === 1 ? '' : 's'} · detected ${a.detected_at ? new Date(a.detected_at).toLocaleDateString() : 'recently'}</div>
                  <div class="b-fs12-text-8">${escapeHtml(humanize(a.reason || ''))}</div>
                </div>
              `).join('')}
            </div>
          </details>
        `;
      }

      html += `</div>`;
    }
  }

  html += `</div>`;
  el.innerHTML = html;

  // Wire up click handlers
  // Round 46: use filteredItems (respects the filter pill)
  filteredItems.forEach((item, i) => {
    const itemEl = el.querySelector(`.brief-item[data-idx="${i}"]`);
    if (itemEl && item.action) {
      itemEl.addEventListener('click', item.action);
    }
  });

  // Round 46 — render the filter pill into the container we created above.
  // This must happen AFTER el.innerHTML is set, so the container exists.
  if (typeof renderFilterPill === 'function') {
    renderFilterPill('filter-pill-container');
  }

  // V8 P0-1: Initialize the swipe deck after rendering
  initSwipeDeck();
}

// V8 Upgrade #3 — Conversational Curiosity submission handler.
// Called when the user types an answer and hits Enter or clicks "Answer".
// Sends the answer to POST /api/oem/curiosity/follow-up, then either
// renders the follow-up question (turn 2 or 3) or shows the
// "Thank you. Understanding updated." closing message (after turn 3).
async function submitCuriosityAnswer(idx) {
  const inputEl = document.getElementById(`curiosity-input-${idx}`);
  if (!inputEl) return;
  const answer = inputEl.value.trim();
  if (!answer) return;

  const convEl = document.getElementById(`curiosity-conv-${idx}`);
  if (!convEl) return;

  const questionId = convEl.dataset.questionId || '';
  const questionType = convEl.dataset.questionType || '';
  const domain = convEl.dataset.domain || '';
  const originalQuestion = convEl.dataset.originalQuestion || '';
  const currentTurn = parseInt(convEl.dataset.turn || '1', 10);

  // Disable the input while we wait for the response
  inputEl.disabled = true;
  inputEl.value = '';

  // Show the user's answer as a chat bubble (right-aligned)
  const chatArea = convEl;
  chatArea.insertAdjacentHTML('beforebegin', `
    <div class="curiosity-chat-bubble curiosity-chat-user b-m80840-p812">
      ${escapeHtml(answer)}
    </div>
  `);

  // Show a loading indicator
  chatArea.insertAdjacentHTML('beforebegin', `
    <div class="curiosity-loading b-m80-text" id="curiosity-loading-${idx}">Maestro is thinking…</div>
  `);

  try {
    const payload = {
      question_id: questionId,
      answer: answer,
    };
    // On turn 1, include the original question + type + domain so the
    // backend can start a new conversation. On subsequent turns, these
    // are ignored (the backend has the conversation state).
    if (currentTurn === 1) {
      payload.original_question = originalQuestion;
      payload.question_type = questionType;
      payload.domain = domain;
    }

    const data = await api.postOEM('/curiosity/follow-up', payload);

    // Remove the loading indicator
    const loadingEl = document.getElementById(`curiosity-loading-${idx}`);
    if (loadingEl) loadingEl.remove();

    if (data.understanding_updated) {
      // Conversation closed — show the closing message
      chatArea.insertAdjacentHTML('beforebegin', `
        <div class="curiosity-chat-bubble curiosity-chat-maestro curiosity-chat-closing b-m80-p1014">
          <span class="b-text-accent">${escapeHtml(humanize(data.summary || 'Thank you. Understanding updated.'))}</span>
        </div>
      `);
      // Remove the input area — the conversation is done
      chatArea.remove();
    } else if (data.follow_up_question) {
      // Show the follow-up question as a chat bubble (left-aligned)
      chatArea.insertAdjacentHTML('beforebegin', `
        <div class="curiosity-chat-bubble curiosity-chat-maestro b-m84080-p1014">
          ${escapeHtml(humanize(data.follow_up_question))}
        </div>
      `);
      // Update the turn counter and re-enable the input
      convEl.dataset.turn = String(data.turn || (currentTurn + 1));
      inputEl.disabled = false;
      inputEl.placeholder = `Turn ${data.turn || (currentTurn + 1)} of 3 — type your answer…`;
      inputEl.focus();
    } else {
      // Unexpected response — re-enable input and show error
      inputEl.disabled = false;
      chatArea.insertAdjacentHTML('beforebegin', `
        <div class="b-m80-text-2">Something went wrong. Try again.</div>
      `);
    }
  } catch (e) {
    // Remove the loading indicator and re-enable input
    const loadingEl = document.getElementById(`curiosity-loading-${idx}`);
    if (loadingEl) loadingEl.remove();
    inputEl.disabled = false;
    chatArea.insertAdjacentHTML('beforebegin', `
      <div class="b-m80-text-2">Failed: ${escapeHtml(e.message)}</div>
    `);
  }
}

// V8 P0-3 — Quick write-back from briefing items.
// Two taps: (1) preview, (2) approve. Never one tap to send.
async function quickWriteBack(provider, actionType, params, idx) {
  const el = document.getElementById(`quick-wb-${idx}`);
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const preview = await api.postOEM('/writeback', { provider, action_type: actionType, params });
    el.innerHTML = `
      <div class="brief-surface-block">
        <pre class="b-fs11-text-8">${escapeHtml(preview.preview)}</pre>
        <div class="b-flex-gap6">
          <button class="ds-btn ds-btn-primary ds-btn-small fs-11" onclick="approveQuickWriteBack('${preview.action_id}', ${idx})">Approve</button>
          <button class="ds-btn ds-btn-ghost ds-btn-small fs-11" onclick="document.getElementById('quick-wb-${idx}').innerHTML=''">Cancel</button>
        </div>
      </div>
    `;
  } catch (e) {
    el.innerHTML = `<div class="ds-error fs-11">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function approveQuickWriteBack(actionId, idx) {
  const el = document.getElementById(`quick-wb-${idx}`);
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const result = await api.postOEM(`/writeback/${actionId}/approve`, { approved_by: 'ceo' });
    if (result.status === 'executed') {
      const r = result.result || {};
      let detail = r.mock ? ' (mock)' : '';
      if (r.issue_key) detail = ` Created ${r.issue_key}.`;
      else if (r.message_ts) detail = ` Posted to Slack.`;
      else if (r.draft_id) detail = ` Draft created (NOT sent).`;
      el.innerHTML = `<div class="b-p8-text-2">Done.${detail}</div>`;
    } else {
      el.innerHTML = `<div class="ds-error fs-11">Failed: ${escapeHtml(result.error || '')}</div>`;
    }
  } catch (e) {
    el.innerHTML = `<div class="ds-error fs-11">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

// V8 P0-2 — Inline "Why?" explanation on any briefing item.
// Fetches /explain with a context-derived question and renders the
// explanation chain inline as a collapsible section. Apple's deference
// principle: the explanation is hidden until the customer asks for it.
async function showInlineWhy(title, idx) {
  const el = document.getElementById(`inline-why-${idx}`);
  if (!el) return;
  if (el.innerHTML.trim()) {
    el.innerHTML = ''; // toggle off if already shown
    return;
  }
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const question = `Why is this happening: ${title}?`;
    const data = await api.getOEM(`/explain?q=${encodeURIComponent(question)}`);
    if (!data.steps || data.steps.length === 0) {
      el.innerHTML = `<div class="b-p812-bg">${escapeHtml(humanize(data.honest_limitation || 'Not enough data to explain yet.'))}</div>`;
      return;
    }
    let chainHtml = '<div class="space-2">';
    for (const step of data.steps.slice(0, 5)) {
      const confPct = Math.round((step.confidence || 0) * 100);
      const confColor = confPct >= 70 ? 'var(--accent)' : confPct >= 40 ? 'var(--secondary)' : 'var(--text-muted)';
      chainHtml += `
        <div class="b-flex-gap10">
          <div class="b-u-5cd1-2">${step.step}</div>
          <div class="flex-1">
            <div class="b-fs12-text-14">${escapeHtml(humanize(step.label || ''))}</div>
            <div class="b-fs11-text-7">${escapeHtml(humanize(step.narrative || ''))}</div>
            <div class="b-mt2-h2"><div class="b-h100-wconfpctp"></div></div>
          </div>
        </div>
      `;
    }
    chainHtml += '</div>';
    el.innerHTML = chainHtml;
  } catch (e) {
    el.innerHTML = `<div class="ds-error fs-11">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

// V8 P0-1 — Send a commitment reminder via write-back (Slack DM draft).
async function sendCommitmentReminder(idx) {
  const el = document.getElementById(`commitment-reminder-${idx}`);
  if (!el) return;
  const commitments = (window._currentBriefingCommitments) || [];
  const c = commitments[idx];
  if (!c) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const reminderText = `Gentle reminder: ${c.description} (due ${c.due_date || 'today'}). Can you provide an update?`;
    const preview = await api.postOEM('/writeback', {
      provider: 'slack',
      action_type: 'post_message',
      params: { channel: 'general', text: reminderText },
    });
    el.innerHTML = `
      <div class="brief-surface-block">
        <pre class="b-fs11-text-8">${escapeHtml(preview.preview)}</pre>
        <div class="b-flex-gap6">
          <button class="ds-btn ds-btn-primary ds-btn-small fs-11" onclick="approveCommitmentReminder('${preview.action_id}', ${idx})">Approve & Send</button>
          <button class="ds-btn ds-btn-ghost ds-btn-small fs-11" onclick="document.getElementById('commitment-reminder-${idx}').innerHTML=''">Cancel</button>
        </div>
      </div>
    `;
  } catch (e) {
    el.innerHTML = `<div class="ds-error fs-11">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function approveCommitmentReminder(actionId, idx) {
  const el = document.getElementById(`commitment-reminder-${idx}`);
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const result = await api.postOEM(`/writeback/${actionId}/approve`, { approved_by: 'ceo' });
    if (result.status === 'executed') {
      el.innerHTML = `<div class="b-p8-text-2">Reminder sent.</div>`;
    } else {
      el.innerHTML = `<div class="ds-error fs-11">Failed: ${escapeHtml(result.error || '')}</div>`;
    }
  } catch (e) {
    el.innerHTML = `<div class="ds-error fs-11">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

// V8 P0-1: Initialize the swipe deck after the briefing renders.
// Called after el.innerHTML is set — finds the container and renders the first card.
function initSwipeDeck() {
  const container = document.getElementById('swipe-deck-container');
  if (!container || !window._swipeDeck || window._swipeDeck.length === 0) return;

  window._swipeDeckIdx = 0;
  window._swipeDeckActed = 0;
  window._swipeDeckDeferred = 0;

  renderSwipeCard();
}

function renderSwipeCard() {
  const container = document.getElementById('swipe-deck-container');
  if (!container) return;

  const deck = window._swipeDeck || [];
  const idx = window._swipeDeckIdx || 0;

  // Check if deck is complete
  if (idx >= deck.length) {
    showSwipeDeckSummary();
    return;
  }

  const cardData = deck[idx];
  container.innerHTML = '';

  // Use createSwipeCard from swipe-cards.js
  if (typeof createSwipeCard !== 'function') return;

  const card = createSwipeCard({
    category: cardData.category,
    category_class: cardData.categoryClass,
    judgment: cardData.judgment,
    evidence: cardData.evidence,
    right_label: cardData.rightLabel,
    left_label: cardData.leftLabel,
    why_link: cardData.whyCallback ? true : false,
    why_callback: cardData.whyCallback || '',
  });

  // Round 44 Phase 6 — Mode indicator dot.
  // Blue dot for Work, coral dot for Personal. Subtle, in the top-right
  // corner of the card. Only shown in "both" mode (when the deck mixes
  // work and personal cards). In single-mode decks the dot is omitted
  // because every card has the same mode.
  if (cardData._mode) {
    const dotColor = cardData._mode === 'personal' ? '#FF6B6B' : '#2196F3';  // coral / blue
    const dotTitle = cardData._mode === 'personal' ? 'Personal' : 'Work';
    const dot = document.createElement('div');
    dot.style.cssText = `position:absolute;top:14px;right:14px;width:10px;height:10px;border-radius:50%;background:${dotColor};opacity:0.85;title:${dotTitle};`;
    dot.title = dotTitle;
    dot.setAttribute('aria-label', `Mode: ${dotTitle}`);
    card.appendChild(dot);
  }

  // Style the card for the deck (absolute positioning within container)
  card.style.position = 'relative';
  container.appendChild(card);

  // Initialize the SwipeCard class on this element
  const swipeHandler = new SwipeCard(card,
    // Swipe right callback
    () => {
      window._swipeDeckActed++;
      if (cardData.swipeRightAction) cardData.swipeRightAction();
      advanceSwipeDeck();
    },
    // Swipe left callback
    () => {
      window._swipeDeckDeferred++;
      advanceSwipeDeck();
    }
  );

  // Update progress
  updateSwipeDeckProgress();
}

function advanceSwipeDeck() {
  window._swipeDeckIdx = (window._swipeDeckIdx || 0) + 1;
  setTimeout(() => renderSwipeCard(), 350);
}

function updateSwipeDeckProgress() {
  const progress = document.getElementById('swipe-deck-progress');
  if (!progress) return;
  const deck = window._swipeDeck || [];
  const idx = window._swipeDeckIdx || 0;
  const remaining = deck.length - idx;
  if (remaining > 0) {
    progress.textContent = `${remaining} ${remaining === 1 ? 'card' : 'cards'}`;
  } else {
    progress.textContent = '';
  }
}

function showSwipeDeckSummary() {
  const container = document.getElementById('swipe-deck-container');
  if (container) container.innerHTML = '';
  const progress = document.getElementById('swipe-deck-progress');
  if (progress) progress.style.display = 'none';
  const summary = document.getElementById('swipe-deck-summary');
  if (summary) {
    summary.style.display = 'block';
    const counts = document.getElementById('swipe-deck-counts');
    if (counts) {
      const acted = window._swipeDeckActed || 0;
      const deferred = window._swipeDeckDeferred || 0;
      counts.textContent = `${acted} ${acted === 1 ? 'action' : 'actions'} taken, ${deferred} ${deferred === 1 ? 'item' : 'items'} deferred. Have a good day.`;
    }
  }
}

// V8 P0-1: Toggle between swipe deck and scrollable list view.
function toggleSwipeDeckView() {
  const deck = document.getElementById('swipe-deck-container');
  const progress = document.getElementById('swipe-deck-progress');
  const list = document.getElementById('swipe-deck-list');
  const summary = document.getElementById('swipe-deck-summary');
  const btn = event ? event.target : null;

  if (deck && deck.style.display !== 'none') {
    // Switch to list view
    deck.style.display = 'none';
    if (progress) progress.style.display = 'none';
    if (summary) summary.style.display = 'none';
    if (list) list.style.display = 'block';
    if (btn) btn.textContent = 'Swipe view';
  } else {
    // Switch to swipe view
    if (deck) deck.style.display = 'block';
    if (progress) progress.style.display = 'block';
    if (list) list.style.display = 'none';
    if (btn) btn.textContent = 'See all';
    if (window._swipeDeckIdx >= (window._swipeDeck || []).length) {
      showSwipeDeckSummary();
    } else {
      renderSwipeCard();
    }
  }
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
    body.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div><div class="skeleton skeleton-line skeleton-line-w50"></div></div>';
    try {
      const plan = await api.getOEM(`/execute?recommendation_id=${encodeURIComponent(title)}`);
      body.innerHTML = `
        <div class="ds-stack">
          <div>
            <div class="ds-cascade-label">Execution plan</div>
            <div class="b-fs15-text-3">${escapeHtml(humanize(plan.summary || ''))}</div>
          </div>
          ${plan.steps ? plan.steps.map(s => `
            <div class="ds-card b-p14">
              <div class="ds-row-between mb-6">
                <span class="ds-tag ds-tag-pending">Step ${s.step}</span>
                <span class="ds-meta">${escapeHtml(s.estimated_time || '')}</span>
              </div>
              <div class="b-fs14-fw500-3">${escapeHtml(humanize(s.title || ''))}</div>
              <div class="subtle-text">${escapeHtml(humanize(s.detail || ''))}</div>
              <div class="ds-meta mt-6">Owner: ${escapeHtml(humanize(s.owner || ''))}${s.prerequisite ? ' · After: ' + escapeHtml(humanize(s.prerequisite)) : ''}</div>
            </div>
          `).join('') : ''}
          <div>
            <div class="ds-cascade-label">Drafted briefing</div>
            <div class="b-p14-bg-3">${escapeHtml(humanize(plan.drafted_briefing || ''))}</div>
          </div>
          <div>
            <div class="ds-cascade-label">Follow-through</div>
            <div class="subtle-text">
              Check-in: ${escapeHtml(plan.follow_through?.check_in_date || '')}<br>
              Success: ${escapeHtml(humanize(plan.follow_through?.success_metric || ''))}
            </div>
          </div>
          <div class="b-u-7f83">
            <div class="ds-cascade-label mb-10">Execute — create tickets, drafts, messages</div>
            <div class="b-flex-gap8-4">
              <button class="ds-btn ds-btn-primary ds-btn-small" onclick="executeWriteBack('jira','create_issue',{project:'ENG',summary:'${escapeJs(title).replace(/'/g,"\\'")}',description:'See execution plan',issue_type:'Task'})">Create Jira ticket</button>
              <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="executeWriteBack('gmail','create_draft',{to:'team@acme.com',subject:'Action needed: ${escapeJs(title).replace(/'/g,"\\'")}',body:'See execution plan'})">Draft email</button>
              <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="executeWriteBack('slack','post_message',{channel:'general',text:'Action needed: ${escapeJs(title).replace(/'/g,"\\'")}'})">Post to Slack</button>
            </div>
            <div id="writeback-result" class="space-3"></div>
          </div>
        </div>
      `;
    } catch (e) {
      body.innerHTML = `<div class="ds-error">Failed to prepare: ${escapeHtml(e.message)}</div>`;
    }
  }, 500);
}

// V8 Daily Work #4 — Write-Back to Tools.
// Called when the user clicks "Create Jira ticket", "Draft email", or
// "Post to Slack" in the execution plan modal. Shows a preview first,
// then requires the user to click "Approve" to execute.
async function executeWriteBack(provider, actionType, params) {
  const resultEl = document.getElementById('writeback-result');
  if (!resultEl) return;

  resultEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    // Step 1: Preview (NOT executed)
    const preview = await api.postOEM('/writeback', { provider, action_type: actionType, params });

    // Show preview + approve/reject buttons
    resultEl.innerHTML = `
      <div class="b-p14-bg-2">
        <div class="b-fs13-fw500-3">Preview</div>
        <pre class="b-fs12-text-20">${escapeHtml(preview.preview)}</pre>
        <div class="flex-row">
          <button class="ds-btn ds-btn-primary ds-btn-small" onclick="approveWriteBack('${preview.action_id}')">Approve & Execute</button>
          <button class="ds-btn ds-btn-ghost ds-btn-small" onclick="rejectWriteBack('${preview.action_id}')">Reject</button>
        </div>
      </div>
    `;
  } catch (e) {
    resultEl.innerHTML = `<div class="ds-error">Preview failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function approveWriteBack(actionId) {
  const resultEl = document.getElementById('writeback-result');
  if (!resultEl) return;
  resultEl.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';
  try {
    const result = await api.postOEM(`/writeback/${actionId}/approve`, { approved_by: 'ceo' });
    if (result.status === 'executed') {
      const r = result.result || {};
      let detail = '';
      if (r.provider === 'jira') detail = `Issue created: <a href="${r.issue_url || '#'}" target="_blank" class="text-accent">${escapeHtml(r.issue_key || '')}</a>`;
      else if (r.provider === 'gmail') detail = `Draft created (NOT sent): <a href="${r.draft_url || '#'}" target="_blank" class="text-accent">Open in Gmail</a>`;
      else if (r.provider === 'slack') detail = `Message posted to ${escapeHtml(r.channel || '')} (ts: ${escapeHtml(r.message_ts || '')})`;
      else if (r.provider === 'github') detail = `Comment created: <a href="${r.comment_url || '#'}" target="_blank" class="text-accent">View</a>`;
      resultEl.innerHTML = `<div class="b-p14-bg">Executed. ${detail}${r.mock ? ' (mock mode — no real API call)' : ''}</div>`;
    } else {
      resultEl.innerHTML = `<div class="ds-error">Execution failed: ${escapeHtml(result.error || 'unknown error')}</div>`;
    }
  } catch (e) {
    resultEl.innerHTML = `<div class="ds-error">Execution failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function rejectWriteBack(actionId) {
  const resultEl = document.getElementById('writeback-result');
  if (!resultEl) return;
  try {
    await api.postOEM(`/writeback/${actionId}/reject`, { rejected_by: 'ceo' });
    resultEl.innerHTML = `<div class="b-p14-text">Action rejected.</div>`;
  } catch (e) {
    resultEl.innerHTML = `<div class="ds-error">Reject failed: ${escapeHtml(e.message)}</div>`;
  }
}

// ═══════════════════════════════════════════════════════════════════════════
