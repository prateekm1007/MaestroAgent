"""
Semantic Organizational Autocomplete Engine.

The real autocomplete — no hardcoded suggestions. Every result is derived
from the live OEM state across ALL data sources:

  - Learning Objects (patterns, experts, bottlenecks, departure risks, etc.)
  - Patterns (detected organizational patterns)
  - Receipts (signal history)
  - Laws (induced organizational laws)
  - Evidence (evidence graph nodes + edges)
  - Knowledge Graph (hidden experts, concentration risks, collaboration)
  - Execution Model (health metrics, approval network, risks)
  - Recommendations (active decision recommendations)
  - Context (current screen, user, organization)
  - History (contradiction feedback log — feedback learning)

For each query, returns rich results with:
  - completion: the suggested text
  - reason: why this suggestion is relevant
  - expected_outcome: what the OEM predicts will happen
  - confidence: 0.0–1.0 Bayesian confidence
  - evidence: supporting evidence chain
  - similar_executions: past similar decisions/patterns
  - citations: law codes, LO ids, receipt ids

Ranking factors:
  - Recency: more recent evidence scores higher
  - Authority: entities with higher influence score higher
  - Outcome weighting: laws with more validated runtimes score higher
  - Feedback learning: laws/LOs that received 'agree' score higher,
    'reject' scores lower (uses the ContradictionLog)

Typing "We should..." produces completely different results for every
company because the underlying LOs, laws, experts, and recommendations
are all derived from that company's actual signal history.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from maestro_oem import OEMEngine, DecisionEngine, EvidenceGraph


# ─── Synonyms / concept expansion ───

# Maps common keywords to OEM concept types. This is NOT hardcoded
# suggestions — it's a semantic expansion layer that maps natural language
# to OEM entity types. The actual results still come from the live OEM.
_CONCEPT_SYNONYMS: dict[str, set[str]] = {
    "hire": {"hiring", "recruit", "onboarding", "staffing", "headcount"},
    "fire": {"departure", "resign", "quit", "attrition", "leaving"},
    "bottleneck": {"blocker", "blockage", "gate", "impediment", "stuck"},
    "risk": {"danger", "threat", "hazard", "exposure", "vulnerability"},
    "expert": {"specialist", "knowledgeable", "go-to", "authority"},
    "law": {"rule", "pattern", "regularity", "invariant"},
    "drift": {"change", "shift", "deviation", "regression"},
    "approve": {"approval", "consent", "sign-off", "authorize"},
    "delay": {"late", "slow", "lag", "behind", "overdue"},
    "duplicate": {"redundant", "repeated", "overlap", "duplication"},
    "velocity": {"speed", "throughput", "cadence", "pace"},
    "incident": {"outage", "bug", "failure", "p1", "p2", "sev"},
    "payment": {"billing", "invoice", "charge", "subscription"},
    "security": {"vulnerability", "cve", "breach", "auth"},
    "legal": {"compliance", "contract", "policy", "regulation"},
    "launch": {"release", "ship", "deploy", "rollout"},
    "roadmap": {"plan", "schedule", "timeline", "milestone"},
    "pricing": {"price", "cost", "tier", "monetization"},
    "promote": {"promotion", "advancement", "elevation"},
    "oauth": {"auth", "sso", "identity", "token"},
    "platform": {"infrastructure", "infra", "platform", "foundation"},
    "engineering": {"dev", "developer", "eng", "swe"},
    # Customer Judgment Engine concepts — map NL queries to customer LOs/laws.
    "customer": {"account", "client", "prospect", "buyer"},
    "champion": {"advocate", "supporter", "ally"},
    "renewal": {"renew", "extend", "continue"},
    "churn": {"left", "departed", "cancelled", "lost"},
    "objection": {"concern", "pushback", "hesitation", "resistance"},
    "committee": {"buying committee", "decision committee", "stakeholders"},
    "commitment": {"promise", "pledge", "guarantee", "commitments"},
    # NOTE: demo-only company names (globex/initech/hooli) were previously
    # hardcoded here as semantic synonyms. This materially shaped autocomplete
    # outputs for ALL tenants — a real customer named "<customer>" would get
    # different suggestions than a customer named "Acme". Removed per the
    # external audit: semantic priors must be learned from tenant data, not
    # hardcoded from demo fixtures. If tenant-specific synonyms are needed,
    # they should be injected at query time from the org's own learning
    # objects, not baked into a global synonym dict.
}

# Maps keywords to OEM LearningObject types
_LO_TYPE_TRIGGERS: dict[str, str] = {
    "bottleneck": "bottleneck",
    "blocker": "bottleneck",
    "blockage": "bottleneck",
    "expert": "hidden_expert",
    "specialist": "hidden_expert",
    "departure": "departure_risk",
    "leaving": "departure_risk",
    "resign": "departure_risk",
    "attrition": "departure_risk",
    "duplicate": "duplicate_work",
    "redundant": "duplicate_work",
    "overlap": "duplicate_work",
    "knowledge death": "knowledge_death",
    "handoff": "handoff_delay",
    "delay": "handoff_delay",
    "approval": "approval_gate",
    "gate": "approval_gate",
    "incident": "incident_pattern",
    "p1": "incident_pattern",
    "outage": "incident_pattern",
    "velocity": "velocity_drop",
    "slowdown": "velocity_drop",
    "release": "release_pattern",
    "review": "review_pattern",
    "decision": "decision_pattern",
    # Customer Judgment Engine LO types
    "champion": "customer_committee_role",
    "committee": "customer_committee_role",
    "buyer": "customer_committee_role",
    "commitment": "customer_commitment",
    "promise": "customer_commitment",
    "pledge": "customer_commitment",
    "objection": "customer_risk",
    "churn": "customer_risk",
    "drift": "customer_drift",
    "renewal": "customer_decision_pattern",
    "customer_decision": "customer_decision_pattern",
}


@dataclass
class AutocompleteSuggestion:
    """A single autocomplete suggestion with full provenance."""
    completion: str                          # The text to complete
    query: str                               # The query to execute
    reason: str                              # Why this is relevant
    expected_outcome: str                    # What the OEM predicts
    confidence: float                        # 0.0–1.0
    evidence: list[dict[str, Any]]           # Supporting evidence
    similar_executions: list[dict[str, Any]] # Past similar patterns
    citations: list[str]                     # Law codes, LO ids, etc.
    source_type: str                         # law|expert|pattern|recommendation|...
    source_id: str                           # ID of the source entity
    rank_score: float = 0.0                  # Composite ranking score
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "completion": self.completion,
            "query": self.query,
            "reason": self.reason,
            "expected_outcome": self.expected_outcome,
            "confidence": round(self.confidence, 4),
            "evidence": self.evidence[:5],  # Top 5 evidence items
            "similar_executions": self.similar_executions[:3],
            "citations": self.citations,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "rank_score": round(self.rank_score, 4),
            "metadata": self.metadata,
        }


class SemanticAutocompleteEngine:
    """
    Real semantic autocomplete over the live OEM.

    Usage:
        engine = SemanticAutocompleteEngine(model, graph, decisions, contradiction_log)
        result = engine.suggest(
            query="We should hire more engineers",
            context={"surface": "ask", "user": "", "org": ""},
            limit=10,
        )
    """

    def __init__(
        self,
        model: Any,
        graph: EvidenceGraph,
        decisions: DecisionEngine,
        contradiction_log: Any = None,
        signals: list | None = None,
    ) -> None:
        self.model = model
        self.graph = graph
        self.decisions = decisions
        self.contradiction_log = contradiction_log
        self.signals = signals or []
        self._now = datetime.now(timezone.utc)

        # Build feedback-learning index: entity_id → (agree_count, reject_count)
        self._feedback_index = self._build_feedback_index()

        # Build adjacency map from edge list for fast lookup
        self._adjacency: dict[str, list[str]] = defaultdict(list)
        for edge in (graph.edges or []):
            src = getattr(edge, "source", "")
            tgt = getattr(edge, "target", "")
            if src and tgt:
                self._adjacency[src].append(tgt)
                self._adjacency[tgt].append(src)

    # ─── Public API ───

    def suggest(
        self,
        query: str,
        context: dict[str, Any] | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Return semantic autocomplete suggestions for a query.

        Args:
            query: The partial text typed by the user (e.g. "We should...")
            context: {surface, user, org} — used for context-aware ranking
            limit: Max suggestions to return

        Returns: {query, suggestions, total, context, ranking_explanation}
        """
        context = context or {}
        query_lower = query.lower().strip()
        tokens = self._tokenize(query_lower)
        expanded = self._expand_concepts(tokens)
        lo_types = self._match_lo_types(query_lower)

        candidates: list[AutocompleteSuggestion] = []

        # 1. Mine recommendations
        candidates.extend(self._mine_recommendations(query_lower, tokens, expanded, context))

        # 2. Mine laws
        candidates.extend(self._mine_laws(query_lower, tokens, expanded, context))

        # 3. Mine learning objects (by type trigger + keyword match)
        candidates.extend(self._mine_learning_objects(query_lower, tokens, expanded, lo_types, context))

        # 4. Mine hidden experts (from knowledge graph)
        candidates.extend(self._mine_experts(query_lower, tokens, expanded, context))

        # 5. Mine concentration risks
        candidates.extend(self._mine_risks(query_lower, tokens, expanded, context))

        # 6. Mine evidence graph (for similar executions)
        candidates.extend(self._mine_evidence_graph(query_lower, tokens, expanded, context))

        # Rank all candidates
        ranked = self._rank(candidates, context)

        # Deduplicate by source_id, keeping highest-ranked
        seen: set[str] = set()
        seen_completions: set[str] = set()  # Also dedup by completion text
        deduped: list[AutocompleteSuggestion] = []
        for c in ranked:
            key = f"{c.source_type}:{c.source_id}"
            comp_key = c.completion.strip().lower()
            if key in seen or comp_key in seen_completions:
                continue
            seen.add(key)
            seen_completions.add(comp_key)
            deduped.append(c)

        return {
            "query": query,
            "context": context,
            "suggestions": [s.to_dict() for s in deduped[:limit]],
            "total": len(deduped),
            "ranking_factors": {
                "recency": "Newer evidence scores higher (90-day half-life)",
                "authority": "Entities with higher influence score higher",
                "outcome": "Laws with more validated runtimes score higher",
                "feedback": "Agreed entities score higher, rejected score lower",
            },
            "semantic_expansion": {
                "tokens": tokens,
                "expanded_concepts": list(expanded),
                "matched_lo_types": lo_types,
            },
        }

    # ─── Tokenization & expansion ───

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Split into lowercase tokens, filtering stopwords and short words."""
        stopwords = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "have", "has", "had", "do", "does", "did", "will", "would",
            "could", "should", "may", "might", "must", "can", "of", "to",
            "in", "on", "at", "by", "for", "with", "about", "as", "into",
            "like", "through", "after", "over", "between", "out", "against",
            "during", "without", "before", "under", "around", "among",
            "we", "i", "you", "they", "it", "this", "that", "these", "those",
            "and", "or", "but", "if", "then", "else", "when", "where",
            "why", "how", "all", "each", "every", "both", "few", "more",
            "most", "other", "some", "such", "no", "not", "only", "own",
            "same", "so", "than", "too", "very", "just", "now",
        }
        tokens = re.findall(r"[a-z0-9]+", text)
        return [t for t in tokens if len(t) > 1 and t not in stopwords]

    @staticmethod
    def _expand_concepts(tokens: list[str]) -> set[str]:
        """Expand tokens using synonym map. Returns the full concept set."""
        expanded = set(tokens)
        for token in tokens:
            if token in _CONCEPT_SYNONYMS:
                expanded.update(_CONCEPT_SYNONYMS[token])
        # Also check if any token IS a synonym of a concept
        for concept, syns in _CONCEPT_SYNONYMS.items():
            for token in tokens:
                if token in syns:
                    expanded.add(concept)
                    expanded.update(syns)
        return expanded

    @staticmethod
    def _match_lo_types(query_lower: str) -> set[str]:
        """Determine which LO types are relevant based on the query."""
        matched = set()
        for keyword, lo_type in _LO_TYPE_TRIGGERS.items():
            if keyword in query_lower:
                matched.add(lo_type)
        return matched

    # ─── Mining functions ───

    def _mine_recommendations(
        self, query_lower: str, tokens: list[str], expanded: set[str], context: dict
    ) -> list[AutocompleteSuggestion]:
        """Mine active recommendations for suggestions."""
        results = []
        # If the query is just stopwords ("we should", "what is"), surface
        # all recommendations — the user is asking an open question.
        surface_all = not tokens
        for rec in self.decisions.get_recommendations():
            text = (rec.title + " " + rec.description + " " + rec.recommendation).lower()
            # Score by token overlap
            score = self._text_overlap(text, tokens, expanded)
            if not surface_all and score == 0 and query_lower:
                continue

            # Build the completion
            completion = f"We should {rec.recommendation.lower().rstrip('.')}"
            if not query_lower or surface_all or score > 0:
                results.append(AutocompleteSuggestion(
                    completion=completion,
                    query=f"Should we {rec.recommendation.lower().rstrip('.')}?",
                    reason=f"Active recommendation from OEM (urgency: {rec.urgency}). "
                           f"{('Matches ' + str(score) + ' concept(s) in your query.') if score > 0 else 'Surfaced as an open recommendation.'}",
                    expected_outcome=rec.impact or rec.description,
                    confidence=rec.confidence,
                    evidence=self._build_evidence_from_rec(rec),
                    similar_executions=self._find_similar_executions(rec.linked_laws or []),
                    citations=(rec.linked_laws or []) + [rec.rec_id],
                    source_type="recommendation",
                    source_id=rec.rec_id,
                    metadata={
                        "urgency": rec.urgency,
                        "evidence_strength": rec.evidence_strength,
                        "title": rec.title,
                    },
                ))
        return results

    def _mine_laws(
        self, query_lower: str, tokens: list[str], expanded: set[str], context: dict
    ) -> list[AutocompleteSuggestion]:
        """Mine laws for suggestions."""
        results = []
        surface_all = not tokens
        for law in self.model.laws.values():
            text = (law.statement + " " + law.condition + " " + law.outcome).lower()
            score = self._text_overlap(text, tokens, expanded)
            if not surface_all and score == 0 and query_lower:
                continue

            completion = f"We should respect {law.code}: {law.statement[:80]}"
            if not query_lower or surface_all or score > 0:
                results.append(AutocompleteSuggestion(
                    completion=completion,
                    query=f"What does {law.code} say?",
                    reason=f"Organizational law {law.code} (status: {law.status.value if hasattr(law.status, 'value') else law.status}). "
                           f"Validated {law.validated_runtimes} times across {len(law.providers)} providers.",
                    expected_outcome=f"If {law.condition}, then {law.outcome}",
                    confidence=law.confidence,
                    evidence=self._build_evidence_from_law(law),
                    similar_executions=self._find_similar_executions([law.code]),
                    citations=[law.code] + (law.pattern_ids or []),
                    source_type="law",
                    source_id=law.code,
                    metadata={
                        "status": law.status.value if hasattr(law.status, "value") else str(law.status),
                        "validated_runtimes": law.validated_runtimes,
                        "failed_runtimes": law.failed_runtimes,
                        "evidence_count": law.evidence_count,
                        "providers": list(law.providers or []),
                    },
                ))
        return results

    def _mine_learning_objects(
        self, query_lower: str, tokens: list[str], expanded: set[str],
        lo_types: set[str], context: dict
    ) -> list[AutocompleteSuggestion]:
        """Mine learning objects for suggestions."""
        results = []
        surface_all = not tokens and not lo_types
        for lo in self.model.learning_objects.values():
            lo_type = lo.type.value if hasattr(lo.type, "value") else str(lo.type)
            # Match by type trigger or by text overlap
            type_match = lo_type in lo_types
            text = (lo.title + " " + lo.description).lower()
            score = self._text_overlap(text, tokens, expanded)
            if not surface_all and not type_match and score == 0 and query_lower:
                continue

            # Build completion based on LO type
            completion = self._build_lo_completion(lo, lo_type)
            reason = self._build_lo_reason(lo, lo_type, score, type_match)
            expected = self._build_lo_outcome(lo, lo_type)

            results.append(AutocompleteSuggestion(
                completion=completion,
                query=self._build_lo_query(lo, lo_type),
                reason=reason,
                expected_outcome=expected,
                confidence=lo.confidence,
                evidence=self._build_evidence_from_lo(lo),
                similar_executions=[],
                citations=[lo.lo_id] + (lo.entities or []),
                source_type=f"lo:{lo_type}",
                source_id=str(lo.lo_id),
                metadata={
                    "type": lo_type,
                    "entities": lo.entities,
                    "evidence_count": lo.evidence_count,
                    "providers": list(lo.providers or []),
                },
            ))
        return results

    def _mine_experts(
        self, query_lower: str, tokens: list[str], expanded: set[str], context: dict
    ) -> list[AutocompleteSuggestion]:
        """Mine hidden experts from the knowledge graph."""
        results = []
        for expert in self.model.knowledge.get_hidden_experts():
            entity = expert.get("entity", "")
            domains = expert.get("domains", [])
            influence = expert.get("influence", 0.0)
            text = (entity + " " + " ".join(domains)).lower()
            score = self._text_overlap(text, tokens, expanded)
            # If query mentions "who" or "expert", surface all experts
            if score == 0 and not any(w in query_lower for w in ("who", "expert", "know")):
                continue

            domain_str = domains[0] if domains else "this domain"
            results.append(AutocompleteSuggestion(
                completion=f"We should consult {entity} about {domain_str}",
                query=f"Who knows the most about {domain_str}?",
                reason=f"{entity} is a hidden expert with influence {influence:.2f} "
                       f"across {len(domains)} domain(s). Not formally recognized but "
                       f"consistently referenced in {expert.get('evidence_count', 0)} signals.",
                expected_outcome=f"Consulting {entity} on {domain_str} will surface "
                                 f"organizational knowledge not captured in formal roles.",
                confidence=min(1.0, influence / 2.0),
                evidence=[{
                    "type": "expert_profile",
                    "entity": entity,
                    "influence": round(influence, 4),
                    "domains": domains,
                }],
                similar_executions=[],
                citations=[entity] + domains,
                source_type="expert",
                source_id=entity,
                metadata={
                    "influence": round(influence, 4),
                    "domains": domains,
                },
            ))
        return results

    def _mine_risks(
        self, query_lower: str, tokens: list[str], expanded: set[str], context: dict
    ) -> list[AutocompleteSuggestion]:
        """Mine concentration risks."""
        results = []
        for domain, score_val in self.model.knowledge.get_concentration_risk().items():
            text = domain.lower()
            score = self._text_overlap(text, tokens, expanded)
            if score == 0 and not any(w in query_lower for w in ("risk", "concentration", "exposure")):
                continue

            results.append(AutocompleteSuggestion(
                completion=f"We should address the concentration risk in {domain}",
                query=f"What are the concentration risks in {domain}?",
                reason=f"Domain '{domain}' has a concentration score of {score_val:.2f}, "
                       f"indicating knowledge is held by too few people.",
                expected_outcome=f"Reducing concentration in {domain} will lower "
                                 f"bus-factor risk and improve resilience.",
                confidence=min(1.0, score_val / 10.0),
                evidence=[{
                    "type": "concentration_risk",
                    "domain": domain,
                    "score": round(score_val, 4),
                }],
                similar_executions=[],
                citations=[domain],
                source_type="risk",
                source_id=f"risk:{domain}",
                metadata={"domain": domain, "score": round(score_val, 4)},
            ))
        return results

    def _mine_evidence_graph(
        self, query_lower: str, tokens: list[str], expanded: set[str], context: dict
    ) -> list[AutocompleteSuggestion]:
        """Mine the evidence graph for related patterns."""
        results = []
        # Look for nodes whose labels match the query
        for node_id, node in list(self.graph.nodes.items())[:200]:  # Cap for perf
            label = (node.label or "").lower()
            if not label:
                continue
            score = self._text_overlap(label, tokens, expanded)
            if score == 0:
                continue

            node_type = node_id.split(":")[0] if ":" in node_id else "unknown"
            neighbor_count = len(self._adjacency.get(node_id, []))
            results.append(AutocompleteSuggestion(
                completion=f"We should investigate: {node.label}",
                query=f"What is the evidence for {node.label}?",
                reason=f"Evidence graph node of type '{node_type}'. "
                       f"Connected to {neighbor_count} other entities.",
                expected_outcome=f"Tracing the evidence chain for {node.label} will "
                                 f"reveal the signal provenance.",
                confidence=0.5,
                evidence=[{
                    "type": "evidence_node",
                    "node_id": node_id,
                    "label": node.label,
                    "node_type": node_type,
                    "connected_count": neighbor_count,
                }],
                similar_executions=[],
                citations=[node_id],
                source_type="evidence",
                source_id=node_id,
                metadata={"node_type": node_type},
            ))
        return results[:5]  # Cap evidence-graph suggestions

    # ─── Ranking ───

    def _rank(
        self, candidates: list[AutocompleteSuggestion], context: dict[str, Any]
    ) -> list[AutocompleteSuggestion]:
        """Rank candidates by composite score: recency + authority + outcome + feedback."""

        # Get max influence for normalization
        max_influence = max(
            (self.model.knowledge.influence.get(e, 0.0)
             for e in self.model.knowledge.expertise),
            default=1.0,
        ) or 1.0

        for c in candidates:
            # Base score from confidence
            base = c.confidence

            # Recency: use the most recent evidence timestamp
            recency = self._recency_score(c)

            # Authority: for experts, use influence; for laws, use evidence_count
            authority = self._authority_score(c, max_influence)

            # Outcome: for laws, use validated_runtimes ratio
            outcome = self._outcome_score(c)

            # Feedback: agreed → boost, rejected → penalize
            feedback = self._feedback_score(c)

            # Context boost: if the suggestion's source was recently viewed, boost
            context_boost = self._context_score(c, context)

            # Composite (weights sum to ~1.0)
            c.rank_score = (
                base * 0.25
                + recency * 0.20
                + authority * 0.15
                + outcome * 0.20
                + feedback * 0.15
                + context_boost * 0.05
            )

        return sorted(candidates, key=lambda c: c.rank_score, reverse=True)

    def _recency_score(self, c: AutocompleteSuggestion) -> float:
        """Score based on how recent the evidence is. 0.0–1.0."""
        # Try to find the most recent timestamp in the evidence
        latest: datetime | None = None
        for ev in c.evidence:
            ts = ev.get("timestamp")
            if ts:
                try:
                    if isinstance(ts, str):
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    else:
                        dt = ts
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if latest is None or dt > latest:
                        latest = dt
                except (ValueError, TypeError):
                    pass

        if latest is None:
            return 0.3  # Neutral if no timestamp

        # 90-day half-life: evidence older than 90 days scores 0.5, older than 1 year scores ~0.25
        age_days = (self._now - latest).days
        if age_days <= 0:
            return 1.0
        return max(0.1, 0.5 ** (age_days / 90.0))

    @staticmethod
    def _authority_score(c: AutocompleteSuggestion, max_influence: float) -> float:
        """Score based on entity authority. 0.0–1.0."""
        if c.source_type == "expert":
            influence = c.metadata.get("influence", 0.0)
            return min(1.0, influence / max(max_influence, 0.01))
        if c.source_type == "law":
            # Laws with more evidence are more authoritative
            ec = c.metadata.get("evidence_count", 0)
            return min(1.0, ec / 20.0)
        if c.source_type == "recommendation":
            return c.metadata.get("evidence_strength", 0.5)
        if c.source_type.startswith("lo:"):
            ec = c.metadata.get("evidence_count", 0)
            return min(1.0, ec / 10.0)
        return 0.4

    @staticmethod
    def _outcome_score(c: AutocompleteSuggestion) -> float:
        """Score based on validated outcomes. 0.0–1.0."""
        if c.source_type == "law":
            vr = c.metadata.get("validated_runtimes", 0)
            fr = c.metadata.get("failed_runtimes", 0)
            total = vr + fr
            if total == 0:
                return 0.3
            return vr / total
        if c.source_type == "recommendation":
            return c.confidence
        return 0.4

    def _feedback_score(self, c: AutocompleteSuggestion) -> float:
        """Score based on contradiction feedback. 0.0–1.0.

        Uses the ContradictionLog to learn from past feedback:
          - AGREE → boost (up to 1.0)
          - REJECT → penalize (down to 0.0)
          - MODIFY → neutral (0.5)
          - No feedback → neutral (0.5)
        """
        agree_count = 0
        reject_count = 0
        for eid in [c.source_id] + c.citations:
            fb = self._feedback_index.get(str(eid), (0, 0))
            agree_count += fb[0]
            reject_count += fb[1]

        total = agree_count + reject_count
        if total == 0:
            return 0.5  # Neutral

        # Weighted: agree boosts, reject penalizes
        return max(0.0, min(1.0, 0.5 + (agree_count - reject_count) / max(total, 1)))

    @staticmethod
    def _context_score(c: AutocompleteSuggestion, context: dict[str, Any]) -> float:
        """Boost score if the suggestion is contextually relevant to the current screen."""
        surface = context.get("surface", "")
        # If we're on the "physics" surface, boost law suggestions
        if surface == "physics" and c.source_type == "law":
            return 1.0
        if surface == "hayek" and c.source_type == "expert":
            return 1.0
        if surface == "inbox" and c.source_type == "recommendation":
            return 1.0
        return 0.5

    # ─── Feedback learning ───

    def _build_feedback_index(self) -> dict[str, tuple[int, int]]:
        """Build an index: entity_id → (agree_count, reject_count).

        Uses the contradiction log to learn from past feedback.
        """
        index: dict[str, tuple[int, int]] = {}
        if not self.contradiction_log:
            return index

        # The contradiction log stores ContradictionEvents
        events = getattr(self.contradiction_log, "events", [])
        if not events and hasattr(self.contradiction_log, "_events"):
            events = self.contradiction_log._events

        from maestro_oem.contradiction import FeedbackAction
        for event in events:
            target_id = getattr(event, "target_id", "")
            action = getattr(event, "action", None)
            if not target_id or not action:
                continue

            agree = 1 if action == FeedbackAction.AGREE else 0
            reject = 1 if action == FeedbackAction.REJECT else 0

            current = index.get(str(target_id), (0, 0))
            index[str(target_id)] = (current[0] + agree, current[1] + reject)

            # Also index affected laws
            for law_code in getattr(event, "affected_laws", []):
                current = index.get(str(law_code), (0, 0))
                index[str(law_code)] = (current[0] + agree, current[1] + reject)

        return index

    # ─── Text matching ───

    @staticmethod
    def _text_overlap(text: str, tokens: list[str], expanded: set[str]) -> int:
        """Count how many query tokens (or their expanded concepts) appear in text."""
        if not tokens:
            return 0
        count = 0
        for token in tokens:
            if token in text:
                count += 2  # Direct match is worth 2
        for concept in expanded:
            if concept in text and concept not in tokens:
                count += 1  # Expanded match is worth 1
        return count

    # ─── Evidence builders ───

    def _build_evidence_from_rec(self, rec) -> list[dict[str, Any]]:
        """Build evidence list from a recommendation."""
        evidence = []
        # Linked laws
        for code in (rec.linked_laws or [])[:3]:
            law = self.model.laws.get(code)
            if law:
                evidence.append({
                    "type": "law",
                    "code": law.code,
                    "statement": law.statement[:120],
                    "confidence": round(law.confidence, 4),
                    "timestamp": law.last_validated or law.first_inferred,
                })
        # Provenance chain
        for p in (rec.provenance or [])[:3]:
            evidence.append({
                "type": "provenance",
                "label": p.get("oem_change") or p.get("gate") or p.get("entity") or "evidence",
                "provider": p.get("provider", ""),
            })
        return evidence

    def _build_evidence_from_law(self, law) -> list[dict[str, Any]]:
        """Build evidence list from a law."""
        evidence = []
        # Sample signals that fed this law
        signal_ids = law.signal_ids or []
        for sig_id in signal_ids[:5]:
            sig = self._find_signal(str(sig_id))
            if sig:
                evidence.append({
                    "type": "signal",
                    "signal_id": str(sig.signal_id),
                    "signal_type": sig.type.value if hasattr(sig.type, "value") else str(sig.type),
                    "actor": sig.actor,
                    "artifact": sig.artifact,
                    "provider": sig.provider.value if hasattr(sig.provider, "value") else str(sig.provider),
                    "timestamp": sig.timestamp.isoformat() if hasattr(sig.timestamp, "isoformat") else str(sig.timestamp),
                })
        # Patterns
        for pid in (law.pattern_ids or [])[:2]:
            evidence.append({
                "type": "pattern",
                "pattern_id": str(pid),
            })
        return evidence

    def _build_evidence_from_lo(self, lo) -> list[dict[str, Any]]:
        """Build evidence list from a learning object."""
        evidence = []
        signal_ids = lo.signal_ids or []
        for sig_id in signal_ids[:3]:
            sig = self._find_signal(str(sig_id))
            if sig:
                evidence.append({
                    "type": "signal",
                    "signal_id": str(sig.signal_id),
                    "signal_type": sig.type.value if hasattr(sig.type, "value") else str(sig.type),
                    "actor": sig.actor,
                    "timestamp": sig.timestamp.isoformat() if hasattr(sig.timestamp, "isoformat") else str(sig.timestamp),
                })
        evidence.append({
            "type": "learning_object",
            "lo_id": str(lo.lo_id),
            "title": lo.title,
            "evidence_count": lo.evidence_count,
        })
        return evidence

    def _find_signal(self, sig_id: str):
        """Find a signal by ID from the signals list."""
        for sig in self.signals:
            if str(sig.signal_id) == sig_id:
                return sig
        return None

    def _find_similar_executions(self, law_codes: list[str]) -> list[dict[str, Any]]:
        """Find past executions (signals) that relate to the given laws."""
        similar = []
        for law_code in law_codes:
            law = self.model.laws.get(law_code)
            if not law:
                continue
            # Sample a few signals
            for sig_id in (law.signal_ids or [])[:2]:
                sig = self._find_signal(str(sig_id))
                if sig:
                    similar.append({
                        "law_code": law_code,
                        "signal_type": sig.type.value if hasattr(sig.type, "value") else str(sig.type),
                        "actor": sig.actor,
                        "artifact": sig.artifact,
                        "timestamp": sig.timestamp.isoformat() if hasattr(sig.timestamp, "isoformat") else str(sig.timestamp),
                        "outcome": "validated" if law.validated_runtimes > 0 else "unknown",
                    })
        return similar

    # ─── Completion builders ───

    @staticmethod
    def _build_lo_completion(lo, lo_type: str) -> str:
        """Build a natural-language completion for an LO."""
        title = lo.title or lo_type
        if lo_type == "bottleneck":
            entity = lo.entities[0] if lo.entities else "someone"
            return f"We should address the bottleneck: {entity}"
        if lo_type == "hidden_expert":
            entity = lo.entities[0] if lo.entities else "an expert"
            return f"We should recognize {entity} as a domain expert"
        if lo_type == "departure_risk":
            entity = lo.entities[0] if lo.entities else "someone"
            return f"We should retain {entity} — departure risk detected"
        if lo_type == "duplicate_work":
            return f"We should eliminate duplicate work: {title[:60]}"
        if lo_type == "knowledge_death":
            return f"We should document before knowledge is lost: {title[:60]}"
        if lo_type == "approval_gate":
            entity = lo.entities[0] if lo.entities else "the approver"
            return f"We should streamline approvals through {entity}"
        if lo_type == "incident_pattern":
            return f"We should prevent recurring incidents: {title[:60]}"
        if lo_type == "velocity_drop":
            return f"We should investigate the velocity drop: {title[:60]}"
        # Customer Judgment Engine LO types — judgment, not investigation
        if lo_type == "customer_committee_role":
            customer = lo.metadata.get("customer", "this customer")
            contact = lo.metadata.get("contact", "a contact")
            role = lo.metadata.get("role", "a role")
            return f"We should engage {contact} ({role}) at {customer} — committee signal detected"
        if lo_type == "customer_commitment":
            customer = lo.metadata.get("customer", "this customer")
            commitment = lo.metadata.get("commitment", "a commitment")
            status = lo.metadata.get("status", "open")
            if status == "broken":
                return f"We should repair trust with {customer} — broken commitment: {commitment[:50]}"
            if status == "kept":
                return f"We should leverage the kept commitment to {customer}: {commitment[:50]}"
            return f"We should fulfill our commitment to {customer}: {commitment[:50]}"
        if lo_type == "customer_drift":
            customer = lo.metadata.get("customer", "this customer")
            contact = lo.metadata.get("contact", "the champion")
            return f"We should re-engage {contact} at {customer} — drift signal detected"
        if lo_type == "customer_risk":
            customer = lo.metadata.get("customer", "this customer")
            obj_type = lo.metadata.get("objection_type", "a risk")
            return f"We should address the {obj_type} concern raised by {customer}"
        if lo_type == "customer_decision_pattern":
            customer = lo.metadata.get("customer", "this customer")
            outcome = lo.metadata.get("outcome", "a decision")
            return f"We should learn from {customer}'s decision: {outcome}"
        return f"We should address: {title[:60]}"

    @staticmethod
    def _build_lo_reason(lo, lo_type: str, score: int, type_match: bool) -> str:
        """Build a reason string for an LO suggestion."""
        parts = [f"Learning object of type '{lo_type}'"]
        if type_match:
            parts.append("matched by concept type")
        if score > 0:
            parts.append(f"matched {score} concept(s) in your query")
        parts.append(f"with {lo.evidence_count} evidence signals")
        if lo.entities:
            parts.append(f"involving: {', '.join(lo.entities[:3])}")
        return ". ".join(parts) + "."

    @staticmethod
    def _build_lo_outcome(lo, lo_type: str) -> str:
        """Build an expected outcome string for an LO."""
        return lo.description or f"Addressing this {lo_type} will improve organizational execution."

    @staticmethod
    def _build_lo_query(lo, lo_type: str) -> str:
        """Build the query to execute when this suggestion is selected."""
        title = lo.title or lo_type
        return f"Tell me about: {title[:80]}"
