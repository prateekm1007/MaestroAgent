# MaestroAgent — The Living Intelligence Layer for Organizations

**An enterprise cognitive intelligence platform that develops an increasingly disciplined model of what your organization knows, believes, assumes, predicts, disputes, learns, and forgets.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://img.shields.io/badge/CI-328%20tests%20passing-brightgreen.svg)](https://github.com/prateekm1007/MaestroAgent)

## What This Is

Maestro is not "17 AI agents." It is not a dashboard. It is a **Living Intelligence Layer for Organizations** — a system where specialists contribute perspectives to SITUATIONS, not insights to a feed.

The product unit is not `Agent → Insight`. It is:

```
Situation → evidence → perspectives → disagreement → unknowns →
judgment → intervention → outcome → learning → changed future judgment
```

A **Situation** is the living object. Everything else serves it.

### The Central Loop

```
PERCEIVE → UNDERSTAND → REMEMBER → QUESTION → PREPARE →
OBSERVE OUTCOME → LEARN → CHANGE FUTURE JUDGMENT
```

The last arrow is the moat. A lot of AI products can answer "What happened?" A smaller group can answer "What should I do?" Maestro answers: *"The last three times your organization faced this situation, one approach worked twice and failed once. The failed case differed because Security entered after customer expectations had already been set. Security is already involved this time, so that earlier failure mechanism is less applicable."*

## Current State

**328 tests passing across 4 cognitive gates + ambient intelligence + Live Copilot + Nerve agents.**

- **Gate 0**: World Model Benchmark (10 longitudinal stories) + 4-Dimensional State Model
- **Gate 1**: Living Situation (thin references + state machine + Globex timeline proof)
- **Gate 2**: Shared Judgment (consequence-path routing + decision boundary + evidence states)
- **Gate 3**: Contextual Delivery (opportunity cost model + CognitiveLoadEngine wiring)
- **Gate 4**: Behavioral Learning (A→B→C→D learning arc + 4 unwired modules wired)
- 17 Nerve agents (Specialist Council) + daily briefings + dashboard API
- 12 Ambient Intelligence engines (calendar, commitments, sentiment, deal health, etc.)
- Live Copilot browser extension (pre-call, live, post-call meeting intelligence)
- F4 CRITICAL security fix (all copilot routes authenticated)
- Cross-feature compounding wired into production (3 links)
- Calibration infrastructure unified (shared primitives, separate populations)

### The Architectural Reframe (CEO Directive)

Maestro evolved from "17 agents + dashboard" into a **situation-centric intelligence layer**:

| Old (wrong) | New (right) |
|-------------|-------------|
| Agent → Insight | Situation → evidence → perspectives → judgment |
| 17 agent cards on a dashboard | One situation, multiple perspectives, coherent judgment |
| Confidence adjectives ("high/moderate/low") | Evidence states (DIRECTLY_SUPPORTED / SUPPORTED_WITH_GAPS / CONTESTED / PRELIMINARY / INSUFFICIENT_EVIDENCE) |
| Keyword-based specialist routing | Consequence-path routing (traverses organizational relationship graph) |
| Single-dimension state enum | 4 orthogonal dimensions (epistemic + operational + delivery + learning) |
| "Here are the facts" / "Here is my recommendation" | "Here is what reality currently permits you to decide" (decision boundary) |
| Fatigue caps only | Opportunity cost model (intervention value vs interruption cost) |

## The 4 Gates

### Gate 0: World Model Benchmark + 4-Dimensional State Model

**10 longitudinal stories** (30-90 simulated days each) prevent Globex overfitting:

1. Customer commitment drift
2. Security prerequisite failure
3. Pricing exception leakage
4. Hiring-plan assumption collapse
5. Product launch scope mutation
6. Duplicate work across teams
7. Expert bottleneck emergence
8. Legal interpretation disagreement
9. Incident pattern that's coincidence (false pattern)
10. Previously learned pattern becoming false after reorg (falsification)

**4 orthogonal state dimensions** (prevents impossible state combinations):

```
epistemic_state:    preliminary | supported | contested | insufficient | resolved
operational_state:  observing | decision_pending | action_in_progress | awaiting_outcome | closed
delivery_state:     silent | briefing_eligible | whisper_eligible | prepare_eligible | urgent
learning_state:     none | hypothesis_created | prospectively_testing | outcome_pending | learning_updated | falsified
```

