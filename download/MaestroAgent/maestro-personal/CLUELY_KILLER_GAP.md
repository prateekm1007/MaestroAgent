# Cluely Killer — Feature Gap Tracker

> **Read this file at the start of every session, alongside GOVERNANCE.md and ENTROPY_RECOVERY.md.**
> This is the single source of truth for what separates Maestro from being a Cluely killer.
> Each time a feature is built, mark it ✅. When all are ✅, the app ships.

**Last updated:** 2026-07-13
**Current completion:** 30% (9 of 30 features done)

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
| 8 | Consent manager | ❌ TODO | Legal requirement — no recording without consent |
| 9 | Server URL config on login | ❌ TODO | Currently hardcoded to localhost:8766 |

### Phase 2 — Audio Capture & Transcription

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 10 | Audio capture (expo-av microphone) | ❌ TODO | P0 — without this, Copilot is just text chat |
| 11 | Local transcription (Whisper or on-device) | ❌ TODO | P0 — audio must not leave device |
| 12 | Transcript stream to backend (WebSocket) | ❌ TODO | P0 — REST is too slow for live meetings |
| 13 | Transcript display (chat bubbles) | ✅ DONE | Copilot screen has speaker bubbles, auto-scroll |

### Phase 3 — Real-Time Intelligence

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 14 | WebSocket connection (ws:// + auth) | ⚠️ PARTIAL | WS auth fixed (Phase 1.1), but Copilot screen uses REST only |
| 15 | Real-time whisper delivery via WS | ❌ TODO | P0 — whispers should slide in during the call |
| 16 | Evidence-backed suggestions | ❌ TODO | P1 — every whisper must cite evidence (the moat vs Cluely) |
| 17 | Confidence values on suggestions | ❌ TODO | P1 — Bayesian calibration, not made-up numbers |
| 18 | Objection handler (battlecards) | ❌ TODO | P1 — Cluely's core feature, Maestro's differentiator |
| 19 | Commitment tracker (real-time) | ⚠️ PARTIAL | Commitments detected (16/30 in benchmark) but no real-time tracking |
| 20 | Context fusion (transcript + history → whisper) | ❌ TODO | P1 — the core intelligence that Cluely lacks |

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

1. **Audio capture** — expo-av microphone recording
2. **WebSocket real-time** — ws:// connection with auth, transcript streaming
3. **Consent manager** — transparent recording consent
4. **Real-time whisper delivery** — suggestions flow during the call
5. **Evidence-backed suggestions** — every whisper cites organizational evidence

## P1 Differentiators (the moat vs Cluely)

6. **Context fusion** — transcript + historical signals → coaching whisper
7. **Objection handler** — battlecards with evidence from past deals
8. **Confidence values** — calibrated, not fabricated
9. **Commitment tracker** — "You promised SSO by Day 60 — today is Day 45"

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
