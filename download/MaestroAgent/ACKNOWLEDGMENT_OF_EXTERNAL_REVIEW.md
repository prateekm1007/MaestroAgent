# Acknowledgment of External Reviewer Response

**From:** Coder (main agent)
**Date:** 2026-07-08
**Re:** Acceptance of external review; execution plan for the 4 missing pieces + 7 engine fixes

---

## I Accept the External Review in Full

The external reviewer answered all four questions. I accept their
conclusions without modification:

1. **Methodology is sound** (with two reservations: no reasoning traces,
   no governance tests). Both reservations are correct. I will address
   them as Missing Pieces 1 and 2.

2. **All 7 gaps are real.** The reviewer confirmed each one against the
   engine architecture. This validates the 7-10 day engine fix estimate,
   conditional on trace-verified closure.

3. **Thresholds need adjustment.** I accept all three:
   - Decision boundary false-decisiveness: 5% → **<1%** (HIGH, not MEDIUM)
   - Auto-disagreement on cross-functional scenarios: **0%**
   - Early-checkpoint detection latency: **<24 hours** on 60-90 day scenarios

4. **Four missing pieces** must be added before pilot readiness:
   - Reasoning traces in Tests 1 and 2
   - Tests 3 and 4 for governance surface
   - One continuous 90-day longitudinal scenario
   - Naked-LLM comparison protocol (20 queries, 4 dimensions)

---

## Execution Plan

The reviewer was explicit: **"Do not begin engine work until you have
integrated the four missing pieces into your test methodology."** I will
follow this order exactly.

### Phase 1: Test Methodology Completion (4 missing pieces)

| Order | Piece | What it does | Estimated effort |
|-------|-------|-------------|-----------------|
| 1 | Reasoning traces in Tests 1 and 2 | Captures Situation state, available evidence, candidate outputs, and selection reason at each checkpoint | 2-3 hours |
| 2 | Tests 3 and 4 (governance surface) | Test 3: operator review/override/suspend/falsify/audit. Test 4: governance stress under flood | 2-3 hours |
| 3 | Continuous 90-day longitudinal scenario | Single Situation observed Day 0 to Day 90, no reset between checkpoints | 1-2 hours |
| 4 | Naked-LLM comparison protocol | 20 fixed executive queries, scored on factual accuracy, evidence traceability, uncertainty honesty, intervention restraint | 1-2 hours |

### Phase 2: Threshold Adjustment

Update Tests 1 and 2 to enforce:
- False-decisiveness: <1% on high-stakes recommendations
- Auto-disagreement: 0% on cross-functional scenarios
- Early-checkpoint latency: <24 hours

### Phase 3: Engine Fixes (one at a time, trace-verified)

Per the reviewer: **"fix one gap at a time, commit, re-run Tests 1 and 2
with traces, and confirm the gap is closed before moving to the next."**

| Order | Gap | File | Verification |
|-------|-----|------|-------------|
| 1 | Situation_id stability | situation_engine.py:1010 | Test 2 (stability check) |
| 2 | Briefing 0 evidence_refs | briefing_bridge.py:205 | Test 2 (evidence overlap) |
| 3 | Outcome-only detection | situation_engine.py:_build_situation | Test 1 (Story 10) |
| 4 | Auto-disagreement | situation_engine.py:_evaluate_initial_transitions | Test 1 (Stories 5, 8) |
| 5 | Decision boundary language | judgment_synthesizer.py:_compute_decision_boundary | Test 1 (Story 5) |
| 6 | Hypothesis-testing state | situation_engine.py (new dimension state) | Test 1 (Story 9) |
| 7 | Early-checkpoint detection | situation_engine.py (lower threshold) | Test 1 (Stories 1,2,4,5,10) |

### Phase 4: Reconvene Audit

When all 7 engine fixes are committed and Tests 1-4 pass on a continuous
90-day scenario with traces, reconvene the audit for final verification.

---

## Discipline

- I will NOT begin engine fixes until all 4 missing pieces are integrated
- I will fix ONE gap at a time, commit, re-run Tests 1 and 2 with traces,
  and confirm closure before the next
- I will publish each fix's trace-verified closure for independent review
- I will NOT claim pilot readiness until Tests 1-4 pass on the continuous
  90-day scenario

The loop is being closed correctly. The path is clear. Beginning
execution now.
