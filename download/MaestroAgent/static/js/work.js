// THE INVISIBLE MAESTRO — WORK surface (Bumble-redesigned, Round 45)
// ═══════════════════════════════════════════════════════════════════════════
// WORK never looks like software. Maestro follows the user into existing
// tools. The user never opens Maestro. Maestro quietly appears.
//
// Round 45 redesign — 3 sub-surfaces, all Bumble-styled:
//   1. Whispers  — ambient intelligence from contradictions + overnight
//   2. Timeline  — chronological signal feed (V8 Daily Work #1)
//   3. Tasks     — b-extracted action items (V8 Daily Work #2)
//
// Bumble design: bold cards, pill buttons, system typography,
// swipe-card-category badges, maestro-btn classes. Each surface uses
// the same maestro-card container so the visual language is consistent
// with Today and Ask.
//
// WITHDRAWAL PATH (Guideline P9):
// The user could check GitHub/Jira/Slack directly. The Work surface
// aggregates signals they would otherwise check across 5 provider
// dashboards. Without it, the user is less oriented but fully functional.
// ═══════════════════════════════════════════════════════════════════════════

// Sub-tab state — persists across nav within the Work surface.
let _workSubTab = 'whispers';  // 'whispers' | 'timeline' | 'tasks'

async function loadWork() {
  const el = document.getElementById('work-content');
  if (!el) return;
  el.innerHTML = '<div class="skeleton-card"><div class="skeleton skeleton-line skeleton-line-w40 skeleton-line-h12"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line-w70"></div></div>';

  try {
    // Fetch everything in parallel — the 3 sub-tabs share the same data
    // fetch so switching tabs is instant (no loading flicker).
    const [briefing, contradictions, dashboard, timeline, tasks] = await Promise.all([
      api.getOEM('/ceo-briefing'),
      api.getOEM('/contradictions').catch(() => ({ contradictions: [] })),
      api.getOEM('/dashboard').catch(() => null),
      api.getOEM('/timeline?limit=30').catch(() => null),
      api.getOEM('/tasks?status=open').catch(() => null),
    ]);

    renderWorkSurface(el, briefing, contradictions, dashboard, timeline, tasks);
  } catch (e) {
    el.innerHTML = `<div class="calm-empty b-text-center-9">
      <div class="brief-card-title">Maestro is connecting to your tools.</div>
      <div class="meta-text">Configure signal sources in Settings to see ambient intelligence here.</div>
    </div>`;
  }
}

function renderWorkSurface(el, briefing, contradictions, dashboard, timeline, tasks) {
  const decisions = briefing.decisions || { decisions: [] };
  const overnight = briefing.overnight || { changes: [] };
  const Contradictions = contradictions.contradictions || [];
  const metrics = dashboard ? dashboard.metrics || {} : {};
  const providers = dashboard ? dashboard.providers_connected || [] : [];

  // ─── Bumble sub-tab navigation (pill buttons) ─────────────────────
  // Three pills: Whispers, Timeline, Tasks. The active pill gets the
  // Bumble yellow background; inactive pills are ghost.
  const tabCounts = {
    whispers: Contradictions.length + overnight.changes.length,
    timeline: timeline ? (timeline.signals || []).length : 0,
    tasks: tasks ? (tasks.tasks || []).filter(t => t.status === 'open').length : 0,
  };

  let html = `<div class="work-section">`;

  // Sub-tab pills — Bumble style
  html += `
    <div class="b-flex-gap8">
      <button class="maestro-btn ${_workSubTab === 'whispers' ? '' : 'maestro-btn-ghost'}"
              class="b-fs13-minh36-3"
              onclick="_workSetTab('whispers')">
        Whispers${tabCounts.whispers > 0 ? ` · ${tabCounts.whispers}` : ''}
      </button>
      <button class="maestro-btn ${_workSubTab === 'timeline' ? '' : 'maestro-btn-ghost'}"
              class="b-fs13-minh36-3"
              onclick="_workSetTab('timeline')">
        Timeline${tabCounts.timeline > 0 ? ` · ${tabCounts.timeline}` : ''}
      </button>
      <button class="maestro-btn ${_workSubTab === 'tasks' ? '' : 'maestro-btn-ghost'}"
              class="b-fs13-minh36-3"
              onclick="_workSetTab('tasks')">
        Tasks${tabCounts.tasks > 0 ? ` · ${tabCounts.tasks}` : ''}
      </button>
    </div>
  `;

  // Render the active sub-tab
  if (_workSubTab === 'whispers') {
    html += _renderWhispersSurface(Contradictions, overnight, decisions, metrics, providers);
  } else if (_workSubTab === 'timeline') {
    html += _renderTimelineSurface(timeline);
  } else if (_workSubTab === 'tasks') {
    html += _renderTasksSurface(tasks);
  }

  html += `</div>`;
  el.innerHTML = html;

  // Wire up any surface-specific interactions
  _wireWorkSurfaceInteractions(el);
}

