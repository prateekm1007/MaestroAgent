"""
Maestro Cognitive Council — Gate 0: The 10 World Model Benchmark Stories.

Each story is a longitudinal organizational scenario (30-90 simulated days)
with expected situation states at each checkpoint.

The 10 failure shapes:
  1. Customer commitment drift (CustomerA renewal)
  2. Security prerequisite failure (OAuth conditional approval)
  3. Pricing exception leakage (enterprise discount precedent)
  4. Hiring-plan assumption collapse (budget cut mid-quarter)
  5. Product launch scope mutation (feature creep)
  6. Duplicate work across teams (two teams building same API)
  7. Expert bottleneck emergence (single point of failure)
  8. Legal interpretation disagreement (contract ambiguity)
  9. Incident pattern that's coincidence (false pattern)
  10. Previously learned pattern becoming false after reorg (falsification)

Reference: docs/MAESTRO_COGNITIVE_COUNCIL_AUDIT_AND_WIRING_PLAN.md
"""

from __future__ import annotations

from .benchmark_types import BenchmarkStory, BenchmarkSignal, CheckpointExpectation


# ════════════════════════════════════════════════════════════════════════════
# Story 1: Customer Commitment Drift (CustomerA Renewal)
# ════════════════════════════════════════════════════════════════════════════

STORY_1_GLOBEX_DRIFT = BenchmarkStory(
    story_id="story-01-globex-drift",
    title="Customer commitment drift — CustomerA renewal",
    failure_shape="commitment_drift",
    description=(
        "CustomerA renewal. Internal commitment to deliver SSO by Friday. "
        "Security approval is conditional. Internal team claims work is "
        "complete, but customer defines availability as production access. "
        "Renewal meeting approaches. Tests: commitment drift, expectation "
        "mismatch, preparation activation."
    ),
    total_days=59,
    signals=[
        BenchmarkSignal(day=12, signal_type="customer.commitment_made",
                        entity="CustomerA", text="Deliver SSO integration by Friday"),
        BenchmarkSignal(day=40, signal_type="security.condition",
                        entity="CustomerA", text="Security approval required for SSO — conditional on audit"),
        BenchmarkSignal(day=50, signal_type="reported_statement",
                        entity="CustomerA", text="SSO implementation reported complete"),
        BenchmarkSignal(day=55, signal_type="reported_statement",
                        entity="CustomerA", text="Customer defines availability as production access, not just implementation"),
        BenchmarkSignal(day=59, signal_type="calendar.meeting",
                        entity="CustomerA", text="CustomerA renewal meeting scheduled for tomorrow"),
    ],
    checkpoints=[
        CheckpointExpectation(
            day=12,
            description="Commitment made — situation detected",
            expected_epistemic_state="insufficient",
            expected_operational_state="observing",
            expected_unknowns=["Was the commitment to CustomerA fulfilled?"],
        ),
        CheckpointExpectation(
            day=40,
            description="Security prerequisite threatens commitment",
            expected_epistemic_state="contested",
            expected_operational_state="observing",
            expected_unknowns=[
                "Was the commitment to CustomerA fulfilled?",
                "Was the security condition for CustomerA cleared?",
            ],
            expected_belief="Commitment feasibility is threatened by unresolved security prerequisite",
        ),
        CheckpointExpectation(
            day=50,
            description="Completion claim — but doesn't resolve prereq",
            expected_epistemic_state="contested",
            expected_operational_state="observing",
            expected_unknowns=[
                "Did security approval clear before the completion claim?",
            ],
            expected_whisper_silent=True,
        ),
        CheckpointExpectation(
            day=55,
            description="Customer expectation mismatch — needs preparation",
            expected_operational_state="decision_pending",
            expected_prepare_activates=True,
            expected_can_decide=["Proceed with general direction"],
            expected_cannot_decide=["Commit to specific delivery date"],
        ),
        CheckpointExpectation(
            day=59,
            description="Renewal meeting tomorrow — prepare",
            expected_operational_state="decision_pending",
            expected_delivery_state="prepare_eligible",
            expected_prepare_activates=True,
        ),
    ],
    forbidden_future_leakage=["Initech", "Hooli"],
)


# ════════════════════════════════════════════════════════════════════════════
# Story 2: Security Prerequisite Failure (OAuth Conditional Approval)
# ════════════════════════════════════════════════════════════════════════════

