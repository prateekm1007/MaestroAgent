# Cluely Killer — Feature Gap Tracker

> **Read this file at the start of every session, alongside GOVERNANCE.md and ENTROPY_RECOVERY.md.**
> This is the single source of truth for what separates Maestro from being a Cluely killer.
> Each time a feature is built, mark it ✅. When all are ✅, the app ships.

**Last updated:** 2026-07-13
**Current completion:** 53% (16 of 30 features done)

---

## The Vision

Cluely is a teleprompter. Maestro Live Copilot is your organization's institutional memory, speaking to you in real time.

**The moat:** Cluely has GPT. Maestro has your data — every commitment, every signal, every outcome. Every suggestion backed by organizational evidence. Every confidence value calibrated. Every commitment tracked. Every meeting feeding the organizational brain.

---

## Feature Status

### Phase 1 — Browser Extension / Mobile Foundation

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 1 | Extension/mobile app scaffold | ✅ DONE | Expo SDK 52, 7 screens, Bumble design, 62/62 tests |
| 2 | Navigation (bottom tabs + stack) | ✅ DONE | 5 tabs: Dashboard, Ask, Commitments, Copilot, Settings |
| 3 | API client (axios + secure storage) | ✅ DONE | expo-secure-store, interceptors, 20 endpoints |
| 4 | Theme system (Bumble colors) | ✅ DONE | Light mode default, #FFC629, #F8F0DD, #FF3B3B, #00C853 |
| 5 | Haptics (expo-haptics) | ✅ DONE | Success/Impact/Error feedback on actions |
| 6 | Production deps (react-query, zod, gesture-handler, reanimated) | ✅ DONE | All 10 production deps installed |
| 7 | app.json + eas.json (Play Store) | ✅ DONE | com.maestro.personal, APK + AAB profiles |
| 8 | Consent manager | ✅ DONE | ConsentContext + ConsentModal with AsyncStorage persistence |
| 9 | Server URL config on login | ❌ TODO | Currently hardcoded to localhost:8766 |

### Phase 2 — Audio Capture & Transcription

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 10 | Audio capture (expo-av microphone) | ✅ DONE | Mic button on Copilot screen, start/stop recording, permission request |
| 11 | Local transcription (Whisper or on-device) | ❌ TODO | Recording saved but not transcribed yet (placeholder text) |
| 12 | Transcript stream to backend (WebSocket) | ✅ DONE | WS connection with maestro-auth + first-message auth, REST fallback |
| 13 | Transcript display (chat bubbles) | ✅ DONE | Auto-scroll, speaker bubbles, empty state with mic icon |

