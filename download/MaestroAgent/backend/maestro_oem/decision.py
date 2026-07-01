"""
DecisionEngine — produces recommendations from the OEM.

This is the layer between the ExecutionModel and the UI.
It reads the model and generates decision recommendations
with full provenance chains.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from maestro_oem.confidence import ConfidenceCalculator
from maestro_oem.model import ExecutionModel
from maestro_oem.signal import SignalProvider


class Recommendation(BaseModel):
    """A decision recommendation with provenance."""
    rec_id: str = Field(default_factory=lambda: f"rec-{uuid4().hex[:8]}")
    title: str
    description: str
    recommendation: str  # "approve", "reject", "defer"
    confidence: float
    decision_question: str  # The DQ this answers
    provenance: list[dict[str, Any]] = Field(default_factory=list)
    linked_laws: list[str] = Field(default_factory=list)
    impact: str = ""  # Business impact description
    urgency: str = "normal"  # "urgent", "normal", "low"
    # Evidence graph fields
    evidence_chain: dict[str, Any] | None = None  # Full traversable chain
    supporting_artifacts: list[dict[str, Any]] = Field(default_factory=list)
    contradicting_artifacts: list[dict[str, Any]] = Field(default_factory=list)
    evidence_strength: float = 0.0  # 0..1, computed from graph traversal


class DecisionEngine:
    """
    Generates recommendations from the OEM.

    The engine reads the model's state and produces actionable
    recommendations. Every recommendation traces back to evidence.

    When an EvidenceGraph is provided, recommendations include:
    - Full evidence chain (traversable)
    - Supporting artifacts
    - Contradicting artifacts
    - Evidence strength (0..1)
    """

    def __init__(self, model: ExecutionModel, evidence_graph: Any = None) -> None:
        self.model = model
        self.evidence_graph = evidence_graph

    def get_recommendations(self) -> list[Recommendation]:
        """Get all active recommendations."""
        recs: list[Recommendation] = []

        # 1. Bottleneck recommendations
        recs.extend(self._bottleneck_recommendations())

        # 2. Hidden expert recommendations
        recs.extend(self._hidden_expert_recommendations())

        # 3. Concentration risk recommendations
        recs.extend(self._concentration_risk_recommendations())

        # 4. Incident velocity recommendations
        recs.extend(self._incident_velocity_recommendations())

        # 5. Departure risk recommendations
        recs.extend(self._departure_risk_recommendations())

        # Enrich with evidence chains if graph is available
        if self.evidence_graph:
            for rec in recs:
                self._enrich_with_evidence(rec)

        return recs

    def _enrich_with_evidence(self, rec: Recommendation) -> None:
        """Attach evidence chain, supporting/contradicting artifacts, and strength."""
        rec_node_id = f"rec:{rec.rec_id}"
        chain = self.evidence_graph.traverse(rec_node_id)

        # If rec node not in graph, try traversing from linked laws
        if not chain.nodes and rec.linked_laws:
            for law_code in rec.linked_laws:
                law_chain = self.evidence_graph.traverse(f"law:{law_code}")
                if law_chain.nodes:
                    chain = law_chain
                    break

        rec.evidence_chain = chain.to_display()
        rec.supporting_artifacts = chain.supporting_artifacts
        rec.contradicting_artifacts = chain.contradicting_artifacts
        rec.evidence_strength = chain.strength

    def _bottleneck_recommendations(self) -> list[Recommendation]:
        recs: list[Recommendation] = []
        bottlenecks = self.model.approvals.get_bottlenecks(min_count=3)
        for bn in bottlenecks:
            gate = bn["gate"]
            count = bn["items_gated"]
            # Confidence from evidence count + linked laws
            linked_laws = [l for l in self.model.laws.values() if gate in l.statement]
            linked_confidences = [l.confidence for l in linked_laws]
            # Gather evidence from LOs that mention this gate
            evidence_count = sum(1 for lo in self.model.learning_objects.values()
                                if lo.type.value == "approval_gate" and gate in lo.entities)
            providers = set()
            for lo in self.model.learning_objects.values():
                if gate in lo.entities:
                    providers.update(lo.providers)
            from datetime import datetime, timezone
            confidence_expl = ConfidenceCalculator.compute_recommendation_confidence(
                evidence_count=max(evidence_count, count),
                contradiction_count=0,
                providers=providers or {"jira"},
                linked_law_confidences=linked_confidences,
                last_seen=datetime.now(timezone.utc),
            )
            confidence = confidence_expl.value
            provenance = self.model.get_provenance_chain(gate)
            recs.append(Recommendation(
                title=f"Address bottleneck: {gate} gates {count} items",
                description=f"{gate} has become an approval bottleneck — {count} items gated, average delay {bn.get('avg_delay_days', 0):.1f} days.",
                recommendation="Redesign or redistribute the approval gate",
                confidence=confidence,
                decision_question="Is this approval gate a VP-level function or a process function?",
                provenance=provenance or [{"oem_change": "bottleneck.detected", "gate": gate, "count": count, "confidence_formula": confidence_expl.formula}],
                linked_laws=[l.code for l in linked_laws],
                impact=f"Resolving this gate could unblock {count} in-flight items",
                urgency="normal" if count < 5 else "urgent",
            ))
        return recs

    def _hidden_expert_recommendations(self) -> list[Recommendation]:
        recs: list[Recommendation] = []
        experts = self.model.knowledge.get_hidden_experts()
        for expert in experts[:3]:
            entity = expert["entity"]
            influence = expert["influence"]
            # Confidence from influence score (normalized) + evidence count
            # Influence is already a count of signals — use it as evidence count
            evidence_count = int(influence)
            providers = set()
            for lo in self.model.learning_objects.values():
                if entity in lo.entities:
                    providers.update(lo.providers)
            from datetime import datetime, timezone
            confidence_expl = ConfidenceCalculator.compute_recommendation_confidence(
                evidence_count=evidence_count,
                contradiction_count=0,
                providers=providers or {"github"},
                linked_law_confidences=[],
                last_seen=datetime.now(timezone.utc),
            )
            confidence = confidence_expl.value
            provenance = self.model.get_provenance_chain(entity)
            recs.append(Recommendation(
                title=f"Formalize hidden expert: {entity}",
                description=f"{entity} has high influence ({influence:.1f}) but no documented expertise. Touches {len(expert['domains'])} domains.",
                recommendation="Document expertise and consider formal role",
                confidence=confidence,
                decision_question=f"Should {entity}'s influence be formalized?",
                provenance=provenance or [{"oem_change": "hidden_expert.detected", "entity": entity, "influence": influence, "confidence_formula": confidence_expl.formula}],
                impact=f"Departure would degrade outcomes in {len(expert['domains'])} domains",
                urgency="normal",
            ))
        return recs

    def _concentration_risk_recommendations(self) -> list[Recommendation]:
        recs: list[Recommendation] = []
        risks = self.model.knowledge.get_concentration_risk()
        for domain, score in risks.items():
            # Confidence from the influence score of the single holder
            # score IS the influence — higher = more risk = more confidence in the risk
            evidence_count = int(score) if score > 0 else 1
            from datetime import datetime, timezone
            confidence_expl = ConfidenceCalculator.compute_recommendation_confidence(
                evidence_count=evidence_count,
                contradiction_count=0,
                providers={"github"},
                linked_law_confidences=[],
                last_seen=datetime.now(timezone.utc),
            )
            confidence = confidence_expl.value
            recs.append(Recommendation(
                title=f"Bus-factor risk in {domain}",
                description=f"Knowledge in {domain} is concentrated in one person. No redundancy.",
                recommendation="Cross-train or document critical knowledge",
                confidence=confidence,
                decision_question=f"What happens if the {domain} expert leaves?",
                provenance=[{"oem_change": "concentration_risk.detected", "domain": domain, "influence": score, "confidence_formula": confidence_expl.formula}],
                impact=f"Loss of this person would create a knowledge gap in {domain}",
                urgency="urgent" if score > 10 else "normal",
            ))
        return recs

    def _incident_velocity_recommendations(self) -> list[Recommendation]:
        recs: list[Recommendation] = []
        if self.model.health.p1_cluster_risk > 0.4:
            # Confidence from the P1 cluster risk itself (already computed from incident count)
            # plus evidence from incident LOs
            evidence_count = int(self.model.health.incident_rate)
            linked_laws = [l for l in self.model.laws.values() if "velocity" in l.statement.lower()]
            linked_confidences = [l.confidence for l in linked_laws]
            from datetime import datetime, timezone
            confidence_expl = ConfidenceCalculator.compute_recommendation_confidence(
                evidence_count=max(evidence_count, 1),
                contradiction_count=0,
                providers={"jira"},
                linked_law_confidences=linked_confidences,
                last_seen=datetime.now(timezone.utc),
            )
            confidence = confidence_expl.value
            recs.append(Recommendation(
                title=f"P1 cluster risk: {self.model.health.p1_cluster_risk:.0%} probability of velocity drop",
                description=f"{self.model.health.incident_rate:.0f} incidents detected. Velocity drop predicted.",
                recommendation="Pause non-critical work and address incident cluster",
                confidence=confidence,
                decision_question="Should we delay the next release to address the incident cluster?",
                provenance=[{"oem_change": "p1_cluster_risk.computed", "risk": self.model.health.p1_cluster_risk, "confidence_formula": confidence_expl.formula}],
                linked_laws=[l.code for l in linked_laws],
                impact="Velocity predicted to drop 22% in the following week",
                urgency="urgent",
            ))
        return recs

    def _departure_risk_recommendations(self) -> list[Recommendation]:
        recs: list[Recommendation] = []
        for entity, prob in self.model.risks.departure_risks.items():
            if prob > 0.5:
                recs.append(Recommendation(
                    title=f"Departure risk: {entity} (P={prob:.0%})",
                    description=f"Signals indicate {entity} may leave within 30 days.",
                    recommendation="Initiate retention conversation and knowledge transfer",
                    confidence=prob,
                    decision_question=f"Should we prioritize retention of {entity}?",
                    provenance=[{"oem_change": "departure_risk.detected", "entity": entity, "probability": prob}],
                    impact=f"Loss of {entity} would degrade outcomes in their domains",
                    urgency="urgent",
                ))
        return recs

    def answer_question(self, question: str) -> dict[str, Any]:
        """
        Answer a natural-language question using the OEM.

        This is the "Ask the Organization" backend.

        V8 Competitor Analysis Feature B — Semantic Ask. The previous
        algorithm was lexical keyword search (MIN_WORD_OVERLAP=2), which
        had a known bug: a question sharing a common word with an
        unrelated law would surface that law as "relevant evidence."
        The new algorithm uses character n-gram TF-IDF with cosine
        similarity via the SemanticMatcher. This captures morphological
        variants ("hire" ≈ "hiring" ≈ "hired"), weights by term rarity
        (TF-IDF), and produces a continuous relevance score.

        The SemanticMatcher interface is designed so a real embedding
        model (Ollama, OpenAI) can replace the TF-IDF backend in
        production without changing any calling code.
        """
        from maestro_oem.semantic_matcher import build_semantic_matcher

        matcher = build_semantic_matcher(self.model)
        q_lower = question.lower()

        # ─── Semantic search for relevant laws ───
        law_candidates: list[tuple[str, dict[str, Any]]] = []
        for law in self.model.laws.values():
            law_text = f"{law.statement} {law.condition} {law.outcome}"
            law_data = {
                "code": law.code,
                "statement": law.statement,
                "confidence": law.confidence,
                "status": law.status.value if law.status else "unknown",
                "evidence_count": law.evidence_count,
                "provenance": self.model.get_provenance_chain(law.code),
                "text": law_text,
            }
            law_candidates.append((law_text, law_data))

        ranked_laws = matcher.rank(question, law_candidates)
        relevant_laws = []
        for score, law_data in ranked_laws[:5]:
            law_data["relevance"] = round(score, 3)
            relevant_laws.append(law_data)

        # ─── Semantic search for relevant learning objects ───
        lo_candidates: list[tuple[str, dict[str, Any]]] = []
        for lo in self.model.learning_objects.values():
            lo_text = f"{lo.title} {lo.description}"
            lo_data = {
                "type": lo.type.value if hasattr(lo.type, "value") else str(lo.type),
                "title": lo.title,
                "confidence": lo.confidence,
                "evidence_count": lo.evidence_count,
                "providers": list(lo.providers),
                "text": lo_text,
            }
            lo_candidates.append((lo_text, lo_data))

        ranked_los = matcher.rank(question, lo_candidates)
        relevant_los = []
        for score, lo_data in ranked_los[:5]:
            lo_data["relevance"] = round(score, 3)
            relevant_los.append(lo_data)

        # Search for hidden experts (still keyword-based — names are exact)
        experts = self.model.knowledge.get_hidden_experts()
        relevant_experts = [e for e in experts if any(word in e["entity"].lower() for word in q_lower.split())]

        # Search for bottlenecks (still keyword-based — names are exact)
        bottlenecks = self.model.approvals.get_bottlenecks()
        relevant_bottlenecks = [b for b in bottlenecks if any(word in b["gate"].lower() for word in q_lower.split())]

        # Build answer
        has_evidence = relevant_laws or relevant_los or relevant_experts or relevant_bottlenecks

        if not has_evidence:
            return {
                "answer": "I don't have enough evidence to answer this question. Try connecting more signal sources, or ask about a different topic.",
                "confidence": 0.0,
                "sources": [],
                "evidence_path": [],
            }

        # Synthesize answer
        answer_parts: list[str] = []
        sources: list[str] = []
        evidence_path: list[dict[str, Any]] = []

        if relevant_laws:
            answer_parts.append(f"Based on {len(relevant_laws)} relevant execution law(s):")
            for law in relevant_laws[:3]:
                answer_parts.append(f"• {law['code']}: {law['statement']} (confidence: {law['confidence']:.2f})")
                sources.extend(law.get("provenance", []))
                evidence_path.append({"type": "law", "code": law["code"], "confidence": law["confidence"]})

        if relevant_los:
            answer_parts.append(f"\nEvidence from {len(relevant_los)} learning object(s):")
            for lo in relevant_los[:3]:
                answer_parts.append(f"• {lo['title']} (confidence: {lo['confidence']:.2f}, providers: {', '.join(lo['providers'])})")
                evidence_path.append({"type": "learning_object", "title": lo["title"], "confidence": lo["confidence"]})

        if relevant_experts:
            answer_parts.append(f"\nHidden experts detected:")
            for exp in relevant_experts[:2]:
                answer_parts.append(f"• {exp['entity']} — influence: {exp['influence']:.1f}, domains: {', '.join(exp['domains'])}")
                evidence_path.append({"type": "hidden_expert", "entity": exp["entity"]})

        if relevant_bottlenecks:
            answer_parts.append(f"\nBottlenecks detected:")
            for bn in relevant_bottlenecks[:2]:
                answer_parts.append(f"• {bn['gate']} — {bn['items_gated']} items gated")
                evidence_path.append({"type": "bottleneck", "gate": bn["gate"]})

        # Compute overall confidence from evidence
        all_confidences = [l["confidence"] for l in relevant_laws] + [lo["confidence"] for lo in relevant_los]
        overall_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0.5

        # V8 P0-4 — Synthesized natural-language answer.
        # Instead of just bullet points, produce a 2-3 sentence paragraph
        # that weaves the evidence into a coherent answer. Rule-based for
        # the pilot; LLM in production. The bullet list remains as
        # "evidence_detail" for the user who wants depth.
        synthesized_answer = self._synthesize_answer(
            question, relevant_laws, relevant_los, relevant_experts,
            relevant_bottlenecks, overall_confidence,
        )

        return {
            "answer": synthesized_answer,
            "synthesized_answer": synthesized_answer,
            "evidence_detail": "\n".join(answer_parts),
            "confidence": overall_confidence,
            "sources": sources[:10],
            "evidence_path": evidence_path,
            "laws": relevant_laws,
            "learning_objects": relevant_los,
            "experts": relevant_experts,
            "bottlenecks": relevant_bottlenecks,
        }

    def _synthesize_answer(
        self,
        question: str,
        laws: list[dict[str, Any]],
        los: list[dict[str, Any]],
        experts: list[dict[str, Any]],
        bottlenecks: list[dict[str, Any]],
        confidence: float,
    ) -> str:
        """Synthesize a 2-3 sentence natural-language answer from evidence.

        Rule-based for the pilot. In production, this is where the LLM
        integration happens: pass the ranked evidence to the LLM with a
        prompt that says 'synthesize this evidence into a 3-sentence answer.
        cite the law codes. do not hallucinate.'

        The synthesis cites evidence by name, not just by code. Verified
        laws (verified_by is set) are cited as facts; unverified laws are
        labeled as candidates.
        """
        if not laws and not los and not experts and not bottlenecks:
            return "I don't have enough evidence to answer this question. Try connecting more signal sources, or ask about a different topic."

        parts: list[str] = []

        # Sentence 1: The main finding
        if laws:
            top_law = laws[0]
            statement = top_law.get("statement", "")
            code = top_law.get("code", "")
            is_verified = top_law.get("verified_by") is not None
            trust_label = "verified" if is_verified else "candidate"
            parts.append(
                f"Based on {code} ({trust_label}, confidence {top_law.get('confidence', 0):.0%}), "
                f"{statement[:120]}."
            )
            if len(laws) > 1:
                parts.append(f" This is supported by {len(laws)} additional pattern{'s' if len(laws) > 2 else ''}.")
        elif los:
            top_lo = los[0]
            parts.append(
                f"Evidence from {top_lo.get('title', 'organizational data')[:100]} "
                f"(confidence {top_lo.get('confidence', 0):.0%}) suggests a relevant pattern."
            )
        elif experts:
            exp = experts[0]
            parts.append(f"{exp.get('entity', 'Someone')} is a hidden expert with influence {exp.get('influence', 0):.1f} across {', '.join(exp.get('domains', [])[:3])}.")
        elif bottlenecks:
            bn = bottlenecks[0]
            parts.append(f"{bn.get('gate', 'A process gate')} is bottlenecking {bn.get('items_gated', 0)} items.")

        # Sentence 2: Supporting detail
        if los and laws:
            top_lo = los[0]
            parts.append(f" This aligns with {top_lo.get('title', 'additional evidence')[:80]}.")
        elif experts and (laws or los):
            exp = experts[0]
            parts.append(f" {exp.get('entity', 'A key person')} has relevant expertise but is not formally documented.")
        elif bottlenecks and (laws or los):
            bn = bottlenecks[0]
            parts.append(f" {bn.get('gate', 'A bottleneck')} is gating {bn.get('items_gated', 0)} items.")

        # Sentence 3: Confidence caveat
        if confidence < 0.5:
            parts.append(" This assessment has moderate confidence — more data would improve accuracy.")
        elif confidence < 0.8:
            parts.append(" This assessment is well-supported by organizational evidence.")
        else:
            parts.append(" This assessment is strongly supported by consistent organizational evidence.")

        return "".join(parts)
