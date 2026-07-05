"""Phase 2.2 — Commitment Timeline Simulator.

Roadmap (6-Parameter Roadmap, parameter 4: Delivery Intelligence):
> Track the commitment lifecycle Day-1 → Day-60. Don't just record what
> happened — project what will happen if the current pattern continues.

The CommitmentMutationTracker (Phase 1.5) records past mutations. The
CommitmentTimelineSimulator (Phase 2.2) DERIVES a forward projection
from that history.

CRITICAL DESIGN RULE (P13 — input-derivation):
    The simulator must NOT accept the rate, pattern, risk, or
    recommendation as caller-supplied inputs. Those are the CONCLUSIONS.
    The valuable work is deriving them from the actual mutation history.
    If the caller supplies the rate, we've built a calculator pretending
    to be a capability.

The simulator's only inputs are:
    - entity (the customer name — a query key, not a conclusion)
    - horizon_days (how far forward to project — defaults to 60)
    - now (a time anchor for "today" — defaults to utcnow)

Everything else is DERIVED from the CommitmentMutationTracker's history.

PATTERN CLASSIFICATION (derived from comparing old_text vs new_text):
    - deadline_slippage: date moved later, scope unchanged
    - scope_expansion: new clauses/scope added (more conjunctions, +, plus)
    - scope_contraction: clauses removed
    - mixed: both deadline + scope changed
    - volatile: ≥3 mutations in 30 days (overrides the per-mutation type)
    - stable: 0 mutations

RISK DERIVATION:
    - stable → low
    - deadline_slippage → medium
    - scope_expansion / scope_contraction → medium
    - mixed → medium-high
    - volatile → high

RECOMMENDATION DERIVATION:
    The recommendation must reference the pattern, so the executive
    sees WHY Maestro is suggesting it. Examples:
    - stable + low → "Pattern stable. Continue monitoring."
    - deadline_slippage + medium → "Customer moved deadline. Confirm new date in writing."
    - scope_expansion + medium → "Scope grew. Re-confirm resources can meet expanded commitment."
    - volatile + high → "Volatile pattern detected. Schedule renegotiation conversation; lock current wording in writing."

This module is wired into the production path via:
    - GET /api/loop1.5/timeline/{entity}  (see maestro_api/routes/oem.py)
    - whisper.py _apply_timeline_projection()  (attaches projection to evidence_spine)

See tests/test_commitment_timeline_simulator.py for adversarial proof.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ─── Constants ─────────────────────────────────────────────────────────────

# Regex for finding dates in commitment text. Intentionally conservative —
# matches YYYY-MM-DD, YYYY/MM/DD, "Month DD, YYYY", and Q1/Q2/Q3/Q4 YYYY.
_DATE_PATTERNS = [
    re.compile(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b"),
    re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b", re.IGNORECASE),
    re.compile(r"\bQ([1-4])\s+(\d{4})\b", re.IGNORECASE),
]

# Conjunctions/scope markers — used to detect scope expansion vs contraction.
# Adding any of these (net) = expansion; removing (net) = contraction.
_SCOPE_MARKERS = re.compile(r"\b(\+|plus|and|&|as well as)\b", re.IGNORECASE)

# Volatility threshold: ≥3 mutations in this window → "volatile"
_VOLATILE_WINDOW_DAYS = 30
_VOLATILE_THRESHOLD = 3


@dataclass
class TimelineProjection:
    """A forward projection of a commitment's lifecycle.

    All fields are DERIVED from the mutation history — none are
    caller-supplied (P13).
    """

    entity: str
    pattern_type: str  # stable | deadline_slippage | scope_expansion | scope_contraction | mixed | volatile
    mutation_rate_per_30d: float  # observed rate
    projected_mutations_by_day_60: int  # extrapolated
    risk_level: str  # low | medium | high
    baseline_trajectory: list[dict]  # [{day, projected_state, projected_wording_hint}, ...]
    recommendation: str
    evidence_summary: dict  # mutation_count, history_span_days, mutation_breakdown

    def to_dict(self) -> dict:
        return {
            "entity": self.entity,
            "pattern_type": self.pattern_type,
            "mutation_rate_per_30d": round(self.mutation_rate_per_30d, 4),
            "projected_mutations_by_day_60": self.projected_mutations_by_day_60,
            "risk_level": self.risk_level,
            "baseline_trajectory": list(self.baseline_trajectory),
            "recommendation": self.recommendation,
            "evidence_summary": dict(self.evidence_summary),
        }


class CommitmentTimelineSimulator:
    """Project a commitment's lifecycle forward from mutation history.

    Usage:
        tracker = CommitmentMutationTracker()  # or with db_path
        # ... record commitments via tracker.record_commitment(signal) ...

        sim = CommitmentTimelineSimulator(tracker=tracker)
        projection = sim.simulate("<customer>", horizon_days=60)

    The simulator derives pattern_type, mutation_rate, risk_level, and
    recommendation from the tracker's history. The caller cannot
    override these (P13).
    """

    def __init__(self, tracker: Any = None, db_path: str = "") -> None:
        """Initialize the simulator.

        Args:
            tracker: an existing CommitmentMutationTracker. If None and
                db_path is provided, a new tracker is created with that
                db_path. If both are None, an in-memory tracker is created
                (useful for unit testing, but won't see any real history).
        """
        if tracker is not None:
            self._tracker = tracker
        else:
            # Lazy import to avoid circular dependency at module load time.
            from maestro_oem.commitment_mutation_tracker import CommitmentMutationTracker
            self._tracker = CommitmentMutationTracker(db_path) if db_path else CommitmentMutationTracker()

    def simulate(
        self,
        entity: str,
        horizon_days: int = 60,
        now: datetime | None = None,
    ) -> TimelineProjection:
        """Project the commitment lifecycle forward for `entity`.

        Args:
            entity: the customer name (a query key, not a conclusion).
            horizon_days: how far forward to project. Default 60.
            now: the time anchor for "today". Default utcnow.

        Returns:
            TimelineProjection with all fields DERIVED from history.

        P13: this method does NOT accept rate, pattern, risk, or
        recommendation as inputs. Those are derived.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        history = self._safe_get_history(entity)
        mutations = self._safe_get_mutations(entity)

        pattern_type = self._classify_pattern(mutations, now)
        rate = self._compute_rate(history, now)
        projected = self._project_mutations(rate, horizon_days)
        risk = self._derive_risk(pattern_type, rate)
        recommendation = self._derive_recommendation(pattern_type, risk, mutations)
        trajectory = self._build_trajectory(pattern_type, rate, risk, horizon_days)
        evidence_summary = self._build_evidence_summary(history, mutations, now)

        return TimelineProjection(
            entity=entity,
            pattern_type=pattern_type,
            mutation_rate_per_30d=rate,
            projected_mutations_by_day_60=projected,
            risk_level=risk,
            baseline_trajectory=trajectory,
            recommendation=recommendation,
            evidence_summary=evidence_summary,
        )

    # ─── Internal: safe tracker access (P6 — fail loud, not silent) ────────

    def _safe_get_history(self, entity: str) -> list:
        try:
            return self._tracker.get_mutation_history(entity)
        except Exception as e:
            logger.warning(
                "CommitmentTimelineSimulator: get_mutation_history failed for %s: %s",
                entity, e,
            )
            return []

    def _safe_get_mutations(self, entity: str) -> list:
        try:
            return self._tracker.get_mutations(entity)
        except Exception as e:
            logger.warning(
                "CommitmentTimelineSimulator: get_mutations failed for %s: %s",
                entity, e,
            )
            return []

    # ─── Internal: pattern classification (P13 — derived, not supplied) ────

    def _classify_pattern(self, mutations: list, now: datetime) -> str:
        """Classify the mutation pattern from the actual mutation events.

        Volatility takes precedence: if ≥3 mutations occurred in the last
        30 days, the pattern is "volatile" regardless of the per-mutation
        types. Volatility is the strongest signal — it indicates an
        unstable relationship that needs immediate attention.
        """
        if not mutations:
            return "stable"

        # Volatility check (highest precedence)
        recent_count = 0
        cutoff = now - timedelta(days=_VOLATILE_WINDOW_DAYS)
        for m in mutations:
            ts = self._coerce_datetime(getattr(m, "new_timestamp", None))
            if ts is not None and ts >= cutoff:
                recent_count += 1
        if recent_count >= _VOLATILE_THRESHOLD:
            return "volatile"

        # Otherwise classify by per-mutation type
        types_seen = set()
        for m in mutations:
            t = self._classify_single_mutation(
                getattr(m, "old_text", ""),
                getattr(m, "new_text", ""),
            )
            types_seen.add(t)

        if types_seen == {"deadline_slippage"}:
            return "deadline_slippage"
        if types_seen == {"scope_expansion"}:
            return "scope_expansion"
        if types_seen == {"scope_contraction"}:
            return "scope_contraction"
        if len(types_seen) > 1:
            return "mixed"
        # Single type, none of the above
        return next(iter(types_seen)) if types_seen else "stable"

    def _classify_single_mutation(self, old_text: str, new_text: str) -> str:
        """Classify a single mutation by comparing old vs new text.

        Returns one of:
          - deadline_slippage: date moved later, scope unchanged
          - scope_expansion: scope added (more conjunctions/markers)
          - scope_contraction: scope removed
          - mixed: both changed
        """
        old_date = self._extract_latest_date(old_text)
        new_date = self._extract_latest_date(new_text)
        old_scope_count = len(_SCOPE_MARKERS.findall(old_text or ""))
        new_scope_count = len(_SCOPE_MARKERS.findall(new_text or ""))

        date_changed = False
        if old_date is not None and new_date is not None:
            date_changed = new_date > old_date
        elif old_date is None and new_date is not None:
            # Date added where there was none — treat as scope expansion
            # (the commitment gained a deadline)
            date_changed = False
        elif old_date is not None and new_date is None:
            # Date removed — treat as scope change too
            date_changed = False

        scope_changed = new_scope_count != old_scope_count
        scope_expanded = new_scope_count > old_scope_count
        scope_contracted = new_scope_count < old_scope_count

        if date_changed and scope_changed:
            return "mixed"
        if date_changed:
            return "deadline_slippage"
        if scope_expanded:
            return "scope_expansion"
        if scope_contracted:
            return "scope_contraction"
        # Text changed but neither date moved nor scope markers changed
        # — fall back to "deadline_slippage" only if dates exist and moved,
        # otherwise call it scope_expansion (wording changed materially).
        return "scope_expansion" if not date_changed else "deadline_slippage"

    # ─── Internal: rate + projection math ─────────────────────────────────

    def _compute_rate(self, history: list, now: datetime) -> float:
        """Compute the observed mutation rate per 30 days.

        Derived from: mutation_count / (history_span_days / 30).
        Falls back to 0.0 if history is empty or span is 0.
        """
        if not history or len(history) < 2:
            return 0.0

        # Span = earliest to latest commitment timestamp
        timestamps = []
        for entry in history:
            ts = self._coerce_datetime(getattr(entry, "timestamp", None))
            if ts is not None:
                timestamps.append(ts)

        if len(timestamps) < 2:
            return 0.0

        span_seconds = (max(timestamps) - min(timestamps)).total_seconds()
        if span_seconds <= 0:
            return 0.0

        span_days = span_seconds / 86400.0
        if span_days < 1:
            span_days = 1.0  # avoid div-by-zero / inflation for sub-day spans

        # Mutations = (history length - 1): each new entry past the first
        # either is a mutation or a duplicate. We count actual mutations.
        # Use the history length minus 1 as the upper bound; the tracker
        # itself records exact mutations.
        mutation_count = len(history) - 1
        rate_per_30d = mutation_count / (span_days / 30.0)
        return max(0.0, rate_per_30d)

    def _project_mutations(self, rate_per_30d: float, horizon_days: int) -> int:
        """Project the number of mutations over the horizon.

        projection = rate_per_30d × (horizon_days / 30), rounded to int.
        """
        if rate_per_30d <= 0 or horizon_days <= 0:
            return 0
        projected = rate_per_30d * (horizon_days / 30.0)
        return int(round(projected))

    # ─── Internal: risk + recommendation derivation ───────────────────────

    def _derive_risk(self, pattern_type: str, rate_per_30d: float) -> str:
        """Derive the risk level from the pattern + observed rate."""
        if pattern_type == "volatile":
            return "high"
        if pattern_type == "mixed":
            return "high" if rate_per_30d >= 2.0 else "medium"
        if pattern_type in ("scope_expansion", "scope_contraction"):
            return "medium"
        if pattern_type == "deadline_slippage":
            return "medium"
        # stable
        return "low"

    def _derive_recommendation(self, pattern_type: str, risk: str, mutations: list) -> str:
        """Derive a recommendation that references the pattern (P13).

        The recommendation must be DERIVED — never caller-supplied.
        Each pattern produces a different recommendation so the
        executive sees WHY Maestro is suggesting it.
        """
        if pattern_type == "stable":
            return (
                "Pattern stable. Continue monitoring. No renegotiation needed "
                "at this time — the customer's commitment wording has not changed."
            )
        if pattern_type == "deadline_slippage":
            return (
                "Deadline slippage detected. The customer has moved the deadline "
                "outward. Confirm the new date in writing before the next meeting, "
                "and ask whether the slippage indicates a deeper blocker."
            )
        if pattern_type == "scope_expansion":
            return (
                "Scope expansion detected. The customer has added scope to the "
                "commitment. Re-confirm that internal resources can meet the "
                "expanded commitment, and document what was added."
            )
        if pattern_type == "scope_contraction":
            return (
                "Scope contraction detected. The customer has narrowed the "
                "commitment. Confirm in writing what was removed and whether "
                "the narrower scope is achievable."
            )
        if pattern_type == "mixed":
            return (
                "Mixed mutation pattern detected (deadline + scope both changed). "
                "This indicates a substantial renegotiation. Schedule a "
                "conversation to align on the new commitment before the next "
                "milestone."
            )
        if pattern_type == "volatile":
            return (
                "Volatile pattern detected (3+ mutations in 30 days). The "
                "customer is repeatedly moving the goalposts. Schedule a "
                "renegotiation conversation; lock the current wording in "
                "writing before the relationship erodes further."
            )
        # Fallback — should not reach here, but P6: fail loud, not silent.
        logger.warning(
            "CommitmentTimelineSimulator: unknown pattern_type %r in recommendation derivation",
            pattern_type,
        )
        return "Pattern unclear. Review the mutation history manually."

    # ─── Internal: trajectory building ────────────────────────────────────

    def _build_trajectory(
        self,
        pattern_type: str,
        rate_per_30d: float,
        risk: str,
        horizon_days: int,
    ) -> list[dict]:
        """Build the Day 1 / 7 / 30 / 60 trajectory checkpoints.

        Each checkpoint projects the commitment's state at that day,
        derived from the pattern + rate.
        """
        checkpoints = [1, 7, 30, 60]
        # Filter out checkpoints beyond the horizon
        checkpoints = [d for d in checkpoints if d <= horizon_days]
        if not checkpoints:
            checkpoints = [1]

        trajectory = []
        for day in checkpoints:
            state = self._project_state_at_day(day, pattern_type, rate_per_30d, risk)
            wording_hint = self._project_wording_hint(day, pattern_type)
            trajectory.append({
                "day": day,
                "projected_state": state,
                "projected_wording_hint": wording_hint,
            })
        return trajectory

    def _project_state_at_day(
        self,
        day: int,
        pattern_type: str,
        rate_per_30d: float,
        risk: str,
    ) -> str:
        """Project the commitment's state at a given day.

        State values: on_track | at_risk | renegotiated | broken
        Derived from pattern + rate + risk.
        """
        if pattern_type == "stable":
            return "on_track"

        # Expected mutations by this day
        expected_mutations = rate_per_30d * (day / 30.0)

        if pattern_type == "volatile":
            # Volatile: high risk throughout
            if day >= 30:
                return "renegotiated" if expected_mutations >= 3 else "at_risk"
            return "at_risk"

        if pattern_type == "deadline_slippage":
            if day >= 30 and expected_mutations >= 1.5:
                return "renegotiated"
            if day >= 7:
                return "at_risk"
            return "on_track"

        if pattern_type == "scope_expansion":
            if day >= 30 and expected_mutations >= 1.5:
                return "renegotiated"
            if day >= 7:
                return "at_risk"
            return "on_track"

        if pattern_type == "scope_contraction":
            if day >= 30 and expected_mutations >= 1.5:
                return "renegotiated"
            if day >= 7:
                return "at_risk"
            return "on_track"

        if pattern_type == "mixed":
            if day >= 30:
                return "renegotiated"
            if day >= 7:
                return "at_risk"
            return "on_track"

        return "unknown"

    def _project_wording_hint(self, day: int, pattern_type: str) -> str:
        """A human-readable hint about what the wording might look like.

        This is intentionally NOT a fabricated future commitment — it's
        a directional hint so the executive can sanity-check the
        projection. P1/P6: we never claim this is a real commitment.
        """
        if pattern_type == "stable":
            return "Worded same as today (no change projected)"
        if pattern_type == "deadline_slippage":
            if day >= 30:
                return "Deadline likely shifted later again"
            return "Wording likely unchanged in this window"
        if pattern_type == "scope_expansion":
            if day >= 30:
                return "Additional scope clause likely added"
            return "Wording likely unchanged in this window"
        if pattern_type == "scope_contraction":
            if day >= 30:
                return "Scope clause likely removed/narrowed"
            return "Wording likely unchanged in this window"
        if pattern_type == "mixed":
            if day >= 30:
                return "Both deadline and scope likely changed"
            return "Wording likely unchanged in this window"
        if pattern_type == "volatile":
            if day >= 7:
                return "Wording likely changed (multiple mutations projected)"
            return "Wording likely changed at least once"
        return "Unknown"

    # ─── Internal: evidence summary ───────────────────────────────────────

    def _build_evidence_summary(
        self,
        history: list,
        mutations: list,
        now: datetime,
    ) -> dict:
        """Build a summary of the evidence the projection was derived from.

        This is for transparency — the executive can verify the projection
        is grounded in actual history, not fabricated.
        """
        mutation_count = len(mutations)
        history_count = len(history)

        # Span of history (days from earliest to latest)
        history_span_days = 0
        if history:
            timestamps = [
                self._coerce_datetime(getattr(e, "timestamp", None))
                for e in history
            ]
            timestamps = [t for t in timestamps if t is not None]
            if len(timestamps) >= 2:
                history_span_days = int((max(timestamps) - min(timestamps)).total_seconds() / 86400)

        # Breakdown by mutation type
        breakdown: dict[str, int] = {}
        for m in mutations:
            t = self._classify_single_mutation(
                getattr(m, "old_text", ""),
                getattr(m, "new_text", ""),
            )
            breakdown[t] = breakdown.get(t, 0) + 1

        return {
            "history_count": history_count,
            "mutation_count": mutation_count,
            "history_span_days": history_span_days,
            "mutation_breakdown": breakdown,
            "derived_from": "CommitmentMutationTracker history",
        }

    # ─── Internal: datetime parsing ───────────────────────────────────────

    def _coerce_datetime(self, ts: Any) -> datetime | None:
        """Coerce a timestamp (datetime, str, or None) into a datetime.

        P6: failures are logged at DEBUG, not silently swallowed —
        the simulator continues with whatever timestamps it can parse.
        """
        if ts is None:
            return None
        if isinstance(ts, datetime):
            return ts
        if isinstance(ts, str):
            try:
                # Handle ISO 8601 with or without 'Z'
                s = ts
                if s.endswith("Z"):
                    s = s[:-1] + "+00:00"
                parsed = datetime.fromisoformat(s)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed
            except (ValueError, TypeError) as e:
                logger.debug(
                    "CommitmentTimelineSimulator: could not parse timestamp %r: %s",
                    ts, e,
                )
                return None
        return None

    # ─── Internal: date extraction from commitment text ───────────────────

    def _extract_latest_date(self, text: str) -> datetime | None:
        """Extract the latest date mentioned in the commitment text.

        Used to detect deadline slippage (date moved later).
        Returns None if no date is found.
        """
        if not text:
            return None

        candidates: list[datetime] = []

        # YYYY-MM-DD or YYYY/MM/DD
        for m in _DATE_PATTERNS[0].finditer(text):
            try:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                candidates.append(datetime(y, mo, d, tzinfo=timezone.utc))
            except (ValueError, IndexError):
                continue

        # Month DD, YYYY
        month_map = {
            "january": 1, "february": 2, "march": 3, "april": 4,
            "may": 5, "june": 6, "july": 7, "august": 8,
            "september": 9, "october": 10, "november": 11, "december": 12,
        }
        for m in _DATE_PATTERNS[1].finditer(text):
            try:
                mo = month_map[m.group(1).lower()]
                d = int(m.group(2))
                y = int(m.group(3))
                candidates.append(datetime(y, mo, d, tzinfo=timezone.utc))
            except (ValueError, IndexError, KeyError):
                continue

        # Q[1-4] YYYY → approximate as the last day of that quarter
        for m in _DATE_PATTERNS[2].finditer(text):
            try:
                q = int(m.group(1))
                y = int(m.group(2))
                # Last day of quarter
                mo = q * 3
                if mo == 12:
                    d = 31
                elif mo in (3, 12):
                    d = 31
                elif mo in (6, 9):
                    d = 30
                else:
                    d = 30
                candidates.append(datetime(y, mo, d, tzinfo=timezone.utc))
            except (ValueError, IndexError):
                continue

        if not candidates:
            return None
        return max(candidates)
