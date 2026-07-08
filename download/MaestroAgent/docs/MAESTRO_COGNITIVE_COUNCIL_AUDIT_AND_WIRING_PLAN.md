# Maestro Cognitive Council — Capability Audit & Wiring Plan

> **Status**: Audit complete. No production code written yet. This document proposes the thin Situation layer and wiring plan.
> **Issued**: 2026-07-08, in response to CEO directive: "Audit the existing capabilities, identify the missing connective tissue, and evolve the current architecture into a shared Situation lifecycle without duplicating engines."
> **Method**: Three parallel Explore agents audited every named capability in the CEO directive against actual source code (not just grep). Each finding below is verified by reading the real implementation.

---

## Executive Summary

**The CEO was exactly right.** Maestro already has ~80% of the cognitive capabilities the Cognitive Council needs. The missing piece is NOT six new engines. The missing piece is:

1. **A thin Situation layer** that organizes cognition over existing OEM memory (references, not copies)
2. **A real lifecycle state machine** with continuous state transition (the biggest gap)
3. **Wiring** — connecting existing engines through Situation into a continuous loop
4. **4 unwired modules** that are real, tested, but bypassed in production (`LayeredOutcomeResolver`, `GovernanceGate.evaluate_for_pattern_candidate()`, `ReplicationMetrics`, `ExecutiveExperienceFormatter`)
5. **Evidence states** replacing confidence adjectives (DIRECTLY_SUPPORTED, SUPPORTED_WITH_GAPS, CONTESTED, PRELIMINARY, INSUFFICIENT_EVIDENCE)
6. **Decision boundary** as a first-class Judgment output
7. **Opportunity cost model** in the Delivery Governor
8. **Consequence-path routing** replacing keyword routing

**The proof is not that every proposed class exists. The proof is that one organizational situation changes correctly over time and causes Ask, Prepare, Whisper, Briefing, and Learning to behave coherently from the same underlying state.**

---

## What Already Exists (Verified Real)

### Situation Engine Precursors — ALL REAL

| Proposed Capability | Existing Implementation | Real? | Tests |
|---------------------|------------------------|-------|-------|
| Temporal workspaces | `TimeAxisEngine` (time_axis.py), `TrajectoryInterventionEngine` (trajectory_intervention.py), `LivingSituation.timeline` | ✅ Real | Partial (no dedicated test_time_axis.py) |
| Entity retrieval | `SituationBuilder.build_for_entity()` (27-field snapshot), `RecallEngine` (semantic+temporal hybrid), `AskPipeline` (entity-scoped state) | ✅ Real, strong | ✅ test_phase2_entity_scoping, test_c2_ask_signal_window, test_h3_ask_pipeline |
| Cross-meeting threads | `CrossMeetingThreadBuilder` (381 lines, 70-80% accuracy, user confirmation for <70%) | ✅ Real, comprehensive | ✅ test_cross_meeting_threads (10+ tests) |
| Commitment history | `CommitmentMutationTracker` (SQLite, immutable), `CommitmentTimelineSimulator` (pattern classifier, 60-day projection, P13-compliant) | ✅ Real, excellent | ✅ test_commitment_timeline_simulator (9 adversarial tests) |
| Relationship reasoning | `CustomerJudgmentEngine.relationship_drift()` (130-line method, 7 metrics), `CustomerScenarioEngine` (7 scenario types), `RelationshipVault` (consent-gated) | ✅ Real, strong | ✅ test_customer_judgment (13 tests), test_phase_b_preparation_wiring |

**Plus**: `LivingSituation` already exists (`maestro_cognitive_council/situation_engine.py`, 664 lines, 9 tests) — built last turn. It has a 7-state lifecycle, 10 epistemic states, 6 delivery routes, timeline, known_facts, unknowns, perspectives, disagreements, judgment.

### Judgment Synthesizer Precursors — MOSTLY REAL