### Gate 1: Living Situation

- **Thin references** (not copies) — Situation holds `_refs[]` to OEM objects; OEM remains source of record
- **Continuous state transition** — 10 primary + 5 side states with justified transitions
- **Globex timeline proof** — Day 12→40→50→55→59 with correct state transitions at each step
- **No future leakage** — situations don't bleed across entities

### Gate 2: Shared Judgment

- **Consequence-path routing** — traverses organizational relationship graph (not keywords)
- **Evidence states** — replaces confidence adjectives with explained certainty
- **Decision boundary** — "what can be decided now vs. what cannot yet be decided"
- **Disagreement preserved** — not converged away; the reasoning path matters
- **Wired existing modules**: DisagreementDetector, CoverageAssessor, RuleBasedSynthesizer

### Gate 3: Contextual Delivery

- **Opportunity cost model** — intervention value vs interruption cost
- **"The best Whisper system is not the one that discovers the most. It is the one whose silence users learn to trust."**
- **Wired CognitiveLoadEngine** → fatigue_level derivation
- **Unified InterruptEngine + delivery_decision** → 6-route taxonomy
- Same Situation produces different behavior by context (silent/prepare/whisper/briefing/urgent)

### Gate 4: Behavioral Learning

- **A→B→C→D learning arc** validated against ALL 10 benchmark stories:
  - A: hypothesis created → no outcomes
  - B: supporting outcomes → belief strengthened
  - C: contradicting outcomes → belief weakened
  - D: enough contradiction → belief falsified
- **4 unwired modules wired**:
  - `LayeredOutcomeResolver` (Priority Zero — prefer not learning over learning falsely)
  - `GovernanceGate.evaluate_for_pattern_candidate()` (6-criteria evaluation)
  - `ReplicationMetrics` (separates evidence/replication/calibration)
  - `ExecutiveExperienceFormatter` (deferred to Ask surface)
- **Calibration infrastructure unified** — shared primitives, separate populations

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

# Open the Nerve Dashboard (17 agents + daily briefings)
# Visit http://localhost:1420/nerve-dashboard
```

## Architecture

```
backend/
  maestro_cognitive_council/   The situation-centric intelligence layer
    - situation_engine.py      LivingSituation (thin refs + 4D state model + transitions)
    - perspective.py           Perspective contract (epistemic discipline)
    - judgment_synthesizer.py  Judgment synthesis (wires DisagreementDetector + CoverageAssessor)
    - delivery_governor.py     Delivery routing (opportunity cost + CognitiveLoadEngine)
    - consequence_path_router.py  Consequence-path specialist routing
    - behavioral_learning_engine.py  A→B→C→D learning arc (wires 4 unwired modules)
    - calibration_primitives.py  Shared calibration infrastructure
    - world_model_benchmark.py  10 longitudinal stories (Gate 0)
    - benchmark_types.py       Benchmark data structures

  maestro_nerve/               17 specialized agents (Specialist Council)
    - base_agent.py            BaseAgent with OEM integration
    - agents_revenue.py        Growth, Sales, Customer Success, Finance
    - agents_product.py        Product, Engineering, Marketing
    - agents_internal.py       HR, Legal, Operations, Support, Data, Security, Partnerships
    - agents_strategy.py       Strategy, Communications, Chief of Staff
    - daily_briefing.py        Morning/evening briefings + dashboard engine

  maestro_oem/                 Organizational Execution Model (the memory)
    - signal ingestion, law inference, pattern detection
    - SituationSnapshot (27 fields — canonical substrate)
    - commitment extraction + escalation engine
    - delivery decision gate (7 options, evidence-derived)
    - governed adaptation loop (OutcomeRecorder → OutcomeLedger → AttributionAnalyzer)
    - content epistemic classifier (13 types)
    - live intelligence engine (4 card types)
    - sentiment pattern engine (5 patterns)
    - deal health engine (4-component weighted score)
    - cross-meeting thread builder (70-80% accuracy)
    - meeting grader (A-F, transparent factors)
    - workplace signal fusion (enterprise, 7 privacy safeguards)
    - LayeredOutcomeResolver (7-layer outcome resolution — Priority Zero)
    - GovernanceGate (6-criteria pattern promotion)
    - ReplicationMetrics (separates evidence/replication/calibration)

  maestro_api/                 FastAPI routes (OEM, auth, copilot, nerve)
  maestro_db/                  SQLAlchemy 2.0 + sqlite3 fallback
  maestro_auth/                RBAC, OAuth, OIDC, SAML, SCIM, Fernet KMS
  maestro_personal/            Personal mode (opt-in, separate from work)

