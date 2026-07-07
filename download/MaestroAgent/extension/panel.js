/**
 * Side panel controller — Maestro Live Copilot.
 *
 * Manages:
 *   - Connection status display
 *   - Consent dialog UI (show/hide on ConsentManager requests)
 *   - Start/Stop button state
 *   - Meeting context display (Phase 3)
 *   - Live feed display (Phase 4)
 *   - Post-call summary display (Phase 5)
 */

// ─── DOM elements ───────────────────────────────────────────────────────────
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const revokeBtn = document.getElementById('revokeBtn');
const consentDialog = document.getElementById('consentDialog');
const consentMessage = document.getElementById('consentMessage');
const consentAllow = document.getElementById('consentAllow');
const consentDeny = document.getElementById('consentDeny');
const defaultState = document.getElementById('defaultState');
const meetingContext = document.getElementById('meetingContext');
const liveFeed = document.getElementById('liveFeed');
const postCallSummary = document.getElementById('postCallSummary');

// ─── Connection status ──────────────────────────────────────────────────────
function setConnectionStatus(connected) {
  if (connected) {
    statusDot.classList.add('connected');
    statusDot.classList.remove('disconnected');
    statusText.textContent = 'Connected';
  } else {
    statusDot.classList.remove('connected');
    statusText.textContent = 'Ready';
  }
}

// ─── Consent dialog ─────────────────────────────────────────────────────────
function showConsentDialog(mediaType, message) {
  consentMessage.textContent = message;
  consentDialog.classList.remove('hidden');

  return new Promise((resolve) => {
    const onAllow = () => {
      cleanup();
      resolve({ granted: true });
    };
    const onDeny = () => {
      cleanup();
      resolve({ granted: false });
    };
    const cleanup = () => {
      consentDialog.classList.add('hidden');
      consentAllow.removeEventListener('click', onAllow);
      consentDeny.removeEventListener('click', onDeny);
    };
    consentAllow.addEventListener('click', onAllow);
    consentDeny.addEventListener('click', onDeny);
  });
}

// ─── Message listener ───────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    case 'SHOW_CONSENT_DIALOG':
      showConsentDialog(message.mediaType, message.message)
        .then(sendResponse);
      return true; // async

    case 'WS_CONNECTED':
      setConnectionStatus(true);
      break;

    case 'WS_DISCONNECTED':
      setConnectionStatus(false);
      break;

    case 'MEETING_CONTEXT':
      showMeetingContext(message);
      break;

    case 'BACKEND_MESSAGE':
      handleBackendMessage(message.data);
      break;

    case 'TRANSCRIPT_UPDATE':
      // Phase 2: display transcript chunks in the live feed
      appendTranscriptChunk(message.data);
      break;
  }
});

// ─── Meeting context display (Phase 3: pre-call briefing) ──────────────────
async function showMeetingContext(message) {
  defaultState.classList.add('hidden');
  meetingContext.classList.remove('hidden');
  document.getElementById('meetingTitle').textContent = message.title || 'Meeting detected';
  startBtn.disabled = false;

  // Phase 3: fetch pre-call briefing from the backend
  await fetchPreCallBriefing(message);
}

// ─── Fetch pre-call briefing (Phase 3) ──────────────────────────────────────
async function fetchPreCallBriefing(meetingInfo) {
  try {
    const response = await fetch('http://localhost:8000/api/copilot/pre-call', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        meeting_title: meetingInfo.title || '',
        meeting_url: meetingInfo.url || '',
        platform: meetingInfo.platform || '',
        attendees: meetingInfo.attendees || [],
        user_email: '',  // Phase 3.5: get from auth context
      }),
    });

    if (!response.ok) {
      console.warn('Maestro: pre-call briefing failed:', response.status);
      return;
    }

    const briefing = await response.json();
    renderPreCallBriefing(briefing);
  } catch (err) {
    console.warn('Maestro: pre-call briefing error:', err);
  }
}

