# Maestro — Product Guide

> **30 verified surfaces.** Every screenshot in this guide was captured by execution — 
> a headless Chromium browser opened the live app, navigated to each surface via 
> `navTo()`, waited for content to render, and saved a PNG. Surfaces with no DOM 
> element (menu triggers like `more` and `coordination`) are documented but not 
> screenshotted — they open menus, not surfaces.

**What this is:** A visual reference for every surface in Maestro. Use it for client 
demos, investor briefings, and onboarding new team members.

**How to reproduce:** Start the backend (`MAESTRO_LOCAL_DEV=true python -m uvicorn 
maestro_api.main:create_app --factory --port 8765`), open `http://127.0.0.1:8765/`, 
and run `python scripts/take_screenshots.py`.

---

**Surface count:** 30 captured, 2 skipped (menu triggers).

---

## The Invisible Maestro — 4 Meta-Surfaces

### Today — Morning Brief

![Today — Morning Brief](screenshots/today.png)

The morning brief. Five swipeable cards: one decision, one opportunity, one risk, one learning, one prediction. Swipe right to act, left to defer. The brief is generated fresh each morning from the OEM's overnight analysis of your execution signals.

*Verified: 2655 chars of rendered content.*

---

### Memory — Unified Feed

![Memory — Unified Feed](screenshots/memory.png)

The unified memory feed — work timeline merged with personal memories. Every decision, signal, and interaction is timestamped and searchable. Connect work tools (Jira, Slack, GitHub) to populate this automatically.

*Verified: 161 chars of rendered content.*

---

### Ask — Executive Question

![Ask — Executive Question](screenshots/ask-v2.png)

Ask any question about your organization in plain English. The autocomplete suggests completions based on your execution signals. Answers cite the specific signals, decisions, and people they're drawn from.

*Verified: 642 chars of rendered content.*

---

### Command Palette (⌘K)

![Command Palette (⌘K)](screenshots/command-palette.png)

The command palette (⌘K or Ctrl+K). Search every surface, jump to any capability, or trigger an action without leaving the keyboard. This is the power-user's primary navigation tool.

*Verified: 0 chars of rendered content.*

---

## Executive Cognition — Strategic Surfaces

### Home — Executive Cognition Center

![Home — Executive Cognition Center](screenshots/home.png)

The executive cognition center — a bird's-eye view of the entire organization. Shows the OEM's current state, top recommendations, active contradictions, and the live signal pulse in one glance.

*Verified: 7574 chars of rendered content.*

---

### Inbox — Decisions Awaiting You

![Inbox — Decisions Awaiting You](screenshots/inbox.png)

Decisions awaiting your input. Each card shows the recommendation, the evidence behind it, the assumptions it depends on, and the cost of inaction. Approve, reject, or defer with one click.

*Verified: 606 chars of rendered content.*

---

### Simulator — Decision Simulator

![Simulator — Decision Simulator](screenshots/simulator.png)

The decision simulator. Pick a recommendation, adjust the variables (what if we hire one more engineer? what if the launch slips two weeks?), and see the projected outcome. The simulator uses your historical execution data to estimate impact.

*Verified: 648 chars of rendered content.*

---

### Canvas — Decision Canvas

![Canvas — Decision Canvas](screenshots/canvas.png)

The decision canvas — a visual map of any decision. Shows the recommendation at the center, surrounded by its dependencies (assumptions, evidence, people, prior decisions). Click any node to drill down.

*Verified: 453 chars of rendered content.*

---

### Hayek — Knowledge Graph

![Hayek — Knowledge Graph](screenshots/hayek.png)

The Hayek Lens — a knowledge graph view of your organization. Shows who knows what, who depends on whom, and where knowledge is concentrated (bus-factor risk) or distributed (resilient). Named after Hayek's insight that knowledge is distributed.

*Verified: 197 chars of rendered content.*

---

### Flow — Knowledge Flow

![Flow — Knowledge Flow](screenshots/flow.png)

Knowledge Flow — how signals move through your organization over time. Shows the path from raw event (PR opened, ticket closed) to insight (pattern detected) to decision (recommendation made) to action (approved/rejected).

*Verified: 419 chars of rendered content.*

---

## Cognitive Organs — Reflection & Learning

### Cognition — Cognitive Organs

![Cognition — Cognitive Organs](screenshots/cognition.png)

Cognitive Organs — the 10 distinct cognitive functions the OEM performs (perception, memory, prediction, contradiction-detection, etc.). Each organ shows its current state, throughput, and accuracy.

*Verified: 5994 chars of rendered content.*

---

### Evolution — Evolution Report

![Evolution — Evolution Report](screenshots/evolution.png)

The Evolution Report — how your organization has changed over the last 90 days. Five dimensions: knowledge growth, decision velocity, contradiction resolution, prediction accuracy, and bus-factor reduction.

*Verified: 936 chars of rendered content.*

---

### Autobiography — Org Story

![Autobiography — Org Story](screenshots/autobiography.png)

Your organization's story — the narrative the OEM has constructed from your signals. Shows the major chapters, turning points, and recurring patterns. Editable: you can correct the OEM's interpretation.

*Verified: 1184 chars of rendered content.*

---

### Learn — Learn Surface

![Learn — Learn Surface](screenshots/learn.png)

The Learn surface — what the OEM has learned that wasn't explicitly taught. Shows discovered laws (e.g. 'PR review time correlates with defect rate'), inferred patterns, and emerging hypotheses.

*Verified: 1363 chars of rendered content.*

