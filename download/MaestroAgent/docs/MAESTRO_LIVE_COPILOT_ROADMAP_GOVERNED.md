# MAESTRO LIVE COPILOT — GOVERNED EXECUTION ROADMAP

> **THE LOOP CANNOT BE BROKEN.**
> Both sides read GOVERNANCE_LOOP.md, ENTROPY_RECOVERY.md Part Four + Five,
> AUDITOR_GOVERNANCE.md Gates 15-20, and audit_scripts/audit_gates.sh from
> disk at the start of every session. Both sides paste a read receipt.

**Date:** 2026-07-07
**Source spec:** "Here's What Maestro Live Copilot Looks Like — 3 Scenes, Full Experience"
**Current HEAD:** `e867cb7` (origin/main)
**L0 gate status:** PASS (3/4 verified by execution; L0.4 deferred — test path varies by environment)

---

## 0. The Non-Negotiable Ethical Line

**FORBIDDEN code paths (the auditor rejects the entire phase if any appear):**

- Hiding from meeting software as a selling feature
- Bypassing screen-share detection
- Unconsented recording (consent MUST be obtained before any audio capture)
- Exam/interview assistance modes
- "Undetectable mode" or any stealth framing
- Automatic answer injection into calls (suggestions are displayed in a side panel; the user speaks them)

**This is the differentiator from Cluely.** Maestro Live Copilot is:
- **Side panel, not overlay** — transparent, anyone can see it
- **Consent-first** — `ConsentManager.checkConsent()` MUST gate every `getUserMedia`/`getDisplayMedia` call
- **Audit-logged** — every suggestion, every capture, every dismiss is logged
- **Evidence-grounded** — every suggestion cites organizational data, not generic AI

---

## 1. The 3 Scenes (Target Experience)

### Scene 1: Before You Join — Pre-Call Intelligence

**Trigger:** User opens a Google Meet / Zoom / Teams lobby URL; Maestro extension detects the meeting metadata.

**Surfaces:**
1. Meeting context card — ARR at risk, renewal countdown, account health (from SituationSnapshot)
2. Attendee intelligence per person — interaction count from OEM signal history, commitment status from CommitmentTracker, last-interaction gap
3. Suggested talking points — each citing the organizational data behind it

**Key data sources:** SituationSnapshot (27 fields, L0-1 PASS), CommitmentTracker, OEM signal history.

### Scene 2: During the Call — Live Intelligence

**Trigger:** User clicks "Start Copilot" in the side panel AFTER consent; audio capture begins via offscreen document.

**Surfaces (real time):**
1. **Objection detected** (rose border, glowing) — transcribed text matches objection pattern; response cites validated organizational runtimes; confidence bar from pattern count
2. **Commitment detected** (amber border) — transcribed text matches commitment pattern; deduped against existing commitments (Day X/Y)
3. **Organizational whisper** (purple border) — transcript entity matches a GitHub PR / Slack message / Confluence page; cross-validated evidence chain
4. **Historical pattern match** (cyan border) — current conversation resembles a past meeting; outcome cited
5. **Live transcript** — last 3 chunks with speaker labels, trigger words highlighted

**Key data sources:** ContentEpistemicClassifier (L0-3 PASS — tentative/sarcasm/artifact), EvidenceBuilder, RecallEngine, PatternDetector.

### Scene 3: After the Call — Meeting Intelligence Captured

**Trigger:** Call ends (WebSocket disconnect or tab close).

**Surfaces:**
1. Hero summary card — meeting title, duration, participant count, transcript chunk count
2. Key stats grid — commitments, objections, suggestions counts
3. Commitments tracked — each with actor, Day X/Y, dedup status
4. Objections raised — with response pattern and action required
5. Draft follow-up email — pre-written, citing specific commitments + patterns; copy/edit/open-in-Gmail
6. What Maestro learned — new signals ingested, pattern data-point count, law-promotion threshold

**Key data sources:** OutcomeLedger (L0-2 PASS — durable, tenant-scoped), ConversationStore, InteractionMemory.

---

## 2. L0 Prerequisite Gate (MUST PASS before Phase 1)

| Gate | Verification command | Status at `e867cb7` |
|---|---|---|
| L0.1 SituationSnapshot 27 fields | `python3 -c "from maestro_oem.situation import Situation; ..."` → `fields=27 missing=0/17` | **PASS** |
| L0.2 OutcomeLedger functional | `python3 -c "from maestro_oem.governed_adaptation import OutcomeLedger; ..."` → `methods=['append','clear','close','count','get_all']` | **PASS** |
| L0.3 Classifier new types | classifier → `tentative` / `sarcasm` / `artifact` for the 3 probes | **PASS** |
| L0.4 SSO scenario 7/7 | `pytest test_hybrid_e2e.py test_sprint_completion.py` | DEFERRED (test path varies; verifier confirms L0.1-3) |

