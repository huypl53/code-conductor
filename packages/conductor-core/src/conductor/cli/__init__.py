"""Conductor CLI entry point."""

import asyncio
import os
from pathlib import Path

import typer
from rich.console import Console

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

_console = Console(highlight=False)


async def _run_chat_with_dashboard(
    resume_id: str | None,
    dashboard_port: int | None,
) -> None:
    """Run the chat session, optionally alongside a dashboard WebSocket server."""
    from conductor.cli.chat import ChatSession

    session = ChatSession(resume_session_id=resume_id)

    if dashboard_port is None:
        await session.run()
        return

    # Start the FastAPI dashboard server alongside the chat session.
    import uvicorn

    from conductor.dashboard.server import create_app

    conductor_dir = Path(os.getcwd()) / ".conductor"
    conductor_dir.mkdir(parents=True, exist_ok=True)
    state_path = conductor_dir / "state.json"

    dashboard_app = create_app(state_path, orchestrator=None)
    config = uvicorn.Config(
        dashboard_app,
        host="127.0.0.1",
        port=dashboard_port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    _console.print(f"Dashboard: http://127.0.0.1:{dashboard_port}")

    # Run chat and server concurrently; when the chat session ends, stop the server.
    chat_task = asyncio.create_task(session.run())
    server_task = asyncio.create_task(server.serve())

    try:
        # Wait for chat to complete; cancel the server when done
        done, pending = await asyncio.wait(
            [chat_task, server_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        # Gracefully stop server and cancel any remaining tasks
        server.should_exit = True
        for task in (chat_task, server_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(chat_task, server_task, return_exceptions=True)


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
    """Launch interactive chat when no subcommand is given."""
    if ctx.invoked_subcommand is not None:
        return

    from conductor.cli.chat import pick_session

    session_id = resume_id
    if resume and session_id is None:
        session_id = pick_session()
        if session_id is None:
            return

    asyncio.run(_run_chat_with_dashboard(session_id, dashboard_port))


app.command("run")(run)
app.command("status")(status)


def main() -> None:
    """Run the Conductor CLI."""
    app()