STORY_2_OAUTH_SECURITY = BenchmarkStory(
    story_id="story-02-oauth-security",
    title="Security prerequisite failure — OAuth standardization",
    failure_shape="security_prerequisite_failure",
    description=(
        "CEO asks: Should we standardize OAuth across all products? "
        "Engineering wants phased migration. Security wants speed. "
        "Legal identifies enterprise contract compatibility risk. "
        "Sales flags renewal window conflict. Tests: consequence-path "
        "routing, disagreement preservation, decision boundary."
    ),
    total_days=45,
    signals=[
        BenchmarkSignal(day=5, signal_type="decision.proposed",
                        entity="Internal", text="Should we standardize OAuth across all products?"),
        BenchmarkSignal(day=10, signal_type="engineering.concern",
                        entity="Internal", text="Migration cost is high — phased approach needed"),
        BenchmarkSignal(day=15, signal_type="security.concern",
                        entity="Internal", text="Inconsistent token policies create audit exposure — delay increases risk"),
        BenchmarkSignal(day=20, signal_type="legal.concern",
                        entity="Internal", text="Three enterprise contracts mention SSO obligations — legacy compatibility may be required"),
        BenchmarkSignal(day=25, signal_type="sales.concern",
                        entity="Internal", text="Two enterprise renewals occur during proposed migration window"),
        BenchmarkSignal(day=35, signal_type="reported_statement",
                        entity="Internal", text="Customer Success: OAuth changes are customer-visible and may cause login disruptions"),
    ],
    checkpoints=[
        CheckpointExpectation(
            day=5,
            description="OAuth question raised",
            expected_epistemic_state="insufficient",
            expected_operational_state="observing",
        ),
        CheckpointExpectation(
            day=20,
            description="Multiple perspectives — disagreement emerges",
            expected_epistemic_state="contested",
            expected_disputes=1,
            expected_can_decide=["Adopt the general direction"],
            expected_cannot_decide=["Determine the specific sequence or timing"],
        ),
        CheckpointExpectation(
            day=35,
            description="Full consequence-path routing — 6 specialists",
            expected_epistemic_state="contested",
            expected_disputes=1,
            expected_can_decide=["Adopt OAuth standardization as architectural direction"],
            expected_cannot_decide=["Migration sequence for enterprise-facing services"],
            expected_belief="OAuth is directionally sound but simultaneous migration creates delivery risk",
        ),
    ],
    forbidden_future_leakage=["CustomerA", "Initech"],
)


# ════════════════════════════════════════════════════════════════════════════
# Story 3: Pricing Exception Leakage (Enterprise Discount Precedent)
# ════════════════════════════════════════════════════════════════════════════

STORY_3_PRICING_LEAK = BenchmarkStory(
    story_id="story-03-pricing-leak",
    title="Pricing exception leakage — enterprise discount precedent",
    failure_shape="pricing_exception_leakage",
    description=(
        "Sales gives Acme a 30% discount to close a deal. Two weeks later, "
        "BetaCo asks for the same discount. The pricing exception has "
        "leaked into a precedent. Tests: pattern detection, precedent "
        "contamination, learning closure."
    ),
    total_days=60,
    signals=[
        BenchmarkSignal(day=5, signal_type="pricing.exception",
                        entity="Acme", text="Sales gave Acme 30% discount to close the deal"),
        BenchmarkSignal(day=20, signal_type="customer.objection",
                        entity="BetaCo", text="BetaCo requests 30% discount — references Acme deal"),
        BenchmarkSignal(day=35, signal_type="customer.objection",
                        entity="GammaCorp", text="GammaCorp requests 30% discount — references Acme deal"),
        BenchmarkSignal(day=50, signal_type="outcome.negative",
                        entity="GammaCorp", text="GammaCorp churned — refused to pay full price after Acme precedent"),
    ],
    checkpoints=[
        CheckpointExpectation(
            day=5,
            description="Pricing exception made — no pattern yet",
            expected_epistemic_state="insufficient",
            expected_learning_state="none",
        ),
        CheckpointExpectation(
            day=20,
            description="Second request — pattern emerging",
            expected_epistemic_state="preliminary",
            expected_learning_state="hypothesis_created",
            expected_belief="Pricing exceptions may be leaking into precedents",
        ),
        CheckpointExpectation(
            day=35,
            description="Third request — pattern strengthening",
            expected_learning_state="prospectively_testing",
        ),
        CheckpointExpectation(
            day=50,
            description="Churn outcome — pattern confirmed",
            expected_learning_state="learning_updated",
            expected_learning_effect="belief_strengthened",
            expected_belief="Pricing exceptions leak into precedents and cause churn",
        ),
    ],
    forbidden_future_leakage=["CustomerA", "Internal"],
)


