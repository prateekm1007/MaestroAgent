/**
 * Offscreen document — audio capture scaffold.
 *
 * Phase 1: scaffold only. NO getUserMedia calls yet.
 * Phase 2 will implement:
 *   - getUserMedia for system audio (gated by ConsentManager.checkConsent())
 *   - WebSocket streaming of audio chunks to the backend
 *   - Speaker diarization
 *
 * The ethical line: every getUserMedia call MUST be preceded by
 * ConsentManager.checkConsent(). The auditor verifies by grep:
 *   grep -rn "getUserMedia\|getDisplayMedia" extension/
 * Every match MUST be preceded by ConsentManager.checkConsent().
 *
 * In Phase 1, there are ZERO getUserMedia calls. This is intentional.
 */

console.log('Maestro: offscreen document loaded (Phase 1 scaffold — no audio capture yet)');

// Phase 2 will add:
// async function startAudioCapture() {
//   const consentManager = await import(chrome.runtime.getURL('lib/consent-manager.js'));
//   const CM = consentManager.default || consentManager;
//
//   // ETHICAL GATE: no capture without consent
//   if (!CM.checkConsent('audio')) {
//     throw new Error('Consent not granted — cannot capture audio');
//   }
//
//   const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
//   // ... stream to backend via WebSocket
// }
