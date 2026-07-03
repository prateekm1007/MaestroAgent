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
    """

    what_is_happening: str = ""
    entities: list[str] = field(default_factory=list)
    commitments: list[dict] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    current_state: str = "unknown"  # "at_risk" | "on_track" | "unknown"
    prior_whispers: list[str] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "what_is_happening": self.what_is_happening,
            "entities": self.entities,
            "commitments": self.commitments,
            "evidence": self.evidence,
            "current_state": self.current_state,
            "prior_whispers": self.prior_whispers,
            "timeline": self.timeline,
        }


class SituationBuilder:
    """Construct a Situation from signals + calendar + whisper history.

    Usage:
        builder = SituationBuilder(signals=signals, calendar_source=cal, whisper_store=store, now=now)
        situation = builder.build_for_entity("<customer>", org_id="default")
    """

    def __init__(
        self,
        signals: list,
        calendar_source: Any = None,
        whisper_store: Any = None,
        now: datetime | None = None,
    ) -> None:
        self._signals = list(signals) if signals else []
        self._calendar = calendar_source
        self._store = whisper_store
        self._now = now or datetime.now(timezone.utc)

    def build_for_entity(self, entity: str, org_id: str = "default") -> Situation | None:
        """Build a Situation for a specific entity.

        Returns None if the entity has no signals (nothing to build from).
        """
        if not entity:
            return None

        # Filter signals for this entity
        entity_signals = [
            s for s in self._signals
            if hasattr(s, "metadata") and s.metadata.get("customer") == entity
        ]
        if not entity_signals:
            return None

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

        return Situation(
            what_is_happening=what_is_happening,
            entities=entities,
            commitments=commitments,
            evidence=evidence,
            current_state=current_state,
            prior_whispers=prior_whispers,
            timeline=timeline,
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
