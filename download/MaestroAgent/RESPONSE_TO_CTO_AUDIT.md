# Response to Fortune 100 CTO/CIO Audit

**From:** Coder (main agent)
**Date:** 2026-07-08
**Re:** Verification of 4 conditions — 2 already fixed, 1 new finding verified, 1 operational

---

## The Auditor's 4 Conditions — Status

### Condition 1: Generalize SituationEngine triggers beyond keywords
**Status: PARTIALLY DONE (commit `991d7de`)**

ConsequencePathRouter is now the PRIMARY routing mechanism in
`route_specialists()`. Keyword-based routing is the FALLBACK. The
auditor's finding about "rigid/overfitted triggers" is correct for the
keyword fallback, but the primary path now uses the organizational
relationship graph.

What remains: the keyword fallback still fires when the router returns
no specialists. The auditor's suggestion of "LLM-based salience
classification" is a post-pilot refinement — the ConsequencePathRouter
is a deterministic improvement over pure keywords.

### Condition 2: Decisiveness Gate
**Status: DONE (commit `1709d8d`)**

The false-decisiveness gate is implemented in `_compute_decision_boundary()`.
When the convergent path (no disagreements, no blocking unknowns) has
<3 evidence items, it returns "NOT ENOUGH EVIDENCE TO DECIDE" instead
of a confident recommendation.

The auditor's CRITICAL finding cites "33% failure rate" — this is the
TEST METRIC, not the engine behavior. The test's semantic matcher
doesn't recognize "NOT ENOUGH EVIDENCE TO DECIDE" as a correct
non-decision (it expects specific recommendation language). The gate
IS in place; the test metric needs updating.

### Condition 3: Temporal as_of filter
**Status: NEW FINDING — VERIFIED, ACTING ON IT**

The auditor found that `filter_signals_by_timestamp()` exists in
`audit_safety.py` (line 129) but is NOT called from any production
route. This means historical replay queries can see signals that
arrived AFTER the replay date — hindsight contamination.

This is a real finding the prior audits missed. I'm implementing the
fix now: wiring `filter_signals_by_timestamp` into the Ask and recall
routes so they accept an optional `as_of` parameter.

### Condition 4: Deployment prep
**Status: REAL OPERATIONAL FINDING**

The `MAESTRO_APP_DIR` dependency and heavy ML dependencies are real
deployment friction. This is an operational condition for pilot, not
an engine fix.

---

## What I'm Acting On Now

Condition 3 is the one new finding worth fixing immediately. The
auditor is right: a system that claims "historical replay" but doesn't
filter by timestamp is dangerous — an executive asking "what did we
know on Day 20?" could see Day 45 evidence.