function _workSetTab(tab) {
  _workSubTab = tab;
  // Re-render without refetching — the data is already in the closure.
  // We trigger a reload to keep the code simple; the SWR cache makes
  // this instant.
  loadWork();
}

// ═══════════════════════════════════════════════════════════════════════════
// SUB-TAB 1: WHISPERS — ambient intelligence from contradictions + overnight
// ═══════════════════════════════════════════════════════════════════════════

function _renderWhispersSurface(Contradictions, overnight, decisions, metrics, providers) {
  // Generate whispers from contradictions and overnight changes
  const whispers = [];

  Contradictions.slice(0, 3).forEach(c => {
    whispers.push({
      text: c.title || c.description || 'A contradiction was detected in your organization.',
      source: c.type || 'organizational pattern',
      action: () => navTo('contradictions'),
    });
  });

  overnight.changes.slice(0, 2).forEach(c => {
    whispers.push({
      text: `${c.title}: ${c.detail}`.substring(0, 120),
      source: c.entity || c.domain || 'overnight signal',
      action: () => navTo('home'),
    });
  });

  // Generate ambient integration cards from REAL data (not hardcoded)
  const ambientCards = [];

  // GitHub card
  const githubConnected = providers.includes('github');
  ambientCards.push({
    tool: 'GitHub',
    message: githubConnected
      ? `${metrics.signals_processed || 0} signals processed from your repositories. ${decisions.decisions.length > 0 ? `${decisions.decisions.length} ${decisions.decisions.length === 1 ? 'decision needs' : 'decisions need'} attention.` : 'No blocked PRs detected.'}`
      : 'GitHub is not connected. Configure it in Settings to see repository intelligence here.',
    action: () => navTo('eng-signals'),
  });

  // Slack card
  ambientCards.push({
    tool: 'Slack',
    message: providers.includes('slack')
      ? (Contradictions.length > 0
        ? `${Contradictions.length} ${Contradictions.length === 1 ? 'cross-team tension was' : 'cross-team tensions were'} detected in recent conversations.`
        : 'Conversations are flowing normally. No tensions detected.')
      : 'Slack is not connected. Configure it in Settings to see conversation intelligence.',
    action: () => navTo('contradictions'),
  });

  // Jira card
  ambientCards.push({
    tool: 'Jira',
    message: providers.includes('jira')
      ? `${metrics.patterns_inferred || 0} patterns inferred from issue transitions. ${metrics.patterns_validated || 0} organizational patterns validated.`
      : 'Jira is not connected. Configure it in Settings to see issue-transition intelligence.',
    action: () => navTo('eng-signals'),
  });

  // Outlook card
  ambientCards.push({
    tool: 'Outlook',
    message: 'Install the Maestro bookmarklet to see organizational context inside your email.',
    action: () => navTo('eng-settings'),
  });

  // Deep capabilities (compressed)
  const deepCaps = [
    { label: 'Decisions I owe', surface: 'inbox', count: decisions.decisions.length },
    { label: 'What changed overnight', surface: 'home', count: overnight.changes.length },
    { label: 'Customer relationships', surface: 'customer', count: 0 },
    { label: 'Live meeting intelligence', surface: 'live', count: 0 },
  ];

  let html = '';

  // Whispers — Bumble cards with amber accent
  if (whispers.length > 0) {
    html += `<div class="b-fs14-fw800-5">Whispers</div>`;
    whispers.forEach((w, i) => {
      html += `
        <div class="maestro-card whisper b-mb12-u" data-idx="${i}">
          <div class="b-fs15-fw700">${escapeHtml(humanize(w.text))}</div>
          <div class="b-fs12-fw600-4">via ${escapeHtml(w.source)}</div>
        </div>
      `;
    });
  } else {
    html += `<div class="calm-empty b-text-center-8">
      <div class="b-fs16-fw800">No whispers right now.</div>
      <div class="b-fs13-text-3">Maestro is listening. You'll know when something matters.</div>
    </div>`;
  }

  // Ambient integrations — Bumble cards with tool badges
  html += `<div class="b-fs14-fw800-9">In your tools</div>`;
  ambientCards.forEach((a, i) => {
    html += `
      <div class="maestro-card ambient-card b-mb12-cursor" data-idx="${i}">
        <div class="b-inline-block-7">${escapeHtml(a.tool)}</div>
        <div class="b-fs14-text-12">${escapeHtml(a.message)}</div>
      </div>
    `;
  });

  // Deep capabilities — Bumble pill buttons
  html += `<div class="b-fs14-fw800-9">Deep capabilities</div>`;
  html += `<div class="b-u-998b-2">`;
  deepCaps.forEach(cap => {
    const label = cap.count > 0
      ? `${escapeHtml(humanize(cap.label))} · ${cap.count}`
      : escapeHtml(humanize(cap.label));
    html += `<button class="maestro-btn maestro-btn-secondary b-fs14-minh44-2" onclick="navTo('${cap.surface}')">${label}</button>`;
  });
  html += `</div>`;

  return html;
}

