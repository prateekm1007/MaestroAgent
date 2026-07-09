# Maestro Personal — Browser Extension

Real-time meeting intelligence with evidence, calibration, and trusted silence.

## What it does

When you join a Google Meet, Zoom, or Teams call, the Maestro side panel opens and shows:
- **Pre-call briefing**: the one thing that needs your judgment, what changed, what's unknown
- **Live suggestions**: real-time commitment detection + state transitions during the call
- **Post-call summary**: commitments tracked, learning triggered, draft follow-up

## Install (developer mode)

1. Open Chrome → `chrome://extensions`
2. Enable "Developer mode" (top right)
3. Click "Load unpacked" → select this `extension/` folder
4. The Maestro icon appears in your toolbar
5. Click it to open the side panel

## Start the API server first

```bash
cd maestro-personal/src/maestro_personal_shell
python api.py
# Starts on http://localhost:8766
```

## Use

1. Start the API server (above)
2. Open the side panel (click the Maestro icon)
3. Navigate to a Google Meet / Zoom / Teams meeting
4. The panel shows pre-call briefing automatically
5. Click "Start Copilot" to begin real-time transcript processing
6. Speak naturally — transcript chunks are sent to `/api/copilot/transcript`
7. Click "Stop" when the call ends — post-call summary generates

## Files

| File | Purpose |
|------|---------|
| `manifest.json` | Manifest V3, sidePanel, Meet/Zoom/Teams permissions |
| `background.js` | Service worker: auth, API calls, transcript routing, post-call |
| `content.js` | Meeting platform detection (lobby → in-call → ended) |
| `panel.html` | Side panel UI (moment, briefing, live, ambient, post-call) |
| `panel.css` | Bumble-inspired: warm cream + honey + purple |
| `panel.js` | Panel logic: views, suggestions, transcript, timer |
| `lib/consent-manager.js` | Consent flow (capture requires explicit permission) |
| `lib/whisper-transcriber.js` | Audio capture + STT (offscreen document) |
| `offscreen.html` / `offscreen.js` | Offscreen document for audio processing |

## API endpoints used

| Endpoint | Purpose |
|----------|---------|
| `POST /api/auth/login` | Get bearer token |
| `GET /api/the-moment` | The one thing that matters (default view) |
| `GET /api/briefing` | Pre-call briefing (SituationBriefingEngine) |
| `GET /api/ambient` | Ambient intelligence (sentiment + staleness + calendar) |
| `GET /api/situations` | Get situation ID for copilot |
| `POST /api/copilot/transcript` | Process transcript chunk (CopilotSituationBridge) |
| `POST /api/copilot/post-call` | Generate post-call summary |
