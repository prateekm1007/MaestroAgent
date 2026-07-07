# MaestroAgent — Executive Cognition Center

**An enterprise cognitive intelligence platform that surfaces what your organization knows but hasn't said.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/prateekm1007/MaestroAgent/actions/workflows/ci.yml/badge.svg)](https://github.com/prateekm1007/MaestroAgent/actions/workflows/ci.yml)

## What This Is

MaestroAgent ingests execution signals from GitHub, Jira, Slack, Confluence, Gmail, and CRM providers, then infers organizational laws, surfaces Whispers (evidence-backed insights), tracks commitments and decisions, and learns — through a governed adaptation loop — when to speak and when to stay silent.

The product is built around a **central loop**: Organizational Event → Evidence → Interpretation → Situation → Memory → Preparation → Whisper or Silence → Question → Decision → Outcome → Learning → Changed Future Behavior. Every arrow is traced through real production code and verified by execution.

**Maestro Live Copilot** extends the platform with a browser extension that provides real-time meeting intelligence — pre-call briefings, live objection/commitment/whisper detection, and post-call summaries. **Maestro Ambient Intelligence** adds 12 always-on engines that work between calls: calendar awareness, commitment escalation, sentiment tracking, deal health scoring, negotiation pattern detection, cross-meeting threading, talk ratio coaching, meeting grading, workplace signal fusion (enterprise), multi-language support, ambient notifications, and advanced analytics.

## Current State

**Pilot-ready code. 199 tests across 16 phases. 3 external audits. Governance loop enforced.**

- 199 ambient/copilot tests (all passing) + 1,874 tests collected in the full suite
- SituationSnapshot: 27 fields (10 original + 17 auditor-required) — the canonical substrate for all surfaces
- OutcomeLedger: durable, tenant-scoped (replaces process-local global state)
- Epistemic classifier: 13 types (10 original + tentative, sarcasm, artifact)
- 9 of 9 forensic audit findings fixed (CRITICAL-01/02, HIGH-01 through HIGH-06, MEDIUM-01)
- 9 of 11 Fortune 100 procurement findings fixed (3 require infrastructure)
- 5 realistic + 4 partially-realistic ambient features built; 1 killed (relationship dynamics); 1 downgraded (negotiation: "historical reference" not "AI strategy")
- Governed adaptation loop functionally closed (outcomes → policies → behavior change)
- Prompt injection defense catches 7 attack categories
- No fabricated precision (P25: confidence scores show denominator; <10 = "insufficient calibration history")

### The Anti-Cluely Design

| Element | Cluely | Maestro |
|---------|--------|---------|
| **Pre-call** | Generic LinkedIn bio | "12 interactions in organizational memory" (from OEM signals) |
| **Objection response** | "Here's a rebuttal" | "Your organization has handled this 3 times before. Phased rollout closed 2 of 3." (with evidence chain) |
| **Commitment** | Not tracked | "Matches existing commitment from Oct 15 — Day 52 of 60" |
| **Confidence** | Made up | 82% from 3 validated patterns (P25: shows denominator) |
| **Follow-up** | Generic email | Cites specific commitments, references organizational patterns |
| **Learning** | None | "This call added a data point. One more and it becomes a law." |
| **Deployment** | Invisible overlay | Side panel (transparent, consent-first) |
| **Ethics** | Stealth cheating | Bright line: "Maestro helps YOU think better. Does NOT help you manipulate, surveil, or win against another person." |

## Quick Start

```bash
# Install
cd backend
pip install -e .

# Run the server (demo mode)
MAESTRO_LOCAL_DEV=true MAESTRO_DEMO_SEED=true \
  uvicorn maestro_api.main:create_app --factory --port 1420 --app-dir .

# Open the app
# Visit http://localhost:1420/app.html
```

The app loads in demo mode with synthetic sample data. Connect real providers via Settings to see live signals.

**Do NOT run with `MAESTRO_DEMO_SEED=true` in production** — the system raises `RuntimeError` if `MAESTRO_ENV=production` and demo seed is enabled.

## Architecture

