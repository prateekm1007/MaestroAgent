# Maestro OEM — Organizational Execution Model

The real OEM. Replaces all hardcoded insights with a signal-driven inference engine.

## Architecture

```
Signal → Normalizer → Receipt → LearningObject → Pattern → Law → ExecutionModel → DecisionEngine → UI
```

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

## Test Results

```
50 passed in 0.78s
```

- 34 core OEM tests (test_oem.py)
- 16 edge case tests (test_oem_edge_cases.py)
- 3 pre-existing memory tests (test_memory.py) — regression pass, no breakage

## Known Limitations

1. **UI not yet wired to OEM** — `app.html` is a standalone prototype with hardcoded data. The OEM backend is real but not connected to the frontend. Wiring requires an API layer (FastAPI/Next.js) that serves OEM state to the UI.
2. **No persistence** — the OEM lives in memory. Page refresh resets state. Production requires PostgreSQL (schema exists in `v6-production/prisma/schema.prisma`).
3. **No real API connections** — providers have normalizers but no OAuth/API client implementations. Production requires GitHub/Slack/Jira OAuth flows.
4. **No multi-user** — single-engine, single-model. Production requires per-org engine instances with Redis pub/sub.
5. **Pre-existing test failures** — `tests/test_core_engine.py` and `tests/test_loops.py` have a pre-existing import error (`RunStatus` not defined in `maestro_core.context.py`). This is unrelated to the OEM work.
