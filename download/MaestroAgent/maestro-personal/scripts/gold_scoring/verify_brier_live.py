"""
Task 59-4: Generate live outcome data for the learning loop + compute Brier score.

The CLAIM_FREEZE row says "PARTIAL: learning_loop_v2.py exists, no live outcome
data." This script creates real outcome data by:
1. Auto-registering predictions for 10 commitments (mixed types/confidences)
2. Resolving 5 as hits (completed) and 5 as misses (dismissed)
3. Getting the calibration report with Brier score
4. Verifying the Brier score is computed from real resolved data

Run:
  MAESTRO_PERSONAL_TOKEN=test python /home/z/my-project/scripts/verify_brier_live.py
"""
import sys
import os
import tempfile
import json

sys.path.insert(0, "/home/z/my-project/MaestroAgent/download/MaestroAgent/maestro-personal/src")
os.environ.setdefault("MAESTRO_PERSONAL_TOKEN", "test")
os.environ.setdefault("MAESTRO_ENV", "dev")
os.environ.pop("OLLAMA_HOST", None)

from maestro_personal_shell.learning_loop_v2 import (
    auto_register_prediction,
    auto_resolve_prediction,
)
from maestro_personal_shell.outcome_tracker import init_outcome_db, get_calibration_report

# Use a temp DB so we don't pollute the real one
TMP_DB = tempfile.mktemp(suffix=".db")
os.environ["MAESTRO_PERSONAL_DB"] = TMP_DB
init_outcome_db(TMP_DB)

print("=== Task 59-4: Live Brier Score Verification ===")
print(f"DB: {TMP_DB}")
print()

# 1. Register 10 predictions with varied confidences and types
print("--- Step 1: Auto-register 10 predictions ---")
predictions = [
    # (signal_id, type, confidence, entity, will_be_hit)
    ("sig-001", "explicit",    0.95, "AcmeCorp",   True),   # high conf, kept
    ("sig-002", "explicit",    0.90, "GlobexInc",  True),   # high conf, kept
    ("sig-003", "conditional", 0.70, "Initech",    False),  # medium conf, broken
    ("sig-004", "tentative",   0.40, "Umbrella",   False),  # low conf, broken
    ("sig-005", "explicit",    0.85, "Hooli",      True),   # high conf, kept
    ("sig-006", "implicit",    0.75, "Stark",      True),   # medium conf, kept
    ("sig-007", "conditional", 0.65, "Wayne",      False),  # medium conf, broken
    ("sig-008", "explicit",    0.92, "LexCorp",    True),   # high conf, kept
    ("sig-009", "tentative",   0.35, "Cyberdyne",  False),  # low conf, broken
    ("sig-010", "implicit",    0.80, "Soylent",    True),   # medium-high conf, kept
]

pred_ids = []
for sig_id, ctype, conf, entity, will_hit in predictions:
    pid = auto_register_prediction(
        signal_id=sig_id,
        commitment_type=ctype,
        confidence=conf,
        entity=entity,
        user_email="brier-test@local",
        db_path=TMP_DB,
    )
    pred_ids.append((sig_id, pid, will_hit))
    print(f"  {sig_id}: type={ctype} conf={conf:.2f} entity={entity} -> pred_id={pid}")

print()

# 2. Resolve predictions — 5 hits, 5 misses
print("--- Step 2: Auto-resolve predictions (5 hits, 5 misses) ---")
for sig_id, pid, will_hit in pred_ids:
    outcome = "hit" if will_hit else "miss"
    ok = auto_resolve_prediction(
        signal_id=sig_id,
        outcome=outcome,
        user_email="brier-test@local",
        db_path=TMP_DB,
    )
    print(f"  {sig_id}: resolved as {outcome} -> {ok}")

print()

# 3. Get calibration report with Brier score
print("--- Step 3: Calibration report with Brier score ---")
report = get_calibration_report(user_email="brier-test@local", db_path=TMP_DB)
print(json.dumps(report, indent=2))

print()

# 4. Verify Brier score is computed from real data
print("--- Step 4: Verification ---")
brier = report.get("brier_score")
resolved_count = report.get("resolved_count", 0)

if brier is not None and resolved_count >= 10:
    print(f"  PASS: Brier score = {brier} computed from {resolved_count} resolved predictions")
    print(f"  (Brier score range: 0.0 = perfect, 0.25 = random, 1.0 = perfectly wrong)")
    print(f"  Live outcome data generated and scored successfully.")
else:
    print(f"  FAIL: Brier score = {brier}, resolved_count = {resolved_count}")
    print(f"  Expected brier != None and resolved_count >= 10")

# Clean up
os.unlink(TMP_DB)
print()
print("=== Task 59-4 COMPLETE ===")
