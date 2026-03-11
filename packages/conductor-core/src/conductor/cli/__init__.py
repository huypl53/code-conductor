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
def _default_callback(
    ctx: typer.Context,
    resume: str = typer.Option(
        None,
        "--resume",
        help="Resume a previous chat session by ID, or pass 'pick' to choose from recent sessions.",
    ),
) -> None:
    """Launch interactive chat when no subcommand is given."""
    if ctx.invoked_subcommand is not None:
        return

    from conductor.cli.chat import ChatSession, pick_session

    resume_id = resume

    # --resume pick  OR  --resume without a valid session ID triggers picker
    if resume is not None and (resume == "pick" or resume == ""):
        resume_id = pick_session()
        if resume_id is None:
            return

    session = ChatSession(resume_session_id=resume_id)
    asyncio.run(session.run())


app.command("run")(run)
app.command("status")(status)


def main() -> None:
    """Run the Conductor CLI."""
    app()