```
backend/
  maestro_oem/          Organizational Execution Model
                        - signal ingestion, law inference, pattern detection
                        - SituationSnapshot (27 fields — canonical substrate)
                        - commitment extraction + escalation engine
                        - delivery decision gate (7 options, evidence-derived)
                        - governed adaptation loop (OutcomeRecorder → OutcomeLedger
                          → AttributionAnalyzer → PolicyProposer → PolicyVersionStore)
                        - content epistemic classifier (13 types: 10 original +
                          tentative, sarcasm, artifact)
                        - live intelligence engine (4 card types: objection,
                          commitment, whisper, pattern)
                        - sentiment pattern engine (5 patterns: escalating
                          frustration, sudden positivity, sentiment divergence,
                          emotional fatigue, stress spike)
                        - deal health engine (4-component weighted score)
                        - negotiation pattern detector (BATNA, anchoring,
                          concessions — historical reference, not AI strategy)
                        - cross-meeting thread builder (70-80% accuracy,
                          <70% requires user confirmation)
                        - talk ratio coach (capability-building, not dominance)
                        - meeting grader (A-F, 4 transparent factors, user override)
                        - workplace signal fusion (enterprise, 7 privacy safeguards)
                        - multi-language support (8 languages, accent-aware DEFERRED)
                        - ambient notification engine (DND, quiet hours, fatigue)
                        - advanced analytics (trends, team performance, org learning)
                        - calendar awareness engine (24/7, preparation gap alerts)
  maestro_api/          FastAPI routes (OEM, auth, imports, copilot WebSocket,
                        copilot pre-call, copilot post-call)
  maestro_db/           SQLAlchemy 2.0 (optional) + sqlite3 fallback + Alembic
  maestro_auth/         RBAC, OAuth, OIDC, SAML, SCIM, Fernet KMS (fail-closed)
  maestro_llm/          Model-agnostic LLM router (Ollama, OpenAI, Anthropic, etc.)
  maestro_personal/     Personal mode (opt-in, separate from work mode)

extension/              Maestro Live Copilot browser extension
                        - manifest.json (Chrome MV3, sidePanel — NOT overlay)
                        - background.js (WebSocket, consent, session lifecycle)
                        - lib/consent-manager.js (MANDATORY consent, revocable,
                          audit-logged — gates every getUserMedia call)
                        - panel.html/css/js (380px side panel, Inter + JetBrains Mono,
                          5 color codes, cardSlideIn, glow effect, aria-live)
                        - content.js (Google Meet / Zoom / Teams detection)
                        - offscreen.js (consent-gated audio capture, MediaRecorder)

app.html                Executive UI (vanilla JS, no build step)
static/                 Modular JS files
docs/                   Governance + roadmap + audit replies + specs
scripts/                Verification + validation scripts
```

### The Central Loop

```
Organizational Event (Slack, GitHub, Jira, Gmail, CRM, Meeting Audio)
    ↓
Evidence (EvidenceBuilder → Evidence Spine with 13 epistemic types)
    ↓
Interpretation (ContentEpistemicClassifier — content-driven, not signal-type-driven)
    ↓
Situation (SituationBuilder — 27 fields from real signal data)
    ↓
Memory (SQLite: WhisperHistoryStore, ConversationStore, InteractionMemory, OutcomeLedger)
    ↓
Preparation (PreparationEngine + CalendarAwarenessEngine — calendar-driven)
    ↓
Whisper or Silence (decide_delivery — 7 options, governed by active policy)
    ↓
Question (AskPipeline — 9 intents + 4 investigation handlers: Why? / Show evidence /
         What don't we know? / What should I ask?)
    ↓
Decision (DecisionV2 — lifecycle with hypothesis linking)
    ↓
Outcome (OutcomeRecorder → OutcomeLedger (durable, tenant-scoped) → AttributionAnalyzer)
    ↓
Learning (PolicyProposer → risk-tiered: LOW auto-activates, HIGH needs approval)
    ↓
Changed Future Behavior (PolicyVersionStore → decide_delivery reads active policy)
```

## Key Capabilities

