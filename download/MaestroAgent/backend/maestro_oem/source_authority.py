"""H-05 fix: Source Authority Model — actor → authority_weight mapping.

The prior adversarial audit found (H-05):
> All signals of the same type carry equal evidentiary weight regardless
> of source authority. A CEO's Slack message carries the same evidentiary
> weight as a junior employee's message of the same signal type.

This module provides the SourceAuthorityModel — a configurable mapping
from actor emails to authority weights (0.0-1.0). The model is populated
from org chart data (P13: derived from evidence, not caller-supplied).

Authority levels (configurable):
  - executive (C-suite, VP): 0.9
  - senior (Staff+, Principal): 0.75
  - mid (Senior Engineer): 0.6
  - junior (Engineer, Intern): 0.3
  - unknown: 0.5 (neutral — never zero, P6 fail-closed)

Design principles:
  1. Authority is PER-ACTOR, not per-signal. The same person has the same
     authority in all their signals.
  2. Unknown actors get 0.5 (neutral). Never zero — that would silence
     new hires and external contributors.
  3. Authority modulates CONFIDENCE, not VISIBILITY. A low-authority
     signal is still ingested and still appears in evidence; it just
     contributes less to law/pattern promotion.
  4. The model is opt-in. If no model is configured, all signals carry
     default weight 0.5 (backward-compatible).

Usage:
    model = SourceAuthorityModel()
    model.load_from_org_chart([
        {"email": "cto@example.com", "role": "CTO", "level": "executive"},
        {"email": "intern@example.com", "role": "Intern", "level": "junior"},
    ])
    weight = model.get_authority_weight("cto@example.com")  # 0.9
    weight = model.get_authority_weight("unknown@example.com")  # 0.5

Wiring (P11):
    The OEMEngine.ingest() path calls SourceAuthorityModel to set
    authority_weight on each signal before processing. See engine.py.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# Default authority weights by org-chart level.
# These are configurable via SourceAuthorityModel(level_weights={...}).
DEFAULT_LEVEL_WEIGHTS: dict[str, float] = {
    "executive": 0.9,   # C-suite, VP, Director
    "senior": 0.75,     # Staff+, Principal, Senior
    "mid": 0.6,         # Mid-level engineer/PM
    "junior": 0.3,      # Junior, Intern
    "unknown": 0.5,     # Neutral — never zero (P6)
}

# Default weight for actors not in the org chart.
NEUTRAL_WEIGHT = 0.5


class SourceAuthorityModel:
    """Maps actor emails to authority weights based on org chart data.

    Authority is DERIVED from org chart data (P13), not caller-supplied
    per-signal. The model is populated via load_from_org_chart() or
    register().

    The model is opt-in. If not configured, get_authority_weight()
    returns NEUTRAL_WEIGHT (0.5) for all actors — backward-compatible
    with code that predates H-05.
    """

    def __init__(self, level_weights: dict[str, float] | None = None) -> None:
        self._actor_weights: dict[str, float] = {}
        self._level_weights = dict(level_weights) if level_weights else dict(DEFAULT_LEVEL_WEIGHTS)

    def register(self, actor: str, role: str = "", level: str = "unknown") -> None:
        """Register an actor with a role and level.

        The authority weight is derived from the level. If a custom
        weight is needed, use set_weight() directly.
        """
        weight = self._level_weights.get(level, NEUTRAL_WEIGHT)
        self._actor_weights[actor.lower()] = weight
        logger.debug("SourceAuthorityModel: registered %s as %s/%s → weight %.2f",
                     actor, role, level, weight)

    def set_weight(self, actor: str, weight: float) -> None:
        """Directly set an actor's authority weight (override level-based)."""
        self._actor_weights[actor.lower()] = max(0.0, min(1.0, weight))

    def get_authority_weight(self, actor: str) -> float:
        """Get the authority weight for an actor.

        Returns NEUTRAL_WEIGHT (0.5) for unknown actors — never zero.
        This is P6 fail-closed: we never silence a signal just because
        we don't know the actor's role.
        """
        if not actor:
            return NEUTRAL_WEIGHT
        return self._actor_weights.get(actor.lower(), NEUTRAL_WEIGHT)

    def load_from_org_chart(self, org_chart: list[dict[str, Any]]) -> None:
        """Load authority mappings from org chart data.

        Each entry should have:
          - email: the actor's email
          - role: human-readable role (e.g., "CTO", "Senior Engineer")
          - level: one of "executive", "senior", "mid", "junior", "unknown"

        This is P13: authority is DERIVED from org chart evidence,
        not caller-supplied per-signal.
        """
        for entry in org_chart:
            email = entry.get("email", "")
            role = entry.get("role", "")
            level = entry.get("level", "unknown")
            if email:
                self.register(email, role=role, level=level)

    def apply_to_signal(self, signal: Any) -> None:
        """Set authority_weight on a signal based on its actor.

        Mutates the signal in place. If the signal already has a
        non-default authority_weight (not 0.5), it is preserved —
        this allows explicit overrides for special cases.
        """
        if not hasattr(signal, "actor") or not hasattr(signal, "authority_weight"):
            return
        # Preserve explicit overrides (any weight that's not the default 0.5)
        if signal.authority_weight != 0.5:
            return
        signal.authority_weight = self.get_authority_weight(signal.actor)

    def apply_to_signals(self, signals: list[Any]) -> None:
        """Apply authority weights to a list of signals (batch)."""
        for sig in signals:
            self.apply_to_signal(sig)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the model for inspection/debugging."""
        return {
            "actor_weights": dict(self._actor_weights),
            "level_weights": dict(self._level_weights),
            "actor_count": len(self._actor_weights),
        }


# ─── Module-level singleton (lazy) ──────────────────────────────────────────
# The default model is empty (all actors get neutral weight). In production,
# OEMEngine loads org chart data into this model on startup.

_default_model: SourceAuthorityModel | None = None


def get_default_model() -> SourceAuthorityModel:
    """Get the default SourceAuthorityModel singleton."""
    global _default_model
    if _default_model is None:
        _default_model = SourceAuthorityModel()
    return _default_model


def set_default_model(model: SourceAuthorityModel) -> None:
    """Set the default SourceAuthorityModel (e.g., from org chart config)."""
    global _default_model
    _default_model = model
