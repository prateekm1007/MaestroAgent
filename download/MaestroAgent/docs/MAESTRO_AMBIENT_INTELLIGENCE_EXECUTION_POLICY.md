# MAESTRO AMBIENT INTELLIGENCE — GOVERNED EXECUTION POLICY

> **THE LOOP CANNOT BE BROKEN.**
> Both sides read GOVERNANCE_LOOP.md, ENTROPY_RECOVERY.md Part Four + Five,
> AUDITOR_GOVERNANCE.md Gates 15-20, and audit_scripts/audit_gates.sh from
> disk at the start of every session. Both sides paste a read receipt.

**Date:** 2026-07-07
**Source spec:** `MAESTRO_AMBIENT_INTELLIGENCE_ROADMAP.md` (1,111 lines, 12 phases)
**Companion spec:** `MAESTRO_LIVE_COPILOT_ROADMAP_GOVERNED.md` (8 phases, the meeting-time layer)
**Current HEAD:** `d9026e2` (origin/main)
**Total scope:** 20 phases, 153 days, ~612 hours, $480K-720K investment
**CEO promise:** "Ambient organizational intelligence layer — works 24/7, not just during calls"

---

## 0. The Non-Negotiable Ethical Line (carried forward from Live Copilot)

**FORBIDDEN code paths (any appearance rejects the entire phase):**