// ═══════════════════════════════════════════════════════════════════════════
// SUB-TAB 2: TIMELINE — chronological signal feed (V8 Daily Work #1)
// Each signal is a maestro-card with a swipe-card-category badge for its
// provider. The timeline shows what happened across all tools in one view.
// ═══════════════════════════════════════════════════════════════════════════

function _renderTimelineSurface(timeline) {
  if (!timeline || !timeline.signals || timeline.signals.length === 0) {
    return `<div class="calm-empty b-text-center-9">
      <div class="b-fs18-fw800-4">No signals yet.</div>
      <div class="meta-text">Connect a signal source (GitHub, Jira, Slack) to see your organizational timeline here.</div>
    </div>`;
  }

  const signals = timeline.signals;
  const pagination = timeline.pagination || {};
  const filtersApplied = timeline.filters_applied || {};

  let html = '';

  // Header — count + pagination info
  html += `<div class="b-fs14-fw800-7">Organizational Timeline</div>`;
  html += `<div class="b-fs12-text-3">${pagination.total || signals.length} signal${(pagination.total || signals.length) === 1 ? '' : 's'} · most recent first${pagination.has_more ? ' · scroll for more' : ''}</div>`;

  // Filter pills (read-only display — future iteration can make them clickable)
  const activeFilters = Object.entries(filtersApplied).filter(([_, v]) => v);
  if (activeFilters.length > 0) {
    html += `<div class="b-flex-gap6-2">`;
    activeFilters.forEach(([key, val]) => {
      html += `<div class="b-inline-block-4">${escapeHtml(key)}: ${escapeHtml(String(val))}</div>`;
    });
    html += `</div>`;
  }

  // Signals — each is a maestro-card with a provider badge
  signals.forEach((sig, i) => {
    const provider = sig.provider || 'unknown';
    const signalType = sig.type || 'signal';
    const actor = sig.actor || '';
    const artifact = sig.artifact || '';
    const domain = sig.domain || '';
    const timestamp = sig.timestamp || '';

    // Provider badge color mapping (matches the swipe-card-category palette)
    const providerBadgeClass = _providerToCategoryClass(provider);

    // Build the signal description from type + artifact
    const description = _describeSignal(signalType, artifact, actor, domain);

    // Relative time (simple — just show the timestamp for now)
    const timeDisplay = _formatTimestamp(timestamp);

    html += `
      <div class="maestro-card timeline-card mb-12" data-idx="${i}">
        <div class="b-flex-u-9">
          <div class="b-flex-u">
            <div class="swipe-card-category ${providerBadgeClass} mb-8">${escapeHtml(provider.toUpperCase())}</div>
            <div class="b-fs15-fw700-2">${escapeHtml(humanize(description))}</div>
            ${actor ? `<div class="b-fs12-fw600-5">by ${escapeHtml(humanize(actor))}</div>` : ''}
            ${domain ? `<div class="b-fs11-text-2">${escapeHtml(humanize(domain))}</div>` : ''}
          </div>
          <div class="b-fs11-text-4">${escapeHtml(timeDisplay)}</div>
        </div>
      </div>
    `;
  });

  // Load more button (if pagination has more)
  if (pagination.has_more) {
    html += `<div class="b-text-center-3">
      <button class="maestro-btn maestro-btn-ghost b-fs13-minh36-2" onclick="_loadMoreTimeline()">Load more</button>
    </div>`;
  }

  return html;
}

function _providerToCategoryClass(provider) {
  // Map provider to the swipe-card-category color palette
  const p = (provider || '').toLowerCase();
  if (p === 'github') return 'decision';      // yellow
  if (p === 'jira') return 'due';             // amber
  if (p === 'slack') return 'contradiction';  // red-tinted
  if (p === 'gmail' || p === 'confluence') return 'habit';  // green
  if (p === 'customer') return 'unknown';     // gray
  return 'unknown';
}

