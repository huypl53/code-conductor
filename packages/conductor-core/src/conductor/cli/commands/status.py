"""conductor status command — one-shot agent/task table from state.json."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from conductor.cli.display import _build_table
from conductor.state.manager import StateManager


def status(
    repo: str = typer.Option(".", "--repo", help="Path to repo root"),
) -> None:
    """Print a one-shot agent/task status table from state.json."""
    console = Console()
    conductor_dir = Path(repo) / ".conductor"
    state_path = conductor_dir / "state.json"

    if not conductor_dir.exists():
        console.print("No conductor state found.")
        return

    state_manager = StateManager(state_path)
    try:
        state = state_manager.read_state()
    except Exception:
        console.print("No conductor state found.")
        return

    table = _build_table(state)
    console.print(table)