- Hiding from meeting software as a selling feature
- Bypassing screen-share detection
- Unconsented recording (consent MUST precede any audio/video/email/Slack capture)
- Exam/interview assistance modes
- "Undetectable mode" or stealth framing
- Automatic answer injection into calls
- **NEW for Ambient:** Inferring commitments from ambiguous language without confirmation
- **NEW for Ambient:** Reading email/Slack/calendare content or attachments without explicit consent
- **NEW for Ambient:** Emotion/sentiment analysis used to manipulate (only for the user's own awareness, never to "win" against the other party)

**The differentiator from Cluely:** Maestro is ambient (works between calls), deep (multi-layer), rich (full context), learning (compounds), evidence-backed (every suggestion cites organizational data). Cluely helps you cheat in the moment. Maestro helps your organization learn.

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    AMBIENT INTELLIGENCE LAYER                    │
├─────────────────────────────────────────────────────────────────┤
│  Calendar   │    Email     │  Slack/Teams  │   CRM      │ Audio │
│  Awareness  │ Integration  │ Message Stream │ Connectors │(Live) │
│     │            │                │             │          │     │
│     └────────────┴────────────────┴─────────────┴──────────┘     │
│                              │                                    │
│                    AMBIENT SIGNAL FUSION                          │
│  (24/7 background loop: ingest → classify → correlate → alert)   │
│                              │                                    │
│     ┌────────────────────────┴────────────────────────┐          │
│     │                                                  │          │
│  Commitment     Deal Health     Relationship       Sentiment     │
│  Escalation      Score           Dynamics           & Emotion    │
│     │               │                │                  │        │
│     └───────────────┴────────────────┴──────────────────┘        │
│                              │                                    │
│                    ORGANIZATIONAL MEMORY                          │
│  (SituationSnapshot 27 fields + OutcomeLedger + OEM signals)     │
│                              │                                    │
│                    SURFACES (always-on)                           │
│  (Today panel + Whisper push + Ask + cross-meeting threads)      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. The 20-Phase Unified Plan

The Ambient Intelligence roadmap (12 phases) integrates with the Live Copilot roadmap (8 phases). The Live Copilot phases (1-8) deliver the meeting-time layer. The Ambient phases (9-20) deliver the always-on layer that works between calls. Together they form the unified 20-phase plan.

### Live Copilot Phases (Days 1-33, ~132 hours) — from MAESTRO_LIVE_COPILOT_ROADMAP_GOVERNED.md

| Phase | Days | Hours | Deliverable |
|---|---|---|---|
| 1: Extension scaffold | 1-3 | 12 | manifest.json, consent-manager, panel shell |
| 2: Audio + transcription | 4-7 | 16 | offscreen audio capture, Whisper STT, live transcript |
| 3: Scene 1 pre-call | 8-11 | 16 | lobby detection, attendee intelligence, talking points |
| 4: Scene 2 live | 12-18 | 28 | 4 card types (objection/commitment/whisper/pattern) |
| 5: Scene 3 post-call | 19-23 | 20 | summary, draft email, "What Maestro learned" |
| 6: Evidence + confidence | 24-27 | 16 | evidence-chain links, P25 confidence gate |
| 7: Accessibility + polish | 28-30 | 12 | keyboard nav, aria-live, contrast, reduced-motion |
| 8: Integration + audit | 31-33 | 12 | E2E test, cross-surface coherence, auditor verdict |

### Ambient Intelligence Phases (Days 34-153, ~480 hours) — from MAESTRO_AMBIENT_INTELLIGENCE_ROADMAP.md

| Phase | Days | Hours | Deliverable | Key File |
|---|---|---|---|---|
| 9: Ambient signal fusion | 34-43 | 40 | Calendar awareness engine + commitment escalation | `calendar_awareness.py`, `commitment_escalation.py` |
| 10: Sentiment & emotion | 44-53 | 40 | Voice tone analysis, sentiment graphs, emotion detection | `sentiment_engine.py` |
| 11: Deal health score | 54-63 | 40 | Live scoring during calls, risk factors, momentum | `deal_health.py` |
| 12: Negotiation strategy | 64-73 | 40 | BATNA analysis, anchoring detection, concessions | `negotiation_strategy.py` |
| 13: Relationship dynamics | 74-83 | 40 | Influence networks, power dynamics, coalitions | `relationship_dynamics.py` |
| 14: Cross-meeting threads | 84-93 | 40 | Conversation continuity, topic evolution, decisions | `cross_meeting_threads.py` |
| 15: Talk ratio + comms coach | 94-103 | 40 | Speaking time, interruptions, clarity scoring | `talk_ratio_coach.py` |
| 16: Meeting grade + analytics | 104-113 | 40 | Effectiveness score, action items, follow-up tracking | `meeting_grader.py` |
| 17: Email/Slack signals | 114-123 | 40 | Ambient monitoring of written comms, response time | `written_signal_fusion.py` |
| 18: Multi-language | 124-133 | 40 | Accent-aware STT, cultural context, translation | `multilang_support.py` |
| 19: Ambient notifications | 134-143 | 40 | Smart nudges, context-aware timing, DND integration | `ambient_notifications.py` |
| 20: Advanced analytics | 144-153 | 40 | Trend analysis, team performance, org learning metrics | `advanced_analytics.py` |

**Totals:** 20 phases, 153 days, ~612 hours, $480K-720K (4 engineers × 6 months).

---

## 3. Detailed Execution Policy (the coding rules)

This is the governed coding policy. Every phase MUST follow it. The auditor verifies compliance by execution (P31).

### 3.1 Pre-Phase (BLOCKING — before any code)

1. **Read receipt:** Paste the complete 8-field governance loop read receipt (GOVERNANCE_LOOP.md, ENTROPY_RECOVERY Part Four P20/P26, Part Five P27/P34, AUDITOR_GOVERNANCE Gates 15/17, audit_gates.sh confirmation). The CEO rejects any message without it.
2. **L0/L-prior gate:** Verify the prior phase's gate passes by execution. If any prior gate fails, STOP. Fix it first.
3. **File plan:** List the files to be created/modified in the phase. Run `grep -rn "<func>(" --include="*.py" | grep -v test_` to identify call sites that will need parameter updates (P20).
4. **Consent audit:** For any phase that touches audio, video, email, Slack, or calendar content — list every capture path and confirm each is gated by `ConsentManager.checkConsent()`. No consent gate = no merge.

### 3.2 During-Phase (per commit)

1. **P23 commit format:** Every commit MUST include a `VERIFICATION:` section with pasted command output. Claims without output are not evidence.
2. **P20 call-site rule:** When a function gains a parameter, run `grep -rn "<func>(" --include="*.py" | grep -v test_ | grep -v "def <func>"` and count callers that pass the new parameter. If M < N, the fix is (M/N)% done — mark INCOMPLETE, not FIXED. Paste the grep output + count in the commit.
3. **P22 production-path test:** For every fix, write TWO tests: (1) a unit test that calls the function directly, (2) an integration test that sends input through the REAL production entry point (a real HTTP request, `engine.ingest()`, or the WebSocket). Both must pass. State in the commit which of the two you wrote.
4. **P24 cross-surface coherence:** After any change to a shared component (SituationSnapshot, CommitmentTracker, OutcomeLedger, classifier), re-run the FULL SSO scenario (6 signals: Days 5, 12, 30, 40, 50, 55) and verify BOTH "pending conditions" AND "commitment dispute" appear in the RISK section. Paste the full answer output.
5. **P25 confidence gate:** For every confidence value displayed to the user, check the calibration sample size. If denominator < 10, display "insufficient calibration history" — never bare 4-decimal precision. Paste the display code + denominator check.
6. **Privacy gate:** For any phase that ingests email, Slack, calendar, or CRM data — verify the consent flow fires BEFORE ingestion. Execute the consent-denied path and confirm zero data is captured. Paste the output.

### 3.3 Post-Phase (BLOCKING — before next phase)

1. **Phase gate:** Run the phase's gate commands (specified in each phase section below). Paste the output. All must pass.
2. **Regression:** Run the L0 gate (SituationSnapshot 27 fields, OutcomeLedger, classifier, SSO scenario). All must still pass — the new phase must not regress the substrate.
3. **Push:** `git push origin main`. Paste `git rev-parse HEAD` and `git rev-parse origin/main` — they MUST match (Gate 11).
4. **Auditor verdict:** The auditor independently fetches, checks out the HEAD, runs the phase gate + L0 gate + SSO scenario by execution (P31), and publishes the verdict. Only "Phase N PASS" allows the next phase.

### 3.4 The Forbidden Anti-Patterns (auditor rejects on sight)

- **Theater tests:** A test that asserts `isinstance(result, bool)` when the claim is "result should be True." A test that asserts `assert True`. (P27)
- **Self-certification:** "✓ VERIFIED" without pasted output from THIS session. (P5, P23)
- **Wiring gaps:** A function with a new parameter where 0 of N callers pass it. (P20, Gate 15)
- **Stale-clone auditing:** Auditing a HEAD that isn't origin/main. (Gate 11)
- **Single-input testing:** Testing only the coder's exact golden input. (P28 — test 3+ inputs: exact, natural variation, edge case)
- **Confidence without denominator:** Any confidence value displayed without its sample size. (P25)
- **Stealth framing:** Any code path that hides from meeting software, bypasses detection, or records without consent. (Chapter 0 ethical line)

---

## 4. Phase Details — Ambient Intelligence (Phases 9-20)

### Phase 9: Ambient Signal Fusion (Days 34-43, 40 hours)

**Deliverables:**
- `backend/maestro_oem/calendar_awareness.py` — Calendar Awareness Engine
  - Predicts upcoming meetings, pre-fetches intelligence
  - Detects meeting clusters (e.g., "3 Globex meetings this week = deal acceleration")
  - Identifies preparation gaps (e.g., "Meeting in 2 hours, no prep done")
  - Surfaces time-based patterns (e.g., "Pricing always comes up in Q4 renewals")
  - **Privacy:** Only reads calendar metadata (title, time, attendees). Never reads content/attachments without consent.
- `backend/maestro_oem/commitment_escalation.py` — Commitment Aging & Escalation
  - Detects aging commitments (approaching due date)
  - Escalates overdue commitments (past due date)
  - Predicts commitment failures (based on historical patterns)
  - Generates follow-up nudges (when, what to say, which channel)
  - Surfaces commitment clusters (multiple commitments to same person/entity)
  - **Privacy:** Only tracks explicitly-made commitments. Never infers from ambiguous language.

**Gate:**
```bash
python -m pytest backend/maestro_oem/tests/test_calendar_awareness.py -q
# Calendar awareness detects meeting in 30 minutes
# Talking points generated from overdue commitments
# Relationship health surfaced for critical accounts
# Similar meetings found and patterns extracted

python -m pytest backend/maestro_oem/tests/test_commitment_escalation.py -q
# Overdue commitment detected and escalated
# Failure prediction based on historical patterns
# Nudge generation with appropriate channel
# Escalation levels calculated correctly
# Engine runs continuously and updates escalations
```

### Phase 10: Real-Time Sentiment & Emotion Tracking (Days 44-53, 40 hours)

**Deliverables:**
- `backend/maestro_oem/sentiment_engine.py` — voice tone analysis, sentiment graphs, emotion detection
- **Ethical guard:** Emotion/sentiment analysis is for the USER's own awareness only. Never used to "win" against the other party. Never displayed to the other party. The bright line: "Maestro helps YOU think better. Maestro does NOT help you manipulate, surveil, or win against another person."

**Gate:**
```bash
python -m pytest backend/maestro_oem/tests/test_sentiment_engine.py -q
# Sentiment detected from voice tone within 5s
# Emotion labels accurate >= 70% on test set
# Sentiment graph updates in real time
# Emotion data NEVER shown to the other party (consent gate test)
```

### Phase 11: Deal Health Score (Days 54-63, 40 hours)

**Deliverables:**
- `backend/maestro_oem/deal_health.py` — live scoring during calls, risk factors, momentum indicators
- Score = f(commitment health, sentiment trend, relationship dynamics, historical patterns)
- Confidence gate (P25): score displayed with sample size; "insufficient calibration history" if < 10 deals in the cohort

**Gate:**
```bash
python -m pytest backend/maestro_oem/tests/test_deal_health.py -q
# Deal health score updates during call
# Risk factors surfaced (e.g., "Sam hasn't spoken in 8 minutes")
# Momentum indicators (positive/negative/neutral)
# Score confidence has denominator (P25)
```

### Phase 12: Negotiation Strategy Engine (Days 64-73, 40 hours)

**Deliverables:**
- `backend/maestro_oem/negotiation_strategy.py` — BATNA analysis, anchoring detection, concession tracking
- **Ethical guard:** Strategy is for the user's preparation, not for manipulation. The system surfaces patterns ("Your organization has handled this objection 3 times before"); it does not generate manipulative tactics.

**Gate:**
```bash
python -m pytest backend/maestro_oem/tests/test_negotiation_strategy.py -q
# BATNA analysis from organizational history
# Anchoring detected (first number mentioned)
# Concessions tracked across the call
# Strategy cites validated organizational runtimes (evidence chain)
```

### Phase 13: Relationship Dynamics Mapper (Days 74-83, 40 hours)

**Deliverables:**
- `backend/maestro_oem/relationship_dynamics.py` — influence networks, power dynamics, coalition detection
- Maps who influences whom (from signal history: who CCs whom, who approves whose PRs, who defers to whom in meetings)
- **Privacy:** Influence maps are derived from organizational signals, not personal data. No personal profile scraping.

**Gate:**
```bash
python -m pytest backend/maestro_oem/tests/test_relationship_dynamics.py -q
# Influence network built from signal history
# Power dynamics detected (who defers to whom)
# Coalitions identified (allied parties)
# Map updates as new signals arrive
```

### Phase 14: Cross-Meeting Thread Builder (Days 84-93, 40 hours)

**Deliverables:**
- `backend/maestro_oem/cross_meeting_threads.py` — conversation continuity, topic evolution, decision tracking
- Links meetings by entity + topic: "This continues the Q3 renewal discussion from Oct 15"
- Tracks decisions across meetings: "Decided to offer phased rollout (Oct 22); confirmed in Nov 5 call"

**Gate:**
```bash
python -m pytest backend/maestro_oem/tests/test_cross_meeting_threads.py -q
# Meetings threaded by entity + topic
# Topic evolution tracked across meetings
# Decisions traced through the thread
# Thread surfaces in the Today panel
```

### Phase 15: Talk Ratio & Communication Coach (Days 94-103, 40 hours)

**Deliverables:**
- `backend/maestro_oem/talk_ratio_coach.py` — speaking time analysis, interruption detection, clarity scoring
- **Ethical guard:** Coaching is for the user only. Never used to make the user "dominate" the call. The constitution: "The organization becomes more capable, not more dependent."

**Gate:**
```bash
python -m pytest backend/maestro_oem/tests/test_talk_ratio_coach.py -q
# Talk ratio calculated per speaker
# Interruptions detected (overlap + cutoff)
# Clarity score from transcript analysis
# Coaching suggestions are capability-building, not dominance-building
```

### Phase 16: Meeting Grade & Post-Call Analytics (Days 104-113, 40 hours)

**Deliverables:**
- `backend/maestro_oem/meeting_grader.py` — effectiveness score, action item completion, follow-up tracking
- Grade = f(commitments captured, objections addressed, talk ratio balance, decision clarity)
- Follow-up tracking: did the committed actions get done by the next meeting?

**Gate:**
```bash
python -m pytest backend/maestro_oem/tests/test_meeting_grader.py -q
# Meeting effectiveness score calculated
# Action items tracked to completion
# Follow-up tracking across meetings
# Grade confidence has denominator (P25)
```

### Phase 17: Email/Slack Signal Integration (Days 114-123, 40 hours)

**Deliverables:**
- `backend/maestro_oem/written_signal_fusion.py` — ambient monitoring of written communication, sentiment trends, response time analysis
- **Privacy (CRITICAL):** Only ingests email/Slack with explicit consent. Consent is per-channel and revocable. The consent-denied path captures ZERO data.
- Sentiment trends: "Sam's emails have shifted from neutral to negative over 2 weeks"
- Response time: "You took 4 days to reply to Raj's last email — pattern suggests disengagement"

**Gate:**
```bash
python -m pytest backend/maestro_oem/tests/test_written_signal_fusion.py -q
# Email/Slack ingested ONLY with consent (consent-denied path = 0 signals)
# Sentiment trends detected
# Response time patterns surfaced
# Consent is revocable (revoke = ingestion stops immediately)
```

### Phase 18: Multi-Language Support (Days 124-133, 40 hours)

**Deliverables:**
- `backend/maestro_oem/multilang_support.py` — accent-aware STT, cultural context, translation suggestions
- **Ethical guard:** Translation is for the user's understanding, not for deceptive fluency. The system never auto-translates the user's speech TO the other party without consent.

**Gate:**
```bash
python -m pytest backend/maestro_oem/tests/test_multilang_support.py -q
# Accent-aware STT accuracy >= 85% on test set
# Cultural context surfaced (e.g., "In Japanese business culture, direct 'no' is rare")
# Translation suggestions displayed to user only
# Auto-translation to other party requires explicit consent
```

### Phase 19: Ambient Notification System (Days 134-143, 40 hours)

**Deliverables:**
- `backend/maestro_oem/ambient_notifications.py` — smart nudges, context-aware timing, do-not-disturb integration
- Smart nudges: "Raj just emailed — you have 3 minutes before your next call. Reply now or schedule for 3pm?"
- Context-aware timing: no notifications during deep-work blocks, focus sessions, or off-hours
- DND integration: respects OS-level DND + calendar "focus" events

**Gate:**
```bash
python -m pytest backend/maestro_oem/tests/test_ambient_notifications.py -q
# Smart nudges generated with context
# Timing respects DND + focus blocks
# Off-hours respected (no notifications 8pm-8am local)
# Notification frequency capped (max 5/hour)
```

### Phase 20: Advanced Analytics Dashboard (Days 144-153, 40 hours)

**Deliverables:**
- `backend/maestro_oem/advanced_analytics.py` — trend analysis, team performance, organizational learning metrics
- Trend analysis: "Your deal cycle time has decreased 15% over 90 days"
- Team performance: aggregate metrics (never individual surveillance — team-level only)
- Org learning metrics: laws validated, patterns promoted, Brier score improvement

**Gate:**
```bash
python -m pytest backend/maestro_oem/tests/test_advanced_analytics.py -q
# Trends calculated from 90-day signal history
# Team performance is aggregate (no individual surveillance)
# Org learning metrics tied to OutcomeLedger + law promotion
# Dashboard renders in the Today panel
```

---

## 5. The Coding Execution Policy — Summary Checklist

For every phase, the coder MUST:

- [ ] Paste the complete 8-field read receipt (GOVERNANCE_LOOP, ENTROPY Part Four P20/P26, Part Five P27/P34, AUDITOR_GOVERNANCE Gates 15/17, audit_gates.sh)
- [ ] Verify the prior phase's gate passes by execution
- [ ] List files to create/modify + run grep for call sites (P20)
- [ ] Audit every capture path for consent gating
- [ ] Write the code with P23-compliant commits (VERIFICATION section)
- [ ] Write 2 tests per fix: unit + integration (P22)
- [ ] Re-run the SSO scenario after shared-component changes (P24)
- [ ] Gate every confidence value on its denominator (P25)
- [ ] Run the phase gate commands; paste output
- [ ] Run the L0 gate; verify no regression
- [ ] Push to origin/main; paste HEAD + origin/main (Gate 11)
- [ ] Await the auditor's "Phase N PASS" verdict before the next phase

---

## 6. The Loop

1. **Before each phase:** read governance modules from disk; paste 8-field receipt.
2. **During each phase:** cite P-numbers (P20 callers, P22 production path, P23 commit output, P24 cross-surface, P25 confidence).
3. **After each phase:** run gate + L0; push; paste HEAD.
4. **Auditor verifies:** fetch → checkout → run gate independently (P31) → run SSO scenario (P29) → publish verdict.
5. **Next phase:** only after "Phase N PASS."

**The loop cannot be broken.**

---

## 7. Honest Disclosure

This is a 153-day, 612-hour, $480K-720K build. The coder can execute every CODE phase (1-20). The CEO must resource the GTM milestones (design partners, ARR, SOC2/HIPAA/GDPR) in parallel. The 20 phases deliver the product the CEO promised investors: an ambient organizational intelligence layer that works 24/7, learns from every interaction, and compounds institutional memory over time. This is not a feature. This is a category.

The governance loop is the enforcement mechanism. Every phase is verified by execution. Every claim is pasted with output. Every gate is independently checked. The loop cannot be broken.
