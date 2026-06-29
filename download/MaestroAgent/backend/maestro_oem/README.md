# Maestro OEM — Organizational Execution Model

The real OEM. Replaces all hardcoded insights with a signal-driven inference engine.

## Architecture

```
Signal → Normalizer → Receipt → LearningObject → Pattern → Law → ExecutionModel → DecisionEngine → UI
                                                                        ↓
                                                                  EvidenceGraph
                                                                  (traversable)
```

Every recommendation traces back through:
  Recommendation → Law → Pattern → LearningObject → Receipt → Signal → Original Artifact

The EvidenceGraph makes this chain traversable, deletable, and reconnectable.

Every provider (GitHub, Jira, Slack, Confluence, Gmail) produces normalized `ExecutionSignal` objects.
The OEM consumes these and updates itself incrementally — never rebuilds.

## Package Structure

```
backend/maestro_oem/
├── __init__.py           — Package exports
├── signal.py             — ExecutionSignal (universal normalized type)
├── receipt.py            — Receipt + ReceiptChain (provenance)
├── learning_object.py    — LearningObject (evidence unit, 12 types)
├── pattern.py            — Pattern + PatternDetector (inference layer, 7 types)
├── law.py                — OrganizationalLaw (validated patterns, 5 statuses)
├── confidence.py         — ConfidenceCalculator (Bayesian Beta-Binomial)
├── model.py              — ExecutionModel (living state, incremental update)
├── engine.py             — OEMEngine (orchestrator)
├── decision.py           — DecisionEngine (recommendations + Ask-the-Org)
├── providers/
│   ├── github.py         — GitHub normalizer
│   ├── jira.py           — Jira normalizer
│   ├── slack.py          — Slack normalizer
│   ├── confluence.py     — Confluence normalizer
│   └── gmail.py          — Gmail normalizer
└── tests/
    ├── test_oem.py            — 34 deterministic tests
    └── test_oem_edge_cases.py — 16 edge case tests
```

## Usage

```python
from maestro_oem import OEMEngine, DecisionEngine
from maestro_oem.providers import normalize_github

engine = OEMEngine()

# Process GitHub signals
signals = [normalize_github(event) for event in github_events]
engine.ingest(signals)

# Get model state
summary = engine.get_summary()
# → {providers_connected: ['github'], learning_objects: 5, laws_inferred: 2, ...}

# Get recommendations
dec = DecisionEngine(engine.get_model())
recs = dec.get_recommendations()
# → [Recommendation(title="Address bottleneck: ...", confidence=0.78, ...)]

# Ask the organization
result = dec.answer_question("Who reviewed the payments PR?")
# → {answer: "...", confidence: 0.72, evidence_path: [...]}
```

## Confidence Formula

Bayesian Beta-Binomial model:

```
alpha = 1 + validated_runtimes
beta  = 1 + failed_runtimes
posterior_mean = alpha / (alpha + beta)

confidence = posterior_mean × evidence_weight × recency_factor + provider_diversity_bonus
```

- **Evidence weight**: logarithmic growth (diminishing returns)
- **Provider diversity**: +5% per additional provider, capped at 20%
- **Recency decay**: half-life of 90 days, floor at 30%

## Key Properties (Verified by Tests)

1. **No hardcoded insights** — empty OEM produces zero laws, zero recommendations
2. **Each provider contributes unique information** — verified by type uniqueness tests
3. **Confidence is mathematical** — Beta-Binomial, not arbitrary numbers
4. **Provenance is complete** — every LearningObject has a Receipt chain to its signal
5. **Laws evolve** — strengthen with evidence, stress with counter-examples, invalidate when disproven
6. **Incremental update** — model preserves state, never rebuilds
7. **No hallucination** — Ask-the-Org returns "I don't know" when evidence is insufficient

## Signal Types

### GitHub
- `pr.opened`, `pr.merged`, `pr.closed`, `pr.reviewed`
- `commit`, `branch.created`, `repo.created`

### Jira
- `issue.created`, `issue.transitioned`, `issue.assigned`
- `sprint.started`, `sprint.completed`

### Slack
- `message.sent`, `thread.started`
- `slack.decision`, `slack.question`, `slack.agreement`, `slack.conflict`

### Confluence
- `page.created`, `page.edited`, `page.owner_changed`
- `rfc.created`, `postmortem.created`

### Gmail
- `meeting.scheduled`, `meeting.completed`
- `email.sent`, `email.received`

## Provider-Specific OEM Changes

| Provider | What it changes | Unique LO types |
|---|---|---|
| GitHub | Knowledge graph, influence scores, release frequency | `REVIEW_PATTERN`, `RELEASE_PATTERN` |
| Jira | Incident rate, approval gates, sprint velocity | `INCIDENT_PATTERN`, `VELOCITY_DROP` |
| Slack | Collaboration graph, conflict detection, departure risk | `BOTTLENECK`, `DECISION_PATTERN` |
| Confluence | Documented knowledge, knowledge death detection | `KNOWLEDGE_DEATH` |
| Gmail | Decision velocity, external communication patterns | `HANDOFF_DELAY` |