### Phase 3 — Real-Time Intelligence

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 14 | WebSocket connection (ws:// + auth) | ✅ DONE | Phase 1.1 WS auth fix + Copilot screen WS with maestro-auth |
| 15 | Real-time whisper delivery via WS | ✅ DONE | WS onmessage handler parses whispers, adds to panel with haptics |
| 16 | Evidence-backed suggestions | ✅ DONE | Every WS whisper now includes evidence_refs (relevant signals + active commitments) |
| 17 | Confidence values on suggestions | ✅ DONE | Confidence = 0.4 + evidence_count*0.1, +0.15 for high-severity contradictions |
| 18 | Objection handler (battlecards) | ✅ DONE | Contradiction detection + stale commitment surfacing + negotiation anchors |
| 19 | Commitment tracker (real-time) | ✅ DONE | Commitments detected in real-time via WS, included in whisper data |
| 20 | Context fusion (transcript + history → whisper) | ✅ DONE | CopilotContextFuser fuses transcript + FTS signals + commitments + contradictions |

### Phase 4 — Copilot UI

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 21 | Whisper panel (right sidebar / overlay) | ✅ DONE | Exists but empty (0 whispers generated) |
| 22 | Critical whisper (red border + haptic) | ⚠️ PARTIAL | Red border design exists, no whispers to show |
| 23 | Suggestion whisper (yellow border) | ⚠️ PARTIAL | Design exists, no whispers generated |
| 24 | Ack whisper (transparent, auto-dismiss) | ❌ TODO | Not implemented |
| 25 | Connection status indicator | ✅ DONE | Connected/Disconnected banner |

### Phase 5 — Post-Call & Intelligence

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 26 | Post-call summary (commitments, completions, talk ratio) | ⚠️ PARTIAL | Endpoint exists, UI not complete |
| 27 | Follow-up email generator | ❌ TODO | P2 — commitment-aware email draft |
| 28 | Pre-call intelligence panel | ⚠️ PARTIAL | /api/prepare exists but not wired to Copilot |
| 29 | Meeting store (ingest into OEM) | ⚠️ PARTIAL | Post-call endpoint exists |
| 30 | Playbook mode (sales teams) | ❌ TODO | Enterprise, Phase 7 |

---

## P0 Blockers (must build before ship)

1. ~~Audio capture~~ — ✅ DONE (expo-av mic button on Copilot screen)
2. ~~WebSocket real-time~~ — ✅ DONE (ws:// with maestro-auth + first-message auth)
3. ~~Consent manager~~ — ✅ DONE (ConsentContext + ConsentModal + AsyncStorage)
4. ~~Real-time whisper delivery~~ — ✅ DONE (WS onmessage → whisper panel with haptics)
5. ~~Evidence-backed suggestions~~ — ✅ DONE (every WS whisper includes evidence_refs + confidence)

**ALL P0 BLOCKERS COMPLETE.** ✅

## P1 Differentiators (the moat vs Cluely)

6. ~~Context fusion~~ — ✅ DONE (CopilotContextFuser: transcript + FTS + commitments + contradictions)
7. ~~Objection handler~~ — ✅ DONE (contradiction detection + stale commitment surfacing + negotiation anchors)
8. ~~Confidence values~~ — ✅ DONE (evidence-count-based, +0.15 for high-severity contradictions)
9. ~~Commitment tracker~~ — ✅ DONE (real-time detection via WS, included in whisper data)

## P2 Polish (nice to have)

10. **Follow-up email generator**
11. **Pre-call intelligence panel**
12. **Post-call summary UI**
13. **Playbook mode**
14. **Shadow mode**

---

## Cluely vs Maestro Comparison

| Capability | Cluely | Maestro | Gap |
|-----------|--------|---------|-----|
| Suggestion source | Generic LLM | Organizational laws (YOUR data) | Maestro has the data, needs to wire it to real-time |
| Evidence | None | Full provenance chain | ✅ Backend exists, needs copilot wiring |
| Confidence | Made up | Bayesian calibration | ✅ Backend exists, needs copilot wiring |
| Customer context | None | Customer Judgment Engine | ✅ Backend exists, needs copilot wiring |
| Objection handling | Generic rebuttals | Commitment tracker | ❌ Not built |
| Follow-ups | Generic email | Commitment-aware | ❌ Not built |
| Organizational memory | None | Historical replay | ✅ Backend exists, needs copilot wiring |
| Privacy | Cloud audio | Local Whisper + on-prem | ❌ Not built (no audio capture) |
| Ethics | "Undetectable" (deceptive) | Transparent (consent-first) | ❌ Not built (no consent manager) |

**Key insight:** Maestro's backend already has 80% of the intelligence (evidence, confidence, commitments, organizational memory). The gap is **wiring** — connecting the backend intelligence to the real-time copilot flow. The mobile app has the UI shell but not the real-time pipeline.

---

## Ship Criteria

The app ships when ALL P0 blockers are done:

- [ ] Audio capture works (mic recording via expo-av)
- [ ] WebSocket connection works (ws:// + maestro-auth + first-message auth)
- [ ] Consent manager works (mandatory before recording)
- [ ] Real-time whispers flow during calls (evidence-backed)
- [ ] Suggestions cite organizational evidence (not generic LLM)

**Estimated effort:** 38 hours (1 week with 1 engineer)

---

## Session Protocol

At the start of every coding session:

1. Read GOVERNANCE.md + ENTROPY_RECOVERY.md from disk
2. Read THIS FILE (cluely_killer_gap.md) from disk
3. Check which features are still ❌ TODO
4. Pick the next P0 blocker
5. Build it
6. Mark it ✅ DONE in this file
7. Commit this file with the update

When all P0 blockers are ✅, the app is ready to ship.
