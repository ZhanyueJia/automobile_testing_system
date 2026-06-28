"""
Command line interface for the Automotive Test Framework.
"""
from __future__ import annotations

import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import click
import pytest


FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent


def _get_version() -> str:
    try:
        return version("automotive-test-framework")
    except PackageNotFoundError:
        pyproject = FRAMEWORK_ROOT / "pyproject.toml"
        with open(pyproject, "rb") as f:
            return tomllib.load(f)["project"]["version"]


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version=_get_version(), prog_name="automotive-test-framework")
def main() -> None:
    """Automotive Test Framework command line tools."""


@main.command()
def info() -> None:
    """Show framework location and common test commands."""
    click.echo(f"Framework root: {FRAMEWORK_ROOT}")
    click.echo("Smoke tests: pytest -m smoke -v")
    click.echo("Cockpit tests: pytest test_cases/cockpit/ -v")


@main.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
def test(pytest_args: tuple[str, ...]) -> None:
    """Run pytest with optional extra arguments."""
    args = list(pytest_args) if pytest_args else ["-m", "smoke", "-v"]
    raise SystemExit(pytest.main(args))


if __name__ == "__main__":
    main()
