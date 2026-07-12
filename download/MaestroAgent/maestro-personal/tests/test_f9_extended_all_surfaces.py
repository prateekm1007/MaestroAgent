"""F9 extended: dismissed signals must not appear in Briefing, the-moment,
or any surface that uses build_shell.

The F9 fix at the build_shell level filters dismissed/cancelled/completed
signals at load time, so every surface automatically gets the correction.
This test verifies the filter works for /api/briefing and /api/the-moment.
"""
import os
import sys
import pathlib
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "backend"))


def _fresh_client():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="f9ext_test_")
    tmp.close()
    os.environ["MAESTRO_PERSONAL_DB"] = tmp.name
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "f9ext-test-token"
    os.environ["MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL"] = "1"
    os.environ.pop("MAESTRO_PERSONAL_ENV", None)
    import importlib
    from maestro_personal_shell import api as personal_api
    importlib.reload(personal_api)
    personal_api.init_db()
    from fastapi.testclient import TestClient
    return TestClient(personal_api.app)


def _login(client):
    r = client.post("/api/auth/login", json={"password": "f9ext-test-token"})
    assert r.status_code == 200
    return r.json()["token"]


def test_dismissed_signal_not_in_the_moment():
    """F9 extended: a dismissed commitment must NOT appear as the-moment."""
    c = _fresh_client()
    token = _login(c)
    h = {"Authorization": f"Bearer {token}"}

    # Seed a strong commitment (high priority for the-moment)
    r = c.post("/api/signals",
               json={"entity": "AcmeCorp",
                     "text": "I will send AcmeCorp the $1M proposal by Friday",
                     "signal_type": "commitment_made"},
               headers=h)
    assert r.status_code == 200
    sig_id = r.json()["signal_id"]

    # Dismiss it
    r = c.post(f"/api/signals/{sig_id}/correct?action=dismiss", headers=h)
    assert r.status_code == 200

    # the-moment must NOT feature the dismissed commitment
    r = c.get("/api/the-moment", headers=h)
    assert r.status_code == 200
    body = r.json()
    if body.get("has_moment"):
        commit = body.get("commitment") or {}
        text = commit.get("text", "")
        assert "$1M proposal" not in text, (
            f"F9 FAIL: dismissed commitment appears in the-moment: {text!r}"
        )


def test_dismissed_signal_not_in_briefing():
    """F9 extended: a dismissed commitment must NOT appear in briefing."""
    c = _fresh_client()
    token = _login(c)
    h = {"Authorization": f"Bearer {token}"}

    r = c.post("/api/signals",
               json={"entity": "VendorZ",
                     "text": "I will pay VendorZ $1M by Friday",
                     "signal_type": "commitment_made"},
               headers=h)
    assert r.status_code == 200
    sig_id = r.json()["signal_id"]

    r = c.post(f"/api/signals/{sig_id}/correct?action=dismiss", headers=h)
    assert r.status_code == 200

    r = c.get("/api/briefing", headers=h)
    assert r.status_code == 200
    body = r.json()
    # Check all string fields in the briefing response
    body_str = str(body)
    assert "$1M" not in body_str, (
        f"F9 FAIL: dismissed commitment appears in briefing: {body_str[:300]}"
    )


def test_active_commitment_appears_in_the_moment():
    """Sanity: an active (non-dismissed) commitment should appear in the-moment."""
    c = _fresh_client()
    token = _login(c)
    h = {"Authorization": f"Bearer {token}"}

    # Seed an old commitment (high stale score → should be the-moment)
    from datetime import datetime, timezone, timedelta
    past_ts = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    c.post("/api/signals",
           json={"entity": "ImportantClient",
                 "text": "I will send ImportantClient the contract by Friday",
                 "signal_type": "commitment_made",
                 "timestamp": past_ts},
           headers=h)

    r = c.get("/api/the-moment", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body.get("has_moment") is True, (
        "F9 overfix: active commitment should produce a the-moment result"
    )


if __name__ == "__main__":
    test_dismissed_signal_not_in_the_moment()
    test_dismissed_signal_not_in_briefing()
    test_active_commitment_appears_in_the_moment()
    print("F9 extended tests PASSED")
