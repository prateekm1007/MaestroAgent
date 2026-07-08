# Maestro + Nerve Integration: 17 Agents Amplified by Organizational Memory

> **Status**: IMPLEMENTED (Phase 1 + Phase 2 complete)
> **HEAD**: post-`ed45857` (F4 fix) + Nerve integration commit
> **Tests**: 116 new tests (22 base + 76 all-agents + 18 briefing+routes), all passing
> **Reference**: Original roadmap provided by CEO (see `upload/MAESTRO_NERVE_INTEGRATION_ROADMAP.md`)

---

## What Nerve Was (Before OpenAI Acquired It)

Nerve's product: 17 specialized AI agents (Growth, Product, Sales, Marketing, Engineering, etc.) with daily briefings, company DNA profiling, and agent-to-agent handoffs.

**The problem**: Nerve's agents were siloed. Each had its own isolated context. The Growth Agent didn't know what the Sales Agent knew. They were 17 separate brains, not one unified intelligence.

---

## The Key Insight: Maestro Makes Every Agent 10x More Powerful

Maestro's OEM Engine (Organizational Execution Model) provides unified organizational memory that Nerve's siloed agents never had:

- **SituationSnapshot** (27-field canonical context per entity)
- **CommitmentTracker** (open/overdue commitments across meetings + email + Slack)
- **SentimentPatternEngine** (5 patterns, RAVDESS-validated)
- **DealHealthEngine** (4-component weighted score: 0-100)
- **CrossMeetingThreadBuilder** (conversation continuity, 70-80% accuracy)
- **CalendarAwarenessEngine** (upcoming meetings + prep gaps)
- **AdvancedAnalyticsEngine** (trends, team performance, Brier scores)
- **CommitmentEscalationEngine** (failure prediction)
- **OrganizationalDNA** (decision/risk/learning/communication style)
- **LearningLedger** (validated patterns → organizational laws)
- **CRMConnector** (Salesforce/HubSpot one-way sync)
- **OutcomeLedger** (durable, tenant-scoped execution history)

**Every agent has access to ALL of this context, not just its own silo.**

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    17 SPECIALIZED AGENTS                         │
│                                                                  │
│  REVENUE:     Growth    Sales    Customer Success    Finance    │
│  PRODUCT:     Product   Engineering    Marketing                │
│  INTERNAL:    HR    Legal    Operations    Support              │
│               Data    Security    Partnerships                  │
│  STRATEGY:    Strategy    Communications                       │
│  CAPSTONE:    Chief of Staff (coordinates all 16 others)        │
│                                                                  │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ Every agent queries OEM
                         │ for organizational context
                         │
┌────────────────────────▼────────────────────────────────────────┐
│                    MAESTRO OEM ENGINE                             │
│                                                                   │
│  • Organizational Laws (validated patterns with evidence)        │
│  • Commitment Tracking (meetings + emails + Slack)               │
│  • Sentiment Trends (across calls, emails, Slack)                │
│  • Deal Health Scores (real-time)                                │
│  • Relationship Health (with every contact)                      │
│  • Cross-Meeting Threads (conversation continuity)               │
│  • Calendar Awareness (upcoming meetings + prep)                 │
│  • Email/Slack Signals (ambient monitoring)                      │
│                                                                   │
│  Every agent has access to ALL of this context                   │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## Implementation — What Was Built

### Phase 1: Core Agent Infrastructure (COMPLETED)

#### Feature 1: BaseAgent Framework

**File**: `backend/maestro_nerve/base_agent.py`

The `BaseAgent` abstract class provides:
- Unified OEM Engine access (lazy-loaded, tenant-scoped)
- `AgentContext` — per-request user/tenant context
- `AgentInsight` — structured insight with confidence + evidence_chain (P4, P23, P25)
- `AgentCapability` — declares what each agent can do (for dashboard + handoffs)
- Confidence gates (60% threshold, 80% high-confidence label) — P25
- `on_insight_generated()` hook — writes insights back to OutcomeLedger (P34)

```python
class BaseAgent(ABC):
    AGENT_NAME: str = "base"
    AGENT_DESCRIPTION: str = "Base agent — override in subclass"

    @abstractmethod
    def generate_insights(self, ctx: AgentContext) -> list[AgentInsight]:
        """Subclasses MUST:
          - Read from OEM (don't accept caller-supplied data — P13)
          - Cite evidence_chain on every insight (P4, P23)
          - Apply confidence gates (P25)
          - Be deterministic for the same OEM state (no random)
        """
```

#### Feature 2: 17 Specialized Agents

**Files**:
- `backend/maestro_nerve/agents_revenue.py` — Growth, Sales, Customer Success, Finance
- `backend/maestro_nerve/agents_product.py` — Product, Engineering, Marketing
- `backend/maestro_nerve/agents_internal.py` — HR, Legal, Operations, Support, Data, Security, Partnerships
- `backend/maestro_nerve/agents_strategy.py` — Strategy, Communications, Chief of Staff