# ════════════════════════════════════════════════════════════════════════════
# Story 4: Hiring-Plan Assumption Collapse (Budget Cut Mid-Quarter)
# ════════════════════════════════════════════════════════════════════════════

STORY_4_HIRING_COLLAPSE = BenchmarkStory(
    story_id="story-04-hiring-collapse",
    title="Hiring-plan assumption collapse — budget cut mid-quarter",
    failure_shape="assumption_collapse",
    description=(
        "Engineering plans to hire 5 engineers based on Q3 budget assumption. "
        "Mid-quarter, finance announces a budget cut. The hiring plan depended "
        "on an assumption that is now falsified. Tests: assumption tracking, "
        "belief weakening, decision invalidation."
    ),
    total_days=75,
    signals=[
        BenchmarkSignal(day=1, signal_type="hiring.plan",
                        entity="Internal", text="Engineering plans to hire 5 engineers in Q3"),
        BenchmarkSignal(day=10, signal_type="assumption.made",
                        entity="Internal", text="Hiring plan assumes Q3 budget of $2M"),
        BenchmarkSignal(day=30, signal_type="commitment.made",
                        entity="Internal", text="Engineering commits to delivery roadmap assuming 5 new hires"),
        BenchmarkSignal(day=45, signal_type="finance.budget_cut",
                        entity="Internal", text="Finance announces Q3 budget cut — hiring reduced to 2 engineers"),
        BenchmarkSignal(day=60, signal_type="outcome.negative",
                        entity="Internal", text="Delivery roadmap slipped — insufficient engineering capacity"),
    ],
    checkpoints=[
        CheckpointExpectation(
            day=10,
            description="Hiring plan based on budget assumption",
            expected_epistemic_state="supported",
            expected_unknowns=["Will Q3 budget be approved at $2M?"],
        ),
        CheckpointExpectation(
            day=45,
            description="Budget cut — assumption falsified",
            expected_epistemic_state="contested",
            expected_unknowns_resolved=["Will Q3 budget be approved at $2M?"],
            expected_cannot_decide=["Commit to original delivery roadmap"],
            expected_belief="Delivery roadmap is at risk — hiring assumption is falsified",
        ),
        CheckpointExpectation(
            day=60,
            description="Roadmap slips — learning confirmed",
            expected_learning_state="learning_updated",
            expected_learning_effect="belief_strengthened",
            expected_belief="Hiring plans that depend on budget assumptions are fragile",
        ),
    ],
    forbidden_future_leakage=["CustomerA", "Acme"],
)


# ════════════════════════════════════════════════════════════════════════════
# Story 5: Product Launch Scope Mutation (Feature Creep)
# ════════════════════════════════════════════════════════════════════════════

STORY_5_SCOPE_MUTATION = BenchmarkStory(
    story_id="story-05-scope-mutation",
    title="Product launch scope mutation — feature creep",
    failure_shape="scope_mutation",
    description=(
        "Product launches with defined scope. Over 60 days, 4 features are "
        "added without timeline adjustment. The scope has mutated but the "
        "deadline hasn't. Tests: scope tracking, timeline coherence, "
        "commitment contradiction."
    ),
    total_days=60,
    signals=[
        BenchmarkSignal(day=1, signal_type="product.launch_plan",
                        entity="Internal", text="Product launch planned for Day 60 with 3 core features"),
        BenchmarkSignal(day=15, signal_type="scope.expansion",
                        entity="Internal", text="Feature 4 added to launch scope by Sales request"),
        BenchmarkSignal(day=25, signal_type="scope.expansion",
                        entity="Internal", text="Feature 5 added to launch scope by Customer Success request"),
        BenchmarkSignal(day=35, signal_type="scope.expansion",
                        entity="Internal", text="Feature 6 added to launch scope by Executive request"),
        BenchmarkSignal(day=45, signal_type="scope.expansion",
                        entity="Internal", text="Feature 7 added to launch scope by Marketing request"),
        BenchmarkSignal(day=55, signal_type="engineering.warning",
                        entity="Internal", text="Engineering: cannot deliver 7 features by Day 60 with current capacity"),
    ],
    checkpoints=[
        CheckpointExpectation(
            day=1,
            description="Launch plan defined — 3 features, Day 60",
            expected_epistemic_state="supported",
        ),
        CheckpointExpectation(
            day=35,
            description="3 scope expansions — timeline unchanged",
            expected_epistemic_state="contested",
            expected_disputes=1,
            expected_belief="Launch scope has mutated but timeline hasn't adjusted",
        ),
        CheckpointExpectation(
            day=55,
            description="Engineering flags — launch at risk",
            expected_operational_state="decision_pending",
            expected_prepare_activates=True,
            expected_can_decide=["Reduce scope to original 3 features"],
            expected_cannot_decide=["Deliver all 7 features by Day 60"],
        ),
    ],
    forbidden_future_leakage=["CustomerA", "Acme"],
)


