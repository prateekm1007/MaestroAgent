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
105 passed, 3 skipped in 0.96s
```

| Suite | Tests | Result |
|---|---|---|
| `test_oem.py` (core OEM) | 34 | ✓ |
| `test_oem_edge_cases.py` (edge cases) | 16 | ✓ |
| `test_evidence_graph.py` (evidence graph) | 15 | ✓ |
| `test_evidence_graph_edge_cases.py` (graph edge cases) | 8 | ✓ |
| `test_contradiction.py` (contradiction learning) | 20 | ✓ |
| `test_contradiction_edge_cases.py` (contradiction edge cases) | 12 | ✓ |
| `tests/test_memory.py` (regression) | 3 | ✓ |
| **Total** | **105** | **✓ All pass** |

## Known Limitations

1. **UI not yet wired to OEM** — `app.html` is a standalone prototype with hardcoded data. The OEM backend is real but not connected to the frontend. Wiring requires an API layer (FastAPI/Next.js) that serves OEM state to the UI.
2. **No persistence** — the OEM lives in memory. Page refresh resets state. Production requires PostgreSQL (schema exists in `v6-production/prisma/schema.prisma`).
3. **No real API connections** — providers have normalizers but no OAuth/API client implementations. Production requires GitHub/Slack/Jira OAuth flows.
4. **No multi-user** — single-engine, single-model. Production requires per-org engine instances with Redis pub/sub.
5. **Pre-existing test failures** — `tests/test_core_engine.py` and `tests/test_loops.py` have a pre-existing import error (`RunStatus` not defined in `maestro_core.context.py`). This is unrelated to the OEM work.
