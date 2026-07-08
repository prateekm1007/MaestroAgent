# Maestro Cognitive Council — Execution Policy

> **Status**: Active — supersedes the literal "17 agents + dashboard" interpretation of the Nerve integration
> **Issued**: 2026-07-08, by CEO directive
> **Reference**: CEO architectural directive on Maestro as a Living Intelligence Layer for Organizations

---

## The Architectural Reframe

Maestro is not becoming "17 AI agents." It is becoming a **Living Intelligence Layer for Organizations**.

The 17 specialists are useful computationally. They are **not** the product. They are invisible machinery beneath a situation-centric product.

### The mistake this policy prevents

```
Dashboard
   │
   ├── Sales Agent (4 insights)
   ├── Security Agent (3 insights)
   ├── Product Agent (7 insights)
   └── 14 more agents
```

This creates **organizational AI theater**. The executive's new job becomes "managing the AI employees." That violates the entire product philosophy.

### The architecture this policy mandates

```
                    USER CONTEXT
                         │
                         ▼
                    SITUATION
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
        SALES         SECURITY       PRODUCT
      perspective     perspective    perspective
          │              │              │
          └──────────────┼──────────────┘
                         ▼
                  SHARED JUDGMENT
                         │
                         ▼
              BEST DELIVERY SURFACE

              Whisper · Ask · Prepare · Briefing · Decision
```

The specialists contribute **perspectives to situations**. The user rarely needs to know which specialist produced them.

---

## The Product Unit

**Before** (wrong):
```
Agent → Insight
```

**After** (right):
```
Situation
  → evidence
  → history
  → perspectives
  → disagreement
  → unknowns
  → judgment
  → intervention
  → decision
  → outcome
  → learning
```

A **Situation** is the living object. Everything else serves it.

---

## The Six-Layer Architecture

```
──────────────────────────────────────────────
5. EXPERIENCE: Whisper · Ask · Prepare · Briefings · Decisions · Ambient
──────────────────────────────────────────────
4. JUDGMENT: Situation understanding · Contradictions · Perspectives ·
              Coordination · Missing evidence · Counterevidence
──────────────────────────────────────────────
3. LEARNING: Hypotheses · Predictions · Outcomes · Calibration ·
              Falsification · Governed promotion
──────────────────────────────────────────────
2. ORGANIZATIONAL MEMORY: Intent · Commitments · Decisions · Evidence ·
                           Outcomes · Patterns · Laws · Relationships
──────────────────────────────────────────────
1. PERCEPTION: GitHub · Jira · Slack · Email · Calendar · CRM · Meetings
──────────────────────────────────────────────
```

The Specialist Council sits **horizontally across** this stack, not as a 6th layer.

---

## The Specialist Classes

The 17 specialists are not uniform. They have four internal classes:

### Observers (detect domain-specific changes)
Sales · Customer Success · Support · Engineering · Security · Finance · HR

### Interpreters (explain implications)
Legal · Product · Data · Marketing · Partnerships · Communications

### Strategists (reason across situations)
Growth · Operations · Strategy

### Synthesizer
Chief of Staff — but NOT a naive aggregator. It must perform:
- Deduplication
- Contradiction detection
- Priority arbitration
- Cross-domain dependency analysis
- Missing-evidence detection
- Counterevidence search
- Decision relevance analysis
- Delivery recommendation

---

## The Perspective Contract

A specialist does not output free-form "insights." It outputs a **Perspective** with a strict epistemic schema:

```
Perspective
  situation_id          # which situation this pertains to
  specialist            # which specialist produced it
  observation           # what does this specialist see?
  implication           # why might it matter?
  evidence              # which records support it?
  counterevidence       # what weakens this interpretation?
  unknowns              # what must still be established?
  scope                 # where is this interpretation applicable?
  urgency               # why now, rather than later?
  recommended_next_step # what is the smallest useful action?
  epistemic_status      # observed | reported | inferred | disputed | unknown
  delivery_recommendation # silent | briefing | whisper | prepare | urgent
```

**Constitutional rule**: A specialist may recommend delivery. It **cannot** decide delivery. That belongs to the Delivery Governor.

---

## Disagreement Is a Feature

Most multi-agent systems converge. Organizations do not.

Maestro must **preserve useful disagreement**:

```
Product:     Delay migration until after the release.
Security:    Delay increases exposure because policy inconsistency remains.
Sales:       Two enterprise renewals occur during the proposed window.

Maestro:     The disagreement is not about whether to standardize.
             It is about sequencing. A phased migration beginning with
             non-renewal-critical services resolves most of the conflict.
```

