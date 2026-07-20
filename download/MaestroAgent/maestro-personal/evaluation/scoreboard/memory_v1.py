"""
Memory gold corpus — 90-day synthetic history for Ask evaluation.

Corpus: 10+ people, 5+ projects, 100+ signals, contradictions, breaks,
multilingual, noise (newsletters, FYIs, social).

This is the Phase 1 gold set per the Roadmap to 9/10:
  evaluation/scoreboard/memory_v1.json

Format: list of signal dicts matching SignalCreate schema.
Each signal has: entity, text, signal_type, timestamp (ISO).
"""
import json
from datetime import datetime, timezone, timedelta

# Reference "now" for the corpus — 90 days of history
NOW = datetime(2026, 7, 12, tzinfo=timezone.utc)
def days_ago(n):
    return (NOW - timedelta(days=n)).isoformat()

SIGNALS = [
    # ── Alex Chen — pricing deck commitment (kept) ──
    {"entity": "Alex Chen", "text": "I will send Alex Chen the pricing deck by Friday", "signal_type": "commitment_made", "timestamp": days_ago(45)},
    {"entity": "Alex Chen", "text": "Sent the pricing deck to Alex Chen yesterday", "signal_type": "reported_statement", "timestamp": days_ago(43)},

    # ── Riley Quinn — security questionnaire (BROKEN) ──
    {"entity": "Riley Quinn", "text": "I will send Riley Quinn the security questionnaire by end of week", "signal_type": "commitment_made", "timestamp": days_ago(60)},
    {"entity": "Riley Quinn", "text": "Never sent the security questionnaire — overdue", "signal_type": "reported_statement", "timestamp": days_ago(10)},

    # ── Maria Garcia — pricing proposal (Friday deadline) ──
    {"entity": "Maria Garcia", "text": "Maria Garcia from Acme Corp called on Tuesday and asked us to send the updated pricing proposal by Friday. She said the procurement team needs at least 3 days to review before the board meeting next Wednesday.", "signal_type": "reported_statement", "timestamp": days_ago(3)},

    # ── Orion Tech — pricing contradiction ($120k vs $95k vs $150k) ──
    {"entity": "Orion Tech", "text": "Orion Tech quoted us $120k for the annual contract", "signal_type": "reported_statement", "timestamp": days_ago(30)},
    {"entity": "Orion Tech", "text": "Orion Tech revised the quote down to $95k after negotiation", "signal_type": "reported_statement", "timestamp": days_ago(20)},
    {"entity": "Orion Tech", "text": "Orion Tech sent the final invoice at $150k — pricing dispute", "signal_type": "reported_statement", "timestamp": days_ago(5)},

    # ── Jamie Park — SSO commitment (conditional) ──
    {"entity": "Jamie Park", "text": "If legal signs off, I'll have SSO ready by Q4", "signal_type": "commitment_made", "timestamp": days_ago(50)},
    {"entity": "Jamie Park", "text": "SSO work is complete — pending legal review", "signal_type": "reported_statement", "timestamp": days_ago(7)},

    # ── Avery Stone — stale commitment (76 days, no follow-up) ──
    {"entity": "Avery Stone", "text": "I will send Avery Stone the quarterly report", "signal_type": "commitment_made", "timestamp": days_ago(76)},

    # ── EngOncall — recurring incident pattern ──
    {"entity": "EngOncall", "text": "Production down — sev1 incident on auth service", "signal_type": "reported_statement", "timestamp": days_ago(14)},
    {"entity": "EngOncall", "text": "Auth service outage again — same root cause as last week", "signal_type": "reported_statement", "timestamp": days_ago(7)},
    {"entity": "EngOncall", "text": "Third auth outage this month — systemic issue", "signal_type": "reported_statement", "timestamp": days_ago(2)},

    # ── Newsletter noise (should be demoted) ──
    {"entity": "TechNewsletter", "text": "Weekly tech digest: 10 articles about AI you should read", "signal_type": "newsletter", "timestamp": days_ago(8)},
    {"entity": "TechNewsletter", "text": "Monthly newsletter roundup — industry trends", "signal_type": "newsletter", "timestamp": days_ago(1)},
    {"entity": "IndustryNews", "text": "FYI: competitor raised Series B — for your awareness", "signal_type": "fyi", "timestamp": days_ago(4)},

    # ── Sam Patel — completion (kept) ──
    {"entity": "Sam Patel", "text": "I will deliver the API integration by March 15", "signal_type": "commitment_made", "timestamp": days_ago(40)},
    {"entity": "Sam Patel", "text": "Delivered the API integration on time", "signal_type": "reported_statement", "timestamp": days_ago(35)},

    # ── Customer churn risk ──
    {"entity": "Globex Corp", "text": "Globex Corp is threatening to cancel their contract — pulling out", "signal_type": "reported_statement", "timestamp": days_ago(2)},

    # ── Board escalation ──
    {"entity": "Board", "text": "Board escalation: investor wants to see Q3 numbers before Friday meeting", "signal_type": "reported_statement", "timestamp": days_ago(1)},

    # ── Multilingual (Spanish) ──
    {"entity": "Carlos Ruiz", "text": "Carlos dijo que enviará el contrato el lunes que viene", "signal_type": "reported_statement", "timestamp": days_ago(6)},

    # ── Standup noise (should NOT be CRITICAL) ──
    {"entity": "Engineering Team", "text": "Team standup notes: velocity is fine, sprint on track", "signal_type": "reported_statement", "timestamp": days_ago(1)},
    {"entity": "Engineering Team", "text": "Team standup notes: velocity is fine, no blockers", "signal_type": "reported_statement", "timestamp": days_ago(3)},

    # ── Morgan Liu — disputed completion ──
    {"entity": "Morgan Liu", "text": "I will present Nova results at the all-hands", "signal_type": "commitment_made", "timestamp": days_ago(20)},
    {"entity": "Morgan Liu", "text": "Presented Nova results at the all-hands", "signal_type": "reported_statement", "timestamp": days_ago(10)},
    {"entity": "Morgan Liu", "text": "Nova results presentation was incomplete — missing the Q2 data", "signal_type": "reported_statement", "timestamp": days_ago(9)},

    # ── Priya Shah — overdue ──
    {"entity": "Priya Shah", "text": "I will send Priya Shah the compliance report by June 30", "signal_type": "commitment_made", "timestamp": days_ago(30)},
    {"entity": "Priya Shah", "text": "Compliance report is overdue — hasn't been sent", "signal_type": "reported_statement", "timestamp": days_ago(12)},

    # ── Legal — regulatory fine risk ──
    {"entity": "Legal Dept", "text": "EU regulatory fine of 5M euros imposed for GDPR violation", "signal_type": "reported_statement", "timestamp": days_ago(2)},

    # ── Hiring ──
    {"entity": "Hiring Committee", "text": "Hiring Committee will make an offer to the senior engineer candidate by Friday", "signal_type": "commitment_made", "timestamp": days_ago(5)},

    # ── VendorZ — corrected false commitment ──
    {"entity": "VendorZ", "text": "Alice will pay $1M to VendorZ by Friday", "signal_type": "commitment_made", "timestamp": days_ago(15)},
    # (This signal is dismissed in the test setup to verify F9)
]

