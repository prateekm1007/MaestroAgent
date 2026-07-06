# CRITICAL-03 Design Doc: Shared Situation Substrate

**Finding:** `SituationBuilder` exists but is built and discarded in Whisper (`whisper.py:117` — literally `pass`). Ask, Whisper, Preparation, and Learning each build their own reality from raw signals via different retrieval paths. The product thesis — "one unified organizational situation model" — is not real.

**Severity:** CRITICAL (architectural — the product's central claim depends on this)

**Status:** Design doc — implementation is a multi-session sprint.

---

## Current State (Verified by Execution)

```
whisper.py:111  situation = builder.build_for_entity(entity)
whisper.py:117  pass  # ← built, then discarded

ask_pipeline.py:execute()
  → _retrieve() → _search_signals() → builds evidence from raw signals
  → does NOT use SituationBuilder

preparation_engine.py:prepare_for_tomorrow()
  → builds its own evidence via EvidenceBuilder
  → does NOT use SituationBuilder

learning_ledger.py:write_entry()
  → reads from model.learning_objects directly
  → does NOT use SituationBuilder
```

**Result:** Each surface sees a different subset of signals, applies different filters, and produces different evidence. The "Situation" is theater — it exists as a class but is not the shared substrate.

---

## The Problem in Detail

The audit's CRITICAL-03 reproduction showed:
- `AskPipeline("Prepare me for Globex")` → "I don't have enough organizational memory"
- `AskPipeline("What exactly did we promise Globex?")` → 12 signals, structured answer
- `AskPipeline("Who thinks differently about SSO?")` → "I don't have enough organizational memory"
- `OrganizationalWhisper` for the same situation → only 1 commitment, no disagreement

These surfaces are looking at the SAME organizational reality but seeing DIFFERENT things because:
1. Ask uses intent-based keyword retrieval (`_search_signals`)
2. Whisper uses signal-type heuristics (`_entity_whispers`, `_entity_warnings`)
3. Preparation uses its own EvidenceBuilder
4. Learning reads from `model.learning_objects` directly

No shared intermediate. No single source of truth for "what is the situation with entity X right now?"

---

## Proposed Solution: Situation as Mandatory Intermediate

### Core Principle

**Every surface that answers a question about an entity MUST render from a `SituationSnapshot`, not from raw signals.**

```
Signal ingestion → OEMEngine → ExecutionModel
                                    ↓
                         SituationBuilder.build_for_entity(entity)
                                    ↓
                         SituationSnapshot (immutable, per-entity, per-moment)
                                    ↓
                    ┌───────────────┼───────────────┐
                    ↓               ↓               ↓
               AskPipeline     WhisperEngine   PreparationEngine
              (renders from   (renders from   (renders from
               snapshot)       snapshot)       snapshot)
```

### SituationSnapshot Structure

The `SituationSnapshot` is the **single source of truth** for what Maestro knows about an entity at a moment in time. All surfaces consume it; none bypass it.

```python
@dataclass(frozen=True)
class SituationSnapshot:
    """Immutable snapshot of the organizational situation for one entity.

    Built once by SituationBuilder, consumed by all surfaces.
    This is the shared cognitive substrate — the ONLY intermediate
    between raw signals and user-facing output.
    """
    entity: str                          # "Globex"
    as_of: datetime                     # when this snapshot was built

    # ─── What is happening ───
    what_is_happening: str               # "Globex Q4 renewal meeting tomorrow"

    # ─── Commitments (all epistemic types) ───
    commitments: list[CommitmentFact]    # "We will deliver SSO by Dec 15"
    proposals: list[CommitmentFact]      # "We should support SSO by Q4"
    estimates: list[CommitmentFact]      # "Engineering thinks SSO by Q4"

    # ─── Evidence (permission-filtered) ───
    evidence: list[EvidenceItem]         # all signals, filtered by user ACL

    # ─── Disagreements ───
    disagreements: list[Disagreement]    # Sales says X, Product says Y

    # ─── Timeline ───
    timeline: list[TimelineEvent]        # chronological events

    # ─── Current state ───
    current_state: str                   # "at_risk" | "on_track" | "unknown"
    pending_conditions: list[str]        # "Security approval still conditional"

    # ─── Prior whispers ───
    prior_whispers: list[WhisperRecord]  # what Maestro already said

    # ─── Outcomes observed ───
    outcomes: list[OutcomeFact]          # "SSO deployed successfully"

    # ─── Unknowns (what we DON'T know) ───
    unknowns: list[str]                  # "Customer's renewal decision date"
```

### How Each Surface Consumes It

#### AskPipeline

```python
def execute(self, query: str, user_email: str = "") -> dict:
    intent = self.classify_intent(query)
    entities = self.resolve_entities(query)

    # CRITICAL-03 fix: build SituationSnapshot FIRST
    # All retrieval happens through the snapshot, not raw signals
    snapshots = {}
    for entity in entities:
        snapshots[entity] = SituationBuilder(
            signals=self._visible_signals(user_email),  # CRITICAL-01: permission-filtered
            calendar_source=self._calendar_source,
            whisper_store=self._whisper_store,
        ).build_for_entity(entity)

    # Intent-specific rendering FROM THE SNAPSHOT
    if intent == AskIntent.RECALL:
        evidence = self._render_recall(snapshots)
    elif intent == AskIntent.PREPARE:
        evidence = self._render_prepare(snapshots)
    elif intent == AskIntent.WHY:
        evidence = self._render_why(snapshots, query)
    # ... etc

    answer = self._synthesize(evidence, snapshots)
    return {"answer": answer, "evidence": evidence, "snapshots": snapshots}
```

#### OrganizationalWhisper

```python
def for_context(self, context: str, entity: str, topic: str) -> dict:
    # CRITICAL-03 fix: build SituationSnapshot FIRST
    # The `pass` at line 117 is replaced with actual usage
    situation = SituationBuilder(
        signals=self.signals,
        calendar_source=self._calendar_source,
        whisper_store=self.whisper_store,
    ).build_for_entity(entity)

    # Generate whispers FROM THE SNAPSHOT
    whispers = []
    for commitment in situation.commitments:
        if self._is_at_risk(commitment, situation):
            whispers.append(self._build_commitment_whisper(commitment, situation))

    for disagreement in situation.disagreements:
        whispers.append(self._build_disagreement_whisper(disagreement, situation))

    for pending in situation.pending_conditions:
        whispers.append(self._build_risk_whisper(pending, situation))

    # Apply delivery gate
    return self._apply_delivery_gate(whispers, situation)
```

#### PreparationEngine

```python
def prepare_for_tomorrow(self, org_id: str, user_email: str) -> dict:
    meetings = self._calendar_source.get_tomorrow_events()

    preparations = []
    for meeting in meetings:
        entity = meeting.entity

        # CRITICAL-03 fix: build SituationSnapshot for each meeting's entity
        situation = SituationBuilder(
            signals=self._visible_signals(user_email),
            calendar_source=self._calendar_source,
            whisper_store=self._whisper_store,
        ).build_for_entity(entity)

        preparations.append({
            "meeting": meeting,
            "situation": situation,  # ← the shared substrate
            "customer_concerns": self._extract_concerns(situation),
            "previous_objections": self._extract_objections(situation),
            "relevant_commitments": situation.commitments,
            "suggested_talking_points": self._derive_talking_points(situation),
            "internal_expert": self._find_expert(situation),
        })

    return {"preparations": preparations}
```

---

## Migration Strategy

### Phase 1: Enrich SituationSnapshot (2 sessions)

Add the missing fields to `SituationSnapshot`:
- `disagreements` — detect Sales vs Product vs Customer conflicts
- `pending_conditions` — extract from negation-classified signals
- `unknowns` — derive from gaps in evidence
- `outcomes` — extract from outcome-classified signals

Write tests verifying each field is populated from the SSO scenario.

### Phase 2: Wire AskPipeline to SituationSnapshot (2 sessions)

Replace `_search_signals` with `SituationBuilder.build_for_entity`. Intent-specific rendering reads from the snapshot. Verify the SSO scenario produces consistent answers across all intents.

### Phase 3: Wire Whisper to SituationSnapshot (2 sessions)

Replace the `pass` at line 117. Whisper generation reads commitments, disagreements, and pending_conditions from the snapshot. Verify Whisper surfaces the same facts Ask surfaces.

### Phase 4: Wire Preparation to SituationSnapshot (1 session)

PreparationEngine builds a snapshot per meeting entity. Verify preparation briefs reference the same commitments and disagreements.

### Phase 5: Cross-surface golden tests (1 session)

Write tests that query the same entity through Ask, Whisper, Preparation, and verify they agree on:
- Same commitments
- Same timeline
- Same evidence IDs
- Same claim types
- Same unresolved questions

---

## Risks

1. **Performance:** Building a SituationSnapshot on every request is expensive. Mitigation: cache per-entity with 60-second TTL, invalidate on signal ingest.
2. **Backward compatibility:** Existing tests expect the old behavior. Mitigation: feature flag (`MAESTRO_SHARED_SITUATION=true`), run both paths in parallel during migration.
3. **Permission filtering:** The snapshot must be permission-filtered at build time (CRITICAL-01). Mitigation: SituationBuilder accepts `user_email` and filters signals before building.

---

## Success Criteria

- [ ] `SituationSnapshot` is the mandatory intermediate for Ask, Whisper, Preparation
- [ ] `whisper.py:117` no longer says `pass` — the situation is used
- [ ] Cross-surface golden test: same entity → same commitments, timeline, evidence across all surfaces
- [ ] The SSO scenario: "Prepare me for Globex" returns the same commitments as "What did we promise Globex?"
- [ ] "Who thinks differently about SSO?" surfaces the Sales/Product disagreement (currently returns "I don't know")

## Estimated Effort

8 sessions (5 phases)
