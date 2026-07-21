"""
Memory gold corpus v2 — ENTERPRISE SALES scenario.

Distinct from memory_v1 (general mixed corpus). This corpus models an
enterprise software sales cycle: 6 prospects/customers at different
stages, with commitments, follow-ups, contract negotiations, and a
churn risk. Used for the 2nd question set in the 3-set Gate 1 ablation.

Added 2026-07-20 per senior auditor direction #4: 'n=100, 3 distinct
question sets'. The 1st set is memory_v1 (general). This is the 2nd
(enterprise sales). memory_v3 will be the 3rd (engineering/ops).

Corpus: 6 entities, 24 signals, 90-day window.
"""
import json
from datetime import datetime, timezone, timedelta


def _days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


SIGNALS_V2 = [
    # ── Acme Industries — closed won, onboarding ──
    {"entity": "Acme Industries", "text": "I will send Acme the onboarding plan by Monday",
     "signal_type": "commitment_made", "timestamp": _days_ago(40)},
    {"entity": "Acme Industries", "text": "Sent Acme the onboarding plan on Tuesday",
     "signal_type": "reported_statement", "timestamp": _days_ago(38)},
    {"entity": "Acme Industries", "text": "Acme signed the contract — $250k annual",
     "signal_type": "reported_statement", "timestamp": _days_ago(30)},
    {"entity": "Acme Industries", "text": "Acme onboarding complete — go-live scheduled for next month",
     "signal_type": "reported_statement", "timestamp": _days_ago(5)},

    # ── Beta Corp — negotiation, pricing dispute ──
    {"entity": "Beta Corp", "text": "I will send Beta the revised pricing by Friday",
     "signal_type": "commitment_made", "timestamp": _days_ago(25)},
    {"entity": "Beta Corp", "text": "Beta Corp originally quoted $180k for the enterprise tier",
     "signal_type": "reported_statement", "timestamp": _days_ago(22)},
    {"entity": "Beta Corp", "text": "Beta Corp pushed back — wants $145k instead",
     "signal_type": "reported_statement", "timestamp": _days_ago(15)},
    {"entity": "Beta Corp", "text": "Never sent the revised pricing to Beta — deal stalled",
     "signal_type": "reported_statement", "timestamp": _days_ago(3)},

    # ── Gamma LLC — churn risk ──
    {"entity": "Gamma LLC", "text": "Gamma LLC is threatening to cancel — unhappy with support response times",
     "signal_type": "alert", "timestamp": _days_ago(7)},
    {"entity": "Gamma LLC", "text": "I will schedule a call with Gamma's CTO this week",
     "signal_type": "commitment_made", "timestamp": _days_ago(6)},
    {"entity": "Gamma LLC", "text": "Gamma LLC sent a formal cancellation notice — 30 day notice period",
     "signal_type": "alert", "timestamp": _days_ago(2)},

    # ── Delta Systems — expansion opportunity ──
    {"entity": "Delta Systems", "text": "Delta wants to add 50 more seats — expansion opportunity",
     "signal_type": "reported_statement", "timestamp": _days_ago(20)},
    {"entity": "Delta Systems", "text": "I will send Delta the expansion quote by end of week",
     "signal_type": "commitment_made", "timestamp": _days_ago(18)},
    {"entity": "Delta Systems", "text": "Sent Delta the expansion quote — $85k for 50 seats",
     "signal_type": "reported_statement", "timestamp": _days_ago(14)},
    {"entity": "Delta Systems", "text": "Delta accepted the expansion quote — PO incoming",
     "signal_type": "reported_statement", "timestamp": _days_ago(1)},

    # ── Epsilon Inc — broken commitment ──
    {"entity": "Epsilon Inc", "text": "I will deliver the POC environment to Epsilon by Wednesday",
     "signal_type": "commitment_made", "timestamp": _days_ago(28)},
    {"entity": "Epsilon Inc", "text": "Never delivered the POC to Epsilon — they're frustrated",
     "signal_type": "reported_statement", "timestamp": _days_ago(10)},

    # ── Zeta Group — recurring issue ──
    {"entity": "Zeta Group", "text": "Zeta Group reported a bug in the reporting module",
     "signal_type": "reported_statement", "timestamp": _days_ago(35)},
    {"entity": "Zeta Group", "text": "Zeta Group reported the same reporting bug again — recurrence",
     "signal_type": "reported_statement", "timestamp": _days_ago(20)},
    {"entity": "Zeta Group", "text": "Zeta Group reported the reporting bug a third time — systemic",
     "signal_type": "reported_statement", "timestamp": _days_ago(5)},

    # ── Omega Partners — completed follow-through ──
    {"entity": "Omega Partners", "text": "I will send Omega the case study by end of month",
     "signal_type": "commitment_made", "timestamp": _days_ago(45)},
    {"entity": "Omega Partners", "text": "Sent Omega the case study on time",
     "signal_type": "reported_statement", "timestamp": _days_ago(33)},

    # ── Noise (newsletter/industry) ──
    {"entity": "SalesNewsletter", "text": "Weekly sales digest: 5 articles about closing techniques",
     "signal_type": "newsletter", "timestamp": _days_ago(8)},
    {"entity": "SalesNewsletter", "text": "Industry report: SaaS churn benchmarks 2026",
     "signal_type": "newsletter", "timestamp": _days_ago(12)},
]