## Evidence Graph

The `EvidenceGraph` is a traversable directed graph connecting recommendations back to original artifacts.

### Components

| Component | Purpose |
|---|---|
| `EvidenceNode` | Typed node (signal, receipt, LO, pattern, law, recommendation) with `artifact_ref` |
| `EvidenceEdge` | Directed "supported by" edge with weight and type (PRODUCED, CAUSED, CONTRIBUTED, VALIDATED, CONTRADICTED, DERIVED) |
| `EvidenceChain` | Complete traversable chain with supporting + contradicting artifacts and computed strength |
| `EvidenceGraph` | The graph — build, traverse, delete, reconnect |

### API

```python
from maestro_oem import EvidenceGraph, DecisionEngine

# Build from model
graph = EvidenceGraph()
graph.build_from_model(model)

# Enrich recommendations with evidence
dec = DecisionEngine(model, evidence_graph=graph)
for rec in dec.get_recommendations():
    print(rec.evidence_chain)        # Full traversable chain
    print(rec.supporting_artifacts)  # [{"artifact": "github:pr/447", "provider": "github", ...}]
    print(rec.contradicting_artifacts)
    print(rec.evidence_strength)     # 0..1

# Traverse from any node
chain = graph.traverse("law:L-0007")
print(chain.to_display())  # UI-ready dict

# Delete evidence (cascading removal, returns affected nodes)
affected = graph.delete_evidence("signal-uuid")

# Reconnect evidence (rebuilds chain after re-add)
graph.reconnect_evidence(signal_node, receipt_node, lo_node, ["law:L-0007"])
```

### Strength Formula

```
strength = total_edge_weight / (total_edge_weight + 2)
```

More edges with higher weights = higher strength. Deleting edges reduces strength. Reconnecting restores it.

## Contradiction Learning

Maestro can admit it is wrong. CEO feedback cascades through the entire model.

### Feedback Actions

| Action | Effect | Confidence Change |
|---|---|---|
| `AGREE` | Law gains validation | ↑ Increases |
| `REJECT` | Law gains counter-example, drift flag set | ↓ Decreases |
| `MODIFY` | Law gains both validation and counter-example | ↓ Slight decrease |
| `IGNORE` | No change to model | None (event recorded) |

### Law Lifecycle from Contradictions

```
VALIDATED → (3 rejections, ratio > 0.3) → STRESSED → (6 rejections, ratio > 0.5) → INVALIDATED
```

Invalidated laws are suppressed — they stop appearing in recommendations.

### Append-Only History

Every `ContradictionEvent` permanently stores:
- Action, reasoning, actor, timestamp
- Predicted confidence, predicted outcome, actual outcome
- Confidence before/after for each affected law
- Law status changes

Events are **never overwritten, never deleted**.

### API

```python
from maestro_oem import ContradictionEngine, FeedbackAction

contra = ContradictionEngine(model)

# CEO rejects a prediction
event = contra.apply_feedback(
    target_type="law",
    target_id="L-TEST",
    action=FeedbackAction.REJECT,
    reasoning="APAC churn didn't increase — the law is wrong for this segment",
    actor="jane@acme.com",
    predicted_confidence=0.84,
    predicted_outcome="APAC churn +14%",
    actual_outcome="APAC churn -2%",
)

# Check calibration impact
impact = contra.get_calibration_impact()
# → {total_feedback: 1, rejection_rate: 1.0, average_confidence_delta: -0.12}

# Check if law should be suppressed
if contra.shouldsuppress_law("L-TEST"):
    print("Law L-TEST is no longer reliable — suppressing from recommendations")
```

## Test Results

```
170 passed, 3 skipped in 1.29s
```

| Suite | Tests | Result |
|---|---|---|
| `test_oem.py` (core OEM) | 34 | ✓ |
| `test_oem_edge_cases.py` (edge cases) | 16 | ✓ |
| `test_evidence_graph.py` (evidence graph) | 15 | ✓ |
| `test_evidence_graph_edge_cases.py` (graph edge cases) | 8 | ✓ |
| `test_contradiction.py` (contradiction learning) | 20 | ✓ |
| `test_contradiction_edge_cases.py` (contradiction edge cases) | 12 | ✓ |
| `test_confidence_refactored.py` (Bayesian confidence) | 19 | ✓ |
| `test_replay.py` (historical replay) | 21 | ✓ |
| `test_persistence.py` (persistence) | 17 | ✓ |
| `test_persistence_edge_cases.py` (persistence edge cases) | 8 | ✓ |
| `tests/test_memory.py` (regression) | 3 | ✓ |
| **Total** | **170** | **✓ All pass** |

