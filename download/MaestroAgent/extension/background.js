/**
 * Background service worker — Maestro Live Copilot.
 *
 * Responsibilities:
 *   1. Manage the side panel lifecycle
 *   2. Maintain the WebSocket connection to the Maestro backend
 *   3. Coordinate consent state ( ConsentManager )
 *   4. Manage the offscreen document for audio capture (Phase 2)
 *   5. Route messages between content script, side panel, and backend
 *
 * Ethical line: this service worker NEVER initiates audio capture without
 * consent. The consent flow is the gate; capture is the action.
 */

// ─── State ──────────────────────────────────────────────────────────────────
let wsConnection = null;
let wsReconnectAttempts = 0;
const WS_MAX_RECONNECT = 5;
const WS_RECONNECT_DELAY_MS = 3000;

// Backend URL — configurable via chrome.storage
let BACKEND_URL = 'ws://localhost:8000/ws/copilot';

// ─── Side panel lifecycle ───────────────────────────────────────────────────
chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true })
    .catch((err) => console.error('Maestro: sidePanel setup failed:', err));
  console.log('Maestro Live Copilot: installed. Side panel ready.');
});

// ─── Message router ─────────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    case 'CONSENT_REQUEST':
      // Forward to side panel for UI display
      chrome.runtime.sendMessage({ type: 'SHOW_CONSENT_DIALOG', ...message })
        .then(sendResponse)
        .catch(() => sendResponse({ granted: false }));
      return true; // async response

    case 'CONSENT_GRANTED':
      handleConsentGranted(message.mediaType);
      sendResponse({ ok: true });
      break;

    case 'CONSENT_REVOKED':
      handleConsentRevoked(message.mediaType);
      sendResponse({ ok: true });
      break;

    case 'CONNECT_BACKEND':
      connectWebSocket()
        .then(() => sendResponse({ connected: true }))
        .catch((err) => sendResponse({ connected: false, error: err.message }));
      return true;

    case 'DISCONNECT_BACKEND':
      disconnectWebSocket();
      sendResponse({ ok: true });
      break;

    case 'MEETING_DETECTED':
      // From content.js — a meeting lobby or call was detected
      handleMeetingDetected(message, sender);
      sendResponse({ ok: true });
      break;

    case 'START_CAPTURE':
      // From side panel — user clicked "Start Copilot" after consent
      handleStartCapture(message)
        .then(sendResponse)
        .catch((err) => sendResponse({ error: err.message }));
      return true;

    case 'STOP_CAPTURE':
      handleStopCapture();
      sendResponse({ ok: true });
      break;

    case 'CHECK_CONSENT':
      // From offscreen.js — check if consent is currently granted
      sendResponse({ granted: checkConsentSync(message.mediaType) });
      break;

    case 'AUDIO_CHUNK':
      // From offscreen.js — stream audio chunk to backend
      handleAudioChunk(message.data, message.timestamp);
      sendResponse({ ok: true });
      break;

    case 'TRANSCRIPT_CHUNK':
      // From backend — forward to side panel for display
      chrome.runtime.sendMessage({ type: 'TRANSCRIPT_UPDATE', data: message.data })
        .catch(() => {});
      sendResponse({ ok: true });
      break;

    default:
      console.warn('Maestro: unknown message type:', message.type);
  }
});

// ─── Consent handlers ───────────────────────────────────────────────────────
function handleConsentGranted(mediaType) {
  console.log(`Maestro: consent GRANTED for ${mediaType}`);
  // Consent is granted — but we do NOT auto-start capture.
  // The user must explicitly click "Start Copilot" in the side panel.
  // Consent is the gate; the button press is the trigger.
}

function handleConsentRevoked(mediaType) {
  console.log(`Maestro: consent REVOKED for ${mediaType} — stopping capture immediately`);
  // Stop ALL capture immediately. This is the withdrawal path.
  handleStopCapture();
}

