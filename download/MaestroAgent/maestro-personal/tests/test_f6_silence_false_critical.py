"""F6 regression test: 'velocity is fine' must NOT trigger CRITICAL (legal).

The independent audit found:
    "Team standup notes: velocity is fine" → CRITICAL (legal)

Root cause: the legal keyword list contained the bare word "fine" as a
substring match, which matched the adjective "fine" in "velocity is fine".
"""
import os
import sys
import pathlib
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "backend"))

os.environ["MAESTRO_PERSONAL_TOKEN"] = "f6-test-token"
os.environ["MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL"] = "1"
os.environ.pop("MAESTRO_PERSONAL_ENV", None)


def _fresh_db():
    """Create a fresh temp DB for one test — ensures isolation."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="f6_test_")
    tmp.close()
    os.environ["MAESTRO_PERSONAL_DB"] = tmp.name
    # F6 fix: set TOKEN explicitly before reload — module-level assignment
    # is unreliable when multiple test files import in different orders
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "f6-test-token"
    os.environ["MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL"] = "1"
    return tmp.name


def _seed_and_get_whispers(signal_text, entity="TestCorp", signal_type="reported_statement"):
    """Seed a signal and return the whispers it generates (fresh DB)."""
    _fresh_db()
    from fastapi.testclient import TestClient
    from maestro_personal_shell import api as personal_api
    # Reload to pick up the new DB path
    import importlib
    importlib.reload(personal_api)
    personal_api.init_db()
    client = TestClient(personal_api.app)

    r = client.post("/api/auth/login", json={"password": "f6-test-token"})
    assert r.status_code == 200
    token = r.json()["token"]
    h = {"Authorization": f"Bearer {token}"}

    r = client.post("/api/signals",
                    json={"entity": entity, "text": signal_text, "signal_type": signal_type},
                    headers=h)
    assert r.status_code == 200, f"seed failed: {r.status_code} {r.text}"

    r = client.get("/api/whisper", headers=h)
    assert r.status_code == 200
    return r.json()


def test_velocity_is_fine_not_critical():
    """F6: 'velocity is fine' must NOT trigger a CRITICAL whisper."""
    whispers = _seed_and_get_whispers(
        "Team standup notes: velocity is fine, sprint on track"
    )
    for w in whispers:
        priority = w.get("priority", "").lower()
        title = (w.get("title", "") + " " + w.get("body", "")).lower()
        assert priority != "high" or "legal" not in title, (
            f"F6 FAIL: 'velocity is fine' triggered a high-priority legal whisper: {w}"
        )


def test_real_legal_keyword_still_detected():
    """Sanity: a real legal signal must still be detected as CRITICAL."""
    whispers = _seed_and_get_whispers(
        "Acme Corp filed a lawsuit against us yesterday"
    )
    high_priority = [w for w in whispers if w.get("priority") == "high"]
    assert len(high_priority) > 0, (
        "F6 overfix: real legal keyword 'lawsuit' no longer triggers CRITICAL"
    )


def test_bare_fine_in_non_legal_context_not_critical():
    """F6: 'the proposal looks fine' must NOT trigger CRITICAL."""
    whispers = _seed_and_get_whispers(
        "The proposal looks fine, we can proceed with the deal"
    )
    for w in whispers:
        if w.get("priority") == "high":
            title = (w.get("title", "") + " " + w.get("body", "")).lower()
            assert "legal" not in title and "lawsuit" not in title, (
                f"F6 FAIL: 'looks fine' triggered legal whisper: {w}"
            )


def test_regulatory_fine_still_detected():
    """Sanity: 'regulatory fine' phrase must still be detected as CRITICAL."""
    whispers = _seed_and_get_whispers(
        "The EU imposed a regulatory fine of 5M euros for GDPR violation"
    )
    high_priority = [w for w in whispers if w.get("priority") == "high"]
    assert len(high_priority) > 0, (
        "F6 overfix: 'regulatory fine' phrase no longer triggers CRITICAL"
    )


if __name__ == "__main__":
    test_velocity_is_fine_not_critical()
    test_real_legal_keyword_still_detected()
    test_bare_fine_in_non_legal_context_not_critical()
    test_regulatory_fine_still_detected()
    print("F6 tests PASSED")