extension/                     Maestro Live Copilot browser extension
static/nerve-dashboard.html    Nerve dashboard (17 agents + briefings)
app.html                       Executive UI
docs/                          Governance + roadmap + audit replies + specs
```

### The 5-Layer Architecture

```
5. EXPERIENCE: Whisper · Ask · Prepare · Briefings · Decisions · Ambient
4. JUDGMENT: Situation understanding · Contradictions · Perspectives ·
             Missing evidence · Counterevidence · Decision boundary
3. LEARNING: Hypotheses · Predictions · Outcomes · Calibration ·
              Falsification · Governed promotion
2. ORGANIZATIONAL MEMORY: Intent · Commitments · Decisions · Evidence ·
                           Outcomes · Patterns · Laws · Relationships
1. PERCEPTION: GitHub · Jira · Slack · Email · Calendar · CRM · Meetings
```

The Specialist Council (17 agents) sits **horizontally across** this stack, not as a 6th layer.

## Key Capabilities

| Capability | Status | Gate |
|---|---|---|
| Living Situation (thin refs + state machine) | ✅ Wired | Gate 1 |
| Consequence-path routing | ✅ Wired | Gate 2 |
| Evidence states (not confidence adjectives) | ✅ Wired | Gate 2 |
| Decision boundary (what can be decided now) | ✅ Wired | Gate 2 |
| Opportunity cost delivery model | ✅ Wired | Gate 3 |
| CognitiveLoadEngine → fatigue wiring | ✅ Wired | Gate 3 |
| A→B→C→D learning arc | ✅ Wired | Gate 4 |
| LayeredOutcomeResolver (Priority Zero) | ✅ Wired | Gate 4 |
| GovernanceGate (6-criteria) | ✅ Wired | Gate 4 |
| ReplicationMetrics (separated) | ✅ Wired | Gate 4 |
| 17 Nerve agents (Specialist Council) | ✅ Wired | Nerve |
| Daily briefings (morning + evening) | ✅ Wired | Nerve |
| Nerve dashboard API | ✅ Wired | Nerve |
| Live Copilot (pre-call + live + post-call) | ✅ Wired | Copilot |
| 12 Ambient Intelligence engines | ✅ Built | Ambient |
| Whisper delivery gate (7 options) | ✅ Wired | OEM |
| Ask Maestro (9 intents + citations) | ✅ Wired | OEM |
| Governed adaptation loop | ✅ Wired | OEM |
| Cross-feature compounding (3 links) | ✅ Wired | Compounding |
| F4 auth (all copilot routes authenticated) | ✅ Fixed | Security |

## Governance

The codebase is governed by 34 anti-entropy principles in a mutual governance loop:
- `GOVERNANCE_LOOP.md` — mutual read protocol (both sides read from disk, paste read receipts)
- `ENTROPY_RECOVERY.md` — 34 principles (P1-P34)
- `AUDITOR_GOVERNANCE.md` — 20 pre-audit gates + 7 post-audit checks
- `audit_scripts/audit_gates.sh` — enforcement script (Gate 11: HEAD must match origin/main)

The coder and auditor hold each other accountable. Neither side can skip the gate. The CEO rejects any message without a read receipt.

## Testing

```bash
cd backend
export MAESTRO_LOCAL_DEV=true

# Run the Cognitive Council suite (200 tests)
python -m pytest maestro_cognitive_council/tests/ -v

# Run the Nerve agent suite (116 tests)
python -m pytest maestro_nerve/tests/ -v

# Run the full regression (328+ tests)
python -m pytest maestro_oem/tests/ maestro_api/tests/ maestro_auth/tests/ \
  maestro_cognitive_council/tests/ maestro_nerve/tests/ -q
```

## The Constitutional Test

> A new intelligence capability is not complete when it produces an output.
> It is complete only when it can **improve a real human decision, explain the evidence behind that improvement, observe the result, and use the result to improve future judgment.**

## License

MIT — see [LICENSE](LICENSE).