The reasoning path matters. The user must be able to ask "Why?" and traverse the same situation object and evidence graph.

---

## The Delivery Governor

Deterministic routing — not a model guess:

| Route | When |
|-------|------|
| **silent** | No intervention justified. The system watches. |
| **ask** | Information available if the user asks, but no proactive push. |
| **briefing** | Include in the morning/evening briefing. |
| **whisper** | Proactive push during an active context (e.g., mid-meeting). |
| **prepare** | Surface a preparation workspace before a known event. |
| **urgent** | Immediate escalation — rare, reserved for critical risks. |

---

## The Action Ladder

Maestro earns autonomy. It does not claim it.

| Level | Action | Example |
|-------|--------|---------|
| 0 | Observe | No action. |
| 1 | Suggest | "You may want to clarify the security status." |
| 2 | Prepare | "I prepared the questions worth asking." |
| 3 | Draft | "I drafted the Slack message and customer follow-up." |
| 4 | Stage | "The Jira items and messages are ready for approval." |
| 5 | Execute with approval | User explicitly approves. |
| 6 | Governed autonomy | Only for narrow, reversible, pre-authorized workflows. |

---

## Organizational Epistemology — The Moat

The moat is not "Maestro remembers more." It is:

> Maestro develops an increasingly disciplined model of what this organization **knows, believes, assumes, predicts, disputes, learns, and forgets.**

| State | Meaning |
|-------|---------|
| KNOWN | Supported directly by evidence. |
| REPORTED | Someone said it. |
| BELIEVED | The organization behaves as though it is true. |
| ASSUMED | A decision depends upon it. |
| HYPOTHESIZED | A proposed relationship being tested. |
| PREDICTED | A prospective claim about a future outcome. |
| DISPUTED | Credible evidence conflicts. |
| UNKNOWN | Important information is missing. |
| FALSIFIED | Independent outcomes contradicted the hypothesis. |
| LEARNED | Prospective evidence repeatedly supported it within scope. |

---

## The Real Product Loop

```
PERCEIVE → UNDERSTAND → REMEMBER → QUESTION → PREPARE → OBSERVE OUTCOME → LEARN → CHANGE FUTURE JUDGMENT
```

The last arrow is the moat.

Maestro should eventually answer:

> The last three times your organization faced this situation, one approach worked twice and failed once. The failed case differed because Security entered after customer expectations had already been set. Security is already involved this time, so that earlier failure mechanism is less applicable.

**Absent**: pseudo-scientific precision ("83.7% success probability") unless there is a genuine, calibrated, sufficiently powered basis for it.

---

## Implementation Sequence

| Phase | Build | Status |
|-------|-------|--------|
| 1 | **Situation Engine** — durable Situation object with timeline, knowns, unknowns, perspectives, judgment, state | IN PROGRESS |
| 2 | **Perspective Contract** — restructure specialists to output structured Perspectives, route per-situation | PENDING |
| 3 | **Judgment Synthesizer** — compare perspectives, preserve disagreement, counterevidence, unknowns | PENDING |
| 4 | **Delivery Governor** — deterministic routing (silent/ask/briefing/whisper/prepare/urgent) | PENDING |
| 5 | **Preparation Workspace** — questions, evidence packets, decision briefs, drafts, approval-ready actions | PENDING |
| 6 | **Learning Closure** — connect decisions to outcomes, calibration, falsification | PENDING |

The 17 specialists from the Nerve integration are **retained** as the Specialist Council. They are refactored to output Perspectives (Phase 2) and routed per-situation by the Situation Engine (Phase 1).

---

## The Constitutional Test

> A new intelligence capability is not complete when it produces an output.
> It is complete only when it can **improve a real human decision, explain the evidence behind that improvement, observe the result, and use the result to improve future judgment.**

That is the line between a sophisticated AI interface and the Living Intelligence Layer for Organizations.

---

## Governance Gates (retained from prior policy)

Every commit that touches `maestro_cognitive_council/` or `maestro_nerve/` or `maestro_api/routes/` must pass:

```
python -m pytest backend/maestro_oem/tests/test_c4_demo_entity_leak.py \
                 backend/maestro_api/tests/test_route_auth_inventory.py \
                 backend/maestro_cognitive_council/tests/ \
                 backend/maestro_nerve/tests/
```

All must pass before commit. P34 lesson (5th occurrence): the fix is execution, not policy.