# ════════════════════════════════════════════════════════════════════════════
# Story 6: Duplicate Work Across Teams (Two Teams Building Same API)
# ════════════════════════════════════════════════════════════════════════════

STORY_6_DUPLICATE_WORK = BenchmarkStory(
    story_id="story-06-duplicate-work",
    title="Duplicate work across teams — two teams building same API",
    failure_shape="duplicate_work",
    description=(
        "Team A and Team B independently build the same authentication API. "
        "Neither knows about the other. Maestro should detect the duplicate "
        "work pattern. Tests: duplicate detection, cross-team coherence, "
        "waste identification."
    ),
    total_days=50,
    signals=[
        BenchmarkSignal(day=5, signal_type="engineering.work_started",
                        entity="TeamA", text="Team A begins building authentication API"),
        BenchmarkSignal(day=10, signal_type="engineering.work_started",
                        entity="TeamB", text="Team B begins building authentication API"),
        BenchmarkSignal(day=25, signal_type="engineering.commitment",
                        entity="TeamA", text="Team A commits to shipping auth API by Day 45"),
        BenchmarkSignal(day=30, signal_type="engineering.commitment",
                        entity="TeamB", text="Team B commits to shipping auth API by Day 50"),
        BenchmarkSignal(day=40, signal_type="duplicate.detected",
                        entity="Internal", text="Maestro detects: Team A and Team B building the same auth API"),
    ],
    checkpoints=[
        CheckpointExpectation(
            day=25,
            description="Both teams committed — duplicate not yet detected",
            expected_epistemic_state="insufficient",
        ),
        CheckpointExpectation(
            day=40,
            description="Duplicate detected — intervention needed",
            expected_epistemic_state="supported",
            expected_delivery_state="prepare_eligible",
            expected_prepare_activates=True,
            expected_belief="Two teams are building the same API — duplicate work detected",
        ),
    ],
    forbidden_future_leakage=["CustomerA", "Acme"],
)


# ════════════════════════════════════════════════════════════════════════════
# Story 7: Expert Bottleneck Emergence (Single Point of Failure)
# ════════════════════════════════════════════════════════════════════════════

STORY_7_EXPERT_BOTTLENECK = BenchmarkStory(
    story_id="story-07-expert-bottleneck",
    title="Expert bottleneck emergence — single point of failure",
    failure_shape="expert_bottleneck",
    description=(
        "Priya is the only engineer who understands the billing system. "
        "Over 70 days, every billing-related question goes to her. She "
        "becomes a single point of failure. Tests: bottleneck detection, "
        "knowledge distribution, retention risk."
    ),
    total_days=70,
    signals=[
        BenchmarkSignal(day=5, signal_type="knowledge.question",
                        entity="Priya", text="Billing question routed to Priya"),
        BenchmarkSignal(day=15, signal_type="knowledge.question",
                        entity="Priya", text="Billing question routed to Priya"),
        BenchmarkSignal(day=25, signal_type="knowledge.question",
                        entity="Priya", text="Billing question routed to Priya"),
        BenchmarkSignal(day=35, signal_type="knowledge.question",
                        entity="Priya", text="Billing question routed to Priya"),
        BenchmarkSignal(day=45, signal_type="knowledge.question",
                        entity="Priya", text="Billing question routed to Priya"),
        BenchmarkSignal(day=55, signal_type="hr.risk",
                        entity="Internal", text="Priya requests extended leave — billing system at risk"),
    ],
    checkpoints=[
        CheckpointExpectation(
            day=35,
            description="5 questions routed to Priya — pattern emerging",
            expected_epistemic_state="preliminary",
            expected_learning_state="hypothesis_created",
            expected_belief="Priya may be a knowledge bottleneck for billing",
        ),
        CheckpointExpectation(
            day=55,
            description="Priya requests leave — bottleneck confirmed",
            expected_epistemic_state="supported",
            expected_delivery_state="prepare_eligible",
            expected_prepare_activates=True,
            expected_belief="Priya is a single point of failure for the billing system",
        ),
    ],
    forbidden_future_leakage=["CustomerA", "Acme"],
)


