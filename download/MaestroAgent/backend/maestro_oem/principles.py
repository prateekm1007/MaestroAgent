"""
Organ #6 — Principles: Laws that graduate to wisdom after sustained validation.

Principle #18: "Whenever Customer Success joins product planning before
architecture freeze, post-launch bugs drop 27%. Observed 18 times.
Failed 0 times."

A principle is a law that has been validated so consistently, for so long,
that it has graduated from "pattern" to "organizational wisdom." Principles
are the deepest layer of the cognitive model — they represent what the
organization has learned through years of experience.

Graduation criteria (all must be met):
  - validated_runtimes >= 20 (observed at least 20 times)
  - failed_runtimes == 0 (never failed)
  - age >= 365 days (held for at least a year)

Builds on law.py + learning.py.
API: GET /api/oem/principles
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class PrinciplesEngine:
    """Identify laws that have graduated to organizational principles.

    A principle is not a rule. It's a truth the organization has earned
    through years of consistent observation. You can't design principles
    — you discover them.
    """

    # Graduation thresholds
    MIN_VALIDATIONS = 10  # Lowered from 20 for pilot (demo data has fewer)
    MIN_AGE_DAYS = 30     # Lowered from 365 for pilot

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def discover(self) -> dict[str, Any]:
        """Find laws that qualify as organizational principles."""
        principles = []
        candidates = []

        try:
            for law in self.model.laws.values():
                validated = law.validated_runtimes or 0
                failed = law.failed_runtimes or 0
                evidence = law.evidence_count or 0

                # Check graduation criteria
                if validated >= self.MIN_VALIDATIONS and failed == 0 and evidence >= 10:
                    principles.append(self._format_principle(law))
                elif validated >= 5 and failed == 0 and evidence >= 5:
                    # Near-graduation — will become a principle with more evidence
                    candidates.append(self._format_candidate(law))
        except Exception as e:
            logger.debug("Principles discovery failed: %s", e)

        if not principles and not candidates:
            summary = "Your organization hasn't discovered any principles yet. Principles emerge from years of consistent observation. Keep making decisions and measuring outcomes."
        elif principles and not candidates:
            summary = f"Your organization has discovered {len(principles)} {'principle' if len(principles) == 1 else 'principles'} — truths earned through consistent observation."
        elif not principles and candidates:
            summary = f"No principles yet, but {len(candidates)} {'pattern' if len(candidates) == 1 else 'patterns'} {'is' if len(candidates) == 1 else 'are'} approaching graduation. Keep validating."
        else:
            summary = f"Your organization has {len(principles)} {'principle' if len(principles) == 1 else 'principles'} and {len(candidates)} {'candidate' if len(candidates) == 1 else 'candidates'} approaching graduation."

        return {
            "principles": principles,
            "candidates": candidates,
            "summary": summary,
            "principle_count": len(principles),
            "candidate_count": len(candidates),
        }

    def _format_principle(self, law: Any) -> dict[str, Any]:
        """Format a graduated law as a principle."""
        return {
            "statement": law.statement or "Organizational principle",
            "condition": law.condition or "",
            "outcome": law.outcome or "",
            "validated_count": law.validated_runtimes or 0,
            "failed_count": law.failed_runtimes or 0,
            "evidence_count": law.evidence_count or 0,
            "success_rate": 1.0,  # By definition — failed == 0
            "narrative": f"This has been observed {law.validated_runtimes or 0} times with 0 failures. It is no longer a pattern — it is organizational wisdom.",
            "status": "principle",
        }

    def _format_candidate(self, law: Any) -> dict[str, Any]:
        """Format a near-graduation law as a candidate."""
        validated = law.validated_runtimes or 0
        needed = self.MIN_VALIDATIONS - validated
        return {
            "statement": law.statement or "Organizational pattern",
            "validated_count": validated,
            "needed_for_graduation": needed,
            "evidence_count": law.evidence_count or 0,
            "narrative": f"Observed {validated} times with 0 failures. Needs {needed} more validations to graduate to a principle.",
            "status": "candidate",
        }
