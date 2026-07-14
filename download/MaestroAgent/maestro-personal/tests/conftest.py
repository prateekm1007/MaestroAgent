"""conftest.py — set up sys.path so maestro_personal_shell + maestro_cognitive_council + no_dilution_guard are importable."""

import os
import sys
import pathlib

import pytest

# F8 fix: tests legitimately need to mint tokens for arbitrary emails
# (e.g. cross-user isolation tests need user A and user B). The production
# default is fail-closed; tests opt in via this env var.
os.environ.setdefault("MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL", "1")

# Add maestro-personal/src to path (the Personal shell package)
personal_src = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(personal_src) not in sys.path:
    sys.path.insert(0, str(personal_src))

# Add maestro-personal/tests to path (so no_dilution_guard is importable)
tests_dir = pathlib.Path(__file__).resolve().parent
if str(tests_dir) not in sys.path:
    sys.path.insert(0, str(tests_dir))

# Add backend/ to path so maestro_cognitive_council is importable
# (the Core lives in backend/maestro_cognitive_council/)
backend_dir = pathlib.Path(__file__).resolve().parents[2] / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))


# ---------------------------------------------------------------------------
# P20/P22 fix: reset LLM router + probe cache between every test.
#
# Without this, tests that mock or probe the LLM leave cached state in
# llm_bridge._router / _probe_cache that leaks into subsequent tests.
# This caused 9 LLM-related tests to fail when run in the full suite
# (they passed in isolation). The autouse fixture below ensures every
# test starts with a clean LLM state.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_llm_state_between_tests():
    """Reset LLM router + probe cache + rate-limit cooldown before each test.

    P20/P22 isolation: without this, tests that mock or probe the LLM leave
    cached state that leaks into subsequent tests. Also clears the ZAI
    rate-limit cooldown so tests don't skip due to a prior test's 429.
    """
    try:
        from maestro_personal_shell.llm_bridge import reset_llm_router, _router
        reset_llm_router()
        # Clear ZAI rate-limit cooldown if the router is a ZAIRouter
        if _router and hasattr(_router, '_rate_limited_until'):
            _router._rate_limited_until = 0.0
    except ImportError:
        pass  # llm_bridge not yet importable (early collection)
    yield
    try:
        from maestro_personal_shell.llm_bridge import reset_llm_router
        reset_llm_router()
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Test-isolation fix: give each test a FRESH temp DB.
#
# Without this, tests share the same SQLite DB file (MAESTRO_PERSONAL_DB),
# causing state pollution — signals seeded by one test appear in another
# test's queries. This caused 18 consent/whisper/LLM tests to fail when
# run in the full suite (they passed in isolation).
#
# The fixture sets MAESTRO_PERSONAL_DB to a fresh temp file before each
# test, ensuring no cross-test contamination.
# ---------------------------------------------------------------------------
import tempfile

@pytest.fixture(autouse=True)
def _fresh_db_per_test():
    """Give each test a fresh temp DB to prevent cross-test state pollution."""
    # Save the old DB path
    old_db = os.environ.get("MAESTRO_PERSONAL_DB")
    # Create a fresh temp DB
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="maestro_test_")
    tmp.close()
    os.environ["MAESTRO_PERSONAL_DB"] = tmp.name
    yield
    # Restore old DB path
    if old_db is not None:
        os.environ["MAESTRO_PERSONAL_DB"] = old_db
    else:
        os.environ.pop("MAESTRO_PERSONAL_DB", None)
    # Clean up temp file
    try:
        os.unlink(tmp.name)
    except OSError:
        pass
