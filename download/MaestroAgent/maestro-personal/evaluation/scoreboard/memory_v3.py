"""
Memory gold corpus v3 — ENGINEERING/OPS scenario.

Distinct from memory_v1 (general) and memory_v2 (enterprise sales).
This corpus models an engineering team's operational world: incidents,
deployments, on-call rotations, tech debt, and cross-team dependencies.
Used for the 3rd question set in the 3-set Gate 1 ablation.

Added 2026-07-20 per senior auditor direction #4: 'n=100, 3 distinct
question sets'. The 1st set is memory_v1 (general). The 2nd is memory_v2
(enterprise sales). This is the 3rd (engineering/ops).

Corpus: 7 entities, 26 signals, 90-day window.
"""
import json
from datetime import datetime, timezone, timedelta


def _days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


SIGNALS_V3 = [
    # ── Auth Service — recurring incidents ──
    {"entity": "Auth Service", "text": "Production down — auth service sev1 incident",
     "signal_type": "alert", "timestamp": _days_ago(30)},
    {"entity": "Auth Service", "text": "Auth service outage again — same root cause as last week",
     "signal_type": "alert", "timestamp": _days_ago(15)},
    {"entity": "Auth Service", "text": "Third auth service outage this month — systemic issue",
     "signal_type": "alert", "timestamp": _days_ago(2)},

    # ── Payment API — broken deployment ──
    {"entity": "Payment API", "text": "I will deploy the payment API fix by Friday",
     "signal_type": "commitment_made", "timestamp": _days_ago(20)},
    {"entity": "Payment API", "text": "Payment API deployment failed — rolled back",
     "signal_type": "reported_statement", "timestamp": _days_ago(18)},
    {"entity": "Payment API", "text": "Never deployed the payment API fix — still broken",
     "signal_type": "reported_statement", "timestamp": _days_ago(5)},

    # ── Database Migration — completed ──
    {"entity": "Database Migration", "text": "I will complete the DB migration by end of sprint",
     "signal_type": "commitment_made", "timestamp": _days_ago(25)},
    {"entity": "Database Migration", "text": "DB migration completed successfully — zero downtime",
     "signal_type": "reported_statement", "timestamp": _days_ago(10)},

    # ── Search Service — performance regression ──
    {"entity": "Search Service", "text": "Search service latency increased from 50ms to 800ms — regression",
     "signal_type": "alert", "timestamp": _days_ago(12)},
    {"entity": "Search Service", "text": "I will investigate the search service latency by Monday",
     "signal_type": "commitment_made", "timestamp": _days_ago(11)},
    {"entity": "Search Service", "text": "Search service latency still high — never investigated",
     "signal_type": "reported_statement", "timestamp": _days_ago(3)},

    # ── Mobile App — release follow-through ──
    {"entity": "Mobile App", "text": "I will ship the mobile app release by Wednesday",
     "signal_type": "commitment_made", "timestamp": _days_ago(14)},
    {"entity": "Mobile App", "text": "Shipped the mobile app release on time — v2.3.0 live",
     "signal_type": "reported_statement", "timestamp": _days_ago(12)},

    # ── API Gateway — contradiction on capacity ──
    {"entity": "API Gateway", "text": "API Gateway handles 10k requests per second — confirmed in load test",
     "signal_type": "reported_statement", "timestamp": _days_ago(40)},
    {"entity": "API Gateway", "text": "API Gateway maxes out at 4k requests per second — production limit",
     "signal_type": "reported_statement", "timestamp": _days_ago(8)},

    # ── Engineering Team — velocity / standup ──
    {"entity": "Engineering Team", "text": "Sprint velocity is 45 points — on track",
     "signal_type": "reported_statement", "timestamp": _days_ago(7)},
    {"entity": "Engineering Team", "text": "Sprint velocity dropped to 28 points — behind this sprint",
     "signal_type": "reported_statement", "timestamp": _days_ago(2)},

    # ── Security Audit — compliance commitment ──
    {"entity": "Security Audit", "text": "I will complete the SOC2 audit by end of quarter",
     "signal_type": "commitment_made", "timestamp": _days_ago(60)},
    {"entity": "Security Audit", "text": "SOC2 audit overdue — hasn't been started",
     "signal_type": "reported_statement", "timestamp": _days_ago(5)},

    # ── Tech Debt — acknowledged but deferred ──
    {"entity": "Tech Debt", "text": "Tech debt in the checkout flow — needs refactoring",
     "signal_type": "reported_statement", "timestamp": _days_ago(50)},
    {"entity": "Tech Debt", "text": "Tech debt in the checkout flow still unaddressed — 50 days old",
     "signal_type": "reported_statement", "timestamp": _days_ago(10)},

    # ── On-call rotation ──
    {"entity": "On-call", "text": "I will be on-call this week — covering the auth service",
     "signal_type": "commitment_made", "timestamp": _days_ago(9)},
    {"entity": "On-call", "text": "On-call rotation — 3 pages this week, all auth-related",
     "signal_type": "reported_statement", "timestamp": _days_ago(1)},

    # ── Noise (engineering newsletters) ──
    {"entity": "EngNewsletter", "text": "Weekly engineering digest: 8 articles about microservices",
     "signal_type": "newsletter", "timestamp": _days_ago(6)},
    {"entity": "EngNewsletter", "text": "Industry blog: Kubernetes best practices 2026",
     "signal_type": "newsletter", "timestamp": _days_ago(11)},

    # ── Customer-facing bug ──
    {"entity": "Bug Report", "text": "Customer reported login fails on Safari — sev2",
     "signal_type": "alert", "timestamp": _days_ago(4)},
    {"entity": "Bug Report", "text": "Login Safari bug still open — 4 days no fix",
     "signal_type": "alert", "timestamp": _days_ago(1)},
]


