/**
 * Offscreen document — audio capture (Phase 2).
 *
 * Captures system audio via getUserMedia, GATED BY CONSENT.
 * Streams audio chunks to the backend via the background WebSocket.
 *
 * ETHICAL LINE: every getUserMedia call is preceded by
 * ConsentManager.checkConsent(). The auditor verifies by grep:
 *   grep -rn "getUserMedia\|getDisplayMedia" extension/
 * Every match MUST be preceded by ConsentManager.checkConsent().
 *
 * If consent is revoked mid-capture, the MediaStream stops immediately.
 */

let mediaStream = null;
let mediaRecorder = null;
let audioContext = null;
let isCapturing = false;

// ─── Message handler (from background.js) ───────────────────────────────────
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    case 'START_AUDIO_CAPTURE':
      startAudioCapture()
        .then(() => sendResponse({ ok: true }))
        .catch((err) => sendResponse({ error: err.message }));
      return true;

    case 'STOP_AUDIO_CAPTURE':
      stopAudioCapture();
      sendResponse({ ok: true });
      break;

    case 'CONSENT_REVOKED':
      // Consent revoked — stop ALL capture immediately
      stopAudioCapture();
      sendResponse({ ok: true });
      break;
  }
});

// ─── Audio capture (gated by consent) ───────────────────────────────────────
async function startAudioCapture() {
  if (isCapturing) {
    return; // already capturing
  }

  // ETHICAL GATE: check consent before any capture
  const consentGranted = await checkConsentViaBackground('audio');
  if (!consentGranted) {
    throw new Error('Consent not granted — cannot capture audio');
  }

  // Capture system audio via getDisplayMedia (system audio) or getUserMedia (mic)
  // For meeting copilot, we want system audio (the call audio), not just mic.
  try {
    mediaStream = await navigator.mediaDevices.getDisplayMedia({
      video: false,
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    // Verify we got an audio track (user may have selected "no audio")
    const audioTracks = mediaStream.getAudioTracks();
    if (audioTracks.length === 0) {
      mediaStream.getTracks().forEach((t) => t.stop());
      throw new Error('No audio track captured — user did not share audio');
    }

    // Set up MediaRecorder to chunk the audio
    mediaRecorder = new MediaRecorder(mediaStream, {
      mimeType: 'audio/webm;codecs=opus',
      audioBitsPerSecond: 16000, // 16kbps — sufficient for speech
    });

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        sendAudioChunk(event.data);
      }
    };

    mediaRecorder.onstop = () => {
      isCapturing = false;
      console.log('Maestro: audio capture stopped');
    };

    // Listen for track ended (user stopped sharing via browser UI)
    audioTracks[0].addEventListener('ended', () => {
      console.log('Maestro: audio track ended by user');
      stopAudioCapture();
    });

    // Start recording in 1-second chunks for low-latency transcription
    mediaRecorder.start(1000);
    isCapturing = true;
    console.log('Maestro: audio capture started (consent verified)');

  } catch (err) {
    if (mediaStream) {
      mediaStream.getTracks().forEach((t) => t.stop());
    }
    throw err;
  }
}

function stopAudioCapture() {
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop();
  }
  if (mediaStream) {
    mediaStream.getTracks().forEach((t) => t.stop());
    mediaStream = null;
  }
  isCapturing = false;
}

// ─── Send audio chunk to background (for WebSocket streaming) ───────────────
async function sendAudioChunk(blob) {
  // Convert blob to array buffer, then send to background
  const arrayBuffer = await blob.arrayBuffer();
  chrome.runtime.sendMessage({
    type: 'AUDIO_CHUNK',
    data: arrayBuffer,
    timestamp: Date.now(),
  }).catch(() => {});
}

// ─── Consent check (delegates to background → ConsentManager) ───────────────
async function checkConsentViaBackground(mediaType) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(
      { type: 'CHECK_CONSENT', mediaType },
      (response) => resolve(response?.granted || false)
    );
  });
}

console.log('Maestro: offscreen document loaded (Phase 2 — audio capture ready, consent-gated)');