## Persistence

The OEM survives restart. All state persists to SQLite.

### What Persists

| Component | Table |
|---|---|
| Model state (health, knowledge, approvals, risks) | `model_state` |
| LearningObjects | `learning_objects` |
| Patterns | `patterns` |
| Laws | `laws` |
| Receipts | `receipts` |
| ReceiptChains | `receipt_chains` |
| Processed signal IDs | `processed_signals` |
| Contradiction events | `contradiction_events` (append-only) |
| Raw signals | `signals` (for replay) |

### Cold Boot

```python
from maestro_oem import PersistentOEM

# First run
persistent = PersistentOEM(db_path="maestro.db")
persistent.ingest(signals)
persistent.close()

# Restart — cold boot reconstructs everything
persistent = PersistentOEM(db_path="maestro.db")
model = persistent.get_model()  # Fully restored — no reprocessing

# Continue with new signals (incremental)
persistent.ingest(new_signals)
```

No full recompute. No reprocessing of historical signals. Migration scripts run automatically on startup (`CREATE TABLE IF NOT EXISTS` + `schema_version` tracking).

## Known Limitations

1. **UI not yet wired to OEM** — `app.html` is a standalone prototype. The OEM backend is real but not connected to the frontend. Every CEO-product surface (inbox, simulator, hayek, etc.) now carries an explicit `DEMO PROTOTYPE` banner so users know the data is illustrative. The engineering console pages (runs, agents, loops) ARE wired to the `maestro_api` backend via `/api/runs` etc. — those pages replace hardcoded rows with real data when the backend is reachable. Wiring the OEM to the UI requires an API layer (FastAPI/Next.js) that serves OEM state.
2. **SQLite (not Postgres)** — persistence uses SQLite (zero-config). Production should swap for PostgreSQL — same interface, swap `OEMStore` for `PostgresStore`.
3. **No real API connections** — providers have normalizers but no OAuth/API client implementations. Production requires GitHub/Slack/Jira OAuth flows.
4. **Multi-user model exists, transport does not** — `multiuser.py` provides `SharedOEM`, `UserSession`, `SyncManager`, and `OptimisticUpdate` with conflict resolution (last-write-wins for simple fields, merge for additive fields). What is missing is the WebSocket transport layer that broadcasts `SyncEvent`s to connected browser sessions. Production requires a `fastapi.WebSocket` endpoint that calls `SyncManager.broadcast()`.
5. **Pre-existing test failures — RESOLVED** — `tests/test_core_engine.py` and `tests/test_loops.py` previously failed because `RunStatus` was imported from the wrong module. Fixed in commit `00a6314`: `RunStatus` is now imported from `maestro_core.state` in `maestro_core/__init__.py`. `EventBus.start()` also handles the no-running-event-loop case gracefully. See `test_sprint_fixes.py` for regression coverage.

## Test Coverage

The OEM engine has **275 tests, all passing, 0 skipped, 0 failed**:

- `tests/test_core_engine.py` — 4 tests (orchestration engine lifecycle)
- `tests/test_loops.py` — 3 tests (loop handler with `RunStatus`)
- `tests/test_memory.py` — 3 tests (memory graph)
- `maestro_oem/tests/test_oem.py` — 34 tests (end-to-end OEM signal flow)
- `maestro_oem/tests/test_oem_edge_cases.py` — 13 tests (edge cases)
- `maestro_oem/tests/test_confidence_refactored.py` — 19 tests (Bayesian confidence)
- `maestro_oem/tests/test_contradiction.py` — 20 tests (CEO contradiction feedback)
- `maestro_oem/tests/test_contradiction_edge_cases.py` — 12 tests
- `maestro_oem/tests/test_evidence_graph.py` — 18 tests (traversable evidence chains)
- `maestro_oem/tests/test_evidence_graph_edge_cases.py` — 8 tests
- `maestro_oem/tests/test_dependency.py` — 19 tests (provider disconnection)
- `maestro_oem/tests/test_persistence.py` — 17 tests (SQLite cold boot)
- `maestro_oem/tests/test_persistence_edge_cases.py` — 8 tests
- `maestro_oem/tests/test_replay.py` — 21 tests (historical replay)
- `maestro_oem/tests/test_multiuser.py` — 23 tests (shared OEM, optimistic updates)
- `maestro_oem/tests/test_ingestion.py` — 28 tests (real ingestion pipeline)
- `maestro_oem/tests/test_sprint_fixes.py` — 25 tests (regression coverage for the fixes from commit `00a6314`)

Run all tests:
```bash
cd backend
pytest tests/ maestro_oem/tests/ -q
# 275 passed in ~130s (ingestion tests are slow due to rate-limit simulation)
```
