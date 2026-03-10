"""Rich Live display module for conductor CLI."""

from __future__ import annotations

import asyncio

from rich.live import Live
from rich.table import Table
from rich.text import Text

from conductor.state.manager import StateManager
from conductor.state.models import ConductorState, TaskStatus

_STATUS_STYLES: dict[str, str] = {
    TaskStatus.PENDING: "dim",
    TaskStatus.IN_PROGRESS: "yellow",
    TaskStatus.COMPLETED: "green",
    TaskStatus.FAILED: "red",
    TaskStatus.BLOCKED: "orange3",
}


def _build_table(state: ConductorState) -> Table:
    """Build a Rich Table from a ConductorState.

    Columns: Agent (cyan), Role (magenta), Task, Status (bold).
    Each row represents a task. Unassigned tasks show '-' for agent/role.
    """
    table = Table(show_header=True, header_style="bold")
    table.add_column("Agent", style="cyan", no_wrap=True)
    table.add_column("Role", style="magenta")
    table.add_column("Task")
    table.add_column("Status", style="bold")

    # Build agent lookup by id
    agents_by_id = {agent.id: agent for agent in state.agents}

    for task in state.tasks:
        assigned_id = task.assigned_agent
        agent = agents_by_id.get(assigned_id) if assigned_id else None

        agent_name = agent.name if agent else "-"
        agent_role = agent.role if agent else "-"

        status_str = str(task.status)
        style = _STATUS_STYLES.get(status_str, "")
        status_text = Text(status_str, style=style)

        table.add_row(agent_name, agent_role, task.title, status_text)

    return table


async def _display_loop(
    live: Live,
    state_manager: StateManager,
    until: asyncio.Task,  # type: ignore[type-arg]
) -> None:
    """Async loop that polls state every 2 seconds and updates the Live display.

    Exits when the `until` task is done. Does one final refresh after the loop.
    """
    while not until.done():
        state = await asyncio.to_thread(state_manager.read_state)
        live.update(_build_table(state))
        await asyncio.sleep(2)

    # Final refresh after the orchestrator task completes
    state = await asyncio.to_thread(state_manager.read_state)
    live.update(_build_table(state))
