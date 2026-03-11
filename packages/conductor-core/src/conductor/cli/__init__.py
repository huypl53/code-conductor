"""Conductor CLI entry point."""

import asyncio

import typer

from conductor.cli.commands.run import run
from conductor.cli.commands.status import status

app = typer.Typer(
    name="conductor",
    help="Conductor: AI agent orchestration",
    invoke_without_command=True,
)


@app.callback(invoke_without_command=True)
def _default_callback(ctx: typer.Context) -> None:
    """Launch interactive chat when no subcommand is given."""
    if ctx.invoked_subcommand is not None:
        return

    from conductor.cli.chat import ChatSession

    session = ChatSession()
    asyncio.run(session.run())


app.command("run")(run)
app.command("status")(status)


def main() -> None:
    """Run the Conductor CLI."""
    app()
