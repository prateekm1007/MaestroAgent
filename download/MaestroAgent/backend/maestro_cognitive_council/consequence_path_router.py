"""
Maestro Cognitive Council — Gate 2: Consequence-Path Router.

Replaces keyword-based specialist routing with consequence-path routing
that traverses the organizational relationship graph.

The router asks:
  - Who owns the object?
  - Who depends on it?
  - Who can veto it?
  - Who absorbs failure?
  - Who made commitments about it?
  - Who has relevant precedent?
  - Who must communicate the outcome?

This produces a dynamic council based on organizational relationships,
not keyword matching. For example, OAuth standardization:
  Direct domain: Engineering, Security
  Consequence paths:
    authentication change → enterprise contract compatibility → Legal
    migration timing → active renewals → Sales
    customer-visible behavior → Customer Success
    capital/time allocation → Finance

Reference: docs/MAESTRO_COGNITIVE_COUNCIL_AUDIT_AND_WIRING_PLAN.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from .situation_engine import LivingSituation, SPECIALIST_DOMAIN_MAP

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# Consequence Path — a directed edge in the organizational relationship graph
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class ConsequencePath:
    """A path from a situation's topic to a specialist who must be consulted.

    Example:
      topic: "authentication change"
      consequence: "enterprise contract compatibility"
      specialist: "legal"
      reason: "OAuth changes may breach legacy compatibility obligations"
    """
    topic: str                           # what aspect of the situation triggers this path
    consequence: str                     # what organizational consequence follows
    specialist: str                      # who must be consulted as a result
    reason: str                          # why this specialist is relevant
    path_type: str = "depends_on"        # owns | depends_on | can_veto | absorbs_failure | committed | precedent | communicates


# ════════════════════════════════════════════════════════════════════════════
# The consequence graph — maps topics → consequence paths
# ════════════════════════════════════════════════════════════════════════════

# This graph encodes organizational relationships. When a situation touches
# a topic, the router traverses this graph to find all specialists who must
# be consulted — not just the direct domain owners.

CONSEQUENCE_GRAPH: dict[str, list[ConsequencePath]] = {
    # ── Authentication / Security topics ──────────────────────────────────
    "auth": [
        ConsequencePath("auth", "enterprise contract compatibility", "legal",
                        "Authentication changes may breach legacy compatibility obligations",
                        "depends_on"),
        ConsequencePath("auth", "customer-visible behavior", "customer_success",
                        "Authentication changes are customer-visible and may cause login disruptions",
                        "communicates"),
        ConsequencePath("auth", "migration timing vs active renewals", "sales",
                        "Authentication migration during renewal windows creates deal risk",
                        "absorbs_failure"),
    ],
    "oauth": [
        ConsequencePath("oauth", "enterprise contract compatibility", "legal",
                        "OAuth standardization may breach legacy SSO obligations",
                        "depends_on"),
        ConsequencePath("oauth", "migration timing vs active renewals", "sales",
                        "OAuth migration during renewals creates deal risk",
                        "absorbs_failure"),
        ConsequencePath("oauth", "customer-visible behavior", "customer_success",
                        "OAuth changes are customer-visible and may cause login disruptions",
                        "communicates"),
        ConsequencePath("oauth", "capital/time allocation", "finance",
                        "OAuth migration requires engineering capacity allocation",
                        "depends_on"),
    ],
    "sso": [
        ConsequencePath("sso", "enterprise contract compatibility", "legal",
                        "SSO commitments are often contractually binding",
                        "committed"),
        ConsequencePath("sso", "customer-visible behavior", "customer_success",
                        "SSO changes are customer-visible",
                        "communicates"),
        ConsequencePath("sso", "security architecture review", "security",
                        "SSO implementation requires security approval",
                        "can_veto"),
    ],
    "security": [
        ConsequencePath("security", "customer-visible behavior", "customer_success",
                        "Security conditions affect customer trust",
                        "communicates"),
        ConsequencePath("security", "contractual obligations", "legal",
                        "Security commitments may be contractually binding",
                        "committed"),
    ],

    # ── Pricing / Commercial topics ────────────────────────────────────────
    "pricing": [
        ConsequencePath("pricing", "deal margins", "finance",
                        "Pricing exceptions affect revenue forecasting",
                        "absorbs_failure"),
        ConsequencePath("pricing", "renewal expectations", "customer_success",
                        "Pricing changes affect renewal conversations",
                        "communicates"),
        ConsequencePath("pricing", "competitive positioning", "marketing",
                        "Pricing signals affect market positioning",
                        "depends_on"),
    ],
    "renewal": [
        ConsequencePath("renewal", "revenue forecasting", "finance",
                        "Renewals affect revenue projections",
                        "absorbs_failure"),
        ConsequencePath("renewal", "customer health", "customer_success",
                        "Renewals are the primary CS health signal",
                        "owns"),
        ConsequencePath("renewal", "contractual obligations", "legal",
                        "Renewals may trigger contract review",
                        "depends_on"),
    ],
    "contract": [
        ConsequencePath("contract", "compliance obligations", "legal",
                        "Contract terms create compliance obligations",
                        "owns"),
        ConsequencePath("contract", "revenue recognition", "finance",
                        "Contract terms affect revenue recognition",
                        "depends_on"),
    ],

    # ── Engineering / Technical topics ─────────────────────────────────────
    "deployment": [
        ConsequencePath("deployment", "customer-visible behavior", "customer_success",
                        "Deployments may cause customer-visible incidents",
                        "communicates"),
        ConsequencePath("deployment", "incident response", "support",
                        "Deployment failures generate support tickets",
                        "absorbs_failure"),
    ],
    "incident": [
        ConsequencePath("incident", "customer communication", "communications",
                        "Incidents require customer communication",
                        "communicates"),
        ConsequencePath("incident", "customer trust", "customer_success",
                        "Incidents affect customer trust and renewal risk",
                        "absorbs_failure"),
        ConsequencePath("incident", "root cause analysis", "engineering",
                        "Incidents require engineering root cause analysis",
                        "owns"),
    ],
    "bug": [
        ConsequencePath("bug", "customer impact", "support",
                        "Bugs generate support tickets",
                        "absorbs_failure"),
        ConsequencePath("bug", "engineering capacity", "engineering",
                        "Bugs consume engineering capacity",
                        "owns"),
    ],

    # ── Product topics ─────────────────────────────────────────────────────
    "roadmap": [
        ConsequencePath("roadmap", "customer commitments", "sales",
                        "Roadmap items may have been committed to customers",
                        "committed"),
        ConsequencePath("roadmap", "engineering capacity", "engineering",
                        "Roadmap items consume engineering capacity",
                        "depends_on"),
    ],
    "feature": [
        ConsequencePath("feature", "customer commitments", "sales",
                        "Features may have been promised to customers",
                        "committed"),
        ConsequencePath("feature", "engineering capacity", "engineering",
                        "Features consume engineering capacity",
                        "depends_on"),
    ],

    # ── People / Organizational topics ─────────────────────────────────────
    "hiring": [
        ConsequencePath("hiring", "budget allocation", "finance",
                        "Hiring requires budget allocation",
                        "depends_on"),
        ConsequencePath("hiring", "team capacity", "operations",
                        "Hiring affects team capacity planning",
                        "owns"),
    ],
    "burnout": [
        ConsequencePath("burnout", "retention risk", "hr",
                        "Burnout is a leading retention risk indicator",
                        "owns"),
        ConsequencePath("burnout", "delivery risk", "operations",
                        "Burnout affects delivery capacity",
                        "absorbs_failure"),
    ],
}


# ════════════════════════════════════════════════════════════════════════════
# ConsequencePathRouter
# ════════════════════════════════════════════════════════════════════════════

class ConsequencePathRouter:
    """Routes specialists based on organizational consequence paths.

    This replaces keyword-based routing. Instead of:
        if "oauth" in text: specialists = ["engineering", "security"]

    It traverses the consequence graph:
        oauth → enterprise contract compatibility → legal
        oauth → migration timing vs active renewals → sales
        oauth → customer-visible behavior → customer_success
        oauth → capital/time allocation → finance

    Producing a dynamic council based on organizational relationships.

    Usage:
        router = ConsequencePathRouter()
        result = router.route(situation)
        # result.specialists = ["chief_of_staff", "customer_success", "engineering",
        #                        "finance", "legal", "sales", "security"]
        # result.paths = [ConsequencePath(...), ...]
    """

    def __init__(self, use_keyword_fallback: bool = True):
        """Initialize the router.

        Args:
            use_keyword_fallback: if True, fall back to keyword-based routing
                (SPECIALIST_DOMAIN_MAP) when no consequence paths are found.
                This ensures backward compatibility during the transition.
        """
        self._use_keyword_fallback = use_keyword_fallback

    def route(self, situation: LivingSituation) -> "RoutingResult":
        """Route specialists for a situation via consequence paths.

        Returns a RoutingResult with:
          - specialists: the set of specialists to consult (sorted)
          - paths: the consequence paths that led to each specialist
          - direct_owners: the specialists who directly own the topic
          - consequence_specialists: specialists reached via consequence paths
        """
        # Build a text bag from the situation
        text_bag = self._build_text_bag(situation)
        text_lower = text_bag.lower()

        # 1. Find direct domain owners (keyword match against SPECIALIST_DOMAIN_MAP)
        direct_owners: set[str] = set()
        matched_topics: set[str] = set()
        for specialist, keywords in SPECIALIST_DOMAIN_MAP.items():
            if not keywords:
                continue
            for kw in keywords:
                if kw in text_lower:
                    direct_owners.add(specialist)
                    matched_topics.add(kw)
                    break

        # 2. Traverse consequence graph from matched topics
        consequence_paths: list[ConsequencePath] = []
        consequence_specialists: set[str] = set()

        for topic, paths in CONSEQUENCE_GRAPH.items():
            if topic in text_lower:
                for path in paths:
                    consequence_paths.append(path)
                    consequence_specialists.add(path.specialist)

        # 3. Always include chief_of_staff (the synthesizer)
        all_specialists: set[str] = {"chief_of_staff"}

        # 4. Add direct owners
        all_specialists.update(direct_owners)

        # 5. Add consequence-path specialists
        all_specialists.update(consequence_specialists)

        # 6. Always include customer_success + sales for entity situations
        #    (they're broadly relevant to any customer-facing situation)
        if situation.entity:
            all_specialists.add("customer_success")
            all_specialists.add("sales")

        # 7. Keyword fallback if no consequence paths found
        if not consequence_paths and self._use_keyword_fallback:
            # Already handled by direct_owners above — no additional action needed
            pass

        return RoutingResult(
            specialists=sorted(all_specialists),
            paths=consequence_paths,
            direct_owners=sorted(direct_owners),
            consequence_specialists=sorted(consequence_specialists),
            matched_topics=sorted(matched_topics),
        )

    def _build_text_bag(self, situation: LivingSituation) -> str:
        """Build a text bag from the situation for topic matching."""
        parts = [situation.title]
        for f in situation.known_facts:
            parts.append(f.statement)
        for e in situation.timeline:
            parts.append(e.description)
        return " ".join(parts)

    def explain(self, result: "RoutingResult") -> str:
        """Explain WHY each specialist was routed (transparency).

        The user should be able to understand why Maestro consulted
        Legal vs. Finance vs. Engineering for a given situation.
        """
        if not result.paths:
            return f"Routed {len(result.specialists)} specialists via direct domain ownership."

        lines = [f"Routed {len(result.specialists)} specialists via consequence paths:"]
        for path in result.paths:
            lines.append(
                f"  {path.topic} → {path.consequence} → {path.specialist} "
                f"({path.path_type}: {path.reason})"
            )
        if result.direct_owners:
            lines.append(f"  Direct owners: {', '.join(result.direct_owners)}")
        return "\n".join(lines)


@dataclass
class RoutingResult:
    """The result of consequence-path routing.

    Contains:
      - specialists: all specialists to consult (sorted)
      - paths: the consequence paths traversed
      - direct_owners: specialists who directly own the topic
      - consequence_specialists: specialists reached via consequence paths
      - matched_topics: the topics that triggered the routing
    """
    specialists: list[str] = field(default_factory=list)
    paths: list[ConsequencePath] = field(default_factory=list)
    direct_owners: list[str] = field(default_factory=list)
    consequence_specialists: list[str] = field(default_factory=list)
    matched_topics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "specialists": self.specialists,
            "paths": [
                {
                    "topic": p.topic,
                    "consequence": p.consequence,
                    "specialist": p.specialist,
                    "reason": p.reason,
                    "path_type": p.path_type,
                }
                for p in self.paths
            ],
            "direct_owners": self.direct_owners,
            "consequence_specialists": self.consequence_specialists,
            "matched_topics": self.matched_topics,
        }