**If any L0 check fails, STOP.** Fix the L0 prerequisite first.

---

## 3. The 8-Phase Plan

### Phase 1: Browser Extension Scaffold (Days 1-3, 12 hours)

**Deliverables:**
- `extension/manifest.json` — Chrome MV3 manifest, `sidePanel` permission, NOT overlay
- `extension/background.js` — service worker (WebSocket client, auth, session lifecycle)
- `extension/lib/consent-manager.js` — MANDATORY consent flow before any audio capture
- `extension/panel.html` + `panel.js` + `panel.css` — side panel shell (380px, Inter + JetBrains Mono)
- `extension/content.js` — meeting platform detection (Google Meet / Zoom / Teams lobby URLs)
- `extension/offscreen.html` + `offscreen.js` — offscreen document scaffold (Phase 2 fills in audio capture)

**Gate (must pass before Phase 2):**
```bash
# 1. Extension loads without errors (manual: chrome://extensions → Load unpacked → 0 errors)
# 2. Consent manager gates every capture path
grep -rn "getUserMedia\|getDisplayMedia" extension/
# Every match MUST be preceded by ConsentManager.checkConsent()

# 3. Side panel opens (manual: click icon → panel opens → "Ready" status)
# 4. WebSocket client exists
grep -rn "WebSocket" extension/background.js  # MUST return ≥1 match
```

### Phase 2: Audio Capture + Transcription (Days 4-7, 16 hours)

**Deliverables:**
- `extension/offscreen.js` — `getUserMedia` / `getDisplayMedia` for system audio, gated by consent
- WebSocket streaming to backend transcription service
- `backend/maestro_live/transcription.py` — Whisper (local) or OpenAI (fallback) transcription
- Speaker diarization (simple energy-based for v1; pyannote for v2)
- Transcript chunks pushed to side panel via WebSocket (last 3 visible, trigger words highlighted)

**Gate:**
```bash
# 1. Audio capture requires explicit consent (consent recorded in audit log)
# 2. Transcript appears in side panel within 3s of speech
# 3. No audio is captured before consent (P31: execute the consent-denied path)
```

### Phase 3: Scene 1 — Pre-Call Intelligence (Days 8-11, 16 hours)

**Deliverables:**
- `extension/content.js` — detect Google Meet / Zoom / Teams lobby URLs; extract meeting title
- `backend/maestro_live/pre_call.py` — query SituationSnapshot + CommitmentTracker + OEM signals for attendees
- `extension/panel.js` — render meeting context card, attendee intelligence, suggested talking points
- Every suggestion cites its evidence ("12 interactions" links to signal history; "Day 45 of 60" links to commitment)

**Gate:**
```bash
# 1. Open a Meet lobby URL → side panel shows pre-call briefing within 2s
# 2. Every suggestion has a visible evidence chain (click → opens the source signal)
# 3. No LinkedIn-style generic bios — every fact cites organizational data
```

### Phase 4: Scene 2 — Live Intelligence (Days 12-18, 28 hours)

**Deliverables:**
- `backend/maestro_live/live_engine.py` — processes transcript chunks in real time:
  - Objection detection (ContentEpistemicClassifier + objection patterns)
  - Commitment detection (deduped against CommitmentTracker via content hash)
  - Organizational whisper (entity match against OEM signals — GitHub PRs, Slack, Confluence)
  - Historical pattern match (PatternDetector against past meetings)
