# Contributing to Maestro

## The Merge-Gate Rule

> **No engineer — including the founder — can merge a feature unless it satisfies one of:**
>
> 1. A design partner explicitly requested it.
> 2. It removes friction from onboarding.
> 3. It improves a measured business outcome.
> 4. It fixes a reliability or security issue.
>
> If a feature doesn't satisfy one of those four criteria, it waits.

This discipline is what turns a sophisticated platform into a successful enterprise company.

---

## Why This Exists

The architecture is complete (see [CONSTITUTION.md](./CONSTITUTION.md)). The cognitive stack is frozen. The next risk is not underbuilding — it's overbuilding.

Every feature that doesn't satisfy the merge-gate rule:
- Adds complexity without adding customer value
- Increases the surface area that needs maintenance
- Distracts from the only hypothesis that matters:
  > *Organizations using Maestro execute measurably better than organizations that don't.*

---

## How to Contribute

### 1. Check the Merge-Gate

Before writing any code, ask: **which of the four criteria does this satisfy?**

If you can't answer with a specific, measurable reason — don't build it.

### 2. Link to Customer Evidence

In your PR description, include:
- Which design partner requested this (or which onboarding friction it removes, or which metric it improves)
- The expected business outcome
- How you'll measure whether it worked

### 3. Keep the Architecture Frozen

No new cognitive layers. The hierarchy is:
```
Learning Object → Pattern → Playbook → Policy → Governance Control →
Evidence → Case → Precedent → Receipt → Operational Knowledge
```

Do not add: Rule Layer, Wisdom Layer, Experience Layer, Meta Pattern Layer, Reflection Layer, or any other conceptual abstraction. The constitution is frozen until 10 enterprise organizations are running Maestro AND we have evidence that a new kind of knowledge cannot be represented by existing layers.

### 4. Customer-Driven, Not Imagination-Driven

The roadmap is driven by observed customer bottlenecks, not architectural imagination. If you're excited about a feature that no customer has asked for, channel that energy into finding a customer who needs it.

---

## What Gets Merged

✅ **Merged:**
- A design partner reported that approval latency is too high → optimize the approval flow
- Onboarding takes 45 minutes → reduce to 15 minutes by pre-configuring defaults
- Knowledge reuse is stuck at 20% → improve pattern retrieval relevance
- Security vulnerability in the receipt hashing → fix immediately

❌ **Not Merged:**
- "It would be cool if Maestro had voice mode"
- "Let's add a new agent type called 'Architect'"
- "What if we added a Wisdom Layer above Policies?"
- "Let's build a mobile app" (no customer has asked for it)

---

## The One Sentence

> **We are no longer a platform engineering company. We are a customer learning company.**

The architecture is complete. The next 6 months are about producing evidence that organizations using Maestro execute better than organizations that don't.

If we can do that with 3 design partners, we have a business.
If we can't, no amount of architecture will save us.

---

*See [DESIGN_PARTNER_PLAYBOOK.md](./DESIGN_PARTNER_PLAYBOOK.md) for the full customer validation plan.*