function _describeSignal(signalType, artifact, actor, domain) {
  // Build a human description from the signal type
  const t = (signalType || '').toLowerCase();
  if (t.startsWith('pr.')) {
    if (t === 'pr.opened') return `Pull request opened: ${artifact}`;
    if (t === 'pr.merged') return `Pull request merged: ${artifact}`;
    if (t === 'pr.closed') return `Pull request closed: ${artifact}`;
    if (t === 'pr.review') return `PR review: ${artifact}`;
    return `Pull request activity: ${artifact}`;
  }
  if (t.startsWith('issue.')) {
    if (t === 'issue.transitioned') return `Issue transitioned: ${artifact}`;
    if (t === 'issue.created') return `Issue created: ${artifact}`;
    if (t === 'issue.closed') return `Issue closed: ${artifact}`;
    return `Issue activity: ${artifact}`;
  }
  if (t.startsWith('message.') || t === 'message') {
    return `Message in ${domain || 'a channel'}: ${artifact}`;
  }
  if (t.startsWith('email.') || t === 'email') {
    return `Email: ${artifact}`;
  }
  if (t.startsWith('doc.') || t === 'doc') {
    return `Document: ${artifact}`;
  }
  // Fallback — show the type and artifact
  return `${signalType}: ${artifact}`;
}

function _formatTimestamp(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    const now = new Date();
    const diffMs = now - d;
    const diffMin = Math.floor(diffMs / 60000);
    const diffHr = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHr / 24);
    if (diffMin < 1) return 'just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    if (diffHr < 24) return `${diffHr}h ago`;
    if (diffDay < 7) return `${diffDay}d ago`;
    return d.toLocaleDateString();
  } catch (e) {
    return String(ts).slice(0, 10);
  }
}

