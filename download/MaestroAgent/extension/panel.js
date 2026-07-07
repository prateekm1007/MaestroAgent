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
  }
});

// ─── Meeting context display (Phase 3 will fully populate) ──────────────────
function showMeetingContext(message) {
  defaultState.classList.add('hidden');
  meetingContext.classList.remove('hidden');
  document.getElementById('meetingTitle').textContent = message.title || 'Meeting detected';
  startBtn.disabled = false;
}

// ─── Backend message handler (Phases 4-5 will fully implement) ─────────────
function handleBackendMessage(data) {
  // Phase 4: live suggestions, transcript chunks
  // Phase 5: post-call summary
  console.log('Maestro: backend message:', data);
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
