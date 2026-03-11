"""Conductor CLI entry point."""

import os

import typer

# Unset CLAUDECODE so the SDK can spawn nested Claude Code sessions.
# Conductor is designed to run *inside* a Claude Code session (or standalone)
# and needs to launch sub-agents as child processes.
os.environ.pop("CLAUDECODE", None)

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
    resume: bool = typer.Option(
        False,
        "--resume",
        help="Resume a previous chat session (opens a picker to choose from recent sessions).",
    ),
    resume_id: str = typer.Option(
        None,
        "--resume-id",
        help="Resume a specific chat session by ID.",
    ),
    dashboard_port: int = typer.Option(
        None,
        "--dashboard-port",
        help="Start the dashboard WebSocket server on this port (e.g. 8000). "
             "Open the dashboard UI and point it at this port to see live agent status.",
    ),
) -> None:
    """Launch interactive TUI when no subcommand is given."""
    if ctx.invoked_subcommand is not None:
        return

    from conductor.cli.chat import pick_session
    from conductor.tui.app import ConductorApp

    session_id = resume_id
    if resume and session_id is None:
        session_id = pick_session()
        if session_id is None:
            return

    try:
        ConductorApp(resume_session_id=session_id, dashboard_port=dashboard_port).run()
    finally:
        # Restore terminal state if Textual exited uncleanly (crash, kill).
        # On clean exit, Textual already emits these -- idempotent to repeat.
        import sys
        sys.stdout.write("\033[?1003l\033[?1006l\033[?1000l")
        sys.stdout.flush()


app.command("run")(run)
app.command("status")(status)


def main() -> None:
    """Run the Conductor CLI."""
    app()
