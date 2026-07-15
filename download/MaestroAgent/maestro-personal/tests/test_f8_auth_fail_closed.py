"""F8/S1 regression test: dev mode must NOT mint tokens for arbitrary emails
unless MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL=1 is explicitly set.

The independent audit found:
    POST /api/auth/login {"user_email":"attacker@evil.com","password":"$TOKEN"}
    → 200, token minted for attacker@evil.com (in dev mode)

This test verifies the fail-closed default.
"""
import os
import sys
import pathlib
import tempfile

# Set up paths
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "backend"))

# Save and restore env var so this test doesn't break other tests
_SAVED_ALLOW = os.environ.get("MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL")


def _setup_env(allow_arbitrary: bool):
    """Set env vars for one test scenario."""
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "f8-test-token"
    os.environ.pop("MAESTRO_PERSONAL_ENV", None)  # dev mode
    if allow_arbitrary:
        os.environ["MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL"] = "1"
    else:
        os.environ.pop("MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL", None)
    # Fresh DB
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="f8_test_")
    tmp.close()
    os.environ["MAESTRO_PERSONAL_DB"] = tmp.name


def _reload_api():
    """Reload the api module so it picks up the current env vars."""
    import importlib
    from maestro_personal_shell import api as personal_api
    importlib.reload(personal_api)
    personal_api.init_db()
    return personal_api


def test_dev_mode_rejects_arbitrary_email_by_default():
    """F8 fix: dev mode must NOT mint tokens for arbitrary emails."""
    _setup_env(allow_arbitrary=False)
    personal_api = _reload_api()
    from fastapi.testclient import TestClient
    client = TestClient(personal_api.app)

    # 1. Login as default user — should succeed
    r = client.post("/api/auth/login",
                    json={"password": "f8-test-token"})
    assert r.status_code == 200, f"Default login failed: {r.status_code} {r.text}"
    body = r.json()
    assert body["user_email"] == "default@personal.local", \
        f"Default login should mint default user, got: {body['user_email']}"

    # 2. Login as attacker@evil.com — must be REJECTED (403)
    r = client.post("/api/auth/login",
                    json={"password": "f8-test-token", "user_email": "attacker@evil.com"})
    assert r.status_code == 403, (
        f"F8 FAIL: arbitrary email minted in dev mode without opt-in. "
        f"Got status {r.status_code}: {r.text}"
    )

    # 3. Login with wrong password — must be 401
    r = client.post("/api/auth/login",
                    json={"password": "wrong-password"})
    assert r.status_code == 401


def test_dev_mode_allows_arbitrary_email_with_explicit_opt_in():
    """When MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL=1 is set, dev mode allows
    arbitrary email (for test environments)."""
    _setup_env(allow_arbitrary=True)
    personal_api = _reload_api()
    from fastapi.testclient import TestClient
    client = TestClient(personal_api.app)

    r = client.post("/api/auth/login",
                    json={"password": "f8-test-token", "user_email": "test@user.com"})
    assert r.status_code == 200, f"Opt-in login failed: {r.status_code} {r.text}"
    body = r.json()
    assert body["user_email"] == "test@user.com"


def teardown_module():
    """Restore env vars so other tests aren't affected."""
    if _SAVED_ALLOW is not None:
        os.environ["MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL"] = _SAVED_ALLOW
    else:
        os.environ.pop("MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL", None)


if __name__ == "__main__":
    test_dev_mode_rejects_arbitrary_email_by_default()
    test_dev_mode_allows_arbitrary_email_with_explicit_opt_in()
    print("F8 tests PASSED")
