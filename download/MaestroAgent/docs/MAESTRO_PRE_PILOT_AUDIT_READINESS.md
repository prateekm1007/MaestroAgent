# Maestro Pre-Pilot World-Class Product Audit — Pilot Readiness Criterion

> **Status**: SAVED AS ACCEPTANCE CRITERION — do NOT run until the 5 production surfaces are wired to the Cognitive Council.
> **Current State**: Cognitive Council passes at level 2 (unit tested, 200 tests). Audit demands level 4 (behaviorally effective on production paths). Gap: Ask, Prepare, Whisper, Briefing, Meeting surfaces are NOT wired to the Cognitive Council.
> **Saved**: 2026-07-08, by CEO directive

---

## The 5-Level Capability Model

```
1. EXISTS → 2. UNIT TESTED → 3. WIRED TO PRODUCTION → 4. BEHAVIORALLY EFFECTIVE → 5. LEARNING-CLOSED
```

Maestro's Cognitive Council is at **level 2** for most capabilities. The audit demands **level 4**.

---

## What Must Be Wired Before This Audit Can Run

### Surface 1: Ask → Situation Engine
Ask must:
- Retrieve the correct Situation (not just OEM signals)
- Reconstruct chronology from the Situation's timeline
- Distinguish fact from report (epistemic states)
- Preserve disagreement in the answer
- Cite evidence by reference (not copy)
- Surface unknowns ("What we don't know yet")

### Surface 2: Prepare → LivingSituation
Preparation must:
- Be Situation-aware (prepare FOR a specific Situation, not generic)
- Update as reality changes (stale preparation detection)
- Reference the Situation's unknowns and decision boundary
- Connect to the Behavioral Learning Engine (surface learned insights)

### Surface 3: Briefing → Situation Judgment
Briefing must:
- Answer "What materially changed?" (not "How many insights did each agent produce?")
- Be Situation-centric (one situation, its judgment, its decision boundary)
- Include learning state (what Maestro believes, why, what would change that)
- Apply the Delivery Governor's route (silent/ask/briefing/whisper/prepare/urgent)

### Surface 4: Whisper → Delivery Governor
Whisper must:
- Route through the Delivery Governor (not the old 7-option decide_delivery alone)
- Apply the opportunity cost model (intervention value vs interruption cost)
- Use the 4-dimensional state model (not the single-enum state)
- Explain WHY it's silent (transparency builds trust)

### Surface 5: Copilot → Situation Engine
Meeting intelligence must:
- Flow through Situations (not a separate LiveIntelligenceEngine)
- Update the Situation's operational state (OBSERVING → ACTION_IN_PROGRESS → AWAITING_OUTCOME)
- Feed commitments to the Situation's commitment_refs
- Trigger the Behavioral Learning Engine on call end

### Cross-Cutting: Tenant Isolation
The Cognitive Council's Situation Engine must:
- Enforce org_id scoping on all situation operations
- Prevent cross-tenant situation leakage
- Filter signals by org_id before situation detection

---

## Audit Structure (23 Parts, 15 Adversarial Tests, 5-Output Report)

### Part I: Establish Real Product
- Clean clone → deploy → test suite
- Lockfile required (reproducibility)
- Docker-compose Postgres wired
- **Gap**: No lockfile, no SaaS, docker-compose Postgres not fully wired

### Part II: The Core Claim
- What is Maestro's central claim?
- Trace the call graph from claim to production code

### Part III: Situation Coherence ✅ PASS (Gate 1)
- Signal → situation → delta → transitions → unknowns
- Globex timeline (Day 12→59) proves this

### Part IV: Ask Maestro ❌ NOT WIRED
- Executive questions with vague language, pronouns, follow-ups
- Ask must retrieve Situation, not just OEM signals

### Part V: Whisper ✅ PASS (Gate 3)
- When to speak, when to stay silent
- Opportunity cost model, silence-explained, 6 contextual routes

### Part VI: Prepare ❌ NOT WIRED
- Preparation that updates as reality changes
- Stale preparation detection not implemented

### Part VII: Shared Judgment ✅ PASS (Gate 2)
- Consequence-path routing, disagreement preservation

### Part VIII: Disagreement ✅ PASS
- Perspectives conflict, not collapsed to consensus

### Part IX: Decision Boundaries ✅ PASS
- What can/cannot be decided

### Part X: Evidence States ✅ PASS (Task 3)
- No decorative precision, evidence states replace confidence adjectives

### Part XI: Learning Integrity ⚠️ PARTIAL (Gate 4)
- Signal → hypothesis → outcome → calibration
- A→B→C→D arc proven, but tested with mocks, not real production data

### Part XII: Unlearning ✅ PASS
- Supported → weakened → falsified

### Part XIII: Calibration Science ✅ PASS (Task 3)
- No decorative precision, populations separate

### Part XIV: Briefing ❌ NOT WIRED
- "What materially changed?" not a digest
- Nerve briefing is agent-centric, not situation-centric

### Part XV: Meeting Intelligence ⚠️ PARTIAL
- Copilot exists but NOT wired to Cognitive Council
- LiveIntelligenceEngine is separate from Situation Engine

### Part XVI: Failure Behavior ⚠️ PARTIAL
- Graceful degradation toward silence
- LLM failure behavior not tested against Cognitive Council

### Part XVII: Security/Tenancy ⚠️ PARTIAL
- Cross-tenant leakage, permission changes
- Auth exists (F4 fixed) but Cognitive Council doesn't enforce org_id yet

### Part XVIII: Executive Usability ❌ NOT TESTABLE
- Real executives, no architecture explanation
- Requires deployed product + real users

### Part XIX: Naked LLM Baseline ❌ NOT TESTABLE
- Maestro vs. ChatGPT with same evidence
- Requires LLM configured + production wiring

### Part XX: World Model Benchmark ✅ PASS (Gate 0)
- 10 longitudinal stories

### Part XXI: Product Coherence ⚠️ PARTIAL
- Same situation across surfaces
- Architecture supports this (thin references) but surfaces not wired

### Part XXII: Pilot Operability ❌ NOT TESTABLE
- Onboarding, connector setup, audit reconstruction
- No real connectors, no SaaS

### Part XXIII: Pilot Success Metrics ❌ NOT TESTABLE
- "Did Maestro surface material information earlier?"
- No measurement framework defined

---

## Summary: Pass/Partial/Fail/Not-Testable

| Status | Count | Parts |
|--------|-------|-------|
| ✅ PASS | 8 | III, V, VII, VIII, IX, X, XII, XIII, XX |
| ⚠️ PARTIAL | 5 | I, XI, XV, XVI, XVII, XXI |
| ❌ NOT WIRED | 4 | IV, VI, XIV, XXII |
| ❌ NOT TESTABLE | 3 | XVIII, XIX, XXIII |

**Maestro is NOT ready for this audit.** Wire the 5 surfaces first, then run this audit.

---

## The Constitutional Test

> A new intelligence capability is not complete when it produces an output.
> It is complete only when it can **improve a real human decision, explain the evidence behind that improvement, observe the result, and use the result to improve future judgment.**

The audit tests this at the production path level — not the unit test level.
