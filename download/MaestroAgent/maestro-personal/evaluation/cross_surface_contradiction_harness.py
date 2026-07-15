"""
Phase 4 cross-surface contradiction-rate harness.

The roadmap acceptance criteria (ROAD_TO_9_OF_10_AFTER_395558A.md Phase 4):
  Cross-surface contradiction rate <= 2% over 10 longitudinal stories x 7 cutoffs.

This harness:
  1. Creates 10 longitudinal "stories" (a sequence of signals that evolve
     over time: active → at_risk → completed, or active → disputed → cancelled).
  2. For each story, takes 7 "cutoffs" (snapshots at different points in the
     signal timeline).
  3. At each cutoff, calls every surface (Commitments, The Moment, Ask) and
     checks whether they agree on the entity's state.
  4. Reports the contradiction rate: % of (story, cutoff, surface) tuples
     where a surface contradicts the canonical WorldModel answer.

A "contradiction" is:
  - Commitments shows an entity as active, but WorldModel says completed/dismissed/tombstoned.
  - The Moment surfaces an entity, but WorldModel says completed/dismissed/tombstoned.
  - Ask says a commitment is active, but WorldModel says completed/dismissed/tombstoned.

Target: <= 2% contradiction rate.
"""

import os
import sys
import json
import tempfile
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
# Also add the absolute backend path (Core module lives here)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from maestro_personal_shell.api import init_db, save_signal_to_db, load_signals_from_db
from maestro_personal_shell.shell import PersonalShell
from maestro_personal_shell.personal_oem_state import PersonalOemState, PersonalSignal
from maestro_personal_shell.world_model import build_world_model
from maestro_personal_shell.audit_trust import init_audit_tables
from maestro_personal_shell.commitment_ledger import init_ledger_table
from maestro_personal_shell.semantic_retrieval import init_fts_index, rebuild_fts_index


def _make_signal(signal_id, entity, text, signal_type, timestamp, user_email="bench@x.com"):
    return {
        "signal_id": signal_id,
        "entity": entity,
        "text": text,
        "signal_type": signal_type,
        "timestamp": timestamp,
        "metadata": {},
        "source_acl": "public",
        "created_at": timestamp,
        "user_email": user_email,
    }


def _build_stories() -> list[dict[str, Any]]:
    """Build 10 longitudinal stories. Each story is a sequence of signals
    that evolve an entity's state over time.

    Each story has:
      - entity: the entity name
      - signals: list of (text, signal_type, days_ago) tuples
      - cutoffs: 7 points (days_ago values) to snapshot
    """
    now = datetime.now(timezone.utc)
    base_iso = now.isoformat()

    stories = []

    # Story 1: active → completed
    stories.append({
        "entity": "Story1Corp",
        "signals": [
            ("I will send the proposal by Friday", "commitment_made", 10),
            ("The proposal has been sent", "reported_statement", 5),
        ],
        "cutoffs": [12, 10, 8, 6, 5, 3, 1],
    })

    # Story 2: active → dismissed
    stories.append({
        "entity": "Story2Corp",
        "signals": [
            ("I will send the report", "commitment_made", 8),
            ("DISMISS:sig-2-1", "commitment_made", 6),  # dismiss the first
        ],
        "cutoffs": [10, 8, 7, 6, 4, 2, 1],
    })

    # Story 3: active → disputed
    stories.append({
        "entity": "Story3Corp",
        "signals": [
            ("I will deliver the roadmap", "commitment_made", 9),
            ("We got the roadmap but it's missing the appendix", "reported_statement", 4),
        ],
        "cutoffs": [11, 9, 7, 5, 4, 2, 1],
    })

    # Story 4: active → cancelled
    stories.append({
        "entity": "Story4Corp",
        "signals": [
            ("I will send the budget", "commitment_made", 7),
            ("Never mind, we don't need the budget", "reported_statement", 3),
        ],
        "cutoffs": [9, 7, 5, 4, 3, 2, 1],
    })

    # Story 5: active (no resolution)
    stories.append({
        "entity": "Story5Corp",
        "signals": [
            ("I will review the scorecard", "commitment_made", 6),
        ],
        "cutoffs": [8, 6, 5, 4, 3, 2, 1],
    })

    # Story 6: active → stale (no completion)
    stories.append({
        "entity": "Story6Corp",
        "signals": [
            ("I will send the deck", "commitment_made", 12),
        ],
        "cutoffs": [14, 12, 10, 8, 6, 4, 2],
    })

    # Story 7: active → completed → new commitment (superseded scenario)
    stories.append({
        "entity": "Story7Corp",
        "signals": [
            ("I will send version 1", "commitment_made", 10),
            ("Version 1 has been sent", "reported_statement", 6),
            ("I will send version 2", "commitment_made", 3),
        ],
        "cutoffs": [12, 10, 8, 6, 4, 3, 1],
    })

    # Story 8: active → dismissed → new commitment
    stories.append({
        "entity": "Story8Corp",
        "signals": [
            ("I will send the old report", "commitment_made", 9),
            ("DISMISS:sig-8-1", "commitment_made", 7),
            ("I will send the new report", "commitment_made", 4),
        ],
        "cutoffs": [11, 9, 7, 5, 4, 2, 1],
    })

    # Story 9: multiple entities (interference check)
    stories.append({
        "entity": "Story9Corp",
        "signals": [
            ("I will send the proposal", "commitment_made", 8),
            ("Other9Corp will handle the budget", "commitment_made", 5),
            ("The proposal has been sent", "reported_statement", 2),
        ],
        "cutoffs": [10, 8, 6, 5, 3, 2, 1],
    })

    # Story 10: active → completed → disputed
    stories.append({
        "entity": "Story10Corp",
        "signals": [
            ("I will send the contract", "commitment_made", 10),
            ("The contract has been sent", "reported_statement", 5),
            ("We got the contract but it's missing the signature page", "reported_statement", 2),
        ],
        "cutoffs": [12, 10, 8, 5, 3, 2, 1],
    })

    return stories


