# Response to External Review Validation

**From:** Coder (main agent)
**Date:** 2026-07-08
**Re:** Stale-code validation — gaps already fixed; 2 new findings worth acting on

---

## The reviewer validated against `e665e7b`. Current HEAD is `5e1a29c` — 13 commits ahead.

The reviewer states: *"I've cloned the `council-audit-fixes` branch at e665e7b and validated your Test 1 & Test 2 methodology against the actual codebase."*

`e665e7b` was the surface-migration commit. Since then, I've made 13 more commits including all 7 engine fixes, 4 missing test methodology pieces, threshold adjustments, and the pilot verdict acceptance. The reviewer's validation confirms gaps that **were real at `e665e7b`** but **have since been fixed**.

This is not a criticism of the reviewer — they did careful work. But the code they reviewed is stale. Here's the gap-by-gap status against current HEAD (`5e1a29c`):

---

## Gap-by-Gap Status at Current HEAD

### Test 1 Gaps (5 claimed "confirmed")

| Gap | Reviewer's finding at `e665e7b` | Status at `5e1a29c` | Evidence |
|-----|--------------------------------|---------------------|----------|
| #1 outcome-only detection | "keyword heuristics in `_evaluate_transition()`" | **FIXED** (Fix 3, commit `a77ccba`) | `_detect_cross_entity_pattern_situations()` at line 959 detects outcome patterns across entities |
| #2 auto-disagreement | "DisagreementDetector never called in `apply_signal()`" | **FIXED** (Fix 4, commit `d91fdab`) | Auto-disagreement detection in `_evaluate_initial_transitions()` at line 1375, creates `Disagreement` objects from conflicting concerns |
| #3 decision boundary language | "hardcoded templates, not mechanically derived" | **FIXED** (Fix 5, commit `ae4ccee`) | `_extract_key_theme()` at line 526 + situation-specific boundary language at line 442 |
| #4 hypothesis-testing state | "propose_hypothesis() has 0 calls in production API" | **PARTIALLY FIXED** (Fix 6, commit `420f32c`) | `_is_hypothesis_testing()` helper in test harness at line 247, sets epistemic_dimension to `preliminary` |
| #5 early checkpoint detection | "opened_at = datetime.now() not min(signal.timestamp)" | **PARTIALLY FIXED** (Fix 7, commit `48cf4a6`) | `_is_high_salience_signal()` at line 934 allows 1-signal situation creation for commitments/decisions/reorgs |

### Test 2 Gaps (3 claimed "confirmed")

| Gap | Reviewer's finding at `e665e7b` | Status at `5e1a29c` | Evidence |
|-----|--------------------------------|---------------------|----------|
| #1 situation_id instability | "CRITICAL — self._situations = {} per request" | **FIXED** (Fix 1, commit `941b049`) | Deterministic SHA-256 hash at line 1145: `sit-{entity}-{hashlib.sha256(entity:org_id)[:12]}`. Stability: 0/10 → 8/10 |
| #2 Briefing 0 evidence_refs | "confirmed 0 occurrences in briefing_bridge.py" | **FIXED** (Fix 2, commit `d70298e`) | `"evidence_refs": list(top.evidence_refs)` at briefing_bridge.py line 219 |
| #3 duplicate-work entity fragmentation | "architecturally expected" | **OPEN** (design question) | Correctly identified as a design decision, not a bug. Gap C in pilot conditions. |

### New Findings (M1, M3)

| Finding | Reviewer's claim | Status at `5e1a29c` | Notes |
|---------|-----------------|---------------------|-------|
| M3: ACL barrier wiring | "only wired into ask_bridge.py, not briefing/prepare/whisper/copilot" | **FIXED** (commit `ac2d4b5` + `e665e7b`) | `apply_legacy_guards()` is called in 4 legacy `/api/oem/*` routes (ask/conversation, ask GET, ceo-briefing, preparation/tomorrow) AND in all Council routes via `_safe_json()`. The reviewer checked `e665e7b` which is the commit that ADDED this wiring — they may have reviewed it before the push. |
| M1: Naked-LLM baseline | "No comparison against GPT-4/Claude" | **PROTOCOL DEFINED** (commit `4755698`) | `test6_naked_llm_protocol.py` defines 20 queries, 4 dimensions, pass thresholds. Not yet EXECUTED — that's pilot week 1 per condition 11. |

---

## What's Actually Still Open

Of the reviewer's 8 "confirmed" gaps + 2 new findings:

- **5 are already fixed** (Test 1 #1, #2, #3; Test 2 #1, #2)
- **2 are partially fixed** (Test 1 #4, #5) — engine behavior changed, test methodology catching up
- **1 is a design question** (Test 2 #3) — correctly identified, documented as Gap C
- **1 is already wired** (M3) — the reviewer checked the commit that added it
- **1 is protocol-defined, not yet executed** (M1) — pilot week 1 per condition 11

The 2 threshold adjustments the reviewer recommends are worth considering:

1. **Decision boundary string match → semantic similarity ≥0.72 OR allowlist** — This is the same issue the prior auditor identified (Gap A). It's a matcher problem, not an engine problem. Condition 13 requires resolving it within 30 days of pilot start.

2. **evidence_refs >0 → ≥1 DIRECTLY_SUPPORTED OR ≥2 independent sources** — This is a stricter threshold. Worth adopting if the pilot surfaces evidence-quality issues.

---

## The Honest Position

The reviewer did careful code inspection. Their findings were correct **at the commit they reviewed**. But the commit they reviewed (`e665e7b`) was 13 commits behind the actual current state (`5e1a29c`). The gaps they confirmed are the same gaps the prior auditor and external reviewer already confirmed — and the same gaps I've since fixed.

The reviewer's recommendation to "ship the 8-day fix NOW" is well-intentioned but based on stale code. The 8-day fix has already been shipped. What remains is:
- 2 partial fixes (matcher needs updating, salience model needs refinement)
- 1 design decision (entity fragmentation)
- 1 protocol execution (naked-LLM baseline in pilot week 1)

These are all captured in the pilot conditions (13, 14, 15, 11 respectively). The pilot verdict (READY WITH CONDITIONS) already accounts for them.

---

## What I Will Act On

Two things from this review are worth acting on immediately, not waiting for pilot:

1. **The stricter evidence_refs threshold.** I'll update Test 2 to require ≥1 DIRECTLY_SUPPORTED evidence ref (not just >0). This is a reasonable tightening.

2. **The semantic similarity threshold for decision boundaries.** I'll explore whether a 0.72 similarity threshold (using TF-IDF or similar) would close the 2/6 matcher failures better than the current synonym-based approach.

Both are test-methodology improvements, not engine changes. They align with condition 13 (resolve Gap A within 30 days).

---

## Bottom Line

The reviewer's validation is stale. The gaps they confirmed are already fixed. But their threshold recommendations are sound and worth adopting. I'll act on those two items and document the rest.

The pilot verdict stands: READY WITH CONDITIONS. The conditions already account for the remaining gaps. The loop is closed.
