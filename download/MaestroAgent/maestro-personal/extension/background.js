/**
 * Background service worker — Maestro Personal Live Copilot.
 *
 * Adapted from Enterprise extension for Personal API (port 8766).
 * Changes:
 *   - Backend URL: ws://localhost:8766/ws/copilot (was 8000)
 *   - Auth: bearer token from Personal API (was Enterprise SSO)
 *   - Endpoints: /api/copilot/transcript, /api/copilot/post-call (was /ws)
 *   - Aesthetic: Bumble-inspired (honey accent, warm cream)
 *
 * Responsibilities:
 *   1. Manage the side panel lifecycle
 *   2. Maintain connection to Personal API
 *   3. Coordinate consent state
 *   4. Route transcript chunks to /api/copilot/transcript
 *   5. Generate post-call summary via /api/copilot/post-call
 */

// ─── State ──────────────────────────────────────────────────────────────────
let authToken = null;
let currentMeeting = null;
let isCapturing = false;
let transcriptChunks = [];
let meetingStartTime = null;

const API_BASE = 'http://localhost:8766';

// ─── Side panel lifecycle ───────────────────────────────────────────────────
chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true })
    .catch((err) => console.error('Maestro: sidePanel setup failed:', err));
  console.log('Maestro Personal: installed. Side panel ready.');
});

// ─── Auth ───────────────────────────────────────────────────────────────────
async function login(password = 'any') {
  const resp = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  });
  const data = await resp.json();
  authToken = data.token;
  await chrome.storage.local.set({ maestroToken: authToken });
  return authToken;
}

async function getAuthToken() {
  if (authToken) return authToken;
  const stored = await chrome.storage.local.get('maestroToken');
  authToken = stored.maestroToken;
  if (!authToken) {
    authToken = await login();
  }
  return authToken;
}

// ─── API calls ──────────────────────────────────────────────────────────────
async function apiCall(path, method = 'GET', body = null) {
  const token = await getAuthToken();
  const resp = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: body ? JSON.stringify(body) : null,
  });
  if (!resp.ok) {
    const error = await resp.text();
    throw new Error(`API error ${resp.status}: ${error}`);
  }
  return resp.json();
}

// ─── Message router ─────────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    case 'MEETING_DETECTED':
      handleMeetingDetected(message, sender);
      sendResponse({ ok: true });
      break;

    case 'START_COPILOT':
      handleStartCopilot(message)
        .then(sendResponse)
        .catch((err) => sendResponse({ error: err.message }));
      return true;

    case 'STOP_COPILOT':
      handleStopCopilot()
        .then(sendResponse)
        .catch((err) => sendResponse({ error: err.message }));
      return true;

    case 'TRANSCRIPT_CHUNK':
      handleTranscriptChunk(message)
        .then(sendResponse)
        .catch((err) => sendResponse({ error: err.message }));
      return true;

    case 'GET_BRIEFING':
      apiCall('/api/briefing')
        .then(data => sendResponse({ briefing: data }))
        .catch(err => sendResponse({ error: err.message }));
      return true;

    case 'GET_AMBIENT':
      apiCall('/api/ambient')
        .then(data => sendResponse({ ambient: data }))
        .catch(err => sendResponse({ error: err.message }));
      return true;

    case 'GET_THE_MOMENT':
      apiCall('/api/the-moment')
        .then(data => sendResponse({ moment: data }))
        .catch(err => sendResponse({ error: err.message }));
      return true;

    case 'LOGIN':
      login(message.password)
        .then(token => sendResponse({ token }))
        .catch(err => sendResponse({ error: err.message }));
      return true;

    default:
      sendResponse({ error: 'Unknown message type' });
  }
});

// ─── Meeting detection ──────────────────────────────────────────────────────
async function handleMeetingDetected(message, sender) {
  currentMeeting = message;
  console.log('Maestro: meeting detected', message.state, message.platform);

  // Fetch pre-call briefing
  if (message.state === 'lobby' || message.state === 'in-call') {
    try {
      const briefing = await apiCall('/api/briefing');
      chrome.runtime.sendMessage({
        type: 'SHOW_BRIEFING',
        briefing,
        meeting: message,
      }).catch(() => {});
    } catch (err) {
      console.debug('Pre-call briefing failed:', err);
    }
  }

  // If in-call, also fetch the-moment + ambient
  if (message.state === 'in-call') {
    try {
      const [moment, ambient] = await Promise.all([
        apiCall('/api/the-moment'),
        apiCall('/api/ambient'),
      ]);
      chrome.runtime.sendMessage({
        type: 'SHOW_INTEL',
        moment,
        ambient,
        meeting: message,
      }).catch(() => {});
    } catch (err) {
      console.debug('In-call intel failed:', err);
    }
  }
}

// ─── Start copilot (user clicked "Start Copilot") ───────────────────────────
async function handleStartCopilot(message) {
  isCapturing = true;
  meetingStartTime = Date.now();
  transcriptChunks = [];
  console.log('Maestro: copilot started for', currentMeeting?.platform);

  // Notify panel
  chrome.runtime.sendMessage({
    type: 'COPILOT_STARTED',
    meeting: currentMeeting,
  }).catch(() => {});

  return { ok: true };
}

// ─── Stop copilot (user clicked "Stop" or call ended) ───────────────────────
async function handleStopCopilot() {
  if (!isCapturing) return { ok: true };
  isCapturing = false;

  // Generate post-call summary
  try {
    // Get situation ID from current meeting
    const situations = await apiCall('/api/situations');
    const situationId = situations[0]?.situation_id || 'unknown';
    const entity = currentMeeting?.title || '';

    const summary = await apiCall('/api/copilot/post-call', 'POST', {
      situation_id: situationId,
      transcript_chunks: transcriptChunks,
      commitments: [],
      entity: entity,
    });

    chrome.runtime.sendMessage({
      type: 'SHOW_POST_CALL',
      summary,
    }).catch(() => {});
  } catch (err) {
    console.debug('Post-call summary failed:', err);
  }

  return { ok: true };
}

// ─── Process transcript chunk ───────────────────────────────────────────────
async function handleTranscriptChunk(message) {
  if (!isCapturing) return { ok: false, error: 'Not capturing' };

  const chunk = {
    speaker: message.speaker || 'unknown',
    text: message.text,
    timestamp: new Date().toISOString(),
  };
  transcriptChunks.push(chunk);

  // Send to Personal API for real-time processing
  try {
    const situations = await apiCall('/api/situations');
    const situationId = situations[0]?.situation_id || 'unknown';
    const entity = currentMeeting?.title || '';

    const result = await apiCall('/api/copilot/transcript', 'POST', {
      situation_id: situationId,
      text: message.text,
      speaker: message.speaker,
      entity: entity,
    });

    // Forward any real-time suggestions to the panel
    if (result && (result.transitions?.length > 0 || result.commitments_detected?.length > 0)) {
      chrome.runtime.sendMessage({
        type: 'SHOW_SUGGESTION',
        suggestion: result,
        chunk,
      }).catch(() => {});
    }

    return { ok: true, result };
  } catch (err) {
    console.debug('Transcript processing failed:', err);
    return { ok: false, error: err.message };
  }
}
