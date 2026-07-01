"""
V8 Daily Work #6 — Role-Specific Playbooks.

Thin layers over decision.py that format the same evidence differently
for sales, marketing, and product roles. Not new engines — the playbook
engine reads the same model + signals + customer judgment data and
produces role-specific output:

  - Sales: match CRM + draft outreach with talking points from transcripts
  - Marketing: unify ad-spend signals into single ROI view
  - Product: transcript → PRD outline + tickets + unresolved concerns

Each playbook is a thin formatting layer — the intelligence is in the
existing engines (decision.py, customer_judgment.py). The playbook just
asks "what does THIS role need to see?" and formats the answer.

API: GET /api/oem/playbook/{role}?context=...
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class PlaybookEngine:
    """Format evidence differently for each role.

    The playbook engine is intentionally NOT a new cognitive engine —
    it's a formatting layer. It reads the same model + signals that
    decision.py and customer_judgment.py read, and produces role-specific
    output. The intelligence is in the existing engines; the playbook
    just asks "what does this role need to see?"
    """

    def __init__(self, model: Any, signals: list, decisions: Any = None) -> None:
        self.model = model
        self.signals = signals
        self.decisions = decisions

    def playbook(self, role: str, context: str = "") -> dict[str, Any]:
        """Generate a role-specific playbook.

        Args:
            role: "sales" | "marketing" | "product"
            context: Optional context (e.g. a customer name for sales,
                     a campaign name for marketing, a feature for product)

        Returns:
            Role-specific dict with drafted artifacts, evidence, and
            action items. See sales(), marketing(), product() for details.
        """
        role = role.lower().strip()
        if role == "sales":
            return self.sales(context)
        elif role == "marketing":
            return self.marketing(context)
        elif role == "product":
            return self.product(context)
        else:
            return {
                "role": role,
                "error": f"Unsupported role: '{role}'. Supported: sales, marketing, product.",
                "supported_roles": ["sales", "marketing", "product"],
            }

    def sales(self, customer: str = "") -> dict[str, Any]:
        """Sales playbook — match CRM + draft outreach with talking points.

        If a customer is specified, produces a drafted outreach email
        with talking points derived from the org's history with that
        customer (meetings, commitments, objections). If no customer is
        specified, identifies the top at-risk customer and produces
        outreach for them.

        Returns:
            {
                role: "sales",
                customer: str,
                drafted_outreach: {to, subject, body, talking_points},
                customer_signals: list,
                arr_at_stake: float,
                next_best_action: str,
                evidence: list,
            }
        """
        from maestro_oem.customer_judgment import CustomerJudgmentEngine
        from maestro_oem.signal import SignalType, SignalProvider

        cje = CustomerJudgmentEngine(self.model, self.signals, self.decisions)

        # If no customer specified, find the top at-risk customer
        if not customer:
            customers = cje._all_customers()
            if not customers:
                return {
                    "role": "sales",
                    "customer": None,
                    "error": "No customers found in the model. Connect a CRM provider to enable the sales playbook.",
                    "drafted_outreach": None,
                }
            # Pick the customer with the most signals (most context to work with)
            customer = max(customers, key=lambda c: len(cje._customer_signals(c)))

        # Get customer signals
        customer_signals = cje._customer_signals(customer)
        if not customer_signals:
            return {
                "role": "sales",
                "customer": customer,
                "error": f"No signals found for customer '{customer}'.",
                "drafted_outreach": None,
            }

        # Extract talking points from signal history
        talking_points = []
        for sig in customer_signals[:10]:
            sig_type = sig.type.value if hasattr(sig.type, "value") else str(sig.type)
            text = sig.metadata.get("text", "") or sig.metadata.get("title", "") or sig.metadata.get("description", "")
            if text:
                talking_points.append(f"Last {sig_type.replace('customer.', '').replace('_', ' ')}: {text[:80]}")
            elif sig_type == "customer.objection":
                talking_points.append(f"Customer raised an objection — address it proactively.")
            elif sig_type == "customer.commitment_broken":
                talking_points.append(f"A commitment was broken — acknowledge and offer a remedy.")
            elif sig_type == "customer.champion_quiet":
                talking_points.append(f"The champion has gone silent — re-engage with a check-in.")

        # Find the internal contact (actor) who has the most interactions with this customer
        from collections import Counter
        actors = Counter(s.actor for s in customer_signals if s.actor)
        owner = actors.most_common(1)[0][0] if actors else "sales@acme.com"

        # Get ARR at stake
        arr = cje._arr_at_stake(customer) if hasattr(cje, "_arr_at_stake") else 0

        # Draft the outreach email
        subject = f"Following up — {customer}"
        body = (
            f"Hi {customer} team,\n\n"
            f"I wanted to follow up on our recent interactions. "
        )
        if talking_points:
            body += f"We've noticed a few things worth discussing:\n\n"
            for tp in talking_points[:3]:
                body += f"  • {tp}\n"
            body += "\n"
        body += (
            f"I'd love to schedule a brief call to address any open items and "
            f"make sure we're aligned on next steps. Are you available this week?\n\n"
            f"Best,\n{owner}"
        )

        return {
            "role": "sales",
            "customer": customer,
            "drafted_outreach": {
                "to": f"{customer}@example.com",  # placeholder — user verifies
                "from": owner,
                "subject": subject,
                "body": body,
                "talking_points": talking_points[:5],
            },
            "customer_signal_count": len(customer_signals),
            "arr_at_stake": round(arr, 2),
            "next_best_action": "Review the drafted outreach, customize the talking points, and send via Gmail (Maestro can create a draft).",
            "evidence": [
                f"{len(customer_signals)} customer signals from CRM",
                f"ARR at stake: ${arr:,.2f}" if arr > 0 else "ARR at stake: unknown",
                f"Top internal contact: {owner}",
            ],
        }

    def marketing(self, campaign: str = "") -> dict[str, Any]:
        """Marketing playbook — unify ad-spend signals into single ROI view.

        Aggregates all signals related to marketing campaigns (ads, content,
        social) and produces a unified ROI view: spend, reach, conversions,
        and cost-per-acquisition across channels.

        Returns:
            {
                role: "marketing",
                campaigns: list[{name, spend, reach, conversions, cpa, roi}],
                total_spend: float,
                total_conversions: int,
                overall_cpa: float,
                best_campaign: str,
                worst_campaign: str,
                recommendation: str,
            }
        """
        from maestro_oem.signal import SignalType
        from collections import defaultdict

        # Find marketing-related signals (DEPLOYMENT, RELEASE, PAGE_CREATED for content)
        # Marketing signals would come from ad platforms — we look for metadata
        # that indicates marketing content
        marketing_signals = []
        for s in self.signals:
            domain = s.metadata.get("domain", "")
            if domain in ("marketing", "ads", "content", "social", "campaign"):
                marketing_signals.append(s)
            elif "campaign" in s.metadata.get("text", "").lower():
                marketing_signals.append(s)

        if not marketing_signals:
            return {
                "role": "marketing",
                "campaigns": [],
                "total_spend": 0,
                "total_conversions": 0,
                "overall_cpa": 0,
                "recommendation": "No marketing signals found. Connect ad platform providers (Google Ads, Facebook Ads) to enable the marketing playbook.",
                "evidence": ["0 marketing signals in the model"],
            }

        # Aggregate by campaign
        campaigns: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "spend": 0.0, "reach": 0, "conversions": 0, "signals": 0,
        })

        for sig in marketing_signals:
            campaign_name = sig.metadata.get("campaign", sig.metadata.get("domain", "unknown"))
            campaigns[campaign_name]["spend"] += float(sig.metadata.get("spend", 0) or 0)
            campaigns[campaign_name]["reach"] += int(sig.metadata.get("reach", 0) or 0)
            campaigns[campaign_name]["conversions"] += int(sig.metadata.get("conversions", 0) or 0)
            campaigns[campaign_name]["signals"] += 1

        # Calculate CPA + ROI per campaign
        campaign_list = []
        for name, data in campaigns.items():
            cpa = data["spend"] / data["conversions"] if data["conversions"] > 0 else 0
            roi = (data["conversions"] * 100 - data["spend"]) / data["spend"] if data["spend"] > 0 else 0
            campaign_list.append({
                "name": name,
                "spend": round(data["spend"], 2),
                "reach": data["reach"],
                "conversions": data["conversions"],
                "cpa": round(cpa, 2),
                "roi": round(roi, 2),
                "signal_count": data["signals"],
            })

        # Sort by ROI descending
        campaign_list.sort(key=lambda c: c["roi"], reverse=True)

        total_spend = sum(c["spend"] for c in campaign_list)
        total_conversions = sum(c["conversions"] for c in campaign_list)
        overall_cpa = total_spend / total_conversions if total_conversions > 0 else 0

        best = campaign_list[0]["name"] if campaign_list else "none"
        worst = campaign_list[-1]["name"] if campaign_list else "none"

        recommendation = (
            f"Best-performing campaign: {best} (ROI {campaign_list[0]['roi']:.0%}). "
            f"Reallocate budget from {worst} to {best} to maximize ROI. "
            f"Overall CPA: ${overall_cpa:.2f}."
            if campaign_list else "No campaigns to analyze."
        )

        return {
            "role": "marketing",
            "campaigns": campaign_list,
            "total_spend": round(total_spend, 2),
            "total_conversions": total_conversions,
            "overall_cpa": round(overall_cpa, 2),
            "best_campaign": best,
            "worst_campaign": worst,
            "recommendation": recommendation,
            "evidence": [
                f"{len(marketing_signals)} marketing signals analyzed",
                f"{len(campaign_list)} campaigns aggregated",
                f"Total spend: ${total_spend:,.2f}",
            ],
        }

    def product(self, feature: str = "") -> dict[str, Any]:
        """Product playbook — transcript → PRD outline + tickets + concerns.

        Scans signals for meeting transcripts, decisions, and open
        questions related to a product area. Produces a PRD outline
        with sections, drafted tickets, and unresolved concerns.

        Returns:
            {
                role: "product",
                feature: str,
                prd_outline: {title, sections: list},
                drafted_tickets: list[{summary, description, priority}],
                unresolved_concerns: list,
                evidence: list,
            }
        """
        from maestro_oem.signal import SignalType

        # Find product-related signals (meetings, decisions, RFCs)
        product_signals = []
        for s in self.signals:
            sig_type = s.type.value if hasattr(s.type, "value") else str(s.type)
            text = s.metadata.get("text", "") or s.metadata.get("title", "") or s.metadata.get("description", "")
            if sig_type in ("meeting.completed", "slack.decision", "rfc.created", "page.created"):
                if feature and feature.lower() not in text.lower():
                    continue
                product_signals.append(s)
            elif feature and feature.lower() in text.lower():
                product_signals.append(s)

        if not product_signals and feature:
            return {
                "role": "product",
                "feature": feature,
                "prd_outline": None,
                "drafted_tickets": [],
                "unresolved_concerns": [],
                "evidence": [f"No signals found for feature '{feature}'."],
            }

        if not product_signals:
            return {
                "role": "product",
                "feature": feature or "general",
                "prd_outline": None,
                "drafted_tickets": [],
                "unresolved_concerns": [],
                "evidence": ["No product-related signals found. Connect meeting/confluence providers to enable the product playbook."],
            }

        # Build PRD outline from the signal history
        feature_name = feature or "New Feature"
        sections = [
            {"title": "Problem Statement", "content": self._extract_problem(product_signals)},
            {"title": "Proposed Solution", "content": self._extract_solution(product_signals)},
            {"title": "Success Metrics", "content": self._extract_metrics(product_signals)},
            {"title": "Open Questions", "content": self._extract_open_questions(product_signals)},
        ]

        # Draft tickets from action items in the signals
        drafted_tickets = []
        for sig in product_signals[:5]:
            text = sig.metadata.get("text", "") or sig.metadata.get("title", "")
            if any(kw in text.lower() for kw in ("todo", "action", "should", "need to", "must")):
                drafted_tickets.append({
                    "summary": text[:80],
                    "description": f"Extracted from {sig.type} signal by {sig.actor}. Full context: {text[:200]}",
                    "priority": "high" if "urgent" in text.lower() or "p0" in text.lower() else "medium",
                    "source_signal_id": str(sig.signal_id),
                })

        # Extract unresolved concerns
        unresolved_concerns = []
        for sig in product_signals:
            text = sig.metadata.get("text", "") or sig.metadata.get("title", "")
            if any(kw in text.lower() for kw in ("concern", "risk", "unresolved", "unclear", "question")):
                unresolved_concerns.append({
                    "concern": text[:120],
                    "raised_by": sig.actor,
                    "source_signal_id": str(sig.signal_id),
                })

        return {
            "role": "product",
            "feature": feature_name,
            "prd_outline": {
                "title": f"PRD: {feature_name}",
                "sections": sections,
            },
            "drafted_tickets": drafted_tickets[:5],
            "unresolved_concerns": unresolved_concerns[:5],
            "evidence": [
                f"{len(product_signals)} product signals analyzed",
                f"{len(drafted_tickets)} tickets drafted",
                f"{len(unresolved_concerns)} unresolved concerns identified",
            ],
        }

    def _extract_problem(self, signals: list) -> str:
        """Extract the problem statement from signals."""
        for s in signals:
            text = s.metadata.get("text", "") or s.metadata.get("title", "")
            if "problem" in text.lower() or "issue" in text.lower() or "fail" in text.lower():
                return text[:200]
        # Fallback: use the first signal's text
        if signals:
            text = signals[0].metadata.get("text", "") or signals[0].metadata.get("title", "")
            return text[:200] if text else "Problem statement not yet defined — gather more context from meetings."
        return "No problem statement available."

    def _extract_solution(self, signals: list) -> str:
        """Extract the proposed solution from signals."""
        for s in signals:
            text = s.metadata.get("text", "") or s.metadata.get("title", "")
            if "solution" in text.lower() or "propose" in text.lower() or "should" in text.lower():
                return text[:200]
        return "Proposed solution not yet defined — draft based on the problem statement and open questions."

    def _extract_metrics(self, signals: list) -> str:
        """Extract success metrics from signals."""
        for s in signals:
            text = s.metadata.get("text", "") or s.metadata.get("title", "")
            if "metric" in text.lower() or "success" in text.lower() or "kpi" in text.lower():
                return text[:200]
        return "Success metrics not yet defined — define measurable outcomes (e.g. 'reduce incident rate by 20%')."

    def _extract_open_questions(self, signals: list) -> str:
        """Extract open questions from signals."""
        questions = []
        for s in signals:
            text = s.metadata.get("text", "") or s.metadata.get("title", "")
            if "?" in text:
                questions.append(text[:100])
        if questions:
            return "\n".join(f"  - {q}" for q in questions[:5])
        return "No open questions detected — verify with the team that all concerns are addressed."
