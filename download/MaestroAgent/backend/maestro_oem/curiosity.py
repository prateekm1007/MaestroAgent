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
