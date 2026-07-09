/**
 * Panel script — Maestro Personal Live Copilot side panel.
 *
 * Adapted for Personal API (port 8766) + Bumble aesthetic.
 * Shows: the-moment, pre-call briefing, live suggestions, ambient, post-call.
 */

// ─── State ──────────────────────────────────────────────────────────────────
let currentView = 'momentView';
let copilotActive = false;
let timerInterval = null;

// ─── View management ────────────────────────────────────────────────────────
function showView(viewId) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  const view = document.getElementById(viewId);
  if (view) {
    view.classList.add('active');
    currentView = viewId;
  }
}

// ─── Connection status ──────────────────────────────────────────────────────
function setStatus(text, connected) {
  document.getElementById('statusText').textContent = text;
  const dot = document.getElementById('statusDot');
  dot.className = 'status-dot ' + (connected ? 'connected' : 'disconnected');
}

// ─── Login on load ──────────────────────────────────────────────────────────
chrome.runtime.sendMessage({ type: 'LOGIN', password: 'any' }, (response) => {
  if (response?.token) {
    setStatus('Connected', true);
    loadMoment();
    loadAmbient();
  } else {
    setStatus('Disconnected', false);
  }
});

// ─── Load the moment ────────────────────────────────────────────────────────
function loadMoment() {
  chrome.runtime.sendMessage({ type: 'GET_THE_MOMENT' }, (response) => {
    if (response?.moment) {
      const m = response.moment;
      if (m.has_moment && m.commitment) {
        document.getElementById('momentEntity').textContent = m.commitment.entity;
        document.getElementById('momentText').textContent = m.commitment.text;
        document.getElementById('momentWhy').textContent = m.why_this_one || '';
        if (m.source_evidence?.length > 0) {
          document.getElementById('momentSource').textContent =
            `Source: "${m.source_evidence[0].text}" via ${m.source_evidence[0].source}`;
        }
        document.getElementById('momentCard').classList.remove('hidden');
        document.getElementById('momentSilence').classList.add('hidden');
      } else {
        document.getElementById('momentCard').classList.add('hidden');
        document.getElementById('momentSilence').classList.remove('hidden');
      }
    }
  });
}

// ─── Load ambient ───────────────────────────────────────────────────────────
function loadAmbient() {
  chrome.runtime.sendMessage({ type: 'GET_AMBIENT' }, (response) => {
    if (response?.ambient) {
      const a = response.ambient;
      document.getElementById('ambientSummary').textContent = a.ambient_summary || 'Nothing urgent right now.';

      const alertsDiv = document.getElementById('ambientAlerts');
      alertsDiv.innerHTML = '';

      // Sentiment alerts
      (a.sentiment_alerts || []).forEach(alert => {
        const div = document.createElement('div');
        div.className = 'alert';
        div.innerHTML = `
          <div class="alert-type ${alert.type}">${alert.type}</div>
          <div>${alert.entity}: "${alert.text}"</div>
        `;
        alertsDiv.appendChild(div);
      });

      // Stale commitments
      (a.stale_commitments || []).forEach(comm => {
        const div = document.createElement('div');
        div.className = 'alert';
        div.innerHTML = `
          <div class="alert-type stale">STALE COMMITMENT</div>
          <div>${comm.entity}: ${comm.days_stale} days overdue</div>
        `;
        alertsDiv.appendChild(div);
      });
    }
  });
}

// ─── Message handler ────────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    case 'SHOW_BRIEFING':
      showBriefing(message.briefing, message.meeting);
      break;

    case 'SHOW_INTEL':
      // Update moment + ambient in background
      loadMoment();
      loadAmbient();
      break;

    case 'COPILOT_STARTED':
      copilotActive = true;
      showView('liveView');
      startTimer();
      document.getElementById('startBtn').classList.add('hidden');
      document.getElementById('stopBtn').classList.remove('hidden');
      break;

    case 'SHOW_SUGGESTION':
      showSuggestion(message.suggestion, message.chunk);
      break;

    case 'SHOW_POST_CALL':
      showPostCall(message.summary);
      break;
  }
  sendResponse({ ok: true });
});