| Capability | Status | API |
|---|---|---|
| Whisper delivery gate (7 options) | ✅ Wired | `GET /api/oem/whisper` |
| Ask Maestro (9 intents + 4 investigation handlers + citations) | ✅ Wired | `POST /api/oem/ask/conversation` |
| Preparation Engine (13 modules) | ✅ Wired | `GET /api/oem/preparation/tomorrow` |
| Governed adaptation loop (OutcomeLedger — durable, tenant-scoped) | ✅ Wired | `POST /api/oem/loop1/outcome` |
| Commitment extraction + escalation (free text + 24/7 monitoring) | ✅ Wired | Via `OEMEngine.ingest()` |
| Content epistemic classifier (13 types: 10 original + tentative, sarcasm, artifact) | ✅ Wired | Via `EvidenceBuilder` |
| Interaction memory (8 states) | ✅ Wired | `POST /api/oem/loop1/action` |
| LLM narrator (constrained, fail-closed) | ✅ Wired | Via `AskPipeline` |
| Prompt injection defense (7 categories) | ✅ Wired | Via `OEMEngine.ingest()` |
| Source authority weighting | ✅ Wired | Via `OEMEngine.ingest()` |
| Today surface (7 engines) | ✅ Wired | `GET /api/personal/today` |
| **Live Copilot: Pre-call intelligence** | ✅ Wired | `POST /api/copilot/pre-call` |
| **Live Copilot: Live meeting intelligence** | ✅ Wired | `WS /ws/copilot` |
| **Live Copilot: Post-call summary** | ✅ Wired | `POST /api/copilot/post-call` |
| **Ambient: Calendar awareness (24/7, prep gap alerts)** | ✅ Built | `CalendarAwarenessEngine` |
| **Ambient: Commitment escalation (failure prediction)** | ✅ Built | `CommitmentEscalationEngine` |
| **Ambient: Sentiment tracking (5 patterns, RAVDESS validation)** | ✅ Built | `SentimentPatternEngine` |
| **Ambient: Deal health score (4-component weighted)** | ✅ Built | `DealHealthEngine` |
| **Ambient: Negotiation pattern detector (historical reference)** | ✅ Built | `NegotiationStrategyEngine` |
| **Ambient: Cross-meeting threads (70-80%, manual correction)** | ✅ Built | `CrossMeetingThreadBuilder` |
| **Ambient: Talk ratio coach (capability not dominance)** | ✅ Built | `TalkRatioCoach` |
| **Ambient: Meeting grade (A-F, transparent, user override)** | ✅ Built | `MeetingGrader` |
| **Ambient: Workplace signals (enterprise, 7 safeguards)** | ✅ Built | `WorkplaceSignalFusion` |
| **Ambient: Multi-language (8 languages, accent-aware DEFERRED)** | ✅ Built | `MultiLanguageSupport` |
| **Ambient: Notifications (DND, quiet hours, fatigue prevention)** | ✅ Built | `AmbientNotificationEngine` |
| **Ambient: Advanced analytics (trends, team, org learning)** | ✅ Built | `AdvancedAnalyticsEngine` |

## Maestro Live Copilot

A Chrome MV3 browser extension providing real-time meeting intelligence.

**Scene 1 (Pre-Call):** When the user opens a Google Meet / Zoom / Teams lobby, the side panel surfaces attendee intelligence (interaction count, commitment status, last gap), suggested talking points (each citing organizational data), and risk factors — all from the OEM signal history.

