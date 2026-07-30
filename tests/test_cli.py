"""Verify Typer CLI loads on Python 3.9+ without union-type evaluation errors."""

from typer.main import get_command

from webscraper.cli import app


def test_typer_command_loads() -> None:
    command = get_command(app)
    assert command is not None
    param_names = {param.name for param in command.params}
    assert "days" in param_names
    assert "dry_run" in param_names