| Proposed Capability | Existing Implementation | Real? | Tests |
|---------------------|------------------------|-------|-------|
| EvidenceReasoner | `CoverageAssessor` (10-check reasoner), `EvidenceGraph` (directed graph, BFS), `EvidenceBuilder` (provenance, claim_type) | ✅ Real | ✅ test_coverage_assessor, test_evidence_graph |
| RuleBasedSynthesizer | `RuleBasedSynthesizer.synthesize()` (235 lines, 4-section output, wired to Ask path) | ✅ Real | ✅ test_production_fallback_and_circuit |
| ClaimVerifier | **DOES NOT EXIST** — only aspirational comments. `ContentEpistemicClassifier` (13 types) is the de-facto substitute | ❌ Stub | ✅ test_content_epistemic_classifier |
| Contradiction detection | `ContradictionEngine` (507 lines, Bayesian), `ContradictionDetector` (4 violation types), `DisagreementDetector` (epistemic-type resolution) | ✅ Real, 3 implementations | ✅ test_contradiction (15+ tests), test_contradiction_edge_cases |
| Counterevidence concepts | `Evidence.conflicting_evidence`, `CustomerImpactReport.counter_evidence`, `Perspective.counterevidence` | ✅ Real as data model | ⚠️ Partial (no dedicated counterevidence-search engine) |
| PerspectiveEngine | `PerspectiveEngine.translate()` (236 lines, 6 perspectives × 10 event types = 60 templates) | ✅ Real | ✅ test_phase2::TestPerspectiveEngine |
| Team translations | `terminology_translation.translate_internal_terms()` (130 lines, API-boundary sanitizer) | ✅ Real (but different concept — term sanitization, not team-to-team) | ✅ test_m4_terminology_translation |

### Delivery Governor Precursors — ALL REAL

| Proposed Capability | Existing Implementation | Real? | Tests |
|---------------------|------------------------|-------|-------|
| Whisper delivery logic | `OrganizationalWhisper.for_context()` (1468 lines), `delivery_decision.decide_delivery()` (7-option gate), `WhisperPrioritizer`, `RecipientRouter`, `WhisperHistoryStore` | ✅ Real, most mature subsystem | ✅ test_phase6_whisper_delivery, test_critical01_delivery_gate_wired |
| Interrupt Intelligence | `InterruptEngine.evaluate()` (220 lines, 5-level priority, ARR escalation, cognitive-load suppression) | ✅ Real | ⚠️ Only route integration tests (no dedicated unit tests) |
| Cognitive load controls | `CognitiveLoadEngine.compute()` (307 lines, 7 weighted factors, OCL score) | ✅ Real | ⚠️ Only route integration tests |

### Preparation Workspace Precursors — REAL

| Proposed Capability | Existing Implementation | Real? | Tests |
|---------------------|------------------------|-------|-------|
| Preparation Engine | **TWO engines**: `preparation_engine.PreparationEngine.prepare_for_tomorrow()` (Chief-of-Staff, 724 lines, 6 wired modules) + `preparation.PreparationEngine.prepare_all()` (5 packet types) | ✅ Real (both) | ✅ test_preparation_phase3, test_phase_b_preparation_wiring |
| Prepared Decisions | `PreparedDecisionEngine.prepare()` (145 lines, personal mode, risk templates) | ✅ Real but light | ✅ test_phase2_3_completion::TestPreparedDecisions |
| Decision briefs | **DOES NOT EXIST** by that name. Closest: `Preparation` with `customer_brief`, `briefing.py`'s `drafted_artifacts` | ❌ Not unified | ✅ test_drafted_briefing (covers the analog) |

### Learning Closure Precursors — REAL BUT PARTIALLY UNWIRED

