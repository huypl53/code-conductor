"""conductor run command — starts the orchestrator with live agent display."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from pathlib import Path

import typer
from rich.console import Console
from rich.live import Live

from conductor.cli.display import _build_table, _display_loop
from conductor.cli.input_loop import _input_loop
from conductor.orchestrator.escalation import HumanQuery
from conductor.orchestrator.orchestrator import Orchestrator
from conductor.state.manager import StateManager

_console = Console()


def run(
    description: str = typer.Argument(..., help="Feature description"),
    auto: bool = typer.Option(True, "--auto/--interactive", help="Run mode"),
    repo: str = typer.Option(".", "--repo", help="Path to repo root"),
    dashboard_port: int = typer.Option(None, "--dashboard-port", help="Start dashboard server on this port"),
) -> None:
    """Start the orchestrator for a feature description with live agent display."""
    asyncio.run(_run_async(description, auto=auto, repo=Path(repo).resolve(), dashboard_port=dashboard_port))


async def _run_async(
    description: str,
    *,
    auto: bool,
    repo: Path,
    dashboard_port: int | None = None,
) -> None:
    """Async implementation of the run command."""
    conductor_dir = repo / ".conductor"
    conductor_dir.mkdir(parents=True, exist_ok=True)

    state_manager = StateManager(conductor_dir / "state.json")
    human_out: asyncio.Queue[HumanQuery] = asyncio.Queue()
    human_in: asyncio.Queue[str] = asyncio.Queue()

    orchestrator = Orchestrator(
        state_manager=state_manager,
        repo_path=str(repo),
        mode="auto" if auto else "interactive",
        human_out=human_out,
        human_in=human_in,
    )

    if auto:
        orch_coro = orchestrator.run_auto(description)
    else:
        orch_coro = orchestrator.run(description)

    orch_task = asyncio.create_task(orch_coro)

    # Console for the input loop — stderr keeps it separate from Rich Live on stdout
    input_console = Console(stderr=True)

    # Optional dashboard server
    gather_extras: list[object] = []
    if dashboard_port is not None:
        import uvicorn

        from conductor.dashboard.server import create_app

        dashboard_app = create_app(conductor_dir / "state.json", orchestrator=orchestrator)
        config = uvicorn.Config(
            dashboard_app,
            host="127.0.0.1",
            port=dashboard_port,
            log_level="warning",
        )
        server = uvicorn.Server(config)
        gather_extras.append(server.serve())
        _console.print(f"Dashboard: http://127.0.0.1:{dashboard_port}")

    try:
        with Live(console=Console(stderr=False), refresh_per_second=4) as live:
            await asyncio.gather(
                _display_loop(live, state_manager, until=orch_task),
                _input_loop(
                    human_out,
                    human_in,
                    orchestrator,
                    state_manager=state_manager,
                    console=input_console,
                ),
                orch_task,
                *gather_extras,
            )
    except KeyboardInterrupt:
        orch_task.cancel()
        with suppress(asyncio.CancelledError):
            await orch_task
        _console.print("Interrupted. Shutting down...")
        # Note: asyncio.to_thread(input) cannot be cancelled from Python — the
        # thread blocks until Enter is pressed. The gather's CancelledError
        # propagation cleans up the _input_loop coroutine. This is acceptable
        # for CLI since the process exits anyway.

    # Print final status table
    try:
        final_state = state_manager.read_state()
        _console.print(_build_table(final_state))
    except Exception:
        pass
