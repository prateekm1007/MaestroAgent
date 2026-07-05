"""CRITICAL-1 Phase 1: Trajectory route module (extracted from oem.py God file).

This is the proof-of-concept extraction prescribed by
docs/CRITICAL_1_GOD_FILE_REFACTOR.md (Phase 1). The trajectory endpoints
are the smallest, most self-contained route group (2 endpoints, minimal
helper dependencies), making them the ideal first extraction.

Endpoints in this module:
  - GET  /trajectory-intervention  — declining trajectories that need intervention
  - GET  /org-pattern              — detect recurring organizational pattern

The module defines its own APIRouter and is registered in oem.py via:
    from maestro_api.routes.trajectory_routes import router as trajectory_router
    router.include_router(trajectory_router, prefix="/api/oem")

Shared state (oem_state singleton) is imported from maestro_api.oem_state.
This is the pattern all future extractions should follow.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from maestro_api.oem_state import oem_state

router = APIRouter()


@router.get("/trajectory-intervention")
def get_trajectory_intervention() -> dict[str, Any]:
    """Declining trajectories that need intervention.

    V6 Spec #4 — weak signal → trajectory change → quiet intervention.
    Computes time_to_failure from slope. Proposes interventions with
    historical analogues.
    """
    from maestro_oem.trajectory_intervention import TrajectoryInterventionEngine
    engine = TrajectoryInterventionEngine(oem_state.model, oem_state.signals)
    return engine.assess()


@router.get("/org-pattern")
def get_organizational_pattern() -> dict[str, Any]:
    """Detect a recurring organizational pattern and suggest a law.

    CEO's 'Friday notification' (2026-07-03): Maestro notices a pattern
    over weeks and surfaces it as an organizational law suggestion.

    Example: 'Customers have raised pricing concerns 11 times. Suggested
    operating law: Address pricing proactively in every customer engagement.'

    Returns None if no significant pattern is detected.
    """
    from maestro_oem.trajectory_intervention import TrajectoryInterventionEngine
    engine = TrajectoryInterventionEngine(oem_state.model, oem_state.signals)
    pattern = engine.detect_organizational_pattern(min_occurrences=5)
    if pattern:
        return {"pattern": pattern, "suggestion": "Review as Law?"}
    return {"pattern": None}