| Proposed Capability | Existing Implementation | Real? | Wired to production? |
|---------------------|------------------------|-------|---------------------|
| PatternProposer | `PatternProposer.propose()` (deterministic, 10 hypothesis templates, wired to AskPipeline) | ✅ Real | ✅ Wired (ask_pipeline.py:994) |
| CandidatePatternStore | `SQLiteCandidatePatternStore` (481 lines, 3 tables, tenant-isolated, durable) | ✅ Real | ✅ Wired (main.py lifespan) |
| ObservationCase | `ObservationCase` + `CaseFingerprintBuilder` (deterministic dedup, evidence-lineage detection) | ✅ Real | ✅ Wired (empirical_loop.py:228) |
| OutcomeResolver | `OutcomeResolver.resolve_pending()` (production) + `LayeredOutcomeResolver` (7-layer, UNWIRED) | ✅ Both real | ⚠️ Simple one wired; layered one NOT wired |
| Prospective prediction | `register_prospective_prediction_from_case()` (freezes evidence, rejects duplicates) | ✅ Real | ✅ Wired |
| Calibration | `CalibrationEngine` (10-bucket, Brier, drift) + `CandidatePattern.calibration_score` (single float) | ✅ Both real | ⚠️ **Two parallel systems, not connected** |
| ScopeRegime | `ScopeRegime` dataclass | ✅ Real (as dataclass) | ❌ **Dead code** — production uses fields directly on CandidatePattern |
| GovernanceGate | `GovernanceGate.evaluate_for_pattern_candidate()` (6 criteria) | ✅ Real | ❌ **NOT WIRED** — production `governance_approve()` does simpler inline check |
| ReplicationMetrics | `compute_replication_metrics()` (separates evidence/replication/calibration) | ✅ Real | ❌ **NOT WIRED** — only used by unwired GovernanceGate |

---

## The 4 Unwired Modules (Highest-Leverage Wiring Opportunities)

These are real, tested modules that exist but are bypassed in production. Wiring them is the single highest-leverage action — they implement the scientific rigor the CEO wants, but the live system doesn't consult them.