// ─── Render pre-call briefing (Phase 3) ─────────────────────────────────────
function renderPreCallBriefing(briefing) {
  const attendeeList = document.getElementById('attendeeList');
  attendeeList.innerHTML = '';

  // Meeting context card
  const ctx = briefing.meeting_context || {};
  const ctxCard = document.createElement('div');
  ctxCard.className = 'suggestion-card tracked';
  ctxCard.innerHTML = `
    <div class="card-title">Meeting Context</div>
    <div class="card-body">
      ${ctx.entity ? `<div>Entity: <strong>${ctx.entity}</strong></div>` : ''}
      ${ctx.relationship_health ? `<div>Health: <strong>${ctx.relationship_health}</strong></div>` : ''}
      ${ctx.open_commitments !== undefined ? `<div>Open commitments: <strong>${ctx.open_commitments}</strong></div>` : ''}
    </div>
  `;
  attendeeList.appendChild(ctxCard);

  // Attendee intelligence
  for (const attendee of (briefing.attendee_intelligence || [])) {
    const card = document.createElement('div');
    card.className = 'suggestion-card whisper';
    const name = attendee.email.split('@')[0];
    card.innerHTML = `
      <div class="card-title">${name}</div>
      <div class="card-body">
        <div>${attendee.interaction_count} interactions in organizational memory</div>
        ${attendee.last_interaction_days_ago !== null
          ? `<div>Last interaction: ${attendee.last_interaction_days_ago} days ago</div>`
          : ''}
        ${attendee.commitment_count > 0
          ? `<div>${attendee.commitment_count} commitments tracked</div>`
          : ''}
      </div>
    `;
    attendeeList.appendChild(card);
  }

  // Suggested talking points
  for (const point of (briefing.suggested_talking_points || [])) {
    const card = document.createElement('div');
    card.className = 'suggestion-card pattern';
    card.innerHTML = `
      <div class="card-title">Talking Point (${point.priority})</div>
      <div class="card-body">${point.text}</div>
      <div class="card-evidence">Evidence: ${point.evidence.source}</div>
    `;
    attendeeList.appendChild(card);
  }

  // Risks
  for (const risk of (briefing.risks_to_address || [])) {
    const card = document.createElement('div');
    card.className = 'suggestion-card objection';
    card.innerHTML = `
      <div class="card-title">Risk: ${risk.type} (${risk.severity})</div>
      <div class="card-body">${risk.text}</div>
    `;
    attendeeList.appendChild(card);
  }
}

// ─── Backend message handler (Phase 4: live suggestions) ──────────────────
function handleBackendMessage(data) {
  if (!data) return;

  switch (data.type) {
    case 'SUGGESTION':
      renderSuggestionCard(data.card);
      break;

    case 'TRANSCRIPT_CHUNK':
      appendTranscriptChunk(data);
      break;

    case 'SESSION_STARTED':
      console.log('Maestro: session started:', data.session_id);
      break;

    case 'AUDIO_RECEIVED':
      // Heartbeat — no action needed
      break;

    default:
      console.log('Maestro: backend message:', data);
  }
}

// ─── Suggestion card rendering (Phase 4: Scene 2 live) ─────────────────────
function renderSuggestionCard(card) {
  if (!card) return;

  const container = document.getElementById('suggestionCards');
  if (!container) return;

  const cardEl = document.createElement('div');
  cardEl.className = `suggestion-card ${card.card_type}`;
  if (card.is_new) {
    cardEl.classList.add('new');
    // Remove 'new' class after 5s (glow effect fades)
    setTimeout(() => cardEl.classList.remove('new'), 5000);
  }
  cardEl.setAttribute('role', 'alert');
  cardEl.setAttribute('aria-live', 'polite');

  // Color-coded left border (per spec)
  cardEl.style.borderLeftColor = card.color || '';

  cardEl.innerHTML = `
    <div class="card-title">${card.title}</div>
    <div class="card-body">${card.text}</div>
    <div class="card-confidence">
      <div class="confidence-label">${card.confidence_label}</div>
      <div class="confidence-bar">
        <div class="confidence-fill" style="width: ${card.confidence * 100}%; background: ${card.color};"></div>
      </div>
    </div>
    <div class="card-evidence">
      <a href="#" class="evidence-link" data-evidence='${JSON.stringify(card.evidence)}'>View evidence →</a>
    </div>
    <div class="card-actions">
      ${card.actions.map(a => `<button class="btn btn-small" data-action="${a}">${a}</button>`).join('')}
    </div>
  `;

  // Wire action buttons
  cardEl.querySelectorAll('button[data-action]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      handleCardAction(card.card_type, btn.dataset.action, card);
      cardEl.remove();
    });
  });

  // Wire evidence link
  const evidenceLink = cardEl.querySelector('.evidence-link');
  if (evidenceLink) {
    evidenceLink.addEventListener('click', (e) => {
      e.preventDefault();
      showEvidence(card.evidence);
    });
  }

  container.appendChild(cardEl);

  // Keep only last 5 cards
  const cards = container.querySelectorAll('.suggestion-card');
  if (cards.length > 5) {
    cards[0].remove();
  }
}

