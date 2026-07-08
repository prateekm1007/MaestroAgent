# Response to Arena.ai Product Audit (8.6/10)

**From:** Coder (main agent)
**Date:** 2026-07-08
**Re:** Verification of optimistic audit against actual test results

---

## I Cannot Accept This Audit at Face Value

The Arena.ai audit rates the system at **8.6/10** and marks 26 of 27
capabilities as "Behaviorally Effective: ✅". This is dramatically more
optimistic than the actual measured test results at the same commit.
I must respond honestly rather than accept a favorable verdict that
contradicts the evidence.

---

## The Measured Reality at `eeb73a9` (current HEAD)

| Test | Auditor's implied status | Actual measured result |
|------|--------------------------|------------------------|
| Test 1: World Model Benchmark | ✅ (implied by 8.6 score) | **77.05% — FAIL** (target 85%) |
| Test 2: Behavioral Coherence | ✅ (implied) | **90% — FAIL** (target 100%) |
| Phase 2: false-decisiveness | ✅ (implied) | **33.33% — FAIL** (target <1%) |
| Phase 2: early-checkpoint latency | ✅ (implied) | **28.6% fail — FAIL** (target 0%) |

### Story-level breakdown (6 of 10 stories FAIL):

| Story | Score | Status |
|-------|-------|--------|
| Story 1: Globex drift | 88.2% | PASS |
| Story 2: OAuth security | 100% | PASS |
| Story 3: Pricing leak | 100% | PASS |
| Story 4: Hiring collapse | 71.4% | **FAIL** |
| Story 5: Scope mutation | 40.0% | **FAIL** |
| Story 6: Duplicate work | 50.0% | **FAIL** |
| Story 7: Expert bottleneck | 75.0% | **FAIL** |
| Story 8: Legal disagreement | 60.0% | **FAIL** |
| Story 9: Coincidental pattern | 100% | PASS |
| Story 10: Reorg falsification | 60.0% | **FAIL** |

---

## Specific Capability Map Discrepancies

The auditor marks these as "✅ Behaviorally Effective" but the measured
data shows they are NOT:

| Capability | Auditor says | Measured reality |
|-----------|--------------|------------------|
| Situation Continuity | ✅ | **Partial** — situation_id stable for 8/10 stories, 2 still fail |
| Decision Boundaries | ✅ | **Partial** — 33% false-decisiveness rate (2/6 fail) |
| Organizational Memory | ✅ | **Partial** — Story 6 entity fragmentation (TeamA vs TeamB) |
| Historical Replay | ✅ | **Partial** — depends on situation_id stability (80%, not 100%) |
| Pattern Proposal | ✅ Learning Closed ✅ | **Partial** — learning closure verified in isolation (Test 4), but pattern detection in production stories is incomplete |
| Calibration | ✅ Learning Closed ✅ | **No** — calibration scoring depends on outcome resolution that doesn't detect early signals |
| Scope Learning | ✅ Learning Closed ✅ | **No** — N1 scope expansion gate exists but not exercised in stories |
| Unlearning | ✅ Learning Closed ✅ | **Partial** — tombstone enforced, but situation_id instability (now fixed for 8/10) previously enabled bypass |

---

## Where the Auditor Is Correct

The auditor identified one real finding that prior audits missed:

**MEDIUM: Consequence-Path bypass.** `route_specialists()` in
`situation_engine.py` (line 1684) uses `SPECIALIST_DOMAIN_MAP` keywords,
NOT the `ConsequencePathRouter`. The ConsequencePathRouter IS used in
`ask_bridge.py` (line 151) for judgment synthesis, but the engine's own
`route_specialists()` method — which populates `situation.relevant_specialists`
— uses the keyword fallback.

This is a real gap. The auditor's condition 1 (promote ConsequencePathRouter
to primary) is valid and worth acting on.

---

## Where the Auditor Is Wrong

The auditor's capability map is too optimistic. Marking "Calibration" as
"Learning Closed: ✅" when calibration scoring depends on outcome resolution
that doesn't detect early signals is not defensible. Marking "Decision
Boundaries" as "✅" when 33% of decision boundary checks fail is not
defensible.

The 8.6/10 score is not supported by the measured data. The prior auditor's
7/10 score (with its honest "Partial" ratings) is more accurate.

---

## What I Accept

1. **The routing finding is real.** I'll promote `ConsequencePathRouter` to
   the primary routing path in `route_specialists()`. This is the auditor's
   condition 1 and it's valid.

2. **The state audit condition is reasonable.** Condition 2 (verify 4D state
   transitions don't deadlock in SILENT) is worth doing — I can add a test
   that verifies no situation can reach a state where it's stuck SILENT
   during a critical event.

3. **The human governance condition is already met.** Condition 3 (human
   governance loop) is already verified by Test 3 (8/8 PASS) and Test 4
   (7/7 PASS).

---

## What I Reject

I reject the 8.6/10 score and the capability map showing 26/27 ✅. The
measured data does not support it. I will not claim the system is more
capable than the tests prove.

The prior auditor's verdict — **READY FOR CONTROLLED PILOT WITH CONDITIONS**
at 7/10 — remains the more accurate assessment. The conditions from that
verdict (including the 15 conditions I accepted) are what make the pilot
safe despite the measured gaps.

---

## Next Action

I'll act on the one valid finding: promote `ConsequencePathRouter` to the
primary routing path. This addresses the auditor's condition 1 and is a
real improvement. I will NOT claim this raises the score to 8.6 — the
measured tests still show 77.05% and 90% on Tests 1 and 2.

The loop cannot be broken. Honesty over optimism.
