"""F4 regression test: days_stale consistency + closure-only reset.

The independent audit found:
  - /api/commitments shows days_stale=0 for Alex's April promise
  - /the-one correctly flags Avery 76 days
  - Inconsistent staleness across surfaces

Root causes:
  1. /api/commitments used days_threshold=5; /the-one used days_threshold=2
  2. detect_stale_commitments treated ANY follow-up signal as resetting
     staleness — so a "team standup notes" follow-up closed a 90-day promise
"""
import os
import sys
import pathlib
import tempfile
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "backend"))

os.environ["MAESTRO_PERSONAL_TOKEN"] = "f4-test-token"
os.environ["MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL"] = "1"
os.environ.pop("MAESTRO_PERSONAL_ENV", None)


def _fresh_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="f4_test_")
    tmp.close()
    os.environ["MAESTRO_PERSONAL_DB"] = tmp.name
    # F4 fix: set TOKEN explicitly before reload — module-level assignment
    # is unreliable when multiple test files import in different orders
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "f4-test-token"
    os.environ["MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL"] = "1"


def _client_and_token():
    _fresh_db()
    import importlib
    from fastapi.testclient import TestClient
    from maestro_personal_shell import api as personal_api
    importlib.reload(personal_api)
    personal_api.init_db()
    client = TestClient(personal_api.app)
    r = client.post("/api/auth/login", json={"password": "f4-test-token"})
    assert r.status_code == 200
    return client, r.json()["token"]


def _seed_old_commitment(client, token, entity, days_ago):
    """Seed a commitment with a backdated timestamp."""
    h = {"Authorization": f"Bearer {token}"}
    past_ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    r = client.post("/api/signals",
                    json={"entity": entity,
                          "text": f"I will send {entity} the proposal by Friday",
                          "signal_type": "commitment_made",
                          "timestamp": past_ts},
                    headers=h)
    assert r.status_code == 200, f"seed failed: {r.status_code} {r.text}"


def _seed_followup(client, token, entity, text, signal_type="reported_statement"):
    h = {"Authorization": f"Bearer {token}"}
    r = client.post("/api/signals",
                    json={"entity": entity, "text": text, "signal_type": signal_type},
                    headers=h)
    assert r.status_code == 200


def test_old_commitment_with_unrelated_followup_is_stale():
    """F4: a 30-day-old commitment + 'team standup notes' follow-up must
    still be flagged as stale. The follow-up is NOT a closure signal."""
    c, token = _client_and_token()
    _seed_old_commitment(c, token, "Alex", days_ago=30)
    _seed_followup(c, token, "Alex", "Team standup notes: velocity is fine")

    h = {"Authorization": f"Bearer {token}"}
    r = c.get("/api/commitments", headers=h)
    assert r.status_code == 200
    comms = r.json()
    alex_comms = [x for x in comms if "Alex" in x.get("entity", "")]
    assert len(alex_comms) > 0, "Alex's commitment should appear"
    for x in alex_comms:
        assert x["days_stale"] >= 28, (
            f"F4 FAIL: Alex's 30-day-old commitment with non-closure follow-up "
            f"shows days_stale={x['days_stale']} (should be ~30)"
        )


def test_old_commitment_with_closure_followup_is_not_stale():
    """F4: when a closure signal arrives ('delivered the proposal'), the
    commitment should NOT be flagged stale."""
    c, token = _client_and_token()
    _seed_old_commitment(c, token, "Sam", days_ago=30)
    _seed_followup(c, token, "Sam", "I delivered the proposal to Sam yesterday")

    h = {"Authorization": f"Bearer {token}"}
    r = c.get("/api/commitments", headers=h)
    assert r.status_code == 200
    comms = r.json()
    # Sam's commitment should either not appear (filtered as completed) or
    # appear with days_stale=0 (closure acknowledged)
    sam_comms = [x for x in comms if "Sam" in x.get("entity", "")]
    for x in sam_comms:
        assert x["days_stale"] == 0, (
            f"F4 FAIL: Sam's commitment has closure signal but shows "
            f"days_stale={x['days_stale']} (should be 0)"
        )


def test_commitments_and_the_one_agree_on_staleness():
    """F4: /api/commitments and /api/commitments/the-one must use the same
    days_threshold. A 3-day-old commitment must appear stale in BOTH or NEITHER."""
    c, token = _client_and_token()
    _seed_old_commitment(c, token, "Pat", days_ago=3)

    h = {"Authorization": f"Bearer {token}"}
    r1 = c.get("/api/commitments", headers=h)
    r2 = c.get("/api/commitments/the-one", headers=h)
    assert r1.status_code == 200
    assert r2.status_code == 200

    list_stale = [x for x in r1.json() if "Pat" in x.get("entity", "") and x.get("days_stale", 0) > 0]
    the_one = r2.json()
    primary = the_one.get("primary")
    pat_in_primary = primary and "Pat" in primary.get("entity", "")
    pat_in_secondary = any("Pat" in x.get("entity", "") for x in (the_one.get("secondary") or []))

    list_has_pat_stale = len(list_stale) > 0
    the_one_has_pat = pat_in_primary or pat_in_secondary

    assert list_has_pat_stale == the_one_has_pat, (
        f"F4 FAIL: /api/commitments has Pat stale={list_has_pat_stale}, "
        f"but /the-one has Pat present={the_one_has_pat}"
    )


if __name__ == "__main__":
    test_old_commitment_with_unrelated_followup_is_stale()
    test_old_commitment_with_closure_followup_is_not_stale()
    test_commitments_and_the_one_agree_on_staleness()
    print("F4 tests PASSED")