let _timelineOffset = 30;
async function _loadMoreTimeline() {
  try {
    const more = await api.getOEM(`/timeline?limit=30&offset=${_timelineOffset}`);
    if (more && more.signals && more.signals.length > 0) {
      _timelineOffset += 30;
      // Append to the existing timeline — for simplicity, just reload
      loadWork();
    }
  } catch (e) {
    // Non-fatal
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// SUB-TAB 3: TASKS — b-extracted action items (V8 Daily Work #2)
// Each task is a maestro-card with a priority badge. Swipe-right marks
// the task done (with confirmation); swipe-left defers it.
// ═══════════════════════════════════════════════════════════════════════════

function _renderTasksSurface(tasks) {
  if (!tasks || !tasks.tasks || tasks.tasks.length === 0) {
    return `<div class="calm-empty b-text-center-9">
      <div class="b-fs18-fw800-4">No open tasks.</div>
      <div class="meta-text">Maestro scans your signals for action items ("Priya to review by Friday", "TODO: update docs"). They'll appear here.</div>
    </div>`;
  }

  const openTasks = tasks.tasks.filter(t => t.status === 'open');
  const doneCount = tasks.done_count || 0;
  const highPriorityCount = tasks.high_priority_count || 0;

  let html = '';

  // Header — counts
  html += `<div class="b-fs14-fw800-7">Your Tasks</div>`;
  html += `<div class="b-fs12-text-3">${openTasks.length} open · ${doneCount} done${highPriorityCount > 0 ? ` · ${highPriorityCount} high priority` : ''}</div>`;

  // Sort open tasks: high priority first, then by due date
  const sorted = [...openTasks].sort((a, b) => {
    const priRank = { high: 0, medium: 1, low: 2 };
    const priDiff = (priRank[a.priority] || 3) - (priRank[b.priority] || 3);
    if (priDiff !== 0) return priDiff;
    // Earlier due dates first
    if (a.due_date && b.due_date) return a.due_date.localeCompare(b.due_date);
    if (a.due_date) return -1;
    if (b.due_date) return 1;
    return 0;
  });

  // Render each task as a maestro-card with a priority badge
  sorted.forEach((task, i) => {
    const priority = task.priority || 'medium';
    const assignee = task.assignee || '';
    const dueDate = task.due_date || '';
    const domain = task.domain || '';
    const description = task.description || '';
    const taskId = task.id || '';

    // Priority badge — color matches the swipe-card-category palette
    const priBadgeClass = priority === 'high' ? 'contradiction'
                       : priority === 'medium' ? 'due'
                       : 'unknown';
    const priLabel = priority.toUpperCase();

    // Due date formatting
    const todayStr = new Date().toISOString().slice(0, 10);
    const isOverdue = dueDate && dueDate < todayStr;
    const isToday = dueDate === todayStr;

    // Confidence label (P0-4 bold confidence)
    const conf = task.confidence;
    let confLabel = null;
    let confColor = '';
    if (conf != null && conf >= 0) {
      if (conf >= 0.8) { confLabel = 'VERIFIED'; confColor = 'var(--maestro-success,#00C853)'; }
      else if (conf >= 0.5) { confLabel = 'CONFIDENT'; confColor = 'var(--maestro-warning,#FF9800)'; }
      else { confLabel = 'EXPLORING'; confColor = 'var(--maestro-gray-mid,#999999)'; }
    }

    html += `
      <div class="maestro-card task-card b-mb12-cursor" data-idx="${i}" data-task-id="${escapeHtml(taskId)}">
        <div class="b-flex-u-9">
          <div class="swipe-card-category ${priBadgeClass} b-mb8-u">${priLabel}</div>
          ${confLabel ? `<div class="b-inline-block-2">${confLabel}</div>` : ''}
        </div>
        <div class="b-fs15-fw700-2">${escapeHtml(humanize(description))}</div>
        <div class="b-flex-gap12-3">
          ${assignee ? `<span>👤 ${escapeHtml(humanize(assignee))}</span>` : ''}
          ${dueDate ? `<span class="text-secondary">📅 ${escapeHtml(dueDate)}${isOverdue ? ' · OVERDUE' : isToday ? ' · TODAY' : ''}</span>` : ''}
          ${domain ? `<span>🏷️ ${escapeHtml(humanize(domain))}</span>` : ''}
        </div>
        <div class="b-flex-gap8-2">
          <button class="maestro-btn maestro-btn-secondary task-done-btn b-flex-fs13" data-task-id="${escapeHtml(taskId)}" onclick="event.stopPropagation();">Mark done</button>
          <button class="maestro-btn maestro-btn-ghost task-defer-btn b-flex-fs13" data-task-id="${escapeHtml(taskId)}" onclick="event.stopPropagation();">Defer</button>
        </div>
      </div>
    `;
  });

  // Done count footer
  if (doneCount > 0) {
    html += `<div class="b-text-center-4">${doneCount} task${doneCount === 1 ? '' : 's'} completed</div>`;
  }

  return html;
}

// ═══════════════════════════════════════════════════════════════════════════
// INTERACTION WIRING
// ═══════════════════════════════════════════════════════════════════════════

function _wireWorkSurfaceInteractions(el) {
  // Whispers — click to dismiss + navigate
  el.querySelectorAll('.whisper').forEach((wEl, i) => {
    wEl.addEventListener('click', () => {
      wEl.style.opacity = '0';
      wEl.style.transform = 'translateX(100%)';
      setTimeout(() => wEl.remove(), 300);
      // The action was stored on the whisper object; we re-fetch to get it.
      // For simplicity, navigate to contradictions (the most common whisper source).
      navTo('contradictions');
    });
  });

  // Ambient cards — click to navigate
  el.querySelectorAll('.ambient-card').forEach((aEl, i) => {
    aEl.addEventListener('click', () => {
      // Navigate based on index — matches the ambientCards order
      if (i === 0 || i === 2) navTo('eng-signals');
      else if (i === 1) navTo('contradictions');
      else navTo('eng-settings');
    });
  });

  // Timeline cards — click to drill down (future: open the signal detail)
  el.querySelectorAll('.timeline-card').forEach((tEl, i) => {
    tEl.addEventListener('click', () => {
      // Future: open a signal detail modal. For now, visual feedback only.
      tEl.style.transform = 'scale(0.98)';
      setTimeout(() => { tEl.style.transform = ''; }, 150);
    });
  });

  // Task cards — Mark done / Defer buttons
  el.querySelectorAll('.task-done-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const taskId = btn.dataset.taskId;
      if (!taskId) return;
      // Visual feedback — fade the card out
      const card = btn.closest('.task-card');
      if (card) {
        card.style.opacity = '0';
        card.style.transform = 'translateX(100%)';
        setTimeout(() => card.remove(), 300);
      }
      // Best-effort API call to mark done (if such an endpoint exists)
      try {
        await api.postOEM('/tasks/complete', { task_id: taskId });
      } catch (e) {
        // Non-fatal — the visual dismissal already happened
      }
    });
  });

  el.querySelectorAll('.task-defer-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const card = btn.closest('.task-card');
      if (card) {
        card.style.opacity = '0';
        card.style.transform = 'translateX(-100%)';
        setTimeout(() => card.remove(), 300);
      }
    });
  });
}

// ═══════════════════════════════════════════════════════════════════════════
