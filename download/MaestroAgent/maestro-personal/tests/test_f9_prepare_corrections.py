"""F9 regression test: Prepare must NOT list dismissed/corrected signals.

The independent audit found:
    Prepare still lists corrected false commitment 'Alice will pay $1M to VendorZ'
    after the user dismissed it.

Root cause: /api/prepare pulled entity_signals from shell.oem_state.signals
without applying _filter_corrected_signals. Dismissed/cancelled/completed
signals survived into the_forgotten / the_open_question / the_contradiction.
"""
import os
import sys
import pathlib
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "backend"))


def _fresh_client():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="f9_test_")
    tmp.close()
    os.environ["MAESTRO_PERSONAL_DB"] = tmp.name
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "f9-test-token"
    os.environ["MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL"] = "1"
    os.environ.pop("MAESTRO_PERSONAL_ENV", None)
    import importlib
    from maestro_personal_shell import api as personal_api
    importlib.reload(personal_api)
    personal_api.init_db()
    from fastapi.testclient import TestClient
    return TestClient(personal_api.app)


def _login(client):
    r = client.post("/api/auth/login", json={"password": "f9-test-token"})
    assert r.status_code == 200
    return r.json()["token"]


def test_dismissed_signal_not_in_prepare():
    """F9: after dismissing a signal, it must NOT appear in /api/prepare."""
    c = _fresh_client()
    token = _login(c)
    h = {"Authorization": f"Bearer {token}"}

    # Seed a commitment
    r = c.post("/api/signals",
               json={"entity": "VendorZ",
                     "text": "Alice will pay $1M to VendorZ by Friday",
                     "signal_type": "commitment_made"},
               headers=h)
    assert r.status_code == 200
    sig_id = r.json()["signal_id"]

    # Dismiss it
    r = c.post(f"/api/signals/{sig_id}/correct?action=dismiss", headers=h)
    assert r.status_code == 200, f"dismiss failed: {r.status_code} {r.text}"

    # Get prepare — the dismissed commitment should NOT appear
    r = c.get("/api/prepare", headers=h)
    assert r.status_code == 200
    for prep in r.json():
        forgotten = prep.get("the_forgotten", "")
        open_q = prep.get("the_open_question", "")
        contradiction = prep.get("the_contradiction", "")
        assert "$1M to VendorZ" not in forgotten, (
            f"F9 FAIL: dismissed commitment appears in the_forgotten: {forgotten!r}"
        )
        assert "$1M to VendorZ" not in open_q, (
            f"F9 FAIL: dismissed commitment appears in the_open_question: {open_q!r}"
        )
        assert "$1M to VendorZ" not in contradiction, (
            f"F9 FAIL: dismissed commitment appears in the_contradiction: {contradiction!r}"
        )


def test_active_commitment_still_in_prepare():
    """Sanity: a non-dismissed commitment should still appear in prepare."""
    c = _fresh_client()
    token = _login(c)
    h = {"Authorization": f"Bearer {token}"}

    c.post("/api/signals",
           json={"entity": "AcmeCorp",
                 "text": "I will send AcmeCorp the proposal by Friday",
                 "signal_type": "commitment_made"},
           headers=h)

    r = c.get("/api/prepare", headers=h)
    assert r.status_code == 200
    # AcmeCorp commitment should appear somewhere in prepare
    all_text = " ".join(
        p.get("the_forgotten", "") + " " + p.get("the_open_question", "") + " " + p.get("the_contradiction", "")
        for p in r.json()
    )
    assert "AcmeCorp" in all_text or "proposal" in all_text, (
        "F9 overfix: active commitment no longer appears in prepare"
    )


if __name__ == "__main__":
    test_dismissed_signal_not_in_prepare()
    test_active_commitment_still_in_prepare()
    print("F9 tests PASSED")
