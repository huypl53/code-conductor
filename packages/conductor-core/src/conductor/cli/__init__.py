"""Conductor CLI entry point."""

import typer

from conductor.cli.commands.run import run
from conductor.cli.commands.status import status

app = typer.Typer(
    name="conductor",
    help="Conductor: AI agent orchestration",
    no_args_is_help=True,
)

app.command("run")(run)
app.command("status")(status)


def main() -> None:
    """Run the Conductor CLI."""
    app()
