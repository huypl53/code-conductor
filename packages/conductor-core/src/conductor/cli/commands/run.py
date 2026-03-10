"""conductor run command — starts the orchestrator with live agent display."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from pathlib import Path

import typer
from rich.console import Console
from rich.live import Live

from conductor.cli.display import _build_table, _display_loop
from conductor.orchestrator.orchestrator import Orchestrator
from conductor.state.manager import StateManager

_console = Console()


def run(
    description: str = typer.Argument(..., help="Feature description"),
    auto: bool = typer.Option(True, "--auto/--interactive", help="Run mode"),
    repo: str = typer.Option(".", "--repo", help="Path to repo root"),
) -> None:
    """Start the orchestrator for a feature description with live agent display."""
    asyncio.run(_run_async(description, auto=auto, repo=Path(repo).resolve()))


async def _run_async(description: str, *, auto: bool, repo: Path) -> None:
    """Async implementation of the run command."""
    conductor_dir = repo / ".conductor"
    conductor_dir.mkdir(parents=True, exist_ok=True)

    state_manager = StateManager(conductor_dir / "state.json")
    human_out: asyncio.Queue[object] = asyncio.Queue()
    human_in: asyncio.Queue[object] = asyncio.Queue()

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

    try:
        with Live(console=Console(stderr=False), refresh_per_second=4) as live:
            await asyncio.gather(
                _display_loop(live, state_manager, until=orch_task),
                orch_task,
            )
    except KeyboardInterrupt:
        orch_task.cancel()
        with suppress(asyncio.CancelledError):
            await orch_task
        _console.print("Interrupted. Shutting down...")

    # Print final status table
    try:
        final_state = state_manager.read_state()
        _console.print(_build_table(final_state))
    except Exception:
        pass
