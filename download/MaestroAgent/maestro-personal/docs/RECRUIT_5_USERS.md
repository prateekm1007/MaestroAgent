# Recruit 5 Dogfood Users — CEO Briefing

**Purpose:** Recruit, onboard, and measure the first 5 dogfood users for Maestro Personal. The 30-day result determines whether the product earns beta expansion or goes back to validation.

## Who to recruit

Target 5 users who match this profile:

| Trait | Why it matters |
|-------|----------------|
| Knowledge worker with 50+ commitments in flight | Enough signal density to test the intelligence layer |
| Uses calendar + email heavily | Real data to seed (even if manual entry for now) |
| Willing to install Python + run a local API | Technical comfort — this is a dogfood, not a product |
| Available for 14 days of daily use | Need longitudinal data to test learning + silence |
| Willing to give honest negative feedback | Sycophants don't move the product forward |

Good candidates: product managers, engineering leads, founders, consultants, analysts.

Bad candidates: anyone who says "I'll try it when there's a mobile app." They won't.

## What to tell them

> "Maestro Personal is a commitment intelligence layer for your work life. It tracks what you promised, what you broke, what's overdue, and what deserves your attention right now. It runs locally on your laptop and uses a GPU in the cloud for the LLM. We need 5 users to use it daily for 14 days and tell us honestly whether it catches things they would have missed. There's no mobile app, no OAuth, no polish — we're testing whether the intelligence is real before we build the rest."

## What to give them

1. The `DOGFOOD_INSTALL_GUIDE.md` (step-by-step setup)
2. Their `MAESTRO_PERSONAL_TOKEN` (generate a unique one per user)
3. The current Kaggle tunnel URL (shared — may need refresh)
4. A 30-minute onboarding call to walk through the first signal + Ask query

## What to measure

### Quantitative (from the API itself)

| Metric | How to get it | Target |
|--------|---------------|--------|
| Signals seeded per user | `GET /api/signals` count | ≥ 50 by day 7 |
| Ask queries per day | `/api/observability/traces` | ≥ 3/day average |
| Whisper dismissal rate | `/api/behavior/patterns` | < 30% (if everything is dismissed, the gate is broken) |
| LLM latency p50 | `/api/observability/traces` | < 30s |
| Cross-user isolation | (verify with audit) | 0 leaks |

### Qualitative (from surveys)

**Day 7 survey (5 questions):**
1. Did Maestro catch something you would have missed? (yes/no + describe)
2. Did Maestro miss something obvious? (yes/no + describe)
3. Was the LLM latency acceptable? (1-5)
4. Did any false positives annoy you? (yes/no + describe)
5. Would you continue using it? (yes/no/maybe)

**Day 14 survey (the north star):**
> **If Maestro disappeared tomorrow, would you feel you lost a meaningful intelligence layer?** (yes/no + explain)

Secondary day-14 questions:
- What did Maestro do that ChatGPT + your notes couldn't?
- What was the most useful single whisper/Ask answer?
- What was the most annoying false positive?
- Would you pay $15/month for this? (yes/no/maybe)
- Would you recommend it to a colleague? (yes/no)

## Go/no-go criteria for beta expansion

**Ship to broader beta (50+ users) only if ALL of these are true:**
- ≥ 3 of 5 users say "yes" to the north-star question
- ≥ 2 of 5 users seed 50+ signals and use Ask daily
- 0 critical security issues reported
- LLM latency p50 < 30s (acceptable for a GPU-backed beta)
- ≥ 1 user volunteers to continue without being asked

**Go back to validation if ANY of these are true:**
- < 2 of 5 users say "yes" to the north-star
- ≥ 3 of 5 users abandon before day 7
- Any cross-user data leak is found
- The most common feedback is "I don't trust the answers"

## Timeline

| Day | Action |
|-----|--------|
| 0 | Recruit 5 users; send install guide + tokens |
| 1 | Onboarding call with each user (30 min) |
| 2-3 | Users seed initial 20+ signals |
| 7 | Day-7 survey sent |
| 10 | Mid-point check-in: any blockers? |
| 14 | Day-14 survey + north-star question |
| 15 | Results compiled; go/no-go decision |

## What NOT to do during dogfood

- Do NOT add features mid-dogfood (freezes the baseline)
- Do NOT change the LLM model mid-dogfood (changes latency + quality)
- Do NOT read users' signal data without explicit permission (trust)
- Do NOT push users to say nice things (honesty > praise)
- Do NOT extend the dogfood past 14 days without a decision (momentum dies)

## The decision rule

After 14 days, the CEO makes one of three calls:

1. **SHIP TO BROADER BETA** — north-star ≥ 3/5 yes, no critical issues, latency acceptable. Invest in mobile + OAuth.
2. **CONTINUE VALIDATION** — mixed results. Fix the top 3 complaints, re-run with 5 new users.
3. **PIVOT OR PAUSE** — north-star < 2/5 yes. The intelligence layer isn't proven yet. Go back to the roadmap and fix Memory/Copilot/Silence before another dogfood.

This is the gate. The 90-day roadmap exists to make option 1 the most likely outcome.
