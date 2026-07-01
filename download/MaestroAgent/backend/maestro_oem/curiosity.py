"""
Organ #2 — Curiosity: Maestro asks questions the org has never asked.

Finds untested assumptions, unmeasured domains, unexplained patterns.
Curiosity is not a feature — it's a cognitive organ that makes the
organization question its own blind spots.

The engine scans for:
  1. Untested assumptions — assumptions with 0 contradicting AND 0 supporting signals
  2. Unmeasured domains — knowledge domains with <3 signals (the org isn't watching)
  3. Unexplained patterns — laws with high evidence but no documented explanation
  4. Repeated bottlenecks — the same bottleneck appearing >3 times with no resolution

V8 Upgrade #2 — Four-Level Unknowns. The engine now also classifies every
organizational area into 4 epistemic levels:
  - Known (coverage > 60%): the org has measured this area thoroughly
  - Known Unknown (10-60% coverage): the org knows it's under-measuring
  - Unknown Unknown (< 10% coverage): the org doesn't know it doesn't know
  - Emerging Unknown (new signal pattern in last 7 days that doesn't match
    any existing learning object): something new is happening

This is more scientifically rigorous than a single "blind spots" list. It
builds trust — the org can see not just what it doesn't know, but the
*shape* of its ignorance. Known Unknowns are actionable (instrument them);
Unknown Unknowns are risky (they're blind spots); Emerging Unknowns are
opportunities (investigate before they become patterns or incidents).

API: GET /api/oem/curiosity
      GET /api/oem/unknowns?levels=all
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


class CuriosityEngine:
    """Find questions the organization has never asked.

    Curiosity is the engine of learning. An organization that stops asking
    questions stops growing. Maestro asks the questions the org doesn't
    know it should ask.
    """

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def generate(self) -> dict[str, Any]:
        """Generate curiosity questions from organizational blind spots."""
        questions = []

        # 1. Untested assumptions
        questions.extend(self._find_untested_assumptions())

        # 2. Unmeasured domains
        questions.extend(self._find_unmeasured_domains())

        # 3. Unexplained patterns
        questions.extend(self._find_unexplained_patterns())

        # 4. Repeated bottlenecks
        questions.extend(self._find_repeated_bottlenecks())

        # Assign stable question_ids (V8 #3 — Conversational Curiosity needs
        # a stable ID to track conversation state across turns). The ID is
        # deterministic from type+domain so the same question always gets
        # the same ID within a session.
        for i, q in enumerate(questions):
            q["question_id"] = f"cq-{q.get('type', 'unknown')}-{q.get('domain', 'unknown')}-{i}"

        # Sort by urgency
        questions.sort(key=lambda q: {"high": 0, "medium": 1, "low": 2}.get(q.get("urgency", "low"), 2))

        # Limit to top 5
        questions = questions[:5]

        if len(questions) == 0:
            summary = "Maestro has no open questions. The organization's blind spots are covered."
        else:
            summary = f"Maestro is curious about {len(questions)} {'thing' if len(questions) == 1 else 'things'} your organization has never investigated."

        return {
            "questions": questions,
            "summary": summary,
            "blind_spots": len(questions),
        }

    # ================================================================
    # V8 Upgrade #2 — Four-Level Unknowns
    # ================================================================

    # Coverage thresholds (percent of expected signal volume per domain).
    # A domain is "Known" if it has >60% of the average domain's signal
    # volume, "Known Unknown" if 10-60%, "Unknown Unknown" if <10%.
    # These thresholds are intentionally domain-relative (not absolute)
    # so the classification adapts to the org's overall signal volume —
    # a small org with 50 signals and a large org with 5000 signals both
    # get meaningful classifications.
    _KNOWN_THRESHOLD = 0.60       # >60% of avg → Known
    _KNOWN_UNKNOWN_MIN = 0.10     # 10-60% → Known Unknown
    # < 10% → Unknown Unknown

    # Emerging unknown window — signals newer than this that don't match
    # any existing learning object are "Emerging Unknowns".
    _EMERGING_WINDOW_DAYS = 7

    def classify_unknowns(self) -> dict[str, Any]:
        """Classify every organizational area into 4 epistemic levels.

        Returns:
            {
                known: list[area],              # coverage > 60%
                known_unknowns: list[area],     # 10-60% coverage
                unknown_unknowns: list[area],   # < 10% coverage
                emerging_unknowns: list[area],  # new pattern in last 7 days, no LO match
                summary: str,
                level_counts: {known, known_unknowns, unknown_unknowns, emerging_unknowns},
            }

        Each area item:
            {
                area: str,           # domain or topic name
                coverage: float,     # 0..1 (fraction of avg domain signal volume)
                signal_count: int,
                reason: str,         # why it's classified at this level
                detected_at: str,    # ISO timestamp — only for emerging_unknowns
            }
        """
        known: list[dict[str, Any]] = []
        known_unknowns: list[dict[str, Any]] = []
        unknown_unknowns: list[dict[str, Any]] = []
        emerging_unknowns: list[dict[str, Any]] = []

        # ─── Levels 1-3: classify every domain by signal coverage ───────
        domain_signal_counts = self._compute_domain_signal_counts()
        if domain_signal_counts:
            # Compute the average signal count per domain (the reference
            # volume). Domains above 60% of this are "Known", etc.
            avg_volume = sum(domain_signal_counts.values()) / max(len(domain_signal_counts), 1)
            for domain, count in domain_signal_counts.items():
                coverage = count / max(avg_volume, 1) if avg_volume > 0 else 0.0
                if coverage > self._KNOWN_THRESHOLD:
                    known.append({
                        "area": domain,
                        "coverage": round(coverage, 3),
                        "signal_count": count,
                        "reason": f"Coverage {coverage:.0%} of average domain volume. The organization has measured this area thoroughly.",
                    })
                elif coverage >= self._KNOWN_UNKNOWN_MIN:
                    known_unknowns.append({
                        "area": domain,
                        "coverage": round(coverage, 3),
                        "signal_count": count,
                        "reason": f"Coverage {coverage:.0%} of average. The organization knows it's under-measuring this area — instrument it.",
                    })
                else:
                    unknown_unknowns.append({
                        "area": domain,
                        "coverage": round(coverage, 3),
                        "signal_count": count,
                        "reason": f"Coverage {coverage:.0%} of average. The organization doesn't know it doesn't know this area. This is a blind spot.",
                    })

            # Sort each level by coverage descending (most-covered first
            # within Known, least-covered first within the lower levels —
            # the most-at-risk items surface to the top).
            known.sort(key=lambda x: x["coverage"], reverse=True)
            known_unknowns.sort(key=lambda x: x["coverage"], reverse=True)
            unknown_unknowns.sort(key=lambda x: x["coverage"])  # least-covered first

        # ─── Level 4: Emerging Unknowns ─────────────────────────────────
        # Signals from the last 7 days whose artifact + actor + type
        # combination doesn't match any existing learning object. These
        # are genuinely new — the org hasn't categorized them yet.
        emerging_unknowns = self._find_emerging_unknowns()

        # ─── Summary ────────────────────────────────────────────────────
        level_counts = {
            "known": len(known),
            "known_unknowns": len(known_unknowns),
            "unknown_unknowns": len(unknown_unknowns),
            "emerging_unknowns": len(emerging_unknowns),
        }
        summary = self._build_unknowns_summary(level_counts)

        return {
            "known": known,
            "known_unknowns": known_unknowns,
            "unknown_unknowns": unknown_unknowns,
            "emerging_unknowns": emerging_unknowns,
            "summary": summary,
            "level_counts": level_counts,
        }

    def _compute_domain_signal_counts(self) -> dict[str, int]:
        """Count signals per domain. Returns {domain: count}.

        Combines domains from the knowledge graph (domain_holders) with
        domains explicitly tagged in signal metadata. This ensures
        domains the org has holders for but no recent signals in are
        still classified (as Unknown Unknowns).
        """
        counts: Counter[str] = Counter()
        # Count from signals
        for s in self.signals:
            domain = s.metadata.get("domain", "")
            if domain:
                counts[domain] += 1
        # Also include domains from the knowledge graph that have 0 signals
        # (so they show up as Unknown Unknowns, not silently absent)
        try:
            for domain in self.model.knowledge.domain_holders.keys():
                if domain not in counts:
                    counts[domain] = 0
        except Exception as e:
            logger.debug("Knowledge graph domain scan failed: %s", e)
        return dict(counts)

    def _find_emerging_unknowns(self) -> list[dict[str, Any]]:
        """Find signals from the last 7 days that don't match any LO.

        A signal "matches" a learning object if the LO's signal_ids
        contains it, OR if the LO's artifacts list contains the signal's
        artifact, OR if the LO's entities list contains the signal's actor.
        A signal that matches none of these is an Emerging Unknown —
        something new is happening that the org hasn't categorized.
        """
        emerging: list[dict[str, Any]] = []
        try:
            now = datetime.now(timezone.utc)
            window_start = now - timedelta(days=self._EMERGING_WINDOW_DAYS)

            # Build a set of all artifacts + entities the org has already
            # categorized into learning objects.
            known_artifacts: set[str] = set()
            known_entities: set[str] = set()
            known_signal_ids: set = set()
            for lo in self.model.learning_objects.values():
                known_artifacts.update(lo.artifacts)
                known_entities.update(lo.entities)
                known_signal_ids.update(str(sid) for sid in lo.signal_ids)

            # Group recent unmatched signals by (type, domain) — each group
            # is one Emerging Unknown area.
            unmatched: Counter[tuple[str, str]] = Counter()
            unmatched_examples: dict[tuple[str, str], Any] = {}
            for s in self.signals:
                # Skip signals older than the window
                sig_time = s.timestamp
                if sig_time.tzinfo is None:
                    sig_time = sig_time.replace(tzinfo=timezone.utc)
                if sig_time < window_start:
                    continue
                # Skip signals that match an existing LO
                sig_id_str = str(s.signal_id) if hasattr(s, "signal_id") else ""
                if sig_id_str and sig_id_str in known_signal_ids:
                    continue
                if s.artifact and s.artifact in known_artifacts:
                    continue
                if s.actor and s.actor in known_entities:
                    continue
                # This signal is unmatched — count it
                sig_type = s.type.value if hasattr(s.type, "value") else str(s.type)
                sig_domain = s.metadata.get("domain", "uncategorized")
                key = (sig_type, sig_domain)
                unmatched[key] += 1
                if key not in unmatched_examples:
                    unmatched_examples[key] = s

            # Convert unmatched groups into Emerging Unknown items
            for (sig_type, sig_domain), count in unmatched.most_common(10):
                example = unmatched_examples.get((sig_type, sig_domain))
                detected_at = example.timestamp if example else now
                # Ensure detected_at is ISO format with timezone
                if detected_at.tzinfo is None:
                    detected_at = detected_at.replace(tzinfo=timezone.utc)
                emerging.append({
                    "area": f"{sig_domain}:{sig_type}",
                    "coverage": 0.0,  # Emerging unknowns have no coverage yet
                    "signal_count": count,
                    "reason": f"{count} new {'signal' if count == 1 else 'signals'} in the last {self._EMERGING_WINDOW_DAYS} days don't match any existing pattern. This is genuinely new — investigate before it becomes a pattern or an incident.",
                    "detected_at": detected_at.isoformat(),
                })
        except Exception as e:
            logger.debug("Emerging unknowns scan failed: %s", e)

        return emerging

    def _build_unknowns_summary(self, counts: dict[str, int]) -> str:
        """Build a human-readable summary of the 4-level classification."""
        k = counts["known"]
        kk = counts["known_unknowns"]
        uu = counts["unknown_unknowns"]
        eu = counts["emerging_unknowns"]
        parts = []
        if k:
            parts.append(f"{k} known")
        if kk:
            parts.append(f"{kk} known-unknown")
        if uu:
            parts.append(f"{uu} unknown-unknown")
        if eu:
            parts.append(f"{eu} emerging")
        if not parts:
            return "The organization's epistemic map is empty — connect providers to begin classification."
        summary = f"Maestro has mapped the organization's knowledge into {', '.join(parts)} {'area' if sum(counts.values()) == 1 else 'areas'}."
        if uu > 0:
            summary += f" {uu} {'area is' if uu == 1 else 'areas are'} a blind spot — the org doesn't know it doesn't know."
        if eu > 0:
            summary += f" {eu} {'area is' if eu == 1 else 'areas are'} emerging — new and uncategorized."
        return summary

    # ================================================================
    # V8 Upgrade #3 — Conversational Curiosity
    # ================================================================

    # Max turns per topic. After turn 3, Maestro stops asking and creates
    # a human_context signal from the accumulated answers. This prevents
    # interrogation — the org teaches Maestro through a bounded conversation,
    # not an endless one.
    _MAX_TURNS = 3

    # In-memory conversation state, keyed by question_id. Each value is:
    #   {
    #     question_id: str,
    #     original_question: str,
    #     question_type: str,         # untested_assumption, unmeasured_domain, etc.
    #     domain: str,
    #     turns: list[{question: str, answer: str}],
    #     turn_count: int,
    #   }
    # This is intentionally in-memory (not persisted) — conversations are
    # ephemeral. The *signal* they produce IS persisted (via the caller's
    # live_ingest). If the server restarts mid-conversation, the user
    # re-answers; the cost is low and the simplicity is worth it.
    _conversations: dict[str, dict[str, Any]] = {}

    def follow_up(self, question_id: str, answer: str, original_question: str = "",
                  question_type: str = "", domain: str = "") -> dict[str, Any]:
        """Process a user's answer and either ask a follow-up or close the conversation.

        Args:
            question_id: The stable ID from generate() (e.g. "cq-unmeasured_domain-payments-0")
            answer: The user's answer to the current question
            original_question: The first question in the conversation (needed to
                               start a new conversation; ignored on subsequent turns)
            question_type: The question type (needed to start a new conversation)
            domain: The domain the question is about (needed to start a new conversation)

        Returns one of:
          - {"follow_up_question": str, "turn": int, "question_id": str, "understanding_updated": false}
          - {"understanding_updated": true, "signal_created": true, "signal_id": str, "turn": int, "question_id": str, "summary": str}

        The conversation is bounded at _MAX_TURNS (3). After the 3rd answer,
        Maestro creates a human_context signal from the accumulated Q&A and
        returns understanding_updated=true.

        Follow-up questions are context-aware — they reference the user's
        previous answer, not generic templates. This is the V8 litmus: the
        org teaches Maestro through conversation, building trust.
        """
        if not question_id or not answer or not answer.strip():
            return {
                "understanding_updated": False,
                "signal_created": False,
                "error": "question_id and answer are required",
            }

        answer = answer.strip()

        # Start or continue the conversation
        convo = self._conversations.get(question_id)
        if convo is None:
            # New conversation — must have original_question + type + domain
            if not original_question:
                return {
                    "understanding_updated": False,
                    "signal_created": False,
                    "error": "original_question is required to start a new conversation",
                }
            convo = {
                "question_id": question_id,
                "original_question": original_question,
                "question_type": question_type or "unknown",
                "domain": domain or "unknown",
                "turns": [],
                "turn_count": 0,
            }
            self._conversations[question_id] = convo

        # Record this turn
        current_turn_num = convo["turn_count"] + 1
        current_question = (
            convo["original_question"] if current_turn_num == 1
            else convo["turns"][-1]["question"]
        )
        convo["turns"].append({
            "turn": current_turn_num,
            "question": current_question,
            "answer": answer,
        })
        convo["turn_count"] = current_turn_num

        # If we've reached the max turns, close the conversation and create
        # the human_context signal.
        if current_turn_num >= self._MAX_TURNS:
            return self._close_conversation(convo)

        # Otherwise, generate a context-aware follow-up
        follow_up_question = self._generate_follow_up(convo)
        return {
            "follow_up_question": follow_up_question,
            "turn": current_turn_num + 1,  # the NEXT turn number
            "question_id": question_id,
            "understanding_updated": False,
            "signal_created": False,
        }

    def _generate_follow_up(self, convo: dict[str, Any]) -> str:
        """Generate a context-aware follow-up question.

        The follow-up references the user's previous answer(s) so the
        conversation feels like Maestro is actually listening. The
        generation is template-based per question_type, with the user's
        answer interpolated.
        """
        q_type = convo["question_type"]
        domain = convo["domain"]
        last_answer = convo["turns"][-1]["answer"]
        # Truncate the answer for interpolation (avoid giant questions)
        answer_snippet = last_answer[:120].rsplit(" ", 1)[0] if len(last_answer) > 120 else last_answer
        turn_num = convo["turn_count"]

        # Turn 2: dig deeper into the answer. Turn 3: ask for the
        # consequence/implication (this sets up the signal creation).
        if turn_num == 1:
            # First follow-up — clarify the answer
            if q_type == "unmeasured_domain":
                return (
                    f"You mentioned {answer_snippet}. Is that because nobody has time to "
                    f"measure the {domain} domain, or because the tools aren't in place to "
                    f"capture it? What would it take to start measuring?"
                )
            elif q_type == "untested_assumption":
                return (
                    f"Given that {answer_snippet}, do you think the assumption still holds, "
                    f"or has it drifted? When was the last time someone actually checked?"
                )
            elif q_type == "unexplained_pattern":
                return (
                    f"You said {answer_snippet}. Have you noticed any conditions that seem "
                    f"to trigger the pattern — time of quarter, team composition, specific "
                    f"types of work? What's your hypothesis?"
                )
            elif q_type == "repeated_bottleneck":
                return (
                    f"Given {answer_snippet}, is this person aware they're the bottleneck? "
                    f"Is it a knowledge gap (they're the only one who knows how), a process "
                    f"gap (everything routes to them), or a capacity gap (too much work)?"
                )
            else:
                return (
                    f"Interesting — {answer_snippet}. Can you say more about why that is? "
                    f"What's the underlying cause as you see it?"
                )
        else:
            # Turn 3 — ask about the consequence/implication. This answer
            # becomes the "so what" of the human_context signal.
            if q_type == "unmeasured_domain":
                return (
                    f"If the {domain} domain stays unmeasured, what's the risk? What could "
                    f"go wrong that we wouldn't see coming? And what would change if we "
                    f"started measuring it tomorrow?"
                )
            elif q_type == "untested_assumption":
                return (
                    f"If the assumption turns out to be wrong, what breaks? Who is affected? "
                    f"And if it's still right, what would confirm it so we can stop wondering?"
                )
            elif q_type == "unexplained_pattern":
                return (
                    f"If your hypothesis is correct, what should we do about it? And if it's "
                    f"wrong, what's the alternative explanation we should investigate?"
                )
            elif q_type == "repeated_bottleneck":
                return (
                    f"What would it take to unblock this — cross-training, process change, "
                    f"or hiring? And what happens if we do nothing (how long until it becomes "
                    f"critical)?"
                )
            else:
                return (
                    f"Given what you've shared, what should the organization do differently? "
                    f"And what's the cost of not acting on this?"
                )

    def _close_conversation(self, convo: dict[str, Any]) -> dict[str, Any]:
        """Close the conversation and create a human_context signal.

        The signal is a DECISION_SIGNAL with metadata.kind="human_context".
        It captures the full Q&A so the model can learn from it. The signal
        is added to the engine via the caller (the API route calls
        oem_state.live_ingest with the signal).
        """
        from maestro_oem.signal import ExecutionSignal, SignalType, SignalProvider
        from datetime import datetime, timezone

        # Build a human-readable summary of the conversation
        turns = convo["turns"]
        q_type = convo["question_type"]
        domain = convo["domain"]

        # The signal's artifact is a stable identifier for this conversation
        artifact = f"human-context:{convo['question_id']}"

        # The metadata captures the full conversation so it's auditable
        # and the model can reference it later.
        metadata = {
            "kind": "human_context",
            "question_id": convo["question_id"],
            "question_type": q_type,
            "domain": domain,
            "original_question": convo["original_question"],
            "turns": [
                {"turn": t["turn"], "question": t["question"], "answer": t["answer"]}
                for t in turns
            ],
            "turn_count": len(turns),
            # The "understanding" is the concatenation of answers — this is
            # what the model learns from. It's the human knowledge that
            # wasn't in the signal stream before.
            "understanding": " | ".join(t["answer"] for t in turns),
        }

        signal = ExecutionSignal(
            type=SignalType.DECISION_SIGNAL,
            timestamp=datetime.now(timezone.utc),
            actor="human-context@maestro",
            artifact=artifact,
            decision=True,  # This is a human-provided decision/knowledge
            confidence=1.0,  # Human-provided context is treated as verified
            metadata=metadata,
            provider=SignalProvider.UNKNOWN,
        )

        # Clean up the conversation state
        del self._conversations[convo["question_id"]]

        # Build a summary for the response
        summary = (
            f"Thank you. Understanding updated. "
            f"Maestro learned {len(turns)} things about the {domain} domain from this conversation. "
            f"The knowledge is now part of the organizational model."
        )

        return {
            "understanding_updated": True,
            "signal_created": True,
            "signal_id": str(signal.signal_id),
            "signal": signal,  # The caller (API route) ingests this into the model
            "turn": len(turns),
            "question_id": convo["question_id"],
            "summary": summary,
            "domain": domain,
            "question_type": q_type,
        }

    # ================================================================
    # Original curiosity question generators (unchanged)
    # ================================================================

    def _find_untested_assumptions(self) -> list[dict[str, Any]]:
        """Find assumptions with no supporting or contradicting evidence."""
        results = []
        try:
            # Access the assumption graph from the model
            # We check if the OEM state has assumptions via the routes
            from maestro_api.routes.oem import _get_assumption_graph
            graph = _get_assumption_graph()
            all_assumptions = graph.list_assumptions()
            for a in all_assumptions:
                supporting = len(a.get("supporting_signals", []))
                contradicting = len(a.get("contradicting_signals", []))
                if supporting == 0 and contradicting == 0:
                    statement = a.get("statement", "")
                    if len(statement) > 10:
                        # Clean truncation: cut at word boundary, no nested quotes
                        clean = statement.replace("'", "").replace('"', '')
                        if len(clean) > 80:
                            # Truncate at last space before 80 chars
                            clean = clean[:80].rsplit(' ', 1)[0]
                        results.append({
                            "question": f"Nobody has tested whether this assumption is still true: {clean}. Should we investigate?",
                            "type": "untested_assumption",
                            "domain": "assumptions",
                            "evidence": "0 supporting, 0 contradicting signals",
                            "urgency": "medium",
                        })
        except Exception as e:
            logger.debug("Untested assumptions scan failed: %s", e)

        return results[:2]

    def _find_unmeasured_domains(self) -> list[dict[str, Any]]:
        """Find knowledge domains with <3 signals — the org isn't watching."""
        results = []
        try:
            kg = self.model.knowledge
            domain_counts = {}
            for domain, holders in kg.domain_holders.items():
                # Count signals per domain
                count = sum(1 for s in self.signals if s.metadata.get("domain", "") == domain)
                domain_counts[domain] = count

            for domain, count in sorted(domain_counts.items(), key=lambda x: x[1]):
                if count < 3 and count > 0:
                    results.append({
                        "question": f"We've only seen {count} {'signal' if count == 1 else 'signals'} from the {domain} domain. Are we paying attention?",
                        "type": "unmeasured_domain",
                        "domain": domain,
                        "evidence": f"{count} signals in {domain}",
                        "urgency": "low" if count > 0 else "medium",
                    })
                elif count == 0:
                    results.append({
                        "question": f"The {domain} domain has zero signals. Is anyone working on this?",
                        "type": "unmeasured_domain",
                        "domain": domain,
                        "evidence": "0 signals",
                        "urgency": "medium",
                    })
        except Exception as e:
            logger.debug("Unmeasured domains scan failed: %s", e)

        return results[:2]

    def _find_unexplained_patterns(self) -> list[dict[str, Any]]:
        """Find laws with high evidence but no documented explanation."""
        results = []
        try:
            for law in self.model.laws.values():
                if law.evidence_count > 5 and not law.outcome:
                    results.append({
                        "question": f"A pattern has appeared {law.evidence_count} times but nobody has explained why. Should we investigate?",
                        "type": "unexplained_pattern",
                        "domain": "patterns",
                        "evidence": f"{law.evidence_count} signals, no documented outcome",
                        "urgency": "high" if law.evidence_count > 10 else "medium",
                    })
        except Exception as e:
            logger.debug("Unexplained patterns scan failed: %s", e)

        return results[:1]

    def _find_repeated_bottlenecks(self) -> list[dict[str, Any]]:
        """Find bottlenecks that keep recurring without resolution."""
        results = []
        try:
            bottleneck_actors = Counter()
            for s in self.signals:
                if s.metadata.get("bottleneck") or "bottleneck" in str(s.metadata.get("text", "")).lower():
                    if s.actor:
                        bottleneck_actors[s.actor] += 1

            for actor, count in bottleneck_actors.most_common(1):
                if count > 3:
                    results.append({
                        "question": f"{actor} has been a bottleneck {count} times. Nobody has investigated why. Should we?",
                        "type": "repeated_bottleneck",
                        "domain": "execution",
                        "evidence": f"{count} bottleneck signals",
                        "urgency": "high",
                    })
        except Exception as e:
            logger.debug("Repeated bottlenecks scan failed: %s", e)

        return results[:1]