# ════════════════════════════════════════════════════════════════════════════
# Story 8: Legal Interpretation Disagreement (Contract Ambiguity)
# ════════════════════════════════════════════════════════════════════════════

STORY_8_LEGAL_DISAGREEMENT = BenchmarkStory(
    story_id="story-08-legal-disagreement",
    title="Legal interpretation disagreement — contract ambiguity",
    failure_shape="legal_disagreement",
    description=(
        "Enterprise contract has ambiguous SSO language. Legal says it "
        "requires legacy compatibility. Sales says it doesn't. The "
        "disagreement blocks the renewal decision. Tests: disagreement "
        "preservation, legal interpretation, decision boundary."
    ),
    total_days=40,
    signals=[
        BenchmarkSignal(day=5, signal_type="legal.interpretation",
                        entity="EnterpriseCo", text="Legal: contract language requires legacy SSO compatibility"),
        BenchmarkSignal(day=10, signal_type="sales.interpretation",
                        entity="EnterpriseCo", text="Sales: contract language does not require legacy SSO compatibility"),
        BenchmarkSignal(day=20, signal_type="customer.commitment_made",
                        entity="EnterpriseCo", text="EnterpriseCo renewal decision needed by Day 40"),
    ],
    checkpoints=[
        CheckpointExpectation(
            day=10,
            description="Legal and Sales disagree on contract interpretation",
            expected_epistemic_state="contested",
            expected_disputes=1,
            expected_can_decide=["Proceed with general direction"],
            expected_cannot_decide=["Determine migration sequence for enterprise-facing services"],
        ),
        CheckpointExpectation(
            day=20,
            description="Renewal deadline approaching — disagreement unresolved",
            expected_operational_state="decision_pending",
            expected_delivery_state="prepare_eligible",
            expected_prepare_activates=True,
            expected_belief="Contract interpretation disagreement blocks the renewal decision",
        ),
    ],
    forbidden_future_leakage=["CustomerA", "Acme"],
)


# ════════════════════════════════════════════════════════════════════════════
# Story 9: Incident Pattern That's Coincidence (False Pattern)
# ════════════════════════════════════════════════════════════════════════════

STORY_9_COINCIDENTAL_PATTERN = BenchmarkStory(
    story_id="story-09-coincidental-pattern",
    title="Incident pattern that's coincidence — false pattern",
    failure_shape="coincidental_pattern",
    description=(
        "Three incidents occur on Fridays over 6 weeks. Maestro hypothesizes "
        "a 'Friday incident pattern.' But the 4th, 5th, and 6th Fridays have "
        "no incidents. The pattern was coincidence. Tests: false pattern "
        "detection, belief weakening, falsification."
    ),
    total_days=60,
    signals=[
        BenchmarkSignal(day=7, signal_type="incident.friday",
                        entity="Internal", text="Incident occurred on Friday"),
        BenchmarkSignal(day=14, signal_type="incident.friday",
                        entity="Internal", text="Incident occurred on Friday"),
        BenchmarkSignal(day=21, signal_type="incident.friday",
                        entity="Internal", text="Incident occurred on Friday"),
        BenchmarkSignal(day=28, signal_type="incident.none",
                        entity="Internal", text="No incident on Friday"),
        BenchmarkSignal(day=35, signal_type="incident.none",
                        entity="Internal", text="No incident on Friday"),
        BenchmarkSignal(day=42, signal_type="incident.none",
                        entity="Internal", text="No incident on Friday"),
    ],
    checkpoints=[
        CheckpointExpectation(
            day=21,
            description="3 Friday incidents — pattern hypothesized",
            expected_epistemic_state="preliminary",
            expected_learning_state="hypothesis_created",
            expected_belief="Incidents may follow a Friday pattern",
        ),
        CheckpointExpectation(
            day=35,
            description="2 Fridays without incidents — belief weakening",
            expected_learning_state="prospectively_testing",
            expected_learning_effect="belief_weakened",
        ),
        CheckpointExpectation(
            day=42,
            description="3 Fridays without incidents — pattern falsified",
            expected_learning_state="falsified",
            expected_learning_effect="falsified",
            expected_belief="Friday incident pattern was coincidence — falsified",
        ),
    ],
    forbidden_future_leakage=["CustomerA", "Acme"],
)