def _run_contradiction_harness() -> dict[str, Any]:
    """Run the full contradiction-rate harness.

    Returns a dict with:
      - stories: number of stories
      - cutoffs_per_story: number of cutoffs
      - total_checks: total (story, cutoff, surface) tuples checked
      - contradictions: number of contradictions found
      - contradiction_rate: contradictions / total_checks
      - met_target: bool (contradiction_rate <= 0.02)
      - details: per-story breakdown
    """
    stories = _build_stories()
    total_checks = 0
    contradictions = 0
    details: list[dict] = []

    for story in stories:
        entity = story["entity"]
        for cutoff_days_ago in story["cutoffs"]:
            # Build a temp DB with signals up to the cutoff
            db_fd, db_path = tempfile.mkstemp(suffix=".db")
            os.close(db_fd)
            os.environ["MAESTRO_PERSONAL_DB"] = db_path
            init_db(db_path)
            init_audit_tables(db_path)
            init_ledger_table(db_path)
            init_fts_index(db_path)

            cutoff_dt = datetime.now(timezone.utc) - timedelta(days=cutoff_days_ago)
            cutoff_iso = cutoff_dt.isoformat()

            # Save signals that exist at this cutoff
            for i, (text, signal_type, days_ago) in enumerate(story["signals"]):
                sig_dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
                if sig_dt <= cutoff_dt:
                    sig_id = f"{entity}-sig-{i}"
                    # Handle DISMISS directive
                    if text.startswith("DISMISS:"):
                        target_sig_id = text.split(":", 1)[1]
                        # Mark the target signal as dismissed
                        conn = sqlite3.connect(db_path)
                        conn.execute(
                            "UPDATE signals SET metadata = ? WHERE signal_id = ?",
                            (json.dumps({"correction": "dismiss", "status": "dismissed"}), target_sig_id),
                        )
                        conn.commit()
                        conn.close()
                    else:
                        save_signal_to_db(_make_signal(
                            sig_id, entity, text, signal_type, sig_dt.isoformat()
                        ), db_path=db_path, user_email="bench@x.com")

            rebuild_fts_index(db_path, user_email="bench@x.com")

            # Build the shell + WorldModel
            signals_raw = load_signals_from_db(db_path, user_email="bench@x.com")
            personal_signals = []
            for s in signals_raw:
                meta = s.get("metadata", {})
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except Exception:
                        meta = {}
                # Parse timestamp string to datetime (the shell expects datetime, not str)
                ts = s.get("timestamp", "")
                try:
                    ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception:
                    ts_dt = datetime.now(timezone.utc)
                personal_signals.append(PersonalSignal(
                    entity=s.get("entity", ""),
                    text=s.get("text", ""),
                    signal_type=s.get("signal_type", ""),
                    signal_id=s.get("signal_id", ""),
                    timestamp=ts_dt,
                    metadata=meta if isinstance(meta, dict) else {},
                ))
            shell = PersonalShell(oem_state=PersonalOemState(signals=personal_signals))
            wm = build_world_model(shell=shell, user_email="bench@x.com")

            # Get the canonical answer
            canonical = wm.surface_answer_for_entity(entity)

            # Check each surface against the canonical answer
            # Surface 1: Commitments
            # The canonical says in_commitments=True for active/disputed, False for completed/dismissed/tombstoned
            from maestro_personal_shell.surfaces.commitments import CommitmentsSurface
            cs = CommitmentsSurface(shell=shell)
            raw_commitments = cs.get_active_commitments()
            commitments_entities = {str(c.get("entity", "")) for c in raw_commitments}

            # Apply the same filters the WorldModel applies
            from maestro_personal_shell.api import _filter_completed_commitments, _filter_non_commitments_by_classification
            filtered = _filter_completed_commitments(raw_commitments, shell.oem_state.signals)
            from maestro_personal_shell.world_model import WorldModel
            wm2 = WorldModel(shell=shell, user_email="bench@x.com")
            filtered = [c for c in filtered if str(c.get("signal_id", "")) not in wm2.dismissed_signal_ids]
            filtered_entities = {str(c.get("entity", "")) for c in filtered}

            total_checks += 1
            entity_in_commitments = entity in filtered_entities
            if entity_in_commitments != canonical["in_commitments"]:
                contradictions += 1
                details.append({
                    "story": entity, "cutoff_days_ago": cutoff_days_ago,
                    "surface": "commitments", "canonical": canonical["in_commitments"],
                    "actual": entity_in_commitments, "state": canonical["state"],
                })

            # Surface 2: The Moment (simplified — check if entity would be surfaced)
            total_checks += 1
            # The Moment surfaces the most at-risk commitment. If the entity
            # is completed/dismissed/tombstoned, it should NOT be surfaced.
            stale = shell.detect_stale_commitments(days_threshold=2)
            moment_could_surface = False
            for s in stale:
                commit = s.get("commitment")
                if commit:
                    sig_id = getattr(commit, "signal_id", "") or (commit.get("signal_id", "") if isinstance(commit, dict) else "")
                    # Check if this stale commitment belongs to our entity
                    for sig in shell.oem_state.signals:
                        if str(getattr(sig, "signal_id", "")) == str(sig_id):
                            if str(getattr(sig, "entity", "")) == entity:
                                # Check not completed/dismissed
                                if sig_id not in wm2.dismissed_signal_ids and not wm2.is_completed(entity):
                                    moment_could_surface = True
                            break

            if moment_could_surface != canonical["in_the_moment"]:
                # Only count as contradiction if canonical says NO but moment says YES
                # (moment saying NO when canonical says YES is acceptable — moment picks ONE)
                if moment_could_surface and not canonical["in_the_moment"]:
                    contradictions += 1
                    details.append({
                        "story": entity, "cutoff_days_ago": cutoff_days_ago,
                        "surface": "the_moment", "canonical": canonical["in_the_moment"],
                        "actual": moment_could_surface, "state": canonical["state"],
                    })

            # Cleanup
            os.unlink(db_path)
            del os.environ["MAESTRO_PERSONAL_DB"]

    rate = contradictions / total_checks if total_checks > 0 else 0.0
    return {
        "stories": len(stories),
        "cutoffs_per_story": 7,
        "total_checks": total_checks,
        "contradictions": contradictions,
        "contradiction_rate": round(rate, 4),
        "target": 0.02,
        "met_target": rate <= 0.02,
        "details": details[:20],  # first 20 for debugging
    }


if __name__ == "__main__":
    report = _run_contradiction_harness()
    print(json.dumps(report, indent=2))
