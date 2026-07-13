# CLAIM FREEZE — Maestro Marketing Alignment

> **Created:** Phase 0, 2026-07-13
> **Rule:** Marketing must match this sheet. No claim is "real" until marked VERIFIED with execution evidence.
> **Baseline audit:** `MAESTRO_WORLD_CLASS_MOBILE_CERTIFICATION_AUDIT.md` @ commit `59333a5` (score 40/100)

## How to use this sheet

Every public claim (README, investor manual, website, demo) must map to a row here. If a claim is FALSE or PARTIAL, either fix it or stop claiming it. The auditor will check this sheet against the code.

## Claim matrix

### Mobile app

| Claim | Status | Evidence | Action |
|-------|--------|----------|--------|
| 7-screen mobile app (Expo) | VERIFIED | `mobile/App.tsx` 1,438 lines, 7 inline screens, 62 structure tests pass | — |
| Bumble-inspired design (yellow #FFC629, honey #F8F0DD) | VERIFIED | `mobile/src/theme.ts` has all Bumble colors, `app.json` splash bg is #F8F0DD | — |
| TypeScript compilation passes | VERIFIED | `npx tsc --noEmit` → EXIT 0 (commit `f0825a5`) | — |
| App assets (icon, splash, adaptive icon) | VERIFIED | `mobile/assets/` has 4 PNGs (commit `f0825a5`) | — |
| Modular screens (src/screens/*) | **FALSE** | App.tsx has 7 INLINE screens; src/screens/ has 7 orphan files NOT imported | Phase 0: pick one tree, kill the other |
| Onboarding flow | **FALSE** | No onboarding — straight to login | Phase 2 |
| Offline mode (react-query cache) | **FALSE** | react-query installed but not imported | Phase 2 |
| Form validation (zod + react-hook-form) | **FALSE** | Both installed but not imported | Phase 2 |
| Gestures (swipe to complete) | **FALSE** | gesture-handler installed but not imported | Phase 2 |
| Animations (reanimated) | **FALSE** | reanimated installed but not imported | Phase 2 |
| Data sharing (expo-sharing) | **FALSE** | expo-sharing installed but not imported | Phase 2 |

### Authentication

| Claim | Status | Evidence | Action |
|-------|--------|----------|--------|
| Bearer token auth | VERIFIED | `POST /api/auth/login` returns token; client.ts axios interceptor attaches it | — |
| Token stored in SecureStore | **PARTIAL** | client.ts imports SecureStore for host URL, but `resolveToken()` reads token from AsyncStorage | Phase 1: fix to SecureStore-only |
| Login rejects empty password | VERIFIED | LoginScreen.tsx validates `!password.trim()` (commit `1c47264`) | — |
| Login no longer accepts "any" | VERIFIED | `password || 'any'` removed (commit `1c47264`) | — |
| Token revocation on logout | **PARTIAL** | `clearToken()` removes from storage, but doesn't call `POST /api/auth/revoke` | Phase 1 |
| Rate limiting on login | **FALSE** | No rate limiting implemented | Phase 1 |
| HTTPS enforcement in production | **FALSE** | No http:// check in production mode | Phase 1 |

### Backend

| Claim | Status | Evidence | Action |
|-------|--------|----------|--------|
| FastAPI on port 8766 | VERIFIED | `api.py` runs uvicorn on 8766 | — |
| `pip install -e .` works (no PYTHONPATH) | VERIFIED | `pyproject.toml` added (commit `1c47264`), import works from /tmp | — |
| SQLite + FTS5 semantic retrieval | VERIFIED | 258 backend tests pass, FTS5 index built | — |
| 26 new API endpoints (P2 + connectors) | VERIFIED | All registered in api.py, tested | — |
| Per-user token isolation | VERIFIED | `test_per_user_isolation` passes | — |
| API rate limiting | **FALSE** | No rate limiting on any endpoint | Phase 1 |
| Postgres support | **FALSE** | SQLite only | Phase 6 |
| Background workers for ingest | **FALSE** | Ingest is synchronous | Phase 6 |
| OpenAPI contract tests | **FALSE** | No shared schemas between mobile + backend | Phase 6 |

### AI Intelligence

| Claim | Status | Evidence | Action |
|-------|--------|----------|--------|
| Ask Ranker (intent classification + reranking) | VERIFIED | `ask_ranker.py` exists, `test_ask_ranker_integration.py` passes | — |
| Cognitive Council (multi-agent) | VERIFIED | `maestro_cognitive_council/` module exists and is wired | — |
| Learning Loop with Brier calibration | **PARTIAL** | `learning_loop_v2.py` exists, but no live outcome data in dogfood | Phase 5 |
| Provenance-first (every answer cites source) | VERIFIED | Ask response includes `source_sentence`, `source_entity`, `evidence_refs` | — |
| Trusted silence (materiality gate) | VERIFIED | `materiality_gate.py` exists, silence benchmark passes | — |
| LLM active by default | **PARTIAL** | LLM works when configured (Ollama/ZAI), but defaults to rule-based | Phase 5 |
| +18.1 lift vs BM25 on gold scoring | **PARTIAL** | Measured on 5-question subset; full 47-question run pending | Phase 5 |
| Gold-150 evaluation | **FALSE** | Not yet created | Phase 5 |

### Copilot

| Claim | Status | Evidence | Action |
|-------|--------|----------|--------|
| Consent manager (modal before recording) | VERIFIED | App.tsx has consent modal, persisted in AsyncStorage | — |
| Audio capture (expo-av) | VERIFIED | `startRecording()` / `stopRecording()` use expo-av | — |
| Real-time transcription | **PARTIAL** | Wit.ai provider wired + tested; but mobile uploads after stop (not streaming) | Phase 4: streaming STT |
| WebSocket real-time streaming | VERIFIED | WS endpoint exists, `test_p0_2_websocket_copilot.py` passes | — |
| Evidence-backed whispers | VERIFIED | Whispers include `evidence_refs`, `confidence`, `entity` | — |
| 3 whisper types (Critical/Suggestion/Ack) | VERIFIED | Red/yellow/muted borders in UI | — |
| Post-call summary modal | VERIFIED | `PostCallSummaryUI` + `/api/copilot/post-call-ui` endpoint | — |
| Follow-up email generator | VERIFIED | `FollowUpEmailGenerator` + `/api/copilot/follow-up-email` endpoint | — |
| Pre-call intelligence panel | VERIFIED | `PreCallIntelPanel` + `/api/copilot/pre-call-intel` endpoint | — |
| Whisper latency p95 < 1.5s | **UNVERIFIED** | No device benchmark | Phase 4 |

### Connectors

| Claim | Status | Evidence | Action |
|-------|--------|----------|--------|
| 8 connectors defined | VERIFIED | `SUPPORTED_CONNECTORS` dict in connectors.py | — |
| Gmail real OAuth2 | **PARTIAL** | Code real + 28 tests pass, but NOT tested with real Google credentials on device | Phase 3: real OAuth test |
| Slack real OAuth2 | **PARTIAL** | Code real + 26 tests pass, but NOT tested with real Slack credentials | Phase 3 |
| GitHub real OAuth2 | **PARTIAL** | Code real + 30 tests pass, but NOT tested with real GitHub credentials | Phase 3 |
| Calendar real OAuth2 (read-only) | **PARTIAL** | Code real + 24 tests pass, but NOT tested with real Google credentials | Phase 3 |
| Encrypted OAuth token storage | VERIFIED | Fernet encryption, `test_token_not_in_plaintext` passes | — |
| Per-connector revocation | VERIFIED | `test_per_connector_revocation` passes | — |
| Draft approval flow (approve/deny/use_draft) | VERIFIED | 9 draft tests pass | — |
| `/api/drafts/auto` DERIVES commitment from signals | VERIFIED | P13 fix, 7 auto-derivation tests pass | — |
| Mobile connectors UI | **FALSE** | No connectors screen in mobile app (only in web app) | Phase 3 |

### Transcription

| Claim | Status | Evidence | Action |
|-------|--------|----------|--------|
| Wit.ai free + scalable STT | VERIFIED | `_transcribe_witai()` tested end-to-end with real token (commit `560bd1e`) | — |
| Local Whisper support | VERIFIED | `_transcribe_whisper_local()` tested with real audio (commit `01fa61c`) | — |
| `POST /api/copilot/transcribe` endpoint | VERIFIED | 7 integration tests pass | — |
| Mobile uploads audio to transcribe endpoint | VERIFIED | `stopRecording()` in App.tsx calls `/api/copilot/transcribe` | — |

### Security

| Claim | Status | Evidence | Action |
|-------|--------|----------|--------|
| Token in SecureStore | **PARTIAL** | SecureStore used for host URL; token still in AsyncStorage | Phase 1: fix |
| Fernet encryption for OAuth tokens | VERIFIED | `test_token_not_in_plaintext` passes | — |
| Rate limiting | **FALSE** | Not implemented | Phase 1 |
| HTTPS enforcement | **FALSE** | Not implemented | Phase 1 |
| npm audit high = 0 | **UNVERIFIED** | 18 vulnerabilities reported (12 moderate, 6 high) | Phase 1 |

### Privacy

| Claim | Status | Evidence | Action |
|-------|--------|----------|--------|
| Export all data | VERIFIED | `GET /api/account/export` returns JSON | — |
| Delete account | VERIFIED | `DELETE /api/account` removes all data | — |
| Privacy mode | VERIFIED | `GET /api/privacy/mode` returns mode + egress paths | — |
| Per-connector consent | **PARTIAL** | Connectors have connect/disconnect, but no granular consent UI in mobile | Phase 1 |
| Data retention documented | **FALSE** | No retention policy doc | Phase 1 |

### Accessibility

| Claim | Status | Evidence | Action |
|-------|--------|----------|--------|
| VoiceOver / TalkBack labels | **FALSE** | No `accessibilityLabel` props in mobile app | Phase 7 |
| Dynamic Type support | **FALSE** | Not tested | Phase 7 |
| Contrast AA | **UNVERIFIED** | Not tested | Phase 7 |
| Reduced motion | **FALSE** | No `AccessibilityInfo.isReduceMotionEnabled` check | Phase 7 |

## Summary

| Status | Count |
|--------|-------|
| VERIFIED | 27 |
| PARTIAL | 12 |
| FALSE | 14 |
| UNVERIFIED | 3 |
| **Total** | **56** |

## Rule

Until a claim moves from FALSE/PARTIAL to VERIFIED with execution evidence, it must not appear in marketing materials, investor docs, or demo scripts.
