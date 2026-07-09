/**
 * Content script — meeting platform detection.
 *
 * Runs on Google Meet, Zoom, and Teams pages. Detects:
 *   - Meeting lobby (pre-join state) → triggers pre-call briefing (Phase 3)
 *   - Active call → signals the background to prepare live mode (Phase 4)
 *   - Call ended → signals the background to generate summary (Phase 5)
 *
 * Privacy: this script only reads page metadata (URL, title, visible DOM
 * elements). It does NOT capture audio, video, or screen content. All
 * capture requires explicit consent via ConsentManager.
 */

// ─── Platform detection ─────────────────────────────────────────────────────
function detectPlatform() {
  const url = window.location.href;
  if (url.includes('meet.google.com')) return 'google-meet';
  if (url.includes('zoom.us')) return 'zoom';
  if (url.includes('teams.microsoft.com')) return 'teams';
  return null;
}

// ─── Meeting state detection ────────────────────────────────────────────────
function detectMeetingState() {
  const platform = detectPlatform();
  if (!platform) return null;

  const url = window.location.href;
  const title = document.title;

  // Lobby / pre-join detection (platform-specific heuristics)
  let state = 'unknown';
  if (platform === 'google-meet') {
    if (url.includes('meet.google.com/') && !url.includes('new')) {
      // Check for the "Join now" button which appears in the lobby
      const joinButton = document.querySelector('[jsname="Qx7uuf"]') ||
                        document.querySelector('button[data-meeting-type]');
      const inCall = document.querySelector('[data-meeting-title]') ||
                    document.querySelector('div[role="main"] canvas');
      if (joinButton) state = 'lobby';
      else if (inCall) state = 'in-call';
    }
  } else if (platform === 'zoom') {
    if (url.includes('/wc/')) state = 'in-call';
    else if (url.includes('/j/')) state = 'lobby';
  } else if (platform === 'teams') {
    if (document.querySelector('[data-tid="call-screen"]')) state = 'in-call';
    else if (document.querySelector('[data-tid="pre-join-screen"]')) state = 'lobby';
  }

  return { platform, url, title, state, detectedAt: new Date().toISOString() };
}

// ─── Notify background script ───────────────────────────────────────────────
function notifyBackground() {
  const meetingInfo = detectMeetingState();
  if (!meetingInfo || meetingInfo.state === 'unknown') return;

  chrome.runtime.sendMessage({
    type: 'MEETING_DETECTED',
    ...meetingInfo,
  }).catch(() => {});
}

// ─── Mutation observer (detect state transitions) ───────────────────────────
let lastState = null;
const observer = new MutationObserver(() => {
  const meetingInfo = detectMeetingState();
  if (meetingInfo && meetingInfo.state !== lastState) {
    lastState = meetingInfo.state;
    notifyBackground();
  }
});

// Start observing once the page is ready
if (document.readyState === 'complete' || document.readyState === 'interactive') {
  setTimeout(notifyBackground, 1000); // initial detection after 1s
} else {
  document.addEventListener('DOMContentLoaded', () => {
    setTimeout(notifyBackground, 1000);
  });
}

// Observe body for state changes (lobby → in-call → ended)
observer.observe(document.body, { childList: true, subtree: true });

console.log('Maestro Live Copilot: content script loaded on', detectPlatform());
