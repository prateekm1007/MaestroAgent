# Scientific History: MaestroAgent Research Program

## Project Identity

> An experimental platform for studying adaptive multi-agent systems using
> reproducible benchmarks, pre-registered experiments, causal ablations,
> and predictive theory evaluation.

The project evolved from an AI agent runtime (v2.1–v2.2) into an
experimental research platform (v2.3–v3.8). The runtime stabilized early;
the lasting contribution is the evaluation methodology.

---

## Phase 1: Architecture (v2.1–v2.4)

### v2.1–v2.2: Integrated Runtime
- Working memory, learning engine, strategy engine, governance repair loops
- Health tracking, federation, genetics, symbiosis
- The runtime was feature-complete by v2.2

### v2.3: Strategy + Experimentation + Planning
- Wilson CI-gated strategy promotion
- Thompson sampling A/B/n experiments with holdout
- Principle → Pattern → Strategy hierarchy
- Planner with EV/CE estimation

### v2.4: World Model + Policy + Meta-Learning
- Beta/Normal beliefs with exponential decay
- Policy layer (veto-capable, audit-logged)
- Meta-learning (funnel metrics, parameter recommendations)
- Selection-bias fix (conditioned Wilson CIs)

---

## Phase 2: Measurement (v2.5–v2.7)

### v2.5: Benchmark Suite + Ablation
- 6 domain benchmarks, ablation harness
- First ablation: world model +26 SR points (biggest contributor)
- 4 subsystems showed 0 effect (not exercised by benchmark)

### v2.6: Statistical Rigor
- Bootstrap CIs, Cohen's d, Mann-Whitney U, permutation tests
- 20-seed stability study: CV=0.041 ("very stable")
- Flagship reflection experiment: reflection does NOT improve calibration
- The benchmark falsified an assumption

### v2.7: Hypothesis-Driven Experimentation
- Epsilon sweep: best epsilon = 0.00 (exploration hurts with good priors)
- Reflection variants: all failed (lesson-matching bug diagnosed)
- 10,000-task longitudinal study: still learning at 10k, no plateau
- MAE drops 73%, approach diversity stable

---

## Phase 3: Causal Isolation (v2.8–v3.1)

### v2.8: Distribution Shift + Regret
- 7.7 SR point generalization gap (ID → OOD)
- World model is a memorizer, not a generalizer
- Cumulative regret metric: ID converges at task 245, OOD doesn't converge
- Threats-to-validity sections introduced

### v2.9: Causal Ablation + Cold-Start
- World model alone cuts regret 57%; planner alone does nothing
- Both-learn is WORSE than WM-only (planner interference discovered)
- Cold-start catches up to warm-start in 6,000 tasks
- Oracle paradox was seed noise (corrected v2.8 conclusion)

### v3.0: Planner Interference Factorial
- 4×3 factorial (α × defer-threshold): interference REPRODUCES
- Lowering α doesn't fix it; deferring doesn't fix it
- Only α=0.0 matches WM-only
- First external baseline: Maestro beats ReAct by +16.2 SR (p<0.0001)

### v3.1: Pre-Registered Design Principles
- 5 alternative update rules tested (pre-registered)
- HYPOTHESIS REJECTED: no rule coexists with WM
- Effect stability: 45/45 cells show disabled > ema
- Design principle: "no planner learning when WM active"

---

## Phase 4: Self-Correction (v3.2–v3.3)

### v3.2: Validity Regions + Episode Learning
- Episode-boundary learning at domain granularity: regret = disabled exactly
- REVISED v3.1 principle: "planner learning OK at coarse episode boundaries"
- Finer-grained capabilities: symbolic transfers (1.31), physical doesn't (0.38)
- One-symmetry experiments: specialization needs structural diversity

### v3.3: Predictive Theories
- TSS theory formulated: "same-scale ASSs interfere"
- Pre-registered predictions P2 (OOD) and P3 (cold-start)
- Both CONFIRMED: delta=0.0 in all 3 conditions
- All 3 alternative explanations rejected
- First confirmed predictive theory