// ─── Show briefing ──────────────────────────────────────────────────────────
function showBriefing(briefing, meeting) {
  if (!briefing) return;

  showView('briefingView');

  document.getElementById('briefingGreeting').textContent = briefing.greeting || '';

  const topDiv = document.getElementById('briefingTopSituation');
  if (briefing.top_situation) {
    topDiv.innerHTML = `
      <h4>THE ONE THING</h4>
      <div>${briefing.top_situation.entity || ''}: ${briefing.top_situation.title || ''}</div>
    `;
  }

  const changesDiv = document.getElementById('briefingChanges');
  if (briefing.material_changes?.length > 0) {
    changesDiv.innerHTML = `
      <h4>WHAT CHANGED</h4>
      <ul>${briefing.material_changes.map(c => `<li>${c}</li>`).join('')}</ul>
    `;
  }

  const unknownsDiv = document.getElementById('briefingUnknowns');
  if (briefing.unknowns?.length > 0) {
    unknownsDiv.innerHTML = `
      <h4>WHAT'S UNKNOWN</h4>
      <ul>${briefing.unknowns.map(u => `<li>${u}</li>`).join('')}</ul>
    `;
  }

  document.getElementById('briefingAsk').textContent = briefing.ask_prompt || 'What do you want to understand?';
}

// ─── Show suggestion (live) ─────────────────────────────────────────────────
function showSuggestion(suggestion, chunk) {
  const cardsDiv = document.getElementById('suggestionCards');

  // Add transcript line
  const transcriptDiv = document.getElementById('transcript');
  const line = document.createElement('div');
  line.className = 'transcript-line';
  line.innerHTML = `<span class="speaker">${chunk.speaker}:</span> ${chunk.text}`;
  transcriptDiv.appendChild(line);
  transcriptDiv.scrollTop = transcriptDiv.scrollHeight;

  // Show suggestion if there's something to say
  if (suggestion.transitions?.length > 0) {
    const card = document.createElement('div');
    card.className = 'suggestion-card';
    card.textContent = suggestion.transitions.map(t =>
      typeof t === 'string' ? t : JSON.stringify(t)
    ).join('; ');
    cardsDiv.appendChild(card);
  }

  if (suggestion.commitments_detected?.length > 0) {
    const card = document.createElement('div');
    card.className = 'suggestion-card';
    card.style.background = 'var(--purple-light)';
    card.style.color = 'var(--purple)';
    card.textContent = `New commitment: ${suggestion.commitments_detected.join(', ')}`;
    cardsDiv.appendChild(card);
  }
}

// ─── Show post-call ─────────────────────────────────────────────────────────
function showPostCall(summary) {
  showView('postCallView');
  const content = document.getElementById('summaryContent');

  let html = '';

  if (summary.commitments_ingested?.length > 0) {
    html += `<div class="briefing-section"><h4>COMMITMENTS TRACKED</h4><ul>`;
    summary.commitments_ingested.forEach(c => html += `<li>${c}</li>`);
    html += `</ul></div>`;
  }

  if (summary.learning_triggered) {
    html += `<div class="briefing-section"><h4>LEARNING TRIGGERED</h4><p>BehavioralLearningEngine updated.</p></div>`;
  }

  if (summary.follow_up_draft) {
    html += `<div class="briefing-section"><h4>DRAFT FOLLOW-UP</h4><p>${summary.follow_up_draft}</p></div>`;
  }

  if (!html) {
    html = '<p>No summary generated.</p>';
  }

  content.innerHTML = html;
}

// ─── Timer ──────────────────────────────────────────────────────────────────
function startTimer() {
  const start = Date.now();
  timerInterval = setInterval(() => {
    const elapsed = Math.floor((Date.now() - start) / 1000);
    const mins = String(Math.floor(elapsed / 60)).padStart(2, '0');
    const secs = String(elapsed % 60).padStart(2, '0');
    document.getElementById('liveTimer').textContent = `${mins}:${secs}`;
  }, 1000);
}

function stopTimer() {
  if (timerInterval) {
    clearInterval(timerInterval);
    timerInterval = null;
  }
}

// ─── Button handlers ────────────────────────────────────────────────────────
document.getElementById('startBtn').addEventListener('click', () => {
  chrome.runtime.sendMessage({ type: 'START_COPILOT' }, (response) => {
    if (response?.error) {
      console.error('Start failed:', response.error);
    }
  });
});

document.getElementById('stopBtn').addEventListener('click', () => {
  chrome.runtime.sendMessage({ type: 'STOP_COPILOT' }, (response) => {
    copilotActive = false;
    stopTimer();
    document.getElementById('stopBtn').classList.add('hidden');
    document.getElementById('startBtn').classList.remove('hidden');
  });
});

// ─── Consent ────────────────────────────────────────────────────────────────
document.getElementById('consentAllow')?.addEventListener('click', () => {
  document.getElementById('consentDialog').classList.add('hidden');
  document.getElementById('startBtn').disabled = false;
});

document.getElementById('consentDeny')?.addEventListener('click', () => {
  document.getElementById('consentDialog').classList.add('hidden');
});

// ─── Refresh moment every 30 seconds ────────────────────────────────────────
setInterval(() => {
  if (!copilotActive) {
    loadMoment();
  }
}, 30000);

// Initial load
loadMoment();
loadAmbient();