| Module | What It Does | Why It's Not Wired | Wiring Action |
|--------|-------------|-------------------|---------------|
| **`LayeredOutcomeResolver`** | 7-layer outcome resolution (structured events → negation → disputed → future → ambiguous → indirect → explicit assertion) | Production uses simpler `_signal_matches_outcome()` | Replace the simple matcher in `OutcomeResolver.resolve_pending()` with the layered resolver. This is "Priority Zero" — prefer NOT LEARNING over learning falsely. |
| **`GovernanceGate.evaluate_for_pattern_candidate()`** | 6-criteria evaluation (sufficient supports, replication, calibration, no contradictions, data coverage, not confounded) | Production `governance_approve()` only checks `status == TESTING` | Call `evaluate_for_pattern_candidate()` inside `governance_approve()` and surface its recommendation. |
| **`ReplicationMetrics`** | Separates evidence_strength / replication_strength / predictive_calibration (the auditor's "no decorative precision" rule) | Production uses single `calibration_score` float | Replace `CandidatePattern.calibration_score` with `ReplicationMetrics` (or expose both). |
| **`ExecutiveExperienceFormatter`** | Honest-uncertainty language ("Maestro is watching a possible pattern…") | No route surfaces it | Wire it into the Ask answer formatter and the briefing generator. |

---

## The Two Parallel Calibration Systems (Must Be Unified)

| System | Tracks | Wired To |
|--------|--------|----------|
| `CalibrationEngine` (learning.py) | 10-bucket reliability diagram, Brier score, drift detection | `prediction_lifecycle.py` (recommendations/simulations/risk) |
| `CandidatePattern.calibration_score` | Single float, inline computed | Empirical loop (candidate patterns) |

**They do not share data.** This is the auditor's "two truth" problem. The fix: connect `CalibrationEngine` to candidate-pattern resolutions so the 10-bucket reliability diagram tracks ALL predictions, not just recommendation predictions.

---

## What's Actually Missing (The Connective Tissue)

### 1. Situation as Thin Cognitive Frame (references, not copies)

**Current state**: `LivingSituation` (built last turn) copies evidence and facts into the situation object. The CEO directive says this creates truth drift.

**What's needed**: Refactor `LivingSituation` to hold **references** (`evidence_refs`, `commitment_refs`, `decision_refs`, etc.) instead of copies. The OEM remains source of record. Situation organizes cognition over OEM memory.

```python
# CURRENT (wrong — copies):
class LivingSituation:
    known_facts: list[KnownFact]  # copies of facts
    commitments: list[dict]       # copies of commitments

# PROPOSED (right — references):
class LivingSituation:
    evidence_refs: list[str]      # IDs into OEM
    commitment_refs: list[str]    # IDs into OEM
    decision_refs: list[str]      # IDs into OEM
    # Situation-specific cognition only:
    unknowns: list[Unknown]
    current_interpretations: list[Interpretation]
    material_changes: list[Change]
```

### 2. Continuous State Transition (the biggest gap)

**Current state**: `LivingSituation` has a 7-state lifecycle, but transitions are manual (`transition_to()`). There's no logic that says "new evidence X causes transition from OBSERVING to MATERIAL because Y."

**What's needed**: The full CEO-specified state machine with transition logic:

```
DETECTED → OBSERVING → MATERIAL → NEEDS_PREPARATION → DECISION_PENDING →
ACTION_IN_PROGRESS → AWAITING_OUTCOME → RESOLVED → LEARNING → ARCHIVED

Side states: DISPUTED, BLOCKED, STALE, SUPERSEDED, INSUFFICIENT_EVIDENCE
```

Each transition must be **justified** (reason + evidence). The Globex example (Day 12 → 40 → 50 → 55 → 59) is the acceptance test.

### 3. Evidence States (not confidence adjectives)

**Current state**: `Judgment.confidence` is a float 0.0-1.0 with labels "high/moderate/low."

**What's needed**: Replace with evidence states that explain WHY certainty is limited:

```python
class EvidenceState(str, Enum):
    DIRECTLY_SUPPORTED = "directly_supported"      # evidence directly backs the claim
    SUPPORTED_WITH_GAPS = "supported_with_gaps"    # evidence backs it but key facts missing
    CONTESTED = "contested"                        # credible evidence conflicts
    PRELIMINARY = "preliminary"                    # early-stage, could change
    INSUFFICIENT_EVIDENCE = "insufficient_evidence" # not enough to say
```

### 4. Decision Boundary (what can be decided now vs. not yet)

**Current state**: `Judgment` has `recommended_next_step` but no concept of "what can be decided now vs. what cannot yet be decided."

**What's needed**: Add `decision_boundary` to `Judgment`:

```python
class DecisionBoundary:
    can_decide_now: list[str]
    cannot_decide_yet: list[str]
    why: str
    smallest_useful_next_step: str
```

### 5. Consequence-Path Routing (not keyword routing)

**Current state**: `SituationEngine.route_specialists()` uses keyword matching (`SPECIALIST_DOMAIN_MAP`).

**What's needed**: Route based on organizational consequence paths. The router asks:
- Who owns the object?
- Who depends on it?
- Who can veto it?
- Who absorbs failure?
- Who made commitments about it?
- Who has relevant precedent?
- Who must communicate the outcome?

This traverses the organizational relationship graph (which `CustomerJudgmentEngine.buying_committee()` and `relationship_drift()` already model).

### 6. Opportunity Cost Model in Delivery Governor

**Current state**: `DeliveryGovernor` uses fatigue caps + urgency + meeting state.

**What's needed**: Add intervention value vs. interruption cost:

**Surface now if:**
- delay materially reduces options
- decision is imminent
- new evidence invalidates preparation
- user is about to act on stale assumptions
- situation has crossed a previously stated boundary

**Remain silent if:**
- information is merely interesting
- user cannot act yet
- nothing materially changed
- same issue was recently surfaced
- evidence is still preliminary
- another upcoming surface is better

### 7. Fatigue / Focus Sensors (currently missing)

**Current state**: `DeliveryGovernor.UserContext` accepts `is_in_focus_mode` and `fatigue_level`, but nothing in `maestro_oem` produces them. `CognitiveLoadEngine` produces a 0-100 OCL score (which `InterruptEngine` uses), but that's not the same as fatigue or focus mode.

**What's needed**: Either (a) derive `fatigue_level` from `CognitiveLoadEngine.score` (OCL > 70 = fatigue > 0.7), or (b) add explicit focus-mode tracking.

---

## The Thin Situation Layer Proposal

### Design Rule

> **Situation organizes cognition. It does not duplicate organizational memory. The OEM remains the source of record. Situation is a dynamically maintained cognitive frame over OEM memory.**

### Proposed `LivingSituation` (revised — thin, references)

```python
@dataclass
class LivingSituation:
    # Identity
    situation_id: str
    title: str
    tenant_id: str

    # Lifecycle (the biggest gap — must be real)
    state: SituationState          # DETECTED → OBSERVING → MATERIAL → ... → ARCHIVED
    state_history: list[StateTransition]  # every transition with reason + evidence
    opened_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime]

    # REFERENCES to OEM (NOT copies)
    entity_refs: list[str]         # customer/entity IDs
    intent_refs: list[str]         # intent IDs in OEM
    commitment_refs: list[str]     # commitment IDs in OEM
    decision_refs: list[str]       # decision IDs in OEM
    evidence_refs: list[str]       # evidence IDs in EvidenceGraph
    hypothesis_refs: list[str]     # CandidatePattern IDs
    meeting_refs: list[str]        # meeting IDs
    relationship_refs: list[str]   # relationship IDs

    # Situation-specific cognition (NOT in OEM — only in Situation)
    unknowns: list[Unknown]                # what's not yet established
    current_interpretations: list[Interpretation]  # what we currently believe + why
    material_changes: list[Change]         # what changed recently

    # Lifecycle sub-states
    delivery_state: DeliveryState          # silent/ask/briefing/whisper/prepare/urgent
    learning_state: LearningState          # untested/observing_evidence/supported/contested/falsified

    # Perspectives + Judgment (transient — recomputed per query)
    perspectives: list[Perspective]        # contributed by specialists (references evidence_refs)
    judgment: Optional[Judgment]           # synthesized (includes decision_boundary)
```

### What This Changes

1. **No truth duplication** — Situation holds refs, OEM holds the actual evidence/commitments/decisions
2. **State transitions are first-class** — every transition is logged with reason + evidence
3. **Learning state is tracked** — Situation knows whether its central hypothesis is untested/supported/contested/falsified
4. **Perspectives and Judgment are transient** — they're recomputed per query, not stored as truth

---

## The Wiring Plan (4 Gates)

### Gate 1: Living Situation (Weeks 1-4)

**Build:**
1. Refactor `LivingSituation` to use references (not copies)
2. Implement the full state machine with transition logic + `StateTransition` logging
3. Wire `SituationEngine` to consume from existing precursors:
   - `CommitmentMutationTracker.get_mutation_history(entity)` → commitment_refs + timeline
   - `CrossMeetingThreadBuilder.get_threads_for_entity(entity)` → meeting_refs + decision_chain
   - `CustomerJudgmentEngine.relationship_drift(customer)` → relationship_refs + unknowns
   - `SituationBuilder.build_for_entity(entity)` → entity context (reuse, don't duplicate)
4. Implement Situation Delta (compute changes when new signals arrive)
5. Implement Situation Query (find relevant situations)

**Acceptance criterion:**
```
new signal
→ correct situation found
→ delta computed
→ state transition justified (reason + evidence)
→ unknowns updated
→ no future leakage
```

**Test with the Globex timeline (Day 12 → 40 → 50 → 55 → 59).**

### Gate 2: Shared Judgment (Weeks 5-8)

**Build:**
1. Consequence-path router (replace keyword routing) — traverse organizational relationship graph
2. Wire `DisagreementDetector` into `JudgmentSynthesizer.detect_disagreements()` (reuse, don't rebuild)
3. Wire `CoverageAssessor` into missing-evidence detection (reuse)
4. Wire `RuleBasedSynthesizer` structure into `Judgment` output (reuse)
5. Add `decision_boundary` to `Judgment`
6. Replace confidence adjectives with evidence states

**Acceptance criterion:**
```
situation
→ relevant perspectives selected (via consequence paths)
→ disagreement preserved (via DisagreementDetector)
→ dependencies identified
→ counterevidence searched (via CoverageAssessor)
→ unknowns stated
→ decision boundary produced
→ evidence state explained
```

### Gate 3: Contextual Delivery (Weeks 9-12)

**Build:**
1. Add opportunity cost model to `DeliveryGovernor` (intervention value vs interruption cost)
2. Wire `CognitiveLoadEngine` → `UserContext.fatigue_level` (derive fatigue from OCL score)
3. Wire `InterruptEngine` logic into `DeliveryGovernor` (unify the two parallel delivery systems)
4. Wire `delivery_decision.decide_delivery()` (7-option) into the 6-route taxonomy
5. Delivery state tracking (what was delivered when?)

**Acceptance criterion:**
```
The same Situation produces different behavior depending on
timing and context without contradicting itself.
```

### Gate 4: Behavioral Learning (Weeks 13-16)

**Build (WIRING, not new engines):**
1. Wire `LayeredOutcomeResolver` into `OutcomeResolver.resolve_pending()` (Priority Zero — prefer not learning over learning falsely)
2. Wire `GovernanceGate.evaluate_for_pattern_candidate()` into `CandidatePatternStore.governance_approve()`
3. Replace `CandidatePattern.calibration_score` with `ReplicationMetrics`
4. Connect `CalibrationEngine` (learning.py) to candidate-pattern resolutions (unify the two parallel calibration systems)
5. Wire `CandidatePatternStore` into `PreparationEngine` (surface learned insights in preparation briefs)
6. Wire `ExecutiveExperienceFormatter` into Ask + Briefing outputs
7. Connect Situation → Preparation Engine → Prepared Decision → Decision event → ObservationCase → OutcomeResolver → empirical loop → Situation learning state updated

**Acceptance criterion:**
```
Situation A → judgment → action → outcome
Situation B → precedent recognized → prior learning applied carefully
Situation C → contradictory outcome → prior belief weakened
Situation D → enough independent contradiction → belief suspended or falsified
```

---

## The World Model Benchmark (Acceptance Criterion)

**Not 100 unit tests. 10 brutal longitudinal organizational stories:**

1. Customer commitment drift (Globex renewal)
2. Security prerequisite failure (OAuth conditional approval)
3. Pricing exception leakage (enterprise discount precedent)
4. Hiring-plan assumption collapse (budget cut mid-quarter)
5. Product launch scope mutation (feature creep across teams)
6. Duplicate work across teams (two teams building same API)
7. Expert bottleneck emergence (Priya becomes single point of failure)
8. Legal interpretation disagreement (contract ambiguity)
9. Incident pattern that turns out to be coincidence (false pattern)
10. Previously learned pattern becoming false after reorganization (falsification)

**Each story unfolds across 30-90 simulated days. At each checkpoint:**
```
What does Ask say?
Does Prepare activate?
Does Whisper stay silent?
What does Briefing include?
What is currently unknown?
What changed?
What is disputed?
What can be decided?
What cannot yet be decided?
What does Maestro believe?
Why?
What would change that belief?
```

---

## What I Will NOT Build

Per the CEO directive:

- ❌ `preparation_v2.py`
- ❌ `learning_closure.py`
- ❌ `new_calibration_engine.py`
- ❌ `new_pattern_store.py`
- ❌ `new_outcome_store.py`
- ❌ Any new engine that duplicates an existing capability

## What I WILL Build

1. **Thin Situation layer** (references, not copies) — refactor existing `LivingSituation`
2. **State machine with transition logic** — the biggest missing capability
3. **Wiring** — connect existing engines through Situation
4. **4 unwired modules wired** (`LayeredOutcomeResolver`, `GovernanceGate`, `ReplicationMetrics`, `ExecutiveExperienceFormatter`)
5. **Evidence states** replacing confidence adjectives
6. **Decision boundary** as first-class Judgment output
7. **Consequence-path routing** replacing keyword routing
8. **Opportunity cost model** in Delivery Governor
9. **World Model Benchmark** (10 longitudinal stories)

---

## Constitutional Test (Retained)

> A new intelligence capability is not complete when it produces an output.
> It is complete only when it can **improve a real human decision, explain the evidence behind that improvement, observe the result, and use the result to improve future judgment.**

The proof is not that every proposed class exists.

The proof is that **one organizational situation changes correctly over time and causes Ask, Prepare, Whisper, Briefing, and Learning to behave coherently from the same underlying state.**
