# Design Partner Success Playbook

> The most important document at Maestro right now.
> Not architecture. Not code. This.

---

## The Only Hypothesis That Matters

> **Organizations using Maestro's Product Delivery Operating Model improve execution quality faster than organizations that don't.**

Everything we've built reduces to this one falsifiable statement. The next 6 months exist to prove or disprove it.

---

## 1. How We Select Partners

### Criteria

| Criterion | Requirement |
|-----------|-------------|
| Type | Software product organization |
| Size | 20–3,000 engineers (we want a range) |
| Pain | Must articulate a specific execution pain (slow releases, compliance gaps, knowledge loss) |
| Access | Must grant access to baseline metrics (cycle time, rework rate, etc.) |
| Commitment | 90-day engagement, weekly check-ins |
| Champion | Must have an internal champion (VP Eng, Head of Product, CTO) |
| Exclusivity | Not required, but we limit to 10 partners total |

### Ideal Partner Profile

- Engineering-led organization (not sales-led)
- Ships software at least weekly
- Has governance/compliance requirements (SOC2, accessibility, security)
- Has experienced knowledge loss when people leave
- Is frustrated with their current tool sprawl (Jira + Confluence + Slack + GitHub + email)

### Anti-Patterns (Reject These)

- "We want to use AI" (wrong motivation — they want AI, not execution improvement)
- "Can you integrate with our custom ERP?" (too early — we need standard workflows first)
- "We need 47 custom policies" (not a design partner — they're a consulting engagement)
- No willingness to share metrics (we can't validate without data)

---

## 2. How We Onboard Them

### Week 1: Operating Model Definition

- Adopt the Product Delivery template (`POST /api/templates/product-delivery/adopt`)
- Customize: org hierarchy, approval chains, policies
- Connect integrations: Jira, GitHub, Slack (minimum 3)
- Complete Design Partner onboarding stages 1–5

### Week 2: First Guided Executions

- Run 3–5 real workflows through Maestro
- These should be ACTUAL work the team needs done (not test projects)
- Goal: prove the system executes real work end-to-end
- Collect feedback on friction points

### Week 3: Baseline Measurement

- Measure BEFORE metrics (see Section 3)
- This is the control — we compare everything against this
- Document current workflow (how do they ship today?)

### Week 4–12: Active Usage

- Team uses Maestro for real work
- Weekly check-ins (30 min)
- Collect metrics automatically via receipts
- Track friction points and feature requests

---

## 3. What Metrics We Collect

### Baseline (Before Maestro)

| Metric | How to Measure | Why |
|--------|---------------|-----|
| Cycle time (idea → production) | Ask the team; verify with Jira/GitHub | The headline number |
| Rework rate | % of PRs rejected or significantly revised | Quality indicator |
| Knowledge reuse | % of new work that references past work | Compounding indicator |
| Governance violations | Count of compliance incidents per quarter | Risk indicator |
| Onboarding time | Time for new engineer to ship first PR | Learning indicator |
| Documentation quality | Self-reported 1-10 scale | Institutional knowledge |
| Approval latency | Average time from PR ready → approved | Bottleneck indicator |

### During Maestro (Auto-Collected)

Every metric is computed from Execution Receipts — no manual reporting.

| Metric | Source | API |
|--------|--------|-----|
| Cycle time | Receipts | `GET /api/metrics` |
| Rework rate | Receipts (rejected/edited outcomes) | `GET /api/metrics` |
| Knowledge reuse | Receipts (patterns referenced) | `GET /api/metrics` |
| Compliance score | Receipts (governance violations) | `GET /api/metrics` |
| Audit readiness | Receipts (evidence completeness) | `GET /api/metrics` |
| Hours saved | Estimated from execution count | `GET /api/metrics` |
| **EII** | Composite of all above | `GET /api/eii` |
| **OED** | After 90 days − Before | `GET /api/oed/:orgId` |

### After 90 Days

- Run the Simulation Engine on their workflow
- Generate the ROI Report (`GET /api/roi-report`)
- Compare against baseline
- This becomes the case study

---

## 4. What Success Looks Like

### 30 Days

- [ ] 10+ real executions completed
- [ ] Design Partner onboarding 100% complete
- [ ] All integrations connected and syncing
- [ ] First patterns emerging (2+ projects of same class)
- [ ] First governance controls tested
- [ ] Friction log: <10 blocking issues

### 60 Days

- [ ] 30+ real executions completed
- [ ] Knowledge reuse rate > 30% (patterns being referenced)
- [ ] Compliance score > 80%
- [ ] First measurable cycle time improvement (any %)
- [ ] Team self-reported satisfaction > 7/10
- [ ] Friction log: <3 blocking issues

### 90 Days

- [ ] 50+ real executions completed
- [ ] **OED > 0** (organization is executing better than baseline)
- [ ] Cycle time reduced by ≥ 15%
- [ ] Knowledge reuse > 50%
- [ ] Zero critical governance violations
- [ ] Rework rate reduced by ≥ 20%
- [ ] Team would be "disappointed if Maestro went away" (5/5)
- [ ] Case study drafted and approved

### Product-Market Fit Declaration

We declare PMF when **3 independent design partners** achieve:
- OED > 0
- Cycle time reduction ≥ 15%
- Team satisfaction ≥ 7/10

One customer can be a coincidence. Three customers with measurable improvements demonstrate repeatability.

---

## 5. Evidence Needed Before Charging

### Free During Design Partner Phase

- No charge for 90 days
- We're learning from them; they're learning from us
- They get: full platform, unlimited executions, dedicated support
- We get: metrics, feedback, case study rights

### When to Start Charging

After 90 days, if the partner achieves OED > 0, we offer:
- **$30/user/month** (Product Delivery plan)
- **$50/user/month** (with governance + compliance features)
- **Custom** (enterprise with SSO, audit, SLA)

If OED ≤ 0, we extend free for another 90 days or part amicably.

### Pricing Principle

> We charge for completed work, not for AI access.
> If Maestro doesn't improve execution, we don't deserve to be paid.

---

## 6. When We Declare Product-Market Fit

### The Three-Customer Rule

PMF is declared when **3 independent design partners** (not related, not referred by each other) all achieve:

1. **OED > 0** (measurable execution improvement)
2. **Cycle time reduction ≥ 15%** (the headline metric)
3. **Team satisfaction ≥ 7/10** (they want to keep using it)
4. **At least one unprompted "how do we expand this?"** request

### What PMF Unlocks

- Series A fundraising (with evidence, not just architecture)
- Expansion beyond Product Delivery (Legal, Compliance, Marketing)
- Public benchmark report
- Enterprise sales motion
- Team scaling (hire customer success, not just engineering)

### What PMF Does NOT Unlock

- More cognitive layers (architecture is frozen)
- More integrations (depth > breadth)
- More templates (Product Delivery is the wedge)
- More features (only customer-requested features get built)

---

## 7. The Execution Observatory

### What It Is

Every design partner contributes anonymous metrics to a shared dataset. No company sees another company's raw data — only aggregate statistics.

### What We Collect

- Cycle time (anonymized, by company size bucket)
- Rework rate
- Knowledge reuse rate
- Compliance score
- Approval latency
- Onboarding time

### What It Becomes

After 10+ partners:
- "Median PR review time for 75-engineer companies: 26 hours. Top 10%: 4 hours."

After 50+ partners:
- "Companies that parallelize security + legal review ship 23% faster (95% confidence, n=41)."

After 500+ partners:
- The proprietary dataset that makes Maestro impossible to compete with.

### Privacy Guarantees

- No raw execution data is shared
- Only aggregate statistics (medians, percentiles)
- Company names are never associated with metrics
- Partners can opt out at any time
- The dataset is one-way (data flows in, only aggregates flow out)

---

## 8. The Merge-Gate Rule

> **No engineer — including the founder — can merge a feature unless it satisfies one of:**
> 1. A design partner explicitly requested it.
> 2. It removes friction from onboarding.
> 3. It improves a measured business outcome.
> 4. It fixes a reliability or security issue.

If a feature doesn't satisfy one of those four criteria, it waits.

This discipline is what turns a sophisticated platform into a successful enterprise company.

---

## 9. Weekly Check-In Agenda

Every design partner gets a 30-minute weekly call.

### Agenda

1. **Metrics review** (5 min) — EII, cycle time, knowledge reuse, compliance
2. **Friction log** (10 min) — what's blocking adoption?
3. **Feature requests** (5 min) — what do they need? (logged for merge-gate evaluation)
4. **Wins** (5 min) — what worked well this week?
5. **Next week** (5 min) — what are they running through Maestro?

### What We're Listening For

- "I wish Maestro could..." (feature request → merge-gate)
- "It was frustrating when..." (friction → fix immediately)
- "We used it for..." (new use case → pattern emergence)
- "Our team noticed..." (organizational change → case study material)

---

## 10. Case Study Template

After 90 days, each design partner gets a case study:

```
[Company Name] Reduces Software Delivery Cycle Time by [X]%

Challenge:
[2-3 sentences about their pain before Maestro]

Solution:
[How they adopted Maestro — template, integrations, workflows]

Results (90 days):
- Cycle time: [before] → [after] ([X]% reduction)
- Knowledge reuse: [before] → [after] ([X]% increase)
- Compliance violations: [before] → [after]
- Rework rate: [before] → [after] ([X]% reduction)
- Onboarding time: [before] → [after]

Quote:
"[Champion quote about impact]"

OED: [score]
```

This is what closes the next 10 customers.

---

## The One Sentence

> **We are no longer a platform engineering company. We are a customer learning company.**

The architecture is complete. The next 6 months are about producing evidence that organizations using Maestro execute better than organizations that don't.

If we can do that with 3 design partners, we have a business.
If we can't, no amount of architecture will save us.

---

*This document is more important than another 10,000 lines of code.*
