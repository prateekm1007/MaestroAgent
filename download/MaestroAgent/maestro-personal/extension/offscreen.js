/**
 * Offscreen document — audio capture + in-browser transcription (Phase 2).
 *
 * Captures system audio via getDisplayMedia, GATED BY CONSENT.
 * Transcribes audio IN THE BROWSER using WhisperTranscriber (Transformers.js).
 * Only text transcript is sent to the backend — audio NEVER leaves the device.
 *
 * ETHICAL LINE: every getDisplayMedia call is preceded by
 * ConsentManager.checkConsent(). Audio is transcribed locally via WASM.
 * Only JSON transcript text is sent to the backend.
 */

let mediaStream = null;
let mediaRecorder = null;
let audioContext = null;
let isCapturing = false;
let transcriber = null;
let streamController = null;

// ─── Initialize Whisper transcriber (lazy load) ─────────────────────────────
async function getTranscriber() {
  if (!transcriber) {
    const module = await import(chrome.runtime.getURL("lib/whisper-transcriber.js"));
    const WhisperTranscriber = module.default || module.WhisperTranscriber || module;
    transcriber = new WhisperTranscriber("Xenova/whisper-tiny.en");
  }
  return transcriber;
}

// ─── Message handler (from background.js) ───────────────────────────────────
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    case "START_AUDIO_CAPTURE":
      startAudioCapture()
        .then(() => sendResponse({ ok: true }))
        .catch((err) => sendResponse({ error: err.message }));
      return true;

    case "STOP_AUDIO_CAPTURE":
      stopAudioCapture();
      sendResponse({ ok: true });
      break;

    case "CONSENT_REVOKED":
      stopAudioCapture();
      sendResponse({ ok: true });
      break;

    case "GET_TRANSCRIBER_STATUS":
      if (transcriber) {
        sendResponse(transcriber.getStatus());
      } else {
        sendResponse({ isLoaded: false, isLoading: false });
      }
      break;
  }
});

// ─── Audio capture + transcription (gated by consent) ───────────────────────
async function startAudioCapture() {
  if (isCapturing) return;

  // ETHICAL GATE: check consent before any capture
  const consentGranted = await checkConsentViaBackground("audio");
  if (!consentGranted) {
    throw new Error("Consent not granted — cannot capture audio");
  }

  try {
    mediaStream = await navigator.mediaDevices.getDisplayMedia({
      video: false,
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    const audioTracks = mediaStream.getAudioTracks();
    if (audioTracks.length === 0) {
      mediaStream.getTracks().forEach((t) => t.stop());
      throw new Error("No audio track captured — user did not share audio");
    }

    audioTracks[0].addEventListener("ended", () => {
      console.log("Maestro: audio track ended by user");
      stopAudioCapture();
    });

    // Initialize the Whisper transcriber (local WASM model)
    const whisper = await getTranscriber();
    await whisper.load();

    // Start streaming transcription — audio processed LOCALLY
    streamController = await whisper.transcribeStream(
      mediaStream,
      (transcript) => {
        // Send ONLY text transcript to background (NOT audio)
        chrome.runtime.sendMessage({
          type: "TRANSCRIPT_CHUNK",
          text: transcript.text,
          isFinal: transcript.isFinal,
          chunkIndex: transcript.chunkIndex,
          timestamp: transcript.timestamp,
        }).catch(() => {});
      },
      { chunkDurationMs: 3000 }
    );

    isCapturing = true;
    console.log("Maestro: audio capture + local Whisper transcription started (audio never leaves device)");

  } catch (err) {
    if (mediaStream) {
      mediaStream.getTracks().forEach((t) => t.stop());
    }
    throw err;
  }
}

function stopAudioCapture() {
  if (streamController) {
    streamController.stop();
    streamController = null;
  }
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
  }
  if (mediaStream) {
    mediaStream.getTracks().forEach((t) => t.stop());
    mediaStream = null;
  }
  isCapturing = false;
}

// ─── Consent check (delegates to background → ConsentManager) ───────────────
async function checkConsentViaBackground(mediaType) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(
      { type: "CHECK_CONSENT", mediaType },
      (response) => resolve(response?.granted || false)
    );
  });
}

console.log("Maestro: offscreen document loaded (Phase 2 — audio capture + local Whisper transcription)");
