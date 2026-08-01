# Independent Production Audit - Live Verification
**Date:** 2026-07-28
**Auditor:** Autonomous agent (direct HTTP probing, no synthesis)
**Backend commit:** a3bf449a48 (build 2026-07-27T19:59:51)
**Method:** 50+ real HTTP requests against production

## Executive Summary

The product has dramatically improved on latency since prior audits (28-75s down to 0.8s).
But three critical bugs remain that make the product unusable for real work:

1. Ask retrieval is broken - abstains on queries where evidence exists
2. State tracking is broken - all commitments have state=unknown
3. Data hygiene is broken - 33 PII leaks in /api/signals

## Latency Fix Confirmed (p50=0.8s)

All 7 test queries returned in 0.7-0.8s on populated bootstrap account.
This is world-class latency. The prior 28-75s issue is FIXED.

## Critical Bug #1: Ask Retrieval Fails

On bootstrap account (25 commitments, 10 active per status endpoint),
POST /api/ask returns "I don't have any records" with confidence=0.0
for EVERY query including "What commitments do I have?"

The retrieval layer is disconnected from the ledger.

## Critical Bug #2: State Tracking Broken

/api/commitments returns 25 items all with state="unknown".
System cannot distinguish active/completed/cancelled.

## Critical Bug #3: 33 PII Leaks

Bootstrap /api/signals contains: kotak (12), zerodha (3), 6POP6 client code (1),
prateek emails (2), API token UUIDs (3), spotify (6), paypal (1), aws billing (1),
product hunt (4). Total: 33 leaks.

## Verdict: Yellow - Promising Prototype

Performance: 9/10 (fixed)
Trust: 3/10 (still broken)
Data Hygiene: 1/10 (worse)
State Consistency: 2/10 (still broken)

## Required Fixes (Priority Order)

1. P0: Fix Ask retrieval - evidence exists in ledger but Ask does not find it
2. P0: Purge PII from bootstrap account
3. P1: Fix state tracking
4. P2: Ground Ask in ledger state
