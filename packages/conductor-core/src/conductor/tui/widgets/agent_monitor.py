"""AgentMonitorPane -- right-side panel showing per-agent status.

Phase 32: static placeholder only.
Phase 35: wired to StateWatchWorker -- collapsible per-agent rows driven
          by AgentStateUpdated messages from a file-watching @work coroutine.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from textual import work
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Collapsible, Static

if TYPE_CHECKING:
    from conductor.tui.messages import AgentStateUpdated


class AgentPanel(Collapsible):
    """Collapsible panel for a single active agent."""

    def __init__(
        self,
        agent_id: str,
        agent_name: str,
        agent_status: str,
        task_title: str,
    ) -> None:
        super().__init__(
            title=f"{agent_name} -- {agent_status}",
            collapsed=True,
            id=f"agent-{agent_id}",
        )
        self._agent_id = agent_id
        self._task_title = task_title

    @property
    def agent_id(self) -> str:
        return self._agent_id

    def compose(self) -> ComposeResult:
        yield Static(self._task_title, id="panel-task")
        yield Static("", id="panel-activity")

    def update_status(
        self, agent_name: str, agent_status: str, task_title: str
    ) -> None:
        """Update panel title and task info for a still-active agent."""
        self.title = f"{agent_name} -- {agent_status}"
        try:
            self.query_one("#panel-task", Static).update(task_title)
        except Exception:
            pass


class AgentMonitorPane(VerticalScroll):
    """Right-side panel showing agent status via collapsible AgentPanel widgets.

    When ``state_path`` is provided, a ``@work`` coroutine watches the parent
    directory for state.json changes and posts ``AgentStateUpdated`` messages.
    When ``state_path`` is None (default), no watcher starts -- useful for tests
    that post messages directly.
    """

    DEFAULT_CSS = """
    AgentMonitorPane {
        width: 30;
        height: 1fr;
        background: $panel;
        border-left: solid $primary 20%;
        padding: 1 1;
    }
    AgentMonitorPane #monitor-heading {
        color: $text-muted;
        text-style: bold;
        text-align: center;
        width: 1fr;
        padding-bottom: 1;
    }
    AgentMonitorPane #monitor-empty {
        color: $text-muted;
        text-align: center;
        width: 1fr;
    }
    AgentMonitorPane AgentPanel {
        margin-bottom: 1;
    }
    """

    def __init__(
        self,
        state_path: Path | None = None,
        *,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._state_path = state_path

    def compose(self) -> ComposeResult:
        yield Static("Agents", id="monitor-heading")
        yield Static("No agents active", id="monitor-empty")

    def on_mount(self) -> None:
        if self._state_path is not None:
            self._watch_state(self._state_path)

    @work(exclusive=True, exit_on_error=False)
    async def _watch_state(self, state_path: Path) -> None:
        """Watch state.json parent directory and post AgentStateUpdated."""
        from watchfiles import awatch

        from conductor.state.manager import StateManager
        from conductor.tui.messages import AgentStateUpdated

        state_path.parent.mkdir(parents=True, exist_ok=True)

        async for changes in awatch(str(state_path.parent), debounce=200):
            changed_names = {Path(p).name for _, p in changes}
            if state_path.name not in changed_names:
                continue
            try:
                new_state = await asyncio.to_thread(
                    StateManager(state_path).read_state
                )
            except Exception:
                continue
            self.post_message(AgentStateUpdated(new_state))

    async def on_agent_state_updated(self, event: "AgentStateUpdated") -> None:
        """Diff agent panels against new state: mount, update, or remove."""
        from conductor.state.models import AgentStatus

        state = event.state

        # Build active agents dict (WORKING or WAITING only)
        active = {
            a.id: a
            for a in state.agents
            if a.status in (AgentStatus.WORKING, AgentStatus.WAITING)
        }

        # Build task lookup: assigned_agent -> task
        tasks = {t.assigned_agent: t for t in state.tasks if t.assigned_agent}

        # Remove panels for agents no longer active
        for panel in list(self.query(AgentPanel)):
            if panel.agent_id not in active:
                await panel.remove()

        # Mount new panels or update existing
        existing_ids = {p.agent_id for p in self.query(AgentPanel)}
        for agent_id, agent in active.items():
            task = tasks.get(agent_id)
            task_title = task.title if task else "(unknown task)"
            if agent_id not in existing_ids:
                await self.mount(
                    AgentPanel(
                        agent_id=agent_id,
                        agent_name=agent.name,
                        agent_status=str(agent.status),
                        task_title=task_title,
                    )
                )
            else:
                panel = self.query_one(f"#agent-{agent_id}", AgentPanel)
                panel.update_status(agent.name, str(agent.status), task_title)

        # Show/hide "No agents active"
        empty_label = self.query_one("#monitor-empty", Static)
        has_panels = len(self.query(AgentPanel)) > 0
        empty_label.display = not has_panels