function handleCardAction(cardType, action, card) {
  console.log(`Maestro: action ${action} on ${cardType} card`);
  // Phase 4: send the action to the backend for logging
  chrome.runtime.sendMessage({
    type: 'CARD_ACTION',
    card_type: cardType,
    action: action,
    evidence: card.evidence,
  }).catch(() => {});
}

function showEvidence(evidence) {
  // Phase 4: display the evidence chain in a modal or expanded view
  console.log('Maestro: evidence:', evidence);
  alert(`Evidence chain:\n${JSON.stringify(evidence, null, 2)}`);
}

// ─── Transcript display (Phase 2) ───────────────────────────────────────────
function appendTranscriptChunk(chunk) {
  const transcriptEl = document.getElementById('transcript');
  if (!chunk || !chunk.text) return;

  const chunkEl = document.createElement('div');
  chunkEl.className = 'transcript-chunk';

  const speakerEl = document.createElement('span');
  speakerEl.className = 'transcript-speaker';
  speakerEl.textContent = (chunk.speaker || 'Unknown') + ': ';

  const textEl = document.createElement('span');
  // Highlight trigger words if present
  if (chunk.trigger_words && chunk.trigger_words.length > 0) {
    let text = chunk.text;
    chunk.trigger_words.forEach((word) => {
      const escaped = word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      text = text.replace(new RegExp(escaped, 'gi'), (match) =>
        `<span class="transcript-trigger">${match}</span>`
      );
    });
    textEl.innerHTML = text;
  } else {
    textEl.textContent = chunk.text;
  }

  chunkEl.appendChild(speakerEl);
  chunkEl.appendChild(textEl);
  transcriptEl.appendChild(chunkEl);

  // Keep only last 3 chunks visible (per spec)
  const chunks = transcriptEl.querySelectorAll('.transcript-chunk');
  if (chunks.length > 3) {
    chunks[0].remove();
  }

  // Auto-scroll
  transcriptEl.scrollTop = transcriptEl.scrollHeight;
}

// ─── Sync consent state to background (so offscreen can check) ─────────────
function syncConsentToBackground(mediaType, granted) {
  chrome.runtime.sendMessage({
    type: 'CONSENT_GRANTED',  // reuse existing handler
    mediaType: mediaType,
    granted: granted,
  }).catch(() => {});
  // Also update the background's cached state
  if (chrome.runtime.sendMessage) {
    chrome.runtime.sendMessage({
      type: 'SYNC_CONSENT',
      mediaType: mediaType,
      granted: granted,
    }).catch(() => {});
  }
}

// ─── Button handlers ────────────────────────────────────────────────────────
startBtn.addEventListener('click', async () => {
  // Phase 1: scaffold. Phase 2+ will implement full capture.
  // Request consent first — this is the ethical gate.
  const granted = await ConsentManager.requestConsent('audio');
  if (!granted) {
    return; // consent denied — no capture
  }

  // Connect to backend
  chrome.runtime.sendMessage({ type: 'CONNECT_BACKEND' }, (response) => {
    if (response?.connected) {
      // Start capture (Phase 2 implements audio; Phase 1 just logs)
      chrome.runtime.sendMessage({ type: 'START_CAPTURE' }, (capResponse) => {
        if (capResponse?.ok) {
          startBtn.classList.add('hidden');
          stopBtn.classList.remove('hidden');
          revokeBtn.classList.remove('hidden');
          liveFeed.classList.remove('hidden');
        }
      });
    }
  });
});

stopBtn.addEventListener('click', () => {
  chrome.runtime.sendMessage({ type: 'STOP_CAPTURE' });
  chrome.runtime.sendMessage({ type: 'DISCONNECT_BACKEND' });
  stopBtn.classList.add('hidden');
  revokeBtn.classList.add('hidden');
  startBtn.classList.remove('hidden');
  liveFeed.classList.add('hidden');
});

revokeBtn.addEventListener('click', () => {
  // Revoke consent — capture stops immediately (the withdrawal path)
  ConsentManager.revokeConsent('audio');
  // The background script will handle stopping capture
  stopBtn.classList.add('hidden');
  revokeBtn.classList.add('hidden');
  startBtn.classList.remove('hidden');
  liveFeed.classList.add('hidden');
});

// ─── Initialize ─────────────────────────────────────────────────────────────
setConnectionStatus(false);
console.log('Maestro Live Copilot: panel loaded');
