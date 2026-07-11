"""
Maestro Cognitive Council — Surface Wiring: Copilot → Situation Engine.

Connects the Live Copilot browser extension to the Cognitive Council's
Situation Engine. Meeting intelligence now flows through Situations:

  Before meeting: Pre-call briefing references the Situation (not raw signals)
  During meeting: Transcript chunks update the Situation's operational state
                  (OBSERVING → ACTION_IN_PROGRESS → AWAITING_OUTCOME)
  After meeting:  Post-call summary feeds commitments to Situation.commitment_refs
                  and triggers the Behavioral Learning Engine

The existing Copilot routes (copilot_pre_call.py, copilot.py, copilot_post_call.py)
are left untouched — this bridge provides Situation-aware versions that can
be used alongside or instead of the legacy endpoints.

Usage:
    bridge = CopilotSituationBridge(oem_state=oem_state)
    pre = bridge.pre_call_briefing(meeting_title, attendees, user_email)
    # pre contains: situation (if found), unknowns, decision_boundary, evidence_refs

    # During meeting:
    bridge.on_transcript_chunk(situation_id, text, speaker)

    # After meeting:
    post = bridge.post_call_summary(situation_id, transcript_chunks, commitments)
    # post contains: situation state transitions, commitments ingested, learning triggered
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from .situation_engine import (
    LivingSituation,
    SituationEngine,
    SituationState,
    SideState,
    DeliveryRoute,
    TimelineEvent,
    Unknown,
)
from .judgment_synthesizer import JudgmentSynthesizer
from .delivery_governor import DeliveryGovernor, UserContext

logger = logging.getLogger(__name__)


@dataclass
class CopilotPreCallBriefing:
    """Situation-aware pre-call briefing.

    Unlike the old pre-call briefing (which queries OEM signals directly),
    this references the LivingSituation — its timeline, unknowns, decision
    boundary, and evidence_refs.
    """
    situation_id: str = ""
    situation_title: str = ""
    situation_state: str = ""
    entity: str = ""
    found_situation: bool = False

    # Attendee intelligence (from Situation timeline)
    timeline_summary: list[dict] = field(default_factory=list)

    # Unknowns to address in the meeting
    unknowns_to_address: list[dict] = field(default_factory=list)
    blocking_unknowns: list[str] = field(default_factory=list)

    # Decision boundary (what can/cannot be decided)
    can_decide_now: list[str] = field(default_factory=list)
    cannot_decide_yet: list[str] = field(default_factory=list)

    # Talking points (each citing Situation evidence_refs)
    talking_points: list[dict] = field(default_factory=list)

    # Risks to address
    risks: list[dict] = field(default_factory=list)

    # Evidence references (NOT copies)
    evidence_refs: list[str] = field(default_factory=list)

    # Delivery recommendation
    delivery_route: str = ""

    def to_dict(self) -> dict:
        return {
            "situation_id": self.situation_id,
            "situation_title": self.situation_title,
            "situation_state": self.situation_state,
            "entity": self.entity,
            "found_situation": self.found_situation,
            "timeline_summary": self.timeline_summary,
            "unknowns_to_address": self.unknowns_to_address,
            "blocking_unknowns": self.blocking_unknowns,
            "can_decide_now": self.can_decide_now,
            "cannot_decide_yet": self.cannot_decide_yet,
            "talking_points": self.talking_points,
            "risks": self.risks,
            "evidence_refs": self.evidence_refs,
            "delivery_route": self.delivery_route,
        }


@dataclass
class CopilotPostCallSummary:
    """Situation-aware post-call summary.

    After the call, the Situation's operational state transitions
    (ACTION_IN_PROGRESS → AWAITING_OUTCOME), commitments are ingested
    as refs, and the Behavioral Learning Engine is triggered.
    """
    situation_id: str = ""
    situation_title: str = ""
    entity: str = ""

    # State transitions during the call
    operational_transitions: list[dict] = field(default_factory=list)

    # Commitments ingested (as refs, not copies)
    commitments_ingested: list[str] = field(default_factory=list)

    # Learning triggered
    learning_triggered: bool = False
    learning_state_after: str = ""

    # What Maestro learned (feedback loop)
    what_maestro_learned: dict = field(default_factory=dict)

    # Draft follow-up (citing Situation evidence_refs)
    draft_followup: dict = field(default_factory=dict)

    # Evidence references
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "situation_id": self.situation_id,
            "situation_title": self.situation_title,
            "entity": self.entity,
            "operational_transitions": self.operational_transitions,
            "commitments_ingested": self.commitments_ingested,
            "learning_triggered": self.learning_triggered,
            "learning_state_after": self.learning_state_after,
            "what_maestro_learned": self.what_maestro_learned,
            "draft_followup": self.draft_followup,
            "evidence_refs": self.evidence_refs,
        }


class CopilotSituationBridge:
    """Connects the Live Copilot to the Situation Engine.

    Meeting intelligence flows through Situations:
      1. Pre-call: find the relevant Situation, surface its unknowns + decision boundary
      2. During call: transcript chunks update the Situation's operational state
      3. Post-call: commitments ingested as refs, learning engine triggered

    Usage:
        bridge = CopilotSituationBridge(oem_state=oem_state)
        pre = bridge.pre_call_briefing("CustomerA Renewal", ["ceo@customera.com"])
        bridge.on_transcript_chunk(pre.situation_id, "We will deliver SSO by Friday", "ceo")
        post = bridge.post_call_summary(pre.situation_id, [...], [...])
    """

    def __init__(self, oem_state: Any = None, learning_engine: Any = None,
                 situation_engine: Any = None):
        self._oem_state = oem_state
        self._situation_engine = situation_engine or SituationEngine(oem_state=oem_state)
        self._learning_engine = learning_engine
        self._delivery_governor = DeliveryGovernor()
        # Track active meeting situations (situation_id → is_in_meeting)
        self._active_meetings: dict[str, bool] = {}

    @property
    def oem_state(self) -> Any:
        if self._oem_state is None:
            try:
                from maestro_api.oem_state import oem_state
                self._oem_state = oem_state
            except ImportError:
                self._oem_state = None
        return self._oem_state

    # ── Pre-call: find Situation, surface unknowns + decision boundary ──────

    def pre_call_briefing(
        self,
        meeting_title: str = "",
        attendees: list[str] = None,
        user_email: str = "",
        org_id: str = "default",
    ) -> CopilotPreCallBriefing:
        """Generate a Situation-aware pre-call briefing.

        Finds the relevant Situation for the meeting (by entity in title
        or attendee domains), surfaces its unknowns and decision boundary,
        and generates talking points that cite Situation evidence_refs.
        """
        attendees = attendees or []
        briefing = CopilotPreCallBriefing()

        # 1. Detect the entity from meeting title or attendee domains
        entity = self._detect_entity(meeting_title, attendees)
        if not entity:
            briefing.talking_points = [{
                "text": "No active situation detected for this meeting.",
                "evidence_ref": None,
            }]
            return briefing

        # 2. Find the relevant situation (use existing if already detected)
        situation = self._find_situation_for_entity(
            list(self._situation_engine._situations.values()), entity
        )
        if not situation:
            # Detect situations if not already done
            situations = self._situation_engine.detect_situations(org_id)
            situation = self._find_situation_for_entity(situations, entity)

        if not situation:
            briefing.talking_points = [{
                "text": f"No active situation found for {entity}.",
                "evidence_ref": None,
            }]
            return briefing

        # 3. Populate the briefing from the Situation
        briefing.found_situation = True
        briefing.situation_id = situation.situation_id
        briefing.situation_title = situation.title
        briefing.situation_state = situation.state.value
        briefing.entity = situation.entity

        # 4. Timeline summary (last 5 events)
        briefing.timeline_summary = [
            {
                "timestamp": e.timestamp.isoformat() if isinstance(e.timestamp, datetime) else str(e.timestamp),
                "description": e.description,
                "event_type": e.event_type,
                "evidence_ref": e.evidence_ref,
            }
            for e in situation.timeline[-5:]
        ]

        # 5. Unknowns to address
        briefing.unknowns_to_address = [
            u.to_dict() for u in situation.unknowns if not u.resolved
        ]
        briefing.blocking_unknowns = [
            u.question for u in situation.unknowns
            if u.blocking and not u.resolved
        ]

        # 6. Decision boundary (from judgment if available)
        if situation.judgment and situation.judgment.decision_boundary:
            db = situation.judgment.decision_boundary
            briefing.can_decide_now = db.can_decide_now
            briefing.cannot_decide_yet = db.cannot_decide_yet

        # 7. Talking points (each citing evidence_refs)
        briefing.talking_points = self._generate_talking_points(situation)

        # 8. Risks to address
        briefing.risks = self._identify_risks(situation)

        # 9. Evidence references
        briefing.evidence_refs = situation.evidence_refs

        # 10. Delivery recommendation
        route = self._delivery_governor.decide(
            situation, [],
            UserContext(is_in_meeting=True)
        )
        briefing.delivery_route = route.value

        return briefing

    # ── During call: transcript chunks update operational state ─────────────

    def on_transcript_chunk(
        self,
        situation_id: str,
        text: str,
        speaker: str = "",
        entity: str = "",
    ) -> dict[str, Any]:
        """Process a transcript chunk during the meeting.

        Updates the Situation's operational state:
          - First chunk: OBSERVING/MATERIAL/NEEDS_PREPARATION → ACTION_IN_PROGRESS
          - Commitment keywords: add to commitment_refs
          - Unknown resolution keywords: resolve unknowns

        Returns a dict with any state transitions or new commitments detected.
        """
        result: dict[str, Any] = {
            "transitions": [],
            "commitments_detected": [],
            "unknowns_resolved": [],
        }

        situation = self._situation_engine.get_situation(situation_id)
        if not situation:
            return result

        # 1. Transition to ACTION_IN_PROGRESS on first chunk
        if situation.operational_dimension.value if hasattr(situation, 'operational_dimension') else situation.state.value not in (
            "action_in_progress", "closed"
        ):
            # Use the 4D model if available
            if hasattr(situation, 'transition_dimension'):
                transition = situation.transition_dimension(
                    dimension="operational",
                    new_state="action_in_progress",
                    reason=f"Meeting in progress — transcript chunk received from {speaker}",
                    triggering_event_refs=[f"transcript-{uuid4().hex[:8]}"],
                    rule_id="copilot.meeting_started",
                    delivery_effect="Whisper eligible during meeting",
                )
                result["transitions"].append(transition.to_dict())
            else:
                # Fallback to legacy state
                if situation.state in (SituationState.OBSERVING, SituationState.MATERIAL,
                                       SituationState.NEEDS_PREPARATION, SituationState.DECISION_PENDING):
                    old_state = situation.state
                    situation.transition_to(
                        SituationState.ACTION_IN_PROGRESS,
                        reason=f"Meeting in progress — transcript chunk received",
                    )
                    result["transitions"].append({
                        "from": old_state.value,
                        "to": "action_in_progress",
                        "reason": "Meeting in progress",
                    })

        # 2. Detect commitments in the transcript
        text_lower = text.lower()
        commitment_keywords = ["will deliver", "will send", "will ship", "commit",
                               "promise", "by friday", "by next", "i'll", "we'll"]
        for kw in commitment_keywords:
            if kw in text_lower:
                commit_ref = f"transcript-commit-{uuid4().hex[:8]}"
                if commit_ref not in situation.commitment_refs:
                    situation.commitment_refs.append(commit_ref)
                    result["commitments_detected"].append({
                        "ref": commit_ref,
                        "text": text[:100],
                        "speaker": speaker,
                    })
                break

        # 2b. Detect revocations in the transcript (Phase 8 fix)
        # The bridge had commitment keywords + resolution keywords but NO
        # revocation keywords. When someone says "the report is cancelled"
        # or "I backed out," the bridge didn't detect it. This was a real
        # gap (not an LLM dependency) — revocation is rule-based.
        revocation_keywords = ["cancelled", "cancel", "revoked", "revoke",
                               "backed out", "back out", "off", "can't do",
                               "won't be able", "called off", "pulled out",
                               "backed out", "no longer", "not anymore"]
        for kw in revocation_keywords:
            if kw in text_lower:
                revoke_ref = f"transcript-revocation-{uuid4().hex[:8]}"
                result.setdefault("revocations_detected", []).append({
                    "ref": revoke_ref,
                    "text": text[:100],
                    "speaker": speaker,
                    "keyword": kw,
                })
                break

        # 3. Check for unknown resolution
        resolution_keywords = ["approved", "resolved", "cleared", "confirmed", "done", "complete"]
        for unknown in situation.unknowns:
            if unknown.resolved:
                continue
            for kw in resolution_keywords:
                if kw in text_lower and any(
                    word in unknown.question.lower()
                    for word in text_lower.split()[:5]
                ):
                    unknown.resolved = True
                    unknown.resolved_by_evidence_ref = f"transcript-{uuid4().hex[:8]}"
                    result["unknowns_resolved"].append(unknown.question)
                    break

        # 4. Add transcript as timeline event
        situation.add_timeline_event(TimelineEvent(
            timestamp=datetime.now(timezone.utc),
            description=f"[{speaker}] {text[:120]}",
            event_type="reported",
            evidence_ref=f"transcript-{uuid4().hex[:8]}",
            source="copilot_transcript",
        ))

        return result

    # ── Post-call: ingest commitments, trigger learning ─────────────────────

    def post_call_summary(
        self,
        situation_id: str,
        transcript_chunks: list[dict] = None,
        commitments: list[dict] = None,
        entity: str = "",
    ) -> CopilotPostCallSummary:
        """Generate a Situation-aware post-call summary.

        After the call:
          1. Transition operational state: ACTION_IN_PROGRESS → AWAITING_OUTCOME
          2. Ingest commitments as refs (not copies)
          3. Trigger the Behavioral Learning Engine
          4. Generate draft follow-up citing Situation evidence_refs
        """
        transcript_chunks = transcript_chunks or []
        commitments = commitments or []
        summary = CopilotPostCallSummary()

        situation = self._situation_engine.get_situation(situation_id)
        if not situation:
            summary.situation_title = "Situation not found"
            return summary

        summary.situation_id = situation.situation_id
        summary.situation_title = situation.title
        summary.entity = situation.entity or entity

        # 1. Transition to AWAITING_OUTCOME
        if hasattr(situation, 'transition_dimension'):
            transition = situation.transition_dimension(
                dimension="operational",
                new_state="awaiting_outcome",
                reason="Meeting concluded — awaiting outcome",
                triggering_event_refs=[f"postcall-{uuid4().hex[:8]}"],
                rule_id="copilot.meeting_ended",
                delivery_effect="Silent — awaiting outcome",
            )
            summary.operational_transitions.append(transition.to_dict())
        else:
            if situation.state == SituationState.ACTION_IN_PROGRESS:
                situation.transition_to(
                    SituationState.AWAITING_OUTCOME,
                    reason="Meeting concluded — awaiting outcome",
                )
                summary.operational_transitions.append({
                    "from": "action_in_progress",
                    "to": "awaiting_outcome",
                    "reason": "Meeting concluded",
                })

        # 2. Ingest commitments as refs
        for commit in commitments:
            commit_ref = commit.get("ref", "") or f"postcall-commit-{uuid4().hex[:8]}"
            if commit_ref not in situation.commitment_refs:
                situation.commitment_refs.append(commit_ref)
                summary.commitments_ingested.append(commit_ref)

        # 3. Trigger the Behavioral Learning Engine
        if self._learning_engine:
            try:
                learning_result = self._learning_engine.apply_learning(situation)
                summary.learning_triggered = True
                summary.learning_state_after = learning_result.learning_state_after
                summary.what_maestro_learned = learning_result.to_dict()
            except Exception as e:
                logger.debug(f"Learning engine failed: {e}")

        # 4. Generate draft follow-up
        summary.draft_followup = self._generate_draft_followup(situation, commitments)

        # 5. Evidence references
        summary.evidence_refs = situation.evidence_refs

        return summary

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _detect_entity(self, meeting_title: str, attendees: list[str]) -> Optional[str]:
        """Detect the entity from meeting title or attendee domains."""
        # Check meeting title against known entities
        if self.oem_state:
            signals = getattr(self.oem_state, "signals", None) or []
            title_lower = (meeting_title or "").lower()

            known_entities: set[str] = set()
            for sig in signals:
                entity = (
                    getattr(sig, "entity", None)
                    or (getattr(sig, "metadata", {}) or {}).get("customer")
                )
                if entity:
                    known_entities.add(entity)

            for entity in known_entities:
                if entity.lower() in title_lower:
                    return entity

        # Check attendee domains
        for email in attendees:
            if "@" in email:
                domain = email.split("@")[1].split(".")[0]
                if domain not in ("gmail", "outlook", "yahoo", "example"):
                    return domain.capitalize()

        return None

    def _find_situation_for_entity(
        self, situations: list[LivingSituation], entity: str
    ) -> Optional[LivingSituation]:
        """Find the most relevant Situation for the given entity."""
        entity_lower = entity.lower()
        matching = [s for s in situations if s.entity.lower() == entity_lower]
        if matching:
            return max(matching, key=lambda s: s.updated_at)
        return None

    def _generate_talking_points(self, situation: LivingSituation) -> list[dict]:
        """Generate talking points citing Situation evidence_refs."""
        points: list[dict] = []

        # Lead with blocking unknowns
        for u in situation.unknowns:
            if u.blocking and not u.resolved:
                points.append({
                    "text": f"Address: {u.question}",
                    "priority": "high",
                    "evidence_ref": situation.evidence_refs[0] if situation.evidence_refs else None,
                    "why": u.why_it_matters,
                })

        # Reference material changes
        if situation.material_changes:
            latest = situation.material_changes[-1]
            points.append({
                "text": f"Discuss: {latest[:80]}",
                "priority": "medium",
                "evidence_ref": situation.evidence_refs[0] if situation.evidence_refs else None,
            })

        # Reference disagreements
        for d in situation.disagreements[:2]:
            if d.unresolved:
                points.append({
                    "text": f"Clarify: {d.topic}",
                    "priority": "medium",
                    "evidence_ref": situation.evidence_refs[0] if situation.evidence_refs else None,
                })

        return points[:5]  # max 5 talking points

    def _identify_risks(self, situation: LivingSituation) -> list[dict]:
        """Identify risks to address in the meeting."""
        risks: list[dict] = []

        if situation.has_blocking_unknown():
            risks.append({
                "type": "blocking_unknown",
                "severity": "high",
                "text": f"{len([u for u in situation.unknowns if u.blocking and not u.resolved])} blocking unknown(s)",
                "evidence_ref": situation.evidence_refs[0] if situation.evidence_refs else None,
            })

        if situation.has_side_state(SideState.DISPUTED):
            risks.append({
                "type": "disputed",
                "severity": "medium",
                "text": "Evidence conflicts — disputed territory",
            })

        return risks

    def _generate_draft_followup(
        self, situation: LivingSituation, commitments: list[dict]
    ) -> dict:
        """Generate a draft follow-up citing Situation evidence_refs."""
        subject = f"Follow-up — {situation.title}"

        body_lines = [
            f"Hi —",
            "",
            "Thank you for the productive call. Here's what I captured:",
            "",
        ]

        if commitments:
            body_lines.append("Commitments:")
            for c in commitments:
                text = c.get("text", "") if isinstance(c, dict) else str(c)
                body_lines.append(f"  • {text}")
            body_lines.append("")

        if situation.unknowns:
            unresolved = [u for u in situation.unknowns if not u.resolved]
            if unresolved:
                body_lines.append("Open questions:")
                for u in unresolved[:3]:
                    body_lines.append(f"  • {u.question}")
                body_lines.append("")

        body_lines.extend([
            "Next steps:",
            "  • I'll follow up on the items above",
            "",
            "Please let me know if I've missed anything.",
        ])

        return {
            "subject": subject,
            "body": "\n".join(body_lines),
            "evidence_refs": situation.evidence_refs,
        }