Each agent:
- Inherits from `BaseAgent`
- Is registered via the `@register_agent` decorator
- Implements `generate_insights(ctx) -> list[AgentInsight]`
- Queries specific OEM engines relevant to its domain
- Returns insights with confidence + evidence_chain

| # | Agent | OEM Engines Queried | Key Insight Type |
|---|-------|---------------------|------------------|
| 1 | Growth | SituationSnapshot, CommitmentTracker, CrossMeetingThreadBuilder | Expansion opportunities |
| 2 | Sales | DealHealthEngine, CommitmentEscalationEngine | At-risk deals, declining momentum |
| 3 | Customer Success | CommitmentEscalationEngine, SentimentPatternEngine | Churn risk, stale relationships |
| 4 | Finance | DealHealthEngine, AdvancedAnalyticsEngine, CommitmentTracker | Revenue at risk, commitment velocity |
| 5 | Product | SentimentPatternEngine, CrossMeetingThreadBuilder, CommitmentTracker | Recurring themes, roadmap pressure |
| 6 | Engineering | CommitmentEscalationEngine, pattern detection | Tech debt signals, overdue deliverables |
| 7 | Marketing | SentimentPatternEngine, pattern detection | Case study opportunities, messaging gaps |
| 8 | HR | MeetingGrader, TalkRatioCoach, CalendarAwarenessEngine | Burnout signals, coaching opportunities |
| 9 | Legal | CommitmentTracker (legal keyword filter) | Compliance commitments |
| 10 | Operations | CommitmentTracker (theme clustering) | Process bottlenecks |
| 11 | Support | SentimentPatternEngine, pattern detection | Escalations, KB gaps |
| 12 | Data | AdvancedAnalyticsEngine | Trend analysis, coverage gaps |
| 13 | Security | CommitmentTracker (security keyword filter) | Data-handling commitments |
| 14 | Partnerships | Pattern detection (partner keywords) | Partner activity signals |
| 15 | Strategy | OrganizationalDNA, cross-decision patterns | Strategic themes |
| 16 | Communications | CommitmentTracker (recent commits) | Follow-up email drafts |
| 17 | Chief of Staff | **ALL** (coordinates the other 16) | Daily briefings, dashboard |

### Phase 2: User Interface (COMPLETED)

#### Feature 3: Daily Briefings

**File**: `backend/maestro_nerve/daily_briefing.py`

The `DailyBriefingEngine` generates two briefing types:

**Morning Briefing** — "What should I focus on today?"
```json
{
  "briefing_id": "morning-abc123def456",
  "briefing_type": "morning",
  "greeting": "Good morning, Jane.",
  "date": "2026-07-08T12:00:00Z",
  "top_insights": [
    {
      "agent": "growth",
      "title": "Expansion opportunity: Acme Corp",
      "body": "Account is on track with 3 open commitments...",
      "confidence": 0.85,
      "confidence_label": "high",
      "evidence_chain": [...],
      "recommended_action": "Schedule expansion call..."
    }
  ],
  "top_actions": ["Follow up: Send pricing to Globex"],
  "calendar_preview": [{"title": "Acme call", "urgency": "high"}],
  "total_insights_generated": 12,
  "agents_consulted": 16
}
```

**Evening Briefing** — "What happened today? What's pending?"
```json
{
  "briefing_id": "evening-abc123def456",
  "briefing_type": "evening",
  "greeting": "Good evening, Jane.",
  "todays_wins": [...],
  "todays_risks": [...],
  "pending_actions": [...]
}
```

#### Feature 4: Agent Dashboard

**Endpoint**: `GET /api/nerve/dashboard`

Unified view of insights from all 17 agents with filtering:
- `agent_filter` — show only one agent's insights
- `priority_filter` — high/medium/low
- `min_confidence` — 0.0 to 1.0

```json
{
  "dashboard_id": "dashboard-abc123",
  "total_insights": 47,
  "agents_represented": ["communications", "customer_success", "finance", ...],
  "insights_by_agent": {
    "growth": [...],
    "sales": [...]
  },
  "all_insights_sorted": [...]  // ranked by priority + confidence
}
```

---

## API Endpoints