**Scene 2 (Live):** During the call, the `LiveIntelligenceEngine` processes transcript chunks and produces 4 color-coded card types:
- **Objection detected** (rose #FF5577) — response cites validated organizational runtimes
- **Commitment detected** (amber #FFB84D) — deduped against CommitmentTracker (Day X/Y)
- **Organizational whisper** (purple #7C5CFF) — cross-validated evidence chain
- **Historical pattern** (cyan #5CC8FF) — resembles a past meeting

Every card has a confidence bar (P25: <10 samples = "insufficient calibration history"), an evidence chain, and action buttons.

**Scene 3 (Post-Call):** Hero summary, key stats, commitments tracked, draft follow-up email (citing specific commitments), and "What Maestro learned" (new signals ingested, pattern data-point count, law-promotion threshold).

**Consent-first:** `ConsentManager.checkConsent()` gates every `getDisplayMedia` call. Consent is per-session, revocable, and audit-logged. No unconsented capture is possible.

## Maestro Ambient Intelligence

12 always-on engines that work between calls — the layer that makes Maestro a category, not a feature.

| Engine | What it does | Reality Check |
|---|---|---|
| Calendar Awareness | 24/7 calendar monitoring, preparation gap alerts, meeting cluster detection | ✅ REALISTIC |
| Commitment Escalation | 24/7 commitment monitoring, failure prediction ("73% failure rate"), nudges | ✅ REALISTIC |
| Sentiment Tracking | 5 emotional patterns (escalating frustration, sudden positivity, divergence, fatigue, stress spike) | ⚠️ 70-75% real-world accuracy; "emotional cues" not "emotion detection" |
| Deal Health Score | 4-component weighted score (commitment + sentiment + relationship + historical) | ⚠️ "Deal momentum" not "deal health"; 60-70% accuracy |
| Negotiation Pattern Detector | BATNA comparison, anchoring detection, concession tracking | ❌ Downgraded to "historical reference" (AI can't understand intent) |
| Cross-Meeting Threads | Topic linking, decision chain tracking, topic evolution | ⚠️ 70-80% accuracy; <70% requires user confirmation |
| Talk Ratio Coach | Speaking time, interruptions, clarity scoring, coaching suggestions | ✅ REALISTIC (capability-building, not dominance) |
| Meeting Grade | A-F effectiveness score, 4 transparent factors, user override | ✅ REALISTIC |
| Workplace Signals | Enterprise email/Slack signal fusion with 7 privacy safeguards | ✅ Enterprise model (GDPR Art. 6 + 21) |
| Multi-Language | 8 languages, translation suggestions, cultural context | ⚠️ Multi-language yes, accent-aware DEFERRED |
| Ambient Notifications | Smart nudges, DND, quiet hours, fatigue prevention | ✅ REALISTIC |
| Advanced Analytics | Trend analysis, team performance (aggregate), org learning metrics | ✅ REALISTIC |

**Killed:** Relationship Dynamics Mapper (invasive, inaccurate, potentially offensive).

## Governance

The codebase is governed by 34 anti-entropy principles in a mutual governance loop:
- `GOVERNANCE_LOOP.md` — mutual read protocol (both sides read from disk, paste read receipts)
- `ENTROPY_RECOVERY.md` — 34 principles (Part One: P1-P10, Part Two: P11-P15, Part Three: P16-P19, Part Four: P20-P26, Part Five: P27-P34)
- `AUDITOR_GOVERNANCE.md` — 20 pre-audit gates + 7 post-audit checks
- `audit_scripts/audit_gates.sh` — enforcement script (Gate 11: HEAD must match origin/main)

The coder and auditor hold each other accountable. Neither side can skip the gate. The CEO rejects any message without a read receipt.

## Testing

```bash
cd backend
export MAESTRO_LOCAL_DEV=true
export MAESTRO_DEMO_SEED=true

# Run the Live Copilot + Ambient Intelligence test suite (199 tests)
python -m pytest maestro_oem/tests/test_copilot_e2e.py \
  maestro_oem/tests/test_phase9_ambient.py \
  maestro_oem/tests/test_sentiment_patterns.py \
  maestro_oem/tests/test_deal_health.py \
  maestro_oem/tests/test_negotiation_strategy.py \
  maestro_oem/tests/test_cross_meeting_threads.py \
  maestro_oem/tests/test_talk_ratio_coach.py \
  maestro_oem/tests/test_meeting_grader.py \
  maestro_oem/tests/test_workplace_signals.py \
  maestro_oem/tests/test_multilang_support.py \
  maestro_oem/tests/test_ambient_notifications.py \
  maestro_oem/tests/test_advanced_analytics.py -v

# Run the full backend suite
python -m pytest maestro_oem/tests/ maestro_api/tests/ maestro_auth/tests/
```

## Production Deployment

**Not yet recommended for production.** The system needs:
1. A live SaaS deployment (no deployment URL exists yet)
2. Real OAuth connectors tested with live APIs
3. Postgres migration for multi-instance reliability
4. Shadow deployment with one design partner

When ready:
```bash
export DATABASE_URL=postgresql://user:pass@host:5432/maestro
export MAESTRO_ENV=production
export MAESTRO_MASTER_KEY=<fernet-key>
export MAESTRO_DEMO_SEED=false
export MAESTRO_DEFAULT_RECIPIENT=exec@yourcompany.com

cd backend && alembic upgrade head
uvicorn maestro_api.main:create_app --factory --port 8001
```

## Audit History

3 independent external audits conducted. All CRITICAL and HIGH findings from the forensic audit fixed. 9 of 11 procurement findings fixed (3 require infrastructure).

| Audit | Type | Lines | Verdict | Findings Fixed |
|---|---|---|---|---|
| Audit 1 | Forensic (code + coherence) | 1,232 | PROMISING PROTOTYPE / SHADOW MODE ONLY | 9/9 |
| Audit 2 | Brutal QA | 275 | NO — close to ABSOLUTELY NOT | Folded into 1+3 |
| Audit 3 | Fortune 100 procurement | 686 | ABSOLUTELY NOT | 9/11 (3 require infrastructure) |

A reality check (567 lines) reviewed all 12 ambient features: 5 REALISTIC, 4 PARTIALLY REALISTIC (with caveats), 3 UNREALISTIC (1 killed, 1 downgraded, 1 revived with enterprise model).

## License

MIT — see [LICENSE](LICENSE).
