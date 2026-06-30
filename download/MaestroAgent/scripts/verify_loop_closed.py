"""Live end-to-end verification that the learning loop is closed.

This is the exact test the auditor ran manually against commit 8f342f8 and
that failed (resolved=0, accuracy=0, brier=0.5). It:

  1. Starts a fresh server on a clean temp DB.
  2. GET /api/oem/recommendations   -> predictions auto-created.
  3. POST /api/oem/contradict        -> CEO agrees on a linked law.
  4. GET /api/oem/improvement        -> must show resolved>0, correct>0, brier!=0.5.
  5. POST /api/oem/predictions/resolve -> must NOT break, returns well-formed summary.

Run:  python scripts/verify_loop_closed.py
Exit 0 = loop is closed. Exit 1 = loop is broken.
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

# Ensure backend is importable
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

import uvicorn
from fastapi.testclient import TestClient


def main() -> int:
    # Hermetic temp environment
    tmp = Path(tempfile.mkdtemp(prefix="maestro_loop_"))
    os.environ["MAESTRO_APP_DIR"] = str(REPO)
    os.environ["MAESTRO_AUTH_DB"] = str(tmp / "auth.db")
    os.environ["MAESTRO_LEARNING_DB"] = str(tmp / "learning.db")
    os.environ["DATABASE_URL"] = f"file:{tmp / 'maestro.db'}"
    os.environ["MAESTRO_ADMIN_PASSWORD"] = "test"
    os.environ["MAESTRO_RATE_LIMIT_RPM"] = "10000"
    os.environ["MAESTRO_DEMO_SEED"] = "true"

    # Reset singletons
    from maestro_api.oem_state import oem_state, import_state
    oem_state._initialized = False
    oem_state.engine = None
    oem_state.decision_engine = None
    oem_state.evidence_graph = None
    oem_state.signals = []
    oem_state._live_signals_ingested = 0
    oem_state._contradiction_log = None
    import_state._initialized = False

    from maestro_api.main import create_app
    app = create_app(db_path=str(tmp / "maestro.db"))

    with TestClient(app) as client:
        print("\n" + "=" * 70)
        print("CLOSED-LOOP VERIFICATION — commit under test")
        print("=" * 70)

        # 1. Surface recommendations -> auto-creates predictions
        r = client.get("/api/oem/recommendations")
        assert r.status_code == 200, r.text
        recs = r.json().get("recommendations", [])
        print(f"\n[1] GET /api/oem/recommendations  -> {len(recs)} recommendations surfaced")

        r = client.get("/api/oem/predictions")
        preds = r.json().get("predictions", [])
        pending = [p for p in preds if p["status"] == "pending"]
        print(f"    GET /api/oem/predictions      -> {len(preds)} predictions ({len(pending)} pending)")
        assert pending, "Recommendations did not auto-create pending predictions"

        # 2. Baseline improvement dashboard (should show resolved=0, brier=0.5)
        r = client.get("/api/oem/improvement")
        baseline = r.json()
        print(f"\n[2] BASELINE /api/oem/improvement:")
        print(f"    resolved={baseline['summary']['resolved']}, "
              f"correct={baseline['summary']['correct']}, "
              f"brier={baseline['calibration'].get('brier_score', 0.5)}")

        # 3. CEO agrees on a linked law
        rec = next((x for x in recs if x.get("linked_laws")), recs[0])
        target_law = rec["linked_laws"][0] if rec.get("linked_laws") else rec["title"]
        target_type = "law" if rec.get("linked_laws") else "recommendation"
        r = client.post("/api/oem/contradict", json={
            "target_type": target_type,
            "target_id": target_law,
            "action": "agree",
            "reasoning": "Live verification: this recommendation is right",
            "actor": "ceo@acme.com",
        })
        assert r.status_code == 200, r.text
        print(f"\n[3] POST /api/oem/contradict  -> agree on {target_type} '{target_law}'")
        print(f"    affected_laws: {r.json().get('affected_laws', [])}")

        # 4. Improvement dashboard must now show the loop closed
        r = client.get("/api/oem/improvement")
        after = r.json()
        s = after["summary"]
        brier = after["calibration"].get("brier_score", 0.5)
        print(f"\n[4] AFTER /api/oem/improvement:")
        print(f"    resolved={s['resolved']}, correct={s['correct']}, "
              f"incorrect={s['incorrect']}, brier={brier}")
        print(f"    is_learning={after['improvement_evidence']['is_learning']}")
        print(f"    evidence: {after['improvement_evidence']['evidence']}")

        ok = True
        if s["resolved"] == 0:
            print("\n[FAIL] resolved=0 — /contradict did not resolve any predictions.")
            ok = False
        if s["correct"] == 0:
            print("\n[FAIL] correct=0 — agree feedback did not register as correct.")
            ok = False
        if brier == 0.5:
            print(f"\n[FAIL] brier=0.5 — calibration never updated (the auditor's exact finding).")
            ok = False

        # 5. Manual /resolve endpoint must still work (fallback path)
        r = client.post("/api/oem/predictions/resolve")
        assert r.status_code == 200, r.text
        rr = r.json()
        print(f"\n[5] POST /api/oem/predictions/resolve -> "
              f"checked={rr['predictions_checked']}, resolved={rr['predictions_resolved']}, "
              f"still_pending={rr['still_pending']}")

        print("\n" + "=" * 70)
        if ok:
            print("VERDICT: LOOP IS CLOSED.")
            print("  - Recommendations auto-create predictions  ✓")
            print("  - CEO feedback via /contradict resolves predictions  ✓")
            print("  - Calibration engine records outcomes (Brier != 0.5)  ✓")
            print("  - /improvement dashboard proves learning  ✓")
            print("=" * 70)
            return 0
        else:
            print("VERDICT: LOOP IS BROKEN — see [FAIL] lines above.")
            print("=" * 70)
            return 1


if __name__ == "__main__":
    sys.exit(main())