QUESTIONS_V2 = [
    # ── direct_lookup (7) ──
    {"q": "What did I promise Acme?", "expected_entities": ["Acme", "onboarding plan"], "expected_type": "direct_lookup"},
    {"q": "What's the status of Beta Corp?", "expected_entities": ["Beta", "pricing"], "expected_type": "direct_lookup"},
    {"q": "What did I send Delta?", "expected_entities": ["Delta", "expansion quote"], "expected_type": "direct_lookup"},
    {"q": "What's the Gamma situation?", "expected_entities": ["Gamma", "cancel"], "expected_type": "direct_lookup"},
    {"q": "What did I promise Epsilon?", "expected_entities": ["Epsilon", "POC"], "expected_type": "direct_lookup"},
    {"q": "What's the Zeta issue?", "expected_entities": ["Zeta", "reporting bug"], "expected_type": "direct_lookup"},
    {"q": "Did I send the case study to Omega?", "expected_entities": ["Omega", "case study"], "expected_type": "direct_lookup"},

    # ── broken (3) ──
    {"q": "What did I fail to deliver?", "expected_entities": ["Beta", "pricing", "Epsilon", "POC"], "expected_type": "broken"},
    {"q": "Which commitments are broken?", "expected_entities": ["Beta", "Epsilon"], "expected_type": "broken"},
    {"q": "What did I not send?", "expected_entities": ["Beta", "pricing"], "expected_type": "broken"},

    # ── overdue (3) ──
    {"q": "Which promises are now overdue?", "expected_entities": ["Beta", "Epsilon"], "expected_type": "overdue"},
    {"q": "What's past due?", "expected_entities": ["Beta", "Epsilon"], "expected_type": "overdue"},
    {"q": "What am I late on?", "expected_entities": ["Beta"], "expected_type": "overdue"},

    # ── at_risk (2) ──
    {"q": "Which commitments are at risk?", "expected_entities": ["Beta", "Epsilon"], "expected_type": "at_risk"},
    {"q": "Which deals might slip?", "expected_entities": ["Beta"], "expected_type": "at_risk"},

    # ── relational (4) ──
    {"q": "Who am I disappointing?", "expected_entities": ["Beta", "Epsilon", "Gamma"], "expected_type": "relational", "expected_not_entities": ["SalesNewsletter"]},
    {"q": "Which customers are unhappy?", "expected_entities": ["Gamma", "Epsilon"], "expected_type": "relational"},
    {"q": "Who keeps their promises?", "expected_entities": ["Acme", "Delta", "Omega"], "expected_type": "relational"},
    {"q": "Who has broken commitments?", "expected_entities": ["Beta", "Epsilon"], "expected_type": "relational", "expected_not_entities": ["SalesNewsletter"]},

    # ── contradiction (3) ──
    {"q": "Did Beta Corp change their price?", "expected_entities": ["Beta", "$180k", "$145k"], "expected_type": "contradiction"},
    {"q": "What was the Beta pricing dispute?", "expected_entities": ["Beta", "$180k", "$145k"], "expected_type": "contradiction"},
    {"q": "Did anyone change their mind?", "expected_entities": ["Beta"], "expected_type": "contradiction"},

    # ── recurring (2) ──
    {"q": "What keeps recurring?", "expected_entities": ["Zeta", "reporting bug"], "expected_type": "recurring"},
    {"q": "Which issue keeps happening?", "expected_entities": ["Zeta", "reporting bug"], "expected_type": "recurring"},

    # ── critical (4) ──
    {"q": "Is any customer churning?", "expected_entities": ["Gamma", "cancel"], "expected_type": "critical"},
    {"q": "Are there any cancellation notices?", "expected_entities": ["Gamma", "cancellation"], "expected_type": "critical"},
    {"q": "What's the most urgent deal?", "expected_entities": ["Gamma", "Beta"], "expected_type": "critical", "expected_not_entities": ["SalesNewsletter"]},
    {"q": "Any at-risk accounts?", "expected_entities": ["Gamma"], "expected_type": "critical"},

    # ── temporal (2) ──
    {"q": "What's been pending the longest?", "expected_entities": ["Beta"], "expected_type": "temporal"},
    {"q": "What's the oldest unresolved commitment?", "expected_entities": ["Beta", "Epsilon"], "expected_type": "temporal"},

    # ── priority (2) ──
    {"q": "What's the most urgent commitment?", "expected_entities": ["Gamma", "Beta"], "expected_type": "priority", "expected_not_entities": ["SalesNewsletter"]},
    {"q": "What needs my attention?", "expected_entities": ["Gamma", "Beta"], "expected_type": "priority", "expected_not_entities": ["SalesNewsletter"]},

    # ── noise_lookup (2) ──
    {"q": "What newsletters did I get?", "expected_entities": ["SalesNewsletter"], "expected_type": "noise_lookup"},
    {"q": "What industry reports came in?", "expected_entities": ["SalesNewsletter", "churn benchmarks"], "expected_type": "noise_lookup"},

    # ── abstention (3) ──
    {"q": "What's the weather?", "expected_entities": [], "expected_type": "abstention"},
    {"q": "Who is the CEO of Apple?", "expected_entities": [], "expected_type": "abstention"},
    {"q": "What did I commit to in 2022?", "expected_entities": [], "expected_type": "abstention"},

    # ── cross_entity (2) ──
    {"q": "Which customers have pricing issues?", "expected_entities": ["Beta"], "expected_type": "cross_entity"},
    {"q": "Which accounts are expansion targets?", "expected_entities": ["Delta"], "expected_type": "cross_entity"},
]


def get_corpus_v2():
    """Return the enterprise-sales signal corpus."""
    return SIGNALS_V2


def get_questions_v2():
    """Return the enterprise-sales question set (40 questions)."""
    return QUESTIONS_V2


if __name__ == "__main__":
    print(f"Corpus v2: {len(SIGNALS_V2)} signals, {len(set(s['entity'] for s in SIGNALS_V2))} entities")
    print(f"Questions v2: {len(QUESTIONS_V2)} gold-labeled questions")
    types = {}
    for q in QUESTIONS_V2:
        types[q["expected_type"]] = types.get(q["expected_type"], 0) + 1
    print(f"Question types: {json.dumps(types, indent=2)}")
