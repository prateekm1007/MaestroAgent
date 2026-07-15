"""HIGH-1 + MEDIUM-2 regression tests.

HIGH-1: XSS in entity field — must be sanitized on ingest.
MEDIUM-2: Input length cap — entity ≤ 200 chars, text ≤ 10K chars.
S4: Empty entity/text rejected.
"""
import os
import sys
import pathlib
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "backend"))

os.environ["MAESTRO_PERSONAL_TOKEN"] = "high1-test-token"
os.environ["MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL"] = "1"
os.environ.pop("MAESTRO_PERSONAL_ENV", None)


def _fresh_client():
    """Fresh DB + reload api module so each test is isolated."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="high1_test_")
    tmp.close()
    os.environ["MAESTRO_PERSONAL_DB"] = tmp.name
    # HIGH1 fix: set TOKEN explicitly before reload — module-level assignment
    # is unreliable when multiple test files import in different orders
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "high1-test-token"
    os.environ["MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL"] = "1"
    import importlib
    from maestro_personal_shell import api as personal_api
    importlib.reload(personal_api)
    personal_api.init_db()
    from fastapi.testclient import TestClient
    return TestClient(personal_api.app)


def _login(client):
    r = client.post("/api/auth/login",
                    json={"password": "high1-test-token"})
    assert r.status_code == 200
    return r.json()["token"]


def test_xss_in_entity_is_sanitized():
    """HIGH-1: <script> tags in entity must NOT survive the round-trip."""
    c = _fresh_client()
    token = _login(c)
    h = {"Authorization": f"Bearer {token}"}

    r = c.post("/api/signals",
               json={"entity": "<script>alert(1)</script>",
                     "text": "test signal",
                     "signal_type": "reported_statement"},
               headers=h)
    assert r.status_code == 200, f"create failed: {r.status_code} {r.text}"

    r = c.get("/api/signals", headers=h)
    assert r.status_code == 200
    for sig in r.json():
        assert "<script>" not in sig["entity"], (
            f"HIGH-1 FAIL: XSS survived in entity: {sig['entity']!r}"
        )
        assert "<" not in sig["entity"], (
            f"HIGH-1 FAIL: angle bracket survived in entity: {sig['entity']!r}"
        )


def test_xss_in_text_is_sanitized():
    """Existing behavior — text was already sanitized. Verify it stays that way."""
    c = _fresh_client()
    token = _login(c)
    h = {"Authorization": f"Bearer {token}"}

    r = c.post("/api/signals",
               json={"entity": "TestEntity",
                     "text": "<script>alert('xss')</script> done",
                     "signal_type": "reported_statement"},
               headers=h)
    assert r.status_code == 200
    r = c.get("/api/signals", headers=h)
    for sig in r.json():
        assert "<script>" not in sig["text"], f"XSS survived in text: {sig['text']!r}"


def test_entity_length_cap():
    """MEDIUM-2: entity > 200 chars must be rejected (422)."""
    c = _fresh_client()
    token = _login(c)
    h = {"Authorization": f"Bearer {token}"}

    huge_entity = "x" * 201
    r = c.post("/api/signals",
               json={"entity": huge_entity, "text": "test",
                     "signal_type": "reported_statement"},
               headers=h)
    assert r.status_code == 422, f"201-char entity should be rejected, got {r.status_code}"


def test_text_length_cap():
    """MEDIUM-2: text > 10K chars must be rejected (422)."""
    c = _fresh_client()
    token = _login(c)
    h = {"Authorization": f"Bearer {token}"}

    huge_text = "x" * 10_001
    r = c.post("/api/signals",
               json={"entity": "TestEntity", "text": huge_text,
                     "signal_type": "reported_statement"},
               headers=h)
    assert r.status_code == 422, f"10K+1 char text should be rejected, got {r.status_code}"


def test_empty_entity_rejected():
    """S4: empty entity must be rejected (422)."""
    c = _fresh_client()
    token = _login(c)
    h = {"Authorization": f"Bearer {token}"}

    r = c.post("/api/signals",
               json={"entity": "", "text": "test",
                     "signal_type": "reported_statement"},
               headers=h)
    assert r.status_code == 422, f"empty entity should be rejected, got {r.status_code}"


def test_whitespace_only_entity_rejected():
    """S4: whitespace-only entity must be rejected after sanitization."""
    c = _fresh_client()
    token = _login(c)
    h = {"Authorization": f"Bearer {token}"}

    r = c.post("/api/signals",
               json={"entity": "   ", "text": "test",
                     "signal_type": "reported_statement"},
               headers=h)
    # Pydantic accepts whitespace as a non-empty string; we reject in the handler
    assert r.status_code in (422, 400), (
        f"whitespace entity should be rejected, got {r.status_code}"
    )


if __name__ == "__main__":
    test_xss_in_entity_is_sanitized()
    test_xss_in_text_is_sanitized()
    test_entity_length_cap()
    test_text_length_cap()
    test_empty_entity_rejected()
    test_whitespace_only_entity_rejected()
    print("HIGH-1 + MEDIUM-2 + S4 tests PASSED")