---

## Phase 5: Stress Testing (v3.4–v3.5)

### v3.4: TSS Stress Tests
- Shared-adaptive-target stress test: TSS SURVIVES, SAT REJECTED
- Three-learner test: boundary condition — TSS applies to ASSs, not all mechanisms
- Theory maturity framework: Proposed → Predictive → Supported → Robust → General
- TSS classified as "Supported"

### v3.5: ASS Construct + Explanatory Compression
- Adaptive State System (ASS) formalized: storage + update + use
- 4/8 subsystems are ASSs (WM, Planner, Experiment, Strategy)
- Explanatory compression: TSS explains 21/22 (95.5%) of training corpus
- One miss: per_workflow_20 (boundary condition at ratio ~20)
- "Root cause" → "strongest supported explanatory variable"

---

## Phase 6: Out-of-Sample Failure (v3.6–v3.7)

### v3.6: Held-Out Corpus — TSS Drops to 70%
- 10 new experiments, predictions locked BEFORE running
- TSS: 7/10 (70%) — significant drop from 95.5%
- SAT: 10/10 (100%) — but was wrong on training corpus
- Root cause: ASS classification too coarse (Strategy/Experiment not operational)
- Maturity downgraded to "Supported (with calibration needed)"

### v3.7: AIC Measurement
- Adaptive Influence Coefficient: P(decision changes | subsystem ablated)
- WM has AIC=0 (operates in belief space, not action space)
- AIC didn't improve accuracy (still 70%) but revealed interference has TWO components
- Decision interference (captured by AIC) vs convergence interference (not captured)

---

## Phase 7: Measurement Science (v3.8)

### v3.8: Three-Dimensional Measurement
- Policy influence (AIC) + Belief influence (MAE delta) + Outcome influence (regret delta)
- WM: Policy=0, Belief=+0.024, Outcome=+20.0 → "belief-dominant"
- Dual-component model: 90% held-out (vs TSS 70%), +2 predictions for +2 assumptions
- Isolation experiment: inconclusive (planner reads both fields)
- Architecture-independent terminology: "behavioral" + "representational"

---

## Key Findings Summary

| Finding | Evidence | Status |
|---|---|---|
| World model is the dominant adaptive mechanism | v2.9 causal ablation: -57% regret | Confirmed |
| Planner updates interfere with WM | v3.0 factorial: 2.5x regret, 45/45 cells | Confirmed |
| Interference is about temporal scale, not shared target | v3.4 stress test: SAT rejected | Confirmed |
| Per-domain episode-boundary updates are safe | v3.2: regret = disabled; v3.3: holds OOD + cold-start | Confirmed |
| Reflection doesn't improve calibration | v2.6: d=0.121, p=0.006; v3.4: not an ASS | Confirmed |
| TSS explains 95.5% in-sample but only 70% out-of-sample | v3.5/v3.6 | Confirmed |
| Interference has behavioral + representational components | v3.7 AIC failure, v3.8 three-dimensional measurement | Partially confirmed |
| Dual-component model: 90% out-of-sample | v3.8: +2 predictions for +2 assumptions | Confirmed |
| System is sample-efficient (cold-start catches up in 6k tasks) | v2.9: cold SR=0.696 vs warm 0.688 | Confirmed |
| Exploration hurts with warm-start priors | v2.7: monotonic decline with epsilon | Confirmed |

---

## What Was Lost and What Survives

The v2.3–v3.8 codebase was lost in a filesystem reset. What survives:

1. **The v2.1–v2.2 runtime** — the execution substrate
2. **This conversation** — full history of every review and implementation
3. **The evaluation framework** — rebuilt from mature designs (v3.8 final form)
4. **The research theories** — rebuilt in final form (TSS + dual-component)
5. **The scientific methodology** — pre-registration, validity regions, model selection

What was NOT rebuilt:
- Intermediate runtime modules that were superseded
- Historical code snapshots that served only as stepping stones
- Experiments whose findings are documented above

The methodology is the product. The runtime is the substrate.
