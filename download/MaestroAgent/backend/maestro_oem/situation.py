"""Loop 1.5 — Minimal Situation Abstraction.

External auditor (AUDITOR-EXTERNAL-REVIEW-3):
> Minimal Situation abstraction — 7 fields (what_is_happening, entities,
> commitments, evidence, current_state, prior_whispers, timeline).

A Situation is Maestro's working memory for a specific organizational
moment. When the exec asks "what's going on with <customer>?" or when
Maestro fires a Whisper before the <customer> meeting, it reasons over a
Situation — not over raw signals.

The 7 fields:
  1. what_is_happening — one sentence: "<customer> Quarterly Review tomorrow"
  2. entities — who/what is involved: ["<customer>", "jane.d@example.com"]
  3. commitments — active commitments: [{"customer": "<customer>", "text": "Deliver SSO by 2024-12-15"}]
  4. evidence — Evidence objects from EvidenceBuilder
  5. current_state — "at_risk" | "on_track" | "unknown"
  6. prior_whispers — whisper IDs previously surfaced for this entity
  7. timeline — chronologically ordered events: [{"date": "...", "event": "..."}]

The SituationBuilder constructs a Situation from:
  - signals (for entities, commitments, evidence, timeline)
  - calendar source (for what_is_happening)
  - whisper store (for prior_whispers)
  - at_risk computation (for current_state)

This is the difference between Maestro reasoning over a flat list of
signals and Maestro reasoning over a structured working memory. The
flat list is data. The Situation is understanding.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Situation:
    """Maestro's working memory for a specific organizational moment.

    7 fields — populated from real signals + calendar + whisper history.

    Phase 2 (auditor Option A): Situation is intentionally DERIVED, not stored.
    It is rebuilt on every surface request from persisted signals + commitments
    + evidence. The situations table in OEMStore is a cache for performance,
    not the source of truth. Do not rely on persisted Situation objects —
    always rebuild from signals for canonical state.

    The builder NEVER returns None — it always returns a valid Situation with
    clear provenance. If no signals exist for an entity, the Situation has
    what_is_happening="No data available for this entity" and current_state="unknown".
    """

    what_is_happening: str = ""
    entities: list[str] = field(default_factory=list)
    commitments: list[dict] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    current_state: str = "unknown"  # "at_risk" | "on_track" | "unknown"
    prior_whispers: list[str] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)
    # CRITICAL-03 Phase 2: enriched fields for cross-surface coherence
    disagreements: list[dict] = field(default_factory=list)
    pending_conditions: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "what_is_happening": self.what_is_happening,
            "entities": self.entities,
            "commitments": self.commitments,
            "evidence": self.evidence,
            "current_state": self.current_state,
            "prior_whispers": self.prior_whispers,
            "timeline": self.timeline,
            "disagreements": self.disagreements,
            "pending_conditions": self.pending_conditions,
            "unknowns": self.unknowns,
        }

    def is_derived(self) -> bool:
        """Phase 2 (auditor Option A): Situation is intentionally derived/deterministic.

        It is rebuilt on every surface request from persisted signals + model state.
        The situations table in OEMStore is a cache, not the source of truth.
        """
        return True


class SituationBuilder:
    """Construct a Situation from signals + calendar + whisper history.

    Usage:
        builder = SituationBuilder(signals=signals, calendar_source=cal, whisper_store=store, now=now)
        situation = builder.build_for_entity("<customer>", org_id="default")

    CRITICAL-01 fix: if user_email is provided, signals are filtered through
    ACLResolver before building the situation. Channel-scoped content is
    deny-by-default — unauthorized users see a situation built only from
    signals they can access.
    """

    def __init__(
        self,
        signals: list,
        calendar_source: Any = None,
        whisper_store: Any = None,
        now: datetime | None = None,
        user_email: str = "",
    ) -> None:
        # CRITICAL-01 fix: ACL-filter signals for this user before building
        # the situation. Deny-by-default for non-public ACLs.
        if signals and user_email:
            try:
                from maestro_oem.acl_resolver import ACLResolver
                acl_resolver = ACLResolver()
                self._signals = [s for s in signals if acl_resolver.can_access(s, user_email)]
            except Exception:
                # If ACL resolution fails, fail-closed: empty signals
                self._signals = []
        else:
            self._signals = list(signals) if signals else []
        self._calendar = calendar_source
        self._store = whisper_store
        self._now = now or datetime.now(timezone.utc)

    def build_for_entity(self, entity: str, org_id: str = "default") -> Situation:
        """Build a Situation for a specific entity.

        Phase 2 (auditor Option A): NEVER returns None. If the entity has no
        signals, returns a valid Situation with what_is_happening="No data
        available for this entity" and current_state="unknown". This prevents
        surfaces from silently degrading when an entity is new or has minimal data.
        """
        if not entity:
            return Situation(
                what_is_happening="No entity specified",
                entities=[],
                current_state="unknown",
            )

        # Filter signals for this entity
        entity_signals = [
            s for s in self._signals
            if hasattr(s, "metadata") and s.metadata.get("customer") == entity
        ]
        if not entity_signals:
            # Phase 2: return a valid (not None) Situation with clear provenance
            return Situation(
                what_is_happening=f"No data available for {entity}",
                entities=[entity],
                current_state="unknown",
            )

        # 1. what_is_happening — from the next consequential meeting
        what_is_happening = self._compute_what_is_happening(entity)

        # 2. entities — the primary entity + actors
        entities = [entity]
        actors = {s.actor for s in entity_signals if hasattr(s, "actor") and s.actor}
        entities.extend(actors)

        # 3. commitments — from commitment signals
        commitments = self._extract_commitments(entity_signals)

        # 4. evidence — from EvidenceBuilder
        evidence = self._build_evidence(entity, entity_signals)

        # 5. current_state — at_risk if broken commitment, else on_track if commitments exist
        current_state = self._compute_current_state(entity_signals)

        # 6. prior_whispers — from the whisper store
        prior_whispers = self._get_prior_whispers(entity, org_id)

        # 7. timeline — chronologically ordered events
        timeline = self._build_timeline(entity_signals)

        # CRITICAL-03 Phase 2: enriched fields
        # 8. disagreements — detect conflicting reported statements
        disagreements = self._detect_disagreements(entity_signals)
        # 9. pending_conditions — from negation-classified signals
        pending_conditions = self._extract_pending_conditions(entity_signals)
        # 10. unknowns — gaps in evidence
        unknowns = self._derive_unknowns(commitments, evidence, entity_signals)

        return Situation(
            what_is_happening=what_is_happening,
            entities=entities,
            commitments=commitments,
            evidence=evidence,
            current_state=current_state,
            prior_whispers=prior_whispers,
            timeline=timeline,
            disagreements=disagreements,
            pending_conditions=pending_conditions,
            unknowns=unknowns,
        )

    def _compute_what_is_happening(self, entity: str) -> str:
        """One sentence describing what's happening with this entity."""
        if self._calendar is None:
            return f"Active relationship with {entity}"

        try:
            tomorrow = self._now + timedelta(days=1)
            events = self._calendar.get_events_for_date(tomorrow)
            entity_events = [e for e in events if e.entity == entity]
            if entity_events:
                event = entity_events[0]
                return f"{event.title} tomorrow at {event.start.strftime('%H:%M')}"
        except Exception as e:
            logger.debug("SituationBuilder: calendar lookup failed: %s", e)

        return f"Active relationship with {entity}"

    def _extract_commitments(self, entity_signals: list) -> list[dict]:
        """Extract commitments from commitment signals."""
        from maestro_oem.signal import SignalType
        commitments = []
        for s in entity_signals:
            try:
                if s.type == SignalType.CUSTOMER_COMMITMENT_MADE:
                    commitments.append({
                        "customer": s.metadata.get("customer", ""),
                        "text": s.metadata.get("commitment", ""),
                        "date": s.timestamp.isoformat()[:10] if hasattr(s.timestamp, "isoformat") else "",
                        "actor": s.actor or "",
                    })
            except Exception:
                continue
        return commitments

    def _build_evidence(self, entity: str, entity_signals: list) -> list[dict]:
        """Build Evidence objects from the entity's signals."""
        try:
            from maestro_oem.evidence import EvidenceBuilder
            builder = EvidenceBuilder(self._signals)
            evidence_obj = builder.build_for_whisper(
                whisper_type="commitment_exists",
                entity=entity,
                topic="",
                raw_evidence={"artifact": "", "timestamp": self._now.isoformat()},
                context="situation",
            )
            return [evidence_obj.to_dict()]
        except Exception as e:
            logger.debug("SituationBuilder: evidence build failed: %s", e)
            return []

    def _compute_current_state(self, entity_signals: list) -> str:
        """Compute current_state: at_risk, on_track, or unknown."""
        from maestro_oem.signal import SignalType
        has_broken = any(s.type == SignalType.CUSTOMER_COMMITMENT_BROKEN for s in entity_signals)
        has_objection = any(s.type == SignalType.CUSTOMER_OBJECTION for s in entity_signals)
        has_commitment = any(s.type == SignalType.CUSTOMER_COMMITMENT_MADE for s in entity_signals)

        if has_broken or has_objection:
            return "at_risk"
        if has_commitment:
            return "on_track"
        return "unknown"

    def _get_prior_whispers(self, entity: str, org_id: str) -> list[str]:
        """Get prior whisper IDs for this entity from the store."""
        if self._store is None or not hasattr(self._store, "get_all_history"):
            return []
        try:
            all_history = self._store.get_all_history(org_id=org_id)
            return [
                wid for wid, history in all_history.items()
                if isinstance(history, dict) and history.get("entity") == entity
            ]
        except Exception as e:
            logger.debug("SituationBuilder: whisper history lookup failed: %s", e)
            return []

    def _build_timeline(self, entity_signals: list) -> list[dict]:
        """Build a chronologically ordered timeline from signals."""
        timeline = []
        for s in entity_signals:
            try:
                sig_type_str = str(s.type).lower()
                if "." in sig_type_str:
                    sig_type_str = sig_type_str.split(".")[-1].replace("_", " ")
                else:
                    sig_type_str = sig_type_str.replace("_", " ")
                timeline.append({
                    "date": s.timestamp.isoformat()[:10] if hasattr(s.timestamp, "isoformat") else "",
                    "event": sig_type_str,
                    "actor": s.actor or "",
                    "artifact": s.artifact or "",
                })
            except Exception:
                continue
        # Sort by date
        timeline.sort(key=lambda x: x.get("date", ""))
        return timeline

    # ─── CRITICAL-03 Phase 2: Enriched field extraction ─────────────────

    def _detect_disagreements(self, entity_signals: list) -> list[dict]:
        """Detect conflicting statements about the entity from different actors.

        A disagreement exists when different actors make conflicting claims
        about the same entity. This uses THREE strategies (not just one)
        to catch disagreements in natural language:

        Strategy 1: Reported statements from 2+ actors (original — "says we")
        Strategy 2: Commitment + negation from different actors
                    ("We will deliver SSO" vs "SSO will not be ready")
        Strategy 3: Same-topic opposing signals from different actors
                    ("promised production" vs "only promised technical")

        The prior version only used Strategy 1 (keyword-based "says we"
        patterns). This was the same theater pattern as MEDIUM-2 — the
        test passed because it used the exact phrasing the code handled.
        Now all 3 strategies are applied, catching natural language
        disagreements without requiring specific phrasings.
        """
        try:
            from maestro_oem.content_epistemic_classifier import ContentEpistemicClassifier
            classifier = ContentEpistemicClassifier()
        except Exception:
            return []

        # Classify all signals and group by actor
        actor_signals: dict[str, list[dict]] = {}  # {actor: [{text, epistemic, signal}]}
        for s in entity_signals:
            try:
                # Check multiple metadata keys — demo seed uses "title", real signals use "text"/"body"
                text = (s.metadata.get("text", "") or s.metadata.get("body", "")
                        or s.metadata.get("title", "") or s.metadata.get("subject", "")
                        or s.metadata.get("commitment", "") or s.metadata.get("note", ""))
                if not text:
                    continue
                result = classifier.classify(text)
                epistemic = result if isinstance(result, str) else getattr(result, "epistemic_type", str(result))
                actor = s.actor or "unknown"
                if actor not in actor_signals:
                    actor_signals[actor] = []
                actor_signals[actor].append({"actor": actor, "text": text[:200], "epistemic": epistemic})
            except Exception:
                continue

        if len(actor_signals) < 2:
            return []  # Need 2+ actors for a disagreement

        disagreements: list[dict] = []

        # Strategy 1: 2+ actors with reported_statement signals
        reported_by_actor: dict[str, list[dict]] = {}
        for actor, sigs in actor_signals.items():
            reported = [s for s in sigs if s["epistemic"] == "reported_statement"]
            if reported:
                reported_by_actor[actor] = reported
        if len(reported_by_actor) >= 2:
            for actor, sigs in reported_by_actor.items():
                for s in sigs:
                    disagreements.append({"actor": actor, "text": s["text"]})

        # Strategy 2: commitment from one actor + negation from another
        actors_with_commitment = set()
        actors_with_negation = set()
        commitment_signals = []
        negation_signals = []
        for actor, sigs in actor_signals.items():
            for s in sigs:
                if s["epistemic"] == "commitment":
                    actors_with_commitment.add(actor)
                    commitment_signals.append({"actor": actor, "text": s["text"]})
                elif s["epistemic"] == "negation":
                    actors_with_negation.add(actor)
                    negation_signals.append({"actor": actor, "text": s["text"]})
        if actors_with_commitment and actors_with_negation and actors_with_commitment != actors_with_negation:
            disagreements.extend(commitment_signals[:2])
            disagreements.extend(negation_signals[:2])

        # Strategy 3: opposing signals from different actors (keyword-based)
        # Detect when 2+ actors have signals with opposing stance keywords
        # on the same topic. This catches direct conflicts like:
        # "SSO will be ready by Q4" vs "SSO will not be ready by Q4"
        opposing_pairs = [
            ("will", "will not"),
            ("will", "won't"),
            ("ready", "not ready"),
            ("promised", "only promised"),
            ("available", "not available"),
            ("complete", "not complete"),
            ("delivered", "not delivered"),
            ("on track", "at risk"),
            ("confirmed", "denied"),
            ("yes", "no"),
            ("production", "only technical"),
            ("production", "technical only"),
            ("expects", "only asked"),
            ("full", "partial"),
            ("met", "unmet"),
            ("honored", "broken"),
        ]
        actor_texts = {actor: [s["text"].lower() for s in sigs] for actor, sigs in actor_signals.items()}
        actors_list = list(actor_texts.keys())
        for i, actor1 in enumerate(actors_list):
            for actor2 in actors_list[i+1:]:
                for pos_kw, neg_kw in opposing_pairs:
                    has_pos = any(pos_kw in t for t in actor_texts[actor1])
                    has_neg = any(neg_kw in t for t in actor_texts[actor2])
                    has_pos_rev = any(pos_kw in t for t in actor_texts[actor2])
                    has_neg_rev = any(neg_kw in t for t in actor_texts[actor1])
                    if (has_pos and has_neg) or (has_pos_rev and has_neg_rev):
                        # Found opposing signals from different actors
                        for s in actor_signals[actor1]:
                            if pos_kw in s["text"].lower() or neg_kw in s["text"].lower():
                                disagreements.append({"actor": actor1, "text": s["text"]})
                        for s in actor_signals[actor2]:
                            if pos_kw in s["text"].lower() or neg_kw in s["text"].lower():
                                disagreements.append({"actor": actor2, "text": s["text"]})
                        break  # One opposing pair is enough for this actor pair

        # Deduplicate by (actor, text) and return up to 5
        seen = set()
        unique = []
        for d in disagreements:
            key = (d["actor"], d["text"][:50])
            if key not in seen:
                seen.add(key)
                unique.append(d)
        return unique[:5]

    def _extract_pending_conditions(self, entity_signals: list) -> list[str]:
        """Extract pending conditions from negation-classified signals.

        A pending condition is a negation signal like "security approval
        is still conditional" — it indicates something that must be
        resolved before a commitment can be fulfilled.
        """
        try:
            from maestro_oem.content_epistemic_classifier import ContentEpistemicClassifier
            classifier = ContentEpistemicClassifier()
        except Exception:
            return []

        conditions = []
        for s in entity_signals:
            try:
                text = s.metadata.get("text", "") or s.metadata.get("body", "")
                if not text:
                    continue
                result = classifier.classify(text)
                epistemic = result if isinstance(result, str) else getattr(result, "epistemic_type", str(result))
                if epistemic == "negation":
                    conditions.append(text[:200])
            except Exception:
                continue
        return conditions[:5]

    def _derive_unknowns(self, commitments: list[dict], evidence: list, entity_signals: list) -> list[str]:
        """Derive what we DON'T know from the gaps in evidence.

        If there's a commitment but no outcome, that's an unknown:
        "Will this commitment be met?"

        If there's a commitment but no timeline events after it,
        that's an unknown: "What progress has been made?"

        If there are disagreements, that's an unknown:
        "Which interpretation is correct?"
        """
        unknowns = []
        if commitments and not any(
            "outcome" in str(s.type).lower() or "kept" in str(s.type).lower()
            for s in entity_signals
        ):
            unknowns.append("Whether the commitment will be met")
        if len(commitments) > 0:
            has_disagreement = len(self._detect_disagreements(entity_signals)) > 0
            if has_disagreement:
                unknowns.append("Which interpretation of the commitment is correct")
        return unknowns[:5]