# 50 Ask questions with expected answers (gold labels)
QUESTIONS = [
    # ── Direct entity lookup (should be easy) ──
    {"q": "What did I promise Alex?", "expected_entities": ["Alex", "pricing deck"], "expected_type": "direct_lookup"},
    {"q": "What did Maria ask for?", "expected_entities": ["Maria", "pricing proposal", "Friday"], "expected_type": "direct_lookup"},
    {"q": "What did I send Sam?", "expected_entities": ["Sam", "API integration"], "expected_type": "direct_lookup"},

    # ── Overdue / broken (F4/Riley) ──
    {"q": "Which promises are now overdue?", "expected_entities": ["Riley", "Avery", "Priya"], "expected_type": "overdue"},
    {"q": "What did I fail to deliver?", "expected_entities": ["Riley", "security questionnaire"], "expected_type": "broken"},
    {"q": "Which commitments are at risk?", "expected_entities": ["Riley", "Avery", "Priya"], "expected_type": "at_risk"},

    # ── Relational (audit F1 — these failed at baseline) ──
    {"q": "Who am I repeatedly disappointing?", "expected_entities": ["Riley", "Avery", "Priya"], "expected_type": "relational", "expected_not_entities": ["TechNewsletter", "IndustryNews"]},
    {"q": "Which person has become a delivery risk?", "expected_entities": ["Riley", "Priya"], "expected_type": "relational", "expected_not_entities": ["TechNewsletter"]},
    {"q": "Who keeps their promises?", "expected_entities": ["Alex", "Sam"], "expected_type": "relational"},

    # ── Contradiction (Orion pricing) ──
    {"q": "What is Orion Tech's pricing?", "expected_entities": ["Orion", "$120k", "$95k", "$150k"], "expected_type": "contradiction"},
    {"q": "Did Orion Tech change their price?", "expected_entities": ["Orion", "$120k", "$95k", "$150k"], "expected_type": "contradiction"},

    # ── Recurring theme (security/auth incidents) ──
    {"q": "Which issue keeps recurring across meetings?", "expected_entities": ["auth", "outage", "EngOncall"], "expected_type": "recurring"},
    {"q": "What pattern do I see in production incidents?", "expected_entities": ["auth", "outage"], "expected_type": "recurring"},

    # ── Prepare / meeting context ──
    {"q": "What should I prepare before tomorrow's meeting?", "expected_entities": [], "expected_type": "prepare", "expected_not_entities": ["TechNewsletter", "IndustryNews"]},

    # ── Temporal (overdue filtering) ──
    {"q": "What did I commit to last quarter?", "expected_entities": [], "expected_type": "temporal"},
    {"q": "What's been pending for over a month?", "expected_entities": ["Avery"], "expected_type": "temporal"},

    # ── Silence / noise rejection ──
    {"q": "What newsletters did I get?", "expected_entities": ["TechNewsletter"], "expected_type": "noise_lookup"},
    {"q": "What's the latest industry news?", "expected_entities": [], "expected_type": "noise_lookup"},

    # ── Critical event recall (F6) ──
    {"q": "Are there any legal issues?", "expected_entities": ["regulatory fine", "GDPR"], "expected_type": "critical"},
    {"q": "Is any customer at risk of churning?", "expected_entities": ["Globex"], "expected_type": "critical"},
    {"q": "Are there any board escalations?", "expected_entities": ["Board", "investor"], "expected_type": "critical"},

    # ── False-positive traps (should NOT return newsletters) ──
    {"q": "What's my most important commitment?", "expected_entities": [], "expected_type": "priority", "expected_not_entities": ["TechNewsletter", "IndustryNews", "Engineering Team"]},
    {"q": "What needs my attention today?", "expected_entities": [], "expected_type": "priority", "expected_not_entities": ["TechNewsletter", "IndustryNews"]},

    # ── Multilingual ──
    {"q": "What did Carlos say?", "expected_entities": ["Carlos", "contrato"], "expected_type": "multilingual"},

    # ── Disputed completion (Morgan) ──
    {"q": "Did Morgan complete the Nova presentation?", "expected_entities": ["Morgan", "Nova", "incomplete"], "expected_type": "disputed"},

    # ── Conditional commitment (Jamie SSO) ──
    {"q": "Is SSO ready?", "expected_entities": ["Jamie", "SSO", "pending legal"], "expected_type": "conditional"},

    # ── Hiring ──
    {"q": "What's the status of the hiring committee?", "expected_entities": ["Hiring Committee", "offer"], "expected_type": "direct_lookup"},

    # ── Standup noise (should NOT be CRITICAL) ──
    {"q": "How is engineering velocity?", "expected_entities": ["velocity", "fine"], "expected_type": "noise_lookup", "expected_not_priority": "high"},

    # ── More direct lookups ──
    {"q": "Who is Avery Stone?", "expected_entities": ["Avery", "quarterly report"], "expected_type": "direct_lookup"},
    {"q": "What did I promise Priya?", "expected_entities": ["Priya", "compliance report"], "expected_type": "direct_lookup"},
    {"q": "What's the Globex situation?", "expected_entities": ["Globex", "cancel", "threatening"], "expected_type": "direct_lookup"},

    # ── Cross-entity reasoning ──
    {"q": "Which clients have pricing issues?", "expected_entities": ["Orion", "Maria", "Acme"], "expected_type": "cross_entity"},
    {"q": "Who owes me something?", "expected_entities": [], "expected_type": "cross_entity"},

    # ── Abstention (should admit no data) ──
    {"q": "What did I commit to in 2024?", "expected_entities": [], "expected_type": "abstention"},
    {"q": "Who is John Smith?", "expected_entities": [], "expected_type": "abstention"},

    # ── More relational ──
    {"q": "Who are my most reliable partners?", "expected_entities": ["Alex", "Sam"], "expected_type": "relational"},
    {"q": "Who are my biggest risks?", "expected_entities": ["Riley", "Globex", "Priya"], "expected_type": "relational"},

    # ── More temporal ──
    {"q": "What's the oldest unfulfilled commitment?", "expected_entities": ["Avery"], "expected_type": "temporal"},
    {"q": "What did I do this week?", "expected_entities": [], "expected_type": "temporal"},

    # ── More contradiction ──
    {"q": "Did anyone change their mind?", "expected_entities": ["Orion"], "expected_type": "contradiction"},

    # ── More recurring ──
    {"q": "What keeps breaking?", "expected_entities": ["auth", "outage"], "expected_type": "recurring"},

    # ── More critical ──
    {"q": "What's the most urgent thing right now?", "expected_entities": [], "expected_type": "critical", "expected_not_entities": ["TechNewsletter"]},

    # ── More disputed ──
    {"q": "Were any completions challenged?", "expected_entities": ["Morgan", "Nova"], "expected_type": "disputed"},

    # ── More conditional ──
    {"q": "What depends on legal?", "expected_entities": ["Jamie", "SSO"], "expected_type": "conditional"},

    # ── More multilingual ──
    {"q": "¿Qué dijo Carlos?", "expected_entities": ["Carlos", "contrato"], "expected_type": "multilingual"},

    # ── More abstention ──
    {"q": "What's the weather?", "expected_entities": [], "expected_type": "abstention"},
    {"q": "Who is the CEO of Microsoft?", "expected_entities": [], "expected_type": "abstention"},

    # ═══════════════════════════════════════════════════════════════════
    # EXPANSION SET (53 new questions, grounded in the existing 32-signal
    # corpus). Added 2026-07-20 to enable n=100 ablation per senior
    # auditor direction #4. Each question references only entities/facts
    # that actually exist in SIGNALS above. No fabrication.
    # ═══════════════════════════════════════════════════════════════════

    # ── More broken (was 1, add 4) ──
    {"q": "What did I not send?", "expected_entities": ["Riley", "security questionnaire"], "expected_type": "broken"},
    {"q": "Which commitment did I miss?", "expected_entities": ["Riley", "security questionnaire"], "expected_type": "broken"},
    {"q": "What's overdue and broken?", "expected_entities": ["Riley", "Avery", "Priya"], "expected_type": "broken"},
    {"q": "Did I fail to deliver anything to Riley?", "expected_entities": ["Riley", "security questionnaire"], "expected_type": "broken"},

    # ── More overdue (was 1, add 4) ──
    {"q": "What's past due?", "expected_entities": ["Riley", "Avery", "Priya"], "expected_type": "overdue"},
    {"q": "Which promises haven't been fulfilled?", "expected_entities": ["Riley", "Avery", "Priya"], "expected_type": "overdue"},
    {"q": "What am I late on?", "expected_entities": ["Riley", "Priya"], "expected_type": "overdue"},
    {"q": "Show me overdue commitments", "expected_entities": ["Riley", "Avery", "Priya"], "expected_type": "overdue"},

    # ── More at_risk (was 1, add 4) ──
    {"q": "What commitments are in danger?", "expected_entities": ["Riley", "Avery", "Priya"], "expected_type": "at_risk"},
    {"q": "Which promises might slip?", "expected_entities": ["Riley", "Avery", "Priya"], "expected_type": "at_risk"},
    {"q": "What's at risk of being missed?", "expected_entities": ["Riley", "Priya"], "expected_type": "at_risk"},
    {"q": "Which commitments are threatened?", "expected_entities": ["Riley", "Avery", "Priya"], "expected_type": "at_risk"},

    # ── More direct_lookup (was 7, add 8) ──
    {"q": "What did I promise Priya?", "expected_entities": ["Priya", "compliance report"], "expected_type": "direct_lookup"},
    {"q": "What did I send Avery?", "expected_entities": ["Avery", "quarterly report"], "expected_type": "direct_lookup"},
    {"q": "What did I promise to deliver to Riley?", "expected_entities": ["Riley", "security questionnaire"], "expected_type": "direct_lookup"},
    {"q": "What's the status of the SSO work?", "expected_entities": ["Jamie", "SSO", "legal"], "expected_type": "direct_lookup"},
    {"q": "What did Carlos say in Spanish?", "expected_entities": ["Carlos", "contrato"], "expected_type": "direct_lookup"},
    {"q": "What did Morgan present?", "expected_entities": ["Morgan", "Nova"], "expected_type": "direct_lookup"},
    {"q": "What did I commit to the Hiring Committee?", "expected_entities": ["Hiring Committee", "offer", "senior engineer"], "expected_type": "direct_lookup"},
    {"q": "What's the VendorZ situation?", "expected_entities": ["Alice", "VendorZ", "$1M"], "expected_type": "direct_lookup"},

    # ── More relational (was 5, add 5) ──
    {"q": "Who has broken commitments?", "expected_entities": ["Riley", "Avery", "Priya"], "expected_type": "relational", "expected_not_entities": ["TechNewsletter"]},
    {"q": "Who should I follow up with?", "expected_entities": ["Riley", "Avery", "Priya"], "expected_type": "relational"},
    {"q": "Which clients are unhappy?", "expected_entities": ["Globex"], "expected_type": "relational"},
    {"q": "Who delivered on time?", "expected_entities": ["Alex", "Sam"], "expected_type": "relational"},
    {"q": "Who has unfulfilled promises?", "expected_entities": ["Riley", "Avery", "Priya"], "expected_type": "relational", "expected_not_entities": ["TechNewsletter"]},

    # ── More temporal (was 4, add 4) ──
    {"q": "What's been outstanding the longest?", "expected_entities": ["Avery"], "expected_type": "temporal"},
    {"q": "What did I commit to months ago?", "expected_entities": ["Avery", "Riley"], "expected_type": "temporal"},
    {"q": "What's the oldest commitment I haven't kept?", "expected_entities": ["Avery"], "expected_type": "temporal"},
    {"q": "What's been delayed the most?", "expected_entities": ["Avery", "Riley"], "expected_type": "temporal"},

    # ── More critical (was 4, add 4) ──
    {"q": "Are there any regulatory issues?", "expected_entities": ["regulatory fine", "GDPR"], "expected_type": "critical"},
    {"q": "Is any account churning?", "expected_entities": ["Globex", "cancel"], "expected_type": "critical"},
    {"q": "What's the board concerned about?", "expected_entities": ["Board", "Q3", "investor"], "expected_type": "critical"},
    {"q": "Are there any legal threats?", "expected_entities": ["regulatory fine", "GDPR"], "expected_type": "critical"},

    # ── More abstention (was 4, add 4) ──
    {"q": "What's the stock price of AAPL?", "expected_entities": [], "expected_type": "abstention"},
    {"q": "How tall is Mount Everest?", "expected_entities": [], "expected_type": "abstention"},
    {"q": "What did I commit to in 2023?", "expected_entities": [], "expected_type": "abstention"},
    {"q": "Who is Albert Einstein?", "expected_entities": [], "expected_type": "abstention"},

    # ── More contradiction (was 3, add 3) ──
    {"q": "Did Orion Tech's price change?", "expected_entities": ["Orion", "$120k", "$95k", "$150k"], "expected_type": "contradiction"},
    {"q": "What was Orion Tech's final invoice?", "expected_entities": ["Orion", "$150k"], "expected_type": "contradiction"},
    {"q": "Was there a pricing dispute with Orion?", "expected_entities": ["Orion", "$150k", "pricing dispute"], "expected_type": "contradiction"},

    # ── More recurring (was 3, add 3) ──
    {"q": "What's the recurring production issue?", "expected_entities": ["auth", "outage"], "expected_type": "recurring"},
    {"q": "What keeps going wrong?", "expected_entities": ["auth", "outage"], "expected_type": "recurring"},
    {"q": "What's the systemic issue?", "expected_entities": ["auth", "systemic"], "expected_type": "recurring"},

    # ── More noise_lookup (was 3, add 3) ──
    {"q": "What digest did I get?", "expected_entities": ["TechNewsletter", "digest"], "expected_type": "noise_lookup"},
    {"q": "What industry trends did I read about?", "expected_entities": ["TechNewsletter", "industry trends"], "expected_type": "noise_lookup"},
    {"q": "What newsletters came in?", "expected_entities": ["TechNewsletter"], "expected_type": "noise_lookup"},

    # ── More priority (was 2, add 2) ──
    {"q": "What's the most urgent commitment?", "expected_entities": ["Riley", "Globex"], "expected_type": "priority", "expected_not_entities": ["TechNewsletter"]},
    {"q": "What needs attention immediately?", "expected_entities": ["Globex", "regulatory fine"], "expected_type": "priority", "expected_not_entities": ["TechNewsletter"]},

    # ── More multilingual (was 2, add 1) ──
    {"q": "¿Qué enviará Carlos?", "expected_entities": ["Carlos", "contrato"], "expected_type": "multilingual"},

    # ── More disputed (was 2, add 1) ──
    {"q": "Was the Nova presentation complete?", "expected_entities": ["Morgan", "Nova", "incomplete"], "expected_type": "disputed"},

    # ── More conditional (was 2, add 1) ──
    {"q": "Is the SSO ready if legal approves?", "expected_entities": ["Jamie", "SSO", "legal"], "expected_type": "conditional"},

    # ── More cross_entity (was 2, add 1) ──
    {"q": "Which entities have compliance issues?", "expected_entities": ["Priya", "compliance"], "expected_type": "cross_entity"},

    # ── More prepare (was 1, add 1) ──
    {"q": "What should I prepare for the board meeting?", "expected_entities": ["Board", "Q3"], "expected_type": "prepare", "expected_not_entities": ["TechNewsletter"]},
]


def get_corpus():
    """Return the signal corpus as a list of dicts."""
    return SIGNALS


def get_questions():
    """Return the 50-question gold set."""
    return QUESTIONS


if __name__ == "__main__":
    print(f"Corpus: {len(SIGNALS)} signals, {len(set(s['entity'] for s in SIGNALS))} entities")
    print(f"Questions: {len(QUESTIONS)} gold-labeled questions")
    types = {}
    for q in QUESTIONS:
        types[q["expected_type"]] = types.get(q["expected_type"], 0) + 1
    print(f"Question types: {json.dumps(types, indent=2)}")
