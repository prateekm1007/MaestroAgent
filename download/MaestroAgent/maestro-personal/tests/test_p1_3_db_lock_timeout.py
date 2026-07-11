"""
P1-3 regression test — Finding S8: "DB lock timeout."

THE BUG (independent product audit):
    SQLite connections had no busy_timeout set, causing 'database is
    locked' errors when concurrent requests tried to write simultaneously.

THE FIX:
    1. Created db_util.py with get_db_conn() helper that sets
       busy_timeout=5000ms + WAL journal mode on every connection.
    2. Replaced all sqlite3.connect() calls across 12 modules with
       get_db_conn() — 47 connection sites total.
    3. Added a 503 Retry-After exception handler in api.py for
       sqlite3.OperationalError("database is locked").

THE PROOF (this test):
    1. get_db_conn() sets busy_timeout PRAGMA to 5000
    2. get_db_conn() enables WAL journal mode
    3. is_database_locked_error correctly identifies lock errors
    4. The 503 handler returns Retry-After header on lock errors

Governance: P1 (execute), P20 (all call sites updated — 47/47 use
get_db_conn), P22 (integration test through REAL production paths).
"""

import sys
import os
import tempfile
import sqlite3
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


class TestGetDbConn:
    """get_db_conn must set busy_timeout and WAL mode."""

    def test_busy_timeout_set(self):
        """get_db_conn must set busy_timeout PRAGMA to 5000ms."""
        from maestro_personal_shell.db_util import get_db_conn
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn = get_db_conn(db_path)
            result = conn.execute("PRAGMA busy_timeout").fetchone()
            conn.close()
            assert result[0] == 5000, (
                f"busy_timeout should be 5000, got {result[0]}"
            )
        finally:
            os.unlink(db_path)

    def test_wal_mode_enabled(self):
        """get_db_conn must enable WAL journal mode for better concurrency."""
        from maestro_personal_shell.db_util import get_db_conn
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn = get_db_conn(db_path)
            result = conn.execute("PRAGMA journal_mode").fetchone()
            conn.close()
            assert result[0].lower() == "wal", (
                f"journal_mode should be 'wal', got {result[0]}"
            )
        finally:
            os.unlink(db_path)

    def test_custom_busy_timeout(self):
        """get_db_conn must respect custom busy_timeout parameter."""
        from maestro_personal_shell.db_util import get_db_conn
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn = get_db_conn(db_path, busy_timeout=10000)
            result = conn.execute("PRAGMA busy_timeout").fetchone()
            conn.close()
            assert result[0] == 10000, (
                f"busy_timeout should be 10000, got {result[0]}"
            )
        finally:
            os.unlink(db_path)


class TestIsDatabaseLockedError:
    """is_database_locked_error must correctly identify lock errors."""

    def test_identifies_database_locked(self):
        from maestro_personal_shell.db_util import is_database_locked_error
        exc = sqlite3.OperationalError("database is locked")
        assert is_database_locked_error(exc) is True

    def test_identifies_table_locked(self):
        from maestro_personal_shell.db_util import is_database_locked_error
        exc = sqlite3.OperationalError("database table is locked")
        assert is_database_locked_error(exc) is True

    def test_rejects_non_lock_error(self):
        from maestro_personal_shell.db_util import is_database_locked_error
        exc = sqlite3.OperationalError("no such table: signals")
        assert is_database_locked_error(exc) is False

    def test_rejects_non_sqlite_error(self):
        from maestro_personal_shell.db_util import is_database_locked_error
        exc = ValueError("not a database error")
        assert is_database_locked_error(exc) is False


class TestAllModulesUseGetDbConn:
    """P20: ALL sqlite3.connect calls must be replaced with get_db_conn.
    This is the call-site audit — grep for remaining raw connections."""

    def test_no_raw_sqlite3_connect_in_personal_shell(self):
        """No module in maestro_personal_shell should use raw
        sqlite3.connect() — all should use get_db_conn()."""
        import pathlib
        shell_dir = pathlib.Path(__file__).resolve().parents[1] / "src" / "maestro_personal_shell"
        violations = []
        for py_file in shell_dir.glob("*.py"):
            content = py_file.read_text()
            # Check for raw sqlite3.connect (not get_db_conn)
            for i, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                # Skip comments and the db_util.py definition itself
                if stripped.startswith("#") or "db_util.py" in str(py_file):
                    continue
                if "sqlite3.connect(" in stripped and "get_db_conn" not in stripped:
                    violations.append(f"{py_file.name}:{i}: {stripped}")
        assert not violations, (
            f"P1-3 P20 FAIL: {len(violations)} raw sqlite3.connect() calls "
            f"found (should use get_db_conn):\n" + "\n".join(violations)
        )


class TestDatabaseLockedHandler:
    """The 503 Retry-After handler must work when SQLite raises a lock error."""

    def test_503_returned_on_database_locked(self):
        """When a sqlite3.OperationalError('database is locked') is raised
        in an endpoint, the client must receive 503 + Retry-After header."""
        import importlib
        import maestro_personal_shell.api as api_module

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        os.environ["MAESTRO_PERSONAL_DB"] = db_path
        os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-p1-3"
        os.environ.pop("MAESTRO_PERSONAL_ENV", None)

        try:
            importlib.reload(api_module)
            api_module.init_db(db_path)

            from fastapi.testclient import TestClient
            client = TestClient(api_module.app)

            # Login
            resp = client.post("/api/auth/login", json={
                "user_email": "test-p1-3@test.com",
                "password": os.environ["MAESTRO_PERSONAL_TOKEN"],
            })
            headers = {"Authorization": f"Bearer {resp.json()['token']}"}

            # Patch load_signals_from_db to raise a database-locked error
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(
                    "maestro_personal_shell.api.load_signals_from_db",
                    lambda **kw: (_ for _ in ()).throw(
                        sqlite3.OperationalError("database is locked")
                    ),
                )
                resp = client.get("/api/signals", headers=headers)
                assert resp.status_code == 503, (
                    f"Expected 503 on database locked, got {resp.status_code}: {resp.text}"
                )
                assert resp.headers.get("Retry-After") == "2", (
                    f"Expected Retry-After=2 header, got {resp.headers.get('Retry-After')}"
                )
                assert "database_locked" in resp.json().get("error_type", ""), (
                    f"Expected error_type=database_locked, got: {resp.json()}"
                )
        finally:
            os.unlink(db_path)
            os.environ.pop("MAESTRO_PERSONAL_DB", None)
            os.environ.pop("MAESTRO_PERSONAL_TOKEN", None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