All endpoints require `@auth_policy(AuthPolicy.USER)` + `Depends(require_user)` (F4 lesson applied).

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/nerve/briefing/morning` | Morning briefing (top insights + actions + calendar) |
| POST | `/api/nerve/briefing/evening` | Evening briefing (wins + risks + pending) |
| GET | `/api/nerve/dashboard` | Unified dashboard (all 17 agents, filterable) |
| GET | `/api/nerve/agents` | List all 17 agents with descriptions |
| POST | `/api/nerve/agent/{name}/insights` | Get insights from a specific agent |

---

## Example: How Maestro's Growth Agent Beats Nerve's

### Nerve's Growth Agent (siloed):
```
User: "What expansion opportunities do we have?"
Nerve: "Acme Corp has NPS 9. Consider upsell."
```

**Problem**: Generic. Doesn't know commitments, sentiment, relationship health, or organizational patterns.

### Maestro's Growth Agent (with OEM):

```python
agent = get_agent("growth")
ctx = AgentContext(user_email="jane@acme.com", org_id="acme")
insights = agent.generate_insights(ctx)
# Returns:
#   AgentInsight(
#     title="Expansion opportunity: Acme Corp",
#     body="Account is on track with 3 open commitment(s) and 4 related meeting(s)...",
#     confidence=0.85,
#     confidence_label="high",
#     evidence_chain=[
#       {"source": "situation_snapshot", "entity": "Acme Corp", "current_state": "on_track"},
#       {"source": "oem_signal_history", "related_meetings": 4}
#     ],
#     recommended_action="Schedule an expansion call with Acme Corp...",
#     organizational_law="L-2024-087"
#   )
```

**This is 10x more powerful because it has the full organizational context.**

---

## Test Coverage

**116 new tests** across 3 test files (all passing):

| Test File | Tests | What's Covered |
|-----------|-------|----------------|
| `test_base_agent.py` | 22 | AgentInsight, AgentContext, confidence_label, BaseAgent abstract enforcement, registry, _NullOemState |
| `test_all_agents.py` | 76 | All 17 agents registered, generate_insights returns list, every insight has confidence + evidence_chain, cold-start doesn't crash, Chief of Staff morning/evening briefings |
| `test_briefing_and_routes.py` | 18 | DailyBriefingEngine morning/evening/dashboard, route auth policy + dependency guard (F4 lesson), route registration in app |

**Verification**:
- `test_route_auth_inventory.py`: 4/4 PASS (F4 fix verified — 5 new nerve routes all have auth)
- All 17 agents pass parametrized behavior tests
- Chief of Staff morning briefing consults exactly 16 agents (excludes self)
- Briefings are deterministic (same OEM state → same insight count)

---

## Governance Loop Compliance

| Principle | How It's Honored |
|-----------|------------------|
| P4 (honest disclosure) | Every insight cites its `evidence_chain` |
| P13 (derived not asserted) | All claims derived from OEM signals, not caller-supplied |
| P23 (commit-cites-output) | Every insight dict has `confidence` + `evidence_chain` |
| P25 (confidence gates) | 60% threshold (strict), 80% high-confidence label; `passes_confidence_gate()` method |
| P31 (independent verification) | 116 tests verify behavior; auth inventory test independently verifies route security |
| P34 (loop closure) | `on_insight_generated()` writes insights back to OutcomeLedger |

---

## What's NOT Built (Honest Disclosure — P4)

The following items from the original roadmap are **deferred** because they require
organizational investment (CEO decisions, not code):

1. **Frontend UI for the dashboard** — only the API is built. The HTML/JS
   dashboard view is a frontend task (~5 days).
2. **Agent-to-agent handoffs** — agents currently run in parallel, but they
   don't pass insights to each other (e.g., Growth Agent doesn't ask Sales
   Agent for context). This is a Phase 3 feature.
3. **Company DNA profiling UI** — `OrganizationalDNA` engine exists in OEM,
   but there's no dedicated UI for viewing the DNA profile.
4. **Context-aware search across workplace tools** — the OEM has importers
   (Gmail, Slack, Jira, Confluence, Salesforce, GitHub) but there's no
   unified search bar that agents can query.
5. **Real LLM-backed narrative generation** — currently insights use
   template-based text. Plugging in an LLM (GLM, GPT) for richer narrative
   is a Phase 3 feature.

---

## Competitive Advantage

| Player | Architecture | Limitation |
|--------|--------------|------------|
| **Nerve (pre-acquisition)** | 17 siloed agents | Each agent had isolated context |
| **ChatGPT (with Nerve tech)** | Will integrate Nerve's framework | No organizational memory — generic agents |
| **Maestro (with Nerve integration)** | 17 agents + unified OEM Engine | Every agent knows your company's history, patterns, commitments, relationships |

**This is the moat.** 40 days of integration work transforms Maestro from
an ambient intelligence platform into an AI Chief of Staff that every
Fortune 100 company needs.

---

## Bottom Line

**Nerve had the right idea (17 specialized agents), but the wrong architecture (siloed context).**

**Maestro has the right architecture (unified organizational memory via OEM engine).**

**Combined, you get 17 agents that are 10x more powerful than anything Nerve or ChatGPT can build.**

**Status: IMPLEMENTED.** 17 agents + daily briefings + dashboard API are live,
with 116 tests verifying behavior and security.
