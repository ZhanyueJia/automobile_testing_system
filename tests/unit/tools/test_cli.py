from __future__ import annotations

from click.testing import CliRunner

from tools import cli


def test_cli_version_uses_project_metadata() -> None:
    result = CliRunner().invoke(cli.main, ["--version"])

    assert result.exit_code == 0
    assert "automotive-test-framework" in result.output
    assert "1.0.0" in result.output


def test_cli_info_displays_framework_root() -> None:
    result = CliRunner().invoke(cli.main, ["info"])

    assert result.exit_code == 0
    assert "Framework root:" in result.output
    assert "Smoke tests:" in result.output


def test_cli_test_uses_default_smoke_args(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_pytest_main(args: list[str]) -> int:
        calls.append(args)
        return 0

    monkeypatch.setattr(cli.pytest, "main", fake_pytest_main)

    result = CliRunner().invoke(cli.main, ["test"])

    assert result.exit_code == 0
    assert calls == [["-m", "smoke", "-v"]]


def test_cli_test_forwards_pytest_args_and_exit_code(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_pytest_main(args: list[str]) -> int:
        calls.append(args)
        return 5

    monkeypatch.setattr(cli.pytest, "main", fake_pytest_main)

    result = CliRunner().invoke(cli.main, ["test", "-m", "p0", "--env", "ci"])

    assert result.exit_code == 5
    assert calls == [["-m", "p0", "--env", "ci"]]
