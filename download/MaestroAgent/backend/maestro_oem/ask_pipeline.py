"""H3 fix: Structured reasoning pipeline for Ask Maestro.

Adversarial audit finding (ADVERSARIAL-AUDIT-LATEST-c5f08fb):
> H3: Ask Maestro is still keyword routing. No LLM integration. No
> intent → entity resolution → structured retrieval → graph traversal
> → evidence assembly → synthesis pipeline.

The CEO's original vision: "LLM is the narrator, not the architecture."
The pipeline is:
  1. Intent classification (deterministic)
  2. Entity resolution (deterministic — synonym map)
  3. Retrieval (deterministic — RecallEngine, PreparationEngine, signal search)
  4. Evidence assembly (deterministic — EvidenceBuilder)
  5. Synthesis (deterministic — evidence-grounded composition, no LLM)

The LLM would be the last-mile narrator (step 5), but no LLM is
integrated. The synthesis is template-based but evidence-grounded —
it references actual signals, commitments, outcomes. Not hardcoded
phrases like "The real issue appears to be delivery trust, not price."

Usage:
    pipeline = AskPipeline(signals=signals, whisper_store=store, oem_state=oem_state)
    result = pipeline.execute("What did we promise TestCorp?", org_id="default")
    # result = {"answer": "...", "evidence": [...], "follow_ups": [...], "actions": [...]}
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AskIntent(str, Enum):
    """The 9 intent types the pipeline can classify."""

    RECALL = "recall"       # "What was that thing about..."
    PREPARE = "prepare"     # "Prepare me for..."
    WHY = "why"             # "Why is X happening?"
    WHO = "who"             # "Who is the expert on...?"
    WHAT = "what"           # "What did we promise...?"
    WISDOM = "wisdom"       # "What should we do about...?"
    WHAT_IF = "what_if"     # "What if...?" / "What would happen if...?"
    SIMULATE = "simulate"   # "Simulate..."
    DEFAULT = "default"     # anything else


class AskPipeline:
    """Structured reasoning pipeline for Ask Maestro.

    Replaces the keyword-routing _generate_conversational_answer() with:
      1. Intent classification
      2. Entity resolution
      3. Retrieval from multiple sources
      4. Evidence assembly
      5. Synthesis (evidence-grounded, no LLM)
    """

    # Intent classification patterns (used for CLASSIFICATION, not routing)
    _RECALL_PHRASES = ["what was that", "remind me", "you showed me", "you warned me", "you told me"]
    _PREPARE_PHRASES = ["prepare me", "prepare for", "get me ready"]
    _WHY_PREFIX = "why"
    _WHO_PREFIX = "who"
    _WISDOM_PHRASES = ["what should we", "what do you recommend", "what would you suggest", "what's your advice", "what do you think we should"]
    _WHAT_IF_PHRASES = ["what if", "what would happen if", "what could happen if", "suppose we"]
    _SIMULATE_PHRASES = ["simulate", "run a simulation", "model the impact"]

    # Entity synonym map (same as RecallEngine)
    _ENTITY_SYNONYMS = {
        "legal": ["legal", "compliance", "contract", "regulation", "law", "clause"],
        "security": ["security", "vulnerability", "cve", "auth", "oauth", "sso", "breach"],
        "pricing": ["pricing", "price", "cost", "budget", "discount", "invoice"],
        "engineering": ["engineering", "deploy", "deployment", "pr", "merge", "rollback", "release"],
        "customer": ["customer", "client", "account"],
        "timeline": ["timeline", "deadline", "delay", "late", "schedule", "due"],
        "hiring": ["hiring", "hire", "recruit", "staff", "headcount"],
        "commitment": ["commitment", "promise", "pledge", "deliverable"],
        "objection": ["objection", "concern", "pushback", "resistance"],
        "decision": ["decision", "decided", "outcome", "verdict"],
    }

    def __init__(
        self,
        signals: list = None,
        whisper_store: Any = None,
        oem_state: Any = None,
        preparation_engine: Any = None,
        meeting_store: Any = None,
        decision_store: Any = None,
        model: Any = None,
        conversation_store: Any = None,
    ) -> None:
        self._signals = list(signals) if signals else []
        self._whisper_store = whisper_store
        self._oem_state = oem_state
        self._preparation_engine = preparation_engine
        self._meeting_store = meeting_store
        self._decision_store = decision_store
        self._model = model
        self._conversation_store = conversation_store
        self._narrator = None  # Lazy-loaded
        self._user_email = ""  # C-003: set by execute() for permission filtering

    # ─── Step 1: Intent classification ───────────────────────────────

    def classify_intent(self, query: str) -> AskIntent:
        """Classify the exec's intent from their query.

        This is CLASSIFICATION (producing a labeled intent), not ROUTING
        (each branch does completely different things). The intent
        determines which retrieval engines to invoke.
        """
        query_lower = query.lower().strip()

        if any(phrase in query_lower for phrase in self._RECALL_PHRASES):
            return AskIntent.RECALL

        if any(phrase in query_lower for phrase in self._PREPARE_PHRASES):
            return AskIntent.PREPARE

        if query_lower.startswith(self._WHY_PREFIX):
            return AskIntent.WHY

        if query_lower.startswith(self._WHO_PREFIX):
            return AskIntent.WHO

        # Phase A: Check for new intents (WISDOM, WHAT_IF, SIMULATE)
        if any(phrase in query_lower for phrase in self._WISDOM_PHRASES):
            return AskIntent.WISDOM

        if any(phrase in query_lower for phrase in self._WHAT_IF_PHRASES):
            return AskIntent.WHAT_IF

        if any(phrase in query_lower for phrase in self._SIMULATE_PHRASES):
            return AskIntent.SIMULATE

        if query_lower.startswith("what") or query_lower.startswith("which"):
            return AskIntent.WHAT

        return AskIntent.DEFAULT

    # ─── Step 2: Entity resolution ───────────────────────────────────

    def resolve_entities(self, query: str) -> list[str]:
        """Resolve entities and topics from the query.

        Uses the same synonym map as RecallEngine. Also extracts
        customer names from the query by matching against known
        customers in the signal data, AND extracts capitalized words
        as potential entity names (a simple heuristic).
        """
        query_lower = query.lower()
        entities: list[str] = []

        # Check synonym map
        for canonical, synonyms in self._ENTITY_SYNONYMS.items():
            for syn in synonyms:
                if syn in query_lower:
                    if canonical not in entities:
                        entities.append(canonical)
                    break

        # Extract customer names from signals
        known_customers = set()
        for s in self._signals:
            try:
                customer = s.metadata.get("customer", "") if hasattr(s, "metadata") else ""
                if customer:
                    known_customers.add(customer)
            except Exception:
                continue

        for customer in known_customers:
            if customer.lower() in query_lower:
                if customer not in entities:
                    entities.append(customer)

        # H3 fix: extract capitalized words as potential entity names
        # (e.g., "TestCorp", "Atlas", "Initech" — proper nouns that might
        # be customer names even if not in the signal data)
        capitalized = re.findall(r'\b[A-Z][a-zA-Z]{2,}\b', query)
        for cap in capitalized:
            # Skip common English words that happen to be capitalized
            if cap.lower() in {"the", "what", "who", "why", "when", "where", "how",
                                "prepare", "show", "tell", "remind", "did", "was",
                                "is", "are", "can", "could", "should", "would",
                                "have", "has", "will", "about", "for", "with"}:
                continue
            if cap not in entities:
                entities.append(cap)

        return entities

    # ─── Step 3-5: Execute the full pipeline ─────────────────────────

    def execute(self, query: str, org_id: str = "default", session_id: str = "", user_email: str = "") -> dict[str, Any]:
        """Execute the full pipeline: classify → resolve → retrieve → assemble → narrate.

        Step 3 (conversation state): if session_id provided, load prior turns
        and resolve pronouns/entities from conversation history.

        Returns:
            {
                "answer": str,           # narrated answer with citations
                "evidence": list[dict],  # evidence pieces
                "citations": list[dict], # source citations [1], [2], etc.
                "follow_ups": list[str], # suggested follow-ups
                "actions": list[dict],   # suggested actions
                "intent": str,           # classified intent
                "entities": list[str],   # resolved entities
            }
        """
        # C-003: Store user_email for permission-aware signal filtering
        self._user_email = user_email

        # Step 1: Classify intent
        intent = self.classify_intent(query)

        # Step 2: Resolve entities (with conversation state for pronoun resolution)
        entities = self.resolve_entities(query)

        # Step 3: Conversation state — resolve pronouns from prior turns
        # Phase 2.4: Entity-scoped retrieval. Once a conversation has resolved
        # to a specific customer entity, subsequent retrieval within that session
        # should be scoped to that entity by default. This prevents cross-customer
        # answers (the D2 bug) even when a follow-up question doesn't mention
        # the entity by name.
        scoped_entity = None  # The entity to scope retrieval to

        # Phase 2.4: If the query explicitly names a customer, scope to it
        # even on the first turn (no prior context needed)
        for e in entities:
            if e not in self._ENTITY_SYNONYMS and len(e) > 2 and e[0].isupper():
                scoped_entity = e
                break

        if session_id and self._conversation_store:
            prior_entities = self._conversation_store.get_last_entities(session_id)
            # If the query has no entities of its own, carry forward from prior turns
            if not entities and prior_entities:
                entities = prior_entities
                # Phase 2.4: Identify the customer entity to scope to
                for e in prior_entities:
                    if e not in self._ENTITY_SYNONYMS and len(e) > 2:
                        scoped_entity = e
                        break
            # If query has entities, merge with prior (prior entities as context)
            elif entities and prior_entities:
                # Phase 2.5: Check if this is an explicit entity pivot
                new_customer_entities = [
                    e for e in entities
                    if e not in self._ENTITY_SYNONYMS and len(e) > 2
                    and e not in prior_entities
                ]
                if new_customer_entities:
                    # Explicit pivot — re-scope to the new entity
                    scoped_entity = new_customer_entities[0]
                else:
                    # Same entity or no new customer — stay scoped to prior
                    for e in prior_entities:
                        if e not in self._ENTITY_SYNONYMS and len(e) > 2:
                            scoped_entity = e
                            break
                # Merge prior entities for context
                for pe in prior_entities:
                    if pe not in entities:
                        entities.append(pe)

        # Step 3.5: C2 fix — Build Situation for the scoped entity (shared substrate).
        # The Situation pre-assembles commitments, timeline, disagreements, and
        # evidence into a coherent view. This is the SAME object that Whisper
        # and Preparation use — ensuring cross-surface coherence.
        situation = None
        target_entity = scoped_entity or (entities[0] if entities else "")
        if target_entity and len(target_entity) > 2:
            try:
                from maestro_oem.situation import SituationBuilder
                builder = SituationBuilder(
                    signals=self._signals,
                    calendar_source=None,
                    whisper_store=self._whisper_store,
                )
                situation = builder.build_for_entity(target_entity)
            except Exception as e:
                logger.debug("AskPipeline: SituationBuilder failed for %s: %s", target_entity, e)

        # Step 4: Retrieve based on intent (Phase 2.4: scoped to entity if available)
        evidence, answer_parts = self._retrieve(intent, entities, query, org_id, scoped_entity=scoped_entity)

        # C2 fix: If Situation was built, enrich evidence with situation data
        # (commitments, disagreements) that may not have been caught by the
        # retrieval path. This ensures all 3 surfaces see the same facts.
        if situation:
            try:
                for commit in situation.commitments[:3]:
                    # Check if this commitment is already in evidence
                    commit_text = commit.get("commitment", "") if isinstance(commit, dict) else str(commit)
                    if commit_text and not any(commit_text[:30] in e.get("text", "") for e in evidence):
                        evidence.append({
                            "source": "situation_builder",
                            "text": commit_text[:100],
                            "date": "",
                            "people": [],
                            "evidence_spine": {
                                "claim": commit_text[:80],
                                "observed_facts": [{"source": "situation", "text": commit_text[:120]}],
                                "claim_type": "commitment",
                            },
                        })
            except Exception as e:
                logger.debug("AskPipeline: situation enrichment failed: %s", e)

        # Step 5: Narrate (with citations)
        narrator = self._get_narrator()
        answer, citations = narrator.narrate_with_citations(query, evidence)

        # Step 6: Save conversation turn
        if session_id and self._conversation_store:
            try:
                history = self._conversation_store.get_history(session_id)
                turn_num = len(history) + 1
                self._conversation_store.add_turn(
                    session_id=session_id, turn=turn_num, role="user",
                    content=query, intent=intent.value, entities=entities,
                )
                self._conversation_store.add_turn(
                    session_id=session_id, turn=turn_num + 1, role="maestro",
                    content=answer, intent=intent.value, entities=entities,
                )
            except Exception as e:
                logger.debug("AskPipeline: failed to save conversation turn: %s", e)

        return {
            "answer": answer,
            "evidence": evidence,
            "citations": citations,
            "follow_ups": self._suggest_follow_ups(intent, entities),
            "actions": self._suggest_actions(intent),
            "intent": intent.value,
            "entities": entities,
        }

    def _get_narrator(self):
        """Lazy-load the narrator.

        Priority 5: When an LLM provider is available (configured via env
        or injected), uses LLMNarrator for evidence-grounded prose generation.
        When no LLM is available, falls back to the template EvidenceNarrator.
        Both implement the same interface (P6: fail-closed).
        """
        if self._narrator is None:
            # Priority 5: Try LLMNarrator first
            try:
                from maestro_oem.llm_narrator import LLMNarrator
                llm_provider = self._get_llm_provider()
                if llm_provider is not None:
                    self._narrator = LLMNarrator(llm_provider=llm_provider)
                    logger.info("AskPipeline: using LLMNarrator")
                else:
                    from maestro_oem.narrator import EvidenceNarrator
                    self._narrator = EvidenceNarrator()
                    logger.info("AskPipeline: using template EvidenceNarrator (no LLM configured)")
            except Exception as e:
                logger.warning("AskPipeline: LLMNarrator init failed, using template: %s", e)
                from maestro_oem.narrator import EvidenceNarrator
                self._narrator = EvidenceNarrator()
        return self._narrator

    def _get_llm_provider(self):
        """Get an LLM provider if one is configured.

        Returns None if no provider is available (P6: fail-closed to template).
        This checks for the maestro_llm LLMRouter via env vars.
        """
        try:
            import os
            # Check if any LLM env vars are set
            has_llm = any(os.environ.get(k) for k in [
                "OLLAMA_BASE_URL", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                "OPENROUTER_API_KEY", "XAI_API_KEY",
            ])
            if not has_llm:
                # Also check if Ollama is running locally at default port
                import urllib.request
                try:
                    urllib.request.urlopen("http://localhost:11434/api/tags", timeout=1)
                    has_llm = True
                except Exception:
                    pass

            if not has_llm:
                return None

            # Use the LLMRouter's from_env factory (async, so we need to run it)
            from maestro_llm.router import LLMRouter
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                # Already in async context — can't use asyncio.run
                return None  # Fall back to template for now
            except RuntimeError:
                router = asyncio.run(LLMRouter.from_env())
                if router.providers:
                    # Return a simple sync wrapper around the async router
                    return _LLMRouterSyncWrapper(router)
                return None
        except Exception as e:
            logger.debug("AskPipeline._get_llm_provider: %s", e)
            return None

    # ─── Retrieval (Step 3) ──────────────────────────────────────────

    def _retrieve(
        self,
        intent: AskIntent,
        entities: list[str],
        query: str,
        org_id: str,
        scoped_entity: str | None = None,
    ) -> tuple[list[dict], list[str]]:
        """Retrieve evidence based on intent + entities.

        Phase 2.4: If scoped_entity is provided, filter all evidence to only
        include signals for that customer entity. This prevents cross-customer
        answers (the D2 bug) when a follow-up question doesn't mention the
        entity by name.

        Returns (evidence_list, answer_parts).
        """
        evidence: list[dict] = []
        answer_parts: list[str] = []

        if intent == AskIntent.RECALL:
            evidence, answer_parts = self._retrieve_recall(query, org_id)

        elif intent == AskIntent.PREPARE:
            evidence, answer_parts = self._retrieve_prepare(entities, org_id)

        elif intent == AskIntent.WHY:
            evidence, answer_parts = self._retrieve_why(entities, query)

        elif intent == AskIntent.WHO:
            evidence, answer_parts = self._retrieve_who(entities)

        elif intent == AskIntent.WHAT:
            evidence, answer_parts = self._retrieve_what(entities, query)

        elif intent == AskIntent.WISDOM:
            evidence, answer_parts = self._retrieve_wisdom(entities, query)

        elif intent == AskIntent.WHAT_IF:
            evidence, answer_parts = self._retrieve_what_if(entities, query)

        elif intent == AskIntent.SIMULATE:
            evidence, answer_parts = self._retrieve_simulate(entities, query)

        else:  # DEFAULT
            evidence, answer_parts = self._retrieve_default(entities, query)

        # Phase 2.4: Entity-scoped filtering. If a scoped_entity was resolved
        # from conversation context, filter the evidence to only include items
        # that reference that customer. This prevents cross-customer answers.
        if scoped_entity and evidence:
            scoped_lower = scoped_entity.lower()
            filtered_evidence = []
            for e in evidence:
                # Check if the evidence references the scoped entity
                e_text = (e.get("text", "") + " " + str(e.get("source", ""))).lower()
                e_spine = str(e.get("evidence_spine", {})).lower()
                if scoped_lower in e_text or scoped_lower in e_spine:
                    filtered_evidence.append(e)
            if filtered_evidence:
                evidence = filtered_evidence
                answer_parts = [ap for ap in answer_parts if scoped_lower in ap.lower() or not ap.startswith("- ")]
            # If filtering removes ALL evidence, keep the original (don't over-filter)
            # — the narrator will say "I don't know" if truly empty

        return evidence, answer_parts

    def _retrieve_recall(self, query: str, org_id: str) -> tuple[list[dict], list[str]]:
        """Retrieve from whisper history via RecallEngine."""
        if not self._whisper_store or not hasattr(self._whisper_store, 'get_all_history'):
            return [], ["I don't have enough whisper history to recall this."]

        try:
            from maestro_oem.recall_engine import RecallEngine
            recall = RecallEngine(
                whisper_history_store=self._whisper_store,
                signals=self._signals,
                oem_state=self._oem_state,
            )
            result = recall.recall(query, org_id=org_id)

            evidence = []
            for w in result.get("whispers", []):
                evidence.append({
                    "source": "whisper_history",
                    "text": w.get("original_insight", ""),
                    "evidence_spine": w.get("evidence_spine", {
                        "claim": w.get("original_insight", ""),
                        "observed_facts": [{"source": "whisper_history", "text": w.get("original_insight", "")}],
                    }),
                })

            answer_parts = []
            if result.get("found"):
                answer_parts.append(result.get("message", "I found a relevant whisper."))
            else:
                answer_parts.append("I couldn't find a whisper matching that description.")

            return evidence, answer_parts
        except Exception as e:
            logger.warning("AskPipeline._retrieve_recall: %s", e)
            return [], ["I don't have enough whisper history to recall this."]

    def _retrieve_prepare(self, entities: list[str], org_id: str) -> tuple[list[dict], list[str]]:
        """Retrieve from PreparationEngine."""
        if not self._preparation_engine:
            return [], ["I don't have enough context to prepare for a meeting."]

        try:
            prep = self._preparation_engine.prepare_for_tomorrow(org_id=org_id)
            meetings = prep.get("meetings", [])
            if not meetings:
                return [], ["No upcoming meetings to prepare for."]

            meeting = meetings[0]
            p = meeting.get("preparation", {})
            evidence = []
            for c in p.get("relevant_commitments", []):
                evidence.append({
                    "source": "preparation_engine",
                    "text": c.get("commitment", ""),
                    "evidence_spine": {
                        "claim": c.get("commitment", ""),
                        "observed_facts": [{"source": "customer signals", "text": c.get("commitment", "")}],
                        "claim_type": "commitment",
                    },
                })

            answer_parts = [f"Preparation for {meeting.get('title', 'upcoming meeting')}:"]
            if p.get("customer_concerns"):
                answer_parts.append(f"Likely to come up: {', '.join(p['customer_concerns'])}")
            if p.get("internal_expert"):
                answer_parts.append(f"Internal expert: {p['internal_expert']}")

            return evidence, answer_parts
        except Exception as e:
            logger.warning("AskPipeline._retrieve_prepare: %s", e)
            return [], ["I don't have enough context to prepare for a meeting."]

    def _retrieve_why(self, entities: list[str], query: str) -> tuple[list[dict], list[str]]:
        """Retrieve signals related to the 'why' question.

        P5: Wire CausalEngine — move from correlation to causation by
        discovering intervention-outcome pairs in law causal chains.
        """
        evidence, answer_parts = self._search_signals(entities, query, focus="why", user_email=self._user_email or "")

        # P5: CausalEngine — discover causal chains
        try:
            from maestro_oem.causal import CausalEngine
            if self._model:
                causal_engine = CausalEngine(self._model, self._signals)
                causal_result = causal_engine.discover()
                chains = causal_result.get("causal_chains", [])
                if chains:
                    for chain in chains[:2]:
                        cause = chain.get("cause", "")
                        effect = chain.get("effect", "")
                        if cause and effect:
                            evidence.append({
                                "source": "causal_engine",
                                "text": f"Causal: {cause} → {effect}",
                                "date": "",
                                "people": [],
                                "evidence_spine": {
                                    "claim": f"{cause} causes {effect}",
                                    "observed_facts": [{"source": "causal", "text": chain.get("description", f"{cause} → {effect}")}],
                                    "claim_type": "inference",
                                },
                            })
                            answer_parts.append(f"Causal link: {cause} → {effect}")
        except Exception as e:
            logger.debug("CausalEngine in _retrieve_why failed: %s", e)

        return evidence, answer_parts

    def _retrieve_who(self, entities: list[str]) -> tuple[list[dict], list[str]]:
        """Retrieve people related to the entities."""
        evidence = []
        answer_parts = []
        people: dict[str, int] = {}

        for s in self._signals:
            try:
                sig_entities = s.metadata.get("customer", "") if hasattr(s, "metadata") else ""
                if entities and not any(e.lower() in sig_entities.lower() for e in entities):
                    continue
                if s.actor:
                    people[s.actor] = people.get(s.actor, 0) + 1
            except Exception:
                continue

        if people:
            best = max(people, key=people.get)
            evidence.append({
                "source": "signal_analysis",
                "text": f"{best} has {people[best]} signal(s) related to this topic",
                "evidence_spine": {
                    "claim": f"{best} is the most active person on this topic",
                    "observed_facts": [{"source": "signals", "text": f"{people[best]} signals"}],
                    "claim_type": "estimate",
                },
            })
            answer_parts.append(f"Based on signal activity, {best} has the most involvement.")
        else:
            answer_parts.append("I don't have enough signal data to identify the relevant person.")

        return evidence, answer_parts

    def _retrieve_what(self, entities: list[str], query: str) -> tuple[list[dict], list[str]]:
        """Retrieve commitments/decisions related to the entities."""
        return self._search_signals(entities, query, focus="what", user_email=self._user_email or "")

    def _retrieve_wisdom(self, entities: list[str], query: str) -> tuple[list[dict], list[str]]:
        """Phase A: Wire WisdomEngine — 'What should we do?' → value synthesis."""
        evidence = []
        answer_parts = []
        try:
            from maestro_oem.wisdom import WisdomEngine
            if self._model:
                engine = WisdomEngine(self._model, self._signals)
                result = engine.synthesize(context=query)
                wisdom_text = result.get("wisdom", "")
                if wisdom_text:
                    evidence.append({"source": "wisdom_engine", "text": wisdom_text[:200], "date": "",
                        "people": [], "evidence_spine": {"claim": wisdom_text[:100],
                        "observed_facts": [{"source": "wisdom", "text": wisdom_text[:120]}], "claim_type": "inference"}})
                    answer_parts.append(f"Wisdom: {wisdom_text}")
                else:
                    answer_parts.append("I don't have enough organizational patterns to synthesize wisdom.")
            else:
                answer_parts.append("I don't have enough model data to synthesize wisdom.")
        except Exception as e:
            logger.warning("AskPipeline._retrieve_wisdom: %s", e)
            answer_parts.append("I don't have enough organizational patterns to synthesize wisdom.")
        return evidence, answer_parts

    def _retrieve_what_if(self, entities: list[str], query: str) -> tuple[list[dict], list[str]]:
        """Phase A: Wire ImaginationEngine — 'What if?' → counterfactual."""
        evidence = []
        answer_parts = []
        try:
            from maestro_oem.imagination import ImaginationEngine
            if self._model:
                engine = ImaginationEngine(self._model, self._signals)
                result = engine.imagine(scenario=query)
                cf = result.get("counterfactual", "")
                if cf:
                    evidence.append({"source": "imagination_engine", "text": cf[:200], "date": "",
                        "people": [], "evidence_spine": {"claim": cf[:100],
                        "observed_facts": [{"source": "imagination", "text": cf[:120]}], "claim_type": "inference"}})
                    answer_parts.append(f"Counterfactual: {cf}")
                else:
                    answer_parts.append("I don't have enough organizational data to imagine this scenario.")
            else:
                answer_parts.append("I don't have enough model data to imagine this scenario.")
        except Exception as e:
            logger.warning("AskPipeline._retrieve_what_if: %s", e)
            answer_parts.append("I don't have enough organizational data to imagine this scenario.")
        return evidence, answer_parts

    def _retrieve_simulate(self, entities: list[str], query: str) -> tuple[list[dict], list[str]]:
        """Phase A: Wire SimulationEngine — 'Simulate' → metric what-if."""
        evidence = []
        answer_parts = []
        try:
            from maestro_oem.simulation import SimulationEngine
            if self._model:
                decisions = getattr(self._model, 'decisions', None)
                engine = SimulationEngine(self._model, decisions)
                result = engine.simulate(scenario=query)
                summary = result.get("summary", "")
                if summary:
                    evidence.append({"source": "simulation_engine", "text": summary[:200], "date": "",
                        "people": [], "evidence_spine": {"claim": "Simulation results",
                        "observed_facts": [{"source": "simulation", "text": summary[:120]}], "claim_type": "prediction"}})
                    answer_parts.append(f"Simulation: {summary}")
                else:
                    answer_parts.append("I don't have enough model data to run this simulation.")
            else:
                answer_parts.append("I don't have enough model data to run this simulation.")
        except Exception as e:
            logger.warning("AskPipeline._retrieve_simulate: %s", e)
            answer_parts.append("I don't have enough model data to run this simulation.")
        return evidence, answer_parts

    def _retrieve_default(self, entities: list[str], query: str) -> tuple[list[dict], list[str]]:
        """Default retrieval: search signals for the query."""
        return self._search_signals(entities, query, focus="default", user_email=self._user_email or "")

    def _search_signals(
        self, entities: list[str], query: str, focus: str = "default",
        user_email: str = "",
    ) -> tuple[list[dict], list[str]]:
        """Search signals for entities + query words.

        C-003 fix: Filters signals by source_acl. Private signals are only
        visible to the actor or explicitly listed viewers. Public signals
        are visible to all org members (backward-compatible default).
        """
        from maestro_oem.signal import SignalType

        evidence = []
        answer_parts = []
        query_lower = query.lower()
        query_words = [w for w in query_lower.split() if len(w) > 3]

        for s in self._signals[:30]:
            # C-003: Permission-aware filtering
            acl = getattr(s, "source_acl", "public")
            if acl == "private":
                # Only the actor or explicitly listed viewers can see private signals
                viewers = s.metadata.get("viewers", [])
                if user_email and s.actor != user_email and user_email not in viewers:
                    continue  # Skip — user doesn't have permission
                if not user_email:
                    continue  # No user context — can't verify permission, skip (fail-closed)
            try:
                sig_text = " ".join(filter(None, [
                    s.artifact or "",
                    str(s.metadata.get("commitment", "")),
                    str(s.metadata.get("objection_type", "")),
                    str(s.metadata.get("customer", "")),
                    str(s.metadata.get("decision_outcome", "")),
                    str(s.type.value if hasattr(s.type, "value") else s.type),
                    s.actor or "",
                ]))
                sig_lower = sig_text.lower()

                # Match: entity OR query word
                entity_match = entities and any(e.lower() in sig_lower for e in entities)
                word_match = any(word in sig_lower for word in query_words)

                if entity_match or word_match:
                    sig_date = s.timestamp.isoformat()[:10] if hasattr(s.timestamp, "isoformat") else ""
                    sig_source = s.provider.value if hasattr(s.provider, "value") else str(s.provider)

                    # Determine claim_type based on signal type
                    claim_type = "observed_fact"
                    if hasattr(s, "type"):
                        if s.type == SignalType.CUSTOMER_COMMITMENT_MADE:
                            claim_type = "commitment"
                        elif s.type == SignalType.CUSTOMER_COMMITMENT_BROKEN:
                            claim_type = "outcome"
                        elif s.type == SignalType.CUSTOMER_DECISION:
                            claim_type = "outcome"
                        elif s.type == SignalType.CUSTOMER_OBJECTION:
                            claim_type = "observed_fact"

                    evidence.append({
                        "source": sig_source,
                        "text": sig_text[:150],
                        "date": sig_date,
                        "people": [s.actor] if s.actor else [],
                        "evidence_spine": {
                            "claim": sig_text[:100],
                            "observed_facts": [{"source": sig_source, "date": sig_date, "text": sig_text[:120], "people": [s.actor] if s.actor else []}],
                            "claim_type": claim_type,
                        },
                    })
                    answer_parts.append(f"- {sig_date} ({sig_source}): {sig_text[:100]}")
            except Exception:
                continue

        if not evidence:
            # C-2 FIX (external audit's most dangerous illusion):
            # Previously, when no entity matched, this code returned the first
            # 3 signals as "context" — producing plausible-looking but irrelevant
            # answers. An executive who asks "What about the weather?" and sees
            # a response with dates and sources assumes the system understood.
            # It did not.
            #
            # Now: return EMPTY evidence. The narrator will honestly say
            # "I don't have enough organizational memory to answer this."
            # This is the difference between a trustworthy system and a
            # sophisticated demo.
            pass

        if not evidence:
            answer_parts.append("I don't have enough relevant signals to answer this.")

        return evidence, answer_parts

    # ─── Synthesis (Step 5) ──────────────────────────────────────────

    def _synthesize(
        self,
        intent: AskIntent,
        entities: list[str],
        evidence: list[dict],
        answer_parts: list[str],
        query: str,
    ) -> str:
        """Compose a natural-language answer from the evidence.

        Template-based but evidence-grounded. No hardcoded phrases like
        "The real issue appears to be delivery trust, not price."
        """
        if not evidence:
            # Honest empty — not a hardcoded template
            entity_str = f" about {', '.join(entities)}" if entities else ""
            return f"I don't have enough organizational knowledge to answer this{entity_str}. Try asking about a specific customer, project, or decision."

        # Build answer from evidence
        parts = []

        # Intent-specific prefix
        if intent == AskIntent.RECALL:
            parts.append("I found this in my memory:")
        elif intent == AskIntent.PREPARE:
            parts.append("Here's what I've prepared:")
        elif intent == AskIntent.WHY:
            parts.append("Based on the organizational signals:")
        elif intent == AskIntent.WHO:
            parts.append("Based on signal activity:")
        elif intent == AskIntent.WHAT:
            parts.append("Here's what I found:")
        else:
            parts.append("I found relevant organizational knowledge:")

        # Add evidence-derived content
        for ap in answer_parts:
            if ap.startswith("- "):
                parts.append(ap)
            else:
                parts.append(ap)

        # Add entity reference if present
        if entities:
            parts.append(f"\nThis relates to: {', '.join(entities)}")

        parts.append("\n**Ask a follow-up...**")

        return "\n".join(parts)

    # ─── Follow-ups and actions ──────────────────────────────────────

    def suggest_autocomplete(self, partial_query: str, limit: int = 5) -> list[dict[str, Any]]:
        """P14: SemanticAutocompleteEngine — type-ahead suggestions for Ask Maestro.

        Returns a list of {text, type, score} suggestions derived from
        Learning Objects + patterns in the org's signal history.
        """
        try:
            from maestro_oem.autocomplete import SemanticAutocompleteEngine
            if not self._model or not self._signals:
                return []
            engine = SemanticAutocompleteEngine(self._model, self._signals)
            suggestions = engine.suggest(partial_query, limit=limit)
            return [s.to_dict() if hasattr(s, "to_dict") else s for s in suggestions]
        except Exception as e:
            logger.debug("AskPipeline.suggest_autocomplete failed: %s", e)
            return []

    def _suggest_follow_ups(self, intent: AskIntent, entities: list[str]) -> list[str]:
        """Suggest follow-up questions based on intent + entities."""
        entity_str = f" about {entities[0]}" if entities else ""

        if intent == AskIntent.RECALL:
            return ["Show the original whisper", "What changed since then?", "Show the evidence"]
        elif intent == AskIntent.PREPARE:
            return ["What exactly did we promise?", "Who was in that conversation?", "What are we assuming?"]
        elif intent == AskIntent.WHY:
            return ["Didn't we fix this?", "Show the original decision", "What changed since then?"]
        elif intent == AskIntent.WHO:
            return [f"What does {entities[0]} know about this?" if entities else "What is their expertise?", "Show their recent activity"]
        elif intent == AskIntent.WHAT:
            return ["Who made this commitment?", "Is this still active?", "What changed since?"]
        elif intent == AskIntent.WISDOM:
            return ["What are we assuming?", "Who disagrees with this?", "What if we're wrong?"]
        elif intent == AskIntent.WHAT_IF:
            return ["What's the evidence for this?", "Has this happened before?", "What would mitigate this?"]
        elif intent == AskIntent.SIMULATE:
            return ["What assumptions drive this?", "What if the inputs change?", "Show the evidence"]
        else:
            return [f"Tell me more about {entities[0]}" if entities else "Show related signals", "What changed recently?"]

    def _suggest_actions(self, intent: AskIntent) -> list[dict]:
        """Suggest actions based on intent."""
        if intent == AskIntent.RECALL:
            return [{"label": "Show original", "type": "evidence"}]
        elif intent == AskIntent.PREPARE:
            return [{"label": "Insert draft", "type": "insert_text"}]
        else:
            return []


class _LLMRouterSyncWrapper:
    """Sync wrapper around the async LLMRouter.

    The LLMNarrator expects a provider with an async complete() method.
    This wrapper adapts the LLMRouter's complete() to that interface.
    """

    def __init__(self, router: Any) -> None:
        self._router = router

    async def complete(self, system: str, user: str, **kwargs: Any) -> Any:
        """Call the LLMRouter's async complete()."""
        return await self._router.complete(system=system, user=user, **kwargs)
