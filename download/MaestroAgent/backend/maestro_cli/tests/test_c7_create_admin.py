"""C7 fix: admin bootstrap CLI — `maestro create-admin` command.

External auditor finding (AUDITOR-ERROR-2-ACKNOWLEDGMENT-EDC99C3):
> C7 STILL UNFIXED. maestro_cli/main.py has 8 commands, none create admin.
> Production with no users = no one can log in.

The fix: add `maestro create-admin --email --password --org-id` command
that creates an admin user in the AuthStore. This is the production
deployment bootstrap path — without it, a fresh production install has
no users and no one can log in.

Adversarial: written FIRST, watched FAIL, then fix applied (P2).
"""
from __future__ import annotations

import sys
import os
import tempfile
import pytest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def test_create_admin_command_exists():
    """C7: the `create-admin` command must exist in the CLI.

    Before the fix: maestro_cli/main.py had 8 commands (version/serve/run/
    resume/list/cost/config/doctor), none create admin.
    """
    from typer.testing import CliRunner
    from maestro_cli.main import app

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0, f"CLI --help failed: {result.output}"
    assert "create-admin" in result.output, \
        f"'create-admin' command must exist in the CLI. Available commands: {result.output}"


def test_create_admin_creates_user_in_auth_store():
    """C7 KEY TEST: `maestro create-admin --email --password` creates a user.

    This is the production deployment bootstrap path. A fresh production
    install has no users → no one can log in → the system is unusable
    until this command is run.
    """
    from typer.testing import CliRunner
    from maestro_cli.main import app
    from maestro_auth.models import AuthStore

    with tempfile.TemporaryDirectory() as tmpdir:
        auth_db = Path(tmpdir) / "auth.db"
        os.environ["MAESTRO_AUTH_DB"] = str(auth_db)

        runner = CliRunner()
        result = runner.invoke(app, [
            "create-admin",
            "--email", "admin@example.com",
            "--password", "test-password-123",
            "--display-name", "Test Admin",
        ])

        assert result.exit_code == 0, \
            f"create-admin failed: exit_code={result.exit_code}, output={result.output}"

        # Verify the user was created in the AuthStore
        store = AuthStore(str(auth_db))
        users = store.list_users(limit=10)
        assert len(users) >= 1, \
            f"create-admin should have created 1 user. Found {len(users)} users."
        admin = users[0]
        assert admin["email"] == "admin@example.com", \
            f"Admin email mismatch. Got: {admin['email']}"
        assert admin.get("is_admin") == 1 or admin.get("is_admin") is True, \
            f"User should be admin. Got: {admin.get('is_admin')}"

        # Cleanup
        del os.environ["MAESTRO_AUTH_DB"]


def test_create_admin_idempotent():
    """C7: running create-admin twice with the same email should not fail
    (idempotent — either updates the existing user or reports already exists).
    """
    from typer.testing import CliRunner
    from maestro_cli.main import app
    from maestro_auth.models import AuthStore

    with tempfile.TemporaryDirectory() as tmpdir:
        auth_db = Path(tmpdir) / "auth.db"
        os.environ["MAESTRO_AUTH_DB"] = str(auth_db)

        runner = CliRunner()
        # First run — creates the admin
        result1 = runner.invoke(app, [
            "create-admin",
            "--email", "admin@example.com",
            "--password", "test-password-123",
        ])
        assert result1.exit_code == 0, f"First create-admin failed: {result1.output}"

        # Second run — should not crash (idempotent or reports exists)
        result2 = runner.invoke(app, [
            "create-admin",
            "--email", "admin@example.com",
            "--password", "test-password-456",
        ])
        # Either exit_code 0 (updated) or non-zero with a clear message (already exists)
        # — but NOT a crash/traceback
        assert "Traceback" not in result2.output, \
            f"Second create-admin crashed with traceback: {result2.output}"

        # Verify still exactly 1 user with this email
        store = AuthStore(str(auth_db))
        users = store.list_users(limit=10)
        admin_users = [u for u in users if u["email"] == "admin@example.com"]
        assert len(admin_users) == 1, \
            f"Should have exactly 1 admin user. Found {len(admin_users)}."

        del os.environ["MAESTRO_AUTH_DB"]