# ════════════════════════════════════════════════════════════════════════════
# Story 10: Previously Learned Pattern Becoming False After Reorg (Falsification)
# ════════════════════════════════════════════════════════════════════════════

STORY_10_REORG_FALSIFICATION = BenchmarkStory(
    story_id="story-10-reorg-falsification",
    title="Previously learned pattern becoming false after reorg — falsification",
    failure_shape="reorg_falsification",
    description=(
        "Maestro learned: 'When Security is involved early, renewal success "
        "rate is higher.' After a reorganization, Security is now involved "
        "early in every renewal — but renewal success rate drops. The "
        "learned pattern is no longer valid in the new organizational "
        "context. Tests: scope invalidation, pattern falsification after "
        "structural change."
    ),
    total_days=90,
    signals=[
        # Phase 1: Pattern learned (days 1-30)
        BenchmarkSignal(day=5, signal_type="outcome.positive",
                        entity="CustA", text="Renewal won — Security involved early"),
        BenchmarkSignal(day=10, signal_type="outcome.positive",
                        entity="CustB", text="Renewal won — Security involved early"),
        BenchmarkSignal(day=15, signal_type="outcome.positive",
                        entity="CustC", text="Renewal won — Security involved early"),
        # Phase 2: Reorganization (day 40)
        BenchmarkSignal(day=40, signal_type="org.reorganization",
                        entity="Internal", text="Reorganization: Security now involved in every renewal by default"),
        # Phase 3: Pattern fails (days 50-85)
        BenchmarkSignal(day=50, signal_type="outcome.negative",
                        entity="CustD", text="Renewal lost — Security involved early"),
        BenchmarkSignal(day=65, signal_type="outcome.negative",
                        entity="CustE", text="Renewal lost — Security involved early"),
        BenchmarkSignal(day=80, signal_type="outcome.negative",
                        entity="CustF", text="Renewal lost — Security involved early"),
    ],
    checkpoints=[
        CheckpointExpectation(
            day=15,
            description="3 renewals won with early Security — pattern learned",
            expected_learning_state="learning_updated",
            expected_learning_effect="belief_strengthened",
            expected_belief="Early Security involvement correlates with renewal success",
        ),
        CheckpointExpectation(
            day=40,
            description="Reorganization — context changed",
            expected_epistemic_state="contested",
            expected_unknowns=["Does the learned pattern still hold after the reorg?"],
        ),
        CheckpointExpectation(
            day=80,
            description="3 renewals lost with early Security — pattern falsified",
            expected_learning_state="falsified",
            expected_learning_effect="falsified",
            expected_belief="Early Security involvement no longer correlates with success after reorg — pattern falsified",
            expected_what_would_change_belief="A new pattern emerging in the post-reorg context",
        ),
    ],
    forbidden_future_leakage=["CustomerA", "Acme"],
)


# ════════════════════════════════════════════════════════════════════════════
# The Complete Benchmark
# ════════════════════════════════════════════════════════════════════════════

ALL_STORIES: list[BenchmarkStory] = [
    STORY_1_GLOBEX_DRIFT,
    STORY_2_OAUTH_SECURITY,
    STORY_3_PRICING_LEAK,
    STORY_4_HIRING_COLLAPSE,
    STORY_5_SCOPE_MUTATION,
    STORY_6_DUPLICATE_WORK,
    STORY_7_EXPERT_BOTTLENECK,
    STORY_8_LEGAL_DISAGREEMENT,
    STORY_9_COINCIDENTAL_PATTERN,
    STORY_10_REORG_FALSIFICATION,
]


def get_story(story_id: str) -> BenchmarkStory | None:
    """Get a benchmark story by ID."""
    for s in ALL_STORIES:
        if s.story_id == story_id:
            return s
    return None


def get_stories_by_failure_shape(shape: str) -> list[BenchmarkStory]:
    """Get all stories testing a specific failure shape."""
    return [s for s in ALL_STORIES if s.failure_shape == shape]


def get_all_failure_shapes() -> list[str]:
    """Get all 10 failure shapes tested by the benchmark."""
    return [s.failure_shape for s in ALL_STORIES]
