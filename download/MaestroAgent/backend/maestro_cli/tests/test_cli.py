"""Smoke tests for maestro_cli — Typer-based CLI entrypoint."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from maestro_cli.main import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_app_is_constructible() -> None:
    assert app is not None


def test_help_exits_zero(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "maestro" in result.stdout.lower()


def test_version_command(runner: CliRunner) -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "maestro" in result.stdout.lower()