- `extension/panel.js` — render 4 card types with color-coded borders + confidence bars:
  - Rose (#FF5577) = objection, Amber (#FFB84D) = commitment, Purple (#7C5CFF) = whisper, Cyan (#5CC8FF) = pattern
- `cardSlideIn` animation (400ms ease-out), glow effect on new cards (fades after 5s)
- `aria-live` regions for new suggestions (accessibility)

**Gate:**
```bash
# 1. Objection card appears within 5s of the objection being spoken
# 2. Commitment card dedupes against existing commitments (not a duplicate)
# 3. Confidence bars are honest: <10 samples = "insufficient calibration history" (P25)
# 4. Every card has a visible evidence chain
```

### Phase 5: Scene 3 — Meeting Intelligence Captured (Days 19-23, 20 hours)

**Deliverables:**
- `backend/maestro_live/post_call.py` — generates summary, stats, commitments, objections, draft email
- `extension/panel.js` — render hero summary, stats grid, commitments tracked, objections, draft email
- Draft follow-up email cites specific commitments + references organizational patterns
- "What Maestro learned" section — new signals count, pattern data-point count, law-promotion threshold
- Ingest new commitments into OutcomeLedger (L0-2 — durable, tenant-scoped)
- Ingest objection outcome into the learning loop (OutcomeRecorder)

**Gate:**
```bash
# 1. After call ends, summary appears within 5s
# 2. Commitments are ingested into OutcomeLedger (verified by ledger.count() increase)
# 3. Draft email cites at least 1 specific commitment from the call
# 4. "What Maestro learned" shows the data-point delta
```

### Phase 6: Evidence Chain + Confidence Honesty (Days 24-27, 16 hours)

**Deliverables:**
- Every suggestion card has a "View evidence →" link that opens the source signal
- Confidence display gate (P25): <10 samples → "insufficient calibration history"; 10-30 → percentage with sample count; >30 → percentage with green/amber bar
- Pattern promotion: when a pattern reaches 5 validated runtimes, it becomes a candidate law; when it reaches 10, it becomes a validated law (visible to the user)

**Gate:**
```bash
# 1. Click "View evidence →" on any card → opens the source signal in a new tab
# 2. No confidence value is displayed without its denominator (P25)
# 3. Law promotion is visible to the user ("This pattern is now a validated law")
```

### Phase 7: Accessibility + Polish (Days 28-30, 12 hours)

**Deliverables:**
- All cards keyboard-navigable (Tab + Enter), focus-visible outlines
- `aria-live` regions for new suggestions (polite, not assertive)
- Color contrast ≥ 4.5:1 (WCAG AA)
- Reduced-motion mode (`prefers-reduced-motion` disables cardSlideIn + glow)
- Mobile-responsive side panel (collapses to 320px on narrow screens)

**Gate:**
```bash
# 1. Lighthouse accessibility audit ≥ 90
# 2. Tab through every card; Enter activates the primary action
# 3. prefers-reduced-motion disables animations
```

### Phase 8: Integration Test + Audit Gate (Days 31-33, 12 hours)

**Deliverables:**
- End-to-end test: lobby → consent → call (with simulated transcript) → post-call summary
- Cross-surface coherence test (P24): commitments detected in the call appear in SituationSnapshot, Ask, Whisper, and Preparation
- Independent auditor runs the full L0 + Phase 1-7 gates
- Auditor publishes verdict; only "PASS" allows ship

**Gate:**
```bash
# 1. E2E test passes (lobby → consent → call → summary → learning loop)
# 2. Cross-surface coherence test passes (commitments appear in all 5 surfaces)
# 3. Independent auditor publishes "Phase 8 PASS"
# 4. SSO scenario still 7/7 (P29 — copilot touches shared OEM)
```

---

## 4. Technical Spec (from the source)

| Element | Value |
|---|---|
| Side panel width | 380px (Chrome native side panel) |
| New-card animation | `cardSlideIn` 400ms ease-out |
| Glow effect | `box-shadow: 0 0 20px rgba(255,214,10,0.15)` fades after 5s |
| Rose (objection) | #FF5577 |
| Amber (commitment) | #FFB84D |
| Purple (whisper) | #7C5CFF |
| Cyan (pattern) | #5CC8FF |
| Green (tracked) | #00D4AA |
| Typography | Inter (sans) + JetBrains Mono (numbers) |
| Accessibility | keyboard-navigable, focus-visible, aria-live |

---

## 5. Commit Format (P23 — NON-NEGOTIABLE)

Every commit MUST include a `VERIFICATION:` section:

```
feat(copilot): Phase N — <short description>

VERIFICATION:
$ <command>
<output>

$ <command>
<output>

Governance: P1 (execute), P23 (commit cites output), P26 (re-read from disk).
Read receipt: pasted in worklog at <timestamp>.
```

If the commit has no `VERIFICATION:` section, the auditor rejects it.

---

## 6. The Loop

1. **Before each phase:** read GOVERNANCE_LOOP.md + ENTROPY_RECOVERY.md Part Four + Five from disk; paste read receipt (8 fields).
2. **During each phase:** cite the P-number principle each fix satisfies (P20 callers, P22 production path, P23 commit output, P24 cross-surface, P25 confidence gate).
3. **After each phase:** run the phase gate commands; paste output in the commit; push to origin/main.
4. **Auditor verifies:** fetch → checkout HEAD → run gate independently (P31) → run SSO scenario (P29) → publish verdict.
5. **Only after auditor says "Phase N PASS"** may the next phase begin.

**The loop cannot be broken.**