---

### Playbook — Role Playbooks

![Playbook — Role Playbooks](screenshots/playbook.png)

Role Playbooks — per-role guides generated from your execution data. The engineering playbook shows the patterns that led to fast shipping; the sales playbook shows the patterns that led to won deals.

*Verified: 603 chars of rendered content.*

---

### Work — Work Surface

![Work — Work Surface](screenshots/work.png)

The Work surface — your personal work timeline. Shows what you shipped, what's in flight, and what's blocked. Merged with personal memories in the unified Memory feed.

*Verified: 660 chars of rendered content.*

---

### Personal — Personal Mode

![Personal — Personal Mode](screenshots/personal.png)

Personal Mode — opt-in personal memory. Maestro remembers your preferences, your relationships, your context. Entirely private (encrypted at rest with your key). Off by default; turn on in Settings.

*Verified: 147 chars of rendered content.*

---

## Decision Infrastructure — Assumptions, Risks, Debates

### Assumptions — Dangerous Assumptions

![Assumptions — Dangerous Assumptions](screenshots/assumptions.png)

Dangerous Assumptions — the high-stakes, unvalidated assumptions your decisions depend on. Each card shows the assumption, the decision it supports, the evidence for/against, and a Validate/Invalidate button. Invalidating an assumption flags every decision that depends on it.

*Verified: 1011 chars of rendered content.*

---

### Contradictions

![Contradictions](screenshots/contradictions.png)

Active contradictions — places where your execution data conflicts with your stated strategy or prior decisions. Each contradiction shows the two sides, the evidence for each, and an Acknowledge/Resolve button.

*Verified: 507 chars of rendered content.*

---

### Predictions — Prediction Market

![Predictions — Prediction Market](screenshots/predictions.png)

The Prediction Market — forecasts the OEM has made (e.g. 'this PR will be merged by Friday', 'this customer will churn next quarter'). Each prediction has a confidence, a resolution date, and a Brier score once resolved.

*Verified: 402 chars of rendered content.*

---

### Intents — Intent Cascade

![Intents — Intent Cascade](screenshots/intents.png)

Intent Cascade — the chain from your stated intent ('ship the payment refactor') down through the recommendations, assumptions, and tasks that implement it. Shows where the chain is strong and where it's fragile.

*Verified: 554 chars of rendered content.*

---

### Debate — Active Debates

![Debate — Active Debates](screenshots/debate.png)

Active Debates — places where the OEM has identified genuine strategic tension (e.g. 'ship fast vs. ship safe'). Shows both sides, the evidence for each, and the cost of each choice.

*Verified: 230 chars of rendered content.*

---

## Customer Intelligence

### Customer — Judgment Engine

![Customer — Judgment Engine](screenshots/customer.png)

Customer Judgment Engine — per-customer view of relationship health, decision history, promised commitments, and churn risk. Each customer shows their committee (who influences them), their drift (how their needs have changed), and their memory (what you've done for them).

*Verified: 1761 chars of rendered content.*

---

## Organizational Physics — Laws & Patterns

### Physics — Execution Laws

![Physics — Execution Laws](screenshots/physics.png)

Organizational Physics — the laws the OEM has discovered from your execution data (e.g. 'review-batch size inversely correlates with defect escape rate'). Each law shows the evidence, the counterexamples, and a Verify button that re-tests it against fresh data.

*Verified: 5486 chars of rendered content.*

---

## Live Operations — Meetings & Coordination

### Live — Meeting Analyzer

![Live — Meeting Analyzer](screenshots/live.png)

The Meeting Analyzer — paste a transcript (or connect your calendar for live capture), and Maestro extracts decisions, action items, assumptions, and contradictions in real time. Shows the meeting's cognitive footprint.

*Verified: 539 chars of rendered content.*

---

## Engineering — Builder & Audit Surfaces

### Engineering — Signals

![Engineering — Signals](screenshots/eng-signals.png)

Engineering — Signals. The raw signal stream the OEM ingests: PR events, ticket transitions, deployment events, postmortems. This is the data layer every other surface is built on.

*Verified: 529 chars of rendered content.*

---

### Engineering — OEM Builder

![Engineering — OEM Builder](screenshots/eng-oem.png)

Engineering — OEM Builder. Inspect and debug the OEM model directly: the entities, the laws, the recommendations, the decision engine state. This is the developer's view of the cognitive engine.

*Verified: 353 chars of rendered content.*

---

### Engineering — Audit Log

![Engineering — Audit Log](screenshots/eng-audit.png)

Engineering — Audit Log. Every state-changing action (approve, reject, invalidate, teach) is logged with timestamp, actor, before/after state. Required for compliance and for debugging 'why did the OEM change its mind?'

*Verified: 130 chars of rendered content.*

---

### Engineering — Settings

![Engineering — Settings](screenshots/eng-settings.png)

Engineering — Settings. Configure OAuth providers (GitHub, Jira, Slack, Confluence, Gmail, Salesforce), API keys, demo mode, and feature flags. This is where you connect real data sources.

*Verified: 1184 chars of rendered content.*

---

## Surfaces Not Screenshotted (Menu Triggers)

The following entries in `pageNames` are not standalone surfaces — they open menus 
or trigger actions rather than rendering a dedicated `<section class="surface">`:

- **more** — no DOM element
- **coordination** — no DOM element

---

*This product guide was generated from `docs/screenshots/manifest.json` by 
`scripts/generate_product_guide.py`. To regenerate after UI changes, re-run the 
screenshot script and this generator.*