QUESTIONS_V3 = [
    # ── direct_lookup (7) ──
    {"q": "What's the auth service status?", "expected_entities": ["Auth Service", "outage"], "expected_type": "direct_lookup"},
    {"q": "What did I promise for the payment API?", "expected_entities": ["Payment API", "deploy", "fix"], "expected_type": "direct_lookup"},
    {"q": "What happened with the DB migration?", "expected_entities": ["Database Migration", "completed"], "expected_type": "direct_lookup"},
    {"q": "What's the search service issue?", "expected_entities": ["Search Service", "latency"], "expected_type": "direct_lookup"},
    {"q": "Did I ship the mobile app?", "expected_entities": ["Mobile App", "release"], "expected_type": "direct_lookup"},
    {"q": "What's the API Gateway capacity?", "expected_entities": ["API Gateway"], "expected_type": "direct_lookup"},
    {"q": "What's the SOC2 audit status?", "expected_entities": ["Security Audit", "SOC2"], "expected_type": "direct_lookup"},

    # ── broken (3) ──
    {"q": "What did I fail to deliver?", "expected_entities": ["Payment API", "Search Service"], "expected_type": "broken"},
    {"q": "Which commitments are broken?", "expected_entities": ["Payment API", "Search Service", "Security Audit"], "expected_type": "broken"},
    {"q": "What did I not deploy?", "expected_entities": ["Payment API"], "expected_type": "broken"},

    # ── overdue (3) ──
    {"q": "Which promises are now overdue?", "expected_entities": ["Security Audit", "Payment API"], "expected_type": "overdue"},
    {"q": "What's past due?", "expected_entities": ["Security Audit"], "expected_type": "overdue"},
    {"q": "What am I late on?", "expected_entities": ["Security Audit", "Search Service"], "expected_type": "overdue"},

    # ── at_risk (2) ──
    {"q": "Which commitments are at risk?", "expected_entities": ["Payment API", "Search Service"], "expected_type": "at_risk"},
    {"q": "What might slip?", "expected_entities": ["Search Service"], "expected_type": "at_risk"},

    # ── relational (4) ──
    {"q": "Who am I disappointing?", "expected_entities": ["Payment API", "Search Service"], "expected_type": "relational", "expected_not_entities": ["EngNewsletter"]},
    {"q": "Which services are failing?", "expected_entities": ["Auth Service", "Payment API", "Search Service"], "expected_type": "relational"},
    {"q": "Which services are healthy?", "expected_entities": ["Database Migration", "Mobile App"], "expected_type": "relational"},
    {"q": "Who has broken commitments?", "expected_entities": ["Payment API", "Search Service"], "expected_type": "relational", "expected_not_entities": ["EngNewsletter"]},

    # ── contradiction (3) ──
    {"q": "Did the API Gateway capacity change?", "expected_entities": ["API Gateway", "10k", "4k"], "expected_type": "contradiction"},
    {"q": "What was the API Gateway discrepancy?", "expected_entities": ["API Gateway", "10k", "4k"], "expected_type": "contradiction"},
    {"q": "Did anyone change their numbers?", "expected_entities": ["API Gateway"], "expected_type": "contradiction"},

    # ── recurring (3) ──
    {"q": "What keeps recurring?", "expected_entities": ["Auth Service", "outage"], "expected_type": "recurring"},
    {"q": "Which issue keeps happening?", "expected_entities": ["Auth Service"], "expected_type": "recurring"},
    {"q": "What's the systemic issue?", "expected_entities": ["Auth Service", "systemic"], "expected_type": "recurring"},

    # ── critical (4) ──
    {"q": "Are there any sev1 incidents?", "expected_entities": ["Auth Service", "sev1"], "expected_type": "critical"},
    {"q": "Is production down?", "expected_entities": ["Auth Service", "Production"], "expected_type": "critical"},
    {"q": "What's the most urgent incident?", "expected_entities": ["Auth Service", "Bug Report"], "expected_type": "critical", "expected_not_entities": ["EngNewsletter"]},
    {"q": "Any sev2 bugs open?", "expected_entities": ["Bug Report", "sev2", "Safari"], "expected_type": "critical"},

    # ── temporal (3) ──
    {"q": "What's been pending the longest?", "expected_entities": ["Security Audit", "Tech Debt"], "expected_type": "temporal"},
    {"q": "What's the oldest unaddressed issue?", "expected_entities": ["Tech Debt", "Security Audit"], "expected_type": "temporal"},
    {"q": "What's been delayed the most?", "expected_entities": ["Security Audit"], "expected_type": "temporal"},

    # ── priority (2) ──
    {"q": "What's the most urgent thing?", "expected_entities": ["Auth Service", "Bug Report"], "expected_type": "priority", "expected_not_entities": ["EngNewsletter"]},
    {"q": "What needs my attention?", "expected_entities": ["Auth Service", "Payment API"], "expected_type": "priority", "expected_not_entities": ["EngNewsletter"]},

    # ── noise_lookup (2) ──
    {"q": "What newsletters did I get?", "expected_entities": ["EngNewsletter"], "expected_type": "noise_lookup"},
    {"q": "What industry blogs came in?", "expected_entities": ["EngNewsletter", "Kubernetes"], "expected_type": "noise_lookup"},

    # ── abstention (3) ──
    {"q": "What's the weather?", "expected_entities": [], "expected_type": "abstention"},
    {"q": "Who won the World Cup?", "expected_entities": [], "expected_type": "abstention"},
    {"q": "What's the stock price?", "expected_entities": [], "expected_type": "abstention"},

    # ── cross_entity (2) ──
    {"q": "Which services have outages?", "expected_entities": ["Auth Service"], "expected_type": "cross_entity"},
    {"q": "Which services have latency issues?", "expected_entities": ["Search Service"], "expected_type": "cross_entity"},
]


def get_corpus_v3():
    """Return the engineering/ops signal corpus."""
    return SIGNALS_V3


def get_questions_v3():
    """Return the engineering/ops question set (41 questions)."""
    return QUESTIONS_V3


if __name__ == "__main__":
    print(f"Corpus v3: {len(SIGNALS_V3)} signals, {len(set(s['entity'] for s in SIGNALS_V3))} entities")
    print(f"Questions v3: {len(QUESTIONS_V3)} gold-labeled questions")
    types = {}
    for q in QUESTIONS_V3:
        types[q["expected_type"]] = types.get(q["expected_type"], 0) + 1
    print(f"Question types: {json.dumps(types, indent=2)}")