// ─── Capture handlers (Phase 2 implements audio) ───────────────────────────
async function handleStartCapture(message) {
  // Phase 2: create offscreen document and start audio capture
  const consentManager = await import(chrome.runtime.getURL('lib/consent-manager.js'));
  const CM = consentManager.default || consentManager;

  // ETHICAL GATE: no capture without consent
  if (!CM.checkConsent('audio')) {
    return { error: 'Consent not granted. Cannot start capture.' };
  }

  // Create the offscreen document if it doesn't exist
  const existingContexts = await chrome.runtime.getContexts({
    contextTypes: ['OFFSCREEN_DOCUMENT'],
  });

  if (existingContexts.length === 0) {
    await chrome.offscreen.createDocument({
      url: 'offscreen.html',
      reasons: ['USER_MEDIA'],
      justification: 'Meeting audio capture for real-time transcription (consent-gated)',
    });
  }

  // Tell the offscreen document to start capturing
  return new Promise((resolve) => {
    chrome.runtime.sendMessage({ type: 'START_AUDIO_CAPTURE' }, (response) => {
      if (response?.ok) {
        resolve({ ok: true, message: 'Audio capture started (consent verified)' });
      } else {
        resolve({ error: response?.error || 'Capture failed' });
      }
    });
  });
}

function handleStopCapture() {
  console.log('Maestro: stop capture');
  // Tell offscreen document to stop
  chrome.runtime.sendMessage({ type: 'STOP_AUDIO_CAPTURE' }).catch(() => {});
  if (wsConnection && wsConnection.readyState === WebSocket.OPEN) {
    wsConnection.send(JSON.stringify({ type: 'CAPTURE_STOPPED' }));
  }
}

// ─── Sync consent check (for offscreen.js) ─────────────────────────────────
function checkConsentSync(mediaType) {
  // The ConsentManager is loaded in the side panel context.
  // For offscreen to check, we use a cached state synced from the panel.
  // In Phase 2, we cache consent state here in the service worker.
  return _cachedConsent[mediaType] === true;
}

let _cachedConsent = { audio: false, screen: false };

// Sync consent state from side panel
function syncConsentState(mediaType, granted) {
  _cachedConsent[mediaType] = granted;
}

// ─── Audio chunk handler (stream to backend via WebSocket) ──────────────────
function handleAudioChunk(arrayBuffer, timestamp) {
  if (wsConnection && wsConnection.readyState === WebSocket.OPEN) {
    // Send as binary frame: [4 bytes timestamp][audio data]
    const header = new ArrayBuffer(8);
    const view = new DataView(header);
    view.setFloat64(0, timestamp);
    const combined = new Uint8Array(header.byteLength + arrayBuffer.byteLength);
    combined.set(new Uint8Array(header), 0);
    combined.set(new Uint8Array(arrayBuffer), header.byteLength);
    wsConnection.send(combined.buffer);
  }
}

// ─── Meeting detection ─────────────────────────────────────────────────────
function handleMeetingDetected(message, sender) {
  console.log('Maestro: meeting detected:', message);
  // Forward to side panel so it can show the pre-call briefing (Phase 3)
  chrome.runtime.sendMessage({
    type: 'MEETING_CONTEXT',
    platform: message.platform,
    url: message.url,
    title: message.title,
    tabId: sender.tab?.id,
  }).catch(() => {}); // side panel may not be open yet
}

// ─── WebSocket client ───────────────────────────────────────────────────────
async function connectWebSocket() {
  if (wsConnection && wsConnection.readyState === WebSocket.OPEN) {
    return; // already connected
  }

  return new Promise((resolve, reject) => {
    try {
      wsConnection = new WebSocket(BACKEND_URL);

      wsConnection.onopen = () => {
        console.log('Maestro: WebSocket connected to', BACKEND_URL);
        wsReconnectAttempts = 0;
        chrome.runtime.sendMessage({ type: 'WS_CONNECTED' }).catch(() => {});
        resolve();
      };

      wsConnection.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          // Route backend messages to the side panel
          chrome.runtime.sendMessage({ type: 'BACKEND_MESSAGE', data }).catch(() => {});
        } catch (e) {
          console.warn('Maestro: failed to parse WS message:', e);
        }
      };

      wsConnection.onerror = (err) => {
        console.error('Maestro: WebSocket error:', err);
      };

      wsConnection.onclose = () => {
        console.log('Maestro: WebSocket closed');
        chrome.runtime.sendMessage({ type: 'WS_DISCONNECTED' }).catch(() => {});
        // Auto-reconnect with backoff
        if (wsReconnectAttempts < WS_MAX_RECONNECT) {
          wsReconnectAttempts++;
          setTimeout(() => connectWebSocket().catch(() => {}), WS_RECONNECT_DELAY_MS * wsReconnectAttempts);
        }
      };
    } catch (err) {
      reject(err);
    }
  });
}

function disconnectWebSocket() {
  if (wsConnection) {
    wsConnection.close();
    wsConnection = null;
  }
}
