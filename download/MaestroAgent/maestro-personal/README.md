# Maestro Personal v1

A thin Personal shell over the existing Python Core. Per the revised 90-day
roadmap: direct Python API, not HTTP. No Core extraction. No Rust. No
enterprise features. Just call Core.

## What this is

The 4 surfaces of Maestro Personal v1:

| Surface | Core capability called | What the shell adds |
|---------|------------------------|---------------------|
| **Prepare** | `SituationPreparationBridge.prepare_for_situation()` | Personal meeting context |
| **Commitments** | `classify_transcript_chunk()` + `should_treat_as_commitment()` from `audit_safety` | Personal commitment tracking |
| **Ask** | `SituationAwareAskBridge.ask()` | Personal-data Q&A |
| **What Changed** | `SituationEngine.apply_signal()` → `SituationDelta` | Personal delta surfacing |

## What this is NOT

- No mobile app (hosted web first, per revised roadmap)
- No Gmail/Calendar/GitHub OAuth (manual signal entry in Week 1)
- No Core extraction (calls existing `maestro_cognitive_council` directly)
- No Rust (Python only)
- No enterprise features (no SAML, SCIM, RBAC, multi-tenant, Postgres)
- No dilution (every Personal module imports Core, never reimplements)

## Architecture

```
maestro-personal/
├── src/maestro_personal_shell/
│   ├── shell.py                     ← THE thin shell: builds SituationEngine with personal signals
│   ├── personal_oem_state.py        ← PersonalOemState: has .signals, passes to Core
│   ├── salience.py                  ← PersonalSalienceConfig: personal signal types
│   ├── signal_adapters/             ← Week 3+: Gmail, Calendar, GitHub adapters (deferred)
│   └── surfaces/
│       ├── prepare.py               ← calls SituationPreparationBridge
│       ├── commitments.py           ← calls classify_transcript_chunk + should_treat_as_commitment
│       ├── ask.py                   ← calls SituationAwareAskBridge
│       └── what_changed.py          ← calls SituationEngine + detect_stale_commitments
└── tests/
    ├── test_personal_shell_works.py ← smoke test (Day 1 gate)
    ├── test_30_day_benchmark.py     ← the Life-of-Work Benchmark (Day 1 → Day 30)
    └── conftest.py                  ← sys.path setup
```

## Day 1 gate (PASSED)

The smoke test proves the existing Core detects situations from personal
signals via the thin shell:

```python
state = PersonalOemState(signals=[
    PersonalSignal(entity="Alex", text="I will send the proposal by Friday", signal_type="commitment_made"),
    PersonalSignal(entity="Alex", text="Following up on the proposal", signal_type="reported_statement"),
    PersonalSignal(entity="Alex", text="Meeting moved to Tuesday", signal_type="calendar_change"),
])
shell = PersonalShell(oem_state=state)
situations = shell.detect_situations()
assert len(situations) >= 1  # PASSES
```

The thesis is testable. The existing Core can detect situations from
personal signals without extraction, without Rust, without HTTP.

## Running the tests

```bash
# Smoke test (Day 1 gate)
python -m pytest maestro-personal/tests/test_personal_shell_works.py -v

# 30-day benchmark (worklist — some checkpoints fail, that's expected)
python -m pytest maestro-personal/tests/test_30_day_benchmark.py -v

# Core regression (Enterprise path unaffected)
python -m pytest backend/maestro_cognitive_council/tests/ -q --tb=no
```

## Package naming

This package is `maestro_personal_shell` (not `maestro_personal`) to
avoid collision with the existing `backend/maestro_personal/` package
(the old diluted Personal mode from prior rounds). The old package is
slated for deletion in Phase 2 per the Module Audit worklist. After
deletion, this package can be renamed to `maestro_personal` if desired.
